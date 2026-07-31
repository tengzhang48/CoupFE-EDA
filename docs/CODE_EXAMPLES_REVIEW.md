# CoupFE-EDA code and examples review

**Review date:** 12 July 2026  
**Reviewed revision:** `994b381` (`main`)  
**Disposition:** all five findings resolved and regression-protected on 12 July 2026

> **Release follow-up (30 July 2026):** this dated review evaluated the former
> GCD-derived fixture. That fixture and `gcd_thermal.py` have since been removed
> from the distribution, not relabeled. The current defaults are the
> project-authored `cases/synthetic_pdn/` fixture and `case_thermal.py`, with a
> closed-form nodal-voltage reference. GCD-specific numbers below remain an
> audit record for the reviewed revision, not current release evidence.

## Technical summary

CoupFE-EDA has a strong component-validation foundation for a project spun off only weeks ago.
At the reviewed `994b381` revision, all **101 tests passed** (53 physics gates, 16 integration/CLI regressions, 9 TSV-device
foundation tests, 4 anisotropic local-TSV tests, and 19 toolchain
tests), all **40 then-current package modules** compiled and parsed, and **13 representative documented entry
points** executed successfully.
The analytic, literature, patch, independent-solver, and serial-versus-MPI results are the
package's strongest evidence at that dated revision. The current release
candidate has 44 modules and a different test inventory; use
`docs/capabilities.md` for the current boundary.

The original review found two high-impact integration defects: a **factor-of-two layout-unit
error** in the 3D reliability map and inactive temperature handoffs in the capstone. It also found
misleading power provenance, a duplicated CLI execution path, and documentation that overstated
direct example coverage. The remediation reads units and provenance from explicit metadata,
activates and tests mission-profile solder and Black-model EM coupling, and adds CLI regressions.

## Findings

| Severity | Finding | Consequence | Status |
|---|---|---|---|
| **High** | Layout DBU conversion was off by 2× | Footprint, DNP, imposed solder displacement, and the fatigue map were mis-scaled | Resolved + gated |
| **High** | Capstone solder and EM handoffs were not fully active | The scorecard overstated end-to-end coupling | Resolved + gated |
| **Medium** | Scaled/model power was labeled “real PDNSim power” | The scorecard reported misleading provenance | Resolved + gated |
| **Medium** | `chip_vtu` executed its complete workflow twice | The CLI doubled runtime and repeated output | Resolved + gated |
| **Low** | Example documentation overstated direct gate coverage | CLI and composed-output regressions could escape green tests | Resolved + clarified |

## Resolved: reliability-map DBU scale

The reviewed implementation defaulted to `dbu_per_um=1000.0`, while the vendored case manifest
declared `dbu_per_micron: 2000`:

- implementation: `eda_multiphysics/reliability_3d.py:88`;
- case metadata: `eda_multiphysics/cases/gcd_nangate45/manifest.json:3`.

The resulting coordinate comparison is:

| Basis | DBU/µm | Footprint X | Footprint Y | Maximum DNP |
|---|---:|---:|---:|---:|
| Reviewed code default | 1,000 | 63.84 µm | 56.34 µm | 42.4869 µm |
| Case manifest | 2,000 | 31.92 µm | 28.17 µm | 21.2434 µm |

The 2,000-DBU result agrees with the manifest core bounds: x = 2.09–34.01 µm. Because distance
to the neutral point drives imposed solder displacement, this error propagates into equivalent
strain and fatigue life, so the correction required regenerating the affected predictions.

The fix removes the numeric default and reads `dbu_per_micron` from the sibling manifest. A
standalone netlist without a manifest must supply the scale explicitly. The toolchain regression
now locks 31.92×28.17 µm and 21.2434 µm DNP; a fast regression checks both manifest discovery and
the fail-closed standalone behavior. The regenerated map gives a worst life of approximately
8.88 million cycles for this tiny test die (calibration-specific), rather than retaining a result
driven by the wrong coordinate scale.

## Resolved: active capstone handoffs

The electrothermal result now drives both the default mission-profile solder cycle and Black's EM
temperature acceleration:

| Applied power | Peak ΔT | Peak TSV stress | Mission upper T | Solder life | Black temperature AF | Blech-immortal |
|---:|---:|---:|---:|---:|---:|---:|
| 0 mW | 0.00000167 K | 0.000000164 MPa | 25.0 °C | 121,816 cycles | 1.00× | 78 |
| 5 mW | 38.5485 K | 3.78950 MPa | 63.55 °C | 9,480 cycles | 55.18× | 78 |
| 20 mW | 154.195 K | 15.1581 MPa | 179.195 °C | 3,570 cycles | 153,411× | 78 |

These values were produced with:

```python
reliability_pipeline.run(nx=12, ncyc=2, P_override=P, verbose=False)
```

The default is now an operating mission profile whose upper cycle temperature is
`T_amb + peak_dT`. A fixed qualification profile is still available explicitly through
`solder_profile="qualification"` and is described as power-independent. The EM stage now reports
Black temperature acceleration relative to ambient and relative lifetime in addition to current
density and Blech immunity. Blech counts correctly remain unchanged because this compact Blech
criterion is not temperature-dependent. The broken-control gate now requires 5 mW to increase
solder damage, reduce solder life, and increase Black acceleration relative to the zero-power run.

## Resolved: power provenance

The reviewed implementation treated the sum of `instance_temperature.csv:power_W` as real
switching power. That file is generated by `gcd_thermal.py`, which distributes either a default or
user-supplied total power by instance area.

The vendored CSV sums to **5.0000455 mW**. In contrast, the actual leakage-only GCD
`report_power` result is **8.52 µW**, with 5 mW documented separately as a scaled scenario. At
review time, file existence was used as the provenance test, so the scorecard printed the
scaled/model-generated value as “real PDNSim power.”

The vendored case now includes `instance_temperature.meta.json`, identifying the total as a
`scaled_user_scenario` and the per-instance model as `area_distributed_proxy`. `gcd_thermal` writes
the same metadata beside requested outputs, and the scorecard displays both fields. Missing
metadata is labeled `unlabeled_instance_csv`, never promoted to a tool export. Back-annotation is
opt-in and no longer mutates the input case by default.

## Resolved: CLI execution and coverage

The representative pure-Python benchmarks, validation ladder, capstone, and design-loop examples
executed successfully. Remediation made the following productization changes:

- removed the duplicate `chip_vtu` entry guard and locked one invocation with two intentional
  thermal regimes;
- changed `gcd_thermal` to default to the vendored case and write only when `--output` is supplied;
- added `argparse` usage handling to `chip_vtu`, `electrothermal_chip`, and `pdn_graph`;
- added ten fast integration/CLI regression tests; and
- narrowed `EXAMPLES.md` to distinguish numerical gates from CLI-format coverage.

## What is working well

- The operator and solver architecture is coherent, including the shared coupled-Newton driver.
- The two-tier test strategy keeps the common development loop fast while retaining compiled,
  gmsh, PETSc, MPI, and 3D regression coverage.
- Many models have more than one validation mode: analytic or published oracle, independent code
  path, broken control, convergence check, or rank-invariance check.
- Limitations such as public material properties, calibration dependence, synthetic scaling
  geometry, and lack of signoff qualification are generally documented honestly.
- Representative examples reproduced the documented electrothermal, design-loop, TSV, Anand,
  transient, creep, capacitance, and PDN results.

## Scope and methodology

For this review:

- **component validation** means an individual model or solver is compared with an analytic
  result, published benchmark, independent code path, broken control, or serial-versus-MPI
  invariant;
- **pipeline validation** means stage-to-stage dependencies, units, provenance, and sensitivity
  are verified across the composed workflow;
- **example coverage** means documented CLI behavior and output semantics are directly exercised,
  not only that an underlying function appears in another test.

The audit combined source inspection, the two automated test tiers, compilation and AST checks,
direct execution of documented examples, and targeted sensitivity runs. The DBU result was checked
under both conversion factors and against manifest coordinates. The capstone was run at 0, 5, and
20 mW to identify which outputs respond to upstream power.

The review did not rerun the historical 5M-DOF, 48-core timing sweep, independently reproduce the
cited laboratory experiments, or assess foundry qualification. The corrected layout-driven
fatigue map was regenerated as part of toolchain validation.

## Verification performed

- Fast suite: **82 passed**, 19 toolchain tests deselected.
- Toolchain suite: **19 passed**, 82 fast tests deselected.
- Post-audit rerun on 12 July 2026: fast **82/82** in 53.14 s; toolchain **19/19** in 256.25 s.
- Compile and AST check: **40/40 modules** parsed.
- Representative entry points executed: **13**, all successful.
- Electrothermal validation ladder: **11/11 checks passed**.
- Design-loop example: peak temperature −33.13%; IR drop −18.95% at fixed current.
- TSV stress example: maximum relative error 0.06% versus the published Lamé benchmark.

The complete saved command/output evidence is in
[`reviews/coupfe_eda_code_examples_review/evidence.md`](reviews/coupfe_eda_code_examples_review/evidence.md).

## Completed correction sequence

1. DBU scale is manifest-driven; the layout map and regression expectations were regenerated.
2. EM uses upstream temperature and reports Black acceleration alongside Blech immunity.
3. The default solder interpretation is a tested operating mission profile; fixed qualification
   cycling is a separate explicit mode.
4. Exported, scenario, and proxy power provenance is machine-readable and printed.
5. Duplicate execution, machine-specific defaults, input mutation, and missing usage handling were
   corrected; CLI smoke coverage was added.
6. The capstone remains an **integration prototype** with active dependency and
   handoff tests rather than only finite-output checks. Its numerical components
   carry separate evidence; the composed downstream output has no device-level oracle.
7. Joint locations now use a versioned stable-ID/unit/transform schema. The vendored 79-row map is
   explicitly labeled as a PDN-derived proxy; absence of a map activates a provenance-labeled
   fallback rather than silently treating PDN nodes as package bumps.

## Further questions

- Which artifact should be the canonical source of instance power?
- Which package-tool or foundry export should replace the schema-valid PDN proxy with real bump
  locations and dimensions?
- Which end-to-end dependency invariants should become release gates?
