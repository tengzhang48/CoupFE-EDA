# TSV local-model physics audit

**Audit date:** 12 July 2026  
**Scope:** `mesh3d.tsv_device_submodel`, `tsv_local_3d`, `tsv_device`, the Jiang Raman benchmark,
and the Ryu mobility/KOZ benchmark.  
**Decision:** the constitutive and Tet4 mechanics are accepted as an implementation foundation; the
current physical scene is not accepted for experimental Raman or KOZ validation.

## Accepted implementation physics

- Cubic (001) silicon uses `C11=166.2 GPa`, `C12=64.4 GPa`, and `C44=79.8 GPa`; 90° rotation gives
  exact fourfold constitutive symmetry and 45° rotation gives the expected anisotropic matrix.
- Engineering-Voigt order is `[exx,eyy,ezz,gxy,gyz,gxz]`, with tensor shear equal to half engineering
  shear and `D44=C44`.
- Tet4 kinematics reproduce arbitrary affine strain. Assembly uses
  `K_e=integral(B^T D B)dV` and `f_e^th=integral(B^T D alpha deltaT I)dV`; coordinates are converted
  from µm to m, stiffness from GPa to Pa, displacement is m, force is N, and recovered stress is MPa.
- A homogeneous-Si free-expansion check gives displacement relative error `6.27e-16` and maximum
  stress `6.20e-13 MPa`.
- The heterogeneous refined solve gives normalized force imbalance `3.76e-15`, moment imbalance
  `7.10e-16`, and free-equilibrium residual `7.34e-15`.
- Scaled mesh mean-ratio quality is acceptable: minimum 0.325 Cu, 0.352 oxide, and 0.227 Si.
- The Raman quantity `sigma_xx+sigma_yy` and extraction plane 0.2 µm below the free surface match
  Jiang's numerical comparison. Current `sigma_zz` is 1–5% of the in-plane sum over the audited
  scan, consistent with a near-surface biaxial approximation but not an experimental proof.
- Ryu's piezoresistance rotations and the signed `delta_mu/mu=-delta_rho/rho` mapping are implemented
  consistently; the KOZ uses the required magnitude.

## Defects and blockers found

| Severity | Finding | Required correction |
|---|---|---|
| Critical | The original Boolean scene created only an oxide sidewall. Cu and Si shared 41 nodes across the scaled blind-tip disk. | Build a conformal oxide cup with sidewall and bottom cap; gate zero direct Cu/Si interface nodes. |
| Critical | The isolated finite cylinder matches neither paper: Jiang used a quarter periodic array; Ryu used a different isolated 200 µm TSV and bottom `u_z=0`. | Maintain separate Jiang periodic-cell and Ryu isolated benchmark configurations. |
| Major | Lateral domain changes remain 59%, 15.4%, and 14.0%; depth-only change is about 3.1%. | Implement the 40/50 µm periodic-cell geometry and its declared boundary semantics. |
| Major | Mesh/crystal axes and applied crystal rotation are implicit. | Store coordinate frame, crystal axes, rotation, materials, and boundary label in every result. |
| Major | Numerical fourfold errors are 3.68% for x/y and 2.51% for the two diagonals on the audited mesh. | Refine/use a symmetry-compatible periodic mesh until the stated 1–3% gate passes. |
| Major | Last-two-mesh Raman differences remain 6.9–14.3%, depending on an assumed spot width. | Freeze recovery and measurement resolution, then pass ≤2% without tuning the width. |
| Medium | Scan distance currently starts at the oxide/Si boundary, while the paper uses nominal Cu/Si-interface language. | Freeze the digitized curve's coordinate origin before peak-location comparison. |
| Medium | Linear Cu omits a mechanism that Ryu shows can reduce KOZ once thermal load/yield permits plasticity. | Run an elastic versus elastic-perfectly-plastic sensitivity before accepting the −270 °C KOZ field. |
| Medium | Positive Tet volume is gated, but a quantitative quality distribution is not part of evidence. | Add a mean-ratio/sliver metric and freeze an acceptance threshold. |

## Benchmark separation

### Jiang curvature/Raman vehicle

- 10 µm Cu diameter, 55 µm blind depth, 0.4 µm oxide, 700 µm wafer;
- pitch 40 µm along `[110]`, 50 µm along `[1-10]`;
- quarter model with symmetric boundary conditions representing the periodic array;
- specimen C/D loads −70 °C and −270 °C;
- compare `sigma_xx+sigma_yy` at 0.2 µm below the surface.

Primary source: <https://sites.utexas.edu/ruihuang/wp-content/uploads/sites/6034/2021/03/MicroReliability1.pdf>

### Ryu isolated mobility/KOZ vehicle

- 10 µm diameter, 200 µm height, −250 °C;
- oxide neglected in that benchmark;
- traction-free top and zero out-of-plane displacement at the bottom;
- surface stress with `sigma_33=0` for the published mobility contours;
- plasticity and array-interaction studies are separate extensions.

Primary source: <https://sites.utexas.edu/ruihuang/wp-content/uploads/sites/6034/2021/03/IEEE_TDMR2012.pdf>

These vehicles must not share geometry or boundary defaults merely because both contain a 10 µm
TSV. Shared constitutive and post-processing functions are appropriate; benchmark scenes are not.

## Corrections completed after the audit

- `tsv_device_submodel` now creates an oxide cup. The scaled gate finds zero direct Cu/Si nodes and
  resolves a Cu/oxide bottom interface across the blind-tip disk.
- Mesh and result records now declare a right-handed coordinate frame, proper crystal-to-global
  rotation, boundary condition, and SHA-256 material/mesh identities.
- `tsv_periodic_cell` now creates the full 40/50 µm rectangular geometry with an oxide cup,
  Gmsh-matched faces, and verified affine node correspondence. CoupFE's exact serial MPC passes
  homogeneous free-expansion and fixed-box broken controls plus heterogeneous equilibrium.
- The old mesh/domain convergence numbers belong to the superseded sidewall-only topology. They
  remain useful failed evidence but must be rerun before any corrected-geometry claim.

## Bug, fix, and prevention ledger

| Defect or error | Physical consequence | Fix and executable guard | Prevention rule |
|---|---|---|---|
| Oxide Boolean produced a sidewall but no bottom cap | Cu was bonded directly to Si over 41 scaled blind-tip nodes, changing the intended load path | Extend the liner one oxide thickness below Cu; require zero `direct_copper_silicon_nodes` and require Cu/oxide interface nodes on the tip disk | Test material adjacency and interface location, not only region names and volumes |
| Jiang periodic and Ryu isolated vehicles were treated as interchangeable 10 µm TSVs | Geometry, oxide, depth, and boundary conditions no longer represented either experiment exactly | Maintain separate benchmark definitions; add the Jiang 40/50 µm cell while retaining the isolated oracle separately | Freeze a benchmark contract containing geometry, materials, axes, loads, boundaries, and observable before coding |
| Crystal/global axes and rotation were implicit | A correct cubic tensor could be applied in the wrong directions without an obvious solver failure | Store a right-handed frame and proper crystal-to-global matrix in the mesh/result; reject improper rotations | Treat orientation as material input and hash it with the mesh |
| Minimal rigid pins were initially interpreted as a far field | A numerically stable solution showed more than 500% domain sensitivity | Relabel pins as null-mode removal; add `silicon_free_expansion` for isolated sensitivity; keep the domain gate failed | Audit physical boundary meaning separately from algebraic well-posedness |
| Named opposite faces could be mistaken for periodic mechanics | A user could report an isolated or unconstrained result as a periodic-array result | Separate `matching_nodes_verified` geometry from `not_solved`; require explicit `periodic_macro_gradient` solve metadata | Require matched nodes, exact MPC, homogeneous/affine controls, and an explicit macro mode before claiming periodicity |
| Old convergence numbers survived a topology correction | Mesh differences from the wrong physical scene could be cited for the corrected model | Mark those studies as superseded failed evidence and require reruns | Any change to topology, units, constitutive law, reference state, or BC invalidates dependent convergence evidence |

## Physics-first debugging order

Debugging must not start and end with source code. Use this order:

1. **Model intent:** identify the benchmark vehicle, fidelity level, and quantity being predicted.
2. **Geometry and topology:** inspect dimensions, material adjacency, interfaces, free surfaces, and
   coordinate origin; visualize or query the actual generated model.
3. **Physics:** write the governing equations, constitutive assumptions, coupling direction,
   reference temperature/state, and omitted mechanisms such as Cu plasticity.
4. **Units and signs:** trace every conversion and convention from input through assembly to output,
   including engineering shear, µm→m, GPa→Pa, K, N, MPa, and cooling-sign conventions.
5. **Setup:** verify loads, constraints, symmetry/periodicity, crystal axes, measurement plane, and
   scan-coordinate origin against the selected source.
6. **Discretization and numerics:** check element quality, connectivity, conservation/residuals,
   mesh/domain convergence, recovery, and measurement averaging.
7. **Code and regression:** only then isolate implementation defects and add a broken control plus a
   permanent regression gate.

A passing residual proves equilibrium of the assembled problem, not that the assembled problem is
the intended physical one.

## Historical execution record (not current release qualification)

On 12 July 2026, after the oxide-cup, provenance, and periodic-geometry changes:

- fast suite: **82 passed**, 19 toolchain tests deselected, in 53.14 s;
- toolchain suite: **19 passed**, 82 fast tests deselected, in 256.25 s;
- total inventory at that recorded revision: **101/101 passed**;
- package wheel built successfully and contains `mesh3d.py` and `tsv_local_3d.py`.

Raw console output and a locked environment were not retained, so this remains historical
regression context. A separate 31 July candidate run against public Core `933e497` passes the
current 19-case toolchain tier, including native Tet4; that does not retroactively promote the
older numerical record or close the physical-validation gaps below.
At the recorded revisions, serial periodic mechanics passed its
implementation controls; source-equivalent macro/bottom BCs, corrected-scene mesh/domain
convergence, a distributed TSV MPC consumer, production memory locality, held Raman curves, and
device validation remain open.

On 13 July 2026, after exact serial MPC integration and the core parallel-reference extension:

- EDA fast suite: **82 passed**, 19 toolchain tests deselected, in 63.45 s;
- real Gmsh periodic-TSV consumer gate: **1 passed** in 22.61 s;
- focused core MPC/assembly/model set: **20 passed** in 7.28 s;
- core analytic PETSc MPC reference: **1/2/4 ranks passed**, field error below `3.5e-17`, reduced
  residual below `7e-16`, and zero MPC error;
- CoupFE and CoupFE-EDA wheels built; wheel-only public imports passed.

The new MPI result qualifies the bulk/history-free core reference, not the anisotropic TSV consumer
or production memory locality. See `PERIODIC_MPC_STATUS.md` for the support matrix.

## Release effect

The audit does not advance a scorecard category. Matching periodic geometry and serial exact-MPC
assembly are now qualified implementation foundations, but `numerical_mechanics` and
`local_experiment` remain blocked until the source-equivalent macro/bottom setup,
corrected-scene mesh/domain/symmetry gates, held curves, and the uncertainty contract pass. The
device preview remains a Lamé-driven integration demonstration.
