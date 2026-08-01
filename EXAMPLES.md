# Examples

This catalog first lists guided, result-bearing workflows and then the package's
module entry points. Run commands from the repository root after creating
`environment.yml` and running `./setup.sh`. Input provenance and per-entry
references are listed in [`examples/REFERENCES.md`](examples/REFERENCES.md).

Each row states its evidence and limits directly. It does not assign one
blanket maturity label to a workflow that may combine checked components,
synthetic inputs, and a composed result without a real-device reference.

Dependency tiers: 🟢 numpy/scipy/CoupFE · 🟠 compiled, mesh, or PETSc/MPI
toolchain · 🔴 caller-installed OpenROAD/OpenDB/PDNSim tooling.

## Verification commands

| Command | What it exercises | Tier |
|---|---|---|
| `python -m eda_multiphysics.run` | Component/reference gates, including fail-closed stateful demonstration cases | 🟢 |
| `python -m pytest -q` | Default regression tier | 🟢 |
| `python -m pytest -q -m toolchain` | Compiled, generated-mesh, and PETSc/MPI tier | 🟠 |
| `python -m eda_multiphysics.validate` | Electrothermal comparison ladder | 🟢 |

Test totals belong to a dated verification record rather than this catalog.
The toolchain pytest tier does not invoke OpenROAD/OpenDB or PDNSim.

## Guided workflows and retained example results

Each directory below contains a README, a runnable `run.py`, and a small JSON
oracle. The runner prints a reviewable result; `--check` compares selected
fields with the retained value. These are numerical examples, not timing
benchmarks or experimental oracles.

| Workflow | Current retained result | Boundary | Tier |
|---|---|---|---|
| [`python examples/solder_plane_cycle/run.py --check`](examples/solder_plane_cycle/) | Six-Quad4 SnPbAg cycle; top-layer cycle energy and solver residual telemetry | Idealized plane-strain block; no stabilized-cycle or package-life validation | 🟢 |
| [`python examples/etv_partitioned_cycle/run.py --check`](examples/etv_partitioned_cycle/) | SAC305 quasisteady versus lumped-transient temperature sensitivity at slow and fast periods | Partitioned uniform-temperature feedback; not a monolithic `phi-T-u` or device result | 🟢 |
| [`python examples/solder_3d_cycle/run.py --check`](examples/solder_3d_cycle/) | Stateful 18-Hex8 SAC305 dissipation field, peak/mean, and residual telemetry | Idealized regular block; no crack-location, mesh/load-step-convergence, or predictive-life result | 🟢 |
| [`python examples/design_linked_solder_screening/run.py --check`](examples/design_linked_solder_screening/) | Maximum-DNP synthetic joint identity carried into the stateful block and a calibration-specific screen | Only object identity and `L_D` cross the handoff; block geometry and solder height remain study inputs | 🟢 |
| [`python examples/tsv_00_device_screening/run.py`](examples/tsv_00_device_screening/) | Synthetic device IDs mapped through a Lamé far-field stress proxy to cited mobility proxies and CSV/JSON/SVG output | Identity-preserving synthetic study; not transistor-delay, measured-stress, or signoff-KOZ evidence | 🟢 |

## Design and data handoffs

| Command | What it demonstrates or checks | Boundary | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.reliability_pipeline` | Synthetic PDN IR → temperature → TSV stress → solder/EM path; closed-form fixture voltage, exact power closure, provenance, and handoffs are regression-checked | Bundled input is project-authored; downstream composed values have no fabricated-device oracle | 🟢 |
| `python -m eda_multiphysics.case_thermal [-o output.csv]` | Synthetic or caller-supplied placement/power → thermal map with provenance-tagged back-annotation | Caller data and case assumptions require their own qualification | 🟢 |
| `python -m eda_multiphysics.design_loop_demo` | Synthetic weak-strap case with a same-current before/after invariant | No bundled OpenROAD round trip | 🟢 |
| `python -m eda_multiphysics.electrothermal_chip <case_dir> <pdn.sp> <P_total_W>` | Coupled R(T) analysis on caller-supplied files; OpenROAD/PDNSim is not invoked at run time | Requires lawful caller input and case-specific checks | 🟢 |
| `python -m eda_multiphysics.chip_vtu <case_dir> <pdn.sp> <P_total_W>` | Caller PDN/case files with a V–T–u handoff and Lamé link check; OpenROAD/PDNSim is not invoked at run time | No direct composed V–T–u device oracle | 🟢 |
| `python -m eda_multiphysics.reliability_3d design [--shape ...] [--package]` | Generated joint/package geometry, caller joint identities/provenance, and calibration-specific global-local screening | Caller joint dimensions do not currently define the FE mesh; no predictive-life claim | 🟠 |
| `python -m eda_multiphysics.reliability_3d stateful` | Maximum-DNP design object → fail-closed stateful 18-Hex8 block → calibration-specific screening value | `L_D` is design-derived; solder height is a caller/default study input; no crack-location, mesh-converged-field, or package-life claim | 🟢 |

The bundled case and device sites are project-authored synthetic data. The
file-based boundary accepts caller-owned OpenROAD/OpenDB placement and PDNSim
`write_pg_spice` exports; see [THIRD_PARTY.md](THIRD_PARTY.md).

## Generated 3D geometry and finite elements

| Command | Evidence and boundary | Tier |
|---|---|---|
| `python -m eda_multiphysics.tsv_3d` | Hex8 cylinder, annulus, and layer-stack cases compared with named idealized references at tested generated meshes | 🟠 |
| `python -m eda_multiphysics.tet_3d` | Native Core Tet4 patch/self-heating checks on generated boxes and cylinders; imported CAD and broader convergence remain open | 🟠 |
| `python -m eda_multiphysics.thermomech_3d` | Monolithic u+T Hex8 free-expansion and constrained-block checks at tested meshes | 🟠 |
| `python -m eda_multiphysics.thermomech_tsv` | Generated Cu/Si mismatch case and composite-cylinder comparison | 🟠 |
| `python -m eda_multiphysics.etv_3d` | Generated Hex8 electrothermal self-heating case at the tested mesh | 🟠 |

The conformal package tests also exercise six generated material regions,
interfaces, positive volumes, prescribed boundaries, and a multimaterial
elastic solve. A STEP/BREP import adapter and broad mesh/domain convergence are
future work.

## Solder and electro-thermo-viscoplastic examples

The guided runners above present the stateful results. The module commands
below additionally execute their component checks and developer-facing output.

| Command | Evidence included | Boundary | Tier |
|---|---|---|---|
| `python -m eda_multiphysics.anand` | Material-point saturation and cited-parameter comparisons | Constitutive checks only; parameter sets are calibration-dependent | 🟢 |
| `python -m eda_multiphysics.solder_joint` | Plane-strain SnPbAg return-map and affine-patch checks plus a fail-closed six-Quad4 stateful cycle | Idealized thermal-cycle mechanics; top-layer-average cycle energy is an example result, not package-life validation | 🟢 |
| `python -m eda_multiphysics.anand_3d` | 3D return-map/transient/patch checks, a fully prescribed Hex8 cycle, and a fail-closed 18-Hex8 field example | Field example is not a crack-location oracle or mesh/load-step-convergence study | 🟢 |
| `python -m eda_multiphysics.etv_solder` | Simplified material-point electro-thermal-viscoplastic study and limiting comparisons | Material/reduced-model scope | 🟢 |
| `python -m eda_multiphysics.etv_fe` | Steady monolithic phi/T checks plus a partitioned lumped-temperature/spatial-mechanics cycle comparison | Top-layer inelastic work is converted to uniform heat with a unit Taylor–Quinney fraction; the cycle is not a monolithic phi-T-u element or device validation | 🟢 |

For all three stateful spatial examples, a numerical constitutive tangent is
used and each mechanical increment must satisfy Core's existing residual rule
before one—and only one—material-state commit. A failed increment raises and
does not emit an energy or life result.

The 4719-cycle PBGA datum is an in-sample calibration anchor. It is not an
independent lifetime validation.

## Distributed solver entry points

| Command | Evidence and boundary | Tier |
|---|---|---|
| `mpirun -n 2 python -m eda_multiphysics.etv_distributed_fs 24 --validate` | Retained serial-versus-rank output agreement at size 24 and two/four ranks; no performance claim | 🟠 |
| `mpirun -n 2 python -m eda_multiphysics.pdn_distributed 400 --direct` | Available distributed synthetic-PDN driver; publish a result only with current-revision rank output | 🟠 |
| `python -m eda_multiphysics.etv_fieldsplit` | Available serial FieldSplit driver; needs a retained current-revision solve record | 🟠 |
| `mpirun -n 2 python -m eda_multiphysics.etv_distributed` | Available ASM distributed driver; needs retained rank output | 🟠 |
| `python -m eda_multiphysics.scaling_bench --n 512 --ranks 1,2,4,8 --repeats 3 --bind-cores --output-dir <new-directory>` | Writes a retained strong-scaling bundle with complete sanitized rank streams, rank binding, and environment/provenance data | 🟠 |

Scaling is a benchmark, not an example or correctness test. See
[`benchmarks/solver_scaling/`](benchmarks/solver_scaling/) for the study
definition, current retained measurements, and separately labeled historical
records.

## Individual component checks

`capacitance`, `transient`, `thermal_runaway`, `thermomech`, `tsv_stress`,
`pdn_graph`, `creep`, and `electromigration` compare selected outputs with named
equations or independent implementations. Run one with
`python -m eda_multiphysics.<name>`. These checks apply to their documented
idealized models and do not qualify a real device.

## Code-generation examples

`etv_kernel` and `thermomech_kernel` generate and compile element kernels from
CoupFE weak forms. `etv_fe` uses the operator contract for its steady
electrothermal element and repaired stateful mechanics example. See
[`skills/SKILL.md`](skills/SKILL.md) for the contributor workflow.
