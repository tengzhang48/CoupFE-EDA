"""Focused tests for the fixed, local CoupFE workbench executor."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def completed_workflow(tmp_path_factory):
    from eda_multiphysics.workbench import (
        TSV_AXISYMMETRIC_EXECUTOR,
        execute_approved_workflow,
    )

    run_root = tmp_path_factory.mktemp("axisymmetric-workbench")
    manifest = execute_approved_workflow(
        TSV_AXISYMMETRIC_EXECUTOR,
        run_root=run_root,
        repository_root=ROOT,
    )
    run_dir = Path(manifest["run_directory"])
    return {
        "manifest": manifest,
        "run_dir": run_dir,
        "summary": json.loads((run_dir / "summary.json").read_text()),
        "field": json.loads((run_dir / "field.json").read_text()),
        "oracle": json.loads(
            (ROOT / "examples/tsv_axisymmetric_field/expected_results.json").read_text()
        ),
    }


def test_only_one_fixed_executor_is_public_and_has_no_tunable_arguments():
    from eda_multiphysics import workbench

    assert set(workbench.APPROVED_WORKFLOWS) == {
        workbench.TSV_AXISYMMETRIC_EXECUTOR,
    }
    workflow = workbench.APPROVED_WORKFLOWS[workbench.TSV_AXISYMMETRIC_EXECUTOR]
    assert workflow.driver == "examples/tsv_axisymmetric_field/run.py"
    assert workflow.oracle == "examples/tsv_axisymmetric_field/expected_results.json"
    assert workflow.timeout_seconds == 180.0
    assert set(inspect.signature(workbench.execute_approved_workflow).parameters) == {
        "executor_key",
        "run_root",
        "repository_root",
    }


def test_workbench_rejects_unknown_executor_before_creating_output(tmp_path):
    from eda_multiphysics.workbench import WorkbenchExecutionError, execute_approved_workflow

    with pytest.raises(WorkbenchExecutionError, match="unsupported workbench executor"):
        execute_approved_workflow(
            "shell.arbitrary",
            run_root=tmp_path,
            repository_root=ROOT,
        )
    assert list(tmp_path.iterdir()) == []


def test_axisymmetric_executor_retains_real_field_metrics_and_provenance(completed_workflow):
    from eda_multiphysics.workbench import TSV_AXISYMMETRIC_EXECUTOR

    manifest = completed_workflow["manifest"]
    run_dir = completed_workflow["run_dir"]
    summary = completed_workflow["summary"]
    field = completed_workflow["field"]
    results = manifest["results"]

    assert manifest["status"] == "succeeded"
    assert manifest["executor_key"] == TSV_AXISYMMETRIC_EXECUTOR
    assert manifest["oracle"]["path"] == (
        "examples/tsv_axisymmetric_field/expected_results.json"
    )
    assert manifest["command_contract"] == (
        "server-owned fixed Python driver and output directory"
    )
    expected_revision = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert manifest["source"]["revision"] == expected_revision
    assert results["eda_revision"] == expected_revision
    assert len(results["core_revision"]) == 40
    assert all(character in "0123456789abcdef" for character in results["core_revision"])
    assert results["degrees_of_freedom"] == 2400
    assert results["elements"] == 2399
    assert results["actual_load_steps"] == 9
    assert results["newton_iterations"] >= 1
    assert results["lame_relative_error"] < 0.03
    assert results["sigma_rr_at_20um_MPa"] == pytest.approx(
        summary["results"]["sigma_rr_at_20um_MPa"]
    )
    assert field["load_sweep"]["is_transient"] is False
    assert len(field["load_sweep"]["steps"]) == 9
    assert all(
        step["solve_kind"] == "independent_static_coupfe_solve"
        for step in field["load_sweep"]["steps"]
    )

    artifact_names = {artifact["name"] for artifact in manifest["artifacts"]}
    assert artifact_names == {
        "field.json",
        "summary.json",
        "contour.svg",
        "stdout.txt",
        "stderr.txt",
    }
    for artifact in manifest["artifacts"]:
        assert artifact["size_bytes"] == (run_dir / artifact["name"]).stat().st_size
        assert artifact["sha256"] == _sha256(run_dir / artifact["name"])
    assert _sha256(run_dir / "manifest.json") == manifest["manifest"]["sha256"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda summary, field: summary["mesh"].__setitem__("degrees_of_freedom", 2399), "degrees_of_freedom"),
        (lambda summary, field: summary["comparison"].__setitem__("relative_error", 0.03), "3 percent"),
        (lambda summary, field: summary["provenance"].__setitem__("core_revision", "unknown"), "40-hex"),
        (lambda summary, field: field["load_sweep"]["steps"].pop(), "nine approved load steps"),
        (
            lambda summary, field: summary.__setitem__(
                "claim_boundary", "Axisymmetric computation without a qualification statement."
            ),
            "claim boundary",
        ),
        (lambda summary, field: summary["results"].__setitem__("sigma_rr_at_20um_MPa", float("nan")), "non-finite"),
    ],
)
def test_validator_rejects_unqualified_or_nonphysical_output(
    completed_workflow, mutation, message
):
    from eda_multiphysics import workbench

    summary = copy.deepcopy(completed_workflow["summary"])
    field = copy.deepcopy(completed_workflow["field"])
    mutation(summary, field)
    with pytest.raises(workbench.WorkbenchExecutionError, match=message):
        workbench._validate_tsv_axisymmetric_outputs(
            summary,
            field,
            oracle=completed_workflow["oracle"],
            eda_identity=completed_workflow["manifest"]["source"],
        )


def test_run_store_is_idempotent_and_does_not_expose_server_paths(
    tmp_path, completed_workflow, monkeypatch
):
    from eda_multiphysics import workbench

    retained = completed_workflow["manifest"]

    def fixed_result(*_args, **_kwargs):
        return copy.deepcopy(retained)

    monkeypatch.setattr(workbench, "execute_approved_workflow", fixed_result)
    store = workbench.WorkbenchRunStore(run_root=tmp_path, repository_root=ROOT)
    try:
        accepted = store.start_run(
            executor_key=workbench.TSV_AXISYMMETRIC_EXECUTOR,
            client_request_id="browser-request-1",
        )
        duplicate = store.start_run(
            executor_key=workbench.TSV_AXISYMMETRIC_EXECUTOR,
            client_request_id="browser-request-1",
        )
        assert duplicate["id"] == accepted["id"]
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            completed = store.get_run(accepted["id"])
            if completed["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert completed["status"] == "succeeded"
        serialized = json.dumps(completed)
        assert str(tmp_path) not in serialized
        assert str(completed_workflow["run_dir"]) not in serialized
        assert "run_directory" not in serialized
        assert completed["output"]["results"]["degrees_of_freedom"] == 2400
        assert store.artifact_path(accepted["id"], "field.json").is_file()
        with pytest.raises(workbench.WorkbenchExecutionError, match="invalid artifact name"):
            store.artifact_path(accepted["id"], "../field.json")
    finally:
        store.close()
