# Historical snapshot: Validation assessment

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/VALIDATION_ASSESSMENT.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# Code & Validation Assessment

This is an honest, high-level assessment of the `coupfe-eda` codebase and its
validation posture. It is intended to help contributors and reviewers decide
where the code is trustworthy, where more work is needed, and where to invest
next.

## Overall verdict

| Aspect | Rating | Notes |
|---|---|---|
| **Architecture** | Good | Clean module split: scalar operators → 2-D coupled ET → 3-D gmsh/PETSc toolchain → reliability pipeline. Public API contracts are written down. |
| **Test coverage** | Current paired tiers pass | Against public Core `933e497`, the 31 July candidate run passed the standalone 53-gate harness, 94/94 default tests (19 toolchain cases deselected), and the separate 19/19 gmsh/PETSc/MPI/gfortran tier (94 default cases deselected). These checks overlap and qualify only their stated tested scopes. |
| **Validation rigor** | Good-to-Strong | Most key physics have either analytic oracles or published benchmarks. Broken-control / sanity tests are present. |
| **Documentation** | Good | `RESULTS.md`, `REFACTOR_CONTRACT.md`, `VALIDATION_GUIDE.md`, and inline docstrings explain intent. |
| **Code maturity** | Fair-to-Good | Shared coupled drivers are integrated; f2py build remains somewhat manual. |
| **CI / reproducibility** | Fair | Public fast CI runs the standalone 53-gate harness and the current 94-test default tier, which includes those 53 gate wrappers plus 41 additional tests; the 19-case gmsh/PETSc/MPI/gfortran tier remains a release/manual run. Exact Core and OpenROAD revisions are pinned, while conda packages are not lockfile-frozen. |

---

## Assessment by module / test category

| Category | Code quality | Validation strength | Key evidence | Gaps / risks |
|---|---|---|---|---|
| **Scalar diffusion (thermal / ohmic)** | Strong | Strong | Patch tests, Ohm's law, Joule self-heating `σV²/8k` | — |
| **ETV 2-D coupled solver** | Good | Good | Analytic 1-D self-heating; Dandu current-crowding benchmark; monolithic vs staggered consistency | Some solver gates are consistency checks, not independent benchmarks |
| **ETV 3-D (Hex8)** | Good | Good | `solve(16, …)` vs `σV²/8k` | Only one mesh size tested in toolchain; coarser validation only via fast gate |
| **Tet4 foundation for future imported CAD** | Implemented, tested on generated shapes | Current toolchain gates | `σV²/8k` on generated gmsh tet box/cylinder, a linear patch test, and conformal package-region/solve gates pass against native Core `tet4`/`tet4r` | No named STEP/BREP import adapter; broader mesh convergence and production CAD/material qualification remain |
| **TSV 3-D stress** | Good | Strong | Choi et al. (*Materials* 2021) Lamé benchmark to 0.06% | Literature oracle is radial stress only, not full stress tensor |
| **TSV device screening** | Early / Partial | Good foundation | Conformal blind Cu/oxide-cup/anisotropic-Si Tet4 solve with zero direct Cu/Si contact; explicit frame/hashes; exact 0.2-µm extraction; matching 40/50 µm cell plus exact serial MPC and thermal controls; Ryu/Jiang equations; stable-ID demo | Source-equivalent macro/bottom BC is not frozen; corrected-scene convergence and MPI MPC are not run; the preview still uses Lamé; no digitized Raman curves or transistor experiment |
| **TSV 3-D thermal (gmsh)** | Good | Good | Solid cylinder, annular via, layer stack — all analytic | Mesh quality assertions are coarse (`min_jacobian > 0`); no h-convergence in CI |
| **Thermomech 3-D** | Good | Good | Free expansion, constrained block | No external literature benchmark; relies on analytic oracles |
| **Thermomech TSV** | Good | Good | Plane-strain composite-cylinder displacement; direct vs fieldsplit agreement | Tolerance on profile error is relatively loose (`6e-3`) |
| **Anand / solder** | Good | Strong | Integrator vs closed-form saturation; Motalab SAC305 constitutive benchmark; 3D Hex8 saturation/transient/patch; **3D BVP corner-dW gradient**; in-sample reproduction of the Motalab 4719-cycle calibration case within ±2× | SAC305 parameters and life mapping are calibration-dependent; no *blind* multi-package validation |
| **Electromigration** | Good | Good | Black 1969 / JEDEC JEP119 AF; Blech 1976 product | Blech range is order-of-magnitude; no interconnect MTTF distribution check |
| **PDN graph** | Good | Strong vs scipy + closed form | Independent `scipy` assembly and bundled symmetric-grid voltage oracle | No bundled real-design PDNSim comparison; caller cases need separate qualification |
| **Capacitance / transient / creep / runaway** | Good | Good | Analytic oracles for each | Mostly 1-D / idealized geometries; not production-extraction validation |
| **Reliability 3-D** | Fair-to-Good | Fair-to-Good | DNP shear estimate; layout checks on the bundled synthetic `pdn_vdd.sp`; solved 3D Anand BVP for the critical joint (`critical_joint_bvp_life`, corner-peak dW); in-sample life calibration reproduction | `N_f` remains calibration-specific; the BVP is a small mesh (elastic-tangent modified-Newton); array map still uses the global-local proxy |
| **Capstone pipeline** | Demonstration | Bounded integration checks | Direct synthetic PDN closed form and power closure; structural handoff checks plus separately tested Lamé, Anand, Syed/Darveaux, and Black/Blech components | First simple composed demo; no real-design or end-to-end experimental oracle |
| **Distributed PETSc solve** | Implemented | Current checked-size correctness; historical scaling | Serial-versus-MPI checks pass at 2 and 4 ranks in the current toolchain tier | All timing, speedup, efficiency, 1M/5M-size, and larger-rank claims lack retained raw output and a locked environment |

---

## Validation type breakdown

| Type | Count (approx.) | Confidence | Comments |
|---|---|---|---|
| **Analytic closed-form** | ~25 gates/tests | High | Patch tests, Ohm, Joule, Lamé, Timoshenko, capacitance, etc. |
| **Published literature / standards** | ~8 gates/tests | High-to-Medium | Choi TSV, Motalab SAC305, Black/Blech, Bhat runaway, Dandu crowding |
| **Independent solver / code path** | ~5 gates/tests | High | PDN vs scipy, monolithic vs staggered, direct vs fieldsplit, serial vs MPI |
| **Broken controls / sanity checks** | ~10 gates/tests | Medium | Useful for catching sign/source bugs, but do not prove correctness |
| **Synthetic layout / interface checks** | 2 tests | Medium | Bundled `pdn_vdd.sp` capstone and `from_design`; schema and sanity checks, not real-design or experimental validation |

---

## Strengths

1. **Contracts are explicit.** `docs/REFACTOR_CONTRACT.md` freezes public APIs and oracle numbers.
2. **Two-tier testing works.** Fast numpy/scipy gates run in ~40 s; heavy toolchain tests run only when requested.
3. **Multiple validation modes.** A single physics path is often checked by analytic + literature + consistency + broken-control tests.
4. **Honest about limitations.** Checked-in claim boundaries do not present unvalidated outputs as truth.
5. **Good use of published benchmarks.** Choi, Motalab, Timoshenko, Black/Blech, Bhat, Dandu are all named.

## Weaknesses / risks

1. **Calibration-dependent outputs — one measured case is reproduced in sample.** `gate_solder_life_experimental_anchor` reproduces the measured thermal-cycling life of the Motalab (Auburn 2013) 19 mm PBGA (N₆₃ = 4719 cycles, −40/+125 °C) within the stated ±2× band. Because that package is the calibration tie-point, this is a calibration-consistency check, not independent validation of the ΔW→N_f mapping or a blind package prediction. `N_f` remains calibration-specific until held multi-package evidence exists.
2. ~~No h-convergence study in CI.~~ **Closed for the base element:** `gate_h_convergence` verifies bilinear diffusion converges at the theoretical **2nd order (L2, O(h²), observed 2.00)** on a manufactured solution + broken control. (The 3-D toolchain tests still use one mesh size each.)
3. **Toolchain environment is heavy.** `gmsh` + `petsc4py` + `mpi4py` + `gfortran` + `meson/ninja` makes CI setup nontrivial.
4. **Some specialized duplication remains.** Shared coupled drivers are integrated, while a few
   module-specific paths remain intentionally separate.
5. ~~Limited multi-rank distributed testing.~~ **Closed for correctness:** `test_etv_distributed_fs` is now parametrized over **2 AND 4 ranks** (the 4-rank case exercises interior-rank ghost exchange a 2-rank split can't). The 4→48 *timing* sweep remains manual (`scaling_bench`, `DISTRIBUTED.md`).
6. **Figures/oracles are mostly 1-D or axisymmetric.** Complex 3-D geometries (arbitrary PDN, full package) rely on link-by-link validation rather than a closed-form end-to-end oracle.

---

## Suggested next investments

| Priority | Action | Impact |
|---|---|---|
| ✅ done | ~~Add h-convergence study~~ — `gate_h_convergence` (2nd-order O(h²), order 2.00, + broken control) | Discretization now quantified for the base element |
| ◐ partial | Add measured fatigue evidence — `gate_solder_life_experimental_anchor` reproduces the in-sample Motalab 4719-cycle calibration case within ±2×; a blind second package remains open | Ties the selected calibration to one measured case without claiming independent predictive validation |
| ✅ done | ~~Add 4-rank distributed regression test~~ — `test_etv_distributed_fs` now runs 2 & 4 ranks | Catches multi-rank partitioning/ghost bugs |
| High | Containerize the toolchain environment and add CI job for `pytest -m toolchain` | Prevents environment drift; catches petsc4py/MPI regressions |
| Medium | Extend h-convergence to a 3-D toolchain case; blind-validate life on a *second* package | Removes the in-sample caveat on the fatigue anchor |
| Medium | Track code coverage and assert ≥80% on `eda_multiphysics/` | Identifies untested branches |
| Low | Add convergence plots to `docs/validation_guide/` figures | Makes the guide even more educational |

---

## How this assessment was produced

- Current automated inventory: 94 default tests (53 physics-gate wrappers plus 41 additional tests:
  16 integration/CLI, 9 TSV-device, 4 anisotropic local-TSV, and 12 EDA periodic-adapter tests) and
  19 toolchain tests. The TSV
  additions were checked against the primary
  Ryu/Jiang equations; their experimental curves remain explicitly blocked rather than inferred.
- Read `docs/REFACTOR_CONTRACT.md`, `eda_multiphysics/RESULTS.md`, and every gate/test file.
- Cross-checked oracle claims against the cited literature where the title/abstract was accessible.
- Did **not** re-run original published experiments or compare against third-party FE codes beyond
  the independent SciPy checks. Historical PDNSim records are not bundled release evidence.

---

*Recorded assessment baseline: commit `049243c`; current release claims are governed by the
checked-in tests, manifests, and claim boundaries above.*
