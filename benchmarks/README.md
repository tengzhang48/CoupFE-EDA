# Benchmarks

Benchmarks are fixed studies used to compare a model, numerical method, or
solver configuration. They are distinct from:

- package code in `eda_multiphysics/`;
- guided runnable workflows in `examples/`; and
- automated pass/fail checks in `tests/`.

A benchmark record should identify its source revision, inputs, observable,
hardware or reference source, software environment, run command, raw result,
and interpretation. A retained benchmark at one configuration does not imply
accuracy or performance for other meshes, devices, machines, or rank counts.

## Index

| Benchmark | Purpose | Evidence status |
|---|---|---|
| [`solver_scaling/`](solver_scaling/) | Strong-scaling measurements for the distributed electrothermal FieldSplit solver | Current measurements and historical development records are kept separate |
| [`tsv_curvature_ryu2012/`](tsv_curvature_ryu2012/) | TSV curvature reference metadata from Ryu et al. | Reference manifest |
| [`tsv_mobility_koz_ryu2012/`](tsv_mobility_koz_ryu2012/) | TSV mobility/keep-out-zone reference metadata from Ryu et al. | Reference manifest |
| [`tsv_more_stress_2025/`](tsv_more_stress_2025/) | Additional published TSV-stress case definition | Definition-only manifest unless accompanied by retained comparison output |
| [`tsv_raman_jiang2013/`](tsv_raman_jiang2013/) | Raman-stress comparison metadata from Jiang et al. | Reference manifest; measured comparison remains open |
| [`tsv_release_scorecard.json`](tsv_release_scorecard.json) | Machine-readable status of TSV evidence requirements | Status record, not a benchmark result by itself |

See the [validation guide](../docs/VALIDATION_GUIDE.md) for the distinction
between analytic checks, published references, calibration, and experimental
validation.
