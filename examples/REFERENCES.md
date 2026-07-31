# Runnable-example references and release status

This is the provenance map for every runnable module entry point in
`eda_multiphysics/` plus the composed TSV-device example. It separates three
different ideas that were previously easy to conflate:

- **Verified** means the numerical behavior is checked against an analytic,
  literature, independent-solver, or serial-versus-MPI oracle identified below.
- **Demonstration** means the workflow is runnable, but the composed result is
  not an independently validated prediction.
- **Withheld** means code may remain available for research, but the named
  public claim is not made until the stated release blocker is cleared.

The detailed equations, tolerances, and citations are in
[`docs/VALIDATION_GUIDE.md`](../docs/VALIDATION_GUIDE.md). Passing a numerical
oracle does not turn an idealized model into foundry, package, lifetime, or
performance signoff.

## Entry-point map

| Entry point | Input provenance | Reference or oracle | Public-release status |
|---|---|---|---|
| `python -m eda_multiphysics.run` | Checked-in gate definitions and constants | Aggregates the analytic/literature gates in `gates.py`, including broken controls | **Verified harness**; individual claim boundaries still apply |
| `python -m eda_multiphysics.validate` | Parametric electrothermal cases | Analytic conduction/Joule limits and an independent SciPy BVP | **Verified numerical ladder** |
| `python -m eda_multiphysics.capacitance` | Parametric parallel-plate geometry | `C = εA/d` | **Verified idealized model** |
| `python -m eda_multiphysics.transient` | Parametric 1-D slab | First heat-equation eigenmode, `(π/L)²α` | **Verified idealized model** |
| `python -m eda_multiphysics.thermal_runaway` | Parametric compact leakage model | Analytic saddle-node/tangency condition; Bhat et al. context | **Verified compact model**, not device signoff |
| `python -m eda_multiphysics.pdn_graph` | Synthetic graph or caller-supplied PDN SPICE | Independent SciPy assembly/solve | **Verified graph solver**; input quality remains caller-owned |
| `python -m eda_multiphysics.pdn_distributed` | Synthetic resistor network | Serial SciPy reference at checked sizes | **Verified distributed correctness** at tested sizes; scale is not accuracy |
| `python -m eda_multiphysics.design_loop_demo` | Synthetic weak-strap grid generated in code | Same-current before/after invariant and electrothermal gates | **Demonstration**; not an OpenROAD round trip |
| `python -m eda_multiphysics.case_thermal` | Bundled project-authored synthetic placement/power case or caller-supplied case | Scalar diffusion gates, deterministic generator, and fixture hashes | **Integration demonstration**; synthetic results are not real-design validation |
| `python -m eda_multiphysics.electrothermal_chip` | Caller-supplied case directory and PDN SPICE | Link-by-link PDN/SciPy and electrothermal analytic checks | **Demonstration**; thermal/material assumptions require case-specific qualification |
| `python -m eda_multiphysics.chip_vtu` | Caller-supplied case/PDN plus a parametric TSV array | V→T link checks plus Lamé T→u oracle | **Demonstration**, not a single independently validated V–T–u prediction |
| `python -m eda_multiphysics.reliability_pipeline` | Defaults to the bundled synthetic case; power and voltage-reference provenance are labeled | Direct full-field closed-form PDN oracle and source/load/loss closure; structural handoff checks plus separate component-level Joule, Lamé, Anand, fatigue, and Black/Blech evidence | **Integration demonstration**; downstream composed outputs have no direct device oracle and are never signoff |
| `python -m eda_multiphysics.reliability_3d` | Parametric joint, caller joint map, or bundled nine-point synthetic proxy | DNP kinematics, geometry/volume checks, Anand material/BVP checks | **Parametric demonstration**; life remains calibration-specific |
| `python -m eda_multiphysics.tsv_stress` | Published material constants and parametric axisymmetric TSV | Choi et al. Lamé benchmark, *Materials* 14 (2021) 5226 | **Verified benchmark model**; not a full tensor/device validation |
| `python -m eda_multiphysics.thermomech` | Parametric bilayer/cylinder cases | Timoshenko bimetal and Timoshenko–Goodier closed forms | **Verified idealized models** |
| `python -m eda_multiphysics.thermomech_3d` | Generated Hex8 block | Homogeneous free expansion and constrained-block control | **Verified numerical mechanics** |
| `python -m eda_multiphysics.thermomech_tsv` | Generated Cu/Si via | Plane-strain composite-cylinder displacement; direct/FieldSplit agreement | **Verified idealized TSV mechanics** |
| `python -m eda_multiphysics.tsv_3d` | Generated cylinder, annulus, and layer-stack meshes | Joule cylinder, composite-cylinder, and series-resistance oracles | **Verified generated-geometry cases** |
| `python -m eda_multiphysics.tet_3d` | Generated all-tet box/cylinder | Linear patch and `σV²/8k` self-heating oracles | **Withheld in this release pin** until EDA is repinned to a qualified core containing native Tet4 and MPC |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 block | `σV²/8k` self-heating oracle | **Verified generated-geometry case** |
| `python -m eda_multiphysics.etv_fieldsplit` | Generated coupled system | Agreement with the direct/serial path and iteration controls | **Verified at tested sizes** |
| `python -m eda_multiphysics.etv_distributed` | Generated coupled system | Serial-versus-MPI invariant at checked sizes | **Verified distributed correctness** at tested sizes |
| `python -m eda_multiphysics.etv_distributed_fs` | Generated coupled system | Serial-versus-MPI checks at 2 and 4 ranks in the toolchain tier | **Verified checked-size correctness**; historical large-run timing is not a release claim |
| `python -m eda_multiphysics.scaling_bench` | New measurements produced by the local MPI machine/environment | Machine-readable `SCALEFS` output from each requested rank | **Harness available**; historical 5M-DOF timing claim withheld until raw outputs and environment are archived |
| `python -m eda_multiphysics.etv_kernel` | CoupFE weak form and generated local build products | Element residual/tangent and self-heating tests | **Verified code-generation example** on the qualified toolchain |
| `python -m eda_multiphysics.thermomech_kernel` | CoupFE weak form and generated local build products | Free-expansion identities and toolchain tests | **Verified code-generation example** on the qualified toolchain |
| `python -m eda_multiphysics.etv_fe` | Generated Quad4 mesh and constitutive parameters | Monolithic/staggered and element-level gate comparisons | **Verified research element**, not signoff |
| `python -m eda_multiphysics.etv_solder` | Published Dandu benchmark constants plus parametric geometry | Exact Joule limit; Dandu et al., *Microelectronics Reliability* 50 (2010) 547 | **Verified benchmark behavior**; composed lifetime inference remains research-only |
| `python -m eda_multiphysics.anand` | Checked-in SnPb/SAC305 parameter sets | Closed-form saturation; Motalab et al. ITherm 2012/Auburn 2013 | **Verified constitutive benchmark**; parameters are calibration-dependent |
| `python -m eda_multiphysics.anand_3d` | Generated Hex8 material/BVP cases | Material-point cross-check, patch test, transient response, and BVP control | **Verified numerical implementation**; lifetime transfer is not blind validation |
| `python -m eda_multiphysics.solder_joint` | Parametric plane-strain joint and checked-in material calibration | Anand saturation, patch test, volume-averaged energy metric | **Verified links / demonstration life**; absolute life remains calibration-specific |
| `python -m eda_multiphysics.creep` | Checked-in Anand parameters and imposed stress histories | Zero-stress, saturation, and stress-relaxation identities | **Verified constitutive behavior** |
| `python -m eda_multiphysics.electromigration` | Checked-in Cu parameters | Black acceleration relation and Blech published range | **Verified screening equations**, not interconnect MTTF signoff |
| `python examples/tsv_00_device_screening/run.py` | Runtime reads 32 **synthetic** device sites from `device_sites.csv`; geometry, load, material coefficients, and 5% threshold are fixed in code and described by the JSON files | Ryu et al. piezoresistance equations plus the project's Lamé far-field stress oracle; deterministic metrics in `expected_metrics.json` | **Demonstration** of identity-preserving mapping only; Raman, delay, protrusion, and signoff-KOZ claims are withheld |

## Composed TSV example input roles

Only `device_sites.csv` is consumed by `run.py` at runtime. The other files are
reviewable records rather than hidden runtime controls:

| File | Role |
|---|---|
| `device_sites.csv` | Synthetic device identifiers, coordinates, carriers, and baseline channel directions read by the script |
| `case.json` | Descriptive record of the fixed geometry, load, action set, and threshold currently hardcoded in `run.py` |
| `materials.json` | Literature/provenance record for constants implemented in `eda_multiphysics.tsv_device` |
| `expected_metrics.json` | Regression oracle consumed by `tests/test_tsv_device.py`, not by the example script |

## Unresolved release boundaries

- **External EDA data:** the bundled fixture is entirely project-authored. The same
  interface can consume caller-supplied OpenROAD/OpenDB and PDNSim exports, as documented by
  OpenROAD's [OpenDB](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html) and
  [PDNSim](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html) interfaces.
  Input rights and real-design qualification remain the caller's responsibility.
- **Real-device validation:** no bundled example yet combines a shareable real layout/package,
  traceable materials and boundary conditions, retained raw evidence, and measured
  electrical/thermal/stress comparison. Until that exists, this package demonstrates an approach;
  it does not define a field standard. Other projects may build independent implementations
  around different FEM packages, coupling architectures, and data models.
- **Core pin and periodic ownership:** the selected public Core pin supplies
  native Tet4 plus the generic affine-MPC representation/compiler. CoupFE-EDA
  owns periodic box metadata, face/node matching, and relation construction;
  those mesh-aware adapters do not belong in core. The EDA-owned adapter and
  Tet4 entry points pass the current paired default/toolchain qualification.
- **Scaling:** the harness can generate new results, but all historical timing,
  speedup, efficiency, 1M/5M-size, and larger-rank records lack retained raw
  stdout, machine inventory, or a locked environment. They are historical
  context, not release evidence.
