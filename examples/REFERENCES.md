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
| `python -m eda_multiphysics.tet_3d` | Generated all-tet box and cylinder meshes | Linear patch and `σV²/8k` self-heating checks | Applies to tested geometry with Core `e2f42ed`; imported CAD and broader convergence remain open |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 block | `σV²/8k` self-heating reference | Applies to the tested generated mesh |
| `python -m eda_multiphysics.etv_fieldsplit` | Generated coupled system | Direct/serial comparison code and iteration controls are present | Retain a current-revision solve record before publishing a result |
| `python -m eda_multiphysics.etv_distributed` | Generated coupled system with explicit native joint/split callback policy | Native residual/RK and normal-static UEL element parity checks; serial-versus-MPI comparison code is present | Retain current-revision rank output before publishing a solver or performance result |
| `python -m eda_multiphysics.etv_distributed_fs` | Generated coupled system | Serial-versus-rank output checks at size 24 with two and four ranks | Evidence is limited to tested output agreement; no scaling claim |
| `python -m eda_multiphysics.scaling_bench` | New measurements from the local MPI machine/environment | Machine-readable `SCALEFS` output for requested ranks | Retain complete sanitized process output and environment data before publishing timings |
| `python -m eda_multiphysics.visual_evidence` | A generated solver-visualization manifest and its exact same-directory artifact inventory | Fail-closed schema, path, byte-size, SHA-256, revision, field-grain, renderer, and non-transient interpretation validation | Validates provenance and integrity only; it does not establish experimental accuracy or expand the case claim boundary |
| `python -m eda_multiphysics.workbench_api` | A source checkout with the pinned CoupFE Core, the reviewed connected-snapshot contract, and a service-owned local run directory; `coupfe-eda-workbench` is the installed console entry point | The browser submits workflow ID `tsv_axisymmetric_field` only; the allowlist maps it to `tsv.axisymmetric-field.v1` and the fixed axisymmetric field runner, then validates strict arrays, nine actual solves, residual acceptance, Lamé/oracle tolerance, source identity, and artifact hashes | Loopback-only, unauthenticated local interface with one approved axisymmetric component-verification workflow; `releaseValidation` remains false, the Pages site cannot execute it, and the result is not 3-D, experimental, transient, or signoff evidence |
| `python -m eda_multiphysics.etv_kernel` | CoupFE weak form and generated local build products | Element residual/tangent and self-heating checks | Applies to the qualified compiled toolchain |
| `python -m eda_multiphysics.thermomech_kernel` | CoupFE weak form and generated local build products | Free-expansion identities and toolchain checks | Applies to the qualified compiled toolchain |
| `python -m eda_multiphysics.etv_fe` | Generated Quad4 mesh and constitutive parameters | Steady phi/T analytic and staggered comparisons; partitioned lumped-temperature/spatial-mechanics cycle with fail-closed increments | The cycle is not a monolithic phi-T-u element or device validation |
| `python -m eda_multiphysics.etv_solder` | Published Dandu context and parametric material-point geometry | Exact Joule limit and Dandu et al., *Microelectronics Reliability* 50 (2010) 547 | Material-point/reduced-model scope; no lifetime qualification |
| `python -m eda_multiphysics.anand` | Checked-in SnPb/SAC305 parameter sets | Closed-form saturation and Motalab et al. ITherm 2012/Auburn 2013 context | Constitutive checks; parameters are calibration-dependent |
| `python -m eda_multiphysics.anand_3d` | Generated Hex8 material/element/block cases | Material-point cross-check, affine patch, transient response, prescribed cycle, and an 18-Hex8 field whose increments meet Core's residual rule | Stateful field is an idealized example, not crack, mesh/load-step-convergence, or life validation |
| `python -m eda_multiphysics.solder_joint` | Checked-in Anand parameters and generated Quad4 mesh | Tensor return-map saturation, affine patch, and a six-Quad4 cold→hot→cold cycle whose increments meet Core's residual rule | Top-layer-average energy output is an idealized example, not package-life validation |
| `python -m eda_multiphysics.creep` | Checked-in Anand parameters and imposed stress histories | Zero-stress, saturation, and stress-relaxation identities | Constitutive checks |
| `python -m eda_multiphysics.electromigration` | Checked-in Cu parameters | Black acceleration relation and Blech published range | Screening-equation checks; no interconnect MTTF signoff |
| `python examples/solder_plane_cycle/run.py` | Project-authored six-Quad4 block, thermal-mismatch history, and checked-in SnPbAg parameters | Retained cycle-energy fields, Core residual acceptance, and one state commit per accepted increment; optional `--check` reads the local JSON oracle | Guided idealized example; not stabilized-cycle, crack, package-life, or experimental validation |
| `python examples/etv_partitioned_cycle/run.py` | Project-authored four-Quad4 block, electrical/thermal assumptions, and checked-in SAC305 parameters | Retained slow/fast quasisteady-versus-lumped-transient results, residual acceptance, and local JSON oracle | Guided partitioned-model sensitivity example; not a monolithic `phi-T-u` or measured-device result |
| `python examples/solder_3d_cycle/run.py` | Project-authored regular 18-Hex8 block, idealized thermal-mismatch history, and checked-in SAC305 parameters | Retained element dissipation field, peak/mean, residual acceptance, and local JSON oracle | Guided field example; not mesh/load-step-convergence, crack-location, predictive-life, or experimental validation |
| `python examples/design_linked_solder_screening/run.py` | Project-authored synthetic joint map plus an idealized regular 18-Hex8 block; `L_D` and stable identity come from the map while solder height is a study input | Retained selected-object provenance, dissipation field, calibration-specific Syed screen, residual acceptance, and local JSON oracle | Guided handoff example; mapped joint geometry is not reproduced and the screen is not predictive package life |
| `python examples/tsv_axisymmetric_field/run.py` | Published Cu/Si material constants and one fixed 30 µm TSV, `-400 K` final load, 300 µm radial domain, and 2,400-node Line2 mesh; the required `--output-dir` selects only the artifact destination, and the load-sweep record contains nine independently prescribed temperatures | Real `AxisymThermoelastic`/`coupfe.newton_solve` fields, finite-array and residual telemetry checks, retained JSON oracle, and the published Lamé radial stress at 20 µm under the declared 3% threshold | Axisymmetric plane-strain thermoelastic component verification; not a finite-depth 3-D TSV, near-surface device field, experimental validation, keep-out-zone signoff, or transient cooling simulation |
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
  `e2f42ed5772850a0a23a2ce434f430c287eae5c8` supplies native Tet4 and the
  generic affine-MPC representation/compiler. CoupFE-EDA owns periodic box
  metadata, mesh matching, and relation construction.
- **Geometry:** generated Tet4 cases are checked at tested resolutions. Imported
  STEP/BREP data and broader mesh/domain convergence are not qualified.
- **Scaling:** [`benchmarks/solver_scaling/`](../benchmarks/solver_scaling/)
  separates historical development tables from reproducible current-revision
  measurements. Each retained result applies only to its recorded problem,
  solver, rank/thread placement, environment, and hardware.
