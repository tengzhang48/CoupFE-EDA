# TSV-to-device screening preview

This demonstration uses a 10 µm Cu TSV, a −250 °C cooling load, (001) silicon,
Ryu's published n/p piezoresistance coefficients, 32 stable **synthetic** device
IDs from `device_sites.csv`, and a fixed 5% screening threshold. The underlying
API accepts a threshold; this example CLI exposes `--output-dir`. It covers:

- stress-tensor → channel-oriented mobility proxy;
- stable source-object, TSV, and device identity plus coordinate back-annotation;
- n/p and [100]/[110]/[1-10] orientation handling; and
- a deterministic orientation action followed by re-screening.

Run from the repository root:

```bash
python examples/tsv_00_device_screening/run.py
python examples/tsv_00_device_screening/run.py --output-dir /tmp/tsv_device_preview
```

The output directory contains `device_screening.csv`, a machine-readable `evidence.json`, and a
two-panel `device_screening.svg` physical back-annotation view. Hovering a device in the SVG shows
its device/source IDs, carrier, selected channel direction, and mobility proxy.

The runtime input read by `run.py` is `device_sites.csv`. The geometry, cooling
load, threshold, and TSV ID are fixed in code. `case.json` documents those fixed
choices, `materials.json` records the literature provenance of constants
implemented in `eda_multiphysics.tsv_device`, and `expected_metrics.json` is
used by the regression test rather than by the example at runtime.
See [`../REFERENCES.md`](../REFERENCES.md) for the complete input-role and claim-status map.

The stress input is a classical Lamé far-field solution, converted to a full
axisymmetric tensor and checked against the corresponding idealized equation.
This is a **DEMONSTRATION** of the data mapping. It does not reproduce the
anisotropic free-surface stress 0.2 µm below the die surface and does not support
claims about measured Raman curves, transistor delay, Cu protrusion, or a
signoff keep-out zone. Those claims require benchmark data, a qualified local
model, convergence evidence, and retained comparison output.

Primary model source: S.-K. Ryu et al., IEEE TDMR 12 (2012), 255–262,
doi:10.1109/TDMR.2012.2194784.
