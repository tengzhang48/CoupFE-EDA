# Local TSV field workbench integration contract

This document fixes the current browser/service contract. The service is
loopback-only and exposes one approved real CoupFE workflow. The retained
GitHub Pages explorer uses the same field schema but does not call this API.

## Start the service

From the repository root, install the audited CoupFE Core checkout and the
optional API dependencies:

```bash
./setup.sh
python -m pip install -e '.[workbench]'
coupfe-eda-workbench --repository-root .
```

This setup is required because the approved driver calls the pinned Core's
`coupfe.newton_solve`; it is not the earlier NumPy-only analytic screening
path. The default server is `http://127.0.0.1:8000`, and the server refuses a
non-loopback host. Its default run root is a server-owned directory under the
system temporary directory.

This is a source-checkout integration. `--repository-root` must contain the
connected snapshot, runner, oracle, Git metadata, and importable EDA package.
Installing the wheel alone does not provide a self-contained GUI or retained
evidence bundle.

For Vite development, run `npm run dev:api` in `web/`. For same-origin use, run
`npm run build:api` and restart the service with `--web-dir web/dist`.

## Fixed identifiers and computation

| Field | Current value |
|---|---|
| Project | `coupfe-eda-local` |
| Active design | `tsv-axisymmetric-field-v1` |
| Browser workflow ID | `tsv_axisymmetric_field` |
| Server executor key | `tsv.axisymmetric-field.v1` |
| Driver owned by server | `examples/tsv_axisymmetric_field/run.py` |
| Regression oracle | `examples/tsv_axisymmetric_field/expected_results.json` |
| Driver timeout | 180 seconds |

The fixed case has a 30 µm TSV diameter, `ΔT = -400 K`, a 300 µm outer
radius, 2,400 radial nodes/DOFs, 2,399 Line2 elements, and no liner. It retains
radial displacement at nodes and `sigma_rr`/`sigma_theta` at element centers.
At 20 µm, the final field is compared with the declared published Lamé
equation under a 3% relative-error limit.

The field record contains nine prescribed-load states at
`[0, -50, -100, -150, -200, -250, -300, -350, -400] K`. Every state is a
fresh `independent_static_coupfe_solve` with its own Newton and residual
telemetry and full arrays. The ordering supports visual inspection; it is not a
transient cooling simulation and carries no time integration.

The initial connected read model is
[`contracts/connected-project-snapshot.json`](contracts/connected-project-snapshot.json).

## HTTP operations

| Operation | Endpoint | Success |
|---|---|---|
| Load authoritative project state | `GET /api/projects/{project_id}` | `200 ProjectSnapshot` |
| Start or retrieve an idempotent run | `POST /api/runs` | `202 RunRecord` |
| Cancel a queued run | `POST /api/projects/{project_id}/runs/{run_id}/cancel` | `200 RunRecord` |
| Observe later run events | `GET /api/projects/{project_id}/events?after={sequence}` | `200 text/event-stream` |
| Read a successful run artifact | `GET /api/runs/{run_id}/artifacts/{artifact_name}` | `200 file` |

The start body is exactly:

```json
{
  "projectId": "coupfe-eda-local",
  "designId": "tsv-axisymmetric-field-v1",
  "workflowId": "tsv_axisymmetric_field",
  "clientRequestId": "a-client-generated-idempotency-key"
}
```

Extra fields are rejected with `422`. The browser must not send `executorKey`,
a command, driver path, arguments, case parameters, output root, environment,
or timeout. Unknown projects return `404`; an inactive design or unsupported
workflow returns `400`; idempotency conflicts and invalid cancellation state
return `409`.

## Snapshot and run shape

The service returns `schemaVersion: 1` and `mode: "connected"`. The initial
snapshot advertises one design and one `approvedWorkflows` entry. It leaves
`models`, `decisions`, `layers`, and `candidates` empty.

A run targets either a model or an approved workflow in the shared TypeScript
type. This service accepts only the workflow form. Its lifecycle is:

```text
queued → running → succeeded
   └→ cancelled       └→ failed
```

Cancellation is supported only while work is queued. Once the fixed subprocess
is running, it must finish or reach the server-owned timeout; cancellation then
returns `409`.

A successful run exposes these generic metric keys:

- `sigma_rr_at_20um_mpa`
- `lame_reference_sigma_rr_at_20um_mpa`
- `lame_relative_error_percent`
- `degrees_of_freedom`
- `elements`
- `actual_load_steps`
- `newton_iterations`
- `runtime_seconds`

`runtime_seconds` is measured by the local executor wrapper; timing is not
embedded in the deterministic solver `summary.json`. The output also contains:

```json
{
  "qualification": {
    "releaseValidation": false,
    "claimBoundary": "Axisymmetric plane-strain thermoelastic component verification against the declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface device field, experimental validation, keep-out-zone signoff, or transient cooling simulation."
  },
  "artifactIds": ["..."],
  "evidenceIds": ["..."],
  "conclusion": "...",
  "nextAction": "..."
}
```

The workflow verifies a bounded numerical component result. It does not set
`releaseValidation: true` or claim device qualification.

## Events

The snapshot has a monotonically increasing `sequence`. The browser subscribes
with the last sequence it observed:

```text
GET /api/projects/coupfe-eda-local/events?after=17
```

Each SSE `data` payload is a JSON `RunEvent` with `projectId`, `sequence`,
`emittedAt`, and the changed `run`. Comment-only keep-alives carry no state. On
an event, the browser reloads the project snapshot instead of treating the
event stream as a durable record.

## Validation, artifacts, and confinement

The browser supplies no execution details. The server registry resolves the
executor to this fixed command shape:

```text
<current Python> examples/tsv_axisymmetric_field/run.py --output-dir <server-owned run directory>
```

Before publishing success, the executor fails closed unless all of the
following hold:

- `summary.json`, `field.json`, and the retained oracle are strict, finite JSON
  with schema version 1 and the same case identity;
- the claim boundary is the exact reviewed text;
- EDA and Core revisions are lowercase 40-hex values, the EDA revision matches
  the executing checkout, and module/operator/solver/command provenance is
  fixed;
- inputs, Line2 topology, node/element/DOF counts, connectivity, array lengths,
  regions, units, and final-state identity match the approved case;
- all nine entries are actual independent static CoupFE solves in the approved
  load order, and the final step exactly matches `final_field` and the summary;
- convergence telemetry is accepted, the FE/Lamé check passes within 3%, and
  retained numerical values match the oracle at its declared tolerance;
- `contour.svg` is present and structurally recognizable as SVG.

The driver writes `field.json`, `summary.json`, and `contour.svg`. The service
captures `stdout.txt` and `stderr.txt`, hashes all five files, and writes a
separate `manifest.json` containing the executor, driver, oracle hash, command
contract, start time, elapsed wrapper time, EDA revision/tree state, numerical
summary, and artifact sizes/hashes. The local connected run does not render
`load-sweep.webm`; that video belongs to the separately built public retained
evidence bundle.

The run directory is allocated beneath startup-time `--run-root`; browser input
cannot change it. The artifact endpoint accepts a basename from a successful
run only. Traversal and unknown names fail closed, and serialized project/run
responses never expose the filesystem path.

The queryable run index is process-local. Successful run directories remain on
disk after shutdown, but restart does not re-index them. Failed-run details
stay in the server-owned run root and are not served. A dirty source state is
recorded as `dirty`, but the manifest does not retain the dirty diff and cannot
claim exact reconstruction of it.

## Frontend modes

| Build setting | Browser behavior | Meaning |
|---|---|---|
| `VITE_COUPFE_BACKEND=retained` | No execution backend; fetch and strictly inspect the checked public field bundle | Static website and GitHub Pages explorer |
| `VITE_COUPFE_BACKEND=fastapi` | `FastApiBackend` plus the same field explorer | Explicit local connection to the one-workflow service |

`VITE_COUPFE_API_BASE_URL` defaults to `/api`;
`VITE_COUPFE_API_DEV_TARGET` controls only the Vite development proxy. Never
put credentials or private data in `VITE_*` variables because Vite exposes
them to browser code.

The field bundle has dedicated runtime validation in the browser. The generic
FastAPI transport performs HTTP status handling and TypeScript compile-time
typing but does not yet apply a runtime schema validator to every API response.
Keep it paired with this repository's tested loopback service until that
validation is added.

## Compatibility checklist

Before changing the API or adding a workflow:

1. add or update real repository solver evidence and a bounded oracle first;
2. update the Python registry, validation, Pydantic request, and response
   projection;
3. update `src/domain/types.ts` and the connected snapshot;
4. preserve workflow-ID-only browser requests and server-owned execution;
5. add executor/store/API rejection and successful real-run tests;
6. add frontend field/backend/product tests;
7. update the repository-data checker and visible claim boundary;
8. run the Python workbench tests and `npm run check` with the Pages base path.
