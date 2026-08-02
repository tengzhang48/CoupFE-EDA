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
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping
import uuid


TSV_DEVICE_EXECUTOR = "tsv.device-screening.v1"


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
    TSV_DEVICE_EXECUTOR: ApprovedWorkflow(
        executor_key=TSV_DEVICE_EXECUTOR,
        label="Synthetic TSV-to-device screening",
        driver="examples/tsv_00_device_screening/run.py",
        oracle="examples/tsv_00_device_screening/expected_metrics.json",
        timeout_seconds=120.0,
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


def _validate_tsv_device_evidence(
    record: Any,
    *,
    oracle: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise WorkbenchExecutionError("TSV device evidence must be a JSON object")
    required = {
        "example_scope",
        "model_scope",
        "release_validation",
        "device_site_provenance",
        "n_devices",
        "baseline_violations",
        "optimized_violations",
        "baseline_peak_abs_mobility_change",
        "optimized_peak_abs_mobility_change",
        "claim_boundary",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise WorkbenchExecutionError(
            f"TSV device evidence is missing required fields: {', '.join(missing)}"
        )
    if record["release_validation"] is not False:
        raise WorkbenchExecutionError(
            "the approved TSV screening workflow must remain labeled as non-validation evidence"
        )
    if not isinstance(record["claim_boundary"], str) or "does not validate" not in record[
        "claim_boundary"
    ].lower():
        raise WorkbenchExecutionError("TSV device evidence is missing its qualification boundary")
    for field in ("n_devices", "baseline_violations", "optimized_violations"):
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise WorkbenchExecutionError(f"TSV device evidence field {field!r} is invalid")
    for field in (
        "baseline_peak_abs_mobility_change",
        "optimized_peak_abs_mobility_change",
    ):
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise WorkbenchExecutionError(f"TSV device evidence field {field!r} is invalid")

    tolerance = oracle.get("tolerance", {}).get("absolute")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
        raise WorkbenchExecutionError("TSV regression oracle has an invalid absolute tolerance")
    for field in ("n_devices", "baseline_violations", "optimized_violations"):
        if record[field] != oracle.get(field):
            raise WorkbenchExecutionError(
                f"TSV device evidence does not match the retained regression oracle for {field}"
            )
    for field in (
        "baseline_peak_abs_mobility_change",
        "optimized_peak_abs_mobility_change",
    ):
        expected = oracle.get(field)
        if (
            isinstance(expected, bool)
            or not isinstance(expected, (int, float))
            or not math.isclose(record[field], expected, rel_tol=0.0, abs_tol=tolerance)
        ):
            raise WorkbenchExecutionError(
                f"TSV device evidence does not match the retained regression oracle for {field}"
            )
    return record


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
        raise WorkbenchExecutionError(f"unsupported workbench executor: {executor_key!r}") from error

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
    try:
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchExecutionError(
            f"approved workflow oracle is unavailable: {workflow.oracle}"
        ) from error
    if not isinstance(oracle, dict):
        raise WorkbenchExecutionError("approved workflow oracle must be a JSON object")
    identity = _repository_identity(repository)

    owned_root = Path(run_root).expanduser().resolve()
    owned_root.mkdir(parents=True, exist_ok=True)
    if not owned_root.is_dir():
        raise WorkbenchExecutionError("workbench run root is not a directory")
    run_dir = Path(
        tempfile.mkdtemp(prefix="tsv-device-screening-", dir=owned_root)
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

    evidence_path = run_dir / "evidence.json"
    try:
        evidence = _validate_tsv_device_evidence(
            json.loads(evidence_path.read_text(encoding="utf-8")),
            oracle=oracle,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchExecutionError("approved workflow did not write valid evidence.json") from error

    required_artifacts = (
        "device_screening.csv",
        "device_screening.svg",
        "evidence.json",
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
        "evidence": evidence,
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
                "claimBoundary": (
                    "Synthetic identity-preserving integration demonstration; "
                    "not experimental TSV, device-performance, or signoff validation."
                ),
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
            "evidence": result["evidence"],
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
                raise WorkbenchExecutionError("run artifacts are unavailable until the run succeeds")
            output = record.get("output", {})
            names = {artifact["name"] for artifact in output.get("artifacts", [])}
            names.add("manifest.json")
            if artifact_name not in names:
                raise WorkbenchExecutionError(f"unknown run artifact: {artifact_name!r}")
        path = (run_directory / artifact_name).resolve()
        if path.parent != run_directory or not path.is_file():
            raise WorkbenchExecutionError("run artifact is unavailable")
        return path
