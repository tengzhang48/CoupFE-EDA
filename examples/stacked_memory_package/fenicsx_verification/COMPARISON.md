# CoupFE vs independent FEniCSx reference - 0.45 mm mesh

Same P1 Tet4 mesh (88,154 nodes / 355,233 tets), same declared materials, loads and
boundary conditions, same reporting definitions; two independently written solvers.

**Overall: agreement within the predeclared tolerances**

Predeclared tolerances (fixed before the comparison was run): nodal fields 1e-05, cell fields 1e-05, scalar metrics 1e-04 relative.

## Reported metrics

| Case | Metric | CoupFE | FEniCSx | Difference | Relative error | Tol |
|---|---|---|---|---|---|---|
| baseline | peak_active_die_C | 76.2081546 | 76.2081546 | +0.000e+00 | 0.00e+00 | 1e-04 |
| baseline | peak_all_C | 76.2081546 | 76.2081546 | +0.000e+00 | 0.00e+00 | 1e-04 |
| baseline | top_removed_W | 15.3010683 | 15.3010683 | -1.972e-13 | 1.29e-14 | 1e-04 |
| baseline | board_removed_W | 0.698931696 | 0.698931696 | +3.020e-14 | 4.32e-14 | 1e-04 |
| baseline | substrate_warpage_um | 3.9056129 | 3.9056129 | +1.955e-11 | 5.01e-12 | 1e-04 |
| baseline | active_die_p95_vm_MPa | 9.97487486 | 9.97487486 | +7.176e-12 | 7.19e-13 | 1e-04 |
| baseline | active_die_mean_vm_MPa | 5.07015231 | 5.07015231 | +4.515e-12 | 8.91e-13 | 1e-04 |
| baseline | active_die_max_principal_MPa | 27.6969252 | 27.6969252 | +2.360e-11 | 8.52e-13 | 1e-04 |
| baseline | max_displacement_um | 7.60066983 | 7.60066984 | +2.182e-09 | 2.87e-10 | 1e-04 |
| improved | peak_active_die_C | 60.5363633 | 60.5363633 | -8.029e-13 | 3.91e-14 | 1e-04 |
| improved | peak_all_C | 60.5363633 | 60.5363633 | -8.029e-13 | 3.91e-14 | 1e-04 |
| improved | top_removed_W | 15.5647964 | 15.5647964 | -8.633e-13 | 5.55e-14 | 1e-04 |
| improved | board_removed_W | 0.435203567 | 0.435203567 | +5.551e-17 | 1.28e-16 | 1e-04 |
| improved | substrate_warpage_um | 1.90072085 | 1.90072085 | +1.431e-11 | 7.53e-12 | 1e-04 |
| improved | active_die_p95_vm_MPa | 6.53607373 | 6.53607373 | +1.694e-12 | 2.59e-13 | 1e-04 |
| improved | active_die_mean_vm_MPa | 3.54179115 | 3.54179115 | +3.146e-12 | 8.88e-13 | 1e-04 |
| improved | active_die_max_principal_MPa | 18.4823157 | 18.4823157 | +2.487e-11 | 1.35e-12 | 1e-04 |
| improved | max_displacement_um | 4.84969507 | 4.84969508 | +1.645e-09 | 3.39e-10 | 1e-04 |
| both | peak_die_reduction_C | 15.6717912 | 15.6717912 | +8.029e-13 | 5.12e-14 | 1e-04 |
| both | warpage_ratio_baseline_over_improved | 2.05480615 | 2.05480615 | -5.186e-12 | 2.52e-12 | 1e-04 |

## Full fields

| Case | Field | Max abs error | Scale | Max rel error | RMS rel error | L2 rel error | Tol |
|---|---|---|---|---|---|---|---|
| baseline | temperature_C | 2.046e-12 | 36.2082 | 5.65e-14 | 1.21e-14 | 2.15e-14 | 1e-05 |
| baseline | displacement_m | 3.126e-15 | 7.60067e-06 | 4.11e-10 | 1.11e-10 | 4.64e-10 | 1e-05 |
| baseline | von_mises_MPa | 1.642e-09 | 53.7505 | 3.05e-11 | 6.85e-13 | 5.71e-12 | 1e-05 |
| baseline | stress_MPa | 3.105e-09 | 63.2205 | 4.91e-11 | 3.75e-13 | 8.62e-12 | 1e-05 |
| baseline | principal_max_MPa | 1.192e-09 | 77.4359 | 1.54e-11 | 4.21e-13 | 6.64e-12 | 1e-05 |
| baseline | substrate_detrended_w_um | 3.690e-11 | 2.74854 | 1.34e-11 | 4.65e-12 | 1.70e-11 | 1e-05 |
| improved | temperature_C | 1.023e-12 | 20.5364 | 4.98e-14 | 2.21e-14 | 3.51e-14 | 1e-05 |
| improved | displacement_m | 2.340e-15 | 4.8497e-06 | 4.83e-10 | 1.30e-10 | 4.49e-10 | 1e-05 |
| improved | von_mises_MPa | 1.210e-09 | 32.445 | 3.73e-11 | 8.51e-13 | 6.95e-12 | 1e-05 |
| improved | stress_MPa | 2.283e-09 | 38.2799 | 5.96e-11 | 4.63e-13 | 1.04e-11 | 1e-05 |
| improved | principal_max_MPa | 8.741e-10 | 46.8213 | 1.87e-11 | 5.22e-13 | 7.94e-12 | 1e-05 |
| improved | substrate_detrended_w_um | 2.769e-11 | 1.40149 | 1.98e-11 | 6.82e-12 | 2.78e-11 | 1e-05 |

## Per-body temperatures (all 90 bodies)

- **baseline**: worst body temperature relative error 5.51e-14 (`bga.1.2`), scaled by the peak temperature rise.
- **improved**: worst body temperature relative error 4.91e-14 (`bga.5.3`), scaled by the peak temperature rise.

## Ordering and locations

- **baseline**: peak active-die node 57850 vs 57850; peak active-die von Mises cell 287560 vs 287560; substrate top node set identical: True.
- **improved**: peak active-die node 57853 vs 57853; peak active-die von Mises cell 287560 vs 287560; substrate top node set identical: True.

## Solver-reported linear residuals

| Solver | Case | Thermal free residual | Mechanical free residual |
|---|---|---|---|
| CoupFE | baseline | 7.33e-13 | 5.77e-14 |
| CoupFE | improved | 6.36e-13 | 4.66e-14 |
| FEniCSx | baseline | 4.03e-13 | 2.65e-14 |
| FEniCSx | improved | 3.52e-13 | 2.03e-14 |

## Cross-residual check (`cross_residual_check.py`)

Each solver's field substituted into the *FEniCSx reference's own* discrete equations, normalised by that reference's load over the unconstrained dofs.

| Case | Equation | CoupFE field | FEniCSx field |
|---|---|---|---|
| baseline | thermal | 7.97e-13 | 4.96e-13 |
| baseline | mechanical | 5.72e-14 | 2.65e-14 |
| improved | thermal | 6.97e-13 | 4.30e-13 |
| improved | mechanical | 4.58e-14 | 2.03e-14 |

Both computed solutions satisfy the independently assembled reference equations with small residuals. This is consistent with roundoff amplified by conditioning; it does not measure a condition number or prove equality of the full matrices. It does not establish the physical validity of the model.


## Independent absolute checks in the FEniCSx reference

- unit-cube Fourier flux error 4.44e-16 W against the exact 2 W,
- free thermal expansion relative error 3.53e-15 against u = alpha dT x,
- fully constrained thermal stress error 0.00e+00 Pa against the exact -3.25e+06 Pa,
- recomputed tetrahedron volumes vs the input array: max relative difference 2.34e-14, 0 non-positive orientations,
- DOLFINx node coordinates vs input after ID mapping: max error 0.0e+00 m, connectivity one-to-one: True,
- 3704 of 106920 exterior facets matched to the supplied top face set, integrated Robin area 3.240000000e-04 m^2 (relative error 1.2e-13 against the 18 mm x 18 mm lid).

## Scope

Two independent implementations of one declared linear synthetic model on the same P1 Tet4 mesh. Agreement here is evidence about numerical implementation only: not real-device validation, not mesh convergence, not plasticity, and not verification of the physical package model or of its synthetic material data.

Provenance: mesh `635773e2dca195bc...`, geometry `183fff442917898b...`; FEniCSx 0.10.0 / PETSc 3.25.5; CoupFE core `e2f42ed57728`, EDA `3f78bab4c8b6`.
