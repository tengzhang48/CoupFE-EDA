"""Controlled execution primitives for the local CoupFE-EDA workbench.

The browser-facing application is deliberately not a command runner.  It may
request an executor key, while this module owns the exact Python entry point,
arguments, output location, timeout, and retained provenance for that key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping
import uuid


TSV_AXISYMMETRIC_EXECUTOR = "tsv.axisymmetric-field.v1"
TSV_AXISYMMETRIC_CLAIM_BOUNDARY = (
    "Axisymmetric plane-strain thermoelastic component verification against the "
    "declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface device "
    "field, experimental validation, keep-out-zone signoff, or transient cooling "
    "simulation."
)


class WorkbenchExecutionError(RuntimeError):
    """Raised when an approved workbench workflow cannot produce valid evidence."""


@dataclass(frozen=True)
class ApprovedWorkflow:
    """Server-owned definition of one operation exposed to the workbench."""

    executor_key: str
    label: str
    driver: str
    oracle: str
    timeout_seconds: float


APPROVED_WORKFLOWS: Mapping[str, ApprovedWorkflow] = {
    TSV_AXISYMMETRIC_EXECUTOR: ApprovedWorkflow(
        executor_key=TSV_AXISYMMETRIC_EXECUTOR,
        label="CoupFE axisymmetric TSV field verification",
        driver="examples/tsv_axisymmetric_field/run.py",
        oracle="examples/tsv_axisymmetric_field/expected_results.json",
        timeout_seconds=180.0,
    )
}


_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_identity(repository_root: Path) -> dict[str, str]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=normal",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise WorkbenchExecutionError(
            "the local workbench requires a source-identified CoupFE-EDA checkout"
        ) from error
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise WorkbenchExecutionError("CoupFE-EDA Git revision is unavailable")
    return {"revision": revision, "tree_state": "dirty" if status else "clean"}


_HEX_REVISION = re.compile(r"^[0-9a-f]{40}$")
_EXPECTED_TEMPERATURE_STEPS = [
    0.0,
    -50.0,
    -100.0,
    -150.0,
    -200.0,
    -250.0,
    -300.0,
    -350.0,
    -400.0,
]


def _strict_json(path: Path, *, label: str) -> Any:
    def reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise WorkbenchExecutionError(f"approved workflow did not write valid {label}") from error


def _object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkbenchExecutionError(f"{label} must be a JSON object")
    return value


def _number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkbenchExecutionError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as error:
        raise WorkbenchExecutionError(f"{label} must be a finite number") from error
    if not math.isfinite(number):
        raise WorkbenchExecutionError(f"{label} must be a finite number")
    return number


def _integer(value: Any, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise WorkbenchExecutionError(f"{label} must be an integer at least {minimum}")
    return value


def _assert_finite_tree(value: Any, *, label: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise WorkbenchExecutionError(f"{label} contains a non-finite number")
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite_tree(child, label=f"{label}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite_tree(child, label=f"{label}[{index}]")


def _require_claim_boundary(value: Any) -> str:
    if not isinstance(value, str):
        raise WorkbenchExecutionError("TSV field output is missing its claim boundary")
    claim = " ".join(value.lower().replace("3d", "3-d").split())
    denies_three_dimensional = bool(
        re.search(r"(?:not|isn't|does not|cannot).{0,80}(?:3-d|three-dimensional)", claim)
        or re.search(r"(?:3-d|three-dimensional).{0,80}(?:not|isn't|cannot)", claim)
    )
    denies_experimental_validation = bool(
        re.search(r"(?:not|isn't|does not|cannot).{0,80}experimental", claim)
        or re.search(r"experimental.{0,80}(?:not|isn't|cannot)", claim)
    )
    if (
        value != TSV_AXISYMMETRIC_CLAIM_BOUNDARY
        or "axisymmetric" not in claim
        or not denies_three_dimensional
        or not denies_experimental_validation
    ):
        raise WorkbenchExecutionError(
            "TSV field claim boundary must identify the axisymmetric scope and disclaim "
            "3-D and experimental validation"
        )
    return value


def _validate_solver(value: Any, *, label: str, require_iteration: bool) -> dict[str, Any]:
    solver = _object(value, label=label)
    if solver.get("converged") is not True:
        raise WorkbenchExecutionError(f"{label} must report a converged CoupFE solve")
    iterations = _integer(
        solver.get("newton_iterations"),
        label=f"{label}.newton_iterations",
        minimum=1 if require_iteration else 0,
    )
    relative_tolerance = _number(
        solver.get("relative_tolerance"), label=f"{label}.relative_tolerance"
    )
    absolute_tolerance = _number(
        solver.get("absolute_residual_tolerance_N_per_m"),
        label=f"{label}.absolute_residual_tolerance_N_per_m",
    )
    if relative_tolerance <= 0 or absolute_tolerance <= 0:
        raise WorkbenchExecutionError(f"{label} tolerances must be positive")
    for key in (
        "initial_free_residual_norm_N_per_m",
        "final_free_residual_norm_N_per_m",
        "final_relative_residual",
        "residual_fraction_of_acceptance_limit",
    ):
        if _number(solver.get(key), label=f"{label}.{key}") < 0:
            raise WorkbenchExecutionError(f"{label}.{key} must be nonnegative")
    solver["newton_iterations"] = iterations
    return solver


def _validate_comparison(
    value: Any, *, label: str, allow_zero_load: bool = False
) -> dict[str, Any]:
    comparison = _object(value, label=label)
    if comparison.get("reference") != "published_Lame_equation":
        raise WorkbenchExecutionError(f"{label} must identify the published Lame equation")
    if not math.isclose(
        _number(comparison.get("query_radius_um"), label=f"{label}.query_radius_um"),
        20.0,
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise WorkbenchExecutionError(f"{label} must compare the field at 20 um")
    _number(comparison.get("fe_sigma_rr_MPa"), label=f"{label}.fe_sigma_rr_MPa")
    _number(comparison.get("lame_sigma_rr_MPa"), label=f"{label}.lame_sigma_rr_MPa")
    absolute_error = _number(
        comparison.get("absolute_error_MPa"), label=f"{label}.absolute_error_MPa"
    )
    threshold = _number(
        comparison.get("acceptance_threshold"),
        label=f"{label}.acceptance_threshold",
    )
    if absolute_error < 0 or threshold < 0 or threshold > 0.03:
        raise WorkbenchExecutionError(
            f"{label} has an invalid Lame comparison acceptance boundary"
        )
    relative_error = comparison.get("relative_error")
    if allow_zero_load and relative_error is None:
        if comparison.get("passed") is not True:
            raise WorkbenchExecutionError(
                f"{label} must report the zero-load comparison as passed"
            )
        return comparison
    error = _number(relative_error, label=f"{label}.relative_error")
    if error < 0 or error >= 0.03 or error > threshold:
        raise WorkbenchExecutionError(
            f"{label} exceeds the 3 percent Lame comparison boundary"
        )
    if comparison.get("passed") is not True:
        raise WorkbenchExecutionError(f"{label} must report the comparison as passed")
    return comparison


def _validate_field_arrays(value: Any, *, label: str) -> dict[str, Any]:
    field = _object(value, label=label)
    lengths = {
        "radial_displacement_nm": 2400,
        "sigma_rr_MPa": 2399,
        "sigma_theta_MPa": 2399,
    }
    for key, expected_length in lengths.items():
        values = field.get(key)
        if not isinstance(values, list) or len(values) != expected_length:
            raise WorkbenchExecutionError(
                f"{label}.{key} must contain {expected_length} computed values"
            )
        for index, item in enumerate(values):
            _number(item, label=f"{label}.{key}[{index}]")
    return field


def _validate_tsv_axisymmetric_outputs(
    summary: Any,
    field_record: Any,
    *,
    oracle: Mapping[str, Any],
    eda_identity: Mapping[str, str],
) -> dict[str, Any]:
    """Validate and normalize one real CoupFE numerical verification run."""

    summary = _object(summary, label="summary.json")
    field_record = _object(field_record, label="field.json")
    _assert_finite_tree(summary, label="summary.json")
    _assert_finite_tree(field_record, label="field.json")
    oracle = _object(oracle, label="expected_results.json")

    if (
        summary.get("schema_version") != 1
        or field_record.get("schema_version") != 1
        or oracle.get("schema_version") != 1
    ):
        raise WorkbenchExecutionError("TSV field outputs must use schema_version 1")
    case_id = oracle.get("case_id")
    if (
        not isinstance(case_id, str)
        or summary.get("case_id") != case_id
        or field_record.get("case_id") != case_id
    ):
        raise WorkbenchExecutionError("TSV field outputs do not match the retained case oracle")
    claim_boundary = _require_claim_boundary(summary.get("claim_boundary"))
    if field_record.get("claim_boundary") != claim_boundary:
        raise WorkbenchExecutionError("field.json and summary.json claim boundaries differ")

    provenance = _object(summary.get("provenance"), label="summary.provenance")
    for revision_key in ("eda_revision", "core_revision"):
        revision = provenance.get(revision_key)
        if not isinstance(revision, str) or _HEX_REVISION.fullmatch(revision) is None:
            raise WorkbenchExecutionError(
                f"summary.provenance.{revision_key} must be a 40-hex Git revision"
            )
    if provenance["eda_revision"] != eda_identity.get("revision"):
        raise WorkbenchExecutionError(
            "summary provenance does not identify this CoupFE-EDA checkout"
        )
    expected_provenance = {
        "application_module": "eda_multiphysics.tsv_stress",
        "operator": "AxisymThermoelastic",
        "solver": "coupfe.newton_solve",
    }
    for key, expected in expected_provenance.items():
        if provenance.get(key) != expected:
            raise WorkbenchExecutionError(f"summary provenance has invalid {key}")
    if provenance.get("command") != [
        "python",
        "examples/tsv_axisymmetric_field/run.py",
        "--output-dir",
        "<OUTPUT_DIR>",
    ]:
        raise WorkbenchExecutionError("summary provenance does not describe the fixed command")

    oracle_inputs = _object(oracle.get("inputs"), label="oracle.inputs")
    inputs = _object(summary.get("inputs"), label="summary.inputs")
    if field_record.get("inputs") != inputs:
        raise WorkbenchExecutionError("field.json and summary.json inputs differ")
    approved_inputs = {
        "diameter_um": 30.0,
        "delta_temperature_K": -400.0,
        "outer_radius_um": 300.0,
        "mesh_points_requested": 2400,
    }
    for key, approved in approved_inputs.items():
        actual = _number(inputs.get(key), label=f"summary.inputs.{key}")
        retained = _number(oracle_inputs.get(key), label=f"oracle.inputs.{key}")
        if actual != float(approved) or retained != float(approved):
            raise WorkbenchExecutionError(f"TSV field input {key} is outside the fixed case")
    if (
        inputs.get("liner_nm") != 0.0
        or inputs.get("formulation") != "axisymmetric_plane_strain"
        or inputs.get("load") != "uniform_thermal_eigenstrain"
    ):
        raise WorkbenchExecutionError("TSV field output does not describe the fixed formulation")
    if _number(oracle_inputs.get("query_radius_um"), label="oracle.inputs.query_radius_um") != 20.0:
        raise WorkbenchExecutionError("TSV field oracle must retain the 20 um query radius")

    mesh = _object(summary.get("mesh"), label="summary.mesh")
    expected_mesh = {
        "topology": "Line2",
        "nodes": 2400,
        "elements": 2399,
        "degrees_of_freedom": 2400,
        "dof_per_node": 1,
    }
    for key, expected in expected_mesh.items():
        if mesh.get(key) != expected:
            raise WorkbenchExecutionError(f"summary.mesh.{key} must equal {expected!r}")

    solver = _validate_solver(summary.get("solver"), label="summary.solver", require_iteration=True)
    results = _object(summary.get("results"), label="summary.results")
    result_keys = (
        "sigma_rr_at_20um_MPa",
        "sigma_theta_at_20um_MPa",
        "max_abs_displacement_nm",
        "silicon_sigma_rr_min_MPa",
        "silicon_sigma_rr_max_MPa",
    )
    for key in result_keys:
        _number(results.get(key), label=f"summary.results.{key}")
    comparison = _validate_comparison(summary.get("comparison"), label="summary.comparison")
    if not math.isclose(
        float(results["sigma_rr_at_20um_MPa"]),
        float(comparison["fe_sigma_rr_MPa"]),
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    ):
        raise WorkbenchExecutionError("summary result and Lame comparison FE stress differ")

    oracle_expected = _object(oracle.get("expected"), label="oracle.expected")
    tolerances = _object(oracle.get("tolerances"), label="oracle.tolerances")
    numeric_tolerance = _number(
        tolerances.get("relative_numeric"), label="oracle.tolerances.relative_numeric"
    )
    if numeric_tolerance < 0 or numeric_tolerance > 1.0e-4:
        raise WorkbenchExecutionError("oracle numeric tolerance is outside the approved boundary")
    oracle_pairs = {
        "sigma_rr_at_20um_MPa": results["sigma_rr_at_20um_MPa"],
        "lame_sigma_rr_at_20um_MPa": comparison["lame_sigma_rr_MPa"],
        "max_abs_displacement_nm": results["max_abs_displacement_nm"],
        "silicon_sigma_rr_min_MPa": results["silicon_sigma_rr_min_MPa"],
        "silicon_sigma_rr_max_MPa": results["silicon_sigma_rr_max_MPa"],
    }
    for key, actual in oracle_pairs.items():
        expected = _number(oracle_expected.get(key), label=f"oracle.expected.{key}")
        if not math.isclose(
            float(actual),
            expected,
            rel_tol=numeric_tolerance,
            abs_tol=max(1.0e-12, numeric_tolerance * max(1.0, abs(expected))),
        ):
            raise WorkbenchExecutionError(f"TSV field output does not match the oracle for {key}")
    oracle_error_limit = _number(
        tolerances.get("lame_relative_error_max"),
        label="oracle.tolerances.lame_relative_error_max",
    )
    if oracle_error_limit > 0.03 or float(comparison["relative_error"]) > oracle_error_limit:
        raise WorkbenchExecutionError("TSV field output exceeds its retained Lame error limit")

    topology = _object(field_record.get("topology"), label="field.topology")
    if topology != {"type": "Line2", "spatial_dimension": 1, "dof_per_node": 1}:
        raise WorkbenchExecutionError("field topology is not the approved radial Line2 mesh")
    field_mesh = _object(field_record.get("mesh"), label="field.mesh")
    mesh_lengths = {
        "radius_nodes_um": 2400,
        "element_centers_um": 2399,
        "connectivity": 2399,
        "region_by_element": 2399,
    }
    for key, expected_length in mesh_lengths.items():
        values = field_mesh.get(key)
        if not isinstance(values, list) or len(values) != expected_length:
            raise WorkbenchExecutionError(
                f"field.mesh.{key} must contain {expected_length} entries"
            )
    for index, radius in enumerate(field_mesh["radius_nodes_um"]):
        _number(radius, label=f"field.mesh.radius_nodes_um[{index}]")
    for index, radius in enumerate(field_mesh["element_centers_um"]):
        _number(radius, label=f"field.mesh.element_centers_um[{index}]")
    for index, connection in enumerate(field_mesh["connectivity"]):
        if connection != [index, index + 1]:
            raise WorkbenchExecutionError("field.mesh.connectivity is not an ordered Line2 chain")
    final_field = _validate_field_arrays(
        field_record.get("final_field"), label="field.final_field"
    )
    if final_field.get("delta_temperature_K") != -400.0:
        raise WorkbenchExecutionError("field.final_field must identify the final -400 K solve")
    field_solver = _validate_solver(
        field_record.get("solver"), label="field.solver", require_iteration=True
    )
    if field_solver != solver:
        raise WorkbenchExecutionError("field.json and summary.json solver records differ")
    field_comparison = _validate_comparison(
        field_record.get("comparison"), label="field.comparison"
    )
    if field_comparison != comparison:
        raise WorkbenchExecutionError("field.json and summary.json comparisons differ")

    sweep = _object(field_record.get("load_sweep"), label="field.load_sweep")
    if (
        sweep.get("sweep_kind") != "independent_static_prescribed_load_cases"
        or sweep.get("is_transient") is not False
    ):
        raise WorkbenchExecutionError(
            "field load sweep must contain independent static CoupFE solves"
        )
    temperatures = sweep.get("delta_temperature_K")
    steps = sweep.get("steps")
    if (
        temperatures != _EXPECTED_TEMPERATURE_STEPS
        or not isinstance(steps, list)
        or len(steps) != 9
    ):
        raise WorkbenchExecutionError("field load sweep must contain the nine approved load steps")
    total_newton_iterations = 0
    for index, step_value in enumerate(steps):
        step = _object(step_value, label=f"field.load_sweep.steps[{index}]")
        if (
            step.get("step_index") != index
            or step.get("delta_temperature_K") != _EXPECTED_TEMPERATURE_STEPS[index]
            or step.get("solve_kind") != "independent_static_coupfe_solve"
            or step.get("is_transient") is not False
        ):
            raise WorkbenchExecutionError(
                f"field load step {index} is not an actual approved solve"
            )
        step_solver = _validate_solver(
            step.get("solver"),
            label=f"field.load_sweep.steps[{index}].solver",
            require_iteration=index != 0,
        )
        total_newton_iterations += step_solver["newton_iterations"]
        step_results = _object(
            step.get("results"), label=f"field.load_sweep.steps[{index}].results"
        )
        for result_key in result_keys:
            _number(
                step_results.get(result_key),
                label=f"field.load_sweep.steps[{index}].results.{result_key}",
            )
        _validate_comparison(
            step.get("comparison"),
            label=f"field.load_sweep.steps[{index}].comparison",
            allow_zero_load=index == 0,
        )
        _validate_field_arrays(
            step.get("field"), label=f"field.load_sweep.steps[{index}].field"
        )

    final_step = steps[-1]
    if (
        final_step.get("solver") != solver
        or final_step.get("results") != results
        or final_step.get("comparison") != comparison
    ):
        raise WorkbenchExecutionError(
            "the final load step does not match the retained summary result"
        )
    final_step_field = _object(
        final_step.get("field"), label="field.load_sweep.steps[8].field"
    )
    for key in ("radial_displacement_nm", "sigma_rr_MPa", "sigma_theta_MPa"):
        if final_step_field.get(key) != final_field.get(key):
            raise WorkbenchExecutionError(
                "the final load-step field does not match field.final_field"
            )

    summary_sweep = _object(summary.get("load_sweep"), label="summary.load_sweep")
    if (
        summary_sweep.get("steps") != 9
        or summary_sweep.get("kind") != "independent_static_prescribed_load_cases"
        or summary_sweep.get("is_transient") is not False
        or summary_sweep.get("delta_temperature_K") != _EXPECTED_TEMPERATURE_STEPS
    ):
        raise WorkbenchExecutionError("summary does not bind the nine actual field load steps")

    return {
        "claim_boundary": claim_boundary,
        "eda_revision": provenance["eda_revision"],
        "core_revision": provenance["core_revision"],
        "sigma_rr_at_20um_MPa": float(results["sigma_rr_at_20um_MPa"]),
        "lame_sigma_rr_at_20um_MPa": float(comparison["lame_sigma_rr_MPa"]),
        "lame_relative_error": float(comparison["relative_error"]),
        "degrees_of_freedom": 2400,
        "elements": 2399,
        "actual_load_steps": 9,
        "newton_iterations": solver["newton_iterations"],
        "total_load_sweep_newton_iterations": total_newton_iterations,
    }


def execute_approved_workflow(
    executor_key: str,
    *,
    run_root: str | os.PathLike[str],
    repository_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Execute one allowlisted workflow and return its retained run manifest.

    ``run_root`` is chosen when the local service starts.  It is never accepted
    from a browser request.  The only browser-controlled execution value is the
    exact ``executor_key`` looked up in :data:`APPROVED_WORKFLOWS`.
    """

    try:
        workflow = APPROVED_WORKFLOWS[executor_key]
    except KeyError as error:
        raise WorkbenchExecutionError(
            f"unsupported workbench executor: {executor_key!r}"
        ) from error

    repository = (
        Path(repository_root).expanduser().resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    driver = repository / workflow.driver
    if not driver.is_file():
        raise WorkbenchExecutionError(
            f"approved workflow driver is unavailable: {workflow.driver}"
        )
    oracle_path = repository / workflow.oracle
    if not oracle_path.is_file():
        raise WorkbenchExecutionError(
            f"approved workflow oracle is unavailable: {workflow.oracle}"
        )
    oracle = _strict_json(oracle_path, label=workflow.oracle)
    if not isinstance(oracle, dict):
        raise WorkbenchExecutionError("approved workflow oracle must be a JSON object")
    identity = _repository_identity(repository)

    owned_root = Path(run_root).expanduser().resolve()
    owned_root.mkdir(parents=True, exist_ok=True)
    if not owned_root.is_dir():
        raise WorkbenchExecutionError("workbench run root is not a directory")
    run_dir = Path(
        tempfile.mkdtemp(prefix="tsv-axisymmetric-field-", dir=owned_root)
    ).resolve()
    if run_dir.parent != owned_root:
        raise WorkbenchExecutionError("workbench allocated an invalid run directory")

    command = [sys.executable, str(driver), "--output-dir", str(run_dir)]
    started = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=workflow.timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise WorkbenchExecutionError(f"approved workflow failed to start: {error}") from error
    elapsed = time.perf_counter() - start_clock

    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise WorkbenchExecutionError(
            f"approved workflow exited with status {completed.returncode}; retained output: {run_dir}"
        )

    summary_path = run_dir / "summary.json"
    field_path = run_dir / "field.json"
    results = _validate_tsv_axisymmetric_outputs(
        _strict_json(summary_path, label="summary.json"),
        _strict_json(field_path, label="field.json"),
        oracle=oracle,
        eda_identity=identity,
    )

    contour_path = run_dir / "contour.svg"
    try:
        contour = contour_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise WorkbenchExecutionError(
            "approved workflow did not write valid contour.svg"
        ) from error
    if "<svg" not in contour or "</svg>" not in contour or contour_path.stat().st_size == 0:
        raise WorkbenchExecutionError("approved workflow did not write valid contour.svg")

    required_artifacts = (
        "field.json",
        "summary.json",
        "contour.svg",
        "stdout.txt",
        "stderr.txt",
    )
    artifacts = []
    for name in required_artifacts:
        path = run_dir / name
        if not path.is_file():
            raise WorkbenchExecutionError(f"approved workflow did not write {name}")
        artifacts.append(
            {"name": name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
        )

    manifest = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "status": "succeeded",
        "executor_key": workflow.executor_key,
        "workflow_label": workflow.label,
        "driver": workflow.driver,
        "oracle": {
            "path": workflow.oracle,
            "sha256": _sha256(oracle_path),
        },
        "command_contract": "server-owned fixed Python driver and output directory",
        "started_at": started.isoformat(),
        "elapsed_seconds": elapsed,
        "source": identity,
        "results": results,
        "artifacts": artifacts,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    manifest["manifest"] = {
        "name": manifest_path.name,
        "sha256": _sha256(manifest_path),
        "size_bytes": manifest_path.stat().st_size,
    }
    manifest["run_directory"] = str(run_dir)
    return manifest


class WorkbenchRunStore:
    """Thread-safe in-process run registry for the localhost workbench service."""

    def __init__(
        self,
        *,
        run_root: str | os.PathLike[str],
        repository_root: str | os.PathLike[str] | None = None,
        max_workers: int = 1,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self.run_root = Path(run_root).expanduser().resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.repository_root = (
            Path(repository_root).expanduser().resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="coupfe-eda")
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._sequence = 0
        self._runs: dict[str, dict[str, Any]] = {}
        self._run_directories: dict[str, Path] = {}
        self._requests: dict[str, tuple[str, str]] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._events: list[dict[str, Any]] = []

    def close(self, *, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait, cancel_futures=not wait)

    def list_workflows(self) -> list[dict[str, Any]]:
        return [
            {
                "executorKey": item.executor_key,
                "label": item.label,
                "driver": item.driver,
                "claimBoundary": TSV_AXISYMMETRIC_CLAIM_BOUNDARY,
            }
            for item in APPROVED_WORKFLOWS.values()
        ]

    def _publish_locked(self, run_id: str) -> None:
        self._sequence += 1
        self._runs[run_id]["sequence"] = self._sequence
        event = {
            "sequence": self._sequence,
            "emittedAt": datetime.now(timezone.utc).isoformat(),
            "run": json.loads(json.dumps(self._runs[run_id], allow_nan=False)),
        }
        self._events.append(event)
        self._condition.notify_all()

    def start_run(self, *, executor_key: str, client_request_id: str) -> dict[str, Any]:
        if executor_key not in APPROVED_WORKFLOWS:
            raise WorkbenchExecutionError(f"unsupported workbench executor: {executor_key!r}")
        if not isinstance(client_request_id, str) or not client_request_id.strip():
            raise WorkbenchExecutionError("clientRequestId must be a non-empty string")
        if len(client_request_id) > 200:
            raise WorkbenchExecutionError("clientRequestId is too long")
        request_key = client_request_id.strip()
        with self._lock:
            previous = self._requests.get(request_key)
            if previous is not None:
                previous_executor, run_id = previous
                if previous_executor != executor_key:
                    raise WorkbenchExecutionError(
                        "clientRequestId is already bound to a different executor"
                    )
                return json.loads(json.dumps(self._runs[run_id], allow_nan=False))

            run_id = f"run-{uuid.uuid4().hex[:12]}"
            record = {
                "id": run_id,
                "executorKey": executor_key,
                "clientRequestId": request_key,
                "status": "queued",
                "requestedAt": datetime.now(timezone.utc).isoformat(),
                "sequence": 0,
            }
            self._runs[run_id] = record
            self._requests[request_key] = (executor_key, run_id)
            self._publish_locked(run_id)
            self._futures[run_id] = self._pool.submit(self._execute_run, run_id)
            return json.loads(json.dumps(record, allow_nan=False))

    def _execute_run(self, run_id: str) -> None:
        with self._lock:
            record = self._runs[run_id]
            if record["status"] == "cancelled":
                return
            record["status"] = "running"
            record["startedAt"] = datetime.now(timezone.utc).isoformat()
            self._publish_locked(run_id)
            executor_key = record["executorKey"]
        try:
            result = execute_approved_workflow(
                executor_key,
                run_root=self.run_root,
                repository_root=self.repository_root,
            )
        except Exception:
            with self._lock:
                record = self._runs[run_id]
                record["status"] = "failed"
                record["completedAt"] = datetime.now(timezone.utc).isoformat()
                record["failureMessage"] = (
                    "The approved workflow failed; operator diagnostics, when produced, "
                    "remain in the server-owned run root."
                )
                self._publish_locked(run_id)
            return

        run_directory = Path(result.pop("run_directory")).resolve()
        public_result = {
            "elapsedSeconds": result["elapsed_seconds"],
            "source": result["source"],
            "results": result["results"],
            "artifacts": [
                {
                    **artifact,
                    "uri": f"/api/runs/{run_id}/artifacts/{artifact['name']}",
                }
                for artifact in result["artifacts"]
            ],
            "manifest": {
                **result["manifest"],
                "uri": f"/api/runs/{run_id}/artifacts/manifest.json",
            },
        }
        with self._lock:
            self._run_directories[run_id] = run_directory
            record = self._runs[run_id]
            record["status"] = "succeeded"
            record["completedAt"] = datetime.now(timezone.utc).isoformat()
            record["output"] = public_result
            self._publish_locked(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return json.loads(json.dumps(self._runs[run_id], allow_nan=False))
            except KeyError as error:
                raise WorkbenchExecutionError(f"unknown workbench run: {run_id!r}") from error

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                json.loads(json.dumps(record, allow_nan=False))
                for record in sorted(
                    self._runs.values(), key=lambda item: item["sequence"], reverse=True
                )
            ]

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                record = self._runs[run_id]
            except KeyError as error:
                raise WorkbenchExecutionError(f"unknown workbench run: {run_id!r}") from error
            if record["status"] in _TERMINAL_STATUSES:
                raise WorkbenchExecutionError(f"run {run_id!r} is already terminal")
            future = self._futures.get(run_id)
            if record["status"] == "running" or future is None or not future.cancel():
                raise WorkbenchExecutionError(
                    "this first local service can cancel queued runs only; the running fixed executor "
                    "must finish or reach its server-owned timeout"
                )
            record["status"] = "cancelled"
            record["completedAt"] = datetime.now(timezone.utc).isoformat()
            self._publish_locked(run_id)
            return json.loads(json.dumps(record, allow_nan=False))

    def events_after(self, sequence: int) -> list[dict[str, Any]]:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise WorkbenchExecutionError("event sequence must be a nonnegative integer")
        with self._lock:
            return [
                json.loads(json.dumps(event, allow_nan=False))
                for event in self._events
                if event["sequence"] > sequence
            ]

    def wait_for_events(self, sequence: int, *, timeout: float) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                events = [event for event in self._events if event["sequence"] > sequence]
                if events:
                    return json.loads(json.dumps(events, allow_nan=False))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)

    def artifact_path(self, run_id: str, artifact_name: str) -> Path:
        if not artifact_name or Path(artifact_name).name != artifact_name:
            raise WorkbenchExecutionError("invalid artifact name")
        with self._lock:
            record = self._runs.get(run_id)
            run_directory = self._run_directories.get(run_id)
            if record is None:
                raise WorkbenchExecutionError(f"unknown workbench run: {run_id!r}")
            if record["status"] != "succeeded" or run_directory is None:
                raise WorkbenchExecutionError(
                    "run artifacts are unavailable until the run succeeds"
                )
            output = record.get("output", {})
            names = {artifact["name"] for artifact in output.get("artifacts", [])}
            names.add("manifest.json")
            if artifact_name not in names:
                raise WorkbenchExecutionError(f"unknown run artifact: {artifact_name!r}")
        path = (run_directory / artifact_name).resolve()
        if path.parent != run_directory or not path.is_file():
            raise WorkbenchExecutionError("run artifact is unavailable")
        return path
