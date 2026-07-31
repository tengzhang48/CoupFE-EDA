# CoupFE-EDA — theory of the simulation models

The governing equations, weak forms, constitutive laws, discretization, and the evidence used for
numerical or model verification, in one place. Each block points at the implementing module and the
applicable analytic/published oracle, independent comparison, invariant, or structural check.
Notation: `∇` spatial gradient, `·` dot,
`:` double contraction, `I` identity, `tr` trace, `sym(A)=½(A+Aᵀ)`. Reference config quantities use
the deformation gradient `F = I + ∇u`, `J = det F`.

The whole suite is built on one abstraction — the **operator contract** (`residual`, `tangent`,
`commit`) with `newton_solve` — and one trick: the consistent tangent is obtained by **complex-step
differentiation** of the residual (exact to machine precision, no hand-coded Jacobian) wherever the
residual is complex-analytic. See §6 for where that holds and where it doesn't.

---

## 1. Scalar transport (diffusion): thermal / electrical / electrostatic

One operator covers steady conduction in all three guises (`fe.solve_field`). Strong form on Ω:

    -∇·(κ ∇u) = f ,   u = ū on ∂Ω_D ,   κ ∂u/∂n = q̄ on ∂Ω_N

with `u` = temperature / electric potential / electrostatic potential and `κ` = thermal / electrical
conductivity / permittivity. Weak form (test `v`):

    ∫_Ω κ ∇u · ∇v dΩ  =  ∫_Ω f v dΩ + ∫_∂Ω_N q̄ v dΓ .

**Reaction flux** (the rigorous electrode current / total heat): `Q = Σ_{a∈S} R_a`, the assembled
residual at the constrained node set `S` — not a gradient guess.
*Oracles:* linear patch (`u=x/L`, exact); Ohm `I=σV₀W/L`; the parabolic source solution; the
`(π/L)²α` first transient eigenmode. *PDN:* a resistor-network Laplacian `Σ_e g_e (Δφ)` (`pdn_graph`,
`pdn_distributed`), validated vs an independent scipy assembly. The bundled synthetic grid also
has a closed-form nodal-voltage reference; caller-supplied cases may carry a separately labeled
PDNSim comparison.

## 2. Coupled electro-thermal (φ, T) — `etv_kernel`, `etv_3d`, `etv_distributed_fs`

Two scalar transport fields per node, generated from one weak form by `coupfe.codegen`:

    φ:  -∇·(σ(T) ∇φ) = 0                 (charge conservation; flux = σ(T)∇φ, storage 0)
    T:  -∇·(k ∇T)    = σ(T)|∇φ|²         (heat conduction with Joule source)

temperature-dependent conductivity `σ(T) = σ₀ / (1 + αT)` couples T→φ; the Joule term `σ|∇φ|²`
couples φ→T. Weak form for each field `w∈{φ,T}`: `∫ (storage_w) Ñ + (flux_w)·∇Ñ = 0`. Both cross
blocks `∂R_φ/∂T`, `∂R_T/∂φ` are in the complex-step tangent — one monolithic Newton block, not a
field split. *Oracle (the closed limit):* the **1-D self-heating** of a slab between two voltage
plates with `α=0`,

    peak ΔT = σ₀ V₀² / (8k)        (validated to ~1e-16 serial, 2e-16 compiled).

## 3. Thermo-mechanical (u, T) — `thermomech_kernel`, `thermomech_3d`, `thermomech_tsv`

A compressible neo-Hookean solid with an isotropic **thermal pressure** and Fourier conduction
(4 dof/node: `u_x,u_y,u_z,T`). First Piola–Kirchhoff stress:

    P(F,T) = G (F − F⁻ᵀ) + K ln(J) F⁻ᵀ − K α T F⁻ᵀ ,
    momentum:  ∫ P : ∇v = 0 ;   heat:  ∫ (c_T Ṫ) θ + (−κ C⁻¹ ∇T)·∇θ = 0 ,  C = FᵀF .

**Small-strain limit** (the bridge to linear thermo-elasticity, used for all the closed forms):
with `F=I+H`, `ε=sym H`,

    σ ≈ 2G ε + K tr(ε) I − Kα T I   ⇒   μ=G, λ=K, thermal-stress coefficient β = Kα .

*Oracles (exact for this law at uniform T = ΔT):*
- **free expansion** — stress-free isotropic stretch `λ` solving `G(λ²−1) + 3K ln λ = K α ΔT`, with
  `u(X) = (λ−1)X` (linear ⇒ trilinear Hex8 nodally exact, ~2e-13);
- **constrained block** — `u=0`, hydrostatic `σ = −K α ΔT` (broken control for the above);
- **plane-strain composite cylinder** (Cu core r<a / Si annulus a<r<b, traction-free wall) — the TSV
  thermal-mismatch field. With `u(r)=C r + D/r` (D=0 in the core) and `σ_r = 2G ε_r + K(ε_r+ε_θ) −
  Kα ΔT`, the three constants `C_c, C_a, D_a` come from `u`- and `σ_r`-continuity at `r=a` and
  `σ_r(b)=0`. (The Lamé-family oracle the project trusts for TSV stress, here in 3-D on a gmsh mesh;
  `u_r` matched to ~1e-3, converging.)

### Anisotropic small-strain local TSV — `tsv_local_3d`

The blind Cu/oxide/Si submodel uses the linear thermal-eigenstrain form

    sigma = C : (epsilon - alpha deltaT I),
    K_e = integral(B^T D B) dV,       f_e^th = integral(B^T D epsilon_th) dV,

with constant `B` in each Tet4. Cu and SiO2 use isotropic `D`; silicon uses cubic
`C11=166.2 GPa`, `C12=64.4 GPa`, `C44=79.8 GPa`, rotated by the declared proper
crystal-to-global matrix. The engineering-Voigt order is
`[exx, eyy, ezz, gamma_xy, gamma_yz, gamma_xz]`, so tensor shear strain is half the engineering
component and `D44=C44`. Full element stress is recovered before any device proxy is calculated.

For (001) backscattering, the held measurement is

    sigma_Raman = sigma_xx + sigma_yy,       z = -0.2 micrometers.

The code can return constant-element stress or an explicitly volume-weighted nodal recovery with
barycentric interpolation, plus a consistent P1 L2 projection. Recovery is a declared numerical
choice, not experimental calibration. Likewise, six minimal pins remove only rigid modes; they do
not represent an infinite matrix. The isolated-domain sensitivity can instead prescribe silicon's
free thermal displacement `u=alpha_Si deltaT x` on the outer/bottom boundary. Neither substitutes
for the periodic array or future global–local boundary data.
The local geometry includes an oxide bottom cap as well as the sidewall; direct Cu/Si contact at the
blind tip is a rejected topology. Every solve records its boundary label, coordinate frame,
crystal-to-global rotation, and SHA-256 digests of the material and mesh inputs.

The Jiang geometry foundation uses a full cell with pitches 40 µm along `[110]` and 50 µm along
the sign-equivalent `[-110]` global direction. Gmsh now constructs matching `x-/x+` and `y-/y+`
surface meshes, and CoupFE independently verifies a strict translated-node bijection. For each
opposite-face pair separated by lattice vector `a`, the mechanical constraint is

    u_plus - u_minus = Hbar a,

where `Hbar` is an explicitly supplied macroscopic displacement gradient. The resulting affine MPC
is compiled as `U=Pq+U0`; equilibrium and tangent are solved exactly in the admissible space as
`Rq=P.T R(U)` and `Kq=P.T K(U) P`. Edge and corner relations are collapsed into consistent
equivalence classes, a representative node is anchored only to remove rigid translation, and the
full accepted displacement is used for stress recovery. Opposite-face traction anti-periodicity
then follows from reduced weak equilibrium; it is checked as a diagnostic rather than imposed as a
second set of constraints.

The homogeneous-Si control with `Hbar=alpha_Si*dT*I` reproduces free expansion with displacement
error `3.72e-23 m`, stress below `1e-11 MPa`, reduced residual `4.94e-14`, and zero MPC error. Its
deliberately wrong zero-jump control develops about `29.1 MPa`, proving that a fixed periodic box is
not a neutral thermal default. The heterogeneous Cu/oxide/anisotropic-Si cell also reaches reduced
residual `1.72e-14` with zero MPC error. These gates qualify the serial constraint algebra and its
EDA integration; they do not select the Jiang source-equivalent macro/bottom boundary condition or
validate a Raman curve.

The existing coarse refinement study used the superseded sidewall-only topology and fails the ≤2%
release criterion. Corrected periodic-scene mesh/domain/recovery convergence, source-equivalent
boundary semantics, and distributed MPC therefore remain release-blocking.

## 4. Viscoplasticity — Anand unified model — `anand`, `solder_joint`, `anand_3d`, `etv_solder`

Rate-dependent solder plasticity. Equivalent viscoplastic strain rate and internal (deformation)
resistance `s`:

    ε̇_p = A exp(−Q/RT) [ sinh(ξ σ/s) ]^{1/m} ,
    ṡ   = h₀ |1 − s/s*|^a sign(1 − s/s*) ε̇_p ,   s* = ŝ ( ε̇_p/A · e^{Q/RT} )^n .

Saturation (`s→s*`, `ε̇_p→ε̇`): `z = (ε̇/A) e^{Q/RT}`, `s* = ŝ z^n`, `σ_sat = (s*/ξ) asinh(z^m)`.
9 constants `(A, Q/R, ξ, m, ŝ, h₀, n, a, s₀, E)` — published SnPb and **SAC305** sets (cross-checked
across 3 sources). *Oracles:* the integrator vs its own analytic saturation (0.02%, rigorous); the
closed form vs the **Motalab Fig 3.10** SAC305 curve (~4–10%, figure-digitization). Sign-safe flow +
stiff BDF / bracketed Brent return map (the `(1−s/s*)^a`-goes-negative hazard). The 3D Hex8 return
map is checked against the full uniaxial-stress transient, not only saturation, and integrates the
resistance evolution exactly for fixed `s*` over the plastic increment, avoiding explicit hardening
overshoot for high-`h0` SAC305 fits.

## 5. Reliability — fatigue life and damage

- **JEDEC JESD22-A104** thermal cycling drives the CTE-mismatch strain `ε = Δα (T − T_ref)`; the
  Anand law gives the **stabilized inelastic strain-energy density per cycle** `ΔW` (mesh-objective).
- **Distance-to-neutral-point (DNP)** solder shear (the classic flip-chip oracle):
  `Δγ = Δα ΔT L_D / h` (`L_D` = joint distance from the die centre, `h` = joint height). The 3-D FE
  reproduces it under the imposed DNP displacement (`reliability_3d`); `anand_3d` stores the Anand
  state at Hex8 Gauss points and computes mesh-averaged `ΔW` directly.
- **Energy life:** Syed `N_f = 1/(W′ ΔW)` (W′=0.0019/MPa); Darveaux crack-init+growth. `ΔW` is the
  stronger numerical output; `N_f` is calibration-specific. The measured Motalab 19 mm PBGA
  4719-cycle case is reproduced within ±2× as an **in-sample calibration check**, not independent
  validation. *Layout-driven*: each joint's
  `L_D` is read from the preferred versioned joint map (`design_joints`); PDN `NET_x_y_layer`
  decoding remains a provenance-labeled proxy fallback. The bundled nine-point map is explicitly
  project-authored synthetic proxy data.
- **Electromigration:** Black `MTTF ∝ J⁻ⁿ exp(E_a/kT)`; Blech immortality product `(jL)_c`.
- **TSV thermo-elastic stress:** Lamé `σ_r(r) ∝ −(D/2r)²` (validated 0.06% in 2-D axisymmetric).
- **Warpage:** Timoshenko 1925 bimetal curvature; Timoshenko–Goodier gradient hollow cylinder.

## 6. Discretization and numerics

- **Elements (codegen).** Weak form → Fortran UEL via `coupfe.codegen` (Quad4/8, **Hex8/Hex20**, and
  native core **Tet4/Tet4r** for
  gmsh's native arbitrary-CAD meshing) → f2py. One **batched** compiled call per assembly (no Python
  element loop). The element
  tangent is the **complex-step** derivative of the residual — exact, automatic — valid for the
  *smooth* couplings (σ(T), Joule, thermal stress). It does **not** apply to the Anand return map
  (`brentq`/`abs`/`sign` are not complex-analytic) → that uses the elastic/modified-Newton tangent.
- **Newton.** One shared serial driver `_coupled_solve.coupled_newton(groups, ndof, dirichlet,
  linsolve)`: set Dirichlet → assemble R,K → linear solve → update → ‖dU‖. Multi-material = a list of
  `ElementGroup`s (the assembler sums them).
- **Meshing.** gmsh (OCC + subdivision → all-hex) for generated canonical, device-relevant geometry; a mesh-validity gate
  `min_signed_jacobian > 0` on every mesh; boundary sets from OCC surfaces.
- **Preconditioning implementations and evidence boundary.**
  - *Electro-thermal (φ,T):* **PCFIELDSPLIT**, GAMG per scalar field. The distributed driver uses a loop-free
    owned-row-CSR assembly (NOT `setValuesCOO`, which corrupts global GAMG state — a confirmed
    upstream PETSc bug, `docs/petsc_coo_gamg_bug_repro.py`). Correctness is checked at 2 and
    4 ranks. Historical mesh-independence, timing, and 5M-DOF observations are withheld pending
    retained raw output and environment evidence.
  - *Thermo-mechanical (u,T):* **PCFIELDSPLIT** (u | T), GAMG on the displacement block **seeded with
    the rigid-body near-null-space** (the 6 modes), jacobi on a prescribed-T block. The historical
    hundreds-versus-~20 iteration ablation and mesh-independent interpretation are unretained local
    observations, not public-release performance evidence.
- **BCs.** Symmetric Dirichlet via `zeroRowsColumns` (keeps SPD for AMG); plane strain = `u_z=0` on
  both z-faces of a thin slab; rigid-body removal by pinning the centre + one rotation dof.

## 7. Validation philosophy (how evidence is classified)

Individual numerical/model components use one or more evidence types: closed forms, published
benchmarks, patch tests, energy balances, independent solvers, invariants, interface/structural
checks, and broken controls where meaningful. Not every gate has an independent oracle, and a
composed workflow's handoff checks do not independently validate every downstream prediction. Two
honesty rules run throughout: (i) distinguish *rigorous/exact* (integrator-vs-its-own-saturation,
nodal-exact 1-D) from *benchmark-within-tolerance* (closed form vs a digitized figure or a
curved-mesh discretization); (ii) report the **mesh-objective** quantity (ΔW, the field) as the
stronger numerical result and identify life `N_f` as calibration-specific, with the measured
4719-cycle case used only as an in-sample reproduction. The fast 53-gate suite
(`eda_multiphysics.run`) covers the numpy/scipy models; the **toolchain tier** (`pytest -m
toolchain`) regression-tests compiled 3-D, thermo-mechanical, reliability, and MPI paths against
their documented analytic, comparison, structural, and iteration-bound contracts.
