# Geometry and mesh handoffs

CoupFE-EDA uses several representations because PDN, die thermal, TSV, and
package-joint questions require different spatial detail. Geometry fidelity is
part of each example's input contract and claim boundary.

| Use | Representation | Source |
|---|---|---|
| PDN voltage and EM screening | resistor graph with layout coordinates | supported SPICE export or synthetic fixture |
| Die temperature | structured two-dimensional grid with instance power bins | placement/power CSV plus metadata |
| Via and layer electrothermal cases | generated Hex8 or Tet4 volume mesh | Gmsh/OpenCASCADE primitives |
| Local TSV mechanics | conformal Cu/oxide/Si Tet4 model | generated blind-via or periodic cell |
| Solder/package handoff | generated joint profile or conformal package regions | Gmsh/OpenCASCADE primitives |
| Joint locations | stable-ID CSV plus JSON metadata | package export or labeled proxy |

The package does not currently provide a general STEP/BREP importer. A new
mesh adapter must supply coordinates, connectivity, material regions, boundary
sets, units, coordinate frame, and stable source-object IDs before downstream
results can retain provenance.

## Blind TSV submodel

`mesh3d.tsv_device_submodel(...)` creates a conformal three-region Tet4 scene in
micrometres:

```python
from eda_multiphysics.mesh3d import tsv_device_submodel

mesh = tsv_device_submodel(
    diameter_um=10.0,
    via_depth_um=55.0,
    oxide_um=0.4,
    si_radius_um=30.0,
    si_depth_um=60.0,
    h_um=2.0,
    raman_depth_um=0.2,
)
```

The Cu occupies the blind cylindrical core. The oxide forms a sidewall and
bottom cup; construction fails if Cu and Si share direct interface nodes. The
returned mapping includes:

- one coordinate table and named `copper`, `oxide`, and `silicon` Tet4 regions;
- `top`, `bottom`, and `outer` boundary node sets;
- conformal material-interface node sets and signed-volume checks;
- exact and discretized volumes;
- unit, coordinate-frame, crystal-rotation, and stable TSV-ID metadata; and
- explicit wafer, Raman-plane, Cu-tip, and liner-tip locations.

Supplying `h_near_um` and `refine_extent_um` together enables a local Gmsh size
field near the Cu/liner top surfaces. The generated geometry is a parametric
submodel, not imported process CAD. Domain-size, mesh, recovery, and boundary
sensitivity remain required for a physical result.

## Periodic TSV cell

`mesh3d.tsv_periodic_cell(...)` generates a rectangular cell with named
opposite faces. Defaults follow the cited Jiang geometry dimensions: 40 and
50 micrometre in-plane pitches, a 10 micrometre Cu diameter, a 0.4 micrometre
oxide cup, and a 55 micrometre blind depth. Global axes are recorded as
`[110]`, `[-110]`, and `[001]`.

Gmsh creates corresponding surface meshes. The EDA adapter independently
checks a translated node bijection and records pair hashes and mismatch. A
geometry result can report
`periodic_pairing_status="matching_nodes_verified"` while
`periodic_mechanics_status="not_solved"`; pairing does not imply a mechanics
solution.

```python
from eda_multiphysics.mesh3d import tsv_periodic_cell
from eda_multiphysics.tsv_local_3d import solve_local_tsv

cell = tsv_periodic_cell(h_um=2.0)
result = solve_local_tsv(
    cell,
    dT_K=-250.0,
    boundary_condition="periodic_macro_gradient",
    macro_gradient=Hbar,
)
```

The macro gradient is required; the adapter does not silently substitute a
fixed periodic box. See [Periodic MPC status](PERIODIC_MPC_STATUS.md).

## Solder profiles

`mesh3d.solder_bump(...)` revolves an axisymmetric radial profile:

```python
from eda_multiphysics.mesh3d import solder_bump

barrel = solder_bump(R_pad=25.0, R_mid=29.0, L=50.0, h=8.0)
hourglass = solder_bump(R_pad=25.0, R_mid=21.0, L=50.0, h=8.0)
```

`R_mid > R_pad` labels a barrel, `R_mid < R_pad` an hourglass, and equality a
cylinder. Dimensions are unit-agnostic but must be consistent. Returned data
includes the connected Hex8 mesh, cap/lateral boundary sets, profile parameters,
OpenCASCADE volume, and a signed-Jacobian check.

`mesh3d.solder_package(...)` adds conformal solder, underfill, top/bottom UBM,
and pad regions. It returns a shared Tet4 node table, named regions, external
pad boundaries, interface node sets, volumes, and all geometry parameters.
`reliability_3d.solve_solder_package_joint(...)` applies the stateless elastic
generated-region example. Default stiffness values are study inputs, not a
qualified package material deck.

The public generated-joint path checks geometry, region assembly, imposed
boundary data, and elastic strain extraction. A converged stateful Anand solve
on the generated joint/package mesh is not included.

## Joint-map contract

`joint_map.load_joint_map()` reads:

- `joints.csv`, with required `joint_id,x,y` and optional
  `z,diameter,height,net,source_object_id`; and
- sibling `joints.meta.json`, containing schema version, coordinate and
  dimension units, source, geometry-fidelity label, coordinate frame, and a
  transform into die micrometres.

Example metadata:

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

The loader converts public coordinates and dimensions to micrometres. It
rejects missing metadata, unsupported units, singular transforms, duplicate
IDs, invalid dimensions, empty input, and unknown fidelity labels. Supported
labels are `proxy`, `design_export`, `calibrated`, and `qualified`; the label is
source metadata and does not by itself qualify a result.

If `neutral_point_um` is omitted, the transformed joint centroid is used.
`design_joints()` and `from_design(joint_map_path=...)` prefer this explicit
map. PDN-name inference remains available as a
`pdn_node_proxy_fallback` and is identified in the result.

The bundled nine-row joint map is project-authored synthetic proxy data. It
demonstrates stable IDs, units, transforms, and handoffs; it is not a package
export.

## OpenROAD and other mesh/software connections

The OpenROAD adapter uses a versioned, file-based boundary:

- placement/object CSV plus manifest;
- PDN SPICE or voltage export;
- explicit units and source identity; and
- stable identifiers retained through downstream maps.

OpenROAD itself is optional and is not bundled in the Python distributions.
Other placement, package, or mesh software can use the same boundary by
producing equivalent declared data. A direct adapter should be added only when
it can preserve region/boundary semantics and source identity; converting
connectivity without those fields is insufficient for a reproducible local
model.

## Acceptance checks

The geometry-related tests cover, at selected parameters:

- connected volume-node tables and positive element measures;
- cap, outer, and material-interface boundary membership;
- profile and exact-volume metadata;
- conformal package-region partitioning;
- blind-TSV oxide-cup topology and absence of direct Cu/Si contact;
- periodic translated-node matching and fail-closed relation construction;
- joint-map units, transforms, IDs, and proxy labeling; and
- native Core Tet4 patch/generated-geometry cases.

These checks do not establish imported-CAD coverage, fabrication tolerances,
material calibration, or mesh/domain convergence for a real device.
