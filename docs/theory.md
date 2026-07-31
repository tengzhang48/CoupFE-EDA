# Model equations and references

This document summarizes the equations implemented by the public examples and
the evidence used to check them. Notation follows small-strain mechanics unless
a finite-deformation quantity is stated explicitly.

## Scalar transport

Thermal conduction, electric conduction, and electrostatics share the steady
diffusion form

```text
-div(kappa grad(u)) = f
```

with Dirichlet and Neumann boundary data. The weak form used by `fe.solve_field`
is

```text
integral(kappa grad(u) . grad(v))
    = integral(f v) + boundary_flux_terms.
```

An electrode current or total heat reaction is the assembled residual summed
over the constrained boundary nodes. Reference checks include a linear patch,
Ohm's law, a manufactured source problem, and the `(pi/L)^2 alpha` transient
eigenmode.

The PDN graph uses the corresponding resistor-network Laplacian,

```text
sum_e g_e (V_a - V_b) = I_a,
```

with a SciPy assembly comparison and a closed-form reference for the bundled
synthetic grid.

## Electrothermal coupling

The spatial electrothermal examples solve

```text
-div(sigma(T) grad(phi)) = 0
-div(k grad(T))          = sigma(T) |grad(phi)|^2
sigma(T)                 = sigma0 / (1 + alpha T).
```

Temperature affects electrical conduction, and electrical power supplies the
thermal source. `etv_fe` places `phi` and `T` in one Quad4 Newton system;
`etv_solder.solve_et` supplies a sequential comparison. For constant
conductivity, the one-dimensional slab reference has

```text
peak temperature rise = sigma0 V0^2 / (8 k).
```

The generated three-dimensional examples apply the same equations on selected
Hex8 and Tet4 meshes. Agreement at those selected meshes does not qualify
arbitrary geometry or material data.

## Thermomechanics

The compiled three-dimensional examples use a compressible neo-Hookean solid
with isotropic thermal pressure. With deformation gradient `F`, `J=det(F)`,
shear modulus `G`, bulk-like coefficient `K`, and thermal coefficient `alpha`,
the implemented first Piola stress is

```text
P(F,T) = G (F - F^-T) + K log(J) F^-T - K alpha T F^-T.
```

The associated small-strain relation is

```text
sigma = 2 G epsilon + K tr(epsilon) I - K alpha T I.
```

The reference cases are uniform free expansion, a constrained block, a
bimetal strip, a pressurized cylinder, a thermal-gradient cylinder, and a
two-material TSV cylinder. Each comparison applies to its stated material law,
geometry, and boundary conditions.

The local blind-TSV model uses linear thermal eigenstrain,

```text
sigma  = C : (epsilon - alpha DeltaT I)
K_e    = integral(B^T D B)
f_e_th = integral(B^T D epsilon_th).
```

Cu and SiO2 use isotropic stiffness. Silicon uses the declared cubic constants
and a proper crystal-to-global rotation. Engineering Voigt order is
`[exx, eyy, ezz, gamma_xy, gamma_yz, gamma_xz]`. Full element stress is
recovered before a Raman or mobility proxy is calculated.

## Periodic displacement constraints

For matched points on opposing faces separated by lattice vector `a`, the EDA
adapter creates

```text
u_plus - u_minus = Hbar a,
```

where `Hbar` is supplied explicitly. Core compiles the relations into
`U = P q + U0` and solves the reduced residual and tangent,

```text
R_q = P^T R(U)
K_q = P^T K(U) P.
```

The EDA adapter resolves face, edge, and corner equivalence classes and adds a
representative anchor to remove rigid translation. Current checks cover
homogeneous free-expansion/fixed-box controls and a generated heterogeneous
cell. Selecting a source-equivalent macroscopic/bottom boundary condition and
showing corrected-scene mesh convergence remain future work.

## Anand viscoplasticity

The material-point and state-update examples use an Anand-type unified model:

```text
epdot = A exp(-Q/(R T)) [sinh(xi sigma_eq/s)]^(1/m)
sdot  = h0 |1 - s/s_star|^a sign(1 - s/s_star) epdot
s_star = s_hat [(epdot/A) exp(Q/(R T))]^n.
```

Included parameter sets are documented in `anand.py` and `anand_3d.py` with
their literature sources. Checks compare the uniaxial integrator with the
saturation relation and selected digitized values from Motalab, and compare the
three-dimensional return map with the one-dimensional transient.

`prescribed_hex8_cycle` prescribes all boundary displacements of one Hex8 and
exercises the state/commit path. It does not solve a multi-element joint
boundary-value problem. A previously explored stateful plane-strain/transient
FE extension is absent because its increments did not meet the stated
convergence criterion.

## Reliability mappings

The examples include these established engineering relations:

- CTE-mismatch/DNP shear: `Delta gamma = Delta alpha DeltaT L_D / h`;
- Syed energy mapping: `N_f = 1/(W' Delta W)`;
- Darveaux crack-initiation and growth mappings;
- Black electromigration acceleration; and
- the Blech `jL` threshold.

`Delta W` is a constitutive/model output. A mapped `N_f` also depends on the
selected calibration, units, geometry reduction, and mission profile. The
included 4719-cycle Motalab PBGA value is an in-sample reproduction check, not
independent life prediction evidence.

## TSV device observables

The local model can derive the in-plane Raman stress sum

```text
sigma_Raman = sigma_xx + sigma_yy
```

at explicitly requested points or Gaussian spot quadrature points. Mobility
and KOZ functions implement published piezoresistive equations and declared
thresholds. These transformations check equation implementation and preserve
device IDs; they require measured stress/device data before they can support a
real-device claim.

## Discretization and nonlinear solution

The examples use structured Quad4/Hex8 elements and Gmsh-generated Hex8/Tet4
meshes. Generated coupled kernels use CoupFE weak-form/code-generation support.
Smooth element residuals can use complex-step differentiation for tangent
construction. Anand return maps contain nonsmooth/root-finding operations and
therefore use their specified elastic or modified-Newton tangent path.

EDA operators implement CoupFE's `residual`, `tangent`, and `commit` contract.
`newton_solve` commits state after its iteration loop; the returned iteration
count is not a convergence flag. An EDA caller must establish convergence
independently and must not repeat that state update. Mesh quality, boundary
sets, units, region identity, and convergence remain part of the problem
definition.

## Interpretation of evidence

The repository distinguishes:

- analytic or manufactured-solution comparisons;
- patch and mesh-refinement checks;
- independent implementation comparisons;
- balance, invariant, topology, and broken-control checks;
- in-sample literature reproduction; and
- synthetic interface demonstrations.

A check supports the equation, implementation path, input, and tolerance that
it names. It does not transfer automatically to a different geometry,
material, mesh, process, or device. Test commands and the current open evidence
items are described in [Validation guide](VALIDATION_GUIDE.md) and
[Roadmap](roadmap.md).

## References

- S. Timoshenko, “Analysis of Bi-Metal Thermostats,” 1925.
- S. Timoshenko and J. N. Goodier, *Theory of Elasticity*, Art. 152.
- Choi et al., “Thermal Stress Analysis of Through-Silicon Via,” *Materials*
  14(18):5226, 2021.
- Motalab, Cai, Suhling, and Lall, “A Study of Anand Constitutive Model
  Constants for SAC305 Solder,” ITherm 2012; Motalab, Auburn dissertation,
  2013.
- Cheng et al., “Viscoplastic Constitutive Relation of Solder Alloys,”
  *Soldering & Surface Mount Technology* 12(2), 2000.
- Syed, “Accumulated Creep Strain and Energy Density Based Thermal Fatigue Life
  Prediction Models for SnAgCu Solder Joints,” ECTC 2004.
- Darveaux, “Effect of Simulation Methodology on Solder Joint Crack Growth
  Model and Thermal Fatigue Life Prediction,” *Advancing Microelectronics*,
  2000.
- Dandu et al., “Current Crowding in Interconnects,” *Microelectronics
  Reliability* 50(4):547, 2010.
- Black, “Electromigration — A Brief Survey and Some Recent Results,” *IEEE
  Transactions on Electron Devices*, 1969.
- Blech, “Electromigration in Thin Aluminum Films on Titanium Nitride,”
  *Journal of Applied Physics*, 1976.
- Ryu et al., “Effect of Thermal Stresses on Carrier Mobility and Keep-Out Zone
  Around Through-Silicon Vias for 3-D Integration,” IEEE TDMR, 2012,
  doi:10.1109/TDMR.2012.2194784.
- Jiang et al., “Measurement and analysis of thermal stresses in 3D integrated
  structures containing through-silicon-vias,” *Microelectronics
  Reliability*, 2013, doi:10.1016/j.microrel.2012.05.008.
- JEDEC JESD22-A104, JEDEC JEP119, and IPC-9701.
