# 3-D SAC305 solder cycle

This example runs the stateful `solder_joint_bvp_3d` path and prints one
deterministic JSON record. It exercises nonlinear element assembly, equilibrium,
and accepted-state transfer across an idealized cold-to-hot-to-cold cycle.

## Inputs and configuration

- Project-authored `0.1 x 0.1 x 0.1 mm` regular `3 x 3 x 2` Hex8 block
  (18 elements), with a fixed bottom face, a rigidly displaced top face, and
  traction-free lateral faces.
- SAC305 Anand parameters from `eda_multiphysics.anand_3d.SAC305_3D`.
- Representative project-model elastic inputs `E = 43,000 MPa` and `nu = 0.40`.
- One `-40 -> 125 -> -40 degC` cycle over 1600 s, resolved by eight
  endpoint-inclusive increments.
- Thermal-expansion mismatch `delta_alpha = 14.4e-6 /K` and the idealized
  geometric loading ratio `L_D/h = 6`.

From the repository root, after installing the project as described in the
top-level README, run:

```bash
python examples/solder_3d_cycle/run.py
python examples/solder_3d_cycle/run.py --check
```

`--check` compares selected values with `expected_results.json` and exits
nonzero on a mismatch. It does not create files in the repository.

## Output

`dW_element_MPa` is the increment-summed, Gauss-point-mean inelastic energy
density for each element over the cycle. Here MPa is numerically equivalent to
MJ/m^3. The JSON also reports the peak and block mean, their ratio, imposed
engineering-shear range, maximum Newton iterations, and the largest final
residual expressed as a fraction of the solver's acceptance limit. The solver
returns a result only after every increment has met that limit and committed
state once.

The checked baseline is `dW_peak = 0.389021 MPa`, `dW_mean = 0.343364 MPa`,
and peak/mean `= 1.13297`. `expected_results.json` is a regression record, not
an experimental oracle.

## Provenance and references

The geometry and loading are project-authored. The Anand constants follow
Motalab, Cai, Suhling, and Lall, “Determination of Anand Constants for SAC
Solders Using Stress-Strain or Creep Data,” ITherm 2012, pp. 910–922,
doi:10.1109/ITHERM.2012.6231522, with the related Motalab Auburn dissertation
(2013). The elastic modulus and Poisson ratio are separate representative
project-model inputs. Equations, implementation checks, and the complete
citation are collected in
[`../../docs/theory.md`](../../docs/theory.md). Current numerical evidence is
summarized in
[`../../eda_multiphysics/RESULTS.md`](../../eda_multiphysics/RESULTS.md).

## Limitations

This is an idealized regular block, not an imported package geometry. One cycle,
mesh, and load-step choice does not establish stabilized-cycle response,
mesh/load-step convergence, a physical crack location, or predictive package
life. The example is useful for inspecting the implemented stateful solver and
its dissipation field within those stated inputs.
