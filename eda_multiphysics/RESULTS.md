# Current evidence summary

This file maps implemented examples to their public evidence. It is not a test
log. Release status comes from a clean, retained checkpoint described in
`docs/RELEASE_EVIDENCE.md`.

## Core and environment boundary

The candidate targets CoupFE revision
`454f73ce2de284262b214a2b37bd676c6aca3c0a`. Evidence must record the imported
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
| Stage-A ETV FE | monolithic Quad4 self-heating and sequential comparison | checks the spatial `phi`/`T` element; no stateful thermo-viscoplastic mesh cycle |

The retained stateful finite-element example is
`anand_3d.prescribed_hex8_cycle`. All face displacements are prescribed, so it
checks state evolution and the CoupFE commit path in one element. It is not a
multi-element solder-joint boundary-value solution.

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

## Excluded stateful workflows

Earlier plane-strain ETV cycles and multi-element stateful solder-joint BVP/life
functions did not meet their stated increment convergence boundary. They are
absent from the public modules and examples. Reintroduction requires explicit
convergence reporting, fail-closed behavior, one solver-owned commit per
returned increment, and mesh/load-step evidence.

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
