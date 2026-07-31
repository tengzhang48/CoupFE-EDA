# CoupFE-EDA — API reference

The call surface of the `eda_multiphysics` package. Everything is built on the **CoupFE
operator contract** (`residual`/`tangent`/`commit`, `newton_solve`, `complex_step_tangent`);
this project adds the meshing, BCs, materials, elements, drivers, and validation *gates* —
the per-problem glue CoupFE deliberately does not own. Detailed results: `eda_multiphysics/
RESULTS.md` (single-process) and `eda_multiphysics/DISTRIBUTED.md` (PETSc/MPI).

## Component inventory

The public surface is organized into **12 logical components** backed by **44 top-level Python
modules**. See [`COMPONENTS.md`](COMPONENTS.md) for the authoritative mapping and count rules. The
component count describes architecture boundaries, not equal maturity: use `capabilities.md` and
the relevant validation scorecard before making a claim.

## Conventions

- **Material = a plain dict of published constants.** e.g. the Anand 9-constant set is
  `dict(A, QR, xi, m, s0, h0, shat, n, a, E)`. New alloys are new dicts (`SNPB`, `SAC305`),
  not new code — the solver and the closed-form oracle take the dict.
- **A gate returns `dict(name, ok, detail)`** via `gates._g(...)`. The suite
  includes published/analytic oracles, independent-path comparisons,
  invariants, interface/structural checks, and broken controls; the evidence
  type is stated per gate. `gates.GATES` is the list and `gates.run_all()` runs
  it. See `skills/SKILL.md` for the authoring contract.
- **Fields are scalar-diffusion** (thermal = electrical = electrostatic Laplacian) unless a
  module says otherwise; mechanics modules carry their own elasticity.

## Core fields (`eda_multiphysics.fe`)
- `StructuredQuadMesh(nx, ny, Lx, Ly)` — Quad4 mesh; `.left()/.right()/.top()/.bottom()`
  node sets, `.coords`, `.elems`.
- `solve_field(mesh, cond_elems, source, bc) -> (U, operator, info)` — steady scalar
  diffusion (thermal/electrical/electrostatic) with Dirichlet `bc={node: value}`.
- `electrode_current(operator, U, nodeset)` — reaction-based flux/current through a node set
  (the rigorous way to read total current/charge, not a gradient guess).

## Electrothermal (`eda_multiphysics.electrothermal`, `.electrothermal_chip`)
- `solve_electrothermal(mesh, sigma0, alpha, k, V0, Tsink) -> dict` — staggered Picard
  R(T)↔Joule↔thermal; returns `peakT` etc. Oracle: σV0²/8k one-way self-heating.
- `electrothermal_chip` / `chip_vtu` — the same coupling driven by a caller-supplied,
  lawfully sourced OpenROAD case (the full V–T–u chain); needs the EDA toolchain
  (see `CONTAINER.md`). The composed result is link-checked, not independently qualified.

## Thermomechanics
- `tsv_stress`: `solve_tsv(D_um, dT) -> (...)`, `lame_sigma_r(r, D, dT)`, `sigma_at(rc, s, r)`
  — axisymmetric thermoelastic TSV stress; oracle: the Lamé closed form.
- `thermomech`: bimetal curvature (Timoshenko 1925), thermal-gradient hollow cylinder
  (Timoshenko–Goodier), 2D axisymmetric r–z Quad4 vs Lamé (the element NAFEMS LE11 needs).
- `tsv_device`: the device-impact boundary around a supplied silicon stress tensor.
  `cubic_stiffness_tensor(C11,C12,C44)` and `rotate_fourth_order(C,R)` implement cubic-Si
  orientation; `stress_from_strain` supplies the thermoelastic tensor check;
  `raman_stress_sum_mpa` / `raman_shift_cm_inv` compute the Jiang (001) observable;
  `mobility_change(stress_mpa, carrier, channel_degrees)` implements the signed Ryu
  piezoresistive proxy for [100]/[010]/[110]/[1-10]; `koz_mask` applies a client-selected
  threshold; and `screen_devices(..., source_object_ids=...)` returns stable `DeviceScreen`
  back-annotations with upstream source-object identity, governing TSV identity, coordinates,
  direction, mobility proxy, and violation flag.
- `lame_far_field_stress` supports the realistic-dimension preview only. It is explicitly not the
  anisotropic 0.2-µm-depth free-surface field required for Raman validation. `best_channel_orientation`
  demonstrates a bounded orientation-screening action without making a timing or placement claim.
- `tsv_validation`: `load_benchmark_manifest`, `manifest_sha256`, and `stamp_evidence` enforce
  source/unit/uncertainty/revision provenance. `evaluate_release_scorecard` returns
  `alpha_numerical_prototype` until all ten release categories pass; curvature or Raman failure
  blocks a validated claim.
- `tsv_local_3d`: the anisotropic small-strain Tet4 foundation. `material_voigt` converts
  isotropic or rotated cubic-Si manifests to engineering-Voigt stiffness;
  `assemble_linear_thermoelastic` and `solve_local_tsv(..., boundary_condition=)` assemble/recover
  the full stress tensor; `silicon_far_field_constraints` prescribes silicon free contraction while
  `minimal_rigid` remains an explicitly finite free-body option;
  `raman_scan_points` fixes the physical sampling plane; `sample_element_field` performs
  fail-closed constant-element lookup; `element_to_nodal_field` plus `sample_nodal_field` provide
  explicit volume-weighted recovery/interpolation; `project_element_field_l2` provides a consistent
  P1 projection; `gaussian_spot_quadrature` and `silicon_raman_spot_profile` expose spatial-resolution
  sensitivity with a mandatory user-supplied width; and `silicon_raman_profile` returns the exact
  `sigma_xx + sigma_yy` observable. Every result remains `release_validation=False` until the
  mesh/domain and held experimental gates pass.

## Viscoplastic reliability
- `anand`: the Anand unified model. `SNPB`, `SAC305` (constant dicts), `SAC305_FIG310`
  (published figure-read oracle data); `sat_stress(eps_dot, T, p)` (closed-form saturation),
  `integrate_uniaxial(eps_dot, T, p, eps_max)` (stiff BDF), `thermal_cycle(p, ...)` (JEDEC
  JESD22-A104 cycling → ΔW/cycle, plastic-strain range), `verify()` / `verify_sac305()`.
- `solder_joint`: plane-strain J2 return map (Brent), elastic patch test, volume-averaged
  **Darveaux** life. `creep`: stress-controlled secondary-creep rate (inverse-saturation).
- `anand_3d`: small-strain **3D Hex8 Anand** solder element. `anand_return_map_3d`
  (J2 return map with stable resistance update), `AnandHex8` (stateful CoupFE operator,
  3 displacement DOF/node), `patch_test_3d()`, `solder_joint_cycle_3d()` (driven material point),
  and `solder_joint_bvp_3d()` — a **regular-block boundary-value reference** (multi-element, traction-free
  lateral faces) returning the nonuniform per-element `dW` field + **peak-based** (corner) life.
  `darveaux_life(dW)` (Darveaux two-part model) + `MOTALAB_2013` anchor the SAC305 life to the
  **measured** 4719-cycle benchmark. Gated by 3D return-map saturation, full uniaxial-stress
  transient vs `integrate_uniaxial`, Hex8 patch, SAC305 life, BVP corner-dW gradient, life vs
  measured (±2×), and broken controls (wrong `h0`, no swing, uniform 1-element, 10×-wrong dW).
- `electromigration`: Black's MTTF temperature-acceleration + Blech immortality product.

## Other physics
- `capacitance`: parallel-plate extraction (charge = electrode reaction) vs ε·A/d.
- `thermal_runaway`: saddle-node critical-power tangency (the bifurcation/nonlinear case).
- `transient`: time-domain conduction decay vs the (π/L)²α first eigenmode.

## PDN — electrical (`eda_multiphysics.pdn_graph`, `.pdn_distributed`)
- `pdn_graph.GraphConduction(n, edges, load)` — resistor-network conductance operator on the
  CoupFE contract (serial); validated vs an independent scipy assembly+solve.
- `pdn_distributed` — PETSc/MPI: `build_grid_pdn(n)`, `build_from_spice(path)` (parses
  `write_pg_spice`), `serial_solve(...)` (scipy oracle), `dist_solve(..., rtol, direct)`
  (CG+GAMG iterative, or `preonly`+LU+`superlu_dist` direct). Invariant: serial == N-rank.
  CLI: `mpirun -n N python -m eda_multiphysics.pdn_distributed <grid|file.sp> [--direct]`.

## Capstone pipeline (`eda_multiphysics.reliability_pipeline`)
- `run(case_dir=DEFAULT_CASE, spice=None, *, T_amb, Tcold, D_tsv, r_ko, ngrid, k_si, t_si,
  h_v, nx, ncyc, P_override, solder_profile, qualification_Thi, verbose) -> dict` — the end-to-end design→reliability chain:
  PDN IR → electrothermal ΔT → TSV stress → SAC305 solder life → EM screen, on a
  solver-neutral case. The bundled `cases/synthetic_pdn/` default is project-authored and returns
  every stage metric plus its closed-form resistor-grid voltage cross-check. Caller-supplied
  cases may instead carry a labeled PDNSim voltage reference. Composes `electrothermal_chip`,
  `tsv_stress`, `anand.thermal_cycle(SAC305)` (Syed energy life), and `electromigration`.
  CLI: `python -m eda_multiphysics.reliability_pipeline [case_dir] [pdn.sp]` → prints a scorecard.
  Power provenance is returned explicitly. The default mission-profile solder cycle and Black EM
  acceleration respond to upstream temperature; `solder_profile="qualification"` selects a fixed
  power-independent qualification cycle. Gated by `gate_capstone_pipeline` plus a structural-zero
  and active-handoff broken control.

## 3D-FE solder fatigue (`eda_multiphysics.reliability_3d`)
- `joint_map.JointMap` is the validated schema-v1 package-location object; `load_joint_map(csv,
  metadata_path=None)` reads `joints.csv` plus sibling `joints.meta.json`, converts coordinates and
  optional dimensions to microns, applies the declared affine transform into the die frame, and
  rejects ambiguous units, singular transforms, invalid geometry, unsupported fidelity labels, and
  duplicate stable IDs. `geometry_fidelity` is explicitly `proxy`, `design_export`, `calibrated`,
  or `qualified`; it exposes `xy_um` and
  neutral-point distances through `dnp_um`.
- The capstone's stress link upgraded to **3D FE on generated joint geometry**: a gmsh solder joint under the
  thermal-cycling **DNP** displacement (`du = dalpha*dT*L_D`) → the 3D thermo-mechanical FE shear →
  the validated **Anand** SAC305 cycle → **Syed** energy life. `solve_solder_joint(du, R, h, ...)`
  (gmsh cylinder/profiled Hex8 joint, FieldSplit+rigid-body PC), `element_strain` (per-Hex8 centroid strain
  tensor), `_equiv` (von Mises). `main()` reports: FE shear vs `du/h` (8%), dW/cycle (mesh-objective,
  MPa), N_f (Syed; an **in-sample calibration reproduction within ±2×** of the measured Motalab
  4719-cycle case, not independent validation). Global-local
  (elastic 3D FE + material-point viscoplastic). `critical_joint_bvp_life(spice, ...)` upgrades the
  critical joint to a **stateful 3D Anand reference BVP** (`anand_3d.solder_joint_bvp_3d`, regular
  cuboid mesh with traction-free lateral faces → corner-peak dW).
- `mesh3d.solder_bump(R_pad, R_mid, L, h)` builds a connected all-Hex8 barrel, hourglass, or
  cylindrical Gmsh/OpenCASCADE solid with cap/lateral boundary sets, profile metadata, and volume.
  `solve_solder_joint(..., joint_shape=, R_mid=)` and `from_design(..., joint_shape=, R_mid=)` wire
  that profile into the elastic/global-local fatigue bridge. The cylinder remains the default
  compatibility oracle. See [`GEOMETRY.md`](GEOMETRY.md).
  CLI: `python -m eda_multiphysics.reliability_3d [design] --shape barrel|hourglass`.
- `mesh3d.solder_package(...)` builds a conformal six-region native-Tet4 local model with named
  solder, underfill, top/bottom UBM, and top/bottom pad arrays; exact OCC volumes; external pad
  boundaries; and shared interface-node sets. `solve_solder_package_joint(du, ..., materials=)`
  assigns one thermo-mechanical `ElementGroup` per region and solves pad-to-pad DNP shear. Defaults
  are representative stiffness ratios for sensitivity, not qualified properties.
- `from_design(..., include_package=True, package_geometry=, package_materials=, package_mod=)`
  drives the per-joint life map from solder strain in the package-region solve. CLI:
  `python -m eda_multiphysics.reliability_3d design --shape barrel --package`; add
  `--joint-map path/to/joints.csv` to override the case map.
- **Geometry-driven bridge:** `design_joints(spice, joint_map_path=None)` prefers an explicit
  versioned joint map and returns coordinates, neutral point, DNP, stable IDs, optional dimensions,
  source-object IDs, coordinate frame, and provenance. If no map exists, `design_grid(spice)` parses
  PDNSim `NET_x_y_layer` nodes and the result is labeled `pdn_node_proxy_fallback`. `from_design(...,
  joint_map_path=...)` and `critical_joint_bvp_life(..., joint_map_path=...)` propagate the source and
  IDs into their scorecards. The bundled nine-row map is an explicit
  `project_authored_synthetic_joint_map` proxy, not a package bump export; it preserves a
  deterministic 60×60 µm footprint and 42.426 µm maximum-DNP regression invariant. Optional per-row
  diameter/height values are normalized and returned for downstream selection, but the current
  critical-joint solve still uses its explicit `R` and `h_solder` analysis parameters.
- `design_joints()` returns the provenance contract `joint_ids`, `source_object_ids`, `source`,
  `geometry_fidelity`, `coordinate_frame`, `explicit`, and `path` beside `xyz`, `neutral_point`, `dnp`, `diameter_um`,
  and `height_um`. `from_design()` propagates these as `joint_ids`, `joint_source`,
  `joint_map_explicit`, `joint_geometry_fidelity`, `coordinate_frame`, and `joint_map_path`. Consumers should back-annotate by
  stable ID and must not infer fidelity from `explicit=True`; inspect `joint_source` because an
  explicit map may intentionally be a proxy. This contract supports CoupFE-EDA's niche—traceable
  EDA-to-local-reliability analysis—rather than claiming general package-data qualification.
- The all-viscoplastic `anand_3d` element stores Anand plastic strain/resistance at Gauss points and
  computes dW directly through the FE operator/commit path. It is pure Python/small-mesh today
  (elastic modified-Newton tangent — slow beyond ~tens of elements) and is **now wired into
  `reliability_3d`** via `critical_joint_bvp_life`. A compiled/distributed implementation (a
  consistent tangent for real Newton) is the next step to scale it beyond small BVPs.

## Electro-thermo-viscoplastic study (`eda_multiphysics.etv_solder`) — Phase 1
- `solve_et(mesh, V_bc, *, sigma0, alpha_sig, k, T0, T_bc, h_vol, T_amb, ...)` — coupled steady
  electro-thermal solve (σ(T)↔Joule↔thermal) via staggered Picard on the CoupFE contract.
- `verify_selfheating(...)` — the rigorous oracle: the exact 1D self-heating limit dT=σV0²/8k.
- `crowding_factor(*, n, post_frac, pad_frac, ...)` — corner current-crowding factor (peak/avg)
  for a bump; reproduces Dandu 2010's "~10×" (corner J is singular → reported at a fixed mesh).
- `dandu_bump()` — the benchmark application (factor + peak J for the 1.7 A chain current).
- `staggered_baseline(*, dT_cyc, dalpha, ncyc)` — Phase 2: the one-way (T prescribed →
  downstream SAC305 Anand) ΔW/cycle baseline. `joule_density(j_avg)` — q = ρj².
- `etv_cycle(*, coupled, q_joule, g_th, ...)` — Phase 3: the unified material-point cycle;
  `coupled=False` is staggered, `coupled=True` is monolithic (local T evolves with Joule +
  inelastic self-heating). `coupling_effect(...)` — Phase 4: monolithic-vs-staggered ΔW delta
  (the finding: <0.1% quasi-static, ~4% as τ/period→1). See the ETV plan. Gated by `gate_etv_*`.

### FE refinement (`eda_multiphysics.etv_fe`)
- `CoupledET(mesh, *, sigma0, alpha_sig, k, h_vol)` — a **monolithic** electro-thermal Q4
  element (2 DOF/node: φ, T) as a CoupFE `Operator`; the φ–T coupling tangent comes from
  `complex_step_tangent` (no hand-coded Jacobian), solved as one `newton_solve` block.
- `solve_coupled_et(mesh, *, dirichlet, ...) -> (phi, Trise, n_iters)`;
  `verify_selfheating_fe()` (vs σV0²/8k, exact); `consistency_vs_staggered()` (== Picard).
  Stage B: `etv_fe_cycle()` couples the validated Anand plane-strain FE mechanics to transient
  thermal lag and reproduces the τ/period finding on a mesh. Gated by `gate_etv_fe_*`.

### Compiled + distributed (`eda_multiphysics.etv_kernel`, `.etv_distributed`)
- `etv_kernel.build_et_kernel(workdir, *, sigma0, alpha, k)` — generate (via `coupfe.codegen`) and
  f2py-compile the coupled electro-thermal Q4 element from its weak form (`ElectroThermalProblem`),
  returning the compiled module. Drive it batched with `CompiledElement` + `ElementGroup` (no Python
  element loop). `python -m eda_multiphysics.etv_kernel` validates vs σV0²/8k (2e-16).
- `etv_distributed` — drives the compiled kernel through `coupfe.assembly.distributed.solve_distributed`
  (PETSc/MPI, ASM+GMRES). The 2D Quad4 driver exists; its old 526k/32-rank correctness and
  strong-scaling record lacks retained raw/environment evidence and is not a release claim.
- `etv_fieldsplit` — serial PCFIELDSPLIT (GAMG per φ/T field). Its old size/iteration table is
  historical and unqualified. `etv_distributed_fs` — the **distributed** FieldSplit
  driver (`solve_distributed` is single-field). **Loop-free vectorized assembly** (node-aligned row
  partition + owned-row CSR via scipy + `createAIJ(csr=)`; not `setValuesCOO`, a confirmed upstream
  PETSc bug — see `docs/petsc_coo_gamg_bug_repro.py`); per-rank locally-owned field IS + full-load
  Newton. Correctness is regression-checked at 2 and 4 ranks. The historical 5M-DOF 4→48 timing
  table lacks retained raw/environment evidence and is not a public-release performance claim.
  `etv_3d` — the same weak form as a **Hex8** (3D) kernel. Its current oracle and
  solver-control gates pass; historical timing/scale records remain unqualified. All need gfortran+meson+ninja (venv bin on
  PATH); the synthetic-grid solves are solver-capability demos (`docs/capabilities.md`).
- `tet_element` / `tet_3d` — the **Tet4** linear tetrahedron, an element family intended for
  complex/imported CAD but currently qualified only on generated box/cylinder/package meshes.
  It is consumed from CoupFE core (`tet4`/`tet4r` in `ELEMENT_CONFIGS`; use
  `build_et_kernel(element="Tet4")`). `mesh3d.tet_box`/`tet_cylinder` mesh
  with tets; `tet_3d` validates `σV0²/8k` on a tet box **and cylinder** (~2%, converging) plus a
  machine-precision linear patch test with native Core Tet4
  (`docs/TET_FEASIBILITY.md`). Those current gates pass on the selected public Core pin; a named
  imported-CAD adapter remains outside the qualified path.

### Generated device-relevant 3D geometry via gmsh (`eda_multiphysics.mesh3d`, `.tsv_3d`)
- `mesh3d` — thin glue over **gmsh** (the mesher; `pip install gmsh meshio`), NOT a hand-rolled
  generator. `via_cylinder(R, L, h)` → dict(coords, elems, cap0, capL, lateral): an all-hex
  cylinder (gmsh OCC + `SubdivisionAlgorithm=2`) with boundary node sets classified by OCC surface.
  `via_annulus(a, b, L, h)` → dict(coords, core, annulus, cap0, capL, outer): a **conformal
  two-material** concentric via (`fragment`-ed at r=a). `layer_stack(thicknesses, W, h)` →
  dict(coords, layers, bottom, top, H, bounds): a stacked-slab **multi-layer** solid (one Hex8
  array per layer). `min_signed_jacobian(coords, elems)` — Hex8 mesh-validity self-check (>0 ⇒
  valid, gmsh node order compatible with our element, no remap).
  `solder_bump` adds profiled Hex8 joints; `solder_package` adds the conformal six-region Tet4
  package model. `tsv_device_submodel(..., h_near_um=, refine_extent_um=)` adds the blind
  Cu/SiO2/Si Tet4 scene with a true oxide sidewall-plus-bottom cup, optional distance-based
  near-surface refinement, named boundaries, shared interfaces, a zero-direct-Cu/Si gate,
  exact/meshed volumes, stable TSV identity, coordinate/crystal-frame provenance, and explicit
  Raman-plane and material-tip metadata. `tsv_periodic_cell(...)` adds the full 40/50 µm Jiang
  rectangular-cell geometry with `[110]/[-110]/[001]` axes, Gmsh-matched opposite faces, verified
  one-to-one node pairs, and periodic-box provenance. Geometry returns
  `periodic_pairing_status="matching_nodes_verified"` and `periodic_mechanics_status="not_solved"`.
  `solve_local_tsv(..., boundary_condition="periodic_macro_gradient", macro_gradient=H)` consumes
  CoupFE's exact affine MPC and records its hash, constraint error, pair mismatch, reduced DOF count,
  and macro gradient. The macro gradient is mandatory; no fixed-box default is hidden. This consumer
  currently uses the serial reduced solve. CoupFE's separate bulk/history-free MPI reference is
  1/2/4-rank gated, but its replicated setup/final lift and the absence of a TSV rank gate mean this
  API does not claim distributed TSV mechanics.
  `min_signed_tet_volume(coords, tets) > 0` is the Tet4 quality invariant.

  **Maturity:** matching geometry and the serial consumer are implemented foundations. Core's
  bulk/history-free MPI reference is separately rank-gated, but `solve_local_tsv` remains serial.
  Source-equivalent Jiang macro/bottom semantics, corrected-scene convergence, distributed TSV
  execution, and experimental validation remain open. See `docs/PERIODIC_MPC_STATUS.md` for the
  evidence ledger and exact boundary of support.

  The blind-TSV geometry contract is fail-closed: an incomplete oxide cup raises instead of
  returning a mesh, `direct_copper_silicon_nodes` must be empty, `copper_tip_z_um` and
  `liner_tip_z_um` expose the bottom-cap thickness, and the result records the boundary label,
  coordinate frame, proper crystal rotation, and material/mesh SHA-256 identities. These fields are
  debugging inputs, not decorative metadata. When a field is surprising, check geometry/material
  adjacency, equations and constitutive assumptions, units/reference temperature, loads and
  boundaries, axes and measurement setup, then mesh/recovery and code—in that order.
- `tsv_3d` — the 3D Hex8 coupled element on **gmsh-meshed, generated
  device-relevant geometry**:
  `solve_via` + `oracle` (solid via vs heat-generation `σ₀V²R²/4kL²`);
  `solve_annular_via` + `oracle_annular` (multi-material core/annulus vs composite cylinder
  `q a²/4k_core + q(b²−a²)/4k_ann`); `solve_layer_stack(specs=[(t,k),...], ...)` + `oracle_stack`
  (die/underfill/solder/substrate vs 1D series resistance `T_top·R(z)/R_tot`, one `ElementGroup`
  per layer). Curved-geometry rel ~1e-3 (converges); the aligned stack is nodally exact (4e-16).
  `python -m eda_multiphysics.tsv_3d [h | annular [h] | stack [h]]`. These
  canonical-geometry 3D FE demonstrations need gmsh and the gfortran toolchain.

### Thermo-mechanical element (`eda_multiphysics.thermomech_kernel`, `.thermomech_3d`)
- `thermomech_kernel` — a **monolithic 3D coupled u+T Hex8** codegen element (4 dof/node:
  u_x,u_y,u_z,T), the coupling tangent by complex step. `ThermoElasticMaterial` (compressible
  neo-Hookean + isotropic thermal pressure −KαT + Fourier conduction), `ThermoElastic` WeakForm
  (`momentum_equation` + `transport_equation`), `build_thermomech_kernel(workdir, element="Hex8")`,
  `free_expansion_lambda(dT, G, K, alpha)` (the stress-free stretch root). Verified vs the codegen
  reference assembly. Promotes the 2D/axisymmetric thermo-elastic work (`tsv_stress`, `thermomech`)
  to a compiled 3D element.
- `thermomech_3d` — `solve_thermomech(n, dT, props, constrained=...)` (serial Newton). Validated vs
  the material's exact closed forms at uniform ΔT: **free expansion** `u=(λ−1)X` (linear → Hex8
  exact, 2e-13) and **constrained block** `u=0, σ=−KαΔT` (the broken control).
  `python -m eda_multiphysics.thermomech_3d`.
- `thermomech_tsv` — the element on a **generated gmsh Cu/Si annular via** = the TSV
  thermal-mismatch stress on canonical geometry. `solve_tsv_thermal_stress(h, mc, ma, dT, ...)`
  (multi-material neo-Hookean, plane strain, traction-free wall); `composite_ur`/`composite_constants`
  /`interface_radial_stress` (the exact plane-strain **composite-cylinder** oracle — the neo-Hookean
  small-strain limit is linear thermo-elasticity with μ=G, λ=K, β=Kα); `profile_error` (robust
  binned-bulk-RMS metric — a plain max is dominated by near-axis nodes). u_r matches to ~1e-3
  (converging). `solve_tsv_thermal_stress(..., solver="fieldsplit")` uses a
  **FieldSplit research path**
  (`_fieldsplit_tm_solve`: PCFIELDSPLIT splitting u from T, GAMG on the displacement block seeded
  with the **rigid-body near-null-space** via `MatNullSpace.createRigidBody`, jacobi on the
  prescribed-T block). Historical local iteration observations are not retained
  release evidence; rerun the final revisions before making a scalability or
  backend-comparison claim. `python -m eda_multiphysics.thermomech_tsv`
  exercises validation plus a direct-vs-FieldSplit research comparison.

## Shared solve driver (`eda_multiphysics._coupled_solve`)
- `coupled_newton(groups, ndof, dirichlet, linsolve, *, maxit, tol) -> (U, n_newton, info)` — the one
  serial coupled-Newton loop used by `etv_3d`, `thermomech_3d`, `thermomech_tsv`, `reliability_3d`
  (set Dirichlet → assemble R,K → `linsolve` → update → ‖dU‖). `linsolve(K_csr, R, drows) ->
  (dU, info)` is the pluggable backend (the only per-problem difference); `info` also carries
  `t_asm`/`t_solve`. `direct_linsolve` = scipy SuperLU + symmetric Dirichlet; FieldSplit backends
  (scalar / rigid-body) are local closures in each module. Multi-material = a list of `ElementGroup`s.

## Validation surface (`eda_multiphysics.gates`, `.run`; `tests/`)
- `gates.GATES` — the list of gate callables; `gates.run_all() -> [dict(name, ok, detail)]`.
- `_g(name, ok, detail)` — the gate result constructor.
- `python -m eda_multiphysics.run` — runs all 53 fast gates (~30 s here, numpy/scipy/coupfe only),
  exit-nonzero on failure (the container's build-time trust check). `pytest eda_multiphysics` — the
  same gates as a suite; a bare `pytest` is fast too (toolchain excluded by default via `addopts`).
- **Toolchain tier** (`tests/test_toolchain.py`, `pytest -m toolchain`): 19 regression tests for the
  compiled 3-D / thermo-mechanical / reliability modules (gmsh + petsc4py + gfortran; `importorskip`).
  They assert the documented mix of analytic oracles, independent comparisons, geometry/structural
  contracts, serial-versus-rank checks, and the FieldSplit `ksp_its` bound. Frozen numerical targets
  are listed in `docs/REFACTOR_CONTRACT.md`. Build-once kernel fixtures live in
  `tests/conftest.py`. Theory for all models: `docs/theory.md`.

## CoupFE contract used (for reference)
`from coupfe import newton_solve` (and the operator protocol). This project never modifies
CoupFE; it only consumes the contract. Install both editable via `setup.sh`.
