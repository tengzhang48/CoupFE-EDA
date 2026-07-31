# CoupFE-EDA code and examples review — evidence log

Review date: 12 July 2026. Repository revision: `994b381` on `main`.

This file records the evidence behind the technical review. It is supporting audit material for
`report.html`, not a replacement for the reader-facing report.

> **Superseded fixture note (30 July 2026):** the GCD-derived files discussed
> below are no longer bundled. Current release defaults use the independently
> authored `cases/synthetic_pdn/` fixture and `case_thermal.py`. The paths,
> values, and findings below intentionally remain unchanged as evidence for the
> dated revision; they must not be quoted as current release results.

## Verification executed

- `pytest -q -p no:cacheprovider`: 53 passed, 13 deselected.
- `pytest -q -m toolchain -p no:cacheprovider`: 13 passed, 53 deselected.
- Python compile/AST check: all 40 modules in `eda_multiphysics/` parsed successfully.
- Representative module entry points executed successfully: `validate`, `design_loop_demo`,
  `reliability_pipeline`, `tsv_stress`, `anand`, `capacitance`, `creep`, `electromigration`,
  `thermal_runaway`, `transient`, `thermomech`, `pdn_graph`, and `etv_solder`.

## Remediation verification — 12 July 2026

The finding evidence below records the pre-fix state. After remediation:

- fast suite: **64 passed**, 18 deselected;
- toolchain suite: **18 passed**, 64 deselected;
- new integration regressions: **10 passed**;
- manifest-driven footprint: **31.92 × 28.17 µm**, maximum DNP **21.2434257 µm**;
- regenerated layout-map life: minimum **8,882,331 cycles**, median **68,148,820 cycles** for the
  tiny vendored GCD test die (calibration-specific);
- capstone at 0/5/20 mW: mission upper temperature **25.0/63.55/179.20 °C**, solder life
  **121,816/9,480/3,570 cycles**, and Black temperature AF **1.00/55.18/153,411×**;
- vendored power is reported as `scaled_user_scenario` + `area_distributed_proxy`;
- `chip_vtu` has one entry guard and exactly two intentional thermal-regime calls; and
- required-argument CLIs emit `argparse` usage instead of `IndexError`.

Geometry follow-up on the same date added five toolchain regressions for parametric barrel/hourglass
Hex8 meshes, conformal package Tet4 regions, solved strain sensitivity, multi-material assembly, and
the layout-driven package path. All pass as part of the 18-test toolchain tier.

## Original finding evidence (pre-fix)

### Layout DBU mismatch

- `eda_multiphysics/reliability_3d.py:88` defaults to `dbu_per_um=1000.0`.
- `eda_multiphysics/cases/gcd_nangate45/manifest.json:3` declares
  `dbu_per_micron: 2000`.
- With 1,000 DBU/µm, the parsed PDN footprint is 63.84 × 56.34 µm and maximum DNP is
  42.4869 µm.
- With the manifest value of 2,000 DBU/µm, the footprint is 31.92 × 28.17 µm and maximum DNP is
  21.2434 µm.
- The 2,000-DBU result agrees with the manifest core bounds: x = 2.09–34.01 µm.
- `tests/test_toolchain.py` currently asserts the 1,000-DBU-derived footprint and DNP, so the
  regression test preserves the incorrect scale.

### Capstone sensitivity

`reliability_pipeline.run(nx=12, ncyc=2, P_override=P, verbose=False)` produced:

| P | peak ΔT | peak TSV stress | cycle upper temperature | solder life | worst EM J | Blech-immortal |
|---:|---:|---:|---:|---:|---:|---:|
| 0 mW | 0.00000167 K | 0.000000164 MPa | 125.0 °C | 4,537.97 cycles | 104,343,253 A/m² | 78 |
| 5 mW | 38.5485 K | 3.78950 MPa | 125.0 °C | 4,537.97 cycles | 104,343,253 A/m² | 78 |
| 20 mW | 154.195 K | 15.1581 MPa | 179.195 °C | 3,570.44 cycles | 104,343,253 A/m² | 78 |

The thermomechanical stage responds to upstream power. At the default 5 mW scenario, the solder
stage does not change because `reliability_pipeline.py:137` applies
`max(125.0, T_amb + peak_dT)`. The EM stage does not change at any tested power because
`_em_screen_pdn(spice, T_op, ...)` accepts `T_op` at line 67 but does not use it in lines 74–104.

### Power provenance

- `reliability_pipeline.py:48-54` treats the sum of `instance_temperature.csv:power_W` as real
  switching power.
- `gcd_thermal.py:53-58` defines or accepts a total power and distributes it by instance area.
- `gcd_thermal.py:95-102` writes that modeled power into `instance_temperature.csv`.
- The vendored file sums to 0.0050000455 W, while `eda_multiphysics/RESULTS.md:110` identifies
  the real GCD `report_power` result as 8.52 µW and separately labels 5 mW as a scaled scenario.
- `reliability_pipeline.py:175` consequently prints the scaled/model-generated value as
  “real PDNSim power.”

### CLI and example coverage

- `eda_multiphysics/chip_vtu.py:109` and `:113` contain duplicate `__main__` blocks. With valid
  arguments, the full workflow executes twice.
- `eda_multiphysics/gcd_thermal.py:107-108` defaults to an external machine-specific case path
  instead of the vendored case.
- `eda_multiphysics/gcd_thermal.py:95-102` writes back into the supplied case directory.
- `EXAMPLES.md:64` says every demo's numbers are pinned by a gate. The underlying kernels are
  often gated, but the CLI behavior and output semantics of `chip_vtu`, `design_loop_demo`,
  `gcd_thermal`, and several distributed/scaling entry points are not directly protected.

## Interpretation boundary

The original findings did not invalidate the analytic, literature, patch, or serial-versus-MPI
component tests. Their specific unit, handoff, provenance, and CLI limitations are now resolved and
regression-protected. CoupFE-EDA should still be described as an experimental research prototype,
not as a foundry-qualified signoff tool.
