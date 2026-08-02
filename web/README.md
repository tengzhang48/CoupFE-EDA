# CoupFE-EDA website and local workbench

This directory builds two deliberately separate browser surfaces from one React/Vite source tree:

- The default route is the public project website. It presents five runnable examples, the retained 526,338-DOF scaling record, project-authored figures, the synthetic TSV device-screening output, and a six-stage roadmap toward a measured real-device workflow. Every quantitative section links back to repository evidence and shows its qualification boundary.
- `?surface=workbench` opens the workbench interface. On GitHub Pages this is a clearly labeled browser-only interaction demonstration. In a local API build it can execute the one server-approved TSV screening workflow.

GitHub Pages is static. It cannot run Python, CoupFE-EDA, OpenROAD, MPI, or an FEM solver.
The public numerical values come from retained project-generated example and
benchmark records; the browser-only lifecycle does not generate replacement
engineering values.

For that reason, public-mode controls use **Simulate** and the history is
labeled **Simulated run history**. The connected local build uses **Run** and
**Recent analyses** because its loopback service executes the allowlisted
repository workflow. This wording distinction is mode-dependent; it does not
fork the shared interaction or backend contract.

## Requirements

- Node.js 22.22.2, as pinned in [`.nvmrc`](.nvmrc)
- npm
- Python 3.10 or newer only for the optional connected workbench and TSV artifact refresh

## Check and preview the public site

From this directory:

```bash
npm ci
npm run check
npm run dev
```

Open the URL printed by Vite. The website is the default route; append `?surface=workbench` to inspect the interface demonstration.

`npm run check` performs four release checks:

1. verifies every displayed repository path, retained value, roadmap stage and evidence status, and committed TSV artifact hash;
2. type-checks the strict TypeScript project;
3. runs the frontend tests;
4. prepares repository figures and legal notices and creates `dist/`.

To reproduce the GitHub Pages base path locally:

```bash
VITE_BASE_PATH=/CoupFE-EDA/ VITE_COUPFE_BACKEND=mock npm run check
VITE_BASE_PATH=/CoupFE-EDA/ VITE_COUPFE_BACKEND=mock npm run preview
```

The deployment workflow is [`.github/workflows/coupfe-workbench-pages.yml`](../.github/workflows/coupfe-workbench-pages.yml). Once GitHub Pages uses **GitHub Actions** as its source, pushes to `main` publish the static site at <https://tengzhang48.github.io/CoupFE-EDA/>.

## Run the connected local workbench

From the repository root, install CoupFE-EDA with the optional loopback API:

```bash
python -m pip install -e '.[workbench]'
coupfe-eda-workbench --repository-root .
```

The current allowlisted TSV screening driver uses the NumPy-based EDA module
and does not require a Core solve. Run `./setup.sh` separately when working with
the wider examples that use the pinned CoupFE Core checkout.

The service binds to `127.0.0.1:8000` by default and refuses a non-loopback host. In a second terminal:

```bash
cd web
npm ci
npm run dev:api
```

Open the Vite URL with `?surface=workbench` appended. During development, Vite proxies `/api` to the local service.

For one same-origin local process, build the API frontend and let FastAPI serve it:

```bash
cd web
npm run build:api
cd ..
coupfe-eda-workbench --repository-root . --web-dir web/dist
```

Then open <http://127.0.0.1:8000/?surface=workbench>.

The current connected service exposes only `tsv_device_screening`, mapped server-side to `tsv.device-screening.v1`. The browser submits project, design, workflow, and idempotency identifiers; it never submits a command, driver path, executor key, output root, or timeout. The resulting output remains labeled `releaseValidation: false` and is not real-device qualification.

Only `device_sites.csv` is read as a runtime data file by this driver; the
geometry, load, threshold, and TSV identifier remain fixed in code.
`case.json` and `materials.json` are descriptive provenance records, not hidden
runtime inputs. The service keeps its queryable run index in process memory.
Successful run directories remain on disk, but a restarted service does not
re-index them; failed-run details remain server-side rather than becoming
downloadable artifacts.

The current CLI is source-checkout-based: `--repository-root` must name a checkout containing `web/contracts/connected-project-snapshot.json` and the released example driver. The wheel alone is not a self-contained GUI or example bundle.

The local API is unauthenticated. It is suitable for one trusted local checkout, not for network or multi-user deployment.

## Repository-backed data

[`site-data.json`](site-data.json) is the display manifest, not an independent source of engineering truth. [`scripts/check-repository-data.mjs`](scripts/check-repository-data.mjs) checks it against:

- each example's README, runner, and retained numerical oracle;
- the scaling summary, table, and benchmark manifest;
- the TSV expected metrics and committed public SVG/CSV/JSON;
- the machine-readable TSV real-device evidence roadmap;
- project-authored validation-guide figures;
- the connected snapshot and approved executor boundary;
- project, media, attribution, and third-party license records.

The retained TSV browser artifacts and their reviewed SHA-256 values are listed in [`contracts/retained-tsv-artifacts.json`](contracts/retained-tsv-artifacts.json). To rerun the repository example and refresh all four files together:

```bash
npm run refresh:tsv
npm run check:data
git diff -- public/generated/tsv_device_screening contracts/retained-tsv-artifacts.json
```

Review the numerical and visual diff before committing it.

## Commands

| Command | Purpose |
|---|---|
| `npm run check:data` | Fail if displayed records, paths, boundaries, or hashes drift from repository evidence |
| `npm run prepare:data` | Run the data check, then stage repository figures and legal files under `public/` |
| `npm run refresh:tsv` | Rerun the released TSV example and refresh its public artifacts plus hash contract |
| `npm run dev` | Public website and interface demonstration using `MockBackend` |
| `npm run dev:api` | Frontend development against the loopback FastAPI service |
| `npm run typecheck` | Strict TypeScript check |
| `npm run test` | One Vitest run |
| `npm run build` | Checked static/mock production build |
| `npm run build:api` | Checked connected production build |
| `npm run check` | Type-check, test, and build the public site |

## Source organization

```text
site-data.json                   reviewed website display manifest
contracts/                      connected snapshot and retained-artifact metadata
scripts/                        repository-data checks and asset preparation
public/generated/               committed TSV demonstration outputs
src/SiteApp.tsx                 public website and explicit workbench route
src/App.tsx                     workbench interface
src/backend/                    mock and FastAPI adapters
src/demo/snapshot.ts            minimal interface-only public seed
src/domain/                     shared TypeScript contract and selectors
src/hooks/use-workbench.ts      snapshot, action, and event synchronization
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the trust boundaries and [INTEGRATION.md](INTEGRATION.md) for the exact API contract.
