# Current evidence summary

This file maps implemented examples to their public evidence. It is not a test
log. Release status comes from a clean, retained checkpoint described in
`docs/RELEASE_EVIDENCE.md`.

## Core and environment boundary

The candidate targets CoupFE revision
`e2f42ed5772850a0a23a2ce434f430c287eae5c8`. Evidence must record the imported
Core path and revision as well as the EDA revision. Optional Gmsh, compiler,
PETSc, and MPI cases are reported separately from the default tests.

## NumPy/SciPy/CoupFE reference paths

| Path | Evidence used | Interpretation |
|---|---|---|
| Scalar diffusion/conduction | linear patch, manufactured-source refinement, Ohm law, transient eigenmode | checks the structured element and boundary/reaction implementation at stated cases |
| Electrothermal | slab self-heating, monolithic-versus-sequential comparison, zero-voltage/power controls | checks Joule and temperature-conductivity coupling for the selected models |
| TSV/cylinder mechanics | Lamé-family and thermal-gradient references | checks the implemented axisymmetric/structured equations and boundary conditions |
| Thermomechanics | bimetal, pressurized cylinder, free/constrained controls | checks the selected constitutive limits and reference geometries |
| Anand material models | saturation relation, selected SAC305 literature values, 3D-to-1D transient, patch and no-swing controls | checks material-point/return-map behavior; literature values are reproduction, not independent experiment |
| PDN graph | independent SciPy assembly/solve and synthetic closed-form voltage | checks the supported resistor-network path |
| Reliability equations | Black, Blech, Syed/Darveaux functions and an in-sample PBGA tie point | checks equations and one calibration reproduction; no device/package life qualification |
| ETV material/reduced model | self-heating, fixed-mesh crowding context, staggered/coupled limit | checks the reduced-model implementation and limiting behavior |
| ETV FE | monolithic Quad4 self-heating and sequential comparison; partitioned lumped-temperature/spatial-SAC305 cycle | checks the spatial `phi`/`T` element and a fail-closed partitioned mechanics example; it is not a monolithic `phi-T-u` validation |

## Repaired stateful demonstration results

These are current reruns, not the earlier modified-Newton outputs. The drivers
use a central-difference material tangent. Each increment is solved without
advancing material state, checked against Core's existing rule
`||R_free|| < 1e-9 ||R0_free||` or `||R_free|| < 1e-14`, and committed exactly
once only after acceptance.

| Example configuration | Current result | Solver record | Interpretation |
|---|---|---|---|
| Plane-strain SnPbAg, 3×2 Quad4, one −40→125→−40 °C cycle over 1600 s, 12 increments | top-layer Gauss/element-mean `dW = 0.331884 MPa` (`MPa = MJ/m³`) | maximum 7 Newton iterations; maximum final-residual/acceptance-limit fraction `0.683` | Idealized stateful block example; not a stabilized-cycle or package-life validation |
| Partitioned SAC305, selected 20×20 Quad4 mesh, Dandu-derived Joule density, two −40→125→−40 °C chamber cycles of 1600 s | last-cycle 20-element top-row mean `dW = 0.197122 MPa` quasisteady and `0.197003 MPa` lumped transient (`-0.0605%`) | maximum 10 iterations; maximum final-residual/acceptance-limit fraction `0.473`; all increments met Core's residual rule before commit | Slow-cycle reduced-model sensitivity with unit Taylor–Quinney conversion to uniform heat; the 5 µm top row is mesh-specific and does not establish convergence or monolithic `phi-T-u` validation |
| Same selected 20×20 partitioned case with a 1 s period | last-cycle 20-element top-row mean `dW = 0.286218 MPa` quasisteady and `0.108291 MPa` lumped transient (`-62.16%`); transient peak `98.58 °C` versus `144.94 °C` | maximum 10 iterations; maximum final-residual/acceptance-limit fraction `0.497`; all increments met Core's residual rule before commit | Fast-cycle model sensitivity with the same reduced heat-feedback assumption; single-mesh result with no crack/life or device oracle |
| SAC305 stateful block, 3×3×2 Hex8, one −40→125→−40 °C cycle over 1600 s, 8 increments | `dW_peak = 0.389021 MPa`, `dW_mean = 0.343364 MPa`, peak/mean `1.13297` | maximum 8 iterations; maximum final-residual/acceptance-limit fraction `0.901` | All increments met Core's residual rule; stabilized-cycle, load-step/mesh-convergence, and crack-location evidence are not established |
| Synthetic maximum-DNP joint → default 18-Hex8 screening block, one −40→125→−40 °C cycle over 1600 s | four corner joints tie; stable row order selects `SYNTH_J00`; caller/default `h = 50 µm`, `L_D/h = 0.848528`, `dW_peak = 0.0111335 MPa`, Syed screen `47,273` cycles | maximum 6 iterations; source object `VDD_20000_20000_1`, tie set, and tie-break rule retained | Identity-preserving, calibration-specific screening output; joint-map height does not size the block and predictive life is not established |

No-swing controls for the plane, 3D, and partitioned examples return zero
inelastic work. A transaction regression also forces nonconvergence and verifies
that no material state is committed.

The normal regression suite retains the separate 2×2 partitioned smoke oracle
for runtime. The 20×20 records above are the explicitly selected public website
case; comparing their mesh-dependent top-row values with the smoke case is not
a mesh-convergence study.

## Integration and provenance paths

The bundled `cases/synthetic_pdn` case checks:

- project-authored placement, power, PDN, and joint-map manifests;
- stable source-object IDs and explicit units;
- resistor-network voltage against the fixture's closed-form reference;
- source/thermal power balance;
- voltage-to-temperature-to-stress-to-screening handoffs; and
- output labels that keep the result at synthetic-integration scope.

Joint-map tests cover unit normalization, affine transforms, duplicate-ID
rejection, explicit-map precedence, and a labeled PDN-node proxy fallback.
No third-party design or PDK data is bundled.

## Local TSV and periodic paths

Public checks cover:

- cubic silicon stiffness and rotation;
- Tet4 affine strain and thermal-eigenstrain assembly;
- conformal Cu/oxide-cup/Si topology with no direct Cu/Si contact;
- field recovery and Raman point/spot sampling contracts;
- material, mesh, coordinate, and stable-ID provenance;
- Gmsh opposite-face correspondence plus EDA node matching; and
- generic Core affine-relation consumption for selected serial controls.

Open work includes corrected-scene mesh/domain/recovery convergence,
source-equivalent periodic/bottom boundary selection, an MPI periodic-TSV
consumer, measured Raman comparison, and transistor/device comparison.

## Optional generated-mesh and distributed paths

The toolchain tier defines selected checks for generated Hex8/Tet4
electrothermal models, three-dimensional thermo-mechanics, composite TSV
stress, serial-versus-MPI coupled output, solder/package geometry and stateless
elastic region assembly, design-map propagation, and native Core Tet4 patch/
self-heating cases.

These checks are bounded by their chosen meshes and solver environments. This
file makes no timing, memory, rank-scaling, imported-CAD, or signoff claim.

## Historical solver record

The pre-repair plane, ETV, and 3D drivers used an elastic modified-Newton
tangent. Instrumented audits showed max-iteration exhaustion in the tested
configurations; the plane and ETV paths also committed each state twice. Their
old energy, life, and corner-location outputs are therefore not current release
results. Git history retains the code for research provenance. The table above
reports only repaired, fail-closed reruns.

## Running the checks

```bash
./setup.sh
python -m eda_multiphysics.run
python -m pytest -q
python -m pytest -q -m toolchain
```

The default pytest configuration excludes `toolchain`. Consult
`docs/VALIDATION_GUIDE.md` for interpretation and `docs/roadmap.md` for the
next evidence-producing work.
