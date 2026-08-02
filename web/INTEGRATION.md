# Local workbench integration contract

This document fixes the current browser/service contract. The service is loopback-only and exposes one approved workflow.

## Start the service

From the repository root:

```bash
python -m pip install -e '.[workbench]'
coupfe-eda-workbench --repository-root .
```

The current approved TSV driver uses the NumPy-based EDA screening module and
does not require a Core solve. Run `./setup.sh` for the wider examples that use
the pinned CoupFE Core checkout. The default server is
`http://127.0.0.1:8000`; its default run root is a server-owned directory under
the system temporary directory.

This is a source-checkout integration. `--repository-root` must contain the connected snapshot contract and released example driver; installing the wheel by itself does not provide a self-contained GUI bundle.

For Vite development, run `npm run dev:api` in `web/`. For same-origin use, run `npm run build:api` and restart the service with `--web-dir web/dist`.

## Fixed identifiers

| Field | Current value |
|---|---|
| Project | `coupfe-eda-local` |
| Active design | `tsv-synthetic-device-sites-v1` |
| Browser workflow ID | `tsv_device_screening` |
| Server executor key | `tsv.device-screening.v1` |
| Driver owned by server | `examples/tsv_00_device_screening/run.py` |

The initial connected read model is [`contracts/connected-project-snapshot.json`](contracts/connected-project-snapshot.json).

## HTTP operations

| Operation | Endpoint | Success |
|---|---|---|
| Load authoritative project state | `GET /api/projects/{project_id}` | `200 ProjectSnapshot` |
| Start or retrieve an idempotent run | `POST /api/runs` | `202 RunRecord` |
| Cancel a queued run | `POST /api/projects/{project_id}/runs/{run_id}/cancel` | `200 RunRecord` |
| Observe later run events | `GET /api/projects/{project_id}/events?after={sequence}` | `200 text/event-stream` |
| Read a retained run artifact | `GET /api/runs/{run_id}/artifacts/{artifact_name}` | `200 file` |

The start body is exactly:

```json
{
  "projectId": "coupfe-eda-local",
  "designId": "tsv-synthetic-device-sites-v1",
  "workflowId": "tsv_device_screening",
  "clientRequestId": "a-client-generated-idempotency-key"
}
```

Extra fields are rejected with `422`. In particular, the browser must not send `executorKey`, a command, driver path, arguments, output root, environment, or timeout. Unknown projects return `404`; an unsupported design or workflow returns `400`; idempotency conflicts and invalid cancellation state return `409`.

## Snapshot and run shape

The service returns `schemaVersion: 1` and `mode: "connected"`. The current snapshot advertises one `approvedWorkflows` entry and leaves `models`, `decisions`, `layers`, and `candidates` empty.

A run targets either a model or an approved workflow in the shared TypeScript type. This service accepts only the workflow form. Its lifecycle is:

```text
queued → running → succeeded
   └→ cancelled       └→ failed
```

This first local service cancels queued work only. Once the fixed subprocess is
running, it must finish or reach the server-owned timeout; a cancellation
request then returns `409`.

The successful TSV output contains these generic metric keys:

- `baseline_violations`
- `optimized_violations`
- `baseline_peak_abs_mobility_proxy`
- `optimized_peak_abs_mobility_proxy`
- `runtime_seconds`

It also contains:

```json
{
  "qualification": {
    "releaseValidation": false,
    "claimBoundary": "...explicit retained boundary..."
  },
  "artifactIds": ["..."],
  "evidenceIds": ["..."],
  "conclusion": "...",
  "nextAction": "..."
}
```

Violation units may be serialized as `devices`; runtime uses seconds and mobility proxies are dimensionless. The UI formats device counts as integers and displays “Release validation: not claimed.”

## Events

The snapshot has a monotonically increasing `sequence`. The browser subscribes with the last sequence it has observed:

```text
GET /api/projects/coupfe-eda-local/events?after=17
```

Each SSE `data` payload is a JSON `RunEvent` with `projectId`, `sequence`, `emittedAt`, and the changed `run`. Comment-only keep-alives carry no state. On an event, the browser reloads the project snapshot rather than treating its local event stream as the durable record.

## Artifacts and confinement

The service allocates the run directory beneath its startup-time `--run-root`. Browser input cannot change that root. Successful runs retain the source revision and clean/dirty tree state, elapsed time, evidence, stdout/stderr, SVG/CSV/JSON outputs, a manifest, and SHA-256 values. A dirty state is a warning, not a retained copy of the dirty diff.

The runtime data file is `device_sites.csv`. The driver fixes the geometry,
thermal load, threshold, and TSV identifier in code; `case.json` describes
those choices and `materials.json` records literature provenance, but neither
JSON file is read by the current driver.

The queryable run index is process-local. Successful run directories remain on
disk after shutdown, but a restarted service does not re-index them. Failed-run
details stay in the server-owned run root and are not exposed by the artifact
endpoint; that endpoint serves successful runs only.

The artifact endpoint accepts a basename from a completed run. Traversal and unknown names fail closed, and serialized project/run responses do not expose the server filesystem path.

## Frontend modes

| Build setting | Adapter | Meaning |
|---|---|---|
| `VITE_COUPFE_BACKEND=mock` | `MockBackend` | Public site; workbench route is interface-only and uses retained repository artifacts |
| `VITE_COUPFE_BACKEND=fastapi` | `FastApiBackend` | Explicit local connection to the service |

`VITE_COUPFE_API_BASE_URL` defaults to `/api`; `VITE_COUPFE_API_DEV_TARGET` controls only the Vite development proxy. Do not put credentials or private data in `VITE_*` variables because Vite exposes them to browser code.

The transport currently performs HTTP status handling and TypeScript compile-time typing, but it does not yet apply runtime JSON-schema validation to responses. Keep it paired with this repository's tested loopback service until that validation is added.

## Compatibility checklist

Before changing the API or adding a workflow:

1. update the Python Pydantic/request and response projection;
2. update `src/domain/types.ts` and the connected snapshot;
3. preserve workflow-ID-only browser requests and the server-owned registry;
4. add executor/store/API rejection and success tests;
5. add frontend backend/product tests;
6. update the repository-data checker and visible claim boundary;
7. run the Python workbench tests and `npm run check` with the Pages base path.
