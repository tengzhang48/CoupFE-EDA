# API reference

The package is at an alpha research stage. Module-level functions are useful
for examples and experiments, but compatibility is not yet guaranteed across
minor releases. Arrays use NumPy. Unless a function states otherwise, geometry
uses SI units; several EDA adapters use micrometres and record that choice in
metadata.

Install through `./setup.sh` so the package imports the qualified CoupFE
revision `454f73ce2de284262b214a2b37bd676c6aca3c0a`. A name-matched package from
an unrelated index is not an accepted substitute.

## Scalar fields

`eda_multiphysics.fe` provides:

- `StructuredQuadMesh(nx, ny, Lx, Ly)` for small rectangular examples;
- `solve_field(mesh, coeff_elem, source_elem, dirichlet, node_source=None)` for
  scalar diffusion/conduction; and
- `electrode_current(op, U, electrode_nodes)` and `elem_gradients(mesh, U)` for
  reaction-flux and gradient recovery.

`electrothermal.solve_electrothermal(...)` performs the structured two-way
electrical/thermal iteration. `etv_fe.solve_coupled_et(...)` solves the
monolithic Quad4 `phi`/`T` system. Its public checks are
`verify_selfheating_fe(...)` and `consistency_vs_staggered(...)`.
`etv_fe.thermoviscoplastic_cycle(...)` and
`thermoviscoplastic_comparison(...)` add a partitioned SAC305 example with a
lumped temperature model and spatial plane-strain mechanics; they are not a
monolithic `phi-T-u` formulation.

`transient.mode_decay(...)`, `capacitance.parallel_plate(...)`, and
`thermal_runaway.critical(...)` / `steady_T(...)` are small reference models.

## PDN and design inputs

`eda_multiphysics.pdn_graph` provides:

- `parse_pg_spice(path)` for the supported resistor/source subset; and
- `solve_pdn(path, conductance_scale=None)` for the serial graph solve.

`pdn_distributed.build_from_spice(path)`, `serial_solve(...)`, and
`dist_solve(...)` expose a PETSc research path. The current release does not
retain a rank-executed regression for this module. Direct mode depends on the
PETSc installation; callers should not infer availability from the Python API
alone.

`case_thermal.run(case_dir, total_power_W=None, ...)` maps instance placement
and labeled power inputs to a two-dimensional temperature field.
`electrothermal_chip.run(...)` and `chip_vtu.run(...)` provide composed
placement/PDN/thermal examples. The bundled default is the project-authored
`cases/synthetic_pdn` scenario. Caller data must declare units and provenance.

`joint_map.load_joint_map(csv_path, metadata_path=None)` loads the versioned
joint-map contract. It normalizes units, applies an optional affine transform,
checks stable IDs, and retains source-object and geometry-fidelity labels.

## Thermomechanics and TSV stress

`eda_multiphysics.thermomech` contains the bimetal, thermal-gradient cylinder,
and pressurized-cylinder reference models:

- `bimetal(...)` and `timoshenko_curvature(...)`;
- `thermal_gradient_cylinder(...)` and `tg_cylinder_hoop(...)`; and
- `lame_cylinder(...)`.

`tsv_stress.solve_tsv(...)`, `lame_sigma_r(...)`, and `sigma_at(...)` implement
the two-dimensional axisymmetric TSV reference path.

For generated three-dimensional problems:

- `thermomech_3d.solve_thermomech(...)` covers a uniform block;
- `thermomech_tsv.solve_tsv_thermal_stress(...)` covers a generated composite
  cylinder and exposes its analytic displacement functions; and
- `thermomech_kernel.build_thermomech_kernel(...)` builds the generated
  operator used by the optional toolchain tests.

These functions exercise stated material laws and boundary conditions. They do
not provide package- or process-qualified material data.

## Generated geometry

`eda_multiphysics.mesh3d` provides Gmsh-backed constructors:

- Hex8: `via_cylinder`, `via_annulus`, `layer_stack`, and `solder_bump`;
- Tet4: `tet_box`, `tet_cylinder`, `solder_package`,
  `tsv_device_submodel`, and `tsv_periodic_cell`; and
- mesh checks: `min_signed_jacobian` and `min_signed_tet_volume`.

Returned dictionaries contain coordinates, connectivity, region membership,
boundary sets, and geometry metadata. `solder_package` returns conformal
multi-region data. The blind-TSV constructors reject an incomplete oxide-cup
topology rather than silently joining Cu to Si at the via tip.

`tet_element.tet4_config()` resolves native Tet4 support from the pinned Core.
`tet_3d.patch_test(...)` and `solve_selfheat(...)` exercise it on generated
box/cylinder meshes. See [Tet4 qualification](TET_FEASIBILITY.md).

## Periodic adapter and local TSV model

`periodic.match_periodic_nodes(...)` checks a translated bijection between two
surface node sets. `periodic.periodic_relations(...)` combines face, edge, and
corner equivalence classes into generic affine relations. These are
geometry-aware EDA functions; the reduction and affine solve primitives are in
Core.

`tsv_local_3d` provides the linear anisotropic Tet4 path:

- `material_voigt(...)`, `tet4_B_volume(...)`, and
  `assemble_linear_thermoelastic(...)`;
- `minimal_rigid_constraints(...)`, `silicon_far_field_constraints(...)`, and
  `periodic_mpc_setup(...)`;
- `solve_local_tsv(...)`;
- constant-element, volume-weighted nodal, and P1 L2 recovery functions; and
- Raman line/spot sampling functions.

Every local solve records the selected boundary label, coordinate frame,
crystal rotation, and mesh/material digests. The provided outer-boundary and
periodic controls are numerical study choices, not an experimentally selected
global-local boundary condition.

`tsv_device` contains silicon stiffness rotation, stress-to-mobility equations,
Raman observables, KOZ thresholding, orientation sampling, and ID-preserving
device screening. `lame_far_field_stress(...)` produces a labeled synthetic
preview; it is not a replacement for the local three-dimensional solution or
device measurements.

`tsv_validation` checks benchmark-manifest structure, stamps evidence metadata,
and evaluates a fail-closed TSV evidence scorecard. A manifest marked
`definition_only` is a model definition, not a measured comparison.

## Solder constitutive and reliability functions

`anand` provides the material-point functions `sat_resistance`, `sat_stress`,
`plastic_strain_rate`, `integrate_uniaxial`, and `thermal_cycle` for the
included parameter sets.

`solder_joint.anand_return_map(...)` and `patch_test()` cover the plane-strain
return-map/reference element. `solder_joint_cycle(...)` runs an idealized
multi-element SnPbAg cold→hot→cold cycle with fail-closed increments and
reports the increment-summed, equal-volume mean of Gauss-point energy-density
increments over the top element layer.

`anand_3d` provides:

- `anand_return_map_3d(...)` and `drive_homogeneous_3d(...)`;
- `validate_return_map_3d()`, `validate_return_map_transient_3d()`, and
  `patch_test_3d()`; and
- `prescribed_hex8_cycle(...)`, a fully prescribed one-Hex8 state-update
  exercise; and
- `solder_joint_bvp_3d(...)`, an idealized multi-element SAC305 block with
  traction-free lateral faces and a returned element dissipation field.

The one-Hex8 cycle is not a multi-element boundary-value solve. In the separate
block example every increment meets Core's residual rule, but the result does
not establish load-step or mesh convergence, a crack location, or device-life
prediction.

`reliability_3d` supplies generated-mesh handoff functions:

- `solve_solder_joint(...)` and `solve_solder_package_joint(...)`;
- `element_strain(...)` and `tet_element_strain(...)`;
- `design_joints(...)` / `design_grid(...)`; and
- `from_design(...)` for applying the documented DNP displacement and
  calibration mappings across a design map; and
- `critical_joint_bvp_screening(...)` for preserving the maximum-DNP joint
identity while driving the idealized stateful block.

`critical_joint_bvp_screening(...)` derives `L_D` from the selected design-map
object and forms `L_D/h` with its caller-supplied `h_solder`. Returned joint-map
height is provenance metadata; it does not currently size the regular block.

`from_design(...)` prefers an explicit joint map. PDN node-name decoding is a
clearly labeled proxy fallback. The stateful screening value is
calibration-specific and is not a package-life prediction.

`electromigration.black_mttf(...)`, `acceleration_factor(...)`,
`blech_product_crit(...)`, and `em_screen(...)` provide the algebraic EM
screening functions.

## Composed synthetic workflow

`reliability_pipeline.run(...)` composes the bundled placement/power data,
resistor-network solve, electrothermal field, thermo-mechanical proxy, solder
mapping, and EM screening. It returns provenance and claim-boundary fields in
addition to numerical outputs. The default result is an interface and
regression demonstration, not real-device evidence.

## Compiled and distributed paths

The following modules require optional compilers, Gmsh, PETSc, and/or MPI:

- `etv_kernel`, `etv_3d`, `tsv_3d`, and `tet_3d` for generated coupled
  electrothermal kernels and meshes;
- `etv_distributed`, `etv_distributed_fs`, `etv_fieldsplit`, and
  `pdn_distributed` for selected PETSc solve paths; and
- `thermomech_kernel`, `thermomech_3d`, `thermomech_tsv`, and
  `reliability_3d` for compiled/generated three-dimensional cases.

Tool availability, solver configuration, and retained checked-size evidence
must be recorded with the run. The package does not make a performance or
scalability guarantee. In this release, the retained multi-rank regression
covers `etv_distributed_fs`; the other distributed modules remain research
drivers.

## Solver contract

EDA operators consume CoupFE's `residual`, `tangent`, and `commit` contract.
`coupfe.newton_solve` calls `commit` after its iteration loop and before it
returns. Its iteration count is not a convergence flag. Callers must establish
convergence independently and must not commit a stateful operator a second
time. The operator owns material state; geometry and source-object adapters
remain in CoupFE-EDA.

`_stateful_solve.solve_stateful_increment(...)` supplies that application
transaction for the solder examples. It suppresses Core's automatic commit
during the trial solve, evaluates the same Core residual rule, raises without
advancing state on failure, and commits the operator exactly once on success.
The Quad4 and Hex8 numerical tangents are checked against a separate assembled-
residual directional difference after a nonzero history preload; the check also
requires trial residual/tangent calls to leave committed state unchanged.

`_coupled_solve.coupled_newton(...)` is the shared driver for selected compiled
multi-group examples. It accepts a linear-solve callback so the same assembly
can be exercised with direct or PETSc backends. The driver rejects non-finite
increments and raises unless both its increment and final free-DOF residual
criteria are met. FieldSplit callbacks also require a positive PETSc convergence
reason. The retained `etv_fe` wrapper and scalar diffusion wrapper recompute a
final unconstrained residual because Core's iteration count is not a convergence
status. Material-point ODE and staggered Picard examples likewise reject failed,
truncated, or exhausted integrations before returning results.

## Test entry points

```bash
python -m eda_multiphysics.run
python -m pytest -q
python -m pytest -q -m toolchain
```

The default pytest configuration excludes `toolchain`. Run through
`./setup.sh`, or otherwise make the exact Core checkout the imported package.
See [Validation guide](VALIDATION_GUIDE.md) for interpretation and
[Release evidence](RELEASE_EVIDENCE.md) for checkpoint requirements.
