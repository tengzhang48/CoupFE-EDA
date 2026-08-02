"""Optional end-to-end checks for the localhost FastAPI workbench adapter."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest


fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "sequence": 0,
                "mode": "connected",
                "project": {
                    "id": "coupfe-eda-local",
                    "name": "Local TSV screening",
                    "studyType": "Synthetic integration demonstration",
                    "activeDesignId": "tsv-synthetic-device-sites-v1",
                    "activeDecisionId": "none",
                },
                "designs": [
                    {
                        "id": "tsv-synthetic-device-sites-v1",
                        "label": "Project-authored synthetic device sites",
                        "packageRevision": "not-applicable",
                        "createdAt": "2026-08-01T00:00:00Z",
                        "parameters": {},
                    }
                ],
                "approvedWorkflows": [
                    {
                        "id": "tsv_device_screening",
                        "executorKey": "tsv.device-screening.v1",
                        "name": "Synthetic TSV-to-device screening",
                        "description": "Released identity-preserving integration workflow.",
                        "releaseValidation": False,
                        "claimBoundary": "Demonstration only; does not validate a device or signoff flow.",
                        "expectedMetricKeys": [
                            "baseline_violations",
                            "optimized_violations",
                            "baseline_peak_abs_mobility_proxy",
                            "optimized_peak_abs_mobility_proxy",
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


def test_local_api_executes_only_advertised_workflow_and_serves_artifacts(tmp_path):
    from eda_multiphysics.workbench_api import create_app

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

        injected = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": "tsv-synthetic-device-sites-v1",
                "workflowId": "tsv_device_screening",
                "clientRequestId": "api-run-1",
                "executorKey": "shell.arbitrary",
            },
        )
        assert injected.status_code == 422

        accepted = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": "tsv-synthetic-device-sites-v1",
                "workflowId": "tsv_device_screening",
                "clientRequestId": "api-run-1",
            },
        )
        assert accepted.status_code == 202
        run_id = accepted.json()["id"]
        duplicate = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": "tsv-synthetic-device-sites-v1",
                "workflowId": "tsv_device_screening",
                "clientRequestId": "api-run-1",
            },
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == run_id

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            current = client.get("/api/projects/coupfe-eda-local").json()
            run = next(item for item in current["runs"] if item["id"] == run_id)
            if run["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert run["status"] == "succeeded"
        assert run["output"]["qualification"]["releaseValidation"] is False
        assert run["input"]["designRevision"] == "Project-authored synthetic device sites"
        assert run["input"]["packageRevision"] == "not-applicable"
        assert run["input"]["runtimeInputSet"] == (
            "examples/tsv_00_device_screening/device_sites.csv"
        )
        assert run["input"]["solverVersion"].startswith("not-applicable:")
        assert {item["key"] for item in run["output"]["genericMetrics"]} == {
            "baseline_violations",
            "optimized_violations",
            "baseline_peak_abs_mobility_proxy",
            "optimized_peak_abs_mobility_proxy",
            "runtime_seconds",
        }
        serialized = json.dumps(current)
        assert str(tmp_path) not in serialized
        artifact_kinds = {
            item["uri"].rsplit("/", 1)[-1]: item["kind"]
            for item in current["artifacts"]
        }
        assert artifact_kinds == {
            "device_screening.csv": "data",
            "device_screening.svg": "render",
            "evidence.json": "report",
            "stdout.txt": "log",
            "stderr.txt": "log",
            "manifest.json": "manifest",
        }
        result_evidence = next(
            item for item in current["evidence"] if item["category"] == "result"
        )
        assert result_evidence["authority"] == "computational-output"
        evidence_uri = next(
            item["uri"] for item in current["artifacts"] if item["id"].endswith("evidence.json")
        )
        evidence = client.get(evidence_uri)
        assert evidence.status_code == 200
        assert evidence.json()["release_validation"] is False
        manifest_uri = next(
            item["uri"] for item in current["artifacts"] if item["id"].endswith("manifest.json")
        )
        manifest = client.get(manifest_uri)
        assert manifest.status_code == 200
        assert manifest.json()["oracle"]["path"] == (
            "examples/tsv_00_device_screening/expected_metrics.json"
        )


def test_local_api_rejects_model_or_arbitrary_workflow_requests(tmp_path):
    from eda_multiphysics.workbench_api import create_app

    snapshot = tmp_path / "snapshot.json"
    _snapshot(snapshot)
    app = create_app(
        run_root=tmp_path / "runs",
        repository_root=ROOT,
        snapshot_path=snapshot,
    )
    with TestClient(app) as client:
        model = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": "tsv-synthetic-device-sites-v1",
                "modelId": "full",
                "clientRequestId": "model-request",
            },
        )
        assert model.status_code == 422
        unknown = client.post(
            "/api/runs",
            json={
                "projectId": "coupfe-eda-local",
                "designId": "tsv-synthetic-device-sites-v1",
                "workflowId": "unknown",
                "clientRequestId": "unknown-request",
            },
        )
        assert unknown.status_code == 400
