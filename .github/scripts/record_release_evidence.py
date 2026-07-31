"""Run release checks and retain a private, checksum-addressed evidence record.

This driver deliberately builds in a disposable copy.  The repository's
gitignored ``dist/`` directory is a transient convenience, never the retained
release record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable


SOURCE_ROOT = Path(__file__).resolve().parents[2]
SENSITIVE_ENV_PARTS = {
    "ACCESS_KEY",
    "API_KEY",
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
    "INDEX_URL",
    "PRIVATE_KEY",
    "PASSWORD",
    "PASSWD",
    "PROXY",
    "SECRET",
    "SSH_AUTH_SOCK",
    "TOKEN",
}
TOKEN_PATTERNS = (
    (
        re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,})\b"
        ),
        "[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "[REDACTED]"),
    (
        re.compile(
            r"(?i)\b(token|password|passwd|secret|api[_-]?key)"
            r"(\s*[:=]\s*)([^\s,;]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(https?://)([^/@\s:]+):([^/@\s]+)@"),
        r"\1[REDACTED]@",
    ),
)


def _private_write(path: Path, payload: str) -> None:
    path.write_text(payload, encoding="utf-8")
    path.chmod(0o600)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=SOURCE_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _safe_environment() -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not any(part in name.upper() for part in SENSITIVE_ENV_PARTS)
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _sanitize(text: str, replacements: Iterable[tuple[str, str]]) -> str:
    for private, label in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if private:
            text = text.replace(private, label)
    for pattern, replacement in TOKEN_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"(?<![A-Za-z0-9])/(?:home|media)/[^/\s]+", "$PRIVATE_ROOT", text)
    text = re.sub(r"(?<![A-Za-z0-9])/tmp/[^/\s]+", "$TMP_ROOT", text)
    return text


def _copy_release_inventory(destination: Path) -> int:
    """Copy exactly tracked plus non-ignored untracked release inputs.

    This mirrors the artifact guard's source boundary. It excludes every
    ignored build/cache product without maintaining a second pattern list, and
    still retains an intentionally tracked file that matches a broad ignore
    rule. Missing tracked paths are working-tree deletions and are skipped; the
    release guard decides whether each deletion is allowed.
    """

    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=SOURCE_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    names = sorted(
        item.decode("utf-8", errors="strict")
        for item in completed.stdout.split(b"\0")
        if item
    )
    copied = 0
    destination.mkdir()
    for name in names:
        source = SOURCE_ROOT / name
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink() or not source.is_file():
            raise SystemExit(f"release input is not a regular file: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def _run(
    *,
    label: str,
    argv: list[str],
    cwd: Path,
    logs_dir: Path,
    ordinal: int,
    env: dict[str, str],
    replacements: list[tuple[str, str]],
) -> dict[str, object]:
    started = dt.datetime.now(dt.timezone.utc)
    before = time.monotonic()
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    duration = time.monotonic() - before
    sanitized_output = _sanitize(completed.stdout, replacements)
    effective_exit_code = completed.returncode
    record: dict[str, object] | None = None
    if label == "runtime_core_provenance" and effective_exit_code == 0:
        try:
            candidate = json.loads(sanitized_output)
        except json.JSONDecodeError as exc:
            effective_exit_code = 2
            sanitized_output += f"\nERROR: invalid JSON identity record: {exc}\n"
        else:
            if not isinstance(candidate, dict):
                effective_exit_code = 2
                sanitized_output += "\nERROR: Core identity record is not an object.\n"
            else:
                record = candidate
    log_name = f"{ordinal:02d}_{label}.log"
    command = shlex.join(argv)
    payload = (
        f"label: {label}\n"
        f"started_utc: {started.isoformat().replace('+00:00', 'Z')}\n"
        f"cwd: {_sanitize(str(cwd), replacements)}\n"
        f"command: {_sanitize(command, replacements)}\n"
        f"exit_code: {effective_exit_code}\n"
        f"duration_seconds: {duration:.3f}\n"
        "\n"
        f"{sanitized_output}"
    )
    _private_write(logs_dir / log_name, payload)
    print(f"{label}: exit {effective_exit_code} ({duration:.2f} s)")
    result: dict[str, object] = {
        "label": label,
        "command": _sanitize(command, replacements),
        "log": f"logs/{log_name}",
        "exit_code": effective_exit_code,
        "duration_seconds": round(duration, 3),
    }
    if record is not None:
        result["record"] = record
    return result


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in ("build", "coupfe", "numpy", "pytest", "scipy", "twine"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _setup_core_defaults() -> tuple[str, str, str]:
    """Read the public Core tuple that setup.sh declares by default."""

    text = (SOURCE_ROOT / "setup.sh").read_text(encoding="utf-8")
    values: list[str] = []
    for field in ("COUPFE_URL", "COUPFE_BRANCH", "COUPFE_REF"):
        matches = re.findall(
            rf'^{field}="\$\{{{field}:-([^}}\r\n]+)\}}"[ \t]*$',
            text,
            flags=re.MULTILINE,
        )
        if len(matches) != 1:
            raise SystemExit(f"setup.sh must declare exactly one default {field}")
        values.append(matches[0])
    url, branch, ref = values
    if url != "https://github.com/tengzhang48/CoupFE.git":
        raise SystemExit(f"setup.sh declares unexpected public Core URL {url!r}")
    if branch != "main":
        raise SystemExit(f"setup.sh declares unexpected public Core branch {branch!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise SystemExit("setup.sh Core ref must be one lowercase full 40-hex revision")
    return url, branch, ref


def _write_checksums(output: Path, artifacts: list[Path]) -> None:
    artifact_lines = [
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}" for path in artifacts
    ]
    _private_write(output / "SHA256SUMS", "\n".join(artifact_lines) + "\n")

    evidence_files = sorted(
        path
        for path in output.rglob("*")
        if path.is_file() and path.name != "EVIDENCE_SHA256SUMS"
    )
    evidence_lines = [
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}"
        for path in evidence_files
    ]
    _private_write(
        output / "EVIDENCE_SHA256SUMS",
        "\n".join(evidence_lines) + "\n",
    )


def _write_readme(
    *,
    output: Path,
    mode: str,
    status: str,
    branch: str,
    head: str,
    dirty: bool,
    results: list[dict[str, object]],
    artifacts: list[Path],
) -> None:
    publishable = mode == "release" and status == "passed" and not dirty
    lines = [
        "# CoupFE-EDA release evidence checkpoint",
        "",
        "Private review evidence; this directory is not part of the source distribution.",
        "",
        f"- Mode: `{mode}`",
        f"- Status: `{status}`",
        f"- Publishable result: `{str(publishable).lower()}`",
        f"- Source branch: `{branch}`",
        f"- Source HEAD: `{head}`",
        f"- Dirty source tree at start: `{str(dirty).lower()}`",
        "",
    ]
    if mode == "audit":
        lines.extend(
            [
                "Audit mode checks the maintained dependency-compatible test partition and",
                "uses the artifact guard's explicit unapproved-ref, untracked-file, and",
                "dirty-source overrides.",
                "It cannot authorize publication.",
                "",
            ]
        )
    lines.extend(["## Commands", ""])
    for result in results:
        lines.append(
            f"- `{result['label']}`: exit `{result['exit_code']}`; "
            f"log `{result['log']}`"
        )
    lines.extend(["", "## Artifacts", ""])
    if artifacts:
        for artifact in artifacts:
            lines.append(
                f"- `{artifact.relative_to(output).as_posix()}`: "
                f"`{_sha256(artifact)}`"
            )
    else:
        lines.append("- No artifacts were retained because the run stopped before a build.")
    lines.extend(
        [
            "",
            "`SHA256SUMS` covers the release artifacts. `EVIDENCE_SHA256SUMS`",
            "covers the artifacts, logs, manifest, README, and artifact sidecar.",
            "Complete combined command output is retained in `logs/`; local/private",
            "paths and recognizable credential patterns are redacted.",
            "",
        ]
    )
    _private_write(output / "README.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and retain a private CoupFE-EDA release-evidence checkpoint."
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new checkpoint directory outside the source worktree",
    )
    parser.add_argument(
        "--mode",
        choices=("release", "audit"),
        default="release",
        help=(
            "release requires a clean tree and all test tiers; audit permits the "
            "documented unapproved-Core-ref and untracked-file checker overrides"
        ),
    )
    args = parser.parse_args()

    output = args.output.expanduser().resolve()
    source = SOURCE_ROOT.resolve()
    if output == source or source in output.parents:
        parser.error("--output must be outside the source worktree")
    if output.exists():
        parser.error("--output must name a new, non-existing checkpoint directory")

    old_umask = os.umask(0o077)
    try:
        output.mkdir(parents=True, mode=0o700)
        output.chmod(0o700)
        logs_dir = output / "logs"
        artifacts_dir = output / "artifacts"
        logs_dir.mkdir(mode=0o700)
        artifacts_dir.mkdir(mode=0o700)
    finally:
        os.umask(old_umask)

    status_bytes = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=SOURCE_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    dirty = bool(status_bytes)
    branch = _git("branch", "--show-current") or "(detached)"
    head = _git("rev-parse", "HEAD")
    start_utc = dt.datetime.now(dt.timezone.utc)
    env = _safe_environment()
    results: list[dict[str, object]] = []
    retained_artifacts: list[Path] = []
    final_status = "failed"

    manifest: dict[str, object] = {
        "schema_version": 1,
        "project": "CoupFE-EDA",
        "mode": args.mode,
        "publishable": False,
        "started_utc": start_utc.isoformat().replace("+00:00", "Z"),
        "source": {
            "branch": branch,
            "head": head,
            "dirty": dirty,
            "porcelain_v1_z_sha256": hashlib.sha256(status_bytes).hexdigest(),
        },
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "packages": _package_versions(),
        },
        "commands": results,
    }
    _private_write(output / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    status_text = status_bytes.decode("utf-8", errors="replace").replace("\0", "\n")
    _private_write(output / "source-status.txt", status_text)

    if args.mode == "release" and dirty:
        results.append(
            {
                "label": "clean_tree_preflight",
                "command": "git status --porcelain=v1 -z",
                "log": "logs/00_clean_tree_preflight.log",
                "exit_code": 2,
                "duration_seconds": 0.0,
            }
        )
        _private_write(
            logs_dir / "00_clean_tree_preflight.log",
            "Release mode requires a clean tracked and untracked source tree.\n",
        )
    else:
        with tempfile.TemporaryDirectory(prefix="coupfe-eda-release-evidence-") as tmp:
            temporary = Path(tmp)
            build_root = temporary / "source"
            dist_root = temporary / "dist"
            _copy_release_inventory(build_root)
            dist_root.mkdir()
            home = str(Path.home().resolve())
            replacements = [
                (str(SOURCE_ROOT.resolve()), "$SOURCE_ROOT"),
                (str(output), "$EVIDENCE_ROOT"),
                (str(temporary), "$TEMP_ROOT"),
                (home, "$HOME"),
            ]
            core_url, core_branch, core_ref = _setup_core_defaults()
            runtime_core_checker = (
                SOURCE_ROOT / ".github/scripts/check_runtime_core.py"
            )
            wheel_smoke_checker = SOURCE_ROOT / ".github/scripts/smoke_wheel.py"
            commands: list[tuple[str, list[str], Path]] = [
                (
                    "python_environment",
                    [sys.executable, "-m", "pip", "freeze", "--all"],
                    SOURCE_ROOT,
                ),
                (
                    "runtime_core_provenance",
                    [
                        sys.executable,
                        str(runtime_core_checker),
                        "--expected-url",
                        core_url,
                        "--expected-branch",
                        core_branch,
                        "--expected-ref",
                        core_ref,
                        "--expected-root",
                        str(SOURCE_ROOT / ".deps/CoupFE"),
                    ],
                    SOURCE_ROOT,
                ),
                (
                    "packaging_tools_preflight",
                    [
                        sys.executable,
                        "-c",
                        (
                            "import build, importlib.metadata, twine; "
                            "print('build=' + importlib.metadata.version('build')); "
                            "print('twine=' + importlib.metadata.version('twine'))"
                        ),
                    ],
                    SOURCE_ROOT,
                ),
            ]
            if shutil.which("conda") and os.environ.get("CONDA_PREFIX"):
                commands.append(
                    (
                        "conda_environment",
                        ["conda", "list", "--explicit"],
                        SOURCE_ROOT,
                    )
                )
            commands.extend(
                [
                    (
                        "gate_harness",
                        [sys.executable, "-m", "eda_multiphysics.run"],
                        SOURCE_ROOT,
                    ),
                ]
            )
            if args.mode == "audit":
                commands.append(
                    (
                        "maintained_fast_tests",
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "-p",
                            "no:cacheprovider",
                            "eda_multiphysics",
                            "tests/test_integration_regressions.py",
                            "tests/test_tsv_device.py",
                            "tests/test_tsv_local_3d.py",
                        ],
                        SOURCE_ROOT,
                    )
                )
            else:
                commands.extend(
                    [
                        (
                            "default_tests",
                            [
                                sys.executable,
                                "-m",
                                "pytest",
                                "-q",
                                "-ra",
                                "-p",
                                "no:cacheprovider",
                            ],
                            SOURCE_ROOT,
                        ),
                        (
                            "toolchain_preflight",
                            [
                                sys.executable,
                                "-c",
                                (
                                    "import gmsh, mpi4py, petsc4py, shutil; "
                                    "assert shutil.which('gfortran'); "
                                    "assert shutil.which('mpirun')"
                                ),
                            ],
                            SOURCE_ROOT,
                        ),
                        (
                            "toolchain_tests",
                            [
                                sys.executable,
                                "-m",
                                "pytest",
                                "-q",
                                "-ra",
                                "-p",
                                "no:cacheprovider",
                                "-m",
                                "toolchain",
                            ],
                            SOURCE_ROOT,
                        ),
                    ]
                )
            commands.append(
                (
                    "build_sdist",
                    [
                        sys.executable,
                        "-m",
                        "build",
                        "--sdist",
                        "--outdir",
                        str(dist_root),
                        ".",
                    ],
                    build_root,
                )
            )

            ordinal = 1
            for label, argv, cwd in commands:
                result = _run(
                    label=label,
                    argv=argv,
                    cwd=cwd,
                    logs_dir=logs_dir,
                    ordinal=ordinal,
                    env=env,
                    replacements=replacements,
                )
                results.append(result)
                ordinal += 1
                if result["exit_code"] != 0:
                    break

            if results and results[-1]["exit_code"] == 0:
                sdists = sorted(dist_root.glob("*.tar.gz"))
                if len(sdists) != 1:
                    result = {
                        "label": "sdist_inventory",
                        "command": "require exactly one .tar.gz",
                        "log": f"logs/{ordinal:02d}_sdist_inventory.log",
                        "exit_code": 2,
                        "duration_seconds": 0.0,
                    }
                    _private_write(
                        logs_dir / f"{ordinal:02d}_sdist_inventory.log",
                        f"Found {len(sdists)} source distributions.\n",
                    )
                else:
                    result = _run(
                        label="build_wheel_from_sdist",
                        argv=[
                            sys.executable,
                            "-m",
                            "pip",
                            "wheel",
                            "--no-deps",
                            "--wheel-dir",
                            str(dist_root),
                            str(sdists[0]),
                        ],
                        cwd=build_root,
                        logs_dir=logs_dir,
                        ordinal=ordinal,
                        env=env,
                        replacements=replacements,
                    )
                results.append(result)
                ordinal += 1

            if results and results[-1]["exit_code"] == 0:
                built = sorted(
                    [*dist_root.glob("*.whl"), *dist_root.glob("*.tar.gz")]
                )
                for artifact in built:
                    target = artifacts_dir / artifact.name
                    shutil.copy2(artifact, target)
                    target.chmod(0o600)
                    retained_artifacts.append(target)
                result = _run(
                    label="twine_check",
                    argv=[
                        sys.executable,
                        "-m",
                        "twine",
                        "check",
                        "--strict",
                        *[str(path) for path in built],
                    ],
                    cwd=build_root,
                    logs_dir=logs_dir,
                    ordinal=ordinal,
                    env=env,
                    replacements=replacements,
                )
                results.append(result)
                ordinal += 1

            if results and results[-1]["exit_code"] == 0:
                wheels = sorted(dist_root.glob("*.whl"))
                if len(wheels) != 1:
                    result = {
                        "label": "wheel_inventory",
                        "command": "require exactly one .whl",
                        "log": f"logs/{ordinal:02d}_wheel_inventory.log",
                        "exit_code": 2,
                        "duration_seconds": 0.0,
                    }
                    _private_write(
                        logs_dir / f"{ordinal:02d}_wheel_inventory.log",
                        f"Found {len(wheels)} wheels.\n",
                    )
                else:
                    result = _run(
                        label="built_wheel_smoke",
                        argv=[
                            sys.executable,
                            str(wheel_smoke_checker),
                            str(wheels[0]),
                        ],
                        cwd=build_root,
                        logs_dir=logs_dir,
                        ordinal=ordinal,
                        env=env,
                        replacements=replacements,
                    )
                results.append(result)
                ordinal += 1

            if results and results[-1]["exit_code"] == 0:
                checker = SOURCE_ROOT / ".github/scripts/check_release_artifacts.py"
                argv = [
                    sys.executable,
                    str(checker),
                    str(dist_root),
                    "--source-root",
                    str(SOURCE_ROOT),
                ]
                if args.mode == "audit":
                    argv.extend(
                        [
                            "--allow-unapproved-core-ref-for-audit",
                            "--allow-untracked-required-for-audit",
                            "--allow-dirty-source-for-audit",
                        ]
                    )
                result = _run(
                    label="artifact_guard",
                    argv=argv,
                    cwd=SOURCE_ROOT,
                    logs_dir=logs_dir,
                    ordinal=ordinal,
                    env=env,
                    replacements=replacements,
                )
                results.append(result)

            if results and all(result["exit_code"] == 0 for result in results):
                final_status = "passed"

    core_records = [
        result["record"]
        for result in results
        if result.get("label") == "runtime_core_provenance"
        and isinstance(result.get("record"), dict)
    ]
    if len(core_records) == 1:
        manifest["dependencies"] = {"coupfe": core_records[0]}

    manifest["finished_utc"] = (
        dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    manifest["status"] = final_status
    manifest["publishable"] = (
        args.mode == "release" and final_status == "passed" and not dirty
    )
    manifest["commands"] = results
    manifest["artifacts"] = [
        {
            "path": path.relative_to(output).as_posix(),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in retained_artifacts
    ]
    _private_write(output / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    _write_readme(
        output=output,
        mode=args.mode,
        status=final_status,
        branch=branch,
        head=head,
        dirty=dirty,
        results=results,
        artifacts=retained_artifacts,
    )
    _write_checksums(output, retained_artifacts)
    print(f"evidence checkpoint: {output}")
    print(f"status: {final_status}; publishable: {manifest['publishable']}")
    return 0 if final_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
