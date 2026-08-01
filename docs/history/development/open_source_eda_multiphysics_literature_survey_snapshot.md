# Historical snapshot: Open-source EDA–multiphysics literature survey

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/open_source_eda_multiphysics_literature_survey.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# Open-Source EDA–Multiphysics Integration — Literature & Prior-Art Survey

**Status:** experimental / exploratory (companion to `open_source_eda_multiphysics_integration_plan.md`)
**Date:** 2026-06-24
**Scope:** prior art for an open-source FE multiphysics solver (CoupFE) coupled into an open digital-IC EDA flow (OpenROAD / OpenDB / PDNSim, SKY130 / Nangate45) for steady-state electrothermal power-delivery-network (PDN) analysis — electrical conduction ↔ Joule heating ↔ temperature-dependent resistance — with EDA back-annotation and a closed design-modification loop.

> **Method.** Compiled with a fan-out web-search + adversarial-verification harness (6 search angles → 26 sources → 127 extracted claims → multi-vote verification). Each finding below is tagged with confidence. **High** = independently verified (≥2 of 3 adversarial votes confirmed). **Reported** = the source was found and extracted but the claim did **not** clear 3-vote verification (transient API rate-limits and a verification budget cap cut ~20 votes mid-run); treat as plausible and source-backed, not adversarially confirmed. Vendor/marketing pages assert capability, not independent benchmarks.

---

## Bottom line

No **single** component of the proposed system is new. CoupFE-EDA demonstrates one
open implementation of the integration: coupling a weak-form FEM solver into an
OpenROAD/PDNSim-oriented workflow for R(T)↔Joule↔IR-drop electrothermal analysis,
back-annotation, and design-loop experiments. It is an example of what can be built
now, not a claim that other open implementations cannot exist or that this architecture
should become the field standard. Other groups can build independent packages around
different FEM solvers, coupling strategies, and data models.

One honest nuance from the survey: an explicitly **AI-oriented authoring philosophy** is *emerging* in 2026 (not unprecedented), so novelty claims should center on the integration, not on AI-orientation alone.

---

## 1. IC / PDN electrothermal tools  *(High confidence)*

All open-source IC thermal simulators are **compact thermal-RC-network solvers, thermal-only, fed by static pre-computed power maps** — none model coupled electrothermal physics (Joule-heating feedback, temperature-dependent resistance, IR-drop coupling).

| Tool | Open? | Physics | Method |
|---|---|---|---|
| HotSpot | open | thermal only, static power | architecture-level RC (electro-thermal duality) |
| 3D-ICE 4.0 | open | thermal only, static power | equivalent thermal RC network (SuperLU) |
| PACT | open (GPLv3) | thermal only, static power | SPICE compact; validated vs COMSOL to 2.77%/3.28% on OpenROAD designs |
| Cool-3D / Open3DBench | open | thermal as a PPA metric | wrap HotSpot 7.0 |
| **RedHawk-SC Electrothermal** | **closed (Synopsys/Ansys)** | **coupled Joule + thermal cycling + thermal stress** | commercial signoff |

The only tool that closes the coupled-electrothermal physics loop is **closed commercial software**, leaving the open-source coupled-electrothermal niche unfilled.

**References:** HotSpot <https://www.cs.virginia.edu/~skadron/Papers/hotspot_mej.pdf> · 3D-ICE 4.0 <https://arxiv.org/html/2512.05823> · PACT <https://www.bu.edu/peaclab/files/2021/05/2021YuanPACT.pdf> · Open3DBench <https://arxiv.org/abs/2503.12946> · RedHawk-SC Electrothermal <https://www.synopsys.com/implementation-and-signoff/signoff/redhawk-sc-electrothermal.html>

---

## 2. Open-source EDA + physics integration  *(High confidence)*

- **PDNSim** (the basis of OpenROAD's `psm` module, BSD) is a **purely electrical static IR-drop / current-density analyzer** — worst IR drop, worst current density, floating-stripe detection, SPICE netlist writer. **No thermal, electrothermal, or temperature-dependent-resistance modeling.** Electromigration support is limited to reporting per-segment current.
- A **one-directional** EDA→thermal pipeline already exists (**PACT ← OpenROAD/OpenSTA**, DEF → power maps), but **no open tool feeds temperature back to modify the design** — there is no open back-annotation / redesign loop. Open3DBench lists PPA-driven thermal optimization only as future work.

**References:** PDNSim / psm <https://openroad.readthedocs.io/en/latest/main/src/psm/README.html> · PDNSim docs (PDF) <https://openroad.readthedocs.io/en/latest/_downloads/86b37e131fb3a938455f51249d86af88/PDNSim-documentation.pdf> · PACT (OpenROAD interface) <https://www.bu.edu/peaclab/files/2021/05/2021YuanPACT.pdf>

---

## 3. General multiphysics / FE frameworks — positioning  *(Mixed)*

Presented as a factual spectrum (code-generation vs hand-coded kernels; lighter vs full-featured), not a value judgment of any tool.

- **Sparselizard** — general-purpose hp-adaptive open-source C++ multiphysics FE library, weak-form authoring, Python bindings (`spylizard`), GPLv2+. Toward the lighter end of full frameworks. *(Reported)* <https://www.sparselizard.org/>
- **MOOSE** — full-featured multiphysics framework; simplified PDE/BC/material interfaces while internally handling the parallel, adaptive, nonlinear solve (a heavier, batteries-included design point). *(Reported)* <https://www.sciencedirect.com/science/article/pii/S2352711019302973>
- **Firedrake** — UFL weak form → auto-generated PETSc callbacks; same script runs under MPI unmodified; symbolic tangents. The closest "weak-form → kernel → PETSc/MPI solver" neighbor. *(Reported — verification abstained on rate-limits)* <https://arxiv.org/pdf/2104.08012>
- **SOniCS** — UFL material model → FFCx C kernels embedded into the separate SOFA C++ solver (weak-form-to-foreign-solver, lightweight compile-time coupling). Closest neighbor to "one definition, foreign solver." *(Reported — verification abstained)* <https://arxiv.org/pdf/2208.11676>

**Positioning takeaway.** CoupFE's distinguishing stance is not "lighter than everyone" but *what the core deliberately omits* (meshing / BC / IO / time-stepping as per-problem glue), which is precisely what makes the kernel portable (Abaqus UEL **or** standalone) and composable. See `docs/DESIGN.md`.

---

## 4. Weak-form → user-element code generation (dual-home + AD tangents)  *(High confidence)*

The **"single symbolic/weak-form definition → multiple solver homes, including a commercial Abaqus UEL and a standalone solver"** pattern is **established prior art**:

- **AceGen / AceFEM** (Korelc) generates FE code from one Mathematica symbolic definition into **ABAQUS (UEL/UMAT), FEAP, ELFEN, and standalone AceFEM**, with consistent symbolic linearizations (tangent operators). This is a direct precedent for "one definition, two homes."

CoupFE's novelty is therefore **not** the dual-home concept but its specific realization: **complex-step** tangents (vs symbolic AD), **PETSc/MPI-native** standalone path, lightweight scaffold, AI-authorable surface. Framed honestly: *same exact-tangent goal as AceGen, via a lighter mechanism.*

**References:** AceGen <https://www.wolfram.com/products/applications/acegen/> · Korelc 2002, *Multi-language and Multi-environment Generation of Nonlinear FE Codes* <https://link.springer.com/article/10.1007/s003660200028> · representative coupled UEL (deformation–electrical–fracture) <https://www.sciencedirect.com/science/article/abs/pii/S0045782510002549>

---

## 5. AI / LLM-assisted FE authoring (2023–2026)  *(Reported — not 3-vote verified)*

An explicitly **AI-oriented authoring philosophy is emerging, not unprecedented**:

- **Constrained Natural-Language Interface for Variational Multi-Physics FE in FEniCS** (2026) — restricts the LLM to a **thin, validated front door** (NL → structured JSON → Gmsh geometry → human-written FEniCS/UFL templates; the LLM never writes solver code or derives weak forms). This is the closest neighbor to CoupFE's "declarative front door for an agent." <https://arxiv.org/abs/2606.10928>
- **ALL-FEM** — agentic AI + domain-fine-tuned LLMs generating FEniCS code across solid/fluid/multiphysics. <https://arxiv.org/abs/2510.04607>
- **"Comprehension–generation gap"** caution — LLM-generated multiphysics code can run/mesh/converge while encoding physics that differs from intent (a strong argument *for* CoupFE's independent-oracle + broken-control validation culture). <https://arxiv.org/abs/2605.09360>

**CoupFE's distinctive twist** (vs the above): the agent authors *weak forms* (not just fills fixed templates), and **skill + validation docs ship in-package** (`skills/`), validated by an independent-oracle harness. Defensible as a design stance, but narrower than "new."

---

## 6. Thermal/electrical material-property data for open PDKs  *(Reported)*

- **SKY130** publishes **baseline electrical** parasitics: per-layer sheet resistance (Metal1/2 = 125 mΩ/sq, Metal5 = 29 mΩ/sq, Poly = 48200 mΩ/sq) and via/contact resistances.
- **Not in the open PDK:** temperature-dependent resistivity, dielectric thermal conductivity, package / heat-spreader models. These must be sourced from literature and maintained as a **documented assumption database** — consistent with risk #1 in the plan.

**References:** SKY130 RCX (parasitics) <https://skywater-pdk.readthedocs.io/en/main/rules/rcx.html> · SKY130 device details <https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html> · interconnect thermal modeling (Stanford EE311) <https://web.stanford.edu/class/ee311/NOTES/InterconnectThermalModeling.pdf>

---

## Gap analysis

| Component | Open prior art? | Closest neighbor |
|---|---|---|
| Lightweight weak-form FE scaffold | yes | Sparselizard, scikit-fem |
| Weak-form → dual-home (UEL + standalone) | **yes** | **AceGen** (symbolic AD) |
| Complex-step tangent (vs symbolic AD) | partially | AceGen via symbolic AD; CS is the lighter variant |
| AI-oriented authoring philosophy | **emerging (2026)** | Constrained-NL-FEniCS, ALL-FEM |
| Open coupled electrothermal IC solver | no established example identified in this review | RedHawk-SC (closed) |
| OpenROAD/PDNSim coupling + back-annotation loop | limited public examples identified; review is not exhaustive | PACT (one-way only) |

**Conclusion (High confidence on the integration claim).** Each piece exists separately; the combination does not. No open-source system simultaneously (i) is a lightweight weak-form FE scaffold, (ii) generates both an Abaqus UEL and a native PETSc/MPI kernel from one definition, **and** (iii) is coupled into an open EDA electrothermal loop with back-annotation. **The novelty is principally in the integration and positioning** — plus the demonstrated solidity of the validated solver — rather than in any single component.

---

## Suggested positioning statement

> An experimental, lightweight finite-element scaffold that authors coupled electrothermal elements from a single weak-form definition — reaching AceGen's exact-tangent goal via complex step, in a PETSc/MPI-native, AI-authorable package — to demonstrate the first open-source OpenROAD-coupled electrothermal PDN loop with back-annotation.

---

## Confidence & caveats

- **High-confidence (verified):** §1, §2, §4, and the integration-gap conclusion.
- **Reported (found, not 3-vote verified):** §3 (Firedrake/SOniCS abstained on rate-limits), §5 (AI authoring), §6 (PDK data). Sources are real and extracted; claims are plausible but not adversarially confirmed.
- ~20 verification votes were lost to transient API rate-limits; the verification budget capped at 25 of 127 extracted claims.
- Vendor pages (RedHawk-SC) assert capability, not independently benchmarked; PACT's accuracy figures are author-self-reported. The Synopsys/Ansys acquisition (completed July 2025) means RedHawk-SC branding is current as of 2026 but may shift.

## Open questions / next steps

1. Firm up §3/§5/§6 by re-running the failed verification batch (Firedrake/SOniCS UFL→external-solver codegen; AI-authoring philosophy; SKY130/Nangate45 temperature-dependent data).
2. Confirm whether any architectural+thermal co-simulation (e.g. gem5-coupled) closes a back-annotation loop beyond PACT.
3. Decide the temperature-dependent material-property assumption database and cite its sources.
