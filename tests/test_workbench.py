"""Tests for the local workbench's allowlisted execution boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_approved_tsv_workflow_import_path_does_not_require_core():
    code = r'''
import builtins

original_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "coupfe" or name.startswith("coupfe."):
        raise AssertionError(f"the lightweight TSV workflow imported Core: {name}")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
from examples.tsv_00_device_screening.run import run

_, _, evidence = run()
assert evidence["baseline_violations"] == 12
assert evidence["optimized_violations"] == 0
'''
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_workbench_rejects_unknown_executor_before_creating_output(tmp_path):
    from eda_multiphysics.workbench import WorkbenchExecutionError, execute_approved_workflow

    with pytest.raises(WorkbenchExecutionError, match="unsupported workbench executor"):
        execute_approved_workflow(
            "shell.arbitrary",
            run_root=tmp_path,
            repository_root=ROOT,
        )
    assert list(tmp_path.iterdir()) == []


def test_tsv_device_executor_runs_real_example_and_retains_provenance(tmp_path):
    from eda_multiphysics.workbench import TSV_DEVICE_EXECUTOR, execute_approved_workflow

    manifest = execute_approved_workflow(
        TSV_DEVICE_EXECUTOR,
        run_root=tmp_path,
        repository_root=ROOT,
    )
    run_dir = Path(manifest["run_directory"])
    assert run_dir.parent == tmp_path.resolve()
    assert manifest["status"] == "succeeded"
    assert manifest["executor_key"] == TSV_DEVICE_EXECUTOR
    assert manifest["oracle"]["path"] == (
        "examples/tsv_00_device_screening/expected_metrics.json"
    )
    assert len(manifest["oracle"]["sha256"]) == 64
    expected_revision = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert manifest["source"]["revision"] == expected_revision
    assert manifest["source"]["tree_state"] in {"clean", "dirty"}

    evidence = manifest["evidence"]
    expected = json.loads(
        (ROOT / "examples/tsv_00_device_screening/expected_metrics.json").read_text()
    )
    assert evidence["release_validation"] is False
    assert evidence["n_devices"] == expected["n_devices"]
    assert evidence["baseline_violations"] == expected["baseline_violations"]
    assert evidence["optimized_violations"] == expected["optimized_violations"]
    assert evidence["baseline_peak_abs_mobility_change"] == pytest.approx(
        expected["baseline_peak_abs_mobility_change"],
        abs=expected["tolerance"]["absolute"],
    )
    assert evidence["optimized_peak_abs_mobility_change"] == pytest.approx(
        expected["optimized_peak_abs_mobility_change"],
        abs=expected["tolerance"]["absolute"],
    )
    assert "does not validate" in evidence["claim_boundary"].lower()

    artifact_names = {artifact["name"] for artifact in manifest["artifacts"]}
    assert artifact_names == {
        "device_screening.csv",
        "device_screening.svg",
        "evidence.json",
        "stdout.txt",
        "stderr.txt",
    }
    assert all(len(artifact["sha256"]) == 64 for artifact in manifest["artifacts"])
    retained_contract = json.loads(
        (ROOT / "web/contracts/retained-tsv-artifacts.json").read_text()
    )
    retained_hashes = {
        artifact["name"]: artifact["sha256"]
        for artifact in retained_contract["artifacts"]
    }
    generated_hashes = {
        artifact["name"]: artifact["sha256"]
        for artifact in manifest["artifacts"]
        if artifact["name"] in retained_hashes
    }
    assert generated_hashes == retained_hashes
    assert (run_dir / "manifest.json").is_file()
    assert len(manifest["manifest"]["sha256"]) == 64


def test_workbench_allocates_a_new_directory_per_run(tmp_path):
    from eda_multiphysics.workbench import TSV_DEVICE_EXECUTOR, execute_approved_workflow

    first = execute_approved_workflow(
        TSV_DEVICE_EXECUTOR,
        run_root=tmp_path,
        repository_root=ROOT,
    )
    second = execute_approved_workflow(
        TSV_DEVICE_EXECUTOR,
        run_root=tmp_path,
        repository_root=ROOT,
    )
    assert first["run_id"] != second["run_id"]
    assert Path(first["run_directory"]).is_dir()
    assert Path(second["run_directory"]).is_dir()


def test_tsv_device_evidence_must_match_the_retained_oracle():
    from eda_multiphysics import workbench

    oracle = json.loads(
        (ROOT / "examples/tsv_00_device_screening/expected_metrics.json").read_text()
    )
    record = {
        "example_scope": "synthetic_identity_preserving_integration",
        "model_scope": "classical_lame_far_field_device_screening_proxy",
        "release_validation": False,
        "device_site_provenance": "synthetic_radial_angular_sampling",
        "n_devices": oracle["n_devices"],
        "baseline_violations": oracle["baseline_violations"] + 1,
        "optimized_violations": oracle["optimized_violations"],
        "baseline_peak_abs_mobility_change": oracle[
            "baseline_peak_abs_mobility_change"
        ],
        "optimized_peak_abs_mobility_change": oracle[
            "optimized_peak_abs_mobility_change"
        ],
        "claim_boundary": "This does not validate an experimental TSV or device.",
    }
    with pytest.raises(workbench.WorkbenchExecutionError, match="retained regression oracle"):
        workbench._validate_tsv_device_evidence(record, oracle=oracle)


def test_run_store_is_idempotent_and_does_not_expose_server_paths(tmp_path):
    from eda_multiphysics.workbench import TSV_DEVICE_EXECUTOR, WorkbenchRunStore

    store = WorkbenchRunStore(run_root=tmp_path, repository_root=ROOT)
    try:
        accepted = store.start_run(
            executor_key=TSV_DEVICE_EXECUTOR,
            client_request_id="browser-request-1",
        )
        duplicate = store.start_run(
            executor_key=TSV_DEVICE_EXECUTOR,
            client_request_id="browser-request-1",
        )
        assert duplicate["id"] == accepted["id"]
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            completed = store.get_run(accepted["id"])
            if completed["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert completed["status"] == "succeeded"
        serialized = json.dumps(completed)
        assert str(tmp_path) not in serialized
        assert "run_directory" not in serialized
        assert completed["output"]["evidence"]["release_validation"] is False
        assert store.artifact_path(accepted["id"], "evidence.json").is_file()
        with pytest.raises(Exception, match="invalid artifact name"):
            store.artifact_path(accepted["id"], "../evidence.json")
    finally:
        store.close()


def test_run_store_rejects_idempotency_key_reuse_for_another_executor(tmp_path):
    from eda_multiphysics import workbench

    second = workbench.ApprovedWorkflow(
        executor_key="test.second.v1",
        label="Test-only second workflow",
        driver="examples/tsv_00_device_screening/run.py",
        oracle="examples/tsv_00_device_screening/expected_metrics.json",
        timeout_seconds=120.0,
    )
    original = workbench.APPROVED_WORKFLOWS
    workbench.APPROVED_WORKFLOWS = {**original, second.executor_key: second}
    store = workbench.WorkbenchRunStore(run_root=tmp_path, repository_root=ROOT)
    try:
        store.start_run(
            executor_key=workbench.TSV_DEVICE_EXECUTOR,
            client_request_id="same-key",
        )
        with pytest.raises(workbench.WorkbenchExecutionError, match="different executor"):
            store.start_run(executor_key=second.executor_key, client_request_id="same-key")
    finally:
        store.close()
        workbench.APPROVED_WORKFLOWS = original
