# Runnable-example references and release status

This ledger covers every public module entry point, the composed TSV-device
example, and the synthetic-fixture generator. It records where the inputs come
from, what reference is checked, and what the result supports.

Status labels:

- **CHECKED** — exercised by a checked-in reference or invariant at the stated
  model and resolution.
- **DEMONSTRATION** — runnable integration without a direct oracle for the
  composed result.
- **RESEARCH** — available harness awaiting retained evidence on the release
  revision.
- **WITHHELD** — removed from the public example/API surface, or not presented
  as supported, until its blocker is resolved.

Equations, tolerances, and citations are maintained in
[`docs/VALIDATION_GUIDE.md`](../docs/VALIDATION_GUIDE.md). Passing a component
reference does not qualify an idealized model for foundry, package, lifetime, or
performance signoff.

## Entry-point map

| Entry point | Input provenance | Reference or invariant | Status and boundary |
|---|---|---|---|
| `python -m eda_multiphysics.run` | Checked-in gate definitions and constants | Aggregates the analytic, literature, independent-solver, invariant, and broken-control gates in `gates.py` | **CHECKED** harness; each component retains its stated boundary |
| `python -m eda_multiphysics.validate` | Parametric electrothermal cases | Analytic conduction/Joule limits and an independent SciPy BVP | **CHECKED** at the documented idealized cases |
| `python -m eda_multiphysics.capacitance` | Parametric parallel-plate geometry | `C = εA/d` | **CHECKED** idealized model |
| `python -m eda_multiphysics.transient` | Parametric 1-D slab | Fundamental heat-equation eigenmode, `(π/L)²α` | **CHECKED** idealized model |
| `python -m eda_multiphysics.thermal_runaway` | Parametric compact leakage model | Analytic saddle-node/tangency condition; Bhat et al. context | **CHECKED** compact-model check; no device signoff |
| `python -m eda_multiphysics.pdn_graph` | Synthetic graph or caller-supplied PDN SPICE | Independent SciPy assembly/solve | **CHECKED** graph-solver check; caller owns input quality |
| `python -m eda_multiphysics.pdn_distributed` | Synthetic resistor network | Serial comparison code is present | **RESEARCH** pending retained current-revision rank output |
| `python -m eda_multiphysics.design_loop_demo` | Synthetic weak-strap grid generated in code | Same-current before/after invariant and electrothermal component checks | **DEMONSTRATION**; no OpenROAD round trip |
| `python -m eda_multiphysics.case_thermal` | Project-authored synthetic placement/power case or caller-supplied case | Scalar-diffusion checks, deterministic generator, and fixture hashes | **DEMONSTRATION**; synthetic output is not real-design validation |
| `python eda_multiphysics/cases/synthetic_pdn/generate_case.py` | Project-authored parameters embedded in the generator | Deterministic fixture content and hashes checked by the integration regressions | **DEMONSTRATION** input generator; it does not reproduce an external design |
| `python -m eda_multiphysics.electrothermal_chip` | Caller-supplied case directory and PDN SPICE | Link-level PDN/SciPy and electrothermal analytic checks | **DEMONSTRATION**; case-specific assumptions require qualification |
| `python -m eda_multiphysics.chip_vtu` | Caller-supplied case/PDN plus a parametric TSV array | V→T link checks and a Lamé T→u reference | **DEMONSTRATION**; no direct V–T–u device oracle |
| `python -m eda_multiphysics.reliability_pipeline` | Project-authored synthetic case with labeled power and voltage provenance | Full-field closed-form PDN reference and source/load/loss closure; later links use separate component references | **DEMONSTRATION**; downstream composed outputs have no device oracle |
| `python -m eda_multiphysics.reliability_3d` | Global parametric joint/package geometry plus caller joint locations/provenance or a bundled nine-point synthetic proxy | DNP kinematics, conformal-package topology/elastic checks, geometry/volume checks, and calibration-specific material-point transfer | **DEMONSTRATION**; caller dimensions do not set the FE mesh, and there is no stateful multi-element Anand BVP or predictive-life claim |
| `python -m eda_multiphysics.tsv_stress` | Published material constants and parametric axisymmetric TSV | Choi et al. Lamé benchmark, *Materials* 14 (2021) 5226 | **CHECKED** benchmark model; no full tensor/device qualification |
| `python -m eda_multiphysics.thermomech` | Parametric bilayer/cylinder cases | Timoshenko bimetal and Timoshenko–Goodier closed forms | **CHECKED** idealized models |
| `python -m eda_multiphysics.thermomech_3d` | Generated Hex8 block | Homogeneous free expansion and constrained-block control | **CHECKED** at tested generated meshes |
| `python -m eda_multiphysics.thermomech_tsv` | Generated Cu/Si via | Plane-strain composite-cylinder displacement and direct/FieldSplit agreement | **CHECKED** at tested generated meshes |
| `python -m eda_multiphysics.tsv_3d` | Generated cylinder, annulus, and layer-stack meshes | Joule cylinder, composite-cylinder, and series-resistance references | **CHECKED** at tested generated meshes |
| `python -m eda_multiphysics.tet_3d` | Generated all-tet box and cylinder meshes | Linear patch and `σV²/8k` self-heating checks | **CHECKED** at the tested generated box/cylinder geometry with Core `454f73c`; imported CAD and broader convergence remain open |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 block | `σV²/8k` self-heating reference | **CHECKED** at the tested generated mesh |
| `python -m eda_multiphysics.etv_fieldsplit` | Generated coupled system | Direct/serial comparison code and iteration controls are present | **RESEARCH** pending a retained current-revision solve record |
| `python -m eda_multiphysics.etv_distributed` | Generated coupled system | Serial-versus-MPI comparison code is present | **RESEARCH** pending retained current-revision rank output |
| `python -m eda_multiphysics.etv_distributed_fs` | Generated coupled system | Serial-versus-rank output checks at size 24 with two and four ranks in the toolchain tier | **CHECKED** only for that tested output agreement; no scaling or performance claim |
| `python -m eda_multiphysics.scaling_bench` | New measurements from the local MPI machine/environment | Machine-readable `SCALEFS` output for requested ranks | **RESEARCH**; publish results after retaining raw output and environment data from the release revision |
| `python -m eda_multiphysics.etv_kernel` | CoupFE weak form and generated local build products | Element residual/tangent and self-heating checks | **CHECKED** on the qualified compiled toolchain |
| `python -m eda_multiphysics.thermomech_kernel` | CoupFE weak form and generated local build products | Free-expansion identities and toolchain checks | **CHECKED** on the qualified compiled toolchain |
| `python -m eda_multiphysics.etv_fe` | Generated Quad4 mesh and constitutive parameters | Stage-A steady monolithic/staggered and element-level comparisons | **CHECKED** for steady electrothermal Stage A; transient thermo-viscoplastic Stage B is withheld |
| `python -m eda_multiphysics.etv_solder` | Published Dandu context and parametric material-point geometry | Exact Joule limit and Dandu et al., *Microelectronics Reliability* 50 (2010) 547 | **CHECKED** at the documented material-point scope; lifetime inference remains research work |
| `python -m eda_multiphysics.anand` | Checked-in SnPb/SAC305 parameter sets | Closed-form saturation and Motalab et al. ITherm 2012/Auburn 2013 context | **CHECKED** constitutive checks; parameters are calibration-dependent |
| `python -m eda_multiphysics.anand_3d` | Generated Hex8 material/element cases | Material-point cross-check, affine patch, transient response, and fully prescribed `prescribed_hex8_cycle` smoke check | **CHECKED** for those checks; multi-element 3D BVP is withheld |
| `python -m eda_multiphysics.solder_joint` | Checked-in Anand parameters and generated Quad4 mesh | Tensor return-map saturation and elastic affine-patch checks | **CHECKED** for those checks; stateful multi-element cycle and life result are withheld |
| `python -m eda_multiphysics.creep` | Checked-in Anand parameters and imposed stress histories | Zero-stress, saturation, and stress-relaxation identities | **CHECKED** constitutive checks |
| `python -m eda_multiphysics.electromigration` | Checked-in Cu parameters | Black acceleration relation and Blech published range | **CHECKED** screening-equation checks; no interconnect MTTF signoff |
| `python examples/tsv_00_device_screening/run.py` | Runtime input is 32 synthetic device sites from `device_sites.csv`; geometry, load, material coefficients, and threshold are fixed in code and recorded in JSON files | Ryu et al. piezoresistance equations, a Lamé far-field stress proxy, and deterministic metrics in `expected_metrics.json` | **DEMONSTRATION** of identity-preserving mapping; Raman, delay, protrusion, and signoff-KOZ claims are withheld |

## Withheld paths

The following nonlinear stateful paths were removed from the public API and
example surface because their modified-Newton increments did not establish the
stated convergence tolerance:

| Path | Status | Retained replacement |
|---|---|---|
| Plane-strain multi-element `solder_joint_cycle` | **WITHHELD** | `solder_joint` return-map and elastic patch checks |
| Transient thermo-viscoplastic ETV FE Stage B | **WITHHELD** | steady electrothermal `etv_fe` Stage A and material-point `etv_solder` |
| Multi-element `solder_joint_bvp_3d` and `critical_joint_bvp_life` | **WITHHELD** | `anand_3d` material/element checks and fully prescribed `prescribed_hex8_cycle` smoke check |

Git history retains the earlier research code. Reintroduction requires a
convergence criterion, a regression that fails on nonconvergence, and a new
qualification record.

## Composed TSV example input roles

`device_sites.csv` is the runtime input consumed by `run.py`. The remaining
files are reviewable records:

| File | Role |
|---|---|
| `device_sites.csv` | Synthetic device identifiers, coordinates, carriers, and baseline channel directions |
| `case.json` | Descriptive record of the fixed geometry, load, action set, and threshold implemented in `run.py` |
| `materials.json` | Literature/provenance record for constants implemented in `eda_multiphysics.tsv_device` |
| `expected_metrics.json` | Regression reference consumed by `tests/test_tsv_device.py` |

## Open boundaries

- **External EDA data:** no ORFS GCD deck, PDK, generated database, or raw tool
  output is bundled. Caller-supplied OpenROAD/OpenDB and PDNSim inputs remain
  subject to the caller's permissions and case-specific qualification.
- **Real-device validation:** no bundled example combines a shareable real
  layout/package, traceable materials and boundary conditions, retained raw
  evidence, and measured electrical/thermal/stress comparison.
- **Core and mesh ownership:** Core
  `454f73ce2de284262b214a2b37bd676c6aca3c0a` supplies native Tet4 and the
  generic affine-MPC representation/compiler. CoupFE-EDA owns periodic box
  metadata, mesh matching, and relation construction.
- **Geometry:** generated Tet4 cases are checked at tested resolutions. Imported
  STEP/BREP data and broader mesh/domain convergence are not qualified.
- **Scaling:** historical timing, speedup, efficiency, problem-size, and rank
  records are excluded from release evidence until reproduced with retained raw
  output and an environment record on the release revision.
