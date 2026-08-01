# Module map

This map groups the package by workflow. The groups are navigation aids, not
independent products or maturity levels. See [Capabilities](capabilities.md)
for the evidence boundary of each path.

| Workflow | Modules | Purpose |
|---|---|---|
| Scalar fields | `fe`, `electrothermal`, `transient`, `capacitance`, `thermal_runaway` | Structured reference problems for diffusion, conduction, self-heating, storage, and thermal feedback |
| Coupled electrothermal | `etv_solder`, `etv_fe`, `etv_kernel`, `etv_3d`, `tsv_3d`, `tet_3d` | Reduced, monolithic, compiled, and generated-mesh electrothermal examples |
| PDN and design handoff | `pdn_graph`, `pdn_distributed`, `case_thermal`, `electrothermal_chip`, `chip_vtu` | Resistor-network solve, placement/power mapping, optional PETSc solve, and output adapters |
| Thermomechanics | `thermomech`, `thermomech_kernel`, `thermomech_3d`, `thermomech_tsv`, `tsv_stress` | Reference and generated three-dimensional thermal-stress models |
| Solder constitutive models | `anand`, `solder_joint`, `anand_3d`, `creep` | Material-point, return-map, prescribed-state-update, fail-closed stateful block, and creep examples |
| Reliability handoff | `joint_map`, `reliability_3d`, `reliability_pipeline`, `electromigration` | Stable design objects, generated package/joint meshes, calibration mappings, and composed synthetic screening |
| Geometry and mesh adapters | `mesh3d`, `tet_element`, `periodic` | Gmsh-generated regions, mesh checks, native Core Tet4 lookup, and EDA-owned periodic matching |
| TSV local/device path | `tsv_local_3d`, `tsv_device`, `tsv_validation` | Anisotropic local mechanics, field recovery, Raman/device transformations, manifests, and fail-closed status evaluation |
| Distributed experiments | `etv_distributed`, `etv_distributed_fs`, `etv_fieldsplit`, `pdn_distributed`, `scaling_bench` | PETSc/MPI implementations and checked-size comparison utilities |
| Test entry points | `gates`, `run`, `validate`; `tests/` | Analytic, comparison, invariant, interface, provenance, and optional-toolchain checks |

## Ownership boundary

CoupFE owns mesh-agnostic element/operator, assembly, nonlinear-solve, and
affine-constraint primitives. CoupFE-EDA owns design-file parsing, geometry and
mesh adapters, region/boundary semantics, EDA provenance, material selections,
coupled workflows, and problem-specific evidence.

This repository pins Core revision
`454f73ce2de284262b214a2b37bd676c6aca3c0a`. Code that imports a mesh-specific
periodic adapter from Core violates the current boundary and is covered by a
regression test.

## Adding a workflow

A public workflow should include:

- a documented input/output and unit contract;
- stable source-object and region identity where data crosses tools;
- a named evidence type and acceptance criterion;
- a broken control or invariant when one is meaningful;
- a runnable example listed in `EXAMPLES.md`; and
- license/provenance information for bundled or caller-supplied data.

Experimental scripts can remain internal until those boundaries are clear.
