# Validation-guide figure maintenance

The PNG files in `figures/` are retained, project-authored documentation
artifacts. Their source of truth is `generate_figures.py`; edits should be made
in the generator and then reproduced, rather than applied directly to a PNG.
These figures summarize named checks. They do not add evidence or broaden the
qualification boundary of the underlying code, tests, or retained results.

## Symbols in the reliability schematic

The reliability figure uses $\Delta u$ for the imposed lateral displacement of
the solder joint's top cap relative to its fixed bottom cap. It is not a
derivative. In the distance-to-neutral-point (DNP) approximation,

$$
\Delta u = \Delta\alpha\,\Delta T\,L_D,
\qquad
\gamma \approx \frac{\Delta u}{h}.
$$

Here $\Delta\alpha$ is the die/substrate coefficient-of-thermal-expansion
mismatch, $\Delta T$ is the temperature change, $L_D$ is the joint's distance
from the neutral point, and $h$ is the joint height. This is the same loading
implemented by `reliability_3d.solve_solder_joint` and checked by
`test_reliability_3d_solder_joint`. The public equations and scope are recorded
in [Theory](../theory.md) and
[`reliability_3d.py`](../../eda_multiphysics/reliability_3d.py).

The `traction-free` annotation in the TSV schematic marks the outer radial
surface of the idealized reference geometry. It is drawn vertically beside
that surface so it remains associated with the boundary without entering the
neighboring stress plot.

## Regeneration process

Run commands from the repository root. Regenerate only an edited figure during
review so unrelated retained PNGs do not change because of a local Matplotlib
or font difference:

```bash
python -c 'from docs.validation_guide.generate_figures import fig_tsv_stress; fig_tsv_stress()'
python -c 'from docs.validation_guide.generate_figures import fig_toolchain_reliability; fig_toolchain_reliability()'
```

To intentionally regenerate the complete set:

```bash
python docs/validation_guide/generate_figures.py
```

Record the Python, Matplotlib, and font environment when a broad regeneration
is intended. PNG bytes can change across rendering environments even when the
plotting code and numerical content do not.

## Review and website flow

After regeneration:

1. Inspect each changed PNG at full resolution. Check the global title, panel
   titles, labels, equations, panel gutter, and plot bounds for overlap or
   clipping.
2. Confirm that schematic equations and boundary labels agree with the code,
   tests, and `docs/theory.md`. A presentation edit must not silently change a
   model definition or evidence claim.
3. Review the targeted source and image diff, then run the whitespace check:

   ```bash
   git diff -- docs/validation_guide/generate_figures.py docs/validation_guide/figures
   git diff --check
   ```

4. From `web/`, run `npm run prepare:data`. This checks every linked source and
   copies the selected retained figures to the generated
   `public/repository-assets/validation-guide/` directory.
5. Run `npm run check` to exercise repository-data checks, frontend tests, type
   checking, and the production website build. Inspect the built page at both
   desktop and narrow viewport widths when figure dimensions or captions
   change.

The generated website copies are ignored build products. Commit the generator,
the reviewed PNGs under `docs/validation_guide/figures/`, and any changed public
caption or maintenance documentation; do not commit the copied web assets.

## Layout correction record: 2026-08-02

This update began with a visual review of the two retained PNGs and then traced
their labels back through the plotting source, implementation, tests, and
theory before changing presentation:

- In `tsv_stress.png`, the horizontal `traction-free` label crossed the panel
  gutter and overlapped the neighboring stress plot's vertical axis label. The
  annotation was rotated vertically and centered beside the outer surface.
- In `toolchain_reliability.png`, the global title and the two-line panel titles
  occupied the same top band. A separate top layout band was reserved so both
  panels and their subtitles begin below the global title.
- The reliability schematic's plain `du` was traced to the imposed top-cap
  displacement in `solve_solder_joint` and its toolchain regression. It was
  relabeled as $\Delta u$, its DNP equation was added, and the loading arrow was
  made horizontal to match the implemented x-direction shift.
- The website caption was changed to identify the same DNP relation. No solver
  source, numerical input, retained result, tolerance, test status, or evidence
  boundary changed.

After the first publication, a same-day visual follow-up moved the complete
red top-cap-shift annotation farther right so its text begins outside the gray
joint schematic. The equation, arrow direction, model definition, and panel
layout were unchanged.

Only the two affected functions were regenerated, using Python 3.13.9 and
Matplotlib 3.11.0. Their retained SHA-256 digests are:

```text
3752b89c72cd9048388408c03904055c677eaa85e97e412efe23489f2a9eaf56  tsv_stress.png
a6eeb67cb4f721d96ba34147d10f5bcbc4122e1aa1891f979bbcc93edc3863ab  toolchain_reliability.png
```

Both PNGs were inspected at full resolution for title, equation, gutter, and
boundary-label clearance. For the first figure commit, `npm run check` passed
35 frontend tests, repository-data validation, type checking, asset
preparation, and the production demo build. After the same-day annotation
position and public-interface wording follow-up, the complete command passed
36 frontend tests and the same data, type, asset, and build checks. The
prepared website copies had the same SHA-256 digests as the retained source
PNGs.

A first unpinned `python -m pytest -q` attempt found an older installed Core
package and stopped during collection because that package did not contain
`coupfe.constraints`. Repeating the command with `PYTHONPATH` set to the
documented public Core checkout at
`e2f42ed5772850a0a23a2ce434f430c287eae5c8` passed 122 tests, skipped one, and
deselected 20 optional toolchain tests. This distinction is retained because
dependency identity is part of the evidence, even though the initial failure
was not an EDA test failure.

A temporary wheel and source distribution were also built. The artifact guard
checked the 262-file source inventory, 77-file wheel, and 270-file source
distribution, including this maintenance record and the regenerated figures.
The check used the explicit dirty/untracked audit allowances because it ran
before the edits were committed, so it was a packaging review rather than a
release checkpoint. The temporary artifacts were removed after the check.
