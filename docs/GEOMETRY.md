# Geometry in CoupFE-EDA

Geometry fidelity is selected by the engineering decision, not maximized uniformly. A routed chip
should not become a volumetric finite-element mesh merely because one solder joint needs local
stress resolution.

## Fidelity map

| Analysis | Representation | Current source |
|---|---|---|
| PDN voltage and EM current | 1-D resistor graph with layout coordinates | PDNSim `write_pg_spice` |
| Die thermal field | 2-D structured grid with placed-instance power bins | OpenDB `instances.csv` + manifest |
| TSV electrothermal/stress | 3-D cylinder, concentric annulus, or blind Cu/oxide/Si submodel | Gmsh/OpenCASCADE primitives |
| Package through-thickness conduction | conformal 3-D layer stack | Gmsh fragmented volumes |
| Solder global-local fatigue | cylinder, barrel, or hourglass Hex8 joint | parametric revolved profile |
| Local package sensitivity | solder + underfill + top/bottom UBM + pads | conformal six-region Tet4 assembly |
| Stateful 3-D Anand reference | small regular cuboid Hex8 BVP | structured reference mesh |

The first two levels preserve EDA object identity and remain computationally tractable. Local 3-D
models are introduced only where shape controls gradients, such as TSV interfaces, solder necks,
current-crowding corners, or crack-initiation regions.

## Blind TSV device-submodel API

`mesh3d.tsv_device_submodel` creates a conformal three-region Tet4 local scene in micrometers:

```python
from eda_multiphysics.mesh3d import tsv_device_submodel

mesh = tsv_device_submodel(
    diameter_um=10.0, via_depth_um=55.0, oxide_um=0.4,
    si_radius_um=30.0, si_depth_um=60.0, h_um=2.0,
    raman_depth_um=0.2,
    h_near_um=0.5, refine_extent_um=12.0,
)
```

The Cu occupies `-via_depth_um <= z <= 0`. The liner extends to
`z=-(via_depth_um+oxide_um)`, forming both a cylindrical sidewall and a bottom cap; a geometry gate
rejects any direct Cu/Si contact. The deeper Si domain makes the via blind and the `z=0` wafer
surface is available as a natural traction-free boundary. The returned object
contains `regions={copper,oxide,silicon}`, `top`, `bottom`, `outer`, shared material-interface node
sets, exact OCC and discretized volumes, signed-volume quality, units, stable TSV identity, and the
explicit Raman-plane and Cu/liner-tip coordinates. It also declares the global axes, crystal-to-
global rotation, and zero direct Cu/Si interface nodes. Gmsh's frontal Tet4 route is intentional:
the thin liner and blind tip are not qualified all-Hex subdivision shapes.

`h_near_um` and `refine_extent_um` must be supplied together. A Gmsh distance/threshold field uses
only the Cu/liner top faces as sources, so refinement expands locally around the TSV surface rather
than across the full silicon disk. The returned `mesh_refinement` metadata records both sizes and
the number of identified source surfaces. Omitting both parameters retains the uniform-size route.

This is a parametric local submodel, not imported process CAD. Its radial/depth boundary and mesh
size must pass `TSV_ANISOTROPIC_3D_PLAN.md` before the field can be used as release evidence.

## Jiang periodic-cell foundation

`mesh3d.tsv_periodic_cell` constructs a full rectangular 40 by 50 µm cell by default, with the
10 µm Cu via, 0.4 µm oxide cup, 55 µm blind depth, and named opposite faces. Global `x`, `y`, and
`z` are `[110]`, `[-110]`, and `[001]`, respectively; `[-110]` is the sign-reversed equivalent of
the paper's `[1-10]` pitch direction and keeps the stored frame right-handed.

```python
from eda_multiphysics.mesh3d import tsv_periodic_cell

cell = tsv_periodic_cell(h_um=2.0, h_near_um=0.5, refine_extent_um=12.0)
assert cell["periodic_pairing_status"] == "matching_nodes_verified"
assert cell["periodic_mechanics_status"] == "not_solved"
```

Gmsh now makes the plus faces periodic copies of the minus faces. The API verifies strict one-to-one
translated node pairs, including edges/corners, and records pair hashes/mismatch plus the periodic
box. Geometry pairing alone still reports `periodic_mechanics_status="not_solved"`. Calling
`solve_local_tsv(..., boundary_condition="periodic_macro_gradient", macro_gradient=H)` then applies
CoupFE's exact affine MPC; `H` is required and is never silently set to zero. A result from the
isolated-cylinder solver must not be relabeled as a Jiang periodic result.

## Parametric solder-joint API

`eda_multiphysics.mesh3d.solder_bump` creates a smooth axisymmetric profile by revolving a radial
meridian through Gmsh's OpenCASCADE kernel:

```python
from eda_multiphysics.mesh3d import solder_bump

barrel = solder_bump(R_pad=25.0, R_mid=29.0, L=50.0, h=8.0)
hourglass = solder_bump(R_pad=25.0, R_mid=21.0, L=50.0, h=8.0)
```

`R_mid > R_pad` produces a barrel; `R_mid < R_pad` produces an hourglass; equality produces a
cylinder. Dimensions are unit-agnostic but must be consistent. The returned dictionary contains:

- `coords`, `elems`: connected Hex8 volume mesh;
- `cap0`, `capL`, `lateral`: boundary-node sets;
- `shape`, `R_pad`, `R_mid`, `L`, `profile_z`, `profile_r`: geometry provenance; and
- `volume`: exact OpenCASCADE solid volume.

The generator removes the source meridian left by a full revolution and constructs the FE node
table only from volume elements. This prevents orphan CAD nodes from creating singular matrix rows.
Every regression also requires a positive minimum signed Hex8 Jacobian.

## Conformal package-region API

`mesh3d.solder_package` adds underfill, two UBM layers, and two metal pads around the profiled
solder. The underfill is cut by the joint, and every touching solid is fragmented so interfaces
share nodes:

```python
from eda_multiphysics.mesh3d import solder_package
from eda_multiphysics.reliability_3d import solve_solder_package_joint

mesh = solder_package(
    R_pad=25.0, R_mid=28.75, L=50.0,
    R_ubm=29.0, R_metal=35.0, R_underfill=45.0,
    t_ubm=5.0, t_pad=8.0, h=12.5,
)

U, mesh, solve_info = solve_solder_package_joint(
    du=0.10, R_pad=25.0, R_mid=28.75, h_joint=50.0,
)
```

The package implementation requires native Tet4 elements from CoupFE core. The selected public
Core release supplies that support, and the current toolchain tier passes the conformal-region
and multi-material package-solve gates. This qualifies the generated model at the tested
parameters, not arbitrary imported CAD or a production material deck. Gmsh's all-Hex8
subdivision produced negative Jacobians in the multiply connected underfill shell; the
implementation switches element family instead of weakening mesh-quality acceptance. Returned
data includes:

- six named `regions` and exact OCC `volumes`;
- `bottom` and `top` external pad boundary sets;
- shared node sets for solder/UBM, solder/underfill, and pad/UBM `interfaces`;
- one connected node table referenced by every Tet4; and
- `element="Tet4"` plus all geometry parameters.

The default material map in `solve_solder_package_joint` supplies representative stiffness ratios
for sensitivity analysis. It is not a foundry-qualified package material deck. Override named
regions with `materials={name: (G, K)}`.

## Reliability integration

The geometry is available through `solve_solder_joint` and `from_design`:

```python
from eda_multiphysics.reliability_3d import solve_solder_joint, from_design

U, mesh = solve_solder_joint(
    du=0.01,
    R=0.5,
    h=0.4,
    joint_shape="hourglass",
    R_mid=0.40,
)

scorecard = from_design(
    joint_shape="barrel",
    R_mid=29.0,       # microns because the design bridge uses microns
    include_package=True,
)
```

CLI equivalents are:

```bash
python -m eda_multiphysics.reliability_3d --shape hourglass --mid-radius 0.40
python -m eda_multiphysics.reliability_3d design --shape barrel --mid-radius 29.0
python -m eda_multiphysics.reliability_3d design --shape barrel --package
python -m eda_multiphysics.reliability_3d design --joint-map path/to/joints.csv
```

The cylindrical profile remains the default because it is the frozen shear oracle and preserves
the historical validation contract. Profiled joints are explicit sensitivity cases rather than a
silent reinterpretation of earlier life predictions. At the regression mesh, the default
hourglass changes the 95th-percentile equivalent strain by more than 2% relative to the cylinder;
the sign and magnitude are model-, profile-, and mesh-dependent and must not be generalized.

## Versioned joint-map input

`joint_map.load_joint_map()` reads a package-location table without discarding object identity or
coordinate provenance. A case supplies two files:

- `joints.csv`: required `joint_id,x,y`; optional `z,diameter,height,net,source_object_id`;
- `joints.meta.json`: schema version, coordinate/dimension units, source label, source coordinate
  frame, affine transform into die microns, and an optional neutral point.

```json
{
  "schema_version": 1,
  "coordinate_unit": "mm",
  "dimension_unit": "mm",
  "coordinate_frame": "package",
  "source": "package_bump_export",
  "geometry_fidelity": "design_export",
  "transform_to_die_um": {
    "matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "offset_um": [1000, 2000, 0]
  }
}
```

The loader normalizes all public geometry to microns and rejects missing metadata, unsupported
units, non-finite or singular transforms, non-positive dimensions, empty maps, duplicate IDs, and
unknown geometry-fidelity labels. `geometry_fidelity` is one of `proxy`, `design_export`,
`calibrated`, or `qualified`; it is independent of whether the file is explicit.
If `neutral_point_um` is absent, it uses the transformed joint centroid. `design_joints()` and
`from_design(joint_map_path=...)` prefer this explicit map; a missing map activates the legacy
PDN-node inference with `pdn_node_proxy_fallback` provenance in the result.

The bundled synthetic case includes nine stable IDs in
`cases/synthetic_pdn/joints.csv`. It is deliberately labeled
`project_authored_synthetic_joint_map` with `geometry_fidelity="proxy"`: the file
demonstrates and regression-tests the schema, but it is not a package bump export.
Replacing it with a caller-owned foundry or package-tool export does not require
changing the reliability solver.

## What is still abstract

- The bundled explicit joint map is a project-authored synthetic proxy; a real package bump export is not
  available in this public reference case.
- UBM, pads, and underfill are parametric canonical regions; intermetallic layers, solder mask,
  substrate traces, voids, and imported dimensions remain absent.
- The profiled Gmsh joint drives the elastic/global-local fatigue bridge. The stateful 3-D Anand BVP
  still uses a regular cuboid mesh and is labeled accordingly.
- The repository does not yet wrap STEP/BREP import, even though the installed Gmsh OpenCASCADE API
  exposes `importShapes()`.
- There is no versioned `PhysicalScene` carrying hierarchy, coordinate transforms, material regions,
  boundary semantics, and stable EDA identifiers across all model dimensions.

## Recommended next increments

1. Replace the reference proxy rows with a real package bump/TSV export using the implemented
   stable-ID and coordinate-transform schema.
2. Calibrate the parametric pad/UBM/underfill regions against a documented package cross-section.
3. Add a STEP/BREP-to-Tet4 local-submodel adapter with named-volume and named-boundary mapping.
4. Generalize the stateful Anand operator to consume a validated external local mesh so the profile
   can use the stateful constitutive model directly.
5. Introduce the common scene/schema only after these concrete object and boundary requirements are
   exercised by reference cases.

## Validation

- `test_solder_bump_profile_geometry`: profile classification, exact caps, connected-node invariant,
  radius, volume, boundary sets, and positive Jacobian.
- `test_reliability_3d_profile_changes_strain_field`: the profile must materially change the solved
  upper-tail strain while preserving the imposed cap boundary conditions.
- `test_solder_package_conformal_regions`: six regions, connected positive-volume Tet4 mesh, shared
  interfaces, exact external caps, and exact OCC volume partition.
- `test_solder_package_multimaterial_solve`: material-region assembly, exact imposed pad BCs,
  finite solder strain, and bounded FieldSplit iterations.
- `test_reliability_design_map_with_package_regions`: the full joint-map-driven fatigue map consumes
  the package-region solve.
- Joint-map regression tests cover unit normalization, affine transforms, duplicate-ID rejection,
  explicit-map preference, labeled fallback, and the nine-row bundled synthetic proxy.
- Existing cylindrical shear and layout-map tests remain unchanged as compatibility oracles.
