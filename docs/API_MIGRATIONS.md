# Pre-release API migrations

CoupFE-EDA is at an alpha stage, but public names should not disappear without
an explanation. The first public source snapshot exposed several stateful
helpers whose increment acceptance and state-commit behavior was later found to
be unsafe. The current functions use fail-closed increments and one state
commit per accepted increment. The old implementations are not restored as
compatibility wrappers because doing so would silently revive the behavior that
was corrected.

| Earlier name or behavior | Current entry point | Migration note |
|---|---|---|
| `etv_fe.etv_fe_cycle(monolithic=False, ...)` | `etv_fe.thermoviscoplastic_cycle(temperature_model="quasisteady", ...)` | Result fields now include residual telemetry and explicit cycle aggregation. |
| `etv_fe.etv_fe_cycle(monolithic=True, ...)` | `etv_fe.thermoviscoplastic_cycle(temperature_model="lumped_transient", ...)` | The current name states that this is a partitioned lumped-temperature/spatial-mechanics model, not a monolithic `phi-T-u` element. |
| `etv_fe.fe_coupling_effect(...)` | `etv_fe.thermoviscoplastic_comparison(...)` | Returns both complete model records plus `relative_energy_difference`. |
| `anand_3d.solder_joint_cycle_3d(...)` | `anand_3d.prescribed_hex8_cycle(...)` or `anand_3d.solder_joint_bvp_3d(...)` | The fully prescribed one-element state-update exercise and multi-element BVP are now separate APIs. |
| `reliability_3d.critical_joint_bvp_life(...)` | `reliability_3d.critical_joint_bvp_screening(...)` | The new name avoids presenting a calibration-specific Syed mapping as predictive package life and retains selected-object provenance. |
| `solder_joint.stage3(...)` | `solder_joint.cycle_demo(...)` | The descriptive name replaces an internal stage number. |
| `scaling_bench.sweep(...)` and printed-only tables | `python -m eda_multiphysics.scaling_bench ... --output-dir <new-directory>` | The harness now requires retained complete sanitized streams, repeats, environment, and source/Core provenance. |

Two existing functions keep their names but changed defaults and result
records:

- `solder_joint.solder_joint_cycle(...)` now uses fail-closed increment solves,
  separates cold initialization from reported cycle work, and returns
  convergence telemetry.
- `anand_3d.solder_joint_bvp_3d(...)` now defaults to one eight-increment cycle,
  returns a bounded screening/result record, and raises rather than reporting
  an unconverged last iterate.

See the four guided runners in [`EXAMPLES.md`](../EXAMPLES.md) for the current
inputs and output fields. When migrating old scripts, compare the physical
configuration and observable definitions as well as the function name; legacy
numerical baselines should not be copied onto the corrected solver path.
