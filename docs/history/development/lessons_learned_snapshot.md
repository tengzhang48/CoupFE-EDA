# Historical snapshot: Detailed lessons learned

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/lessons_learned.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# CoupFE-EDA lessons learned

> **Release-evidence boundary:** exact timings, speedups, iteration counts, and
> scale figures in this dated narrative are historical local observations
> without retained raw logs and a locked environment. Rerun them before
> citation. Functional and correctness gates are tracked separately.

Dated, narrative lessons from building the EDA-multiphysics suite on top of CoupFE. The
how-to discipline lives in `skills/SKILL.md`; this is the "why we did it this way" record.
Newest first.

## 2026-07-20 — The assumed macro gradient is a hidden calibration; the Raman probe cannot falsify it

The recurring release blocker "Jiang macro/bottom boundary semantics are not frozen" is not a
documentation gap. It is a physics shortcut compiled into the consumer: `silicon_far_field_constraints`
(`tsv_local_3d.py`) prescribes **pure-silicon free contraction** (`alpha=2.3e-6`) as a Dirichlet
condition on the outer *and* bottom faces, and the periodic path takes the macro strain **H as a
required input** (`periodic_macro_gradient`), never solved.

- **An infinite TSV array under uniform ΔT, free surface, no external in-plane load, has a macro
  strain set by the Cu+oxide+Si composite average — the traction-free (zero-macro-stress) condition
  — not pure silicon.** Prescribing pure-Si displacement on the outer face is a boundary *assumption*,
  not the far field. Jiang's own model was a quarter cell with symmetry BCs, which is the same
  physics reached a different way; neither is "clamp the outer face to pure-Si free expansion."
- **The assumed H is a hidden calibration knob.** The validation observable — near-surface
  σ_xx+σ_yy — is computed *against* the assumed boundary. If H is assumed (or the Raman spot width is
  tuned), the Raman comparison **cannot falsify the boundary assumption**. This is the pinned-`c`
  swelling trap from the cohesive work: a probe that cannot falsify the error it certifies will
  report a match on the wrong arithmetic. Freeze H by physics, freeze the spot width by the paper,
  *then* compare — do not let the comparison choose either.
- **The decisive experiment freezes the contract with evidence, in either direction.** Solve the cell
  under zero-macro-stress so H is an *output* (6 unit-strain cell solves → effective stiffness →
  invert for the thermal macro strain), keep the top traction-free, freeze the bottom as `u_z=0` at
  wafer depth. Compare near-surface σ_xx+σ_yy from *assumed α_Si·ΔT* vs *solved composite H* with
  nothing tuned. Cu is ~3.9% area fraction (π·5²/(40·50)), so the two may agree to a few percent —
  if so, freeze the shortcut *with a documented error bar*; if not, the solved-H path is mandatory.
  Either outcome retires the blocker permanently instead of deferring it again.
- **A stable solution is not a physical boundary.** This is the same failure the audit already logged
  for the rigid pins (algebraically well-posed, 500% domain-sensitive). Assumed-α_Si is well-posed
  and converges cleanly; that says nothing about whether it is the array's boundary. Audit physical
  boundary meaning separately from numerical residuals.

## 2026-07-13 — Periodic status is a vector, not a yes/no label

The phrase “parallel MPC works” became technically true before “the TSV runs scalably in parallel”
became true. Those claims must not be collapsed.

- Track pairing, serial mechanics, direct reduced assembly, real MPI correctness, production memory
  locality, and the specific application consumer separately.
- A scalar bulk patch at 1/2/4 ranks proves reduced PETSc routing and rank invariance. It does not
  prove anisotropic TSV execution, state commit, contact, dynamics, or large-memory behavior.
- Record whether setup and output are replicated. A distributed Mat/Vec with a globally replicated
  transform is a valuable correctness reference, but it is not scale evidence.
- Status documentation must cite the latest executed tier. Preserve the last complete toolchain run
  and separately state later focused reruns; do not synthesize an unexecuted “complete” total.
- Keep the niche explicit: the value is physics-aware, traceable EDA-to-local reliability analysis,
  not universal element, boundary-condition, or signoff coverage.

## 2026-07-13 — Periodic geometry, MPC algebra, and macro physics need separate status bits

The first periodic TSV integration passed only after three independently testable layers were kept
separate.

- **Matching faces are geometry evidence.** Gmsh now copies minus-face meshes to plus faces and
  CoupFE independently verifies the complete translated bijection. This advances
  `periodic_pairing_status`, not the mechanics result.
- **MPC is kinematic topology, not material.** Elements on opposite sides share reduced solution
  DOFs through `U=Pq+U0`; their coordinates, regions, integration points, and material state remain
  physical and unchanged.
- **Macro strain is model setup.** `periodic_macro_gradient` requires an explicit 3×3 input. A zero
  jump is a fixed box, not a neutral default during cooling; the broken control develops 29.09 MPa.
- **Test engineering and SI scales.** The initial core lattice determinant test used an absolute
  unit floor and rejected the valid micrometre box after conversion to metres. A scale-relative
  determinant gate plus an SI-microscale regression fixed the setup error.
- **Use the homogeneous material limit before mismatch physics.** Identical cubic Si across all
  geometric regions reproduced affine free expansion and machine-zero stress, isolating pairing,
  units, constraint signs, edge/corner classes, and `P/P.T` before Cu/oxide mismatch was enabled.
- **Parallel correctness and scalable ownership are separate milestones.** Each equivalence class
  needs one global reduced ID; elements on either face can assemble into it with PETSc
  `ADD_VALUES`. CoupFE's replicated-setup reference now passes 1/2/4 ranks, proving that algebra and
  routing. It does not prove memory-local constraint compilation or a distributed TSV consumer, so
  those remain separate gates rather than being inferred from serial or small-MPI success.

## 2026-07-12 — Debug the model, physics, units, and setup before blaming the solver

The oxide-tip defect is the clearest example of why a green test suite is not enough. The linear
system was well-conditioned, residual and reaction balance were excellent, stresses were finite,
and the constitutive patch tests passed. The solved geometry was still physically wrong.

- **Start from the physical contract.** Write down the intended materials and their adjacency,
  dimensions, reference state, governing equations, omitted physics, coordinate/crystal axes,
  loads, boundaries, and measured observable before reading the assembly code.
- **Inspect what was generated.** Region counts and positive volumes cannot detect every topology
  error. Query shared interfaces, direct material contacts, tip/surface coordinates, and named
  boundaries; use a visual mesh inspection when the shape or adjacency is important.
- **Make a unit ledger.** Check input units, internal units, and result units at each interface. For
  this model that includes µm→m, GPa→Pa, thermal expansion per K, force in N, stress in MPa,
  engineering versus tensor shear, and the sign of cooling from the stress-free temperature.
- **Distinguish numerical constraints from physical boundaries.** Rigid-mode pins can make a matrix
  solvable without representing an infinite matrix or a periodic array. Verify each constraint by
  its physical meaning, not only by whether the solve converges.
- **Use controls that can expose a wrong setup.** Homogeneous free expansion, fully constrained
  thermal stress, affine strain, force/moment balance, symmetry, domain enlargement, and a broken
  control cover different failure modes. No single check is sufficient.
- **Invalidate dependent evidence after a model change.** Fixing topology means the old mesh/domain
  study no longer qualifies the new scene. Preserve it as a lesson, then rerun the evidence ladder.
- **Close the loop with a regression.** Each repaired defect needs a machine-checkable invariant;
  prose alone will not prevent the geometry or setup from regressing.

## 2026-07-12 — Audit material topology and reference frames before interpreting a stress contour

The first anisotropic TSV solve passed constitutive and residual gates but its CAD Boolean created
only an oxide sidewall. Cu and Si shared 41 nodes across the scaled blind-tip disk, so the stress
field represented a different physical stack than the intended lined via.

- **A named material region does not prove the intended topology.** The corrected geometry extends
  the liner below the Cu to form an oxide cup and fails if any Cu/Si nodes remain in direct contact.
  The regression checks the bottom interface near the via axis, not only nonempty region volumes.
- **Separate benchmark vehicles even when dimensions overlap.** Jiang's 40/50 µm array and Ryu's
  isolated 200 µm TSV use different geometry and boundary contracts. The new periodic-cell API is
  a geometry foundation only; the isolated solve cannot stand in for its missing periodic DOFs.
- **A coordinate frame is part of the material model.** Cubic stiffness is meaningful only with
  declared crystal and global axes. Mesh metadata now stores a right-handed frame and a proper
  crystal-to-global rotation; results carry both plus material/mesh hashes and the boundary label.
- **Named periodic faces are not periodic mechanics.** Opposite meshes may not even have matching
  nodes yet. The next implementation must build correspondence and enforce a macroscopic thermal-
  strain jump plus periodic fluctuation, with a free-expansion patch test before mismatch loading.
- **Keep the failed evidence after fixing topology.** Earlier convergence numbers diagnose the
  superseded sidewall-only scene and must not be promoted as evidence for the corrected oxide cup.
  Mesh/domain studies must be rerun on the corrected and then periodic geometry.

## 2026-07-12 — Preserve the validated Hex oracle; add a separate Tet path for the thin blind TSV

The existing Cu/Si all-Hex TSV is a valuable plane-strain composite-cylinder oracle, but it is the
wrong geometry path for a thin oxide liner, a blind tip, and a free wafer surface. Extending that
canonical mesh in place would mix a new CAD challenge into a stable solver/scaling regression.

- **Add fidelity beside an oracle, not on top of it.** The new `tsv_device_submodel` uses conformal
  frontal Tet4 regions while the two-region all-Hex case remains unchanged.
- **Use physical coordinates for the measurement contract.** The local geometry sets the surface at
  `z=0` and stores the Raman plane explicitly. `raman_scan_points` constructs `z=-0.2 µm`; the field
  sampler fails if a point is outside silicon instead of silently selecting a nearest element.
- **Engineering shear is an API decision.** Cubic `C_ijkl` must be converted consistently to a
  Voigt matrix acting on `[exx,eyy,ezz,gxy,gyz,gxz]`; otherwise `C44` is off by a factor of two.
  Building each Voigt column from a tensor strain makes that convention executable.
- **A converged linear solve is not a validated stress curve.** Positive volumes, shared interfaces,
  affine strain, fourfold symmetry, residual balance, and exact-depth extraction qualify the
  foundation. Mesh/domain convergence, an independent element route, and specimens C/D still block
  the experimental claim.
- **Mesh size and measurement resolution are separate sensitivities.** A local Gmsh distance field
  can refine the Cu/liner surface without refining the whole Si disk. A consistent L2 stress
  projection and Gaussian spot quadrature make recovery and spatial averaging explicit, but the
  spot width cannot be tuned to manufacture convergence. Across the two finer scaled meshes, the
  Raman-profile difference changed from 14.3% at `sigma=0.08` to 11.3% at `sigma=0.15` and 6.9% at
  `sigma=0.25`; all remain above 2%, and the paper does not supply the exact width.
- **Rigid-mode removal is not a far-field model.** Minimal pins make a mathematically solvable free
  finite cylinder, but the Raman profile changed by more than 500% when that cylinder was enlarged.
  Prescribing silicon free contraction on the outer/bottom boundary is a more physical isolated-
  inclusion approximation and reduced successive domain changes to 54% and then 18%, but still
  misses the 3% gate. Eventual global–local displacement transfer must replace both approximations.
- **Separate radius from depth before buying a larger mesh.** Depth enlargement changed the scaled
  profile only 3.1%, whereas radial changes were 59%, 15.4%, and 14.0% across successive sizes.
  The experimental specimen is a periodic 40/50 µm array, so an isolated cylindrical boundary is
  the wrong route to validate that curve. Implement the published unit-cell boundary semantics;
  retain the large-cylinder study only for the isolated-TSV benchmark.
- **Keep the evidence bit attached.** Both geometry and result report `release_validation=false`;
  adding anisotropy does not automatically advance the scorecard.

## 2026-07-12 — A device-scale-dimension demo is useful only when the stress-field evidence level travels with it

The TSV release plan exposed the right niche for CoupFE-EDA: preserve EDA identities while moving
from global loading to a local physical field and a device-screening quantity. The first tranche
also exposed several claim-control rules:

- **Freeze the observable, not a colorful contour.** Raman measures `sigma_xx + sigma_yy` under
  the stated (001) backscattering configuration, 0.2 µm below the surface. Von Mises stress or a
  surface-node maximum is not a substitute.
- **Trace every benchmark number to the primary source.** The proposed 67.94%/3.45% mobility pair
  was not present in the cited Ryu paper. Its actual stated isolated-case outcomes are about 61%
  for n-[100], below 5% for p-[100] and n-[110], and up to about 63% for p-[110]. Unsupported
  precision must not become a frozen oracle.
- **Separate equation verification from experiment.** Cubic stiffness rotation, Raman conversion,
  piezoresistance units, and channel rotation can be exact numerical gates. They verify the proxy
  layer; they do not validate the upstream near-surface stress or a transistor.
- **Make preview fidelity machine-readable.** The 10 µm/−250 °C demo uses a validated Lamé
  far-field stress tensor and real literature coefficients, but reports `release_validation=false`.
  Its identity/back-annotation and orientation action are useful integration evidence, not Raman,
  KOZ, or delay qualification.
- **A release scorecard should fail closed.** Missing digitized curves, anisotropic 3-D FE,
  conservation, external comparison, and clean-machine evidence remain `blocked` or `not_started`.
  A partially green scorecard yields an alpha prototype, never a “validated workflow” by optimism.

## 2026-07-12 — Count gap closure with a fixed denominator and evidence levels

As the implementation accelerated, “we filled the gaps” became easy to say and hard to audit. The
gap PDF uses seven principal gaps in its executive summary but twelve distinct families across its
detailed table and subsections. The durable rule is:

- **Publish the denominator.** Use the consolidated twelve-family inventory for progress counts;
  also show the seven-gap executive view when communicating the headline.
- **Separate closure from movement.** These rounds materially narrowed 8/12 families, but no
  ecosystem-level gap is fully closed. A local workflow can be “demonstrated” while the general
  platform capability remains partial.
- **Require executable evidence for an advance.** Code, a public API, provenance-bearing data, a
  regression test, or a reproduced benchmark can change status. Documentation alone cannot.
- **Keep limitations in the same row as evidence.** A generated six-region
  package is canonical-geometry evidence, yet it is not imported package CAD;
  a versioned proxy map is semantic progress, yet it is not a
  real bump export; the then-current 87 passing tests were strong research
  validation for that round, yet they were not signoff.
- **Track the next status-changing artifact.** Real bump export, conservative transfer, multi-die
  hierarchy, workload traces, and blind package validation are more useful roadmap units than a
  vague request for “more multiphysics.”

The canonical inventory now lives at the top of `docs/capabilities.md`. Update it in the same change
that adds evidence or changes a claim boundary.

## 2026-07-12 — Joint identity and transforms are geometry, not file-format details

The first layout-driven fatigue map inferred 79 “joints” from PDN-node names. That was useful for
proving the DNP-to-life mechanism, but it blurred a power-grid footprint with package geometry. The
new `joints.csv` + `joints.meta.json` path makes the distinction executable:

- **Stable IDs are required model data.** Coordinates alone cannot carry results back to a package
  object. Every row now has a unique `joint_id`, with optional net and source-object identity.
- **Units and coordinate frames must fail closed.** Schema version, coordinate unit, dimension
  unit, frame name, affine transform, and offset are metadata requirements. Guessing a DBU scale or
  silently assuming aligned die/package frames creates plausible but wrong DNP values.
- **The neutral point is an input with a documented fallback.** A package export can state it in die
  microns; otherwise the transformed joint centroid is used. The scorecard exposes the value.
- **An explicit proxy is better than an implicit proxy, but it is still a proxy.** The bundled map
  has nine stable IDs and a closed-form 60×60 µm / `sqrt(1800)` µm geometry oracle, yet its source
  is `project_authored_synthetic_joint_map`. It demonstrates the interface; it does not prove
  real bump placement.
- **Compatibility paths need end-to-end tests.** Unit/transform, duplicate-ID, explicit preference,
  fallback provenance, and vendored-map tests caught the semantic layer. The toolchain run then
  exposed a separate Tet4 bug: the thermo-mechanical builder ignored the repository's older-core
  fallback and classified Tet4 as 2-D. Routing Tet4 through `TET4_CONFIG` fixed the intended
  consumer compatibility path.

## 2026-07-12 — Profiled solder geometry: CAD construction entities are not FE nodes, and shape sensitivity is not an oracle

Added parametric cylinder/barrel/hourglass solder joints with Gmsh/OpenCASCADE and wired them into
the global-local fatigue bridge. The useful result was not merely the spline profile; it exposed
several reusable geometry rules:

- **Build the FE node table from volume connectivity.** A full OCC revolution left the source
  meridian as an orphan surface. `gmsh.model.mesh.getNodes()` included nodes on that construction
  entity even though no volume element referenced them. Passing those nodes to the operator created
  missing diagonal rows and a singular PETSc matrix. Remove orphan construction entities, then
  restrict coordinates to node tags referenced by the selected volume elements. Gate the invariant
  `unique(elems) == arange(len(coords))`.
- **Classify only the solid's boundary.** Searching every model surface can accidentally pick an
  orphan or internal construction surface. Start from `getBoundary([(3, volume_tag)])`, classify
  those surfaces, and filter any unmapped node tags. Keep cap, lateral, and material-interface sets
  explicit—the boundary name is part of the physical model.
- **Keep the analytic shape as the compatibility oracle.** The cylinder has the DNP shear check;
  barrel/hourglass profiles have no equally strong closed form. The profiled-geometry test therefore
  proves mechanism—valid connected mesh, exact imposed caps, and a material change in the solved
  upper-tail strain—without pretending that one profile's life is an independently validated truth.
- **“Device-shaped” is not “package CAD.”** The profile and follow-on UBM/pad/underfill regions are
  parametric and physically recognizable, but the public reference map still uses PDN-node proxies;
  qualified dimensions/materials, voids, and a named STEP/BREP mapping are absent. Use precise
  language so a working mesh does not become an inflated fidelity claim.
- **Geometry fidelity should follow the decision.** Keep PDN electrical as a 1-D graph and die
  thermal as a 2-D compact field. Spend 3-D DOFs on interfaces, necks, corners, and local failure
  regions where geometry changes gradients.
- **Do not force Hex8 onto a multiply connected solid.** The revolved bump passed the Hex8
  Jacobian gate, but the underfill shell created by cutting the bump from an outer cylinder produced
  inverted subdivision hexes. Native Gmsh Tet4 gave a connected positive-volume mesh immediately.
  Element-family selection is part of geometry fidelity: keep qualified canonical solids on Hex8,
  use Tet4 for boolean-rich local package geometry, and never lower the quality threshold to save a
  preferred element type.
- **Conformal interfaces need a mechanism gate.** Fragmenting solder, underfill, UBM, and pads is
  not proven by a plausible picture. Intersect adjacent regions' node sets and require every named
  interface to be nonempty; also verify the exact OCC volume partition before solving.

## 2026-06-27 — End-to-end 3D-FE solder fatigue: connect a validated FE to a validated fatigue model, and match the oracle's BCs

Closed the loop from the new 3D thermo-mechanical FE to the project's validated SAC305 Anand/Syed
fatigue (`reliability_3d.py`): a gmsh solder joint → 3D FE shear → equivalent-strain range →
`anand.thermal_cycle` dW/cycle → Syed life (N_f ~ 491 cycles for a harsh JEDEC swing -- a realistic
order of magnitude). Durable points:

- **Connect through the quantity each model actually consumes.** Both `anand.thermal_cycle` and
  `etv_cycle` drive the mechanical strain as `eps = dalpha*(T - T_ref)` -- so the bridge from a 3D FE
  is its **equivalent-strain range** mapped to an effective `dalpha = eps_eq/dT`. Read that off the
  solver (no new model), feed the validated downstream. dW is the mesh-objective output; N_f is
  calibration-specific and anchored only to one in-sample package (±2×) -- keep that distinction.
- **A free assembly relieves CTE mismatch by BENDING -- the DNP shear is the *constrained* upper
  bound.** First cut modeled a free flip-chip sandwich (die/solder/substrate) under dT and compared
  the emergent solder shear to the textbook `dgamma = dalpha*dT*L_D/h`: it came out **25× smaller**
  -- not a bug, physics. A freely-warping bilayer bends, and bending accommodates most of the
  in-plane mismatch, so the interfacial shear is small. The DNP formula assumes *rigid, non-bending*
  plates. **Match the oracle's boundary conditions:** the textbook solder-joint FE imposes the DNP
  differential displacement `du = dalpha*dT*L_D` directly on the joint (bottom fixed, top sheared) --
  then the FE shear reproduces `du/h` (8%), and the chain is clean. When an emergent FE disagrees
  with a hand formula by ~25×, check which constraint the formula assumed before doubting the FE.
- **Reuse the block PC across problems.** The same `_fieldsplit_tm_solve` (FieldSplit + rigid-body
  near-null-space) drives this joint solve unchanged -- a multi-material / single-material elasticity
  block just works once the near-null-space is wired.
- **A coordinate-labeled power-grid footprint can be decoded, but the proxy must be labeled.**
  PDNSim `write_pg_spice` node names use `NET_x_y_layer` coordinates in DBU, and the bundled
  project-authored SPICE fixture exercises the same convention. Its explicit nine-point map has
  a 60×60 µm footprint and `sqrt(1800)` µm corner DNP at the manifest's 1000 DBU/µm scale.
  That turns the 3D-FE fatigue from an *assumed* L_D into a **per-joint life map over
  the explicit proxy array** (worst corner / best centre). The bundled loading/footprint is synthetic; the
  local joint now supports parametric cylinder/barrel/hourglass profiles and canonical
  solder/underfill/UBM/pad regions, while real package bump exports, package CAD, and qualified
  inputs remain. A caller-provided OpenROAD/PDNSim case can drive the same adapter, but it needs
  its own provenance, package mapping, and qualification.

## 2026-06-27 historical PC study: rigid-body near-null-space

This historical study compared SuperLU with **PCFIELDSPLIT**, splitting
displacement u from temperature T, **GAMG on the u-block seeded with the
rigid-body near-null-space**, and Jacobi on the prescribed-T block. It recorded
about 20 iterations over 16k→144k DOF, but raw output and a locked environment
were not retained. Treat the numbers as a rerun target, not a current
mesh-independence, complexity, or performance claim. Implementation lessons:

- **Seed elasticity AMG with the rigid-body near-null-space.** The historical
  ablation recorded 565 versus 21 KSP iterations without/with the six modes.
  Retain a final-revision ablation before quoting those values or claiming
  mesh independence.
- **`PC.setCoordinates()` broke GAMG here** ("Computed maximum singular value as zero" in
  `PCGAMGOptimizeProlongator`). The robust route is explicit: build the modes with
  `MatNullSpace.createRigidBody(coords_vec)` (coords as a block-size-3 Vec) and
  `Au.setNearNullSpace(...)` on the FieldSplit u sub-block (`ksp_u.getOperators()[0]`), set *after*
  `ksp.setUp()` (the sub-blocks don't exist before it) but *before* the solve (GAMG sets up lazily).
- **A fully-prescribed field's FieldSplit block is the identity — don't GAMG it.** With T Dirichlet
  everywhere, `zeroRowsColumns` makes the T block identity; GAMG can't coarsen it (same zero-singular
  -value error). Use `jacobi` for that block (a genuine conduction T-block would use GAMG).
- **Build the PETSc Mat from the scipy CSR on COMM_SELF** (`createAIJ(csr=...)`, SEQAIJ) — this
  sidesteps the `setValuesCOO` global-state bug entirely (that bug is MPIAIJ-COO specific).
- **Start from the standard PETSc field-split-by-component pattern.** The rigid-body
  near-null-space on the displacement block is what makes that pattern scalable for elasticity.
- **On hypre:** the pip petsc4py 3.25.2 wheel has **no hypre** (`PCSetType hypre` → err 86), so
  BoomerAMG isn't an option in this environment; GAMG + the rigid-body near-null-space gives the
  same scalability (~20 iterations). Conda-forge PETSc includes hypre as a possible qualified
  fallback.

## 2026-06-28 — Parallel hardening against a frozen contract

The regression-net and solver-dedup work proceeded in parallel and merged cleanly. What made it
work:

- **Disjoint file sets + a frozen contract enable safe parallelism.** Tests/configuration and
  implementation changes stayed separate. `docs/REFACTOR_CONTRACT.md` froze the public API
  signatures and oracle numbers, and `pytest -m toolchain` was the merged acceptance gate.
- **Concurrent branches need separate worktrees.** Sharing one checkout across branches changes
  the files beneath other active work. Give each concurrent task its own worktree or clone.
- **The trust net proved the refactor.** Migrating all four 3-D/thermo-mech solves onto one shared
  `coupled_newton` driver was guarded by re-running each `main()` *and* by the toolchain suite —
  every oracle came out bit-identical (e.g. thermo-mech free-expansion 2.23e-13, TSV FieldSplit-vs-
  direct agreement 5e-20, `ksp_its` 13<40). That last assertion (iteration *count*, not just
  convergence) is what proves the rigid-body near-null-space is actually doing its job — assert the
  mechanism, not just the result.
- **`addopts = "-m 'not toolchain'"`** keeps a bare `pytest` fast (toolchain opt-in via `-m
  toolchain`); the slow gmsh/petsc tests are excluded by default, not by hoping nobody runs them.
- **Defer with rationale, don't silently drop.** Two planned items (a global kernel-build cache; a
  shear-extraction refinement) were *not* done — the cache is low-value once the hot paths pass a
  prebuilt `mod=`, and the refinement would perturb a validated, contract-pinned number. Both are
  written down in the contract as honest follow-ups, not quietly abandoned.

## 2026-06-27 — TSV thermal-mismatch stress on a real gmsh via: a physical oracle, a robust metric, and where the direct solver dies

Connected the two threads — gmsh device geometry (`mesh3d.via_annulus`) + the thermo-mechanical
element (`thermomech_kernel`) — into a reliability result: the Cu/Si CTE-mismatch thermal stress in
a TSV (`thermomech_tsv.py`), validated against the exact plane-strain **composite-cylinder** closed
form. Durable points:

- **The neo-Hookean small-strain limit IS linear thermo-elasticity — reuse it, derive the oracle in
  its constants.** No need for a separate linear material: at small strain the element's
  `G(F−F⁻ᵀ)+K ln J·F⁻ᵀ−KαT·F⁻ᵀ` reduces to `σ = 2G ε + K tr(ε) I − KαT I`, i.e. μ=G, λ=K,
  thermal-stress coefficient β=Kα. The composite-cylinder oracle (a 3×3 solve for u=Cr+D/r constants
  from u- and σ_r-continuity at r=a and σ_r(b)=0) uses *those* constants. Keep ΔT·α small (~1e-3) so
  the nonlinear correction stays below the discretization error.
- **Validate displacement, not stress, when you can — it avoids gradient post-processing.** u_r(r)
  uniquely determines the stress (given the law), and reading it off the solution
  (`u_r=(x·u_x+y·u_y)/r`) needs no element-stress recovery on the unstructured mesh. The interface
  σ_r(a) is then reported analytically from the matched oracle.
- **A plain max-over-nodes error is a trap on radial fields — bin it.** `max|u_r−u_ref|/peak` bounced
  5%→7%→0.6%→2.5% with refinement (NOT converging) because it was dominated by a handful of
  near-axis nodes where u_r→0 (tiny denominator) and the rigid-body-pin neighbourhood. A
  binned-bulk-RMS over r∈[0.2,0.97] converges cleanly and monotonically (3.1e-3→1.0e-3). Choose the
  metric to measure the physics, not the worst pinned node.
- **Plane strain in 3D = u_z=0 on both z-faces + a thin slab** (verified |u_z|~1e-7 throughout); the
  in-plane rigid body is removed by pinning the centre node and one rotation dof — minimal, away from
  the region of interest.
- **The serial direct solve is the wall, and the scaling test makes that concrete.** 3D SuperLU
  fill-in took the solve 4.2 s → 95 s over 15k → 62k DOF (super-linear) — the honest "this doesn't
  scale" result. The 4-field elastic+thermal block needs a FieldSplit/GAMG PC with the displacement
  **rigid-body near-null-space** to go large/distributed (the same machinery as the electro-thermal
  5M demo, heavier per DOF). Documented as the next step rather than over-claimed.

## 2026-06-27 — Thermo-mechanical 3D element: reuse the core template, validate against the material's own closed form

Promoted the project's 2D/axisymmetric thermo-elastic work (`tsv_stress`, `thermomech`) to a
**compiled monolithic 3D Hex8 element** with displacement *and* temperature (4 dof/node), the
coupling tangent from complex step. Durable points:

- **Don't invent the weak form — the codegen already has a thermo-mechanical example.** CoupFE
  core ships `examples/thermo_mechanics_quad8` (a compressible neo-Hookean solid + isotropic
  thermal pressure −KαT + Fourier conduction, `momentum_equation` + `transport_equation`). I copied
  that material/weak-form into the consumer layer (`thermomech_kernel.py`) and changed only `ndim=3`
  + `element="Hex8"` (u,T both degree-1, equal-order — fine without an incompressibility
  constraint). It generated + verified first try (NDOFEL=32 = 8×4). Search core `examples/` before
  writing any new element.
- **The oracle is the material's OWN exact solution, which keeps the prime directive even for a
  "demo" constitutive law.** At uniform ΔT this neo-Hookean+thermal material has two exact states:
  *free expansion* — a stress-free isotropic stretch λ solving `G(λ²−1)+3K ln λ = KαΔT`, with
  `u(X)=(λ−1)X`; and *fully constrained* — `u=0, σ=−KαΔT`. No physical alloy data needed; the
  constitutive law itself is the oracle (and the two states are each other's broken control).
- **Pick the oracle that is exactly representable to get a machine-precision gate.** `u=(λ−1)X` is
  *linear* in X, so trilinear Hex8 reproduces it to **2e-13** (like the layer stack's nodal
  exactness) — a tight correctness gate on the whole coupled element (thermal pressure → strain →
  equilibrium), not a discretization-limited few-percent. The next step (a *physical* linear
  thermo-elastic material → Lamé/bimetal on a gmsh-meshed Cu/Si via) is where real-alloy data and
  the curved-geometry discretization error come back in.

## 2026-06-27 — Real 3D geometry: use gmsh for Hex8 meshing, don't hand-roll a generator

Closing the "synthetic-grid" honesty gap means running the 3D Hex8 coupled element on a real
device shape (a TSV/via), not a unit cube. First instinct was to hand-roll a cylinder mesh (an
elliptic square→disk map). It *worked* (validated to 1e-5) — but it was the wrong instinct:
**meshing is a solved problem with mature software; use it.** gmsh (`pip install gmsh meshio`)
generates the geometry with its OpenCASCADE kernel and produces an **all-hexahedral** mesh via its
**subdivision algorithm** (`Mesh.SubdivisionAlgorithm = 2`) for the qualified canonical solids
(a cylinder → 18,640 pure Hex8, zero tets/prisms). Durable points:

- **Hex8, not Tet4, is the binding constraint.** The codegen supports `Hex8`/`Hex20` only (no
  tetrahedra). Robust *unstructured* meshing normally means tets (gmsh's Delaunay) — so the
  all-hex *subdivision* path (tet/prism-mesh, then split into hexes) works for the qualified shapes
  in this repository. Arbitrary CAD with robust mesh quality wants a Tet element
  in core (a bigger, shared-tree change) — deferred.
  **Update (2026-07): no longer deferred.** Tet4 (`tet4`/`tet4r`) is a native CoupFE core primitive;
  `mesh3d.tet_box`/`tet_cylinder` +
  `build_et_kernel(element="Tet4")` now mesh + solve generated box/cylinder solids, validated to
  σV0²/8k and a machine-precision patch test (`docs/TET_FEASIBILITY.md`). The element path is ready
  for arbitrary CAD; a named STEP/BREP import and boundary-mapping adapter remains.
- **gmsh's hex node order is directly compatible** with our Hex8 element (bottom-CCW/top-CCW): the
  per-element signed Jacobian (`mesh3d.min_signed_jacobian`) is >0 for every element with no remap.
  Run that Jacobian check on every generated mesh — it's the mesh-validity gate that makes
  "robust" verifiable (subdivision hexes near a curved wall get squished but stay valid, ~1e-6).
- **Subdivision-mesh accuracy is lower than a structured grid** (rel ~1e-3 peak vs the structured
  map's 1e-5) because the cells are unstructured/squished — but it's a *real* mesher on *real*
  geometry, converging with refinement, which is the honest demonstration. Report it as
  benchmark-within-discretization, not "exact" (the slab's nodal-exactness doesn't carry to a 2D
  radial quadratic on trilinear hexes).
- **Boundary BCs come from gmsh OCC surfaces, not guessed coordinates** — classify each surface by
  its bounding box (caps are planar in z; the wall is not) and pull its nodes. Watch the tolerance:
  OCC "planar" cap surfaces have a ~1e-6 numerical z-extent, so a 1e-7 flatness test silently
  dropped the voltage caps → no current → T≡0. An L-relative tol (1e-4·L) fixes it.
- **Multi-material needs no core change.** `props` is one global vector per `CompiledElement`, but
  the assembler sums over a *list* of operators — so one `ElementGroup` per material (each with its
  own props) assembled together gives a multi-material system. **Validated**: the annular Cu/Si via
  (gmsh `fragment`-ed conformal two-volume mesh, k_core≠k_ann, uniform Joule) reproduces the
  composite-cylinder closed form to rel ~1e-3. (The log term in the composite oracle vanishes under
  *uniform* generation — heat through radius r is just q·πr², so flux is k-independent → two matched
  parabolas.) The **layer/package stack** (die/underfill/solder/substrate, one `ElementGroup` per
  layer) reproduces the 1D **series-resistance** oracle `T_top·R(z)/R_tot` to **machine precision
  (4e-16)**.
- **Accuracy is geometry-shaped, and that's the honest story to tell.** Same element, three demos:
  the curved via/annulus are **discretization-limited** (~1e-3, converging with refinement — the
  trilinear hex can't represent a 2D radial quadratic exactly, and subdivision cells near a curved
  wall are squished); the axis-aligned layer stack is **nodally exact** (4e-16 — 1D piecewise-linear
  conduction with interfaces on element boundaries is exactly representable). Report curved cases as
  benchmark-within-discretization (not "exact"), and let the aligned case double as a strong
  correctness check on the multi-material assembly (the interface temperatures are fixed purely by
  the per-material k, and they land exactly).

## 2026-06-27 — Removing the distributed assembly's Python loop: `setValuesCOO` poisons GAMG; assemble owned-row CSR instead

The distributed FieldSplit driver stamped each element's tangent with a per-element
`A.setValues(...)` loop (à la `solve_distributed`). Profiling showed that loop is **~50% of
per-step wall and grows linearly with element count** (n=350/4-rank: 0.55 s stamp vs 0.35 s
GAMG solve) — at 5M DOF it's the wall, not the solve. So it had to go. The obvious vectorized
replacement, PETSc's COO interface (`setPreallocationCOO`/`setValuesCOO`), produces a
**numerically exact** matrix (matched scipy to 1.8e-15, even at the strongly-coupled iter-1
state) — yet the Newton loop **diverged**. A long isolation hunt found the cause:

- **`setValuesCOO` corrupts global PETSc state — a confirmed upstream bug, not our misuse.** The
  *first* solve after a COO (`setPreallocationCOO`/`setValuesCOO`) assembly works; *every
  subsequent* solve in the process fails — so iter 0 of Newton is right and iter 1+ blow up. The
  failure mode depends on the PC, which is the tell that it's **memory corruption**, not a
  numerical/algorithmic quirk: GAMG **stagnates** at max_it (reason −3); ILU and bjacobi report
  **PC-setup failure** (reason −11); `MatConvert` of a COO matrix outright **segfaults**. It is
  **not** the matrix values (identical to `setValues` to ~1e-15, even at the strongly-coupled
  iter-1 state), **not** the field IS, **not** additive-vs-multiplicative, **not** the smoother
  eigen-estimate (a deterministic SOR smoother stagnates too), **not** GAMG-specific, and **not**
  fixed by destroying objects, `garbage_cleanup`, KSP reuse, or rebuilding the COO matrix as a
  plain AIJ. The poison is **global**: a clean `setValues`-built matrix's GAMG solve that passed
  *before* any COO solve **fails after** one. `SEQAIJ` (serial, `etv_3d`) is immune — only the
  parallel COO path triggers it. **A ~30-line pure-petsc4py reproducer** (a trivial scalar 2D
  Laplacian, plain GAMG, no application code, no FieldSplit) is checked in at
  `docs/petsc_coo_gamg_bug_repro.py`. It **fails identically under two independent builds and
  releases — pip-wheel petsc4py 3.25.2 AND conda-forge 3.24.2** — so it's an upstream PETSc bug in
  the `MatSetValuesCOO` path, worth reporting, not a packaging/version artifact of our venv. The
  committed `setValues`-loop version worked precisely because it never touches the COO interface.
- **The fix keeps assembly fully vectorized without `setValuesCOO`:** a **node-aligned**
  contiguous row partition (rank owns nodes [na,nb) → rows [2na,2nb)); each rank evaluates the
  elements *touching* its owned nodes (owned + a one-node-row ghost) in one batched
  `element_rk_batch` call; it keeps only the **owned-row** COO triplets and builds a local CSR
  with `scipy.sparse.coo_matrix(...).tocsr()` (vectorized, sums duplicates), then
  `createAIJ(csr=...)` — a plain AIJ block with **no off-process routing, no COO interface, no
  Python loop**. The residual is summed with `np.bincount`. Result: assembly **0.55 s → 0.074 s
  (7.4×)** at n=350/4-rank, GAMG healthy at every Newton step, serial==N-rank **1e-16** at
  1/2/4/8/48 ranks.

Lesson: "numerically exact matrix" is necessary but not sufficient — an assembly *interface* can
carry global side-effects that only surface on the *second* solve. When a first solve converges
and identical later ones don't, suspect process state, not the operator. And the textbook
distributed-FE pattern (own a row partition, assemble owned rows + a ghost layer, hand PETSc a
local CSR) is both the vectorized-fast path *and* the one that sidesteps PETSc's stateful
off-process assembly entirely. The serial==N-rank gate (KSP-converged ≠ correct) caught every
wrong turn along the way.

## 2026-06-27 — Distributed FieldSplit: the scalable coupled PC, and two bugs that masquerade as convergence problems

ASM/block-Jacobi (the PCs `solve_distributed` offers for coupled fields) have no coarse grid →
iterations grow with size (~340 @132k → ~1200 @526k 2D) → impractical at millions of DOF. The fix
is **PCFIELDSPLIT (GAMG per scalar field)**: split the interleaved (φ,T) system into its two scalar
fields; GAMG mis-coarsens the *coupled* block but is scalable on each *scalar* field. Serial
(`etv_fieldsplit.py`): 745→17 iters at 132k, **flat 16→19 across a 16× size range**. Distributed
(`etv_distributed_fs.py`, a custom driver — `solve_distributed` is single-field only): serial==N-rank
to **3.3e-16**, 13 iters. Two bugs cost real time, and both *looked* like "the solver won't converge":

- **FieldSplit index sets must be each rank's LOCALLY-OWNED field DOFs, not the global set.** Passing
  the full global even/odd (φ/T) IS on every rank made GMRES stagnate at max_it with a 40% error.
  Each rank must pass the φ/T DOFs within its own matrix row-ownership range
  (`loc = arange(rs, re); is_phi = loc[loc%2==0]`). After the fix: 13 iters, but still 22% wrong —
  which led to the second bug.
- **A full-load Newton loop, not load-stepping-with-one-solve.** The Joule term σ|∇φ|² is *quadratic*
  in φ, so one linear solve per load step (3 total) doesn't converge the nonlinearity (peak ΔT 0.68
  vs 0.98). A proper Newton loop at full load (iterate until ‖dU‖ small) → exact (3.3e-16). The 2D
  `etv_distributed` got this for free because `solve_distributed` does real Newton internally; my
  hand-rolled driver had to do it explicitly.

Lesson: a distributed iterative solve that *runs* and *converges its KSP* can still be wrong two ways
— a mis-specified PC (stagnation) and an under-iterated Newton (wrong fixed point). The serial==N-rank
gate against an independent oracle caught both; KSP-converged ≠ correct.

## 2026-06-27 — Going large: use CoupFE's compiled codegen + distributed path, not a hand-rolled loop

For the large coupled solve I first hand-rolled a vectorized-numpy batch assembler. Wrong rung.
**Read CoupFE core's `skills/performance.md` (the acceleration ladder) and `docs/capabilities.md`
BEFORE writing assembly** — they say plainly: f2py-compile the hot, regular element kernel; CoupFE
already generates it from the weak form. Durable lessons:

- **The compiled path is the right tool and it's not much code:** weak form (a `Material` +
  `WeakForm` with `transport_equation` returning `(storage, flux)`) → `generate_uel` → Fortran UEL
  with the full coupled **complex-step tangent** → `build_element_kernel` (f2py) → `ElementGroup`
  (one batched call, no Python loop) → `solve_distributed` (PETSc/MPI). Electro-thermal as two
  scalar transport fields generated, compiled, and validated to **2e-16** (σV0²/8k) in ~3.5 s
  (`etv_kernel.py`); the distributed nonlinear coupled solve hit **80k DOF / 4 ranks /
  serial==N-rank 6.35e-12** (`etv_distributed.py`).
- **GAMG is for scalar elliptic operators; it mis-coarsens an interleaved multi-field block
  system.** The φ,T system gave a misleading ~3–4% error with the `gamg` default — it *ran* and
  looked plausible. `pc="bjacobi"`+GMRES (no scalar-elliptic assumption) dropped it to 6e-12. The
  serial==N-rank gate is exactly what exposed it — a distributed solve that "runs" is not a
  distributed solve that's *right*. (Core capabilities list distributed coupled multi-field as ◐
  "single-field today"; bjacobi makes it work, FieldSplit is the cleaner fix.)
- **Toolchain footguns:** f2py's meson backend invokes `meson` as a *command* → `pip install meson`
  AND put the venv `bin` on PATH (importable `mesonbuild` is not enough). `superlu_dist`
  (machine-precision distributed direct) is conda-only; the pip-PETSc venv is iterative. The codegen
  reads method bodies via `inspect.getsource` → the weak form must be a real `.py` file, not a heredoc.
- **Check the capability matrix before claiming/assuming coverage.** I nearly under-claimed (the core
  matrix says coupled-multifield-distributed is "single-field today") and nearly over-trusted a
  plausible-but-wrong GAMG solve. The honest matrix (`docs/capabilities.md`) is the antidote to both.

## 2026-06-27 — The electro-thermo-viscoplastic study: where complex-step works, where it doesn't, and the honest finding

Built the strongly-coupled electro-thermo-viscoplastic solder study (`etv_solder.py`,
`etv_fe.py`) — defined from the literature (Dandu 2010 benchmark; see the ETV plan), validated
at material-point and FE level. Durable lessons:

- **Complex-step gives the consistent tangent for SMOOTH coupling, but not for the
  viscoplastic return map.** The electro-thermal element (`CoupledET`) puts σ(T) and the Joule
  term in one residual and the cross-field tangent falls straight out of `complex_step_tangent`
  (exact self-heating to 4e-15, no hand-coded Jacobian). But the Anand return map uses
  `brentq` + `abs`/`sign`/`max` — none complex-analytic — so the viscoplastic FE block uses the
  **elastic (modified-Newton) tangent**, exactly as the project's existing `AnandPlaneStrain`
  does. Lesson: complex-step is a property of the *residual's analyticity*; know which physics
  is smooth before promising a complex-step consistent tangent. (Hyper-dual / smoothed-plasticity
  exist, but that's a research effort, not a free lunch.)
- **The honest finding is a *criterion*, not a splash.** Monolithic vs staggered ΔW/cycle is
  **<0.1% for quasi-static thermal cycling** (so the standard staggered practice is quantitatively
  justified) but the staggered scheme **over-predicts fatigue by up to ~60% at fast/pulsed
  loading**, governed by τ/period (τ = ρc/g_th). A bounded result with a quantitative threshold is
  a real contribution — don't pre-commit to "coupling matters a lot"; let the number decide.
- **Numerical robustness is problem-specific, and the *physical* choice is often the robust one.**
  Three hard-won failures: (1) SAC305's stiff h₀=180000 MPa overflows the SnPb-tuned Brent return
  map → used SnPb (the finding is alloy-independent); (2) SnPb at the hot 50–125 °C *steady* range
  is at 0.7–0.87 of melt and creeps so fast the elastic-tangent modified Newton stops converging →
  used the **JEDEC −40↔125 °C** range, which is both numerically robust *and* the actual
  qualification test; (3) the monolithic temperature update blew up with explicit Euler at large
  g_th → **backward Euler** (unconditionally stable, and it gives the consistency limit for free).
  In each case the fix that made the math behave was also the more physically-honest setup.
- **Report singular quantities at a fixed mesh, and say so.** The corner current density (Dandu's
  current crowding) is a genuine singularity (Fan 2011) — it grows with refinement. The
  mesh-converged oracle is the self-heating limit σV0²/8k (exact); the crowding factor (~10×) is
  reported at a fixed mesh with the singularity named, not dressed up as converged.
- **Integrating a FEM into the EDA flow is *easy*.** The coupled element dropped onto the same
  CoupFE operator contract as everything else. That ease is the point: it confirms the
  contribution is the τ/period *physics finding*, not the integration — and reinforces that the
  tool itself is better *shared* than published (see the positioning discussion).

## 2026-06-25 — Reproducing a published SAC305 benchmark: cross-check the constants, separate the rigorous gate from the figure-read gate

Added the modern lead-free solder **SAC305 (Sn-3.0Ag-0.5Cu)** as a validated Anand
benchmark (`anand.py`, gates `gate_anand_sac305_*`), reproducing Motalab et al.
(ITherm 2012 / Auburn 2013) Fig 3.10. Durable lessons:

- **"More recent" usually means a new validated material/dataset, not new machinery.** The
  legacy Sn-Pb work already had the Anand integrator and the closed-form saturation oracle;
  SAC305 was a new 9-constant *dict* + a published figure to hit. Before building anything,
  ask whether the frontier is new physics or just the modern, actually-used data.
- **Cross-check a published parameter set across independent sources — a single source is a
  transcription risk.** Three sources (Motalab dissertation Table 4.1, arXiv:2204.05583,
  MDPI *Materials* 2023) agreed on 8 of 9 constants; the MDPI table prints `h0 = 18000`, a
  dropped zero (correct: `180000`). One source would have silently shipped the typo.
- **Separate the rigorous claim from the benchmark claim, and say which is which.**
  *Rigorous:* the integrator reproduces the model's own analytic saturation (0.02%, exact —
  validates the solver). *Benchmark:* the closed form lands on the paper's published figure
  (~4–10%, within ±1–2 MPa figure-digitization + model-fit tolerance — validates the
  constants/data). Conflating "exact" with "matches the paper" overclaims; the honest split is
  the credible one.
- **Recompute literature-survey numbers before baking them in.** The initial result was
  42.1 MPa at 25 °C/1e-3; it was recomputed independently with the actual
  `sat_stress()` before committing. Trust the oracle you ran, not the one you were told.
- **Know which constant feeds which oracle.** `h0` drives only the hardening *transient*, not
  the saturation value — so the closed-form gate is insensitive to the `h0` typo, but the
  *integrator* gate (which must reach saturation) uses it. Knowing this located the risk.

## 2026-06-25 — Containerizing: pin artifacts, don't resolve them live; the conda MPI is MPICH

Built the conda-based container (`Dockerfile`, `build.sh`, `CONTAINER.md`). Lessons:

- **A build should depend on as few live services as possible.** The first cut resolved "the
  newest OpenROAD `.deb`" via an `api.github.com` call *during* the build — fragile (one build
  hit a transient `could not resolve host`; the unauthenticated API is rate-limited to 60/hr)
  and non-reproducible (same Dockerfile, different binary on different days). Fix: **pin** the
  `.deb` URL as an ARG, add `curl --retry`, allow a deliberate override. Reproducibility means
  pinning, not "fetch latest."
- **Historical private-source lesson: never bake a token into an image.** The first container
  recipe used a transient gitignored checkout because the core was not yet public. The public
  release recipe supersedes that workaround: it clones HTTPS, verifies the documented branch,
  and installs an exact commit without credentials.
- **Know your MPI flavor.** conda-forge `petsc4py`/`mpi4py` pull **MPICH**, not OpenMPI. MPICH
  oversubscribes by default and rejects the OpenMPI-only `--oversubscribe` / `--allow-run-as-root`
  — which silently produced empty output until stderr was un-suppressed. Use plain `mpirun -n N`.
- **Run the trust suite as the last build step.** It turns "the image built" into "the image's
  whole numerical stack imports and reproduces every oracle" — a regression cannot ship green.
- **A trailing command masks the real exit code.** A background wrapper ending in `tail` reported
  exit 0 while `docker build` had failed at the OpenROAD step. Make the *verifying* command the
  last command in the pipeline, or check its status explicitly.

## Foundational lessons (carried from the prototype, pre-spinoff)

The durable ones that shaped the suite:

- **Validate against the analytic LIMIT, and make broken controls STRUCTURAL ZEROS, not scaling
  checks.** A transient "halve-the-rate ⇒ halve-the-decay" proportionality control failed at 2%
  because backward-Euler biases the rate — the *control* was wrong, not the code. Replaced with a
  structural zero (`k=0 ⇒ no decay`, exact). A broken control must be unfalsifiable-if-correct.
- **Units are a first-class correctness hazard.** The Darveaux life constants are calibrated in
  **psi/inch**; feeding ΔW in MPa gave N_f 1000× wrong (3.2M vs ~2,780 cycles). Validate the
  rigorous, mesh-objective quantity (ΔW = strain-energy density/cycle); treat the life number
  N_f as order-of-magnitude (constants are calibration- and unit-specific).
- **The boundary condition encodes the engineering scenario — pick it to match reality.** A PDN
  reinforcement looked *worse* under fixed-voltage and *better* under fixed-current; the real
  chip draws a fixed current, so fixed-current is the correct verdict (−33% hotspot, −19% IR).
  The "bug" was a modeling choice, not a solver error.
- **Make the viscoplastic flow sign-safe and bracket the return map.** Implicit Anand update
  NaNs out: `(1 − s/s*)^a` goes negative and `s*` can be near zero. Use a sign-safe flow rule +
  a stiff BDF integrator (uniaxial) and a bracketed Brent root-find (J2 return map).
- **Use conda-forge `petsc4py` — it bundles `superlu_dist` prebuilt.** A source build of
  superlu_dist fought `--with-fc=0` / f2c-BLAS and failed; the conda binary "just works"
  (serial==N-rank to ~6e-13 on the AES PDN). Don't rebuild what conda-forge already ships.
- **The spin-off validated "lightweight by omission."** Extracting the entire EDA suite as a
  standalone consumer required adding **nothing** to the CoupFE core — every mesh, BC, material,
  element, and gate lives in the consumer layer, built on the public operator contract. The clean
  core/glue boundary is real, not aspirational.
