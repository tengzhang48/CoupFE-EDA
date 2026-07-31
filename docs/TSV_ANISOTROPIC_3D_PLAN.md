# Anisotropic 3-D TSV implementation plan

**Objective:** replace the Lamé far-field stress used by the TSV/device preview with a numerically
qualified Cu/oxide/(001)-Si local submodel, then validate the exact Raman observable before making
any experimental or KOZ claim.

**Positioning:** this plan deepens CoupFE-EDA's EDA-aware local interconnect/package-reliability
niche. It does not add TCAD, foundry timing, Cu protrusion, fracture, or signoff capability.

The detailed post-implementation physics review and correction record is
[`TSV_PHYSICS_AUDIT.md`](TSV_PHYSICS_AUDIT.md).

## Accepted physical scene

| Item | Initial value | Contract |
|---|---:|---|
| Cu diameter | 10 µm | Explicit input; stable TSV ID |
| Cu depth | 55 µm | Blind via ending inside silicon |
| SiO₂ liner | 0.4 µm | Separate conformal material region |
| Si local-domain radius/depth | convergence-controlled | Must be enlarged until the device observable changes by ≤3% |
| Wafer surface | `z = 0` | Traction-free |
| Raman sampling plane | `z = -0.2 µm` | Never substitute the surface or von Mises stress |
| Crystal | (001) Si | Explicit crystal-to-global proper rotation |
| Thermal load | specimen manifest | Reference temperature and ΔT are evidence inputs, not hidden defaults |

The numerical output consumed by the device layer is the full symmetric silicon stress tensor in
MPa. The held experimental observable is `sigma_xx + sigma_yy` at the Raman plane. Mobility and KOZ
remain downstream literature-model calculations.

## Delivery sequence

### A. Geometry and extraction foundation

1. Add a Gmsh/OCC Cu/SiO₂/Si blind-TSV scene with conformal Tet4 regions, named top/bottom/outer
   boundaries, exact input geometry metadata, positive-volume checks, and no orphan FE nodes.
2. Add deterministic Raman scan-point generation and Tet4 point-location/constant-element-field
   extraction at exactly 0.2 µm below the free surface.
3. Gate material-region presence, shared interfaces, positive volumes, sampling depth, scan
   direction, and fail-closed behavior for points outside the mesh.

**Exit:** geometry/extraction APIs are usable, but `release_validation` remains false.

### B. Anisotropic linear-thermoelastic local solver

1. Assemble a small-strain Tet4 operator using cubic-Si `C11/C12/C44`, explicit fourth-order
   crystal rotation, isotropic Cu/SiO₂, and thermal eigenstrain.
2. Keep the top surface natural/traction-free. Constrain only rigid modes for the isolated local
   model; add optional displacement boundary data later for submodel transfer.
3. Recover the full stress tensor by material region and expose silicon-only Raman/device fields.
4. Add independent gates: affine constant-strain patch, uniform free expansion, 90° fourfold
   symmetry, reaction balance, and isotropic-Si negative control.

**Exit:** `numerical_mechanics` may pass only after the scorecard's mesh and symmetry tolerances pass.

### C. Discretization and domain qualification

1. Run at least three Tet4 refinements and require ≤2% Raman-observable change on the two finest.
2. Add an independently constructed Hex8 route or structured local oracle and require ≤3% agreement
   for the device-layer quantity of interest.
3. Enlarge the silicon radius/depth until the device metric changes by ≤3%.
4. Record code, geometry, mesh, material, and benchmark-manifest revisions in every evidence result.

**Exit:** numerical qualification only; still no experimental claim.

### D. Curvature and Raman evidence

1. Digitize and freeze the Ryu/Jiang stabilized curvature branch as calibration data.
2. Digitize specimens C and D Raman curves as held validation, including uncertainty and fixed
   comparison masks.
3. Compare the exact `sigma_xx + sigma_yy` observable along the published crystallographic scan at
   `z=-0.2 µm` without retuning between specimens.
4. Apply the mandatory peak-location, magnitude, NRMSE, load-ratio, and symmetry gates from
   `CoupFE_EDA_TSV_Device_Validation_Release_Plan.md`.

**Exit:** only passing evidence may move `global_experiment` or `local_experiment` to `passed`.

### E. EDA action and multilevel scaling

1. Replace the preview stress proxy with the accepted local field while preserving source/device/TSV
   IDs and coordinates.
2. Emit placement keep-out constraints or a legal cell-move/reorientation action; report area,
   displacement, and wirelength proxies without a timing claim.
3. Implement conservative global→local temperature/displacement/traction transfer and compare with
   a fully resolved array at matched local fidelity.
4. Run the independent MORE-Stress comparison and distributed 3-D scaling only after the isolated
   local solution is qualified.

## API targets

- `mesh3d.tsv_device_submodel(...) -> dict`: conformal oxide-cup regions, boundaries, interfaces,
  zero direct Cu/Si contact, coordinate/crystal frame, and geometry.
- `mesh3d.tsv_periodic_cell(...) -> dict`: full 40/50 µm cell, named opposite faces, proper frame,
  and explicit periodic-pairing status.
- `tsv_local_3d.solve_local_tsv(...) -> LocalTSVResult`: displacement, element stress, reactions,
  boundary/frame/material/mesh provenance, and explicit `release_validation`.
- `tsv_local_3d.raman_scan_points(...)`: physical scan coordinates at the required depth.
- `tsv_local_3d.sample_element_field(...)`: fail-closed constant-element extraction.
- `tsv_local_3d.element_to_nodal_field(...)` / `sample_nodal_field(...)`: explicit
  volume-weighted recovery and barycentric interpolation for refinement studies.
- `tsv_local_3d.project_element_field_l2(...)`: consistent P1 recovery for a declared convergence
  route.
- `tsv_local_3d.gaussian_spot_quadrature(...)` / `silicon_raman_spot_profile(...)`: deterministic
  spatial-resolution sensitivity with no hidden default width.
- Existing `tsv_device.screen_devices(...)`: unchanged downstream consumer of supplied stress.

## Immediate implementation slice

This round implements section A and the reusable constitutive/extraction parts of section B. It
must not mark any of the ten TSV release-scorecard categories passed. The connected solve should
now be used for mesh/domain convergence before digitized experimental curves are compared.

**Status, 12 July 2026:** section A and the section-B linear assembly are now connected and gated.
The first coarse three-mesh Raman-profile study did not meet the ≤2% requirement (successive changes
were about 28% and 35%), so numerical mechanics correctly remains blocked. The immediate next task
is local refinement plus a declared Raman spatial-averaging operator, followed by finer-mesh and
domain-enlargement studies. Jiang reports sub-micron measurement resolution but does not state an
exact spot width in the paper text, so the averaging width remains benchmark uncertainty rather
than a guessed default. The failed convergence result must remain visible until superseded by a
passing evidence record.

Near-surface distance refinement, consistent L2 recovery, and explicit Gaussian spot sensitivity
are now implemented. On the two finer scaled meshes, the profile difference is still 14.3%, 11.3%,
or 6.9% for assumed spot sigmas 0.08, 0.15, or 0.25 scaled µm, respectively. Because none passes
2% and the exact experimental width is unavailable, these are sensitivity results—not a basis for
selecting 0.25 or advancing the scorecard.

The first boundary study also rejected the finite free-cylinder assumption: enlarging the scaled
radius/depth from 3 to 4 changed the profile by more than 500% with minimal rigid pins. An explicit
`silicon_free_expansion` far-field boundary reduced—but did not remove—the sensitivity: 3→4 changed
54%, and 4→5 changed 18%. The ≤3% domain gate therefore remains open; the next study must enlarge
further and separate radial from depth sensitivity before adopting a canonical local boundary.

That separation is now complete for the scaled sensitivity case. Increasing depth alone from 3 to
4 changes the profile by about 3.1%, while increasing radius 3→4 changes it 59%; subsequent radial
changes remain 15.4% (4→5) and 14.0% (5→6). The lateral boundary dominates. The next validation
geometry should therefore implement Jiang's periodic 40/50 µm cell with symmetry/periodic boundary
semantics, while the isolated-cylinder route remains a separate large-domain benchmark.

**Physics-audit amendment, 12 July 2026:** the original geometry contained an oxide sidewall but no
bottom cap, leaving 41 direct Cu/Si interface nodes across the scaled blind tip. The scene now uses
a true oxide cup and gates zero direct contact. Coordinate/crystal frame, rotation, boundary label,
and material/mesh SHA-256 identities are stored with the result. A full 40/50 µm rectangular cell
with named opposite faces is also implemented. It remains geometry-only:
The matching periodic mesh, node correspondence, exact affine MPC, and declared macroscopic-gradient
API are now implemented. Homogeneous free expansion reproduces machine-zero stress; the zero-jump
fixed-box control produces 29.09 MPa; the heterogeneous solve has reduced residual `1.72e-14` and
zero MPC error. The next increment is to freeze Jiang-equivalent macro/bottom semantics and pass the
anisotropic symmetry plus corrected-scene mesh/recovery convergence gates. All older mesh/domain
numbers above were produced by the superseded sidewall-only topology and must not qualify this scene.

The implementation boundary, affine-reduction equations, proposed CoupFE-core API, edge/corner
handling, validation ladder, and phased rollout are frozen in
[`PERIODIC_BOUNDARY_CONDITION_PLAN.md`](PERIODIC_BOUNDARY_CONDITION_PLAN.md). Implement its serial
core Phase 1 before changing this TSV solver.
