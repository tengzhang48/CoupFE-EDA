# Examples

This catalog groups the runnable modules and composed examples by purpose. Run
commands from the repository root after creating `environment.yml` and running
`./setup.sh`. Input provenance and per-entry references are listed in
[`examples/REFERENCES.md`](examples/REFERENCES.md).

Status labels:

- **CHECKED** — exercised by a checked-in reference or invariant at the stated
  model and resolution.
- **DEMONSTRATION** — runnable integration without a direct oracle for the
  composed result.
- **RESEARCH** — available harness awaiting retained evidence on the release
  revision.
- **WITHHELD** — removed from the public example/API surface, or not presented
  as supported, until its blocker is resolved.

Dependency tiers: 🟢 numpy/scipy/CoupFE · 🟠 compiled, mesh, or PETSc/MPI
toolchain · 🔴 caller-installed OpenROAD/OpenDB/PDNSim tooling.

## Qualification commands

| Command | Scope | Status | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.run` | Component/reference gate harness | **CHECKED** | 🟢 |
| `python -m pytest -q` | Default regression tier | **CHECKED** | 🟢 |
| `python -m pytest -q -m toolchain` | Compiled, mesh, and PETSc/MPI tier | **CHECKED** after a clean release-revision run | 🟠 |
| `python -m eda_multiphysics.validate` | Electrothermal comparison ladder | **CHECKED** | 🟢 |

Test totals are recorded by each release qualification rather than fixed in
this catalog.

The toolchain pytest tier does not invoke OpenROAD/OpenDB or PDNSim. Entries
marked 🔴 require caller-installed EDA tools and caller-qualified data.

## Design and data handoffs

| Command | Scope | Status | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.reliability_pipeline` | Synthetic PDN IR → temperature → TSV stress → solder/EM screening, with a closed-form fixture voltage field and component-level references | **DEMONSTRATION** | 🟢 |
| `python examples/tsv_00_device_screening/run.py` | Synthetic device IDs → Lamé far-field stress proxy → cited mobility proxy → identity-preserving CSV/JSON/SVG output | **DEMONSTRATION** | 🟢 |
| `python -m eda_multiphysics.case_thermal [-o output.csv]` | Synthetic or caller-supplied placement/power case → thermal map and provenance-tagged back-annotation | **DEMONSTRATION** | 🟢 |
| `python -m eda_multiphysics.design_loop_demo` | Synthetic weak-strap case and a same-current before/after comparison | **DEMONSTRATION** | 🟢 |
| `python -m eda_multiphysics.electrothermal_chip` | Coupled R(T) analysis on a caller-supplied, lawfully sourced case | **DEMONSTRATION** | 🔴 |
| `python -m eda_multiphysics.chip_vtu` | Caller-supplied PDN/case data with a V–T–u handoff and Lamé link check | **DEMONSTRATION** | 🔴 |
| `python -m eda_multiphysics.reliability_3d [design] [--shape cylinder\|barrel\|hourglass] [--package]` | Global parametric joint/package geometry, caller-supplied joint locations/provenance, and a calibration-specific global-local workflow; caller joint dimensions do not set the FE mesh | **DEMONSTRATION** | 🟠 |

The bundled case and device sites are project-authored synthetic data. The
file-based case interface accepts caller-owned OpenROAD/OpenDB placement and
PDNSim `write_pg_spice` exports; see [THIRD_PARTY.md](THIRD_PARTY.md).

## Generated 3D geometry and finite elements

| Command | Scope | Status | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.tsv_3d` | Hex8 electrothermal cylinder, annulus, and layer-stack cases with idealized references | **CHECKED** at tested generated meshes | 🟠 |
| `python -m eda_multiphysics.tet_3d` | Native Core Tet4 on generated box and cylinder, including patch/self-heating checks | **CHECKED** at tested generated meshes with Core `454f73c`; imported CAD and broader convergence remain open | 🟠 |
| `python -m eda_multiphysics.thermomech_3d` | Monolithic u+T Hex8 free-expansion and constrained-block checks | **CHECKED** at tested generated meshes | 🟠 |
| `python -m eda_multiphysics.thermomech_tsv` | Generated Cu/Si TSV mismatch case and composite-cylinder comparison | **CHECKED** at tested generated meshes | 🟠 |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 electrothermal self-heating case | **CHECKED** at tested generated mesh | 🟠 |

The Tet4 statement is limited to generated geometries and the checked conformal
package case. A STEP/BREP import adapter and mesh/domain-convergence evidence are
research work.

## Solder and electro-thermo-viscoplastic examples

| Command or path | Scope | Status | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.anand` | Material-point Anand saturation and cited parameter comparisons | **CHECKED** for the named constitutive checks | 🟢 |
| `python -m eda_multiphysics.anand_3d` | 3D return map, transient material update, affine patch, and fully prescribed `prescribed_hex8_cycle` smoke check | **CHECKED** for those checks | 🟢 |
| `python -m eda_multiphysics.solder_joint` | Plane-strain return-map and elastic affine-patch checks | **CHECKED** for those checks | 🟢 |
| `python -m eda_multiphysics.etv_solder` | Simplified material-point electro-thermal-viscoplastic study | **CHECKED** at the documented material-point scope | 🟢 |
| `python -m eda_multiphysics.etv_fe` | Steady electrothermal Quad4 Stage A, compared with the analytic self-heating limit and staggered solve | **CHECKED** at the documented steady scope | 🟠 |
| Stateful multi-element `solder_joint_cycle` | Nonlinear plane-strain thermal cycle | **WITHHELD** — removed because nonlinear increment convergence was not established | — |
| ETV FE Stage B | Transient thermo-viscoplastic mesh cycle | **WITHHELD** — removed because nonlinear increment convergence was not established | — |
| Multi-element 3D Anand BVP / `critical_joint_bvp_life` | Stateful BVP and design-chain life transfer | **WITHHELD** — removed because nonlinear increment convergence was not established; `prescribed_hex8_cycle` remains as a fully prescribed check | — |

The 4719-cycle PBGA datum is used as an in-sample calibration anchor. It is not
an independent lifetime validation.

## Distributed and scaling harnesses

| Command | Scope | Status | Tier |
|---|---|---|---|
| `mpirun -n 2 python -m eda_multiphysics.etv_distributed_fs 24 --validate` | Serial-versus-rank FieldSplit correctness at the retained test size | **CHECKED** for tested-output agreement at size 24 and 2/4 ranks; no performance claim | 🟠 |
| `mpirun -n 2 python -m eda_multiphysics.pdn_distributed 400 --direct` | Distributed synthetic PDN solve | **RESEARCH** pending retained current-revision rank output | 🟠 |
| `python -m eda_multiphysics.etv_fieldsplit` | Serial FieldSplit driver | **RESEARCH** pending retained current-revision solve record | 🟠 |
| `mpirun -n 2 python -m eda_multiphysics.etv_distributed` | ASM distributed coupled driver | **RESEARCH** pending retained current-revision rank output | 🟠 |
| `python -m eda_multiphysics.scaling_bench --n 1580 --ranks 2,4,8` | Machine-specific scaling measurements | **RESEARCH**; historical timing and large-size claims are excluded | 🟠 |

## Individual component checks

The following modules compare selected outputs with named equations or
independent implementations:

- `capacitance` — parallel-plate `C = εA/d`;
- `transient` — fundamental heat-equation mode;
- `thermal_runaway` — compact-model saddle-node condition;
- `thermomech` — bimetal and cylinder closed forms;
- `tsv_stress` — Lamé benchmark;
- `pdn_graph` — independent SciPy assembly/solve;
- `creep` — zero-stress, saturation, and relaxation identities; and
- `electromigration` — Black and Blech screening equations.

Run one with `python -m eda_multiphysics.<name>`. These are **CHECKED** at their
documented idealized scope; they do not qualify a real device.

## Code-generation examples

`etv_kernel` and `thermomech_kernel` generate and compile element kernels from
CoupFE weak forms. `etv_fe` uses the operator contract for the retained steady
electrothermal stage. These are **CHECKED** on the qualified compiled toolchain at
the checked cases. See [`skills/SKILL.md`](skills/SKILL.md) for the contributor
workflow.

The numerical reference, provenance, and public-claim boundary for every entry
point are maintained in [examples/REFERENCES.md](examples/REFERENCES.md).
