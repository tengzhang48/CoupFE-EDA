# Independent FEniCSx reference for the stacked-memory package

An independently written FEniCSx (DOLFINx 0.10.0) solve of the same declared model as
`../solve_thermal.py` + `../solve_mechanics.py`, on the same mesh, plus a field-by-field
comparison of the two solvers.

Both designs (top-TIM k = 1 and k = 5 W/(m K)) are solved and compared on the 0.45 mm mesh.
Result: **agreement to <= 4.8e-10 relative on every full field and <= 3.4e-10 relative on
every reported metric**, against predeclared tolerances of 1e-5 and 1e-4. See
[`COMPARISON.md`](COMPARISON.md), [`comparison.json`](comparison.json) and
[`comparison.png`](comparison.png).

## What this is and is not

The two codes share the mesh, the declared material data, the loads, the boundary
conditions and the reporting definitions. Independently implemented pieces include the weak
forms, kernel generation, assembly, constraint handling and linear solve. Both use P1 Tet4
discretization. The comparison checks **numerical implementation** of this declared model.

It is therefore evidence that the two implementations of that model agree. It is **not**:

- validation against a real device or measured data (the geometry, the stackup and the
  material values are synthetic and have not been physically qualified),
- a mesh convergence or discretisation-accuracy study (the same P1 Tet4 mesh is used on
  purpose, so the discretisation error is common to both and cancels),
- verification of the physical modelling choices (a lumped Robin lid coefficient, no
  contact resistance, no temperature-dependent properties, no TSVs or microbumps),
- anything about plasticity, creep, cure stress, delamination, fatigue or life; solder is
  linear elastic in both codes.

Small residuals alone are not evidence of a correct model. The reference therefore also
carries absolute checks that do not depend on the other solver (below).

## Independence of the implementation

`fenicsx_reference.py` imports only the standard library, `numpy`, `dolfinx`, `ufl`,
`basix`, `petsc4py` and `mpi4py`. It does not import `coupfe` or `eda_multiphysics`, does not load
any generated kernel, does not reuse any matrix or load vector, and does not read any
original result field. The reference mechanical solve is driven by the reference thermal
solution only.

`compare_solvers.py` and `cross_residual_check.py` are the comparison-stage scripts and the
only ones here that open the original `*_fields.npz` / `*_mechanics.npz` outputs.

## Physics solved

Thermal (steady, isotropic Fourier, solved for `theta = T - 40 C`):

- k [W/(m K)]: organic 0.8, attach 1.5, silicon 120, mold 0.8, copper 390, solder 50;
  `top_tim` 1.0 (`baseline`) or 5.0 (`improved`) - the only varied parameter.
- Source: uniform volumetric power per powered body, `P_body / V_body,meshed`, integrated
  as a consistent P1 load. 17 powered bodies, 8 W logic die + 16 x 0.5 W memory dies = 16 W.
- Bottom: `theta = 0` on the supplied bottom faces. Top: Robin `h = 4000 W/(m^2 K)`
  against the 40 C reservoir on the supplied top faces. All other faces adiabatic.

Mechanical (one-way, small-strain isotropic linear thermoelasticity, stress free at 40 C):

- `sigma = 2 mu (eps - alpha theta I) + lambda tr(eps - alpha theta I) I`, with the thermal
  term integrated against the P1 reference `theta`.
- E [GPa], nu, linear CTE [1/K]: organic (20, 0.30, 16e-6), silicon (130, 0.28, 2.6e-6),
  attach (1, 0.35, 40e-6), mold (18, 0.30, 12e-6), copper (110, 0.34, 17e-6),
  solder (40, 0.35, 22e-6), top_tim (0.05, 0.35, 60e-6).
- Restraint: 3-2-1 corner anchors only, at (-0.011, -0.011, -0.001) m fixing x, y, z,
  (0.011, -0.011, -0.001) m fixing y, z and (-0.011, 0.011, -0.001) m fixing z. Every other
  face is traction-free. No clamps, no applied tractions.
- One LU factorization is reused for both load cases.
- Stress is reported at cell centroids on the original Tet4 cells; no nodal smoothing.

Discretisation: P1 Lagrange on the supplied Tet4 mesh (88,154 nodes, 355,233 cells on the
0.45 mm mesh; 90 bodies, 7 materials). Materials, conductivity and the volumetric source are DG0 cell
fields. Every integrand here is at most degree 2 and is integrated with
`quadrature_degree = 2`, i.e. exactly. Serial `COMM_SELF` assembly, PETSc LU with MUMPS.

## Run it

First run the CoupFE example on the mesh to compare, for example
`python examples/stacked_memory_package/run.py --mesh-size 0.45`. Then, with a Python that
has DOLFINx 0.10 (real PETSc scalars, MUMPS), from this folder:

```bash
# 1. independent reference solve, both designs (about 20 s and 3 GiB on the 0.45 mm mesh)
OMP_NUM_THREADS=4 python -u fenicsx_reference.py --mesh-dir ../runs/h0.45 --out results

# 2. substitute each solver's field into the reference's own discrete equations
python -u cross_residual_check.py --mesh-dir ../runs/h0.45 --reference results

# 3. compare against the CoupFE outputs
python -u compare_solvers.py --mesh-dir ../runs/h0.45 --reference results --out .
```

Add `--cases baseline` to solve one design, `--no-figure` to skip the PNG. Each script
overwrites its own outputs only; `results/` is not tracked.

Run-to-run reproducibility was measured, not assumed: the temperature field is bitwise
identical across repeat runs, while the mechanical fields vary by <= 1e-13 relative
(threaded BLAS / MUMPS accumulation order). That scatter is about four decades below the
cross-solver difference, so it does not affect any conclusion.

Retained run environment: Python 3.12, DOLFINx 0.10.0, basix 0.10.0, UFL 2025.2, PETSc 3.25
(real scalars), MPICH, NumPy 2.

## Files

| File | What it is |
|---|---|
| `fenicsx_reference.py` | The independent reference solve: mesh mapping, patch tests, thermal, mechanics, outputs. |
| `cross_residual_check.py` | Substitutes each solver's field into the reference's own discrete equations. |
| `compare_solvers.py` | Field, metric and per-body comparison against the retained CoupFE outputs. Declares its tolerances at the top. |
| `results/fenicsx_result.json` (generated) | Reference metrics, mesh and patch checks, provenance and hashes. |
| `results/{baseline,improved}_fenicsx_fields.npz` | `temperature_C`, `temperature_rise_K` in original node order. |
| `results/{baseline,improved}_fenicsx_mechanics.npz` | `displacement_m`, `stress_MPa`, `von_mises_MPa`, `principal_max_MPa`, `substrate_top_nodes`, `substrate_detrended_w_um`, `residual_N` in original node / cell order. |
| `cross_residual.json` | Cross-residual output, folded into `COMPARISON.md` when present. |
| `COMPARISON.md`, `comparison.json` | Two-solver comparison, actual errors against the predeclared tolerances. |
| `comparison.png` | Relative-error distributions for T, U and von Mises, plus a von Mises parity plot. |
| `reference_run.txt` | Console log of the retained reference run. |

## Mesh identity and ID mapping

DOLFINx renumbers nodes and cells, so the reference maps every output array back to the
original input ordering using `geometry.input_global_indices` and
`topology.original_cell_index`, and refuses to continue unless:

- both maps are permutations of the input IDs,
- the P1 dofmap coincides with the geometry dofmap,
- mapped node coordinates equal the input coordinates **exactly** (0.0 m error),
- mapped cell vertex sets equal the input `tets` rows exactly,
- the integrated DOLFINx volume matches the recomputed input volume (5.6e-13 relative),
- the supplied top triangles match one-to-one onto exterior facets (3,704 of 106,920) and
  the integrated Robin area equals the 18 mm x 18 mm lid footprint (1.2e-13 relative).

Tetrahedron volumes are recomputed geometrically from the nodes and checked against the
supplied `volume_m3`: max relative difference 2.3e-14, no non-positive orientations.

## Absolute checks inside the reference

Run before the package solve, on a 6-tetrahedron unit cube, against closed-form answers:

| Check | Exact | Error |
|---|---|---|
| Fourier flux through a face for k = 2, T = x | 2 W | 4.4e-16 W |
| Free thermal expansion, u = alpha dT x | - | 3.5e-15 relative |
| Fully constrained thermal stress, -E alpha dT / (1 - 2 nu) | -3.25 MPa | 0.0 Pa |

Conservation on the package problem itself: assembled power 16.000000 W in both cases,
`top_removed + board_removed - input` balance error 1.1e-13 relative, free thermal residual
4.0e-13 / 3.5e-13, free mechanical residual 2.6e-14 / 2.0e-14
(baseline / improved), and anchor reactions and net force at round-off level, as expected
for a self-equilibrated thermal load on a 3-2-1 support.

## Headline comparison

| Quantity | CoupFE | FEniCSx | Relative error |
|---|---|---|---|
| Peak active-die temperature, baseline | 76.20815456 C | 76.20815456 C | 0.0e+00 |
| Peak active-die temperature, improved | 60.53636331 C | 60.53636331 C | 3.9e-14 |
| Substrate warpage, baseline | 3.905612899 um | 3.905612899 um | 5.0e-12 |
| Substrate warpage, improved | 1.900720850 um | 1.900720850 um | 7.5e-12 |
| Active-die P95 von Mises, baseline | 9.974874863 MPa | 9.974874863 MPa | 7.2e-13 |
| Active-die P95 von Mises, improved | 6.536073733 MPa | 6.536073733 MPa | 2.6e-13 |
| Worst of all six full fields | - | - | 4.8e-10 |

The temperature-rise scale is 36.21 K (baseline) and 20.54 K (improved); displacement is
scaled by the maximum nodal magnitude. Full tables, per-body temperatures for all 90
bodies, and the ordering / peak-location checks are in `COMPARISON.md`.

Where the remaining ~1e-10 displacement difference comes from: substituting the CoupFE
displacement field into this reference's independently assembled equations leaves a
relative residual of 5.7e-14 (baseline) and 4.6e-14 (improved), the same order as the
reference's own solution leaves (2.6e-14 / 2.0e-14). Both computed solutions satisfy the
reference equations to small residuals. This is consistent with linear-algebra roundoff
amplified by conditioning, but does not measure a condition number or prove equality of
the full matrices. The largest reported metric difference is 3.39e-10 relative, on the
maximum displacement magnitude.
