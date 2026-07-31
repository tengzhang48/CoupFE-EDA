# CoupFE-EDA

Open, EDA-coupled **electro-thermo-mechanical multiphysics**, built on the
[CoupFE](https://github.com/tengzhang48/CoupFE) operator contract.

**Niche and strength:** CoupFE-EDA is strongest as an EDA-aware, validation-first integration and
local-reliability research platform—especially PDN/electrothermal handoffs, thermo-mechanical TSV
stress, solder/package global-local analysis, and traceable design-object provenance. It is not a
universal multiphysics package, package-CAD system, broad electromagnetic/CFD suite, or signoff tool.

The current architecture has **12 logical components implemented by 44 top-level Python modules**;
the count and boundaries are defined in [`docs/COMPONENTS.md`](docs/COMPONENTS.md).

This project couples caller-supplied OpenROAD/OpenDB and PDNSim data to a finite-element
multiphysics solver for steady electrothermal power-delivery-network analysis, TSV
thermomechanical stress, viscoplastic solder fatigue, electromigration, and more. A small
project-authored synthetic case makes the integration path runnable without external design
data. The trust suite validates the implemented numerical links against published or analytic
oracles where available and checks other handoffs structurally. Those component checks
do not provide an end-to-end device oracle; the experimental TSV-to-device claims
remain blocked as described below.

This release begins laying the **framework and foundation**: a solver-neutral case
format, OpenROAD/OpenDB and PDNSim adapters, traceable object/provenance fields,
multiphysics handoffs, and independently checked numerical components. The bundled
synthetic case is the first simple, reproducible demonstration of that direction—not
a finished framework or a substitute for a qualified real design.

It is a **downstream consumer of CoupFE**: CoupFE is a pinned dependency installed by
`setup.sh`; *no CoupFE core file is modified here*. The entire suite is built on the public
operator contract (`residual`/`tangent`/`commit`, `newton_solve`, `complex_step_tangent`).
That clean separation is the point — CoupFE stays lean ("lightweight by omission"); this
project grows independently.

This repository shows **what one implementation can do now**. It is not a
prescribed architecture or a proposed field-wide standard. Others can build
entirely new EDA–multiphysics packages around different FEM solvers, coupling
strategies, and data models. The tests and numerical claims here apply only to
this CoupFE-based implementation.

**Release label:** experimental alpha research software. Public source availability is not a
declaration that the TSV validation program is complete. The device-screening example remains a
Lamé-proxy preview, the ten-category TSV scorecard is not green, and this is not a foundry or
package-reliability signoff tool. See the
[validation guide](docs/VALIDATION_GUIDE.md), [release scorecard](benchmarks/tsv_release_scorecard.json),
and [third-party record](THIRD_PARTY.md).

## Quick start (local conda)

```bash
conda env create -f environment.yml        # scientific + petsc4py/mpi4py + yosys + volare
conda activate coupfe-eda
./setup.sh                                  # clones CoupFE + installs both (editable)
python -m eda_multiphysics.run              # 53 trust gates (~32 s)
```

`setup.sh` clones the public CoupFE repository into the dedicated `.deps/CoupFE` checkout,
verifies that public branch `main` contains the exact audited commit, installs that source
path, and verifies the imported module location. Overrides are available through
`COUPFE_URL` / `COUPFE_BRANCH` / `COUPFE_DIR` / `COUPFE_REF`. The environment carries the full
open-EDA + MPI stack; OpenROAD itself is not on conda — install a compatible binary (the container does this
for you, see below) or build from source.

Periodic TSV mechanics requires pinned CoupFE core commit
`933e497301ee3ddb23391b787726674f70b480c5`; `setup.sh` records it by default.
That qualified Core release root is reachable from public `main`. The setup,
container recipe, CI, and release checks all verify the exact revision rather
than trusting a mutable branch tip or a name-only package dependency.
The fast suite exercises the clean EDA periodic adapter, generic affine
algebra, matching, and setup controls. See
`docs/PERIODIC_MPC_STATUS.md` and the validation guide's
periodic-MPC environment section before changing the dependency or reporting periodic results.
The selected Core release root contains both generic affine MPC and native
Tet4; the current EDA qualification uses that exact public revision.

## Quick start (optional container)

Docker is optional and is not a source-release acceptance gate; the conda +
`setup.sh` path above runs the complete qualification directly. The container
recipe is a convenience for users who want one image containing the pinned/tested Precision
Innovations Ubuntu 22.04 OpenROAD binary `2.0-17598` (2024-12-14), yosys, and the PETSc/MPI
stack. The core commit and OpenROAD artifact digest are pinned; most conda-forge packages are a
rolling compatible solve, so archive `conda list --explicit` when a byte-for-byte environment is
required. The Dockerfile clones CoupFE over public HTTPS and verifies the same branch and commit:

```bash
./build.sh                                  # -> image; 53-gate harness plus default pytest tier
docker run --rm -it coupfe-eda              # interactive shell with the whole toolchain
docker run --rm coupfe-eda \
    mpirun -n 4 python -m eda_multiphysics.pdn_distributed 400 --direct   # MPICH oversubscribes by default
COUPFE_REF=<sha> ./build.sh                 # pin a specific CoupFE commit
```

The default pytest tier includes wrappers for all 53 trust gates plus additional
integration, CLI, and TSV tests. The container runs the standalone harness first and then that
default tier, so these are overlapping checks rather than 147 independent tests.

Full details — what's inside, build knobs, design decisions, verification evidence, and
troubleshooting — are in **[CONTAINER.md](CONTAINER.md)**.
The [release-evidence runbook](docs/RELEASE_EVIDENCE.md) defines the clean-root
test/build record, retained logs and checksums, and the transient `dist/` policy.

## The Trust Suite (53 Self-Contained Gates)

`python -m eda_multiphysics.run` (or `pytest eda_multiphysics`) runs 53 gates
covering published/analytic oracles, independent implementation comparisons,
invariants, and interface contracts, with broken controls where they are
meaningful — numpy+scipy+coupfe only, no OpenROAD/PETSc needed:

| domain | examples (oracle) |
|---|---|
| Electrical / PDN | conduction (Ohm); PDN-graph vs scipy; capacitance (ε·A/d) |
| Thermal | steady (patch/parabolic); transient ((π/L)²α); thermal runaway (saddle-node); **h-convergence (2nd-order O(h²))** |
| Electrothermal | Joule self-heating (σV0²/8k); coupled R(T) |
| Thermomechanics | TSV (Lamé); bimetal (Timoshenko); cylinder (T&G); axisym (Lamé) |
| Viscoplastic reliability | Anand saturation (SnPb); **SAC305 vs published Motalab Fig 3.10**; 2D and **3D Hex8** Anand return maps; **3D BVP corner-dW gradient**; Motalab 19 mm PBGA measured 4719-cycle case used as an **in-sample calibration anchor** (±2×), not independent validation; Darveaux/Syed; creep; electromigration (Black/Blech) |

## Bigger demonstrations

- **Capstone — design → reliability scorecard** (`reliability_pipeline.py`): one automated
  chain on a deterministic, project-authored synthetic case — PDN IR → electrothermal
  ΔT → TSV stress → SAC305 solder life → EM screen. The graph solve is checked against the
  fixture's full closed-form voltage field; its per-instance `V×I` heat and resistor
  loss close to source power during R(T) coupling. The remaining numerical stages
  retain separate component gates. `python -m eda_multiphysics.reliability_pipeline`
  prints the scorecard.
  This is an integration demonstration, not real-design validation or signoff.
- **Caller-supplied OpenROAD designs** (need the EDA toolchain — easiest via the container, which ships
  the pinned/tested OpenROAD binary + yosys): `electrothermal_chip.py`, `chip_vtu.py` (full V–T–u
  chain), `case_thermal.py`, and the Phase-7 PDN reinforcement. The adapter follows OpenDB's
  [database interface](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html), and
  PDN networks can use
  [`write_pg_spice`](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html).
  See `eda_multiphysics/RESULTS.md`.
- **3D FE on generated device-relevant geometry, meshed by gmsh** (`mesh3d.py` + `tsv_3d.py`; need `gmsh`+`meshio`
  and the gfortran toolchain): the compiled **Hex8** coupled element on canonical geometries — a
  **cylindrical TSV** (heat-generation oracle), an **annular Cu/Si via** and a **layer/package
  stack** (multi-material, one `ElementGroup` per material; composite-cylinder and 1D
  series-resistance oracles). All-hex meshes from gmsh's subdivision algorithm — no hand-rolled
  mesher.
- **Generated-geometry linear-tet path** (`tet_element.py` + `tet_3d.py`): this Tet4 foundation
  is intended for future imported CAD, while the repository currently qualifies generated
  box/cylinder solids; the all-hex
  subdivision is limited to qualified shapes, and a named STEP/BREP import adapter remains. A
  **Tet4** coupled element comes from CoupFE core (CoupFE-EDA carries no consumer fallback).
  The public Core pin supplies native `tet4`/`tet4r`, and the current 19-case toolchain tier
  passes the Tet4 patch/self-heating and conformal-package gates. This qualifies the generated
  shapes at the tested resolutions; a named STEP/BREP import adapter remains future work. See
  `docs/TET_FEASIBILITY.md`.
- **Thermo-mechanical stress on generated device-relevant geometry** (`thermomech_kernel.py`, `.thermomech_3d`,
  `.thermomech_tsv`): a monolithic 3D **u+T** Hex8 element (complex-step coupling tangent) →
  the **Cu/Si TSV thermal-mismatch stress**, validated vs the plane-strain composite-cylinder
  closed form. A PCFIELDSPLIT u/T implementation with GAMG and a displacement rigid-body
  near-null-space exists; its old timing and iteration table lacks retained raw/environment
  evidence and is not a release performance claim.
- **End-to-end 3D-FE solder fatigue** (`reliability_3d.py`) plus the **3D Hex8 Anand** element
  (`anand_3d.py`): `anand_3d` stores the Anand state at Hex8 Gauss points and validates saturation,
  full transient hardening (0.01% vs `integrate_uniaxial`), patch, and — as a **solved boundary-value
  problem** on a regular cuboid reference mesh (`solder_joint_bvp_3d`, traction-free lateral
  faces) — the **nonuniform corner-dW
  gradient** where the crack initiates (`critical_joint_bvp_life` wires it into the design chain).
  The Auburn 19 mm PBGA's **measured 4719-cycle** result is used as an
  **in-sample calibration anchor**: the Darveaux/Motalab SAC305 model reproduces
  it within the stated ±2× range, which is not independent validation.
  **Geometry-driven**: `… reliability_3d design` prefers a versioned `joints.csv` map with stable
  IDs, units, coordinate transform, and source provenance → each point's DNP → a per-joint fatigue
  map. The bundled nine-point map is explicitly labeled as a project-authored **synthetic proxy**,
  not a package bump export; missing maps use the labeled coordinate-decoding fallback.
  The local elastic/global-local bridge now supports explicit **cylinder, barrel, and hourglass**
  Gmsh profiles plus a conformal **solder/underfill/UBM/pad Tet4 package model**; the bare cylinder
  remains the frozen oracle. See [`docs/GEOMETRY.md`](docs/GEOMETRY.md).
- **TSV-to-device screening preview** (`tsv_device.py`, `examples/tsv_00_device_screening/`):
  cubic (001)-Si rotation, the exact Raman stress-sum observable, published n/p piezoresistive
  mobility mapping, stable source-object/device/TSV IDs, and a deterministic channel-orientation
  action for a physically scaled 10 µm TSV case. CSV/JSON evidence and an SVG physical map are emitted.
  A separate conformal blind Cu/oxide/anisotropic-Si Tet4 foundation now solves and samples the
  exact Raman depth, but the preview retains its Lamé far-field proxy until mesh/domain convergence
  passes. Experimental curvature/Raman validation and conservative transfer remain release-blocking.
- **Distributed PETSc/MPI** (need `petsc4py`+`mpi4py` — `conda install -c conda-forge
  petsc4py mpi4py`, which bundles superlu_dist): distributed PDN and coupled-solve drivers are
  available. Historical 1M/5M-size and larger-rank timing tables are retained in
  `eda_multiphysics/DISTRIBUTED.md`, but every performance claim is withheld until raw run
  artifacts and environment records are retained on the final revisions.

## Layout

```
environment.yml            conda env (scientific + open-EDA + MPI stack)
Dockerfile / build.sh      repeatable container recipe (pinned OpenROAD/core; rolling conda solve)
CONTAINER.md               full container guide (build/run/design/troubleshooting)
EXAMPLES.md                catalog of every runnable demo (grouped, with run commands)
setup.sh                   clone CoupFE + install both (editable)
pyproject.toml             package + optional extras ([distributed], [codegen], [dev])
skills/SKILL.md            how to add a validated example/gate (read before extending)
docs/                      documentation — see docs/README.md for the index
  README.md                the doc index (reference / assessment / plans)
  RELEASE_EVIDENCE.md      immutable private checkpoints, logs, and artifact checksums
  theory.md · api.md · capabilities.md · lessons_learned.md   (reference)
  VALIDATION_GUIDE.md · VALIDATION_ASSESSMENT.md · TET_FEASIBILITY.md   (validation)
examples/REFERENCES.md     provenance and release status for every runnable entry point
eda_multiphysics/          the package
  run.py                   one-command trust-gate runner
  gates.py                 the 53 gates (+ broken controls)
  fe.py                    scalar-diffusion + helpers (thermal/electrical/electrostatic)
  electrothermal*.py       coupled R(T)<->Joule<->thermal (+ caller-supplied cases)
  tsv_stress / thermomech  thermoelasticity (TSV, bimetal, cylinder, 2D axisym)
  anand / anand_3d / solder_joint / creep
                           viscoplasticity + Darveaux/Syed fatigue
  electromigration / capacitance / thermal_runaway / transient
  pdn_graph / pdn_distributed    PDN electrical (serial + PETSc/MPI)
  case_thermal.py                placement/power case -> thermal map + back-annotation
  reliability_pipeline.py        CAPSTONE: synthetic integration scorecard; caller cases supported
  etv_solder.py / etv_fe.py      electro-thermo-viscoplastic study (material-point + monolithic FE element)
  etv_kernel / etv_distributed   compiled (codegen f2py) coupled element + distributed PETSc/MPI solve
  etv_fieldsplit.py              FieldSplit (GAMG/field); performance record historical
  etv_3d.py                      3D Hex8 coupled element (codegen) -- synthetic grid, validated
  etv_distributed_fs.py          distributed FieldSplit correctness path; historical scaling record
  mesh3d.py                      gmsh glue: via/stack/profiled bump + six-region Tet4 package
  tet_element.py                 fail-closed lookup of core's native Tet4 configuration
  tsv_3d.py                      3D Hex8 coupled element on gmsh device shapes (via/annulus/stack)
  tet_3d.py                      Tet4 foundation on generated gmsh box/cylinder meshes
  thermomech_kernel / _3d        monolithic 3D thermo-mechanical (u+T) Hex8 element + oracles
  thermomech_tsv.py              Cu/Si TSV thermal-mismatch stress + FieldSplit/RBM research path
  reliability_3d.py              end-to-end: gmsh solder joint -> 3D FE shear -> Anand -> Syed life
  cases/synthetic_pdn/           project-authored deterministic integration fixture
  openroad/export_case.tcl       OpenDB -> case exporter
  RESULTS.md / DISTRIBUTED.md     detailed writeups
  tests/                   pytest wrapper over the gates
```

## Status

Experimental alpha. The 53 gates are the trust layer; the design-oriented and distributed demos are
documented in `eda_multiphysics/RESULTS.md` and `eda_multiphysics/DISTRIBUTED.md`. Experimental
curvature/Raman validation, conservative global-local transfer, and a real OpenDB round trip are
still release-blocking for the stronger TSV claims.

The project could help inform a reusable field interface if it matures, but it is
currently only an example. The primary next milestone is **real-device
validation**: a lawfully shareable device/layout and package geometry, traceable
materials and loads, documented boundary conditions, retained raw solver evidence,
and comparison with measured electrical/thermal/stress observables. A larger
simulation alone will not satisfy that milestone.

## Acknowledgments and attribution

CoupFE-EDA builds on the work of the
[OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD) community, including
[OpenDB](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html) and
[PDNSim](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html), and on the
solver contract provided by [CoupFE](https://github.com/tengzhang48/CoupFE).
The external [ORFS GCD sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd)
helped motivate the small-case workflow; its upstream README credits PyMTL and OpenCelerity.
No GCD input decks, generated design files, or raw tool outputs are bundled here. Dated
development documents retain explicitly labeled numerical summaries as historical context,
not reproducible release evidence.

The analytic, constitutive, and reliability models are credited to their original
authors at the point of use and in the
[validation guide](docs/VALIDATION_GUIDE.md) and
[entry-point reference map](examples/REFERENCES.md). Third-party names identify
their contributions and do not imply endorsement.

## License and third-party notices

Code, tests, schemas, and configuration are Apache-2.0 licensed under [LICENSE](LICENSE).
Project-authored prose and figures are CC-BY-4.0 under [the documentation license](docs/LICENSE.md).
The bundled synthetic fixture's generator, assumptions, hashes, and first-party provenance are
stored beside it. OpenROAD's container notice and the boundary for caller-supplied designs are
documented in [NOTICE](NOTICE), [THIRD_PARTY.md](THIRD_PARTY.md), and [LICENSES/](LICENSES/).
