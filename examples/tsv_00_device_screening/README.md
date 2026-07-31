# TSV-to-device screening preview

This is the first executable slice of the multilevel TSV release plan. It uses a 10 µm Cu TSV,
−250 °C cooling load, (001) silicon, Ryu's published n/p piezoresistance coefficients, 32 stable
**synthetic** device IDs from `device_sites.csv`, and a fixed 5% KOZ threshold. The underlying
screening API accepts a threshold, but this example CLI currently exposes only `--output-dir`.
It demonstrates:

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

`run.py` reads only `device_sites.csv`. The geometry, cooling load, threshold, and TSV ID are
currently fixed in code. `case.json` documents those fixed choices, `materials.json` records the
literature provenance of constants implemented in `eda_multiphysics.tsv_device`, and
`expected_metrics.json` is used by the regression test rather than by the example at runtime.
See [`../REFERENCES.md`](../REFERENCES.md) for the complete input-role and claim-status map.

The stress input is the project's validated classical Lamé far-field solution, converted to a full
axisymmetric tensor. That makes this a realistic-dimension integration preview, not the release
validation case. It does **not** reproduce the anisotropic free-surface stress 0.2 µm below the die
surface, and it must not support claims about measured Raman curves, transistor delay, Cu
protrusion, or signoff KOZ. The Raman and anisotropic 3-D FE gates in the release plan remain
blocked until their benchmark data and full local model are frozen.

Primary model source: S.-K. Ryu et al., IEEE TDMR 12 (2012), 255–262,
doi:10.1109/TDMR.2012.2194784.
