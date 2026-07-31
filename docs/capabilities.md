# CoupFE-EDA — capability status (honest)

A frank matrix of what works, what it's validated against, and what isn't built — so coverage
isn't implicitly over-claimed (serial validation ≠ distributed/scale coverage; a material-point
result ≠ a 3D FE result). Mirrors CoupFE core's `docs/capabilities.md`. Keep it current.

Legend: ✓ done + validated · ◐ partial / documented-assumption · ✗ not built.

> **Release evidence boundary (2026-07-31):** against public Core `933e497`,
> the current candidate passes the standalone 53-gate harness, the 94-test
> default EDA tier (19 toolchain cases deselected), and the separate 19-test
> gmsh/PETSc/MPI/gfortran tier (94 default cases deselected). These overlapping
> checks qualify only the tested sizes and models. The former 101-test inventory,
> every timing/speedup/efficiency table below, and larger-rank observations remain
> historical records rather than current release claims.

**Positioning:** the project is not trying to be uniformly strong across every multiphysics domain.
Its defensible niche is EDA-aware, validation-first coupling and global-local interconnect/package
reliability: preserve design identity, connect compact and FE models, validate every handoff, and
return actionable design quantities. Electromagnetic breadth, CFD, semiconductor-device simulation,
general package CAD, generic optimization, PDK qualification, and signoff remain outside or beyond
the present strength.

This is the first simple, reproducible CoupFE-based implementation example and
foundation, not a completed framework or a field standard. Independent projects
may use different FEM solvers, coupling architectures, and data models. A
lawfully shareable real-device comparison with traceable inputs and measured
observables is the primary next milestone.

## Gap-closure scorecard — July 2026 update rounds

The July gap assessment names seven principal platform gaps in its executive summary. Its detailed
table and subsections expand to twelve distinct families after separating dynamic workloads,
cross-resolution scalability, usability/reproducibility, and signoff. To avoid inflating progress,
this scorecard uses the twelve-family denominator and distinguishes a selected workflow being
demonstrated from the ecosystem-level gap being closed.

**Answer:** these update rounds materially narrowed **8 of 12 gap families**. The current project
state is **3 demonstrated for selected CoupFE-EDA workflows, 8 partial, and 1 open**. **No broad
ecosystem gap is claimed fully closed.** “Round advance” means the recent bug, geometry, package,
joint-map, validation, API, documentation, or AI-skill work changed executable evidence—not merely
the wording of a claim.

| Consolidated gap family | Current project status | Round advance | Executable evidence and remaining boundary |
|---|---:|---:|---|
| EDA-aware physical data model | ◐ Partial | Yes | Joint schema preserves stable IDs, units, frames, affine transforms, source objects, and provenance; a common hierarchical `PhysicalScene` is absent. |
| Physics-enabled process/package data | ◐ Partial | Yes | Named region material maps and public/calibrated/signoff claim levels exist; no versioned foundry-qualified physics PDK or uncertainty schema. |
| Chip/package geometry construction | ◐ Partial | Yes | Profiled Hex8 joints and conformal six-region Tet4 package are generated and gated; no general mask/STEP/package reconstruction pipeline. |
| Robust multiphysics coupling | ✓ Selected workflows demonstrated | Yes | Staggered and monolithic ET, compiled u–T, active capstone handoffs, and nonlinear tests; no general coupling manager, restart, or error control. |
| Conservative transfer, model reduction, and back-annotation | ◐ Partial | Yes | Instance power/temperature, DNP maps, result identity, and a PDN redesign loop work; no general conservative graph↔grid↔FE projection or ROM framework. |
| Package and chiplet support | ◐ Partial | Yes | Local solder/underfill/UBM/pad package and coordinate-aware joint maps exist; no multi-die/interposer hierarchy or real bump export. |
| Dynamic workloads | ◐ Partial | No | Transient conduction and mission-profile sensitivity exist; time-dependent EDA activity/power traces are not integrated end to end. |
| Verification and benchmarks | ◐ Current paired tiers | Yes | Against public Core `933e497`, the 53-gate harness, 94-test default tier, and separate 19-test toolchain tier pass. These overlapping component, integration, and checked-size tests do not supply an end-to-end real-device oracle. |
| Scalability across incompatible resolutions | ◐ Unqualified historical record | No | Distributed drivers and prior checked-size correctness records exist, but all timing, speedup, efficiency, 1M-node, and larger-rank claims require retained final-revision evidence. Cross-resolution conservative transfer and distributed 3-D remain open. |
| Closed-loop design optimization | ◐ Partial | No | One PDN reinforcement example closes analysis→change→verification; no generic optimizer, adjoint, or bump/cooling optimization. |
| Usability, reproducibility, and stable APIs | ✓ Research workflow demonstrated | Yes | Versioned case metadata, packaged data, CLI checks, API contract, lessons, AI skill, two test tiers, an exact public Core pin, runtime dependency provenance, and source/wheel/sdist guards exist. Locked environments and restartability still need work. |
| Signoff qualification | ✗ Open | No | Claims are explicitly research/calibration scoped; no foundry-qualified materials, process corners, uncertainty propagation, or signoff evidence. |

The seven executive-summary gaps were all touched by these rounds, but only coupling and validation
crossed to “demonstrated for selected workflows.” Geometry, data semantics, material provenance,
transfer/back-annotation, and package representation remain partial platform layers.

## Physics components (claim boundary shown per row)
| Capability | Status | Evidence / boundary |
|---|---|---|
| DC conduction / IR-drop (PDN) | ✓ | Ohm; PDN-graph vs scipy; bundled synthetic grid vs closed-form nodal reference |
| Steady thermal conduction | ✓ | patch / parabolic; (π/L)²α transient; **h-convergence 2nd-order O(h²)** (order 2.00, manufactured solution) |
| Coupled electrothermal R(T) + Joule | ✓ | σV0²/8k self-heating; caller-supplied case integration |
| TSV thermomechanical stress | ✓ | Lamé closed form (0.06%) |
| Linear thermoelasticity (bimetal, cylinder, axisym) | ✓ | Timoshenko, T&G, Lamé |
| Anand viscoplasticity (SnPb + **SAC305**) | ✓ | closed-form saturation 0.02%; published Motalab Fig. 3.10; 3D Hex8 saturation/transient/patch; BVP corner-dW gradient; measured 4719-cycle Motalab case used as an in-sample calibration anchor (±2×), not independent validation |
| Solder-joint J2 return map | ✓ (2D plane-strain) | shear saturation 0.04%; patch 4e-16 |
| Darveaux/Syed life mapping | ◐ Calibration demonstration | calibration- and unit-specific; the measured 4719-cycle Motalab case is reproduced in sample within ±2×, not independently validated |
| Electromigration (Black + Blech) | ✓ | JEDEC accel; Blech product range |
| Capacitance / thermal-runaway / creep | ✓ | ε·A/d; saddle-node tangency; inverse-saturation |

## Multiphysics couplings
| Capability | Status | Notes |
|---|---|---|
| Staggered electrothermal (R(T)↔Joule↔thermal) | ✓ | Picard; caller-supplied case integration |
| Full V–T–u chain | ◐ Demonstration | link-checked on synthetic/caller data, not independently qualified as a composed prediction |
| **Capstone design→reliability** (IR→ΔT→stress→life→EM) | ◐ Demonstration | project-authored synthetic default; stages gated, not real-design validation |
| **3D-FE solder fatigue** (gmsh joint→3D shear→Anand→Syed) | ◐ Demonstration | `reliability_3d`: generated cylinder/barrel/hourglass geometry; cylindrical FE shear vs DNP oracle, profiled solved-sensitivity gate, and mesh-objective dW; life is calibration-specific and the measured 4719-cycle case is an in-sample anchor; `critical_joint_bvp_life` is a stateful regular-block Anand BVP |
| **Joint map→3D-FE fatigue map** | ◐ Demonstration | schema-v1 stable IDs + units + package-to-die transform + source provenance; explicit maps preferred, labeled PDN fallback; bundled nine-row map is a synthetic proxy and the composed life map has no real-package oracle |
| Electro-thermo-viscoplastic (monolithic vs staggered) | ✓ | the τ/period finding (material-point + FE) |
| Monolithic electro-thermal FE element (φ,T; complex-step tangent) | ✓ | self-heating to 4e-15 |
| **Monolithic thermo-mechanical Hex8 (u,T; complex-step tangent)** | ✓ | **3D, compiled**; free-expansion λ exact (2e-13), constrained σ=−KαΔT; neo-Hookean+thermal-pressure |
| **TSV thermal-mismatch stress (gmsh Cu/Si via, 3D)** | ◐ | plane-strain **composite-cylinder** oracle recorded u_r convergence; FieldSplit timing and iteration-count records are historical/unretained and require a final-revision rerun |
| **TSV→device mobility/KOZ screening** | ◐ | conformal blind Cu/oxide-cup/anisotropic-Si Tet4 solve, zero direct Cu/Si contact, coordinate/material/mesh provenance, Gmsh-matched 40/50 µm periodic geometry, exact affine MPC with explicit macro gradient, homogeneous free-expansion/fixed-box controls, local refinement, L2 recovery, Raman spot sensitivity, published piezoresistance, stable IDs, and a device-scale-dimension synthetic preview are tested; a quarantined legacy branch carried a bulk/history-free distributed MPC prototype, but it is not current public evidence, and corrected-scene convergence, a distributed TSV consumer, production memory locality, source-equivalent macro/bottom BCs, and experiment remain blocked |
| Mechanical→thermal/electrical back-coupling | ◐ | inelastic-heat term included; geometric/large-strain not |

## Solve drivers / scale

> **All numeric results and interpretations in this section are historical and unqualified for the
> public release.** No raw output or locked environment was retained for the timing, speedup,
> efficiency, iteration-count, or large-rank records. Only the driver inventory is current; rerun
> correctness and performance on the final public revisions before quoting any number below.

| Capability | Serial | Distributed (MPI) |
|---|---|---|
| Scalar field (electrical / thermal) | ✓ | ◐ drivers exist; historical 1M-node/AES records require a retained rerun |
| **Compiled (f2py codegen) coupled element** | ✓ (batched, no Python loop; σV0²/8k to 2e-16) | ✓ |
| **Distributed NONLINEAR coupled (φ,T) solve** | ✓ | ◐ driver exists; historical 526k/32-rank correctness and scaling record is unqualified |
| Distributed direct (machine-precision 1-vs-N) | — | ◐ `superlu_dist` **conda-only** (pip-PETSc venv is iterative) |

### Historical scaling record (compiled coupled electro-thermal, `etv_distributed`, ASM+GMRES)
All distributed runs in this record (and the earlier 1M-node PDN) are **2D** — large in DOF *count*
on a structured grid, but a 2D sparse stencil is computationally lighter per DOF than 3D. The
codegen machinery supports `Hex8`/`Hex20`; a serial 3D Hex8 path now exists, while distributed 3D
rank scaling remains open.

**Historical strong-scaling record** — fixed 132,098 DOF (nonlinear, α=0.05; 2D Quad4),
wall = solve time (compile excluded):

| ranks | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| wall (s) | 55.2 | 36.2 | 19.3 | 10.5 |
| speedup | 1.0× | 1.52× | 2.86× | **5.26×** |
| KSP iters | 232 | 350 | 341 | 336 |

The historical interpretation attributed near rank-independent iterations and strong scaling to
ASM overlap; it is withheld pending a retained rerun.

**Historical large-sample strong-scaling record** — fixed **526,338 DOF**; the unretained record
reported **serial==N-rank = 5.2e-11**:

| ranks | 8 | 16 | 32 |
|---|---|---|---|
| wall (s) | 88.8 | 47.4 | 27.8 |
| speedup (vs 8) | 1.0× | 1.87× | **3.19×** |
| KSP iters | 1121 | 1363 | 1263 |

The historical record described continued scaling to 32 ranks; that speedup, efficiency, and
iteration interpretation are not release evidence.

**Historical interpretation of problem-size scaling:** the record attributed growth from 336
iterations at 132k DOF to about 1200 at 526k to ASM's lack of a coarse grid. It also reported that
GAMG mis-coarsened the interleaved two-field block. These observations require a retained rerun.

**Historical FieldSplit comparison (`etv_fieldsplit.py`).** The implementation splits the (φ,T)
system into two scalar fields and applies **GAMG** to each. The unretained record reported flat
iterations across a 16× size range:

| DOF | 33k | 132k | 296k | 526k |
|---|---|---|---|---|
| FieldSplit iters | 16 | 17 | 17 | 19 |
| ASM iters (contrast) | — | 340 | — | ~1200 |

The historical record described constant iterations, O(N)-like time, and fewer iterations than
ASM. Those numerical and “scalable-to-1M+” claims are withheld.

**Distributed FieldSplit (`etv_distributed_fs.py`).** The custom driver wires FieldSplit
into a distributed PETSc solve (`solve_distributed` is single-field/ASM only), with **fully
vectorized owned-row-CSR assembly** (no Python per-element loop; *not* PETSc `setValuesCOO`, a
confirmed upstream bug that corrupts global state — reproduced pure-petsc4py on 3.24.2 + 3.25.2).
Correctness is checked at 2 and 4 ranks. A historical table reports a 4,999,122-DOF 4→48-core
sweep, but the raw output and environment record were not retained; its timing, speedup, and
1–48-rank equality headlines are withheld from the public release.

> The historical table and the `scaling_bench` measurement harness live in
> **[`eda_multiphysics/DISTRIBUTED.md`](../eda_multiphysics/DISTRIBUTED.md)** — not duplicated here.

**Historical 3D Hex8 size-scaling record** (`etv_3d.py`, FieldSplit GAMG/GAMG, serial):

| DOF | 9.8k | 31k | 72k | 138k | 235k |
|---|---|---|---|---|---|
| FieldSplit iters | 16 | 17 | 17 | 17 | 17 |
| solve (s) | 0.07 | 0.25 | 0.62 | 1.24 | 2.37 |
| µs/DOF | 7.4 | 7.9 | 8.6 | 9.0 | 10.1 |

The historical record interpreted the iteration sequence as mesh-independent and the timings as
approximately linear. Those claims require a retained rerun. The path is serial, uses a synthetic
unit cube, and distributed 3D rank scaling is not implemented.

**Historical thermo-mechanical FieldSplit record** (`thermomech_tsv.py`, Cu/Si TSV on a generated
gmsh via, serial) — the
4-field (u,T) block needs a careful PC: **PCFIELDSPLIT** splitting displacement from temperature,
**GAMG on the u-block seeded with the displacement rigid-body near-null-space** (the 6 modes via
`MatNullSpace.createRigidBody`), jacobi on the prescribed-T block. The unretained record reported
about 565 iterations without the near-null-space and about 20 with it:

| DOF | 16k | 23k | 49k | 89k | 145k |
|---|---|---|---|---|---|
| KSP iters | 20 | 19 | 17 | 21 | 20 |
| solve (s) | 2.7 | 1.9 | 5.2 | 14.6 | 19.1 |

The historical record described flat iterations and approximately linear time; those claims are
withheld. The composite-cylinder oracle remains the relevant physics target, while this path is
serial and a distributed thermo-mechanical consumer has not been qualified.

| **FieldSplit (GAMG/field)** | ◐ implementation present; historical iteration table unqualified | ◐ custom driver present; current 2/4-rank checked-size correctness passes, while 1–48-rank timing claims are withheld |
| **3D Hex8 coupled element** | ✓ (codegen `Hex8`; σV0²/8k to 1e-16, FieldSplit-solved) | ✗ (serial; distributable via the same path) |
| **3D Tet4 coupled element** (foundation for future imported CAD) | ✓ native Core `tet4`/`tet4r`; current patch and box/cylinder self-heating gates pass on generated meshes | ✗ |
| **3D Hex8 on generated device-relevant geometry (gmsh)** | ✓ (`tsv_3d`/`mesh3d`: cylinder, annulus, stack, barrel/hourglass solder; mesh/physics gates) | ✗ |
| **Parametric solder geometry** | ✓ (`solder_bump`: cylinder/barrel/hourglass, exact cap sets, connected-node + positive-Jacobian gates; wired to global-local fatigue) | ✗ (stateful Anand remains regular-block) |
| **Conformal local package geometry** | ◐ native-Tet4 region and multi-material solve gates pass on the generated model | ✗ (imported production CAD and qualified material/dimension inputs absent) |
| **Multi-material 3D (annular Cu/Si via)** | ✓ (gmsh conformal 2-volume, one `ElementGroup`/material; composite-cylinder oracle, rel ~1e-3) | ✗ |
| **Multi-material 3D (layer/package stack)** | ✓ (gmsh stacked-slab, 1 `ElementGroup`/layer; 1D series-resistance oracle, **nodally exact 4e-16**) | ✗ |
| Transient viscoplastic FE (thermo-mechanical) | ✓ (2D + 3D small mesh, modified Newton) | ✗ |

## OpenROAD / EDA integration
| Capability | Status |
|---|---|
| OpenROAD/PDNSim case export (`write_pg_spice`, OpenDB) | ◐ adapter implemented; real-tool round trip pending |
| Caller-supplied OpenROAD cases | ◐ supported by drivers; the bundled case is synthetic and historical AES evidence is not release-qualified |
| Pinned/tested OpenROAD in a repeatable container recipe | ✓ (`2.0-17598`, 2024-12-14; rolling conda solve) |

The case adapter follows OpenROAD's official
[OpenDB interface](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html);
electrical networks may be supplied through the
[PDNSim `write_pg_spice` interface](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html).
Those citations establish format applicability, not validation of an unbundled external design.
The checked implementation uses CoupFE and shows one workable approach. It is not a
field-wide interface standard: other projects can build independent implementations around
different FEM packages, coupling architectures, and data models.

## Honest limitations (read before claiming scale)
- **Pure-Python assembly** for most multiphysics elements (`fe.py`, `solder_joint.py`, `etv_*.py`
  material-point/FE) caps mesh size; the **compiled codegen path** (`etv_kernel.py`) is intended for
  larger solves and is used by the distributed driver. Don't hand-roll batch assembly for a hot element — see
  `skills/SKILL.md` and CoupFE core `skills/performance.md`.
- **3D viscoplastic mechanics is available as a pure-Python small-mesh reference** (`anand_3d`).
  It uses the elastic modified-Newton tangent and is correctness-first, not the compiled large-scale path.
- **Viscoplastic FE uses the elastic (modified-Newton) tangent**, not complex-step (the Brent return
  map isn't analytic); complex-step is the *smooth* electro-thermal coupling only.
- **Life constants** (Darveaux, Syed) are calibration- and unit-specific. The
  Motalab 4719-cycle case is an in-sample calibration anchor reproduced within
  ±2×, not independent validation; the stronger numerical outputs are the
  mesh-objective ΔW and field solutions.
- The compiled/distributed demos need the **gfortran+meson** toolchain → not in the *fast* gate
  suite, but they are regression-tested by the **toolchain tier** (`pytest -m toolchain`, 19 tests
  asserting documented analytic, comparison, structural, and iteration-bound contracts;
  `tests/test_toolchain.py`) — so they're CI-verifiable, not verified-by-hand.
- **The compiled/distributed *scaling* solves use SYNTHETIC structured grids** (a unit square/cube
  with a self-heating BC), chosen for an *exact* oracle (σV0²/8k) and controlled solver studies. They are
  **solver-capability** demonstrations. The generated device-relevant geometry layer is
  **partially implemented**:
  `tsv_3d`/`mesh3d` run the 3D Hex8 coupled element on a **gmsh-meshed cylindrical via** (canonical
  curved 3D-IC geometry, all-hex via gmsh's subdivision mesher — we do not hand-roll a generator),
  validated against the heat-generation-cylinder closed form (peak `σ₀V²R²/4kL²`, rel ~1e-3 on the
  unstructured mesh, converging with refinement). **Multi-material is validated** too: the
  **annular Cu/Si via** (gmsh conformal two-volume mesh, one `ElementGroup` per material)
  reproduces the **composite-cylinder closed form** (peak `q a²/4k_core + q(b²−a²)/4k_ann`, rel
  ~1e-3), and the **layer/package stack** (die/underfill/solder/substrate, one `ElementGroup` per
  layer) reproduces the **1D series-resistance** oracle `T_top·R(z)/R_tot` to **machine precision**
  (4e-16 — flat aligned 1D conduction is nodally exact for Hex8). And the **loading is now
  geometry-driven**: `reliability_3d.from_design` prefers a versioned joint map → each point's DNP
  → the 3D-FE solder-fatigue map (not an assumed L_D), preserving stable IDs, transforms, and
  provenance. The bundled locations are explicitly labeled as a project-authored synthetic proxy. The local joint now
  supports parametric cylinder/barrel/hourglass profiles and a conformal solder/underfill/UBM/pad
  Tet4 assembly with geometry + solved-sensitivity gates. What remains: a real package export to
  replace the schema-valid proxy, qualified material/dimension inputs, imported package CAD, full TSV
  arrays, and the profiled mesh in the stateful Anand BVP.
  Needs **gmsh + meshio** (pip).

## What's next (roadmap)
- Make real-device validation the primary milestone: shareable geometry/layout and stable
  object IDs, traceable material/load/BC records, retained raw outputs, and comparison against
  measured electrical, thermal, and stress observables. A larger synthetic solve is not a
  substitute.
- ~~FieldSplit PC for the distributed coupled solve~~ — **done** (`etv_distributed_fs.py`).
- Re-run and archive the large distributed sweep with raw output, hardware/topology, tool versions,
  and a locked environment before making a 1M+ performance claim.
- ~~Connect the 3D Hex8 element to generated device-relevant 3D geometry via gmsh~~ — **started** (`tsv_3d`/`mesh3d`:
  gmsh all-hex via; **multi-material done** — annular Cu/Si via + layer/package stack, one
  `ElementGroup` per material, validated; **parametric barrel/hourglass solder done**). Remaining:
  real exported arrays and qualified CAD import.
- Distributed **3D Hex8** coupled solve (wire `etv_3d`'s element into the `etv_distributed_fs`
  partition — same owned-row-CSR machinery, 3D connectivity) for a true 3D rank-scaling story.
- ~~A compiled *thermo-mechanical* codegen element~~ — **done** (`thermomech_kernel`: monolithic
  3D Hex8 u+T, complex-step coupling, free-expansion λ exact).
- ~~Thermo-elastic on a gmsh Cu/Si via → Lamé/composite-cylinder oracle~~ — **done**
  (`thermomech_tsv`: TSV thermal-mismatch stress, u_r to ~1e-3).
- ~~FieldSplit PC for the 4-field elastic+thermal block~~ — **implemented** (FieldSplit u/T + GAMG
  with a displacement rigid-body near-null-space). The historical ~20-iteration
  16k→144k record is unqualified and must be rerun before any scaling claim. Next:
  wire it **distributed** (the electro-thermal 5M path), then the full φ-T-u chain and viscoplastic.
- ~~3D solder joint viscoplastic reference~~ — **done** (`anand_3d`: stateful Hex8 Anand,
  return-map saturation + patch + SAC305/Syed life gates). It currently uses a regular cuboid;
  next consume the profiled external Hex8 mesh, then compile/distribute that path.
- Distributed 3D solder viscoplastic solve with FieldSplit/superlu_dist for machine-precision 1-vs-N.
