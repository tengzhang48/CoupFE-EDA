# Tet4 element — consumer qualification

**Task:** qualify a 4-node linear tetrahedron so gmsh can mesh arbitrary CAD; the all-hex
subdivision path is limited to selected shapes.

## Ownership decision

Tet4 is a general finite-element/code-generation primitive, so `tet4` and `tet4r` belong in
CoupFE core next to the other element definitions. CoupFE-EDA consumes the native core
`ElementConfig`; it does not ship a duplicate shape/quadrature template or modify core's
template resolver.

This is a fail-closed dependency. The EDA release is pinned to publicly reachable Core
`933e497301ee3ddb23391b787726674f70b480c5`, which contains native `tet4` support. The current
toolchain tier passes the Tet4 patch and self-heating gates against that exact dependency.

Periodic mesh metadata, face/node matching, and box construction are EDA-owned adapters. They must
not be restored to core merely to create a combined pin. If periodic support remains in scope, the
final core may expose only the generic affine-relation/compiler primitives consumed by EDA's local
periodic adapter.

## Current qualification gates

The values below are encoded as regression targets in `tests/test_toolchain.py`
(`test_tet4_patch_test`, `test_tet4_self_heating`) and the gates pass on the selected public
Core pin. They qualify generated box/cylinder meshes at the checked resolutions, not a general
imported-CAD workflow.

| gate | oracle | result |
|---|---|---|
| **Patch test** (linear T, irregular tet mesh) | linear-complete → machine precision | `max|err| = 4.4e-16` |
| **Self-heating, tet box** | `σV₀²/8k` (the exact oracle etv_3d's Hex8 hits) | peak 1.021 vs 1.000, **2.1%**, → 1.0% at half h |
| **Self-heating, tet cylinder** (curved CAD) | `σV₀²/8k` (1-D through the height) | peak 1.020 vs 1.000, **2.0%**, all signed vols > 0 |

The patch test is the rigorous correctness gate (a wrong element gives O(1e-1), not 1e-16); the
self-heating error is linear-tet discretization of the parabolic profile and **converges** with
refinement (2.1%→1.0% as h halves) — confirming it's discretization, not a bug. The **cylinder** is
the payoff: a curved shape the all-hex path handles poorly, meshed natively as tets, validated.

## Files
- `eda_multiphysics/tet_element.py` — fail-closed lookup of core's native `tet4` configuration.
- `eda_multiphysics/mesh3d.py` — `tet_box`, `tet_cylinder`, `min_signed_tet_volume`, `_orient_tets`.
- `eda_multiphysics/tet_3d.py` — build + solve + `patch_test` / `solve_selfheat` / `oracle_selfheat`.
- `eda_multiphysics/etv_kernel.py` — `build_et_kernel(..., element="Tet4")` routes to the tet config.

## Reuse for other physics
`build_et_kernel(element="Tet4")` is the pattern: any codegen weak form (including the
thermo-mechanical `u+T` element) can target core's native tet configuration. The mesh side is
`mesh3d.tet_box` / `tet_cylinder`; a named imported-CAD adapter remains future work.
