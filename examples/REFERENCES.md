# Runnable-example references and evidence boundaries

This ledger covers every public module entry point, the composed TSV-device
example, and the synthetic-fixture generator. It records where the inputs come
from, what reference is checked, and what the result supports.

The final column states the evidence and boundary directly. Component checks,
input provenance, solver convergence, and real-device qualification are
separate questions; one status word cannot represent all four.

Equations, tolerances, and citations are maintained in
[`docs/VALIDATION_GUIDE.md`](../docs/VALIDATION_GUIDE.md). Passing a component
reference does not qualify an idealized model for foundry, package, lifetime, or
performance signoff.

## Entry-point map

| Entry point | Input provenance | Reference or invariant | Evidence and boundary |
|---|---|---|---|
| `python -m eda_multiphysics.run` | Checked-in gate definitions and constants | Aggregates analytic, literature, independent-solver, invariant, broken-control, and fail-closed stateful-example gates | Each component retains its own stated boundary |
| `python -m eda_multiphysics.validate` | Parametric electrothermal cases | Analytic conduction/Joule limits and an independent SciPy BVP | Applies to the documented idealized cases |
| `python -m eda_multiphysics.capacitance` | Parametric parallel-plate geometry | `C = εA/d` | Idealized equation check |
| `python -m eda_multiphysics.transient` | Parametric 1-D slab | Fundamental heat-equation eigenmode, `(π/L)²α` | Idealized equation check |
| `python -m eda_multiphysics.thermal_runaway` | Parametric compact leakage model | Analytic saddle-node/tangency condition; Bhat et al. context | Compact-model check; no device signoff |
| `python -m eda_multiphysics.pdn_graph` | Synthetic graph or caller-supplied PDN SPICE | Independent SciPy assembly/solve | Graph-solver check; caller owns input quality |
| `python -m eda_multiphysics.pdn_distributed` | Synthetic resistor network | Serial comparison code is present | Driver is available; retain current-revision rank output before publishing a result |
| `python -m eda_multiphysics.design_loop_demo` | Synthetic weak-strap grid generated in code | Same-current before/after invariant and electrothermal component checks | Runnable synthetic example; no OpenROAD round trip |
| `python -m eda_multiphysics.case_thermal` | Project-authored synthetic placement/power case or caller-supplied case | Scalar-diffusion checks, deterministic generator, and fixture hashes | Synthetic output is not real-design validation |
| `python eda_multiphysics/cases/synthetic_pdn/generate_case.py` | Project-authored parameters embedded in the generator | Deterministic fixture content and hashes checked by integration regressions | Input generator; it does not reproduce an external design |
| `python -m eda_multiphysics.electrothermal_chip` | Caller-supplied case directory and PDN SPICE | Link-level PDN/SciPy and electrothermal analytic checks | Case-specific assumptions require qualification |
| `python -m eda_multiphysics.chip_vtu` | Caller-supplied case/PDN plus a parametric TSV array | V→T link checks and a Lamé T→u reference | No direct V–T–u device oracle |
| `python -m eda_multiphysics.reliability_pipeline` | Project-authored synthetic case with labeled power and voltage provenance | Full-field closed-form PDN reference and source/load/loss closure; later links use separate component references | Integration-checked synthetic example; downstream composed outputs have no device oracle |
| `python -m eda_multiphysics.reliability_3d` | Global parametric joint/package geometry plus caller joint locations/provenance or a bundled nine-point synthetic proxy; `stateful` mode drives a regular 18-Hex8 block from the maximum-DNP identity | DNP kinematics, package topology/elastic checks, geometry/volume checks, fail-closed Core residual rule, and one commit per accepted stateful increment | Caller dimensions do not set the FE mesh; in `stateful` mode only `L_D` comes from the design map and solder height remains a study input; no crack-location, mesh-convergence, or predictive-life claim |
| `python -m eda_multiphysics.tsv_stress` | Published material constants and parametric axisymmetric TSV | Choi et al. Lamé benchmark, *Materials* 14 (2021) 5226 | Benchmark-model check; no full tensor/device qualification |
| `python -m eda_multiphysics.thermomech` | Parametric bilayer/cylinder cases | Timoshenko bimetal and Timoshenko–Goodier closed forms | Idealized-model checks |
| `python -m eda_multiphysics.thermomech_3d` | Generated Hex8 block | Homogeneous free expansion and constrained-block control | Applies to tested generated meshes |
| `python -m eda_multiphysics.thermomech_tsv` | Generated Cu/Si via | Plane-strain composite-cylinder displacement and direct/FieldSplit agreement | Applies to tested generated meshes |
| `python -m eda_multiphysics.tsv_3d` | Generated cylinder, annulus, and layer-stack meshes | Joule cylinder, composite-cylinder, and series-resistance references | Applies to tested generated meshes |
| `python -m eda_multiphysics.tet_3d` | Generated all-tet box and cylinder meshes | Linear patch and `σV²/8k` self-heating checks | Applies to tested geometry with Core `454f73c`; imported CAD and broader convergence remain open |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 block | `σV²/8k` self-heating reference | Applies to the tested generated mesh |
| `python -m eda_multiphysics.etv_fieldsplit` | Generated coupled system | Direct/serial comparison code and iteration controls are present | Retain a current-revision solve record before publishing a result |
| `python -m eda_multiphysics.etv_distributed` | Generated coupled system | Serial-versus-MPI comparison code is present | Retain current-revision rank output before publishing a result |
| `python -m eda_multiphysics.etv_distributed_fs` | Generated coupled system | Serial-versus-rank output checks at size 24 with two and four ranks | Evidence is limited to tested output agreement; no scaling claim |
| `python -m eda_multiphysics.scaling_bench` | New measurements from the local MPI machine/environment | Machine-readable `SCALEFS` output for requested ranks | Retain raw output and environment data before publishing timings |
| `python -m eda_multiphysics.etv_kernel` | CoupFE weak form and generated local build products | Element residual/tangent and self-heating checks | Applies to the qualified compiled toolchain |
| `python -m eda_multiphysics.thermomech_kernel` | CoupFE weak form and generated local build products | Free-expansion identities and toolchain checks | Applies to the qualified compiled toolchain |
| `python -m eda_multiphysics.etv_fe` | Generated Quad4 mesh and constitutive parameters | Steady phi/T analytic and staggered comparisons; partitioned lumped-temperature/spatial-mechanics cycle with fail-closed increments | The cycle is not a monolithic phi-T-u element or device validation |
| `python -m eda_multiphysics.etv_solder` | Published Dandu context and parametric material-point geometry | Exact Joule limit and Dandu et al., *Microelectronics Reliability* 50 (2010) 547 | Material-point/reduced-model scope; no lifetime qualification |
| `python -m eda_multiphysics.anand` | Checked-in SnPb/SAC305 parameter sets | Closed-form saturation and Motalab et al. ITherm 2012/Auburn 2013 context | Constitutive checks; parameters are calibration-dependent |
| `python -m eda_multiphysics.anand_3d` | Generated Hex8 material/element/block cases | Material-point cross-check, affine patch, transient response, prescribed cycle, and an 18-Hex8 field whose increments meet Core's residual rule | Stateful field is an idealized example, not crack, mesh/load-step-convergence, or life validation |
| `python -m eda_multiphysics.solder_joint` | Checked-in Anand parameters and generated Quad4 mesh | Tensor return-map saturation, affine patch, and a six-Quad4 cold→hot→cold cycle whose increments meet Core's residual rule | Top-layer-average energy output is an idealized example, not package-life validation |
| `python -m eda_multiphysics.creep` | Checked-in Anand parameters and imposed stress histories | Zero-stress, saturation, and stress-relaxation identities | Constitutive checks |
| `python -m eda_multiphysics.electromigration` | Checked-in Cu parameters | Black acceleration relation and Blech published range | Screening-equation checks; no interconnect MTTF signoff |
| `python examples/tsv_00_device_screening/run.py` | Runtime input is 32 synthetic device sites from `device_sites.csv`; geometry, load, material coefficients, and threshold are fixed in code and recorded in JSON files | Ryu et al. piezoresistance equations, a Lamé far-field stress proxy, and deterministic metrics in `expected_metrics.json` | Identity-preserving mapping example; it does not establish Raman, delay, protrusion, or signoff-KOZ results |

## Stateful-example repair record

The earlier drivers used an elastic modified-Newton tangent, accepted the last
iterate without checking convergence, and—on the plane and ETV paths—committed
state twice. Instrumented reruns showed explicit nonconvergence for those old
configurations, so their old energy, life, and corner-location conclusions are
not release results.

The current examples use a numerical material tangent, defer state advancement
until Core's existing residual rule is met, and commit exactly once. Regression
tests require either a converged result or an exception with no state commit.
The public results are new reruns of the repaired code, not relabeled legacy
outputs. Scope remains idealized and demonstration-oriented.

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
