# CoupFE-EDA

CoupFE-EDA is an experimental, CoupFE-based implementation for EDA-linked
electrothermal and thermo-mechanical research. The current examples cover
PDN/electrothermal handoffs, TSV stress, solder/package global-local studies,
and design-object provenance. Evidence is limited to the tests, reference
cases, and model scopes documented in this repository; this is not a signoff
tool.

AI agents assisted with implementation, documentation, and test development.
Public claims are defined by checked-in source, tests, cited references, and
engineering review; agent output by itself is not evidence.

The package consumes caller-supplied OpenROAD/OpenDB and PDNSim data through a
versioned, file-based case format. A project-authored synthetic case keeps the
integration path runnable without external design data. This repository shows
one implementation built on CoupFE. Independent projects can use other finite
element packages, coupling strategies, and data models; the checks here apply
to this implementation and its stated inputs.

CoupFE-EDA is a downstream consumer of
[CoupFE](https://github.com/tengzhang48/CoupFE). It uses the public operator
contract (`residual`, `tangent`, `commit`, `newton_solve`, and
`complex_step_tangent`) and does not modify CoupFE source. Mesh-aware adapters,
including periodic face/node matching and relation construction, remain in the
EDA package while generic affine constraints and finite-element operators remain
in core.

## Release scope

The release reports availability, evidence, input provenance, and qualification
boundary separately. A single maturity label would hide important differences
between a checked component, a synthetic integration example, and a
real-device comparison.

| Capability available now | Evidence included here | Qualification boundary |
|---|---|---|
| Analytic and component paths for PDN, heat transfer, electrothermal coupling, thermoelasticity, constitutive updates, and electromigration | Named equations, reference meshes, independent implementations, invariants, and broken controls | Applies only to the documented equations, meshes, tolerances, and parameter sets |
| Synthetic PDN → temperature → stress → solder/EM example | Closed-form PDN field, exact power closure, provenance/hash checks, and separately checked downstream components | Bundled inputs are project-authored; the composed downstream result has no fabricated-device oracle or signoff claim |
| Caller OpenDB/PDNSim case and back-annotation contracts | Parser/schema, stable-ID, unit/frame-transform, provenance, and back-annotation tests; the bundled exporter is reviewed but not executed by this suite | No bundled live OpenROAD round trip or qualification of caller-owned designs |
| Generated profiled solder, six-region package, Hex8, and Tet4 paths | Topology, Jacobian/volume, interface, boundary-condition, multimaterial, patch, and generated-mesh checks | No imported production CAD, qualified package deck, or broad mesh-convergence claim |
| Plane-strain SnPbAg `solder_joint_cycle` | Repaired numerical material tangent; every increment must satisfy Core's residual rule before one state commit | Idealized block and loading; reported energy is an example result, not package-life validation |
| Partitioned SAC305 thermo-viscoplastic cycle in `etv_fe` | Backward-Euler lumped temperature plus spatial Anand increments that meet Core's residual rule; quasisteady comparison | Unit Taylor–Quinney conversion of top-layer work to uniform heat; not a monolithic phi-T-u element or device validation |
| Multi-element `solder_joint_bvp_3d` and design-linked screening | Fail-closed 18-Hex8 dissipation field and retained design-object provenance | Idealized regular block; no crack-location, mesh/load-step-converged field, or predictive-life claim |
| `etv_distributed_fs` serial-versus-rank path | Output agreement at size 24 with two and four ranks | No scaling or performance claim; other PETSc/MPI drivers require their own retained run records |

See [EXAMPLES.md](EXAMPLES.md) and
[examples/REFERENCES.md](examples/REFERENCES.md) for entry-point evidence and
provenance.

## Quick start

```bash
conda env create -f environment.yml
conda activate coupfe-eda
./setup.sh
python -m eda_multiphysics.run
python -m pytest -q
```

`setup.sh` clones or refreshes public CoupFE `main` in `.deps/CoupFE`, checks out
and verifies commit `454f73ce2de284262b214a2b37bd676c6aca3c0a`, rejects a dirty
dependency checkout, installs both packages in editable mode, and checks the
import location. The source URL, branch, checkout directory, and commit can be
set with `COUPFE_URL`, `COUPFE_BRANCH`, `COUPFE_DIR`, and `COUPFE_REF`; changing
the commit requires a new qualification run.

The default environment includes the scientific, mesh, MPI, and open-EDA Python
dependencies. OpenROAD is installed separately or through the optional
container.

### Optional container

Docker is a convenience, not a source-release acceptance gate:

```bash
./build.sh
docker run --rm -it coupfe-eda
docker run --rm coupfe-eda python -m eda_multiphysics.run
```

The image recipe pins the CoupFE commit and OpenROAD artifact digest. The
conda-forge solve is rolling; record `conda list --explicit` when an exact
environment record is needed. See [CONTAINER.md](CONTAINER.md).

## What is included

### EDA and PDN handoffs

- `eda_multiphysics/openroad/export_case.tcl` maps OpenDB objects into the
  versioned case representation.
- PDN networks can be read from caller-supplied PDNSim `write_pg_spice` output.
- `case_thermal.py`, `electrothermal_chip.py`, and `chip_vtu.py` preserve source
  identifiers and back-annotation fields across the handoff.
- `reliability_pipeline.py` runs a deterministic synthetic IR → temperature →
  stress → screening chain. Its graph voltage is checked against the fixture's
  closed-form field, while later links rely on separate component checks. The
  composed result is a demonstration.

No ORFS GCD deck, PDK, generated design database, or raw OpenROAD output is
bundled. The project-authored fixture and caller-data boundary are documented in
[THIRD_PARTY.md](THIRD_PARTY.md).

### Generated geometry and mechanics

- `tsv_3d.py` exercises Hex8 electrothermal elements on generated cylinder,
  annulus, and layer-stack meshes with named idealized references.
- `tet_3d.py` exercises CoupFE's native Tet4 on generated box and cylinder
  meshes. With Core `454f73c`, the checked scope includes the tested generated
  shapes and conformal package case; imported STEP/BREP geometry and broader
  mesh convergence remain research work.
- `thermomech_3d.py` and `thermomech_tsv.py` cover generated thermo-mechanical
  cases and compare selected observables with free-expansion,
  constrained-block, or composite-cylinder references.
- `mesh3d.py` provides generated TSV, layer-stack, profiled-joint, and conformal
  package geometry helpers. It is not a package-CAD interface.

### Solder and electro-thermo-viscoplastic studies

- `anand.py` and `anand_3d.py` provide material-point, return-map, transient,
  affine-patch, fully prescribed `prescribed_hex8_cycle`, and fail-closed
  multi-element block examples. The measured 4719-cycle PBGA value is an
  in-sample calibration anchor, not independent validation.
- `solder_joint.py` exposes the plane-strain return-map, elastic patch, and a
  fail-closed stateful multi-element cycle example.
- `etv_solder.py` retains the simplified material-point electro-thermal-
  viscoplastic study.
- `etv_fe.py` contains the steady electrothermal Quad4 implementation and its
  analytic/staggered comparisons, plus a partitioned lumped-temperature and
  spatial-mechanics cycle example.
- `reliability_3d.py` demonstrates global parametric joint/package geometry,
  caller-supplied joint locations and provenance, and a calibration-specific
  global-local workflow. Caller joint dimensions do not currently set the FE
  mesh dimensions. `critical_joint_bvp_screening` connects the maximum-DNP
  design object to the idealized stateful block while retaining that boundary.

### TSV-to-device screening

`examples/tsv_00_device_screening/` maps a classical Lamé far-field stress proxy
onto synthetic, stable device IDs using cited piezoresistance equations. It emits
CSV, JSON, and SVG records. The result demonstrates identity-preserving mapping;
it does not establish near-surface anisotropic stress, transistor delay, Cu
protrusion, measured Raman agreement, or a signoff keep-out zone.

### Distributed execution

`etv_distributed_fs.py` includes the retained serial-versus-rank output check at
size 24 with two and four ranks. The other PETSc/MPI modules and
`scaling_bench.py` are research harnesses. Historical timing, speedup,
efficiency, and large-problem records are not release evidence without raw
output, machine inventory, and an environment record produced from the release
revision.

## Evidence and references

The release checks are separated by dependency needs:

```bash
python -m eda_multiphysics.run       # self-contained component/reference gates
python -m pytest -q                  # default regression tier
python -m pytest -q -m toolchain     # compiled, mesh, and PETSc/MPI checks
```

Test totals are intentionally omitted here because they are regenerated during
release qualification. A passing component check supports its named boundary;
it does not qualify every composed workflow or caller dataset.

The pytest toolchain tier does not run an OpenROAD/OpenDB or PDNSim round trip.
Those adapters require a caller-provided tool installation and case-specific
data.

Useful records:

- [Validation guide](docs/VALIDATION_GUIDE.md) — equations, references,
  tolerances, and claim boundaries.
- [Capabilities](docs/capabilities.md) — current implementation inventory.
- [Geometry guide](docs/GEOMETRY.md) — mesh and package geometry scope.
- [Periodic MPC status](docs/PERIODIC_MPC_STATUS.md) — ownership and dependency
  boundary.
- [Release evidence runbook](docs/RELEASE_EVIDENCE.md) — how to retain logs,
  environments, and artifact checksums.
- [Third-party record](THIRD_PARTY.md) — software, data, and attribution.

The main open milestone is real-device validation: a lawfully shareable layout
and package geometry, traceable materials and loads, documented boundary
conditions, retained solver evidence, and comparison with measured electrical,
thermal, or stress observables.

## Repository map

```text
environment.yml            conda environment
Dockerfile / build.sh      optional container recipe
setup.sh                   pinned CoupFE checkout and editable install
EXAMPLES.md                runnable example catalog
examples/REFERENCES.md     entry-point provenance and status
skills/SKILL.md            contributor workflow for adding a checked example
docs/                      theory, API, geometry, validation, and release records
eda_multiphysics/          package source and synthetic fixture
tests/                     regression and toolchain tests
```

The package modules are grouped for navigation in
[docs/COMPONENTS.md](docs/COMPONENTS.md); the grouping is organizational rather
than a maturity score.

## Acknowledgments and attribution

CoupFE-EDA uses the operator contract provided by
[CoupFE](https://github.com/tengzhang48/CoupFE) and builds on interfaces provided
by the [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) community,
including
[OpenDB](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html) and
[PDNSim](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html).
Analytic, constitutive, and reliability models are credited at the point of use,
in the [validation guide](docs/VALIDATION_GUIDE.md), and in the
[entry-point reference map](examples/REFERENCES.md). Third-party names identify
their contributions and do not imply endorsement.

The external
[ORFS GCD sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd)
helped illustrate an applicable flow. No GCD source, platform data, generated
design file, or tool output is distributed here.

## License and third-party notices

Code, tests, schemas, and configuration are Apache-2.0 licensed under
[LICENSE](LICENSE). Project-authored prose and figures are CC-BY-4.0 under the
[documentation license](docs/LICENSE.md). OpenROAD's container notice and the
boundary for caller-supplied designs are documented in [NOTICE](NOTICE),
[THIRD_PARTY.md](THIRD_PARTY.md), and [LICENSES/](LICENSES/).
