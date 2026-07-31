# Periodic TSV and MPC status

**As of:** 31 July 2026
**Scope:** matching-node translated periodicity for the Jiang 40 × 50 µm Cu/oxide-cup/Si cell.
**Current candidate dependency:** CoupFE
`933e497301ee3ddb23391b787726674f70b480c5`
(`main`), the qualified and anonymously reachable Core release root.

The release architecture now keeps `PeriodicBox`, translated-node matching,
and periodic relation construction in `eda_multiphysics.periodic`. Core supplies
only mesh-agnostic affine constraint/reduction primitives. The legacy feature
branch is evidence and port provenance, not the desired public ownership split.

> **Evidence boundary:** against public Core `933e497`, the current EDA
> candidate passes the standalone 53-gate harness, the 94-test default tier,
> and the separate 19-test gmsh/PETSc/MPI/gfortran tier. The 53 gates overlap
> wrappers in the default tier. The detailed cell and legacy-Core MPI numbers
> below remain historical observations; they are not promoted into current
> performance or distributed-TSV claims. Publication uses the clean
> committed-root recorder in `RELEASE_EVIDENCE.md`.

## Status at a glance

| Layer | Status | What is qualified |
|---|---|---|
| Periodic cell geometry | Implemented; current toolchain gate passed | full 40/50 µm box, `[110]/[-110]/[001]` frame, oxide cup, and zero direct Cu/Si contact pass in the paired toolchain tier |
| Opposite-face correspondence | Implemented; current toolchain gate passed | Gmsh periodic surfaces plus the EDA-owned strict bijection pass in the paired toolchain tier |
| Generic affine MPC | Implemented against the public pin | Core owns only `ConstraintRelation` and exact `U=Pq+U0`, `P.T R`, `P.T K P`; EDA owns edge/corner periodic equivalence construction and the representative anchor policy |
| EDA serial TSV consumer | Implementation gates passed at the tested case | explicit `macro_gradient`; homogeneous free-expansion and fixed-box controls; heterogeneous equilibrium |
| Core MPI reference | Legacy research prototype, not current public API | the private feature branch carried a bulk/history-free `solve_distributed_affine`; fresh qualification is required if reintroduced |
| Distributed TSV consumer | Open | the anisotropic Cu/oxide/Si TSV has not been run serial-versus-N-rank |
| Production memory locality | Open | core MPI reference replicates transform setup and final lift |
| Jiang model qualification | Open | source-equivalent macro/bottom boundary semantics and corrected-scene convergence are not frozen/passed |
| Experimental/device validation | Open | held Raman curves, uncertainty contract, transistor validation, and signoff evidence remain absent |

## Historical toolchain evidence and current focused evidence

The historical scaled periodic TSV gate contained 2,863 nodes and 13,809 Tet4 elements. It checked matching
periodic faces, material topology, SI units, and exact constraint satisfaction.

- Homogeneous cubic-Si free expansion with `H=alpha*dT*I`:
  - reduced residual `4.94e-14`;
  - maximum displacement error `3.72e-23 m`;
  - maximum stress below `1e-11 MPa`;
  - zero MPC error.
- Deliberately wrong zero-jump box:
  - approximately `29.09 MPa` maximum stress, proving that zero jump suppresses free expansion.
- Heterogeneous Cu/oxide/anisotropic-Si cell:
  - reduced residual `1.72e-14`;
  - zero node-pair mismatch and zero MPC error;
  - finite recovered stresses in every material.
- Legacy Core parallel prototype:
  - analytic scalar periodic gradient passes at 1/2/4 MPI ranks;
  - maximum field error `<3.5e-17`, reduced residual `<7e-16`, zero MPC error.

Paired execution on 31 July 2026 against public Core `933e497` produced
**53/53 standalone gates passed**, **94/94 default EDA tests passed** with the
19 optional toolchain tests deselected, and **19/19 toolchain tests passed**
with the 94 default tests deselected. The standalone gates overlap the default
wrappers. This includes the EDA-owned adapter, Gmsh, PETSc/MPI, native Tet4,
and Fortran paths. The clean committed-root evidence recorder remains the
publication authority for this same tree.

Historical execution on 13 July 2026: 82/82 EDA fast tests passed in 63.45 s; the real Gmsh periodic-TSV
consumer gate passed in 22.61 s; 20/20 focused core tests and all three core MPI rank cases passed;
both wheels built and wheel-only imports passed. The complete 19-test EDA toolchain suite was last run on
12 July 2026 and passed. These are implementation/model-verification results, not experimental TSV
validation.

## Current public dependency path

1. Build the matching cell with `mesh3d.tsv_periodic_cell(...)`.
2. Require `periodic_pairing_status == "matching_nodes_verified"`.
3. Call `tsv_local_3d.solve_local_tsv(...,
   boundary_condition="periodic_macro_gradient", macro_gradient=H)` with an explicit, sourced 3×3
   macroscopic displacement gradient.
4. Check the reduced residual, constraint error, pair mismatch, material/mesh hashes, frame, and
   boundary label before interpreting stress.

There is intentionally no hidden zero-gradient default. `periodic_mechanics_status="not_solved"`
on a mesh means only that geometry/pairing is ready; mechanics status belongs to a solve result.

## What the current result does not establish

- It does not prove that the selected `H` and bottom boundary reproduce Jiang's quarter-array
  experiment.
- It does not replace corrected-scene mesh/domain/recovery convergence or Raman spot averaging.
- It does not qualify nonmatching mortar, cyclic/Bloch, finite-strain box evolution, unknown
  zero-average-stress box strain, contact, dynamics, or path-dependent material state.
- It does not make CoupFE-EDA a universal multiphysics package. The niche remains traceable
  EDA-to-local thermo-mechanical/reliability analysis with physics-aware setup and executable
  validation controls.

## Next status-changing work

1. Freeze the Jiang source-equivalent lateral macro mode and bottom/symmetry boundary contract.
2. Run corrected periodic-scene mesh, domain, recovery, and measurement-averaging convergence.
3. Add force/moment and opposite-face traction-resultant diagnostics to the heterogeneous gate.
4. Only then run the actual TSV consumer through serial-versus-2/4-rank MPC and assess memory.
5. Compare held specimen C/D Raman curves and propagate uncertainty before advancing the release
   scorecard.

The detailed design and rollout remain in `PERIODIC_BOUNDARY_CONDITION_PLAN.md`; the physics defect
ledger and release effect remain in `TSV_PHYSICS_AUDIT.md`.
