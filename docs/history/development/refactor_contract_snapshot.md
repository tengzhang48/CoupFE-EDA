# Historical snapshot: Refactor contract

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/REFACTOR_CONTRACT.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# Toolchain API and oracle contract

This contract freezes the public interfaces and numerical oracles that protect implementation
changes. The toolchain tests are the acceptance gate.

**Rules.**
1. **Public API signatures below are frozen.** Internal functions, loops, and build/caching paths
   may change without changing the documented call surface.
2. **Oracle numbers below are frozen.** They are recorded outputs from commit `1920e6d`. A number
   changes only with a documented, evidence-backed amendment.
3. **Acceptance = `pytest -m toolchain` green on the integrated tree.**

## Frozen public API (do not change signatures)
- `mesh3d`: `via_cylinder(R,L,h)`, `via_annulus(a,b,L,h)`, `layer_stack(thicknesses,W,h)`,
  `solder_bump(R_pad,R_mid,L,h)`, `solder_package(...)`,
  `min_signed_jacobian(coords,elems)`, `min_signed_tet_volume(coords,tets)`
- `tsv_3d`: `solve_via(h,...)`/`oracle`, `solve_annular_via(...)`/`oracle_annular`,
  `solve_layer_stack(specs,...)`/`oracle_stack`
- `thermomech_kernel`: `build_thermomech_kernel(workdir,element=)`, `free_expansion_lambda(dT,G,K,alpha)`
- `thermomech_3d`: `solve_thermomech(n,dT,props,constrained=)`
- `thermomech_tsv`: `solve_tsv_thermal_stress(h,...,solver=)`, `composite_ur`, `composite_constants`,
  `interface_radial_stress`, `profile_error`
- `mesh3d.tsv_device_submodel(...)`: conformal Cu/oxide-cup/Si Tet4 regions, named boundaries,
  zero direct Cu/Si contact, interfaces, volume/quality metadata, stable TSV ID, declared
  coordinate/crystal frame, and explicit tip/Raman coordinates
- `mesh3d.tsv_periodic_cell(...)`: full Jiang 40/50 µm geometry, right-handed
  `[110]/[-110]/[001]` frame, matching Gmsh opposite faces, verified node pairs, box/pair hashes,
  and separate geometry/mechanics statuses
- `tsv_local_3d`: `material_voigt`, `tet4_B_volume`, `assemble_linear_thermoelastic`,
  `solve_local_tsv(boundary_condition=, macro_gradient=)`, `periodic_mpc_setup`,
  `silicon_far_field_constraints`, `raman_scan_points`,
  `sample_element_field`, `element_to_nodal_field`,
  `sample_nodal_field`, `project_element_field_l2`, `gaussian_spot_quadrature`,
  `silicon_raman_profile`, `silicon_raman_spot_profile`; `LocalTSVResult` records boundary/frame,
  proper crystal rotation, material/mesh/constraint SHA-256, constraint error, macro gradient,
  periodic pair mismatch, reduced DOFs, and fail-closed release status
- `reliability_3d`: `solve_solder_joint(du,...)`, `element_strain(coords,elems,U)`,
  `design_grid(spice)`, `design_joints(spice,joint_map_path=)`, `from_design(spice,...)`;
  `joint_map`: `JointMap`, `load_joint_map(csv,metadata_path=)`
- `etv_3d`: `solve(n,props,V0=)`; `etv_distributed_fs`: CLI `main()`
- Internal implementation details (not public API): `_newton_fieldsplit`, `_fieldsplit_tm_solve`, the per-module Newton
  loops, the kernel-build/caching path.

## Frozen oracle numbers (run small/fast; assert within tolerance)
| module | call (fast size) | assertion |
|---|---|---|
| `etv_3d` | `solve(16,(3.0,0.0,1.5))` | peak `U[1::2].max()` == σV0²/8k = 1.0, rel < 2e-3 |
| `tsv_3d` solid | `solve_via(0.18)` | peak vs σ₀V²R²/4kL²=2.0, rel < 6e-3 |
| `tsv_3d` annular | `solve_annular_via(0.18)` | peak vs `interface`/composite, rel < 6e-3 |
| `tsv_3d` stack | `solve_layer_stack([(0.3,1.5),(0.1,0.5),(0.2,3.0),(0.4,1.0)],h=0.18)` | interface temps **max\|err\| < 1e-12** (nodally exact, ~4e-16) |
| `thermomech_3d` | `solve_thermomech(4,dT=10)` | free-exp `max\|u-(λ-1)X\|/max\|u\|` < 1e-9 (≈2e-13) |
| `thermomech_3d` broken | `solve_thermomech(4,dT=10,constrained=True)` | `max\|u\|` < 1e-9 (≈1e-17) — the control |
| `thermomech_tsv` | `solve_tsv_thermal_stress(0.18,solver="fieldsplit")` & `="direct"` | `profile_error` < 6e-3 **and** the two solutions agree rel < 1e-6 **and** fieldsplit `ksp_its` < 40 |
| `etv_distributed_fs` | `mpirun -n 2 ... 24 --validate` | serial==N-rank rel < 1e-6 (≈1e-16) |
| `reliability_3d` joint | `main()` (no args) | FE `gamma` within 15% of `du/h`; `N_f` finite > 0 |
| `reliability_3d` design | `from_design()` on bundled synthetic `pdn_vdd.sp` | 9 joints, extent 60×60 µm, DNP = √1800 µm; `lives.min() < lives.max()`, all finite > 0 |

All toolchain tests are marked `@pytest.mark.toolchain` (need gmsh + petsc4py + gfortran;
`importorskip`), **excluded from the fast suite**, run via `pytest -m toolchain`.

**12 July 2026 amendment:** the original 64×56 µm / 42.5 µm oracle was invalidated by the audited
1000-vs-2000 DBU defect; the then-corrected GCD values were 31.92×28.17 µm and
21.2434 µm DNP. **30 July 2026 amendment:** that third-party-derived fixture was removed and
the current table now freezes the independently authored nine-point synthetic case. A second
additive amendment introduced optional
`joint_shape`/`R_mid` keywords and the `solder_bump` API; the original cylindrical call remains
bit-compatible and frozen. A third additive amendment introduced `solder_package`,
`solve_solder_package_joint`, and `from_design(include_package=True)`; structural, exact-volume,
multi-material-solve, and composed layout tests protect the new path.
A fourth additive amendment introduced the schema-v1 `joints.csv` + `joints.meta.json` API and
optional `joint_map_path` keywords. Explicit maps take priority, all scorecards expose provenance,
and absence of a map retains the old calculation under a labeled PDN-proxy fallback.

## Recorded implementation status

- Toolchain regression coverage was integrated and reported green for the then-current 10-test
  tier under petsc4py 3.25.2.
- Shared-driver deduplication was completed: all four solves (`etv_3d`, `thermomech_3d`,
  `thermomech_tsv`, `reliability_3d`) on the shared `_coupled_solve.coupled_newton` with a local
  linear backend. Verified 41/41 gates at merge time + 10/10 toolchain, every oracle bit-identical.
- `pyproject` uses `addopts = "-m 'not toolchain'"` so a bare `pytest` stays fast.
- **Deferred (documented, not done):** (1) a global kernel-build cache — low value now that the hot
  paths already pass a prebuilt `mod=` (build is once-per-process); a cross-workdir cache adds
  correctness risk for little gain. (2) `reliability_3d` shear-extraction refinement — would perturb
  a validated, contract-pinned number (`gamma` within 15%); it's a refinement, not a bug. Both are
  honest follow-ups, intentionally not rushed.
