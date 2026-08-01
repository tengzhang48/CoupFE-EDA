# Design-linked 3-D solder screening

This example selects a maximum-distance-to-neutral-point joint from the bundled
synthetic design map, retains its joint/source identity, and uses its `L_D` to
drive the stateful 18-Hex8 solder-block example. It prints one deterministic
JSON record.

## Inputs and configuration

- Project-authored synthetic joint map at
  `eda_multiphysics/cases/synthetic_pdn/joints.csv`, with provenance metadata in
  the sibling `joints.meta.json`.
- Four corner objects (`SYNTH_J00`, `SYNTH_J02`, `SYNTH_J20`, and
  `SYNTH_J22`) tie at the maximum DNP. The stable rule selects the first tied
  row, `SYNTH_J00`, linked to PDN object `VDD_20000_20000_1`; its `L_D` is
  `42.4264 um` from the declared synthetic neutral point and coordinate frame.
- Caller study input `h_solder = 50 um`, producing `L_D/h = 0.848528`.
- Regular `0.1 x 0.1 x 0.1 mm`, `3 x 3 x 2` SAC305 Hex8 block, one
  `-40 -> 125 -> -40 degC` cycle over 1600 s, and eight endpoint-inclusive
  increments. The separate representative elastic inputs are
  `E = 43,000 MPa` and `nu = 0.40`.
- Syed screen coefficient `W' = 0.0019 /MPa`, the corrected hyperbolic-sine
  value used by the package's calibration-specific mapping.

The map deliberately leaves per-joint diameter and height blank, so the JSON
reports them as `null`. The `50 um` screening height is a study input used to
form `L_D/h`; it is not recovered from the joint map and does not geometrically
size the regular FE block.

From the repository root, after installing the project as described in the
top-level README, run:

```bash
python examples/design_linked_solder_screening/run.py
python examples/design_linked_solder_screening/run.py --check
```

`--check` compares selected values with `expected_results.json` and exits
nonzero on a mismatch. It does not create files in the repository.

## Output

The provenance and selected-object sections show the tied maximum-DNP objects,
the deterministic row-order tie break, and exactly which identity supplied
`L_D`. `dW_element_MPa`, its peak and mean, and the residual telemetry describe
the stateful block solve. Here MPa is numerically equivalent to MJ/m^3.
`Syed_calibration_screen_cycles` applies the checked Syed algebraic mapping to
the peak energy value.

The checked baseline retains `SYNTH_J00` / `VDD_20000_20000_1`, gives
`dW_peak = 0.0111335 MPa`, and reports a calibration-specific screen of 47,273
cycles. `expected_results.json` is a regression record, not measured package
data or a lifetime oracle.

## Provenance and references

The input map, geometry, and loading are project-authored. SAC305 Anand
constants follow Motalab, Cai, Suhling, and Lall, “Determination of Anand
Constants for SAC Solders Using Stress-Strain or Creep Data,” ITherm 2012,
pp. 910–922, doi:10.1109/ITHERM.2012.6231522, and Motalab's Auburn dissertation
(2013). The elastic inputs are separate representative project choices. The
energy-to-life equation is the Syed ECTC 2004 mapping.
Equations, limits, and full citations are in
[`../../docs/theory.md`](../../docs/theory.md); the joint-map contract is
documented in [`../../docs/api.md`](../../docs/api.md). Current numerical
evidence is summarized in
[`../../eda_multiphysics/RESULTS.md`](../../eda_multiphysics/RESULTS.md).

## Limitations

The design map is synthetic and the FE model is an idealized regular block, not
the mapped joint's package geometry. Only identity and `L_D` cross the design
handoff. The study-input height, one mesh, and one load-step choice do not
establish stabilized-cycle response, mesh/load-step convergence, crack
location, or predictive package life. The Syed result is a
calibration-specific screening value.
