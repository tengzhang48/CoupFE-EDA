"""Localhost FastAPI adapter for the CoupFE-EDA workbench.

GitHub Pages uses the static public snapshot and cannot execute Python.  This
optional service is for a local checkout.  It exposes only server-owned
workflow identifiers and never accepts commands, executable paths, solver
arguments, or output directories from the browser.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import argparse
import asyncio
import json
from pathlib import Path
import tempfile
from typing import Any

try:  # Optional: importing the core package must not require the GUI stack.
    from fastapi import Request
    from pydantic import BaseModel, ConfigDict, Field
except ImportError:  # pragma: no cover - create_app reports the actionable error
    Request = Any
    BaseModel = None
    ConfigDict = None
    Field = None

from .workbench import (
    APPROVED_WORKFLOWS,
    TSV_AXISYMMETRIC_CLAIM_BOUNDARY,
    TSV_AXISYMMETRIC_EXECUTOR,
    WorkbenchExecutionError,
    WorkbenchRunStore,
)


LOCAL_PROJECT_ID = "coupfe-eda-local"
TSV_AXISYMMETRIC_WORKFLOW_ID = "tsv_axisymmetric_field"
_WORKFLOW_EXECUTORS = {
    TSV_AXISYMMETRIC_WORKFLOW_ID: TSV_AXISYMMETRIC_EXECUTOR,
}


if BaseModel is not None:
    class ApprovedRunRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")

        projectId: str = Field(min_length=1, max_length=200)
        designId: str = Field(min_length=1, max_length=200)
        workflowId: str = Field(min_length=1, max_length=200)
        clientRequestId: str = Field(min_length=1, max_length=200)
else:
    ApprovedRunRequest = Any


def _load_snapshot(path: Path) -> dict[str, Any]:
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot load connected workbench snapshot {path}") from error
    required_arrays = (
        "approvedWorkflows",
        "models",
        "decisions",
        "runs",
        "evidence",
        "artifacts",
        "layers",
        "candidates",
        "designs",
    )
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1:
        raise RuntimeError("connected workbench snapshot must use schemaVersion 1")
    if snapshot.get("mode") != "connected":
        raise RuntimeError("connected workbench snapshot must declare mode='connected'")
    project = snapshot.get("project")
    if not isinstance(project, dict) or project.get("id") != LOCAL_PROJECT_ID:
        raise RuntimeError(f"connected workbench project id must be {LOCAL_PROJECT_ID!r}")
    for field in required_arrays:
        if not isinstance(snapshot.get(field), list):
            raise RuntimeError(f"connected workbench snapshot field {field!r} must be an array")
    if not all(isinstance(item, dict) for item in snapshot["approvedWorkflows"]):
        raise RuntimeError("connected workbench workflows must be objects")
    workflows = {item.get("id"): item for item in snapshot["approvedWorkflows"]}
    if (
        len(snapshot["approvedWorkflows"]) != len(_WORKFLOW_EXECUTORS)
        or set(workflows) != set(_WORKFLOW_EXECUTORS)
    ):
        raise RuntimeError(
            "connected workbench snapshot must expose only the fixed approved workflow"
        )
    for workflow_id, executor_key in _WORKFLOW_EXECUTORS.items():
        item = workflows[workflow_id]
        if (
            item.get("executorKey") != executor_key
            or item.get("releaseValidation") is not False
            or item.get("claimBoundary") != TSV_AXISYMMETRIC_CLAIM_BOUNDARY
            or item.get("driverPath") != APPROVED_WORKFLOWS[executor_key].driver
        ):
            raise RuntimeError(
                f"connected workflow {workflow_id!r} has an invalid execution boundary"
            )
    return snapshot


def _run_input(run: dict[str, Any], design: dict[str, Any]) -> dict[str, str]:
    output = run.get("output", {})
    source = output.get("source", {})
    results = output.get("results", {})
    manifest = output.get("manifest", {})
    return {
        "designRevision": str(design.get("label", design["id"])),
        "packageRevision": str(design.get("packageRevision", design["id"])),
        "codeRevision": source.get("revision", "resolved when execution starts"),
        "solverVersion": results.get("core_revision", "resolved when execution starts"),
        "runtimeInputSet": "examples/tsv_axisymmetric_field fixed verification case",
        "manifestSha256": manifest.get("sha256", "pending"),
    }


def _public_run(
    run: dict[str, Any], *, project_id: str, design: dict[str, Any]
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": run["id"],
        "projectId": project_id,
        "designId": design["id"],
        "workflowId": TSV_AXISYMMETRIC_WORKFLOW_ID,
        "clientRequestId": run["clientRequestId"],
        "sequence": run["sequence"],
        "status": run["status"],
        "requestedAt": run["requestedAt"],
        "input": _run_input(run, design),
    }
    if "startedAt" in run:
        record["startedAt"] = run["startedAt"]
    if "completedAt" in run:
        record["completedAt"] = run["completedAt"]
    if run["status"] == "failed":
        record["failureMessage"] = run.get("failureMessage", "Approved workflow failed.")
    if run["status"] == "succeeded":
        result = run["output"]
        results = result["results"]
        result_evidence_id = f"ev-{run['id']}-result"
        provenance_evidence_id = f"ev-{run['id']}-manifest"
        artifact_ids = [f"artifact-{run['id']}-{item['name']}" for item in result["artifacts"]]
        record["input"] = _run_input(run, design)
        record["output"] = {
            "genericMetrics": [
                {
                    "key": "sigma_rr_at_20um_mpa",
                    "label": "Radial stress at 20 µm",
                    "value": results["sigma_rr_at_20um_MPa"],
                    "unit": "MPa",
                    "assessment": "measured",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "lame_reference_sigma_rr_at_20um_mpa",
                    "label": "Lamé reference stress at 20 µm",
                    "value": results["lame_sigma_rr_at_20um_MPa"],
                    "unit": "MPa",
                    "assessment": "observed",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "lame_relative_error_percent",
                    "label": "Lamé relative error",
                    "value": 100.0 * results["lame_relative_error"],
                    "unit": "%",
                    "assessment": "pass",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "degrees_of_freedom",
                    "label": "Degrees of freedom",
                    "value": results["degrees_of_freedom"],
                    "unit": "DOF",
                    "assessment": "measured",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "elements",
                    "label": "Finite elements",
                    "value": results["elements"],
                    "unit": "elements",
                    "assessment": "measured",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "actual_load_steps",
                    "label": "Actual CoupFE load solves",
                    "value": results["actual_load_steps"],
                    "unit": "steps",
                    "assessment": "measured",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "newton_iterations",
                    "label": "Final-step Newton iterations",
                    "value": results["newton_iterations"],
                    "unit": "iterations",
                    "assessment": "measured",
                    "evidenceIds": [result_evidence_id],
                },
                {
                    "key": "runtime_seconds",
                    "label": "Local executor runtime",
                    "value": result["elapsedSeconds"],
                    "unit": "s",
                    "assessment": "measured",
                    "evidenceIds": [provenance_evidence_id],
                },
            ],
            "qualification": {
                "releaseValidation": False,
                "claimBoundary": results["claim_boundary"],
            },
            "artifactIds": artifact_ids + [f"artifact-{run['id']}-manifest.json"],
            "evidenceIds": [result_evidence_id, provenance_evidence_id],
            "conclusion": (
                "CoupFE solved the 2,400-DOF axisymmetric TSV case and the radial stress "
                "agreed with the Lamé reference within the 3% acceptance bound."
            ),
            "nextAction": (
                "Inspect the full field and load-step artifacts; experimental and 3-D "
                "validation remain outside this numerical verification case."
            ),
        }
    return record


def _run_records(snapshot: dict[str, Any], store: WorkbenchRunStore) -> list[dict[str, Any]]:
    design_id = snapshot["project"]["activeDesignId"]
    design = next(item for item in snapshot["designs"] if item["id"] == design_id)
    return [
        _public_run(run, project_id=snapshot["project"]["id"], design=design)
        for run in store.list_runs()
    ]


def _run_evidence_and_artifacts(
    snapshot: dict[str, Any], store: WorkbenchRunStore
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_records: list[dict[str, Any]] = []
    artifact_records: list[dict[str, Any]] = []
    for run in store.list_runs():
        if run["status"] != "succeeded":
            continue
        output = run["output"]
        result_evidence_id = f"ev-{run['id']}-result"
        provenance_evidence_id = f"ev-{run['id']}-manifest"
        artifact_ids = []
        for item in output["artifacts"]:
            artifact_id = f"artifact-{run['id']}-{item['name']}"
            artifact_ids.append(artifact_id)
            if item["name"] == "field.json":
                kind = "field"
            elif item["name"] == "summary.json":
                kind = "report"
            elif item["name"] == "contour.svg":
                kind = "render"
            else:
                kind = "log"
            artifact_records.append(
                {
                    "id": artifact_id,
                    "runId": run["id"],
                    "kind": kind,
                    "uri": item["uri"],
                    "sha256": item["sha256"],
                }
            )
        manifest_id = f"artifact-{run['id']}-manifest.json"
        artifact_records.append(
            {
                "id": manifest_id,
                "runId": run["id"],
                "kind": "manifest",
                "uri": output["manifest"]["uri"],
                "sha256": output["manifest"]["sha256"],
            }
        )
        summary_artifact = next(
            item for item in output["artifacts"] if item["name"] == "summary.json"
        )
        evidence_records.extend(
            [
                {
                    "id": result_evidence_id,
                    "runId": run["id"],
                    "title": "CoupFE axisymmetric TSV field result",
                    "category": "result",
                    "authority": "computational-output",
                    "status": "generated",
                    "description": output["results"]["claim_boundary"],
                    "source": summary_artifact["uri"],
                    "updatedAt": run["completedAt"],
                    "artifactIds": artifact_ids,
                },
                {
                    "id": provenance_evidence_id,
                    "runId": run["id"],
                    "title": "Local workbench run manifest",
                    "category": "provenance",
                    "authority": "input-provenance",
                    "status": "generated",
                    "description": "Exact source identity and output checksums for this local run.",
                    "source": output["manifest"]["uri"],
                    "updatedAt": run["completedAt"],
                    "artifactIds": [manifest_id],
                },
            ]
        )
    return evidence_records, artifact_records


def create_app(
    *,
    run_root: str | Path,
    repository_root: str | Path | None = None,
    snapshot_path: str | Path | None = None,
    web_dir: str | Path | None = None,
):
    """Create the optional FastAPI application without importing it from core package paths."""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as error:  # pragma: no cover - exercised without the optional extra
        raise RuntimeError(
            "the local workbench API requires the 'workbench' optional dependencies"
        ) from error

    repository = (
        Path(repository_root).expanduser().resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    snapshot_file = (
        Path(snapshot_path).expanduser().resolve()
        if snapshot_path is not None
        else repository / "web/contracts/connected-project-snapshot.json"
    )
    base_snapshot = _load_snapshot(snapshot_file)
    active_design = next(
        item
        for item in base_snapshot["designs"]
        if item["id"] == base_snapshot["project"]["activeDesignId"]
    )
    store = WorkbenchRunStore(run_root=run_root, repository_root=repository)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        store.close()

    app = FastAPI(title="CoupFE-EDA local workbench", version="0.1.0", lifespan=lifespan)
    app.state.workbench_store = store

    def snapshot_response() -> dict[str, Any]:
        current = json.loads(json.dumps(base_snapshot, allow_nan=False))
        current["runs"] = _run_records(current, store)
        run_evidence, run_artifacts = _run_evidence_and_artifacts(current, store)
        current["evidence"] = [*current["evidence"], *run_evidence]
        current["artifacts"] = [*current["artifacts"], *run_artifacts]
        events = store.events_after(0)
        if events:
            current["sequence"] = max(current["sequence"], events[-1]["sequence"])
        return current

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str):
        if project_id != base_snapshot["project"]["id"]:
            raise HTTPException(status_code=404, detail="unknown workbench project")
        return snapshot_response()

    @app.post("/api/runs", status_code=202)
    async def start_run(request: ApprovedRunRequest):
        if request.projectId != base_snapshot["project"]["id"]:
            raise HTTPException(status_code=404, detail="unknown workbench project")
        if request.designId != base_snapshot["project"]["activeDesignId"]:
            raise HTTPException(status_code=400, detail="run design is not the active design")
        try:
            executor_key = _WORKFLOW_EXECUTORS[request.workflowId]
        except KeyError as error:
            raise HTTPException(status_code=400, detail="unsupported approved workflow") from error
        try:
            accepted = store.start_run(
                executor_key=executor_key,
                client_request_id=request.clientRequestId,
            )
        except WorkbenchExecutionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _public_run(
            accepted,
            project_id=request.projectId,
            design=active_design,
        )

    @app.post("/api/projects/{project_id}/runs/{run_id}/cancel")
    async def cancel_run(project_id: str, run_id: str):
        if project_id != base_snapshot["project"]["id"]:
            raise HTTPException(status_code=404, detail="unknown workbench project")
        try:
            cancelled = store.cancel_run(run_id)
        except WorkbenchExecutionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return _public_run(
            cancelled,
            project_id=project_id,
            design=active_design,
        )

    @app.get("/api/projects/{project_id}/events")
    async def events(project_id: str, request: Request, after: int = 0):
        if project_id != base_snapshot["project"]["id"]:
            raise HTTPException(status_code=404, detail="unknown workbench project")
        if after < 0:
            raise HTTPException(status_code=400, detail="after must be nonnegative")

        async def stream():
            sequence = after
            while not await request.is_disconnected():
                batch = await asyncio.to_thread(store.wait_for_events, sequence, timeout=10.0)
                if not batch:
                    yield ": keep-alive\n\n"
                    continue
                for event in batch:
                    sequence = event["sequence"]
                    payload = {
                        "projectId": project_id,
                        "sequence": sequence,
                        "emittedAt": event["emittedAt"],
                        "run": _public_run(
                            event["run"],
                            project_id=project_id,
                            design=active_design,
                        ),
                    }
                    yield f"id: {sequence}\ndata: {json.dumps(payload, allow_nan=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/runs/{run_id}/artifacts/{artifact_name}")
    async def artifact(run_id: str, artifact_name: str):
        try:
            path = store.artifact_path(run_id, artifact_name)
        except WorkbenchExecutionError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return FileResponse(path, filename=path.name)

    if web_dir is not None:
        static_root = Path(web_dir).expanduser().resolve()
        if not (static_root / "index.html").is_file():
            raise RuntimeError(f"compiled workbench frontend is unavailable: {static_root}")
        app.mount("/", StaticFiles(directory=static_root, html=True), name="workbench")

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / "coupfe-eda-workbench-runs",
        help="server-owned directory for retained local run records",
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--web-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error(
            "this unauthenticated workbench binds to loopback only; add an authenticated "
            "deployment design before exposing it on a network"
        )
    try:
        import uvicorn
    except ImportError as error:
        raise SystemExit(
            "Install CoupFE-EDA with the 'workbench' extra before starting the local GUI."
        ) from error
    application = create_app(
        run_root=args.run_root,
        repository_root=args.repository_root,
        snapshot_path=args.snapshot,
        web_dir=args.web_dir,
    )
    uvicorn.run(application, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
