# Axisymmetric TSV field evidence

This example retains the actual displacement and recovered stress arrays from a
CoupFE finite-element solve. It is intended to make the TSV benchmark
inspectable as data, not merely illustrate a multiphysics concept.

The fixed case is a `30 um` copper via cooled by `-400 K` in a silicon domain
with outer radius `300 um`. The radial mesh has 2,400 Line2 nodes and 2,399
elements. Each node has one radial-displacement degree of freedom. CoupFE's
`newton_solve` solves the axisymmetric plane-strain thermoelastic operator, then
the runner recovers element-center radial stress `sigma_rr` and hoop stress
`sigma_theta`.

From the repository root, after `./setup.sh`, run:

```bash
python examples/tsv_axisymmetric_field/run.py --output-dir /tmp/tsv-field
```

The runner accepts no case-changing options. It writes only these fixed files:

- `field.json`: mesh, connectivity, region labels, full final arrays, and full
  arrays for nine actual CoupFE solves at prescribed temperature changes of
  `0, -50, ..., -400 K`.
- `summary.json`: fixed inputs, exact EDA/Core Git revisions, normalized command
  provenance, mesh/DOF counts, Newton residual evidence, and numerical checks.
- `contour.svg`: a deterministic radial contour and stress profile derived from
  the final recovered arrays.

The nine load records are independent static prescribed-load cases. Their
ordering is useful for visual comparison, but it is **not a transient
simulation** and contains no time integration. No synthetic interpolation is
substituted for those solves.

## Numerical check

At `r = 20 um`, the fixed mesh gives `sigma_rr = 354.1718 MPa`; the published
Lamé equation gives `353.9476 MPa`, a relative difference of about `0.0633%`.
The declared acceptance threshold remains 3%. `expected_results.json` is a
regression oracle for this fixed numerical case, not experimental data.

The equation and material values follow the benchmark already documented in
`eda_multiphysics.tsv_stress` and Choi et al., *Materials* 2021, 14(18):5226
(PMC8472814).

## Claim boundary

Axisymmetric plane-strain thermoelastic component verification against the
declared Lamé equation. It is not a finite-depth 3-D TSV, near-surface device
field, experimental validation, keep-out-zone signoff, or transient cooling
simulation.

The circular SVG is an axisymmetric reconstruction of the one-dimensional
radial field.

## Rebuild the website media bundle

The checked website bundle is generated only from a clean CoupFE-EDA checkout
and the clean Core revision pinned by `setup.sh`. Install the two rendering
dependencies, then write to a new directory outside this repository:

```bash
python -m pip install "Pillow>=10" "imageio-ffmpeg>=0.5"
python examples/tsv_axisymmetric_field/build_visual_evidence.py \
  --output-dir /tmp/coupfe-tsv-visual-evidence
python -m eda_multiphysics.visual_evidence \
  /tmp/coupfe-tsv-visual-evidence/visual-evidence.json
```

`load-sweep.webm` repeats only the nine retained solved states in forward and
reverse order. It uses piecewise-linear spatial sampling of the radial arrays
for display, but does not interpolate between load states. The manifest binds
the four generated artifacts to exact byte sizes and SHA-256 digests and
records the EDA/Core revisions, field semantics, renderer configuration, and
the non-transient interpretation.
