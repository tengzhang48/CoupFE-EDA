"""Fail closed unless Python imports the exact clean, public CoupFE checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _public_branch_tip(url: str, branch: str) -> str:
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_ASKPASS"] = "/bin/false"
    completed = subprocess.run(
        [
            "git",
            "-c",
            "credential.helper=",
            "ls-remote",
            "--exit-code",
            url,
            f"refs/heads/{branch}",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    rows = [line.split() for line in completed.stdout.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 2:
        raise SystemExit(
            f"public Core branch lookup returned {len(rows)} records; expected one"
        )
    tip, advertised_ref = rows[0]
    if advertised_ref != f"refs/heads/{branch}" or not re.fullmatch(
        r"[0-9a-f]{40}", tip
    ):
        raise SystemExit("public Core branch lookup returned an invalid ref record")
    return tip


def verify(
    *,
    expected_url: str,
    expected_branch: str,
    expected_ref: str,
    expected_root: Path | None = None,
) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_ref):
        raise SystemExit("--expected-ref must be one lowercase full 40-hex revision")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", expected_branch) or (
        ".." in expected_branch
    ):
        raise SystemExit("--expected-branch is invalid")

    import coupfe

    if coupfe.__file__ is None:
        raise SystemExit("imported coupfe has no filesystem location")
    module_path = Path(coupfe.__file__).resolve()
    try:
        core_root = Path(_git(module_path.parent, "rev-parse", "--show-toplevel")).resolve()
    except subprocess.CalledProcessError as exc:
        raise SystemExit("imported coupfe is not inside a Git worktree") from exc

    if expected_root is not None and core_root != expected_root.expanduser().resolve():
        raise SystemExit(
            f"imported CoupFE root is {core_root}, expected {expected_root.resolve()}"
        )
    expected_module = (core_root / "coupfe" / "__init__.py").resolve()
    if module_path != expected_module:
        raise SystemExit(
            f"imported coupfe module is {module_path}, expected {expected_module}"
        )
    try:
        _git(core_root, "ls-files", "--error-unmatch", "coupfe/__init__.py")
    except subprocess.CalledProcessError as exc:
        raise SystemExit("imported coupfe package entry point is not tracked") from exc

    head = _git(core_root, "rev-parse", "HEAD^{commit}")
    if head != expected_ref:
        raise SystemExit(f"imported CoupFE HEAD is {head}, expected {expected_ref}")

    status = subprocess.run(
        [
            "git",
            "-C",
            str(core_root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    if status:
        raise SystemExit("imported CoupFE worktree is not clean")

    origin = _git(core_root, "remote", "get-url", "origin")
    if origin != expected_url:
        raise SystemExit(f"imported CoupFE origin is {origin!r}, expected {expected_url!r}")

    public_tip = _public_branch_tip(expected_url, expected_branch)
    local_public_tip = _git(
        core_root,
        "rev-parse",
        "--verify",
        f"refs/remotes/origin/{expected_branch}^{{commit}}",
    )
    if local_public_tip != public_tip:
        raise SystemExit(
            "local origin branch is stale relative to the anonymously reachable branch; "
            "rerun setup.sh"
        )
    ancestry = subprocess.run(
        [
            "git",
            "-C",
            str(core_root),
            "merge-base",
            "--is-ancestor",
            expected_ref,
            public_tip,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if ancestry.returncode != 0:
        raise SystemExit(
            f"approved CoupFE revision {expected_ref} is not reachable from public "
            f"{expected_branch}"
        )

    return {
        "branch": expected_branch,
        "branch_tip": public_tip,
        "git_head": head,
        "import_path": str(module_path),
        "origin": origin,
        "worktree": "clean",
        "worktree_root": str(core_root),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-url", required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-ref", required=True)
    parser.add_argument("--expected-root", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                expected_url=args.expected_url,
                expected_branch=args.expected_branch,
                expected_ref=args.expected_ref,
                expected_root=args.expected_root,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
