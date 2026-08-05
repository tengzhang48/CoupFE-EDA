"""End-to-end checks for the fixed localhost workbench boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import pytest


fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
DESIGN_ID = "tsv-axisymmetric-field-v1"
WORKFLOW_ID = "tsv_axisymmetric_field"
CASE_ID = "axisymmetric_tsv_thermoelastic_field_v1"
CLAIM_BOUNDARY = (
    "Axisymmetric plane-strain thermoelastic component verification against the "
    "declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface device "
    "field, experimental validation, keep-out-zone signoff, or transient cooling "
    "simulation."
)


def _snapshot(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sequence": 0,
                "mode": "connected",
                "project": {
                    "id": "coupfe-eda-local",
                    "name": "Local TSV field verification",
                    "studyType": "Axisymmetric numerical verification",
                    "activeDesignId": DESIGN_ID,
                },
                "designs": [
                    {
                        "id": DESIGN_ID,
                        "label": "30 µm TSV radial field verification",
                        "packageRevision": "examples/tsv_axisymmetric_field",
                        "createdAt": "2026-08-05T00:00:00Z",
                        "parameters": {},
                    }
                ],
                "approvedWorkflows": [
                    {
                        "id": WORKFLOW_ID,
                        "executorKey": "tsv.axisymmetric-field.v1",
                        "name": "CoupFE axisymmetric TSV field verification",
                        "description": "Fixed numerical verification case.",
                        "driverPath": "examples/tsv_axisymmetric_field/run.py",
                        "releaseValidation": False,
                        "claimBoundary": CLAIM_BOUNDARY,
                        "expectedMetricKeys": [
                            "sigma_rr_at_20um_mpa",
                            "lame_reference_sigma_rr_at_20um_mpa",
                            "lame_relative_error_percent",
                            "degrees_of_freedom",
                            "elements",
                            "actual_load_steps",
                            "newton_iterations",
                            "runtime_seconds",
                        ],
                    }
                ],
                "models": [],
                "decisions": [],
                "runs": [],
                "evidence": [],
                "artifacts": [],
                "layers": [],
                "candidates": [],
            }
        )
        + "\n"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_fake_fixed_result(monkeypatch):
    from eda_multiphysics import workbench

    def execute(_executor_key, *, run_root, repository_root=None):
        run_dir = Path(run_root).resolve() / "fixed-test-run"
        run_dir.mkdir(parents=True, exist_ok=False)
        field = {
            "schema_version": 1,
            "case_id": CASE_ID,
            "claim_boundary": CLAIM_BOUNDARY,
            "final_field": {
                "radial_displacement_nm": [0.0, 1.0],
                "sigma_rr_MPa": [-54.2],
                "sigma_theta_MPa": [-31.0],
            },
            "load_sweep": {
                "is_transient": False,
                "steps": [
                    {
                        "step_index": index,
                        "solve_kind": "independent_static_coupfe_solve",
                    }
                    for index in range(9)
                ],
            },
        }
        summary = {
            "schema_version": 1,
            "case_id": CASE_ID,
            "results": {"sigma_rr_at_20um_MPa": -54.2},
        }
        (run_dir / "field.json").write_text(json.dumps(field) + "\n")
        (run_dir / "summary.json").write_text(json.dumps(summary) + "\n")
        (run_dir / "contour.svg").write_text("<svg><path d='M0 0'/></svg>\n")
        (run_dir / "stdout.txt").write_text("fixed solver output\n")
        (run_dir / "stderr.txt").write_text("")
        artifacts = []
        for name in (
            "field.json",
            "summary.json",
            "contour.svg",
            "stdout.txt",
            "stderr.txt",
        ):
            artifact = run_dir / name
            artifacts.append(
                {
                    "name": name,
                    "sha256": _sha256(artifact),
                    "size_bytes": artifact.stat().st_size,
                }
            )
        manifest_record = {
            "schema_version": 1,
            "status": "succeeded",
            "executor_key": "tsv.axisymmetric-field.v1",
            "artifacts": artifacts,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_record) + "\n")
        return {
            **manifest_record,
            "run_id": run_dir.name,
            "elapsed_seconds": 1.25,
            "source": {"revision": "a" * 40, "tree_state": "clean"},
            "results": {
                "claim_boundary": field["claim_boundary"],
                "eda_revision": "a" * 40,
                "core_revision": "b" * 40,
                "sigma_rr_at_20um_MPa": -54.2,
                "lame_sigma_rr_at_20um_MPa": -54.0,
                "lame_relative_error": 0.0037037037,
                "degrees_of_freedom": 2400,
                "elements": 2399,
                "actual_load_steps": 9,
                "newton_iterations": 2,
                "total_load_sweep_newton_iterations": 16,
            },
            "manifest": {
                "name": "manifest.json",
                "sha256": _sha256(manifest_path),
                "size_bytes": manifest_path.stat().st_size,
            },
            "run_directory": str(run_dir),
        }

    monkeypatch.setattr(workbench, "execute_approved_workflow", execute)


def _request(client: TestClient, *, request_id: str = "api-run-1", **extra):
    return client.post(
        "/api/runs",
        json={
            "projectId": "coupfe-eda-local",
            "designId": DESIGN_ID,
            "workflowId": WORKFLOW_ID,
            "clientRequestId": request_id,
            **extra,
        },
    )


def test_local_api_reports_real_solver_metrics_and_serves_field_json(tmp_path, monkeypatch):
    from eda_multiphysics.workbench_api import create_app

    _install_fake_fixed_result(monkeypatch)
    snapshot = tmp_path / "snapshot.json"
    _snapshot(snapshot)
    app = create_app(
        run_root=tmp_path / "runs",
        repository_root=ROOT,
        snapshot_path=snapshot,
    )
    with TestClient(app) as client:
        initial = client.get("/api/projects/coupfe-eda-local")
        assert initial.status_code == 200
        assert initial.json()["approvedWorkflows"][0]["releaseValidation"] is False

        accepted = _request(client)
        assert accepted.status_code == 202
        assert "progress" not in accepted.json()
        run_id = accepted.json()["id"]
        duplicate = _request(client)
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == run_id

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            current = client.get("/api/projects/coupfe-eda-local").json()
            run = next(item for item in current["runs"] if item["id"] == run_id)
            if run["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        assert run["status"] == "succeeded"
        assert run["output"]["qualification"]["releaseValidation"] is False
        assert run["input"]["solverVersion"] == "b" * 40
        assert run["input"]["codeRevision"] == "a" * 40
        assert set(run["input"]) == {
            "designRevision",
            "packageRevision",
            "codeRevision",
            "solverVersion",
            "runtimeInputSet",
            "manifestSha256",
        }
        metrics = {
            metric["key"]: metric for metric in run["output"]["genericMetrics"]
        }
        assert set(metrics) == {
            "sigma_rr_at_20um_mpa",
            "lame_reference_sigma_rr_at_20um_mpa",
            "lame_relative_error_percent",
            "degrees_of_freedom",
            "elements",
            "actual_load_steps",
            "newton_iterations",
            "runtime_seconds",
        }
        assert metrics["sigma_rr_at_20um_mpa"]["value"] == -54.2
        assert metrics["lame_reference_sigma_rr_at_20um_mpa"]["value"] == -54.0
        assert metrics["lame_relative_error_percent"]["value"] == pytest.approx(
            0.37037037
        )
        assert metrics["degrees_of_freedom"]["value"] == 2400
        assert metrics["elements"]["value"] == 2399
        assert metrics["actual_load_steps"]["value"] == 9
        assert metrics["newton_iterations"]["value"] == 2
        assert metrics["runtime_seconds"]["value"] == 1.25
        assert "progress" not in run

        serialized = json.dumps(current)
        assert str(tmp_path) not in serialized
        artifact_kinds = {
            item["uri"].rsplit("/", 1)[-1]: item["kind"]
            for item in current["artifacts"]
        }
        assert artifact_kinds == {
            "field.json": "field",
            "summary.json": "report",
            "contour.svg": "render",
            "stdout.txt": "log",
            "stderr.txt": "log",
            "manifest.json": "manifest",
        }
        field_uri = next(
            item["uri"] for item in current["artifacts"] if item["kind"] == "field"
        )
        field_response = client.get(field_uri)
        assert field_response.status_code == 200
        served_field = field_response.json()
        assert served_field["case_id"] == CASE_ID
        assert len(served_field["load_sweep"]["steps"]) == 9


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("executorKey", "shell.arbitrary"),
        ("executablePath", "/bin/sh"),
        ("driverPath", "elsewhere/run.py"),
        ("mesh", {"nodes": 2}),
        ("load", {"delta_temperature_K": -999}),
        ("loadSteps", 1),
        ("ranks", 128),
        ("arguments", ["--output-dir", "/tmp/escape"]),
        ("outputDirectory", "/tmp/escape"),
    ],
)
def test_run_request_never_accepts_execution_or_solver_controls(
    tmp_path, monkeypatch, field, value
):
    from eda_multiphysics.workbench_api import create_app

    _install_fake_fixed_result(monkeypatch)
    snapshot = tmp_path / "snapshot.json"
    _snapshot(snapshot)
    app = create_app(
        run_root=tmp_path / "runs",
        repository_root=ROOT,
        snapshot_path=snapshot,
    )
    with TestClient(app) as client:
        rejected = _request(client, request_id=f"reject-{field}", **{field: value})
        assert rejected.status_code == 422
        assert app.state.workbench_store.list_runs() == []


def test_local_api_rejects_arbitrary_workflow_requests(tmp_path):
    from eda_multiphysics.workbench_api import create_app

    snapshot = tmp_path / "snapshot.json"
    _snapshot(snapshot)
    app = create_app(
        run_root=tmp_path / "runs",
        repository_root=ROOT,
        snapshot_path=snapshot,
    )
    with TestClient(app) as client:
        unknown = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": DESIGN_ID,
                "workflowId": "unknown",
                "clientRequestId": "unknown-request",
            },
        )
        assert unknown.status_code == 400
