# CoupFE-EDA component inventory

As of 30 July 2026, CoupFE-EDA contains **12 logical components**, implemented by **44 top-level
Python modules** (excluding `eda_multiphysics/__init__.py`). A component is a coherent public
capability or workflow boundary; a module is an implementation file. This distinction prevents
helper modules and solver variants from inflating the architecture count.

| # | Logical component | Principal modules | Current boundary |
|---:|---|---|---|
| 1 | Core FE and scalar fields | `fe`, `transient`, `capacitance` | Reusable conduction/diffusion operators and scalar-field oracles. |
| 2 | EDA/PDN semantics and back-annotation | `pdn_graph`, `chip_vtu`, `case_thermal`, `joint_map` | Stable IDs, units, coordinates, source provenance, synthetic or caller-supplied PDNSim/OpenROAD case data; no common hierarchical scene graph yet. |
| 3 | Electrothermal analysis | `electrothermal`, `electrothermal_chip`, `etv_fe` | Staggered and monolithic voltage–temperature coupling with Joule heating. |
| 4 | Thermomechanics and TSV stress | `thermomech`, `thermomech_3d`, `thermomech_kernel`, `thermomech_tsv`, `tsv_stress`, `tsv_3d` | Analytic, axisymmetric, compiled 3-D, and FieldSplit research implementations for Cu/Si TSV mechanics; experimentally anchored near-surface TSV stress remains pending. |
| 5 | Geometry, mesh, and periodic adaptation | `mesh3d`, `tet_element`, `tet_3d`, `periodic` | Gmsh Hex8/Tet4 generated canonical device-relevant and package geometry plus EDA-owned periodic lattice/matching adapters; Core receives only generic affine relations. |
| 6 | Viscoplastic solder mechanics | `anand`, `anand_3d`, `solder_joint`, `etv_solder` | SAC305/SnPb material-point, return-map, FE, and coupled studies; life calibration remains package-specific. |
| 7 | Reliability physics | `electromigration`, `creep`, `thermal_runaway` | Black/Blech EM, creep, and electrothermal runaway oracles. |
| 8 | 3-D package reliability | `reliability_3d` | Profiled joints, conformal package regions, Anand BVP, and fatigue-map workflows. |
| 9 | Capstone and design loop | `reliability_pipeline`, `design_loop_demo` | Identity-preserving IR→temperature→stress→life→EM chain and one bounded redesign example. |
| 10 | Compiled, distributed, and scaling solvers | `_coupled_solve`, `etv_kernel`, `etv_3d`, `etv_distributed`, `etv_distributed_fs`, `etv_fieldsplit`, `pdn_distributed`, `scaling_bench` | f2py kernels, PETSc/MPI, FieldSplit/GAMG, checked-size serial-versus-rank invariance, and a scaling harness; historical performance records are unqualified and distributed 3-D remains open. |
| 11 | TSV local physics, device screening, and release evidence | `tsv_local_3d`, `tsv_device`, `tsv_validation` | Conformal Cu/oxide-cup/anisotropic-Si Tet4 foundation, coordinate/input provenance, matching 40/50 µm periodic cell plus exact serial MPC, Raman-depth extraction, mobility/KOZ mapping, stable IDs, manifests, and fail-closed scorecard; source-equivalent macro BC, convergence, MPI MPC, and experimental validation remain pending. |
| 12 | Validation and execution surface | `gates`, `run`, `validate` | Current 94-test default tier, optional toolchain tier, broken controls, packaging guard, and user-facing validation entry points; the former 101-test inventory is historical. |

## Count rules

- Count a new component only when it introduces a distinct public workflow boundary, documented API,
  validation contract, and ownership of inputs/outputs.
- Do not count mesh variants, solver backends, benchmark cases, schemas, examples, or report assets as
  separate components; they are evidence or implementations of the components above.
- The 12 components are not 12 universally mature products. The honest maturity and claim boundary
  remain in [`capabilities.md`](capabilities.md), including the 12-family gap scorecard.

The package currently also contains four TSV benchmark manifests, three packaged TSV schemas, and
the device-scale-dimension synthetic TSV/device example. These are supporting assets, not additional components.
