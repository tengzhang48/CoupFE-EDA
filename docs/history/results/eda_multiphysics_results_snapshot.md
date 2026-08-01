# Historical snapshot: EDA–multiphysics development results

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `eda_multiphysics/RESULTS.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.
> Local documentation links that no longer resolve in that layout are rebased
> to their current historical or public locations; the narrative is unchanged.

---

# EDA–Multiphysics Prototype — Results & Phase-by-Phase Evaluation

**Status:** experimental. **Date:** 2026-06-24. **Branch:** `eda-multiphysics-integration`.
Companion to `open_source_eda_multiphysics_integration_plan.md` (the plan) and
`open_source_eda_multiphysics_literature_survey.md` (prior art).

> **Public-release boundary (2026-07-30):** this is a historical development record, not a
> release qualification report. AES inputs/raw logs and the former GCD-derived fixture are not
> bundled. Historical GCD/AES measurements below therefore are not reproducible release evidence.
> The current distribution instead ships the project-authored `synthetic_pdn` case; current
> entry-point status is authoritative in
> [`examples/REFERENCES.md`](../../../examples/REFERENCES.md).
> All timing, speedup, efficiency, iteration-count, 1M/5M-size, and larger-rank records below are
> likewise historical context: raw console output and a locked environment were not retained.
> Rerun them on the final public core/EDA revisions before quoting them as release capabilities.
> The current package is one CoupFE-based implementation example, not a
> completed framework or field standard; independent projects may use other FEM
> solvers, couplings, and data models. Real-device validation with traceable
> inputs, retained raw evidence, and measured observables is the primary next
> milestone.

This records an attempt to "go through all phases, test/evaluate, report the most
promising." Selected **solver components (Phases 3–5)** were implemented on the
CoupFE operator contract and checked against the evidence identified below; the
original **EDA front-end assessment (Phases 0–2, 6 back-annotation, 8)** was
blocked in that environment (no OpenROAD/Yosys/KLayout/PDK installed).

## Original development environment

- Present: `gfortran`, `gmsh`, `mpirun`, Python 3.13, `scipy`, `sympy`, `meson`, and `ninja`.
  The original machine path is intentionally not part of the public interface; current users
  should create `environment.yml` and run `./setup.sh`.
- Absent: `openroad`, `yosys`, `klayout`, and the SKY130/Nangate45 PDKs.
- Verified working: pure-Python operator spine (`examples/linear_bar`), and the
  codegen→Fortran path (`examples/scalar_diffusion_uel/build.py` emits the coupled
  u–T UEL) — confirming the "one definition, two homes" mechanism is real.

## What was built (`eda_multiphysics/`)

- `fe.py` — a steady scalar-diffusion Quad4 **operator** (residual = single source of
  truth; tangent by complex step), structured mesh, current/flux post-processing. One
  operator serves **both** electrical and thermal conduction.
- `electrothermal.py` — the **staggered Picard** coupled solver: σ(T) → electrical
  solve → Joule Q=σ|∇V|² → thermal solve → under-relax → repeat. Voltage- or
  current-driven.
- `validate.py` — validation ladder (analytical + independent BVP oracles, broken controls).
- `design_loop_demo.py` — Phase-7 closed-loop "reinforce → verify improvement."

**Trust gates (fast, self-contained — no OpenROAD/case data, ~30 s):**
```
python -m eda_multiphysics.run        # 53 analytic, literature, invariant, interface, and control gates
pytest eda_multiphysics               # same gates as a regression suite
```
**3D / thermo-mechanical / reliability toolchain tier (needs gmsh + petsc4py + gfortran, ~3 min):**
```
pytest -m toolchain
```
The suite mixes published or analytic oracles, independent implementation
comparisons, invariants, interface/structural checks, and broken controls. See
`docs/VALIDATION_GUIDE.md` for each gate's actual evidence boundary.

**Bundled and caller-supplied demonstrations:**
```
python -m eda_multiphysics.validate              # the 11-check electrothermal ladder
python -m eda_multiphysics.case_thermal           # bundled synthetic placement -> thermal map
python -m eda_multiphysics.reliability_pipeline   # bundled synthetic integration scorecard
python -m eda_multiphysics.electrothermal_chip <case> <pdn.sp> <P>   # coupled R(T) on supplied case data
python -m eda_multiphysics.chip_vtu <case> <pdn.sp> <P>              # full V-T-u chain
python -m eda_multiphysics.solder_joint          # viscoplastic FE + Darveaux
```
The first two case-oriented commands run without an EDA installation. Caller-supplied
OpenROAD/OpenDB and PDNSim exports require the external EDA toolchain and input rights.

## Validation results (11/11 pass)

| Case | Oracle | Error | Phase |
|---|---|---|---|
| C1 thermal linear (patch test) | exact T=x/L | 1.7e-15 | 3 |
| C1 broken control (wrong BC) | must fail | rejected ✓ | 3 |
| C2 thermal parabolic, uniform source | nodally exact T=s·x(L−x)/2k | 1.8e-15 | 3 |
| C2 peak T | analytic sL²/8k | 1.3e-15 | 3 |
| C3 Ohm current | sigma·V0·W/L | 4.4e-14 | 4 |
| C3 voltage profile | exact linear | 5.3e-15 | 4 |
| C4 Joule one-way peak ΔT | analytic σV0²/8k | 1.6e-10 | 5 |
| C4 broken control (Q=0) | must fail | rejected ✓ | 5 |
| **C5 coupled peak T** | **independent scipy 1D BVP** | **4.1e-12** | **5** |
| C5 coupled current density | independent scipy 1D BVP | 6.8e-6 | 5 |
| C5 reduces to one-way as α→0 | analytic σV0²/8k | 1.6e-10 | 5 |

**Headline coupling effect** (α=0.6, normalized units): temperature-dependent
resistance reduces delivered current **−4.59%** vs an isothermal analysis; peak ΔT
0.125→0.1206; converged in **16** staggered iterations.

The strongest result is **C5**: a 2D CoupFE staggered solve agrees with a fully
independent 1D boundary-value-problem solver (`scipy.solve_bvp`, different
discretization and code path) to **~4e-12** on the coupled nonlinear electrothermal
peak temperature.

## Phase-7 closed-loop demonstration (fixed current demand)

A locally under-provisioned power strap (0.35× conductance over x∈[0.45,0.55])
creates a Joule hotspot and excess IR drop; "reinforcement" (1.6× conductance =
widen/add vias) is verified by re-solving at the same delivered current:

| Run | peak T | hotspot x | IR drop | current |
|---|---|---|---|---|
| C baseline (weak strap) | 0.18691 | 0.500 | 1.40919 | 1.000 |
| D reinforced strap | 0.12498 | 0.490 | 1.14218 | 1.000 |
| **Δ** | **−33.1%** | — | **−19.0%** | 0% |

→ **Verified improvement: lower hotspot AND lower IR drop at the same current** — the
plan's Phase-7 exit criterion, demonstrated on the solver side.

## Historical external integration (GCD/Nangate45; data no longer bundled)

The original EDA toolchain used OpenROAD 2.0, Yosys, and KLayout in a separate CPython 3.10
environment.
ORFS HEAD's flow scripts break against the Feb-2024 OpenROAD (≈2.3-yr skew), so the
flow was run with **minimal version-appropriate local scripts**:
yosys synth → OpenROAD floorplan/place → `pdngen` (M1/M4/M7) → `analyze_power_grid`.
The exact OpenROAD/ORFS generator revisions were not embedded in the original export and were
later recovered from preserved records. To keep the public distribution unambiguous, all
GCD-derived files were later removed rather than relabeled. ORFS describes and credits the
external [GCD sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd);
the measurements in this section remain historical context only.

**Historical end-to-end pipeline:** OpenROAD → `eda_multiphysics/openroad/export_case.tcl`
(OpenDB → `instances.csv` + `manifest.json`) → the predecessor of
`eda_multiphysics/case_thermal.py` (CoupFE
thermal solve) → temperature map + per-instance back-annotation.

| Quantity | Value |
|---|---|
| Design | GCD on Nangate45, 251 instances, die 36×36 µm |
| PDNSim worst IR drop | 2.83e-5 V (oracle captured: `case/pdnsim_vdd_nodes.csv`) |
| Total power (report_power) | 8.52 µW (leakage-only — no switching activity) |
| CoupFE peak ΔT (real power) | 6.7e-5 K, hotspot (20.0,17.5) µm → instance `_268_` (XNOR2_X1) |
| CoupFE peak ΔT (5 mW scaled) | 0.039 K, same hotspot location |

**Historical status by piece:** Phase 1 (external EDA baseline) recorded · Phase 2
(OpenDB exporter) recorded · Phase 3 (thermal on external placement geometry)
recorded · Phase 4 PDNSim data captured, but
the **quantitative CoupFE-vs-PDNSim electrical comparison is not yet done** — it needs
a 1D PDN-graph conduction operator (the plan §4.1 mixed-dimensional piece) · Phase 6
back-annotation (`instance_temperature.csv`) ✓ partial.

**Honest caveats:** GCD's absolute ΔT is tiny because it dissipates µW (leakage only,
no activity); the hotspot *pattern* is the robust result. Thermal BCs (edge-cooled)
and material values (k_si, die thickness) are documented assumptions — the SKY130/
Nangate thermal-property gap (survey §6) is real. Per-instance power is distributed ∝
cell area, normalized to the OpenROAD total.

## Phase 4: electrical PDN validation vs PDNSim (added)

`eda_multiphysics/pdn_graph.py` adds a **1D PDN-graph conduction operator** (resistor
network on the CoupFE contract — the plan §4.1 1D model). It parses PDNSim's own
exported network (`write_pg_spice`: 111 R, 68 current sources, 1 V source) and solves it.

| Check | Result |
|---|---|
| CoupFE vs independent scipy linear solve (identical network) | machine precision (worst IR 4.07e-5 V both) → **solver correct** |
| CoupFE vs PDNSim IR-drop **spatial field** (251 instances) | correlation **0.89**, R²=**0.80**, worst 3.23e-5 vs PDNSim 3.0e-5 (≈8%) |
| Current-scale factor | 0.79 — see finding below |

**Finding (open cross-validation caught a tool inconsistency):** OpenROAD's
`write_pg_spice` exports ~1.3–1.4× larger total load current (1.09e-5 A) than
`analyze_power_grid` uses (~7.8e-6 A, consistent with `report_power`/V), so solving the
exported netlist gives a 1.4× larger IR drop than PDNSim reports. An independent open
solver surfaced this — a concrete argument for the integration's value.

**Insight for the demonstration:** GCD's self-heating is negligible (peak ΔT ~6.7e-5 K
real, ~0.04 K even at 5 mW), so the **coupled R(T) effect is invisible on GCD**
(ΔR/R = α·ΔT ~ 1e-4). The coupled-electrothermal headline ("temperature-dependent
resistance shifts the IR-drop verdict") **needs a higher-power / larger design** (Ibex,
or a documented stress scenario) — a key finding for choosing the flagship case.

## Historical Phase 5: coupled electrothermal on external AES data (unqualified)

`eda_multiphysics/electrothermal_chip.py` closes the loop the project exists to
demonstrate: the **1D PDN graph** (from `write_pg_spice`) coupled to a **2D compact
die thermal model** (lateral spreading + vertical sink to ambient, the new reaction
term in `fe.py`). thermal→electrical: `g_e(T)=g_e0/(1+α·ΔT)`; electrical→thermal: PDN
Joule adds to the die source. Staggered Picard with under-relaxation.

| Design | cells | peak ΔT | isothermal worst IR | coupled worst IR | **R(T) shift** |
|---|---|---|---|---|---|
| GCD (derisk, 260 µW stress) | 251 | 20.0 K | 4.07e-5 V | 4.40e-5 V | **+8.0%** |
| **AES (5 mW active)** | **9900** | **15.8 K** | **8.01e-4 V** | **8.52e-4 V** | **+6.33%** |

**Historical interpretation:** this experiment explored an open research
analogue of coupled electrothermal analysis. Under its documented assumptions,
the AES case raised worst IR drop by 6.33% relative to the isothermal solve.
The inputs and raw logs are not bundled, so this is not current validation or
signoff evidence.

**Physical self-consistency check:** the IR-drop shift (+6.33%) ≈ α·ΔT = 0.004 × 15.8 K
= 6.3% — the worst-path IR drop rises by exactly the metal-resistance increase, as it
must. Thermal calibration (k_si=148, t_si=100 µm, vertical sink h_v=1e4 W/m²K) and
α=0.004/K are documented assumptions (survey §6 PDK thermal-data gap); the *direction
and mechanism* are robust, the absolute % scales with α·ΔT.

## Historical Phase 7: closed-loop modification on external AES data (unqualified)

The recorded design modification was performed in OpenROAD: re-`pdngen` the
same placed AES with a denser grid (M4/M7 pitch 28/15 → 14/7.5, wider straps; 3088 →
5080 PDN nodes), re-export, re-run the **coupled** electrothermal solve.

| Run | PDN | coupled worst IR | peak ΔT | R(T) penalty |
|---|---|---|---|---|
| C baseline | M4 p28 / M7 p15 | 8.52e-4 V | 15.8 K | +6.33% |
| **D reinforced** | M4 p14 / M7 p7.5 | **5.56e-4 V** | 15.8 K | +6.33% |
| Δ | denser grid | **−34.7%** | 0 | — |

(PDNSim's own isothermal worst IR confirms the EDA-side change: 6.44e-4 → 3.47e-4 V.)

**Historical model result:** the assumed coupled analysis recorded an
OpenROAD → multiphysics → redesign → re-solve loop. It must be rerun with
retained inputs and outputs before being treated as current evidence.

**Insight the coupled analysis reveals (isothermal can't):** the PDN reinforcement
cuts the IR drop 35% but leaves **peak ΔT unchanged (15.8 K)** — the hotspot is driven
by instance power density, not the grid. The coupled solve distinguishes an *electrical*
fix (reinforce the PDN) from a *thermal* one (spread placement / add cooling); an
isothermal IR-drop flow cannot make that distinction.

## Harder case: TSV thermomechanical stress vs a PUBLISHED benchmark

### Anisotropic blind-TSV local foundation (not experimental validation)

`mesh3d.tsv_device_submodel` and `tsv_local_3d` now provide a separate conformal Tet4 path for the
next-stage 10 µm Cu / 0.4 µm SiO2 / (001)-Si blind TSV. The physical scene stores the 55 µm Cu
depth, a 0.4 µm sidewall-and-bottom oxide cup, free `z=0` surface, and `z=-0.2 µm` Raman plane
explicitly. Cubic-Si stiffness rotation,
engineering-Voigt conversion, linear thermal assembly, full stress recovery, barycentric silicon
field lookup, and `sigma_xx+sigma_yy` extraction are regression tested.

The corrected refined scaled toolchain case has 2,563 connected nodes and 12,060 Tet4 elements,
preserves both conformal interfaces, contains no orphan nodes or direct Cu/Si tip contact, and
balances the unconstrained equilibrium residual at `7.03e-15`. Every result records the boundary
condition, coordinate/crystal frame, and SHA-256 material and mesh digests. This is geometry/
assembly evidence only. Mesh/domain convergence, an
independent Hex8 comparison, and digitized curvature/Raman curves remain release-blocking, so every
result is labeled `release_validation=false`.

An exploratory scaled refinement (`h=0.55, 0.45, 0.35` in the scaled geometry) did **not** pass the
release convergence gate: the recovered six-point [110] Raman profile changed by roughly 28% and
35% between successive meshes, even after volume-weighted nodal recovery. This is useful failed
evidence, not a publishable curve. The next numerical work must introduce measurement-aware spatial
averaging/local refinement and continue to finer meshes; the required two-finest-mesh change remains
≤2%.

Distance-based near-surface refinement, consistent P1 L2 stress projection, and explicit Gaussian
spot quadrature were then added. The last-two-mesh profile difference remains 14.3%, 11.3%, and
6.9% for assumed spot sigmas 0.08, 0.15, and 0.25 scaled µm. This confirms that measurement
resolution materially changes the apparent convergence, but no tested value passes 2% and the
experimental width is not known precisely enough to select one as an oracle.

Boundary sensitivity is also not qualified. With minimal rigid pins, enlarging the scaled Si
radius/depth from 3 to 4 changed the spot-averaged profile by over 500%, proving that rigid-mode
removal was being mistaken for a physical far field. The new `silicon_free_expansion` boundary
prescribes `u=alpha_Si deltaT x` on the outer/bottom Si boundary and reduces the 3→4 and 4→5 changes
to 54% and 18%. That is progress but still far above the required 3%; no domain size is accepted.

Separate enlargement shows the depth change 3→4 is about 3.1%, while radial changes are 59%
(3→4), 15.4% (4→5), and 14.0% (5→6). Lateral boundary semantics—not simply wafer depth—dominate
this local result. Because the held Raman specimens are periodic arrays, the next accepted geometry
must reproduce their 40/50 µm unit cell rather than extrapolate this isolated-cylinder sensitivity.

`mesh3d.tsv_periodic_cell` now creates a conformal full rectangular cell with
`[110]/[-110]/[001]` axes, an oxide cup, and Gmsh-matched opposite faces. The scaled regression has
2,863 connected nodes and 13,809 Tet4 elements; both x faces contain 142 nodes and both y faces 106,
with exact translated correspondence, zero direct Cu/Si contact, and Cu/oxide/Si volume errors
1.42%/0.72%/0.075%.

CoupFE's exact serial MPC now drives this cell. A homogeneous-Si `H=alpha*dT*I` patch gives affine
displacement error `3.72e-23 m`, maximum stress `9.76e-12 MPa`, reduced residual `4.94e-14`, and zero
constraint error. The zero-jump broken control gives 29.09 MPa. With real Cu/oxide/anisotropic-Si
properties and the explicitly assumed Si free-contraction macro gradient, reduced residual is
`1.72e-14` and MPC error is zero. This qualifies the pairing/reduction/assembly mechanism—not the
choice of Jiang macro/bottom BC, corrected-scene convergence, distributed TSV execution, or
experimental stress curve—and does not advance a release-score category. Core's separate
bulk/history-free PETSc reference passes an analytic periodic-gradient solve at 1/2/4 ranks, but its
setup/final lift remain replicated. The maintained support matrix is
`docs/PERIODIC_MPC_STATUS.md`.

The next, harder multiphysics case (chosen via a literature survey): electro-thermo-
mechanical / TSV stress — the temperature field drives thermal expansion → stress,
exercising CoupFE's mechanics core (not just the scalar electrothermal). The
2026 survey found limited reproducible OpenROAD-coupled thermo-mechanical stress
examples, and this component has a closed-form oracle.

`eda_multiphysics/tsv_stress.py` is an **axisymmetric thermoelastic FE** on the CoupFE
operator contract, validated against the **published Lamé TSV-stress benchmark**
(Choi et al., *Materials* 2021 14(18):5226, PMC8472814):

| D (µm) | r (µm) | CoupFE σ_r (MPa) | published Lamé (MPa) | rel err |
|---|---|---|---|---|
| 5 | 20 | 9.84 | 9.83 | 0.06% |
| 10 | 20 | 39.35 | 39.33 | 0.06% |
| 15 | 20 | 88.53 | 88.49 | 0.05% |
| 30 | 20 | 354.17 | **353.95** | 0.06% |

→ **0.06% match to a published analytic benchmark** (Cu/Si properties from the
paper's Table 1, ΔT=−400 K). This verifies the idealized axisymmetric model
against that benchmark; it is not experimental device validation.

**Honest finding (independent FE surfaces a nuance, again):** the paper attributes its
56% analytic-vs-3D-FEA overestimate (353.95 vs 225.77 MPa) to "neglecting the
barrier/STI stress-buffer." But in the axisymmetric in-plane model the thin liner
changes the Si stress by **<1%** (40 nm TaN +0.20%, 160 nm SiO₂ −0.58%) — so the liner
is **not** the cause. The 56% gap is a 3D effect (free top surface + finite TSV depth +
directional "longitudinal" channel stress) that neither the closed form nor a 2D
axisymmetric model represents; reproducing 225.77 MPa needs a full 3D submodel. (This
echoes the PDNSim current-inconsistency the same independent solver caught in Phase 4.)

**Status:** the T→u thermoelastic component matches the published analytic
benchmark. A full V–T–u device workflow would require qualified V→T data plus
the separately checked T→u model and a composed/device-level oracle; component
checks alone are not end-to-end validation.

## Historical V–T–u chain on external AES data (unqualified) (`chip_vtu.py`)

The historical run chained two separately checked components on AES-derived
data: **V→T** drove the Lamé-benchmarked axisymmetric **T→u** model across a
parametric TSV array. No single closed-form or experimental oracle covered the
composed three-field output. The external inputs and raw logs are not bundled,
so the result is historical integration evidence only.

The chain reveals **when per-TSV thermal coupling actually matters**, via the lateral
spreading length √(k·t/h_v) vs die size:

| Die regime | spreading len | dT_op range | TSV-stress range | verdict |
|---|---|---|---|---|
| thick, conventional cooling | 1217 µm ≫ 178 | 0.1% | 0.1% | laterally isothermal — uniform estimate suffices |
| **thinned 3D-IC + microchannel** | **172 µm ≈ 178** | **5.3%** | **5.3%** | **real gradient — per-TSV analysis matters** |

So the coupled per-TSV analysis is only needed in the thinned/aggressively-cooled 3D-IC
regime (exactly where TSVs live); a thick evenly-cooled die is near-isothermal and a
single uniform stress estimate is adequate. That "when does it matter" answer is itself
the useful output.

**Physical insight the chain produces (uniform/process-only analysis cannot):** the
operating temperature gives TSVs in the hotspot the **worst thermal-cycling amplitude**
(fatigue driver) but the **lowest static stress** (operating heat relieves the cooling
residual) — opposite design implications for the same via.

**Honest scope:** absolute operating-induced stresses are modest (the uniform process
residual ~37 MPa dominates the static magnitude); the chain's value is the spatial
*variation* and the cycling/static distinction. Thermal calibration (k_si, t_si, h_v, α)
and the 5 mW activity are documented assumptions (survey §6 PDK thermal-data gap).

## Widely used viscoplastic solder-fatigue model (`anand.py`)

The next step up — nonlinear, rate- and history-dependent material under cyclic load,
an industrial reliability workflow pattern. The surveyed literature and tools commonly use
the **Anand unified viscoplastic model** (in ANSYS/Abaqus/Simcenter) + **JEDEC
JESD22-A104** thermal cycling + **Coffin–Manson / Darveaux** energy-based life.

**Trust gate — validated against the model's exact closed-form steady state** (the
standard verification for viscoplastic integrators), using the published Cheng/Wang
2000 parameter set for 62Sn36Pb2Ag solder:

| oracle | result |
|---|---|
| integrator vs closed-form saturation stress σ_sat = (ŝzⁿ/ξ)·sinh⁻¹(zᵐ) | **0.07% max err** across 9 (T, ε̇) combos (25/75/125 °C × 1e-4/1e-3/1e-2 s⁻¹) |
| broken control (Q/R ×1.1) | rejected ✓ |

**Industrial workflow — JEDEC −40↔125 °C cycling of a constrained joint:**

| metric | value |
|---|---|
| inelastic strain-energy-density / cycle (ΔW) | 0.082 → **0.061 MJ/m³** (shakedown after cycle 1 — the standard behavior) |
| plastic strain range / cycle | 0.211% |
| Coffin–Manson life N_f | ~47,000 cycles (εf′=0.325, c=−0.5, representative published SnPb constants) |

**Open-source status:** the 2026 survey found this integrated workflow primarily
in commercial tools such as ANSYS, Abaqus, and Simcenter, and found limited
reproducible open examples. That survey is not an exhaustive claim about the
field. **Honest scope:** this is a material-point / constitutive-level validation
(the law CoupFE's viscoplastic codegen emits as a UMAT), integrated with a stiff ODE
solver for the reference; a full 3D solder-joint FE + Darveaux volume-averaging is the
next step. Life constants are illustrative/published. The *trust gate* (0.07% vs the
published model's analytic saturation) is the rigorous, reproducible result.

**Sources:** Anand model & parameters — Cheng, Wang, Chen, Wilde, Becker,
*Soldering & Surface Mount Technology* 12(2) 2000; standards — JEDEC JESD22-A104,
IPC-9701; life — Coffin–Manson, Darveaux (energy-based).

## Full solder-joint viscoplastic FE + volume-averaged Darveaux life (`solder_joint.py`)

The Anand material put into a finite-element solder joint under JEDEC cycling, with the
mesh-objective **volume-averaged Darveaux** damage metric — an industrial
reliability FE workflow pattern. Built and checked in stages, with the evidence
identified for each:

| Stage | what | oracle | result |
|---|---|---|---|
| 1 | plane-strain J2 **return map** (radial return, Brent) | closed-form saturation stress, **pure shear** (multiaxial) | **0.04%** max err |
| 2 | Quad4 plane-strain FE assembly | **elastic patch test** (affine field exact) | **4.3e-16** |
| 3 | solder joint, JEDEC −40↔125 °C, ~2% shear | volume-averaged ΔW per cycle → Darveaux | see below |

**Stage 3 result:** the inelastic strain-energy density **shakes down** to a stabilized
**ΔW = 0.0394 MJ/m³** per cycle (volume-averaged over the crack-prone interface layer —
Darveaux's mesh-objective metric). Darveaux energy-based life (eutectic-SnPb constants,
Darveaux 2000): **N_f ≈ 2,780 cycles** (N0=1,584 init + 1,196 growth), a
calibration-specific estimate for this assumed SnPb case.

**Unit-sensitivity caught (another independent-solver finding):** the Darveaux constants
are calibrated in **psi/inch**; feeding ΔW in MPa gave N_f=3.2M (1000× wrong). Using the
constants in their native units gives 2,780 for this calibration. ΔW (MJ/m³) is the rigorous,
mesh-objective output; N_f is order-of-magnitude (constants are calibration-specific).

**3D refinement:** `anand_3d.py` now carries the same Anand law in a stateful small-strain
Hex8 element. It is checked by a 3D pure-shear saturation oracle (**0.03%**), a full
uniaxial-stress transient check vs `integrate_uniaxial` (**0.01%**), a wrong-`h0` broken control,
a Hex8 patch test (**1e-19**), and a SAC305/Syed driven-cycle gate (**ΔW≈0.362 MPa,
N_f≈1.5k cycles** in the fast gate configuration), plus a no-thermal-swing broken control. This
pure-Python standalone path is the correctness reference; compiling/distributing it is the next
scale step.

**Honest scope:** ΔW is the rigorous mesh-objective result; Darveaux/Syed life constants are
calibration-specific and order-of-magnitude. The shear amplification (L_dnp/h=6) and life
constants are documented/published assumptions. The 2026 survey found comparable
integrated stacks primarily in commercial tools; it did not establish that no
other open implementation exists.

## Profiled joint and conformal local package geometry (`mesh3d.py`, `reliability_3d.py`)

The global-local 3D bridge now separates two fidelity levels:

1. a cylinder/barrel/hourglass solder solid on all-Hex8 Gmsh meshes; and
2. a conformal six-region native-Tet4 package containing solder, underfill, top/bottom UBM, and
   top/bottom pads.

The package uses Tet4 deliberately. Cutting a profiled cavity into the underfill produced inverted
subdivision hexes; native tetrahedra pass the positive-volume gate without weakening acceptance.
At the regression size (`h=0.25`, normalized dimensions), the package has **400 nodes and 1,479
Tet4 elements**. All nodes are referenced, all five named material interfaces share nodes, and the
minimum signed tet volume is **7.59e-5**. Exact OCC checks verify:

- solder volume + underfill-shell volume = outer-cylinder volume;
- pad and UBM volumes = `πR²t`; and
- external pad surfaces lie at the requested elevations.

The compiled Tet4 thermo-mechanical solve creates one `ElementGroup` per material region. For
`du=0.01`, it converges in **18 FieldSplit KSP iterations**, preserves the imposed pad BCs to machine
precision, and gives solder 95th-percentile equivalent strain **0.01216**. The normalized CLI
JEDEC/DNP example (`--shape barrel --package`) gives 1,479 Tet4, positive minimum volume, and a
finite downstream life. That life is a **sensitivity result**: default regional stiffnesses are
representative, not a qualified package material deck.

The geometry-driven path is available with `from_design(include_package=True)` or:

```bash
python -m eda_multiphysics.reliability_3d design --shape barrel --package
```

Its tests protect geometry connectivity, exact volume partition, material interfaces, the
multi-material solve, and the composed nine-joint synthetic life map. The design bridge now prefers a versioned
`joints.csv` + metadata map with stable IDs, explicit units, coordinate transforms, optional
dimensions, and source provenance. The bundled nine-row map is project-authored and
labeled `synthetic_pdn_spec`; it is a parametric proxy, not package-exported bump data.
Remaining fidelity work is a real package export, calibrated package dimensions/materials,
imported CAD, and a stateful Anand operator on the external local mesh. See `docs/GEOMETRY.md`.

## Added examples: electromigration + classic mechanics benchmarks

Six more examples, each checked against the stated published or analytic oracle, wired into
the gate suite at that milestone (then **22/22 gates**, ~8 s):

| Example | module | oracle | result |
|---|---|---|---|
| **Electromigration** | `electromigration.py` | Black's eqn temp-acceleration (JEDEC) + Blech immortality product | AF 13.15× (std ~13.1×); (jL)_crit 3348 A/cm (published range 1000–6000) |
| **Bimetallic strip** | `thermomech.py` | **Timoshenko (1925)** exact curvature | FE κ=0.7441 vs 0.7500 1/m (**0.8%**) — adds the *bending* validation mode |
| **Thermal-gradient cylinder** | `thermomech.py` | **Timoshenko–Goodier** Art. 152 hollow-cylinder hoop stress | FE 17.44 vs 17.44 MPa (**0.0%**) — validates a non-uniform T-field driving stress |
| **Capacitance extraction** | `capacitance.py` | exact parallel-plate ε·A/d (charge = electrode reaction) | 1e-14 (the *C* to complement the PDN *R*) |
| **Thermal runaway** | `thermal_runaway.py` | saddle-node **tangency** critical power (Bhat et al.) | Pc=0.340 W; converges below, diverges above — the *bifurcation*/nonlinear case |
| **Transient conduction** | `transient.py` | exact eigenvalue λ=(π/L)²α (first-mode decay) | 2.2% (adds the *time* dimension; backward-Euler FE) |
| **Creep / relaxation** | `creep.py` | inverse-saturation secondary-creep rate (Anand, stress-controlled) | 0.0% (adds *stress-controlled* viscoplasticity) |
| **2D axisymmetric element** | `thermomech.py` | exact **Lamé** pressurized thick-cylinder hoop | 0.0% (the r–z element NAFEMS LE11 needs) |

Total at this milestone: **30/30 gates** (~11 s; includes the capstone pipeline below). *(The
suite has since grown to **53 gates** — this table is the milestone snapshot, not the current total;
run `python -m eda_multiphysics.run` for the live count.)*

## Capstone: the end-to-end design → reliability pipeline (`reliability_pipeline.py`)

The current automated flow uses the bundled, project-authored **synthetic_pdn**
fixture and emits a reliability scorecard. The resistor-grid network, placement,
power values, and joint-map proxy are synthetic and Apache-2.0 licensed. The
voltage oracle follows from grid symmetry; no external design or EDA output is
used by the default run.

| # | stage | metric (this run) | evidence |
|---|---|---|---|
| 1 | PDN electrical | worst IR **0.250 mV** | closed-form symmetric grid (**0.250 mV**) + scipy |
| 2 | electrothermal | peak **ΔT 9.12 K**; R(T) shifts IR **+3.6 %** | load-plus-grid-loss power closure; separate electrothermal component gates |
| 3 | thermomechanics | peak parametric TSV stress **0.90 MPa** | separate Lamé component evidence |
| 4 | solder fatigue (SAC305) | mission cycle −40→34 °C; ΔW **0.0120 MJ/m³** → **N_f ≈ 44,038 cyc** | separate Anand/Syed component evidence |
| 5 | electromigration | worst **J 3.03×10⁴ A/cm²**; Black temperature AF **2.83×**; **12/12 Blech-immortal** | separate Black/Blech component evidence |

**Physical hand-offs propagate:** the coupled electrothermal ΔT sets the upper temperature of the
default operating mission cycle (hotter die → larger ΔT_cycle → more fatigue) and drives Black's
temperature acceleration (hotter → shorter relative EM lifetime). The PDN solve supplies the
per-segment current for the EM screen (`J = |ΔV|/ρL`, derived from the synthetic netlist). A fixed 125 °C
qualification cycle remains available via `solder_profile="qualification"` and is labeled as
power-independent. Source metadata identifies the bundled 9 mW scenario as project-authored
synthetic power, not an EDA-tool report. During R(T) coupling, per-instance `V×I`
load heat is recomputed; this run closes 8.998135 mW load plus 1.864918 µW grid
loss to the 9.000000 mW source.

**Gated, not just demoed:** `gate_capstone_pipeline` requires the CoupFE graph solve to match
the bundled closed-form IR reference, requires source/load/loss power closure, and
requires every downstream stage to return finite physical values. The release
artifact checker independently solves all nine nodes and verifies KCL, every
per-instance `V×I` value, resistor loss, hashes, and declared/computed closure.
`gate_capstone_broken_control` checks the structural zero and active solder/EM handoffs from
0 to 5 mW. The same solver-neutral interface accepts caller-supplied
[OpenDB placement](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html) and
[PDNSim `write_pg_spice`](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html)
data, but those external results require their own provenance and qualification.

**Honest scope:** the exact bundled-case oracle covers the linear PDN voltage field. The thermal,
Lamé, Anand/Syed, and Black/Blech implementations retain their separate numerical or published
checks. The composed output has no single experimental oracle; its stress and life stages use
parametric geometry/material assumptions and are demonstrations, not predictions for a real
design or package.

## Most-recent benchmark: SAC305 lead-free Anand (`anand.py`)

The prior Anand validation used **62Sn36Pb2Ag** (legacy eutectic Sn-Pb, Cheng/Wang 2000).
The modern RoHS-era industry standard is the lead-free alloy **SAC305 (Sn-3.0Ag-0.5Cu)**,
so the most-recent step is to reproduce a *published* SAC305 benchmark — the actual alloy
in current electronics.

**Parameter set (cross-checked across three independent sources).** The canonical recent
SAC305 Anand 9-constant set is from the Auburn CAVE3 group: **Motalab, Cai, Suhling, Lall,
ITherm 2012** (DOI 10.1109/ITHERM.2012.6231522) / Motalab PhD dissertation (Auburn 2013),
Table 4.1 (non-aged stress-strain fit). It is independently reproduced in arXiv:2204.05583
(Table 2) and MDPI *Materials* 2023 16(14):4922. A transcription trap was caught in the
cross-check: the MDPI table prints `h0 = 18000` (a dropped zero); the dissertation value is
**180000 MPa** — and h0 affects only the hardening *transient*, not the saturation oracle,
so the closed form is insensitive to it (the integrator gate uses 180000).

| oracle | result |
|---|---|
| **(rigorous)** integrator vs closed-form saturation σ_sat, 9 (T, ε̇) combos | **0.02%** max err |
| **(benchmark)** closed-form vs **published Motalab Fig 3.10(a)** | room-T anchor **42.1 MPa** vs published ~40–41; worst figure diff **10.2%** (figure-read ±1–2 MPa) |
| broken control (A ×100) | misses the figure by 39% → rejected ✓ |

The full published-vs-computed matrix (Fig 3.10a, σ_sat in MPa):

| T (°C) | ε̇ (1/s) | closed-form | published (fig) | diff |
|---|---|---|---|---|
| 25 | 1e-3 | 42.1 | ~40.5 | 3.9% |
| 50 | 1e-3 | 35.8 | ~33.5 | 7.0% |
| 100 | 1e-3 | 26.4 | ~24.0 | 10.2% |
| 125 | 1e-3 | 22.8 | ~21.5 | 6.2% |
| 25 | 1e-4 | 36.1 | ~35.5 | 1.8% |
| 25 | 1e-5 | 30.4 | ~29.5 | 3.2% |

**Honest scope:** the **rigorous** result is the integrator reproducing the model's own
analytic saturation (0.02%, exact). The **benchmark** result is the closed form landing on
Motalab's published Fig 3.10 within figure-digitization + model-fit tolerance (the dataset
the constants were fit to). The room-temperature anchor (≈42 vs the published ~40–41 MPa, and
within the published SAC305 UTS cluster of 40–55 MPa) is the cleanest single checkable number.
**Source:** Motalab et al., ITherm 2012 / Auburn dissertation 2013, Table 4.1 + Fig 3.10.

**On NAFEMS LE11 specifically:** the literal LE11 target (σ_zz = −105.04 MPa at A) requires
the exact cylinder/taper/sphere geometry, which is in the NAFEMS TNSB publication / vendor
`.inp` files — *not* in the open verification pages (Abaqus, Altair, OnScale, feenox all
state E=210 GPa, ν=0.3, α=2.3e-4, T=√(x²+y²)+z, A=(1,0,0), but none tabulate the full
geometry). Rather than guess the geometry (which would be an invented benchmark), I built
the **2D axisymmetric r–z thermoelastic element LE11 requires** and validated it against the
exact Lamé cylinder (0.0%). LE11 is then a geometry-input step away, achievable given the
NAFEMS `.inp` / the publication.

EM completes the reliability arc (IR-drop → thermal → TSV stress → solder fatigue → **EM**);
it reuses the validated J (PDN-graph) and T (electrothermal) fields, and applies the
Blech filter (short high-current segments are EM-immortal). The bimetal adds bending
(the prior mechanics gates were conduction/uniaxial/shear); the cylinder validates the
electrothermal→mechanics coupling against an exact analytic thermal-stress benchmark.
(NAFEMS LE11 is the FE-suite analog of the cylinder benchmark; its solid-of-revolution
geometry is a heavier follow-up — the T&G closed form is the same analytic basis.)

## Historical 2026-06-24 distributed/MPI snapshot (unqualified)

The serial suite is the current trust layer. This section preserves the original
PETSc/MPI development snapshot; its raw logs and locked environment were not
retained, so none of the numerical performance statements below is a current
release claim.

**CoupFE's own distributed path verified first** (Open MPI 4.1.6 + petsc4py 3.25):
- `examples/mpi_smoke/distributed_residual.py` — distributed assembly, serial == 2-rank to
  **1.78e-15** (the 1-vs-N invariant).
- `examples/mpi_smoke/distributed_solve.py` — PETSc KSP, serial == 2-rank to **1.67e-15**.

**`eda_multiphysics/pdn_distributed.py`** — the PDN-graph electrical solve made distributed:
each rank stamps only the resistor edges it owns (PETSc routes off-process contributions);
symmetric Dirichlet (`zeroRowsColumns`) keeps the Laplacian SPD; **CG + GAMG** solves it.

| case | nodes | ranks | iters | wall | serial == N-rank |
|---|---|---|---|---|---|
| grid 400² | 160 k | 1/2/4 | 16/15/15 | 1.57→**0.67 s** (2.3×) | ~3e-11 |
| **grid 1000²** | **1 M** | 4 | 18 | **4.3 s** | 9e-11 |
| external AES PDN (`write_pg_spice`; historical) | 3 k | 1/2 | 20/16 | 0.02 s | 3e-11 |

The historical record showed similar iteration counts and serial/MPI agreement,
including on external AES-derived data. Because the case inputs, raw outputs,
and environment record are absent, this is neither a current scaling result nor
real-device validation. The `--direct`/superlu_dist path was implemented but its
PETSc rebuild failed in that original environment. See
[`DISTRIBUTED.md`](../../../eda_multiphysics/DISTRIBUTED.md) for the archived interpretation and rerun
requirements.

## Original 2026-06-24 phase-by-phase evaluation

| Phase | What it needs | Status here |
|---|---|---|
| 0 Setup / select designs / freeze versions | planning + toolchain | env + module skeleton done; design selection N/A without PDKs |
| 1 Reproducible EDA baseline (run OpenROAD) | OpenROAD, PDK | **blocked** (no OpenROAD/Yosys/PDK) |
| 2 OpenDB geometry exporter | OpenDB | **blocked** (needs OpenROAD/OpenDB) |
| 3 One-way thermal model | FE conduction + source | **done + validated** (C1,C2,C4) |
| 4 Electrical model | DC conduction; PDNSim compare | **done + validated vs Ohm's law** (C3); PDNSim compare blocked (not installed) |
| 5 Closed-loop electrothermal coupling | σ(T), Joule, staggered solve | **done + validated vs independent BVP** (C5) |
| 6 Visualization + back-annotation | fields/CSV; KLayout/OpenROAD overlays | fields/CSV producible; EDA overlays **blocked** |
| 7 Closed-loop design modification | re-solve + metric compare | **done (solver-side proxy)**; EDA back-annotation blocked |
| 8 Packaging (`mpeda run`) over the EDA flow | full toolchain | `python -m` entry works; full pipeline blocked |

## Most promising cases in the original report

1. **Coupled electrothermal solver core (Phase 5)** — matched an independent
   reduced-model oracle to ~1e-12. This supported the original feasibility claim that Phases 3–5 are
   lightweight operator/WeakForm authoring in CoupFE, not new solver R&D. Strongest
   result.
2. **Phase-7 verified improvement** — the whole plan's value proposition (a design
   change that produces an actionable, verified electrothermal improvement) works on
   the solver: −33% hotspot, −19% IR drop at fixed current.
3. **"Two homes" confirmed** — the same weak form generates a native kernel and an
   Abaqus UEL; the codegen path runs here.

## Honest limitations

- **1D-reduced slab geometry.** The cases reduce to 1D in x (insulated top/bottom) so
  the analytical/BVP oracles are exact. Device-level 2D/3D PDN geometry from EDA is not
  exercised (no OpenDB). The operator is genuinely 2D; the *test cases* are 1D by
  construction for oracle exactness.
- **Normalized units**, not SI PDK values (temperature-dependent SKY130 properties are
  a known data gap — see the survey §6).
- **No PDNSim cross-check** (Phase 4 validated against Ohm's law instead).
- **EDA glue remained the main integration work in this snapshot.** A qualified
  next step is to feed shareable OpenROAD/PDK-derived geometry and traceable
  inputs into the separately checked numerical components, retain the raw
  evidence, and compare with device measurements.
