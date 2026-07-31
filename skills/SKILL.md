---
name: develop-coupfe-eda
description: Develop, extend, review, or validate CoupFE-EDA multiphysics models, EDA adapters, geometry, solvers, examples, documentation, and regression gates. Use for changes involving OpenROAD or PDNSim data, Gmsh Hex8/Tet4 geometry, electrothermal or thermomechanical coupling, solder/TSV reliability, PETSc/MPI scaling, validation oracles, capability claims, or project technical reports.
---

# Develop CoupFE-EDA

Read this before adding a multiphysics example or a validation gate. This project's
value is **trust through reproduction**: numerical components should be checked
against independent published, analytic, or experimental evidence wherever
available. Composed chains must distinguish those component checks from structural
handoff tests and from end-to-end device validation. Codifying that distinction
keeps the suite honest as it grows. Pair it with CoupFE core's `skills/SKILL.md`
and `skills/testing.md` (the operator-contract + test discipline this builds on).

## The prime directive

**Reproduce a real oracle. Never an invented problem.** Every example must reduce to — or be
checked against — something whose answer is known *independently of this code*: a closed form,
a published benchmark with actual numbers, a patch test, an energy balance, or an independent
solver. "The number looks plausible" is how a wrong result ships. If you cannot find an oracle,
you are not done finding one; you are not building the example yet.

## How to add a validated example + gate

1. **Build the physics on the CoupFE contract, in this consumer layer.** Reuse `fe.py`
   (scalar diffusion), the existing material dicts, and the existing elements. Put the whole
   physics in a residual; derive the tangent by complex step. **Add nothing to CoupFE core** —
   meshing, BCs, materials, elements, and gates are per-problem glue and live here. (The
   spin-off proved the suite needs zero core changes; keep it that way.)
2. **Find the oracle and pin its numbers.** A closed form (Lamé, Timoshenko, σV0²/8k, the
   Anand saturation), or a published benchmark. **If it's a published parameter set or figure,
   cross-check the numbers across ≥2 independent sources** — single-source transcription has
   already bitten us (a dropped zero in an Anand `h0`). Record the source in the module
   docstring and `RESULTS.md`.
3. **Recompute it yourself before trusting it.** Don't bake a number a survey/agent handed you;
   run the actual oracle function and confirm.
4. **Write the gate (`gates.py`).** Return `_g(name, ok, detail)`. Reproduce the oracle to a
   *stated* tolerance, and **ship a broken control**: reintroduce a bug (wrong constant, wrong
   sign, `k=0`, `A×100`) inline and assert the oracle *rejects* it. A broken control must be a
   structural change that cannot pass if the code is right — prefer a structural zero over a
   scaling/proportionality check (backward-Euler bias broke one of those).
5. **Separate rigorous from benchmark, and state the honest scope.** Distinguish
   *self-consistency / closed-form exact* (e.g. integrator-vs-its-own-saturation, 0.02%) from
   *matches-the-paper-within-tolerance* (e.g. closed-form vs a digitized figure, a few %). Never
   call the second "exact." Put the honest scope in `RESULTS.md`.
6. **Wire it in.** Append the gate(s) to `gates.GATES`. It then auto-joins `run.py`, the pytest
   suite, and the container's build-time trust check — no other registration needed.

## Recurring hazards (each has already cost us)

- **Units are correctness.** Darveaux life constants are psi/inch — MPa input gave N_f 1000×
  wrong. Validate the rigorous quantity (ΔW); life remains calibration-specific and has only one
  in-sample package anchor (±2×), not general qualification.
- **The BC encodes the engineering scenario.** Fixed-voltage vs fixed-current flipped a PDN
  verdict. Choose the BC that matches the real operating constraint, then say which you chose.
- **Viscoplastic flow must be sign-safe + bracketed.** `(1−s/s*)^a` goes negative and `s*`→0;
  use the sign-safe flow + stiff BDF / bracketed Brent return map (see `anand`, `solder_joint`).
- **Know which constant feeds which oracle** before trusting a cross-check (e.g. `h0` affects
  only the hardening transient, not the saturation closed form).
- **Geometry metadata is physics input.** Carry units, coordinate frame, stable object ID, region,
  boundary semantics, and provenance. Never infer DBU, power source, or material identity from file
  existence or an unlabeled array.

## Going fast / large: use CoupFE's compiled + distributed path — don't hand-roll

**Read CoupFE core's `skills/performance.md` (the acceleration ladder) and `docs/capabilities.md`
BEFORE writing your own assembly.** The ladder: vectorize numpy → numba → **f2py Fortran for the
hot, regular element kernels** → Rust. A per-element Python loop (or even batched numpy) for the
*element kernel* is the wrong rung at scale — CoupFE already generates a compiled kernel from the
weak form. The lesson (learned the slow way): don't reinvent batch assembly; the compiled path is:

1. Write the element weak form once in Python (`coupfe.codegen`): a `Material` with named
   `*_storage`/`*_flux` methods + a `WeakForm` with `transport_equation`/`species_transport_equation`
   returning `(storage, flux)` → `∫ storage·N + flux·∇N`. Diffusion/conduction/electrical are all
   this form (see `eda_multiphysics/etv_kernel.py`: φ flux = σ(T)∇φ, T flux = −k∇T, storage = Joule).
   It MUST live in a real `.py` file (`inspect.getsource` can't read a heredoc).
2. `generate_uel(problem, "x.for", element="Quad4")` → Fortran UEL with the **full coupled
   complex-step tangent**; `build_element_kernel(for, mod, workdir)` f2py-compiles it.
3. `CompiledElement(mod, props, dof_per_node, ...)` + `ElementGroup(...)` → a CoupFE Operator with
   **one batched compiled call** (no Python loop). Validate it serially against an oracle first.
4. Distributed: `element_partition(view, rank, size)` + `solve_distributed(..., elem.element_rk_batch,
   dirichlet_fn, n_steps)` (PETSc/MPI, ghosted U). Validate **serial==N-rank** (see `etv_distributed.py`,
   80k-DOF nonlinear coupled, 6e-12).

Toolchain + gotchas (hard-won, 2026-06-27):
- needs **gfortran + ninja + meson**; `pip install meson` and put the **venv `bin` on PATH** (f2py
  invokes `meson` as a command, not `python -m`).
- **GAMG mis-coarsens an interleaved multi-field (φ,T) block system** → use `pc="bjacobi"`+GMRES,
  not the scalar-elliptic `gamg` default. (The core capability matrix lists distributed coupled
  multi-field as ◐ "single-field today" — bjacobi makes it work here; FieldSplit is the cleaner fix.)
- `superlu_dist` (machine-precision distributed direct) is **conda-only**; the pip-PETSc venv is
  iterative-only.

**FieldSplit strategy for a coupled (multi-field) scaling study.**
ASM/block-Jacobi have no coarse grid, and GAMG can mis-coarsen the interleaved
(φ,T) block. **PCFIELDSPLIT (GAMG per scalar field)** is the implementation to
evaluate. Historical iteration and 1–48-rank records lack retained raw evidence;
rerun them before claiming mesh/rank independence or scale. `solve_distributed`
is single-field/ASM only, so the distributed FieldSplit is a custom driver
(compiled batch assembly + your own KSP). Three traps that look like "won't converge":
- **field index sets = each rank's LOCALLY-OWNED field DOFs** (`loc=arange(rs,re); loc[loc%2==0]`),
  NOT the full global set (→ GMRES stagnation + wrong answer).
- **a full-load Newton loop**, not load-stepping-with-one-solve — the Joule term is quadratic in φ,
  so it needs real Newton iterations (peak ΔT wrong otherwise). `solve_distributed` does Newton for
  you; a hand-rolled driver must. Always gate on **serial==N-rank** — KSP-converged ≠ correct.
- **do NOT assemble with PETSc's `setValuesCOO` if you then solve more than once per process.** It
  corrupts global state (a **confirmed upstream PETSc bug** — reproduced in ~30 lines of pure
  petsc4py with a trivial Laplacian, `docs/petsc_coo_gamg_bug_repro.py`; **fails identically on
  pip-wheel 3.25.2 AND conda-forge 3.24.2**, so it's not a venv artifact). The *first* solve after
  a COO assembly works; *every subsequent* one fails — GAMG stagnates (reason −3), ILU/bjacobi
  PC-setup fails (reason −11), `MatConvert` segfaults — so a Newton loop diverges at iter 1. It's
  memory corruption, not a value bug (the matrix matches `setValues` to ~1e-15). Removing the
  per-element `setValues` *stamp* loop (~50% of wall, grows with element count) is still right —
  just do it the **owned-row-CSR** way: node-aligned row partition, evaluate elements touching owned
  nodes (owned + 1 ghost layer) in one `element_rk_batch`, keep owned-row triplets, build a local
  CSR with `scipy` (vectorized), `createAIJ(csr=...)` — plain AIJ, no off-process, no COO, no loop
  (7× faster than the stamp loop, GAMG stays healthy). See `etv_distributed_fs.py` / lessons_learned.
- **for a MECHANICS (displacement) FieldSplit block, seed GAMG with the rigid-body
  near-null-space.** Historical runs showed hundreds versus tens of iterations;
  retain a final-revision ablation before generalizing.
  Attach them explicitly: `MatNullSpace.createRigidBody(coords_vec[bs=3])` → `Au.setNearNullSpace`
  on the u sub-block (`ksp_u.getOperators()[0]`), after `setUp` / before solve. `PC.setCoordinates`
  broke GAMG here; a fully-prescribed (Dirichlet) field's block is the identity → use `jacobi`, not
  GAMG, for it. See `thermomech_tsv._fieldsplit_tm_solve`.

## Device geometry: use mixed fidelity and Gmsh

Read `docs/GEOMETRY.md` before changing geometry. Preserve mixed dimensionality: PDN wires remain a
1-D graph, die power remains a 2-D field, and only local shape-sensitive regions become 3-D. Use
Gmsh (`pip install gmsh meshio`) rather than writing a mesh generator. Workflow:

1. **Build geometry with gmsh OCC** (`addCylinder`, `addBox`, `fragment` for conformal
   multi-material interfaces; `addSpline` + `revolve` for a profiled joint). Two meshing routes:
   **all-hex** via `Mesh.SubdivisionAlgorithm = 2` for qualified canonical solids, or **all-tet**
   via Gmsh's native Delaunay output. `mesh3d.tet_box`/`tet_cylinder` validate the Tet4 element path;
   a named STEP/BREP import adapter is still pending. The
   codegen now has **Hex8/Hex20 AND Tet4** as first-class elements (`tet4`/`tet4r` were **promoted to
   CoupFE core**; use `build_et_kernel(element="Tet4")`; see `docs/TET_FEASIBILITY.md`).
2. **Extract + validate the mesh.** Build the FE node table from nodes referenced by volume
   elements, not `getNodes()` alone. Full revolutions and boolean operations can leave orphan CAD
   entities; including their nodes creates disconnected zero rows and a singular PETSc matrix.
   Remove source construction surfaces when possible and assert that every returned node appears in
   an element. Gmsh's hex node order is directly compatible with our element
   (no remap) — but *prove* it: `mesh3d.min_signed_jacobian(coords, elems) > 0` on every mesh (run
   it always; it is the validity gate). Restrict surface classification to the selected volume's
   boundary entities. Pull boundary node sets from **OCC surfaces** (classify by
   bounding box), not guessed coordinates — and mind the tolerance: OCC "planar" cap surfaces have a
   ~1e-6 numerical z-extent, so use an L-relative tol (1e-4·L), or a tight test silently drops the
   BC face (→ no drive, zero field).
3. **Multi-material = one `ElementGroup` per physical region** (no core change — the assembler sums
   a list of operators). Fragment/cut overlapping OCC solids into non-overlapping conformal volumes,
   map resulting volume tags to explicit region names, and keep shared-interface node sets. Do not
   rely on incidental entity ordering. Give each region its own properties and test that interfaces
   share nodes.
   Use `mesh3d.solder_package` as the reference: it returns six named Tet4 regions, external pad
   boundaries, shared interface sets, and exact OCC volumes. Do not force subdivision Hex8 when a
   boolean-rich underfill shell fails the signed-Jacobian gate; select Tet4 and keep the gate.
4. **Validate against a real closed form** (prime directive). Curved geometry is discretization-
   limited (~1e-3, converging) — report it as benchmark-within-discretization, not exact; flat/
   axis-aligned 1D conduction is **nodally exact** (~1e-16). Oracles used: heat-generation cylinder
   `σ₀V²R²/4kL²` (solid via), composite cylinder `qa²/4k_core+q(b²−a²)/4k_ann` (annular via — the
   log term vanishes under uniform generation), 1D series resistance `T_top·R(z)/R_tot` (stack).
5. **Chaining a 3D FE into a downstream validated model** (e.g. FE stress → solder fatigue,
   `reliability_3d.py`): connect through the **quantity the downstream actually consumes** and reuse
   the validated model — don't re-derive it. The Anand/Syed life is driven by `ε = dalpha·(T−T_ref)`,
   so the bridge is the FE **equivalent-strain range** mapped to an effective `dalpha = ε_eq/dT`; feed
   that to `anand.thermal_cycle`. Keep the project's split: dW is the **mesh-objective** output, N_f
   is calibration-specific and anchored only to one in-sample package (±2×). And **match the
   oracle's boundary conditions**:
   a *free* assembly relieves CTE mismatch by bending, so its emergent solder shear is ~25× below the
   textbook DNP `dalpha·dT·L_D/h` (which assumes *rigid* plates) — impose the DNP displacement on the
   joint (the standard solder-joint FE BC) and the FE reproduces `du/h`. When an emergent FE disagrees
   with a hand formula by a big factor, check the formula's constraint assumption before doubting the FE.
   **Drive it from explicit geometry, not an assumed dimension:** prefer schema-v1 `joints.csv` +
   `joints.meta.json` through `joint_map.load_joint_map` / `reliability_3d.design_joints`. Require
   stable IDs, explicit coordinate and dimension units, a named coordinate frame, and the affine
   transform into die microns; require `geometry_fidelity` (`proxy`, `design_export`, `calibrated`,
   or `qualified`) and reject duplicates, singular transforms, and ambiguous metadata. If no map exists, PDNSim
   `NET_x_y_layer` decoding is allowed only as the scorecard-labeled `pdn_node_proxy_fallback`.
   The bundled map is an explicit project-authored synthetic proxy, not a package bump export.
   Never turn that provenance improvement into a fidelity claim. For joint-shape studies use
   `mesh3d.solder_bump` through `solve_solder_joint(joint_shape=, R_mid=)`. Keep the cylinder as the
   frozen shear oracle; treat barrel/hourglass results as sensitivity until independently
   qualified. The stateful Anand BVP still uses a regular cuboid and must be labeled separately.

6. **Update the claim surface with the code.** Update `docs/GEOMETRY.md`, `docs/api.md`,
   `docs/capabilities.md`, `docs/lessons_learned.md`, and any technical report that states geometry
   coverage. Say “device-shaped” or “parametric” unless imported package CAD and its object mapping
   are actually present.
   Maintain the twelve-family gap-closure scorecard at the top of `docs/capabilities.md`. Change a
   status or mark a round advance only when the same change supplies executable evidence. Preserve
   the fixed denominator and use exactly three project states: demonstrated for selected workflows,
   partial, or open. Never translate a local demonstration into “the ecosystem gap is closed.”
   Lead with the project's niche: EDA-aware, validation-first coupling and local interconnect/package
   reliability. Do not describe CoupFE-EDA as universally strong across electromagnetics, CFD,
   semiconductor devices, full package CAD, optimization, PDK qualification, or signoff.

7. **For TSV-to-device work, enforce the release scorecard.** Read
   `CoupFE_EDA_TSV_Device_Validation_Release_Plan.md` and
   `docs/TSV_ANISOTROPIC_3D_PLAN.md`, `docs/TSV_PHYSICS_AUDIT.md`,
   `docs/PERIODIC_BOUNDARY_CONDITION_PLAN.md`, and
   `benchmarks/tsv_release_scorecard.json`. Preserve the
   canonical all-Hex composite-cylinder oracle; use `mesh3d.tsv_device_submodel` and
   `tsv_local_3d` for the thin-liner/free-surface Tet4 path. Keep curvature as calibration and specimen-C/D Raman
   curves as held validation. Compute the measured stress sum at 0.2 µm depth; never substitute
   von Mises or a surface contour. Preserve `release_validation=false` for the Lamé-driven device
   preview. Only change a blocked category to passed when its exact metric, source manifest hash,
   revisions, and regression evidence exist. Literature mobility equations are model verification,
   not transistor validation.
   For Raman convergence, declare `h_near_um`/`refine_extent_um`, stress recovery, and any
   `spot_sigma_um`. The paper says sub-micron resolution but does not freeze an exact width; never
   tune the Gaussian spot sensitivity to pass the mesh gate. Preserve failed refinement evidence.
   Record `boundary_condition` too: `minimal_rigid` only removes null modes; it is not a far field.
   Require a sidewall-plus-bottom oxide cup and zero direct Cu/Si interface nodes. Record the
   right-handed coordinate frame, proper crystal-to-global rotation, and material/mesh SHA-256
   identities with every accepted numerical artifact. A material-region label alone is not a
   topology gate.
   Use `silicon_free_expansion` for isolated-domain sensitivity until conservative global–local
   displacement/traction transfer exists, and require the ≤3% domain-enlargement gate.
   For Jiang specimen validation, do not force an isolated cylindrical far field to represent the
   array: use the published 40/50 µm periodic cell and declared [110]/[1-10] boundary semantics.
   `tsv_periodic_cell` must report `matching_nodes_verified` before mechanics. Use
   `solve_local_tsv(..., boundary_condition="periodic_macro_gradient", macro_gradient=H)` only with
   an explicit, sourced macro mode; preserve the separate geometry/mechanics statuses and record
   constraint hash/error, pair mismatch, reduced DOFs, and `H`.
   Put only exact, mesh-agnostic affine reduction (`U=Pq+U0`, `Rq=P.T@R`,
   `Kq=P.T@K@P`) in CoupFE Core. Keep `PeriodicBox`, translated-node matching,
   corner-equivalence relation construction, Gmsh pairing inputs, the TSV
   macroscopic-strain mode, thermal history, Raman observable, and benchmark
   semantics in CoupFE-EDA. Pin the exact clean-root Core revision for periodic
   tests, and verify that it is publicly reachable before release. Never default the periodic jump
   to zero for a thermally expanding cell. Require the homogeneous free-expansion and fixed-box
   broken-control pair before heterogeneous mismatch. CoupFE's bulk/history-free
   `solve_distributed_affine` reference passes an analytic 1/2/4-rank gate, but it replicates
   constraint setup/final lifting. Do not claim scalable or TSV-parallel MPC until memory-local
   equivalence-class ownership and a real TSV serial==N-rank gate pass.
   Report periodic status with all seven fields: geometry pairing, serial mechanics, direct reduced
   assembly, core MPI reference, production memory locality, state/contact/dynamics, and named
   consumer validation. Use `docs/PERIODIC_MPC_STATUS.md` as the current evidence ledger.
   When updating status, run the fast EDA tier and focused periodic consumer, then the core algebra
   and MPI gates when available. State the last complete toolchain date separately from focused
   reruns; never imply unexecuted tests passed.
   Keep Jiang's periodic vehicle separate from Ryu's isolated 200 µm/no-oxide benchmark. Treat old
   refinement/domain numbers from the sidewall-only geometry as superseded failed evidence and rerun
   them on the corrected scene.

8. **Debug multiphysics in a physics-first order.** A passing solve or test suite is necessary but
   never sufficient. Before changing implementation code, write and inspect the case contract in
   this order:
   - model/benchmark intent and fidelity;
   - generated geometry, material topology, dimensions, interfaces, and coordinate origin;
   - governing equations, constitutive assumptions, coupling direction, omitted mechanisms, and
     reference state;
   - unit and sign ledger from inputs through assembly to outputs;
   - loads, physical boundaries, symmetry/periodicity, axes, and measurement definition;
   - mesh quality/connectivity, conservation, residuals, convergence, recovery, and uncertainty;
   - implementation, broken control, and permanent regression gate.
   Do not equate algebraic constraints with physical boundary conditions: rigid pins remove null
   modes but do not create an infinite or periodic medium. Inspect material adjacency directly; a
   nonempty named region and positive volume do not prove the correct topology. When topology,
   units, constitutive physics, reference state, loading, or BCs change, invalidate and rerun every
   dependent convergence/validation result. Record a defect as `(symptom, physical consequence,
   root cause, fix, executable guard, remaining limitation)` in `docs/TSV_PHYSICS_AUDIT.md` and add
   the reusable reasoning to `docs/lessons_learned.md`.

## Two test tiers — and where a new model goes
- **Fast (53 gates):** `python -m eda_multiphysics.run` (~30 s) / `pytest eda_multiphysics` — numpy/
  scipy/coupfe only. A new *numpy/scipy* model adds a gate here (with a broken control).
- **Fast integration/CLI (16 tests):** `pytest tests/test_integration_regressions.py`.
- **TSV-device foundation (9 tests):** `pytest tests/test_tsv_device.py` — cubic crystal rotation,
  Raman and mobility observables, stable-ID device screening and SVG back-annotation, manifest
  hashes, and the fail-closed release scorecard. These are numerical/model-verification gates, not
  experimental TSV validation.
- **Local-TSV foundation (4 tests):** `pytest tests/test_tsv_local_3d.py` — cubic engineering-Voigt
  stiffness, Tet4 affine strain and thermal-stress recovery, exact Raman-depth coordinates,
  volume/L2 recovery, explicit Gaussian spot quadrature, and fail-closed field lookup. These do not
  replace mesh convergence or experiment.
- **Toolchain tier (19 tests):** `pytest -m toolchain` (`tests/test_toolchain.py`) — the compiled 3-D /
  geometry / thermo-mechanical / reliability models (need gmsh + petsc4py + gfortran). A new *compiled/gmsh/
  distributed* demo MUST add a test here: build the kernel once (a fixture, pass `mod=`), call the
  **public** API, assert the closed-form oracle within tolerance, and **assert the mechanism not just
  the result** (e.g. the FieldSplit `ksp_its` bound proves the rigid-body near-null-space, not mere
  convergence). Keep the contract numbers in `docs/REFACTOR_CONTRACT.md`. A bare `pytest` excludes
  toolchain by default (`addopts = "-m 'not toolchain'"`); opt in with `-m toolchain`.
- **Current paired execution (31 July 2026):** against public Core `933e497`, the standalone
  harness passed 53/53 gates, the default tier passed 94/94 tests with 19 toolchain cases
  deselected, and the separate toolchain tier passed 19/19 with 94 default cases deselected. The
  harness gates overlap the default wrappers; these are regression/model-verification results,
  not experimental TSV validation.
- **Historical execution (12–13 July 2026):** the earlier 82/82 fast and 19/19 toolchain run, real
  Gmsh periodic-consumer run, and Core 1/2/4-rank reference remain dated implementation context,
  not current release or performance evidence.
- **Don't re-roll the Newton loop.** New 3-D coupled solves use `_coupled_solve.coupled_newton(groups,
  ndof, dirichlet, linsolve)` with a local linear backend; multi-material = a list of `ElementGroup`s.

## Running and shipping
- EDA integration + distributed demos: `RESULTS.md`, `DISTRIBUTED.md`. Toolchain/container: `CONTAINER.md`.
- Component ownership/count rules: `docs/COMPONENTS.md`. The call surface: `docs/api.md`. Geometry
  contract: `docs/GEOMETRY.md`. The math/oracles:
  `docs/theory.md`. Why-we-did-it: `docs/lessons_learned.md`. Gap status and its fixed denominator:
  the opening scorecard in `docs/capabilities.md`.

## What does NOT belong here
General CoupFE solver/numerics lessons (complex-step safety, the coupled-convergence gate,
distributed 1-vs-N invariant mechanics) belong in **CoupFE core** `skills/` — they help every
downstream project, not just EDA. This repo holds only the EDA-multiphysics integration glue
and its validation.

**Solver setups:** the per-case KSP/PC details stay HERE (`etv_fieldsplit.py`,
`DISTRIBUTED.md` — FieldSplit-per-field, CG+GAMG for the PDN, superlu_dist for 1-vs-N);
the cross-project ladder + traps (when direct vs AMG vs FieldSplit, symmetric Dirichlet
for CG, the two 1-vs-N tolerance regimes, rank-dependent-iterations = PC bug) are
consolidated in CoupFE-core `skills/performance.md`, "The solver ladder". Read that before
adding a new solver setup here.
