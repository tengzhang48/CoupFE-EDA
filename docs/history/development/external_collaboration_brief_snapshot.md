# Historical snapshot: External-collaboration brief

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/COLLABORATION_BRIEF.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# CoupFE-EDA — checkpoint and external-collaboration brief

**Date:** 2026-07-20
**Purpose:** an honest statement of what is built, what is validated, and what can only be finished
with external data or partners. The remaining blockers are primarily evidence and integration
problems; the source-equivalent boundary-condition contract remains a defined internal correction.

## One-paragraph summary

CoupFE-EDA is a physics-aware, traceable multiphysics consumer built on the CoupFE core operator
contract. Selected constitutive and numerical components are verified against analytic limits,
published benchmarks, and structural controls. Its **device-scale claims are not yet experimentally validated** — every
category of the TSV-to-device release scorecard is `blocked` or `not_started`, and the blockers are
now dominated by missing experimental ground truth and real EDA-database integration, both of which
need an external partner. The honest label remains *alpha numerical/device-screening prototype*.

## What is genuinely validated (defensible today)

- **Material-point constitutive stack.** Anand viscoplasticity and creep
  (`anand.py`, `creep.py`) are checked against uniaxial oracles; strain-energy-density-per-cycle
  (ΔW) is the stronger numerical quantity, while life N_f remains calibration-specific.
- **Electrothermal solver core** (Phases 3–5) validated against analytic limits with structural-zero
  broken controls.
- **Cubic-Si anisotropic Tet4 mechanics.** Exact fourfold symmetry, affine constant-strain patch,
  homogeneous free-expansion at machine zero, heterogeneous equilibrium residual ~1e-14.
- **Periodic MPC machinery.** Exact `U=Pq+U0` serial constraint, verified matching-face bijection,
  1/2/4-rank MPI reference on a scalar patch. This is numerical verification, not TSV-scale validation.
- **Traceability.** The local TSV/device path records coordinate frame, crystal rotation, and
  SHA-256 material/mesh identities; other workflows carry their documented, narrower provenance
  fields. The spin-off added nothing to the CoupFE core.

## What is NOT validated (must not be claimed)

Foundry signoff; quantitative transistor-delay prediction; Cu protrusion; interface fracture;
fatigue life as an absolute number. The current end-to-end TSV device demo is driven by a **classical
Lamé far-field proxy**, explicitly labeled as such.

## The two blockers that internal work cannot clear

1. **The boundary-condition contract is a hidden assumption, not frozen physics.** The periodic model
   prescribes pure-silicon free contraction on the outer/bottom faces and takes the macro strain as an
   input rather than solving the traction-free composite condition. The Raman observable is computed
   against that assumption and therefore cannot falsify it. See `lessons_learned.md` (2026-07-20) and
   the decisive assumed-vs-solved experiment proposed there. *This one is closable internally* and is
   the recommended last internal task before the pivot.

2. **There is no experimental ground truth in the repo.** Release is gated on digitized Ryu curvature
   branches and Jiang specimen C/D Raman curves that are defined in manifests but not present. Without
   held experimental data — ideally measured, not digitized from a figure — the accuracy, conservation,
   and device-mapping categories cannot move to `passed` no matter how good the solver is.

## Where external collaboration is the unlock

| Need | Ideal partner | What they provide | What CoupFE-EDA offers back |
|---|---|---|---|
| Experimental ground truth | TSV/packaging reliability lab (µRaman, wafer curvature, thermal cycling) | Measured near-surface stress and life data on known geometries | Traceable, open, physics-aware back-annotation of their specimens |
| Real device/EDA integration | OpenROAD / OpenDB users or a design team | A real DEF/LEF layout + keep-out and timing context | Implemented stable-ID screening adapters, with case-specific qualification still required |
| A concrete first problem | Anyone with a *specific* reliability question on a real part | The part, the load history, the question | An auditable research analysis with explicit assumptions and stated non-claims; formal uncertainty quantification would be joint work |
| Independent numerical check | A group with an established TCAD/FE TSV model | A second solver's field on one shared geometry | Cross-validation that raises both tools' credibility |

## Recommended path from here

1. **Close the BC contract** (last internal task): run the assumed-vs-solved-H experiment, freeze the
   result with an error bar, and flip `numerical_mechanics` off "blocked" or state precisely what core
   support is missing. This is a few days, not a program.
2. **Freeze this checkpoint** and stop broad internal development. Do not start the 3-D viscoplastic
   *element* beyond the currently qualified scope — it widens the validation
   surface while nothing device-scale is yet validated.
3. **Take the brief above to one external partner with one real problem.** The scorecard's remaining
   categories are exactly the things a real specimen + a real layout make answerable. The tool is now
   good enough to be *useful on a real question*; it is not good enough to be *trusted in the
   abstract*. A single real collaboration resolves more than another quarter of internal gates.

## Pointers

- Release contract and scorecard: `CoupFE_EDA_TSV_Device_Validation_Release_Plan.md`,
  `benchmarks/tsv_release_scorecard.json`
- Physics audit and benchmark separation: `docs/TSV_PHYSICS_AUDIT.md`
- Periodic status vector: `docs/PERIODIC_MPC_STATUS.md`
- Lessons: `docs/lessons_learned.md`
