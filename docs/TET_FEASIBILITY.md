# Native Tet4 consumer status

CoupFE-EDA uses native Tet4 support from Core for generated curved and
multi-region examples. The pinned dependency is
`454f73ce2de284262b214a2b37bd676c6aca3c0a`.

## Ownership

- Core owns the generic Tet4 element configuration, assembly, operator
  contract, and affine-constraint primitives.
- CoupFE-EDA owns Gmsh generation, region/boundary identity, material mapping,
  local-TSV semantics, and problem-specific evidence.

`eda_multiphysics.tet_element.tet4_config()` fails if the imported Core does not
provide the required native configuration. The setup scripts verify the exact
Core source rather than accepting an unrelated name-matched installation.

## Public checks

The optional toolchain tier contains:

- an affine Tet4 patch case; and
- a coupled self-heating case on generated box/cylinder geometry.

Other tests exercise Tet4 region/topology and affine-strain behavior in the
generated solder-package and blind-TSV models. These cases define acceptance at
their selected geometries, sizes, materials, and tolerances. Release evidence
must record the actual command result and environment.

## Scope

The current path supports generated Tet4 boxes, cylinders, conformal package
regions, and blind/periodic TSV regions used by this repository. It does not
establish:

- arbitrary STEP/BREP import;
- named-region recovery from an external CAD hierarchy;
- broad element-quality or mesh-convergence behavior;
- stateful Anand fatigue on an imported local mesh;
- distributed periodic-TSV consumption; or
- process/device prediction accuracy.

Adding an external mesh reader requires more than connectivity conversion. It
must preserve units, coordinate frame, material regions, boundary sets, stable
source-object identifiers, and mesh provenance. The corresponding physics
workflow also needs a named oracle, comparison, invariant, or measured dataset.

## Relevant files

- `eda_multiphysics/tet_element.py` — native Core Tet4 lookup.
- `eda_multiphysics/tet_3d.py` — generated patch and self-heating cases.
- `eda_multiphysics/mesh3d.py` — Tet4 geometry and region construction.
- `eda_multiphysics/tsv_local_3d.py` — anisotropic local mechanics and field
  recovery.
- `eda_multiphysics/reliability_3d.py` — stateless elastic generated-package
  handoff.
- `tests/test_toolchain.py` and `tests/test_tsv_local_3d.py` — public
  acceptance definitions.

See [Geometry](GEOMETRY.md) and [Roadmap](roadmap.md).
