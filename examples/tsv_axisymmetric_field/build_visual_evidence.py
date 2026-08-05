"""Build and validate one reproducible TSV visual-evidence bundle.

This command requires a clean CoupFE-EDA checkout and the exact clean CoupFE
revision selected by ``setup.sh``.  It runs the fixed nine-state solver case in
an empty directory, renders the retained states, writes a checksum-bound
``visual-evidence.json``, and invokes the fail-closed bundle validator.

Rendering additionally requires::

    python -m pip install "Pillow>=10" "imageio-ffmpeg>=0.5"

Run with an output directory outside the source checkout::

    python examples/tsv_axisymmetric_field/build_visual_evidence.py \
        --output-dir /tmp/coupfe-tsv-visual-evidence
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from eda_multiphysics.visual_evidence import (
    VisualEvidenceValidationError,
    validate_manifest,
)
from eda_multiphysics.source_identity import (
    APPROVED_COUPFE_URL,
    SourceIdentityError,
    resolve_coupfe_identity,
)
from examples.tsv_axisymmetric_field.render_video import (
    CASE_ID,
    CLAIM_BOUNDARY,
    EXPECTED_LOADS_K,
    MediaDependencyError,
    RenderInputError,
    load_field,
    render_video,
)


SOURCE_ROOT = Path(__file__).resolve().parents[2]
RUNNER_RELATIVE = Path("examples/tsv_axisymmetric_field/run.py")
NORMALIZED_RUNNER_COMMAND = [
    "python",
    RUNNER_RELATIVE.as_posix(),
    "--output-dir",
    "<OUTPUT_DIR>",
]
EXPECTED_RUNNER_ARTIFACTS = {"field.json", "summary.json", "contour.svg"}
FINAL_ARTIFACT_ROLES = {
    "field.json": "raw-field",
    "summary.json": "summary",
    "contour.svg": "image",
    "load-sweep.webm": "video",
}
_REVISION = re.compile(r"[0-9a-f]{40}")
_SUMMARY_KEYS = {
    "schema_version",
    "case_id",
    "claim_boundary",
    "provenance",
    "inputs",
    "units",
    "mesh",
    "solver",
    "results",
    "comparison",
    "load_sweep",
}


class VisualEvidenceBuildError(RuntimeError):
    """Raised when a reproducible visual-evidence build cannot be trusted."""


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=not binary,
    )
    if binary:
        return completed.stdout
    return completed.stdout.strip()


def _revision(root: Path) -> str:
    try:
        revision = _git(root, "rev-parse", "HEAD^{commit}")
    except subprocess.CalledProcessError as exc:
        raise VisualEvidenceBuildError(f"not a Git checkout: {root}") from exc
    if _REVISION.fullmatch(revision) is None:
        raise VisualEvidenceBuildError(f"Git returned an invalid revision for {root}")
    return revision


def _require_clean_checkout(root: Path, *, label: str) -> str:
    revision = _revision(root)
    try:
        status = _git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            binary=True,
        )
    except subprocess.CalledProcessError as exc:
        raise VisualEvidenceBuildError(f"could not inspect {label} checkout") from exc
    if status:
        raise VisualEvidenceBuildError(
            f"{label} checkout must be clean before evidence generation: {root}"
        )
    return revision


def _setup_core_ref() -> str:
    text = (SOURCE_ROOT / "setup.sh").read_text(encoding="utf-8")
    matches = re.findall(
        r'^COUPFE_REF="\$\{COUPFE_REF:-([0-9a-f]{40})\}"[ \t]*$',
        text,
        flags=re.MULTILINE,
    )
    if len(matches) != 1:
        raise VisualEvidenceBuildError(
            "setup.sh must declare exactly one lowercase full CoupFE revision"
        )
    return matches[0]


def _core_identity() -> tuple[Path, str]:
    approved = _setup_core_ref()
    identity = resolve_coupfe_identity(
        expected_url=APPROVED_COUPFE_URL,
        expected_revision=approved,
    )
    return identity.root, identity.revision


def _prepare_output_directory(output_dir: str | Path) -> Path:
    candidate = Path(output_dir).expanduser()
    if candidate.is_symlink():
        raise VisualEvidenceBuildError("output directory must not be a symbolic link")
    output = candidate.resolve(strict=False)
    source = SOURCE_ROOT.resolve()
    if output == source or source in output.parents:
        raise VisualEvidenceBuildError("output directory must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise VisualEvidenceBuildError("output path must be a regular directory")
    entries = list(output.iterdir())
    if entries:
        raise VisualEvidenceBuildError(
            f"output directory must be empty, found: {sorted(path.name for path in entries)}"
        )
    return output


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VisualEvidenceBuildError(f"JSON repeats key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise VisualEvidenceBuildError(f"JSON contains non-finite constant {value!r}")


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise VisualEvidenceBuildError(f"expected regular JSON artifact: {path.name}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisualEvidenceBuildError(f"invalid strict JSON in {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise VisualEvidenceBuildError(f"{path.name} must contain a JSON object")
    return value


def _exact_object(value: Any, location: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisualEvidenceBuildError(f"{location} must be an object")
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        raise VisualEvidenceBuildError(
            f"{location} key mismatch: missing={missing}, extra={extra}"
        )
    return value


def _validate_summary(
    summary: dict[str, Any],
    field: dict[str, Any],
    *,
    eda_revision: str,
    core_revision: str,
) -> None:
    root = _exact_object(summary, "summary", _SUMMARY_KEYS)
    if root["schema_version"] != 1 or isinstance(root["schema_version"], bool):
        raise VisualEvidenceBuildError("summary.schema_version must equal 1")
    if root["case_id"] != CASE_ID or root["case_id"] != field["case_id"]:
        raise VisualEvidenceBuildError("summary.case_id does not match the field case")
    if (
        root["claim_boundary"] != CLAIM_BOUNDARY
        or root["claim_boundary"] != field["claim_boundary"]
    ):
        raise VisualEvidenceBuildError("summary.claim_boundary is not authoritative")

    provenance = _exact_object(
        root["provenance"],
        "summary.provenance",
        {
            "eda_revision",
            "core_revision",
            "application_module",
            "operator",
            "solver",
            "command",
        },
    )
    expected_provenance = {
        "eda_revision": eda_revision,
        "core_revision": core_revision,
        "application_module": "eda_multiphysics.tsv_stress",
        "operator": "AxisymThermoelastic",
        "solver": "coupfe.newton_solve",
        "command": NORMALIZED_RUNNER_COMMAND,
    }
    if provenance != expected_provenance:
        raise VisualEvidenceBuildError(
            "summary.provenance does not bind the executed reviewed runner and revisions"
        )
    for key in ("inputs", "units", "solver", "comparison"):
        if root[key] != field[key]:
            raise VisualEvidenceBuildError(f"summary.{key} disagrees with field.{key}")

    mesh = _exact_object(
        root["mesh"],
        "summary.mesh",
        {"topology", "nodes", "elements", "degrees_of_freedom", "dof_per_node"},
    )
    node_count = len(field["mesh"]["radius_nodes_um"])
    element_count = len(field["mesh"]["element_centers_um"])
    expected_mesh = {
        "topology": "Line2",
        "nodes": node_count,
        "elements": element_count,
        "degrees_of_freedom": node_count,
        "dof_per_node": 1,
    }
    if mesh != expected_mesh:
        raise VisualEvidenceBuildError("summary.mesh disagrees with the field inventory")
    if root["results"] != field["load_sweep"]["steps"][-1]["results"]:
        raise VisualEvidenceBuildError("summary.results disagrees with final solved state")

    sweep = _exact_object(
        root["load_sweep"],
        "summary.load_sweep",
        {"steps", "kind", "is_transient", "delta_temperature_K"},
    )
    if sweep != {
        "steps": len(EXPECTED_LOADS_K),
        "kind": "independent_static_prescribed_load_cases",
        "is_transient": False,
        "delta_temperature_K": list(EXPECTED_LOADS_K),
    }:
        raise VisualEvidenceBuildError("summary.load_sweep is not the reviewed sweep")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def construct_manifest(
    output_dir: str | Path,
    *,
    field: dict[str, Any],
    summary: dict[str, Any],
    eda_revision: str,
    core_revision: str,
    renderer_configuration: dict[str, Any],
) -> dict[str, Any]:
    """Construct the strict manifest after all four bound files exist."""

    output = Path(output_dir)
    _validate_summary(
        summary,
        field,
        eda_revision=eda_revision,
        core_revision=core_revision,
    )
    expected_files = set(FINAL_ARTIFACT_ROLES)
    actual_files = {
        path.name
        for path in output.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if actual_files != expected_files:
        raise VisualEvidenceBuildError(
            "pre-manifest artifact inventory mismatch: "
            f"missing={sorted(expected_files - actual_files)}, "
            f"extra={sorted(actual_files - expected_files)}"
        )
    nonregular = sorted(
        path.name for path in output.iterdir() if path.is_symlink() or not path.is_file()
    )
    if nonregular:
        raise VisualEvidenceBuildError(
            f"output contains non-regular entries: {nonregular}"
        )

    artifacts = []
    for name, role in FINAL_ARTIFACT_ROLES.items():
        path = output / name
        artifacts.append(
            {
                "path": name,
                "role": role,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    steps = field["load_sweep"]["steps"]
    node_count = len(field["mesh"]["radius_nodes_um"])
    element_count = len(field["mesh"]["element_centers_um"])
    return {
        "schema_version": 1,
        "case": {
            "id": CASE_ID,
            "description": (
                "Solver-derived axisymmetric TSV thermoelastic field and prescribed "
                "cooling-sweep media"
            ),
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "revisions": {"eda": eda_revision, "core": core_revision},
        "command": list(NORMALIZED_RUNNER_COMMAND),
        "field": {
            "topology": "Line2 axisymmetric plane strain",
            "mesh": {
                "name": f"{CASE_ID}_{node_count}_nodes",
                "spatial_dimension": 1,
                "node_count": node_count,
                "element_count": element_count,
            },
            "degree_of_freedom_count": node_count,
            "components": [
                {
                    "name": "radial_displacement_nm",
                    "unit": field["units"]["radial_displacement"],
                    "location": "node",
                },
                {
                    "name": "sigma_rr_MPa",
                    "unit": field["units"]["stress"],
                    "location": "element_center",
                },
                {
                    "name": "sigma_theta_MPa",
                    "unit": field["units"]["stress"],
                    "location": "element_center",
                },
            ],
            "load_steps": [
                {
                    "index": step["step_index"],
                    "name": f"prescribed_static_cooling_{step['step_index']}",
                    "value": step["delta_temperature_K"],
                    "unit": field["units"]["temperature_change"],
                }
                for step in steps
            ],
        },
        "renderer": {
            "name": "examples.tsv_axisymmetric_field.render_video",
            "version": "1",
            "configuration": renderer_configuration,
            "interpretation": (
                "The axisymmetric display reconstructs each retained solved static field. "
                "The animation is a prescribed load sweep, not a transient simulation, "
                "and contains no interpolated physical states."
            ),
        },
        "artifacts": artifacts,
    }


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def build_visual_evidence(output_dir: str | Path) -> Path:
    """Run, render, bind, and validate one clean-source evidence bundle."""

    eda_revision = _require_clean_checkout(SOURCE_ROOT, label="CoupFE-EDA source")
    _core_root, core_revision = _core_identity()
    output = _prepare_output_directory(output_dir)
    actual_command = [
        sys.executable,
        RUNNER_RELATIVE.as_posix(),
        "--output-dir",
        str(output),
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    current_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(SOURCE_ROOT)
        if not current_pythonpath
        else os.pathsep.join((str(SOURCE_ROOT), current_pythonpath))
    )
    completed = subprocess.run(
        actual_command,
        cwd=SOURCE_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise VisualEvidenceBuildError(
            "fixed runner failed with exit "
            f"{completed.returncode}:\n{completed.stdout}\n{completed.stderr}"
        )
    runner_files = {path.name for path in output.iterdir() if path.is_file()}
    if runner_files != EXPECTED_RUNNER_ARTIFACTS:
        raise VisualEvidenceBuildError(
            "fixed runner artifact mismatch: "
            f"missing={sorted(EXPECTED_RUNNER_ARTIFACTS - runner_files)}, "
            f"extra={sorted(runner_files - EXPECTED_RUNNER_ARTIFACTS)}"
        )

    field = load_field(output / "field.json")
    summary = _load_json(output / "summary.json")
    try:
        stdout_summary = json.loads(
            completed.stdout,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise VisualEvidenceBuildError("fixed runner stdout was not strict JSON") from exc
    if stdout_summary != summary:
        raise VisualEvidenceBuildError("fixed runner stdout differs from summary.json")
    _validate_summary(
        summary,
        field,
        eda_revision=eda_revision,
        core_revision=core_revision,
    )

    configuration = render_video(
        output / "field.json",
        output / "load-sweep.webm",
    )
    manifest = construct_manifest(
        output,
        field=field,
        summary=summary,
        eda_revision=eda_revision,
        core_revision=core_revision,
        renderer_configuration=configuration,
    )
    manifest_path = output / "visual-evidence.json"
    _write_json(manifest_path, manifest)
    validate_manifest(manifest_path)

    if _revision(SOURCE_ROOT) != eda_revision:
        raise VisualEvidenceBuildError("source revision changed during evidence generation")
    _require_clean_checkout(SOURCE_ROOT, label="CoupFE-EDA source")
    return manifest_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = build_visual_evidence(args.output_dir)
    except (
        MediaDependencyError,
        RenderInputError,
        VisualEvidenceBuildError,
        VisualEvidenceValidationError,
        SourceIdentityError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"visual evidence build failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"manifest": str(manifest), "status": "valid"},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
