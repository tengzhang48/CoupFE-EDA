# Historical snapshot: Periodic boundary-condition plan

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/PERIODIC_BOUNDARY_CONDITION_PLAN.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# Periodic boundary-condition plan: CoupFE core and the TSV consumer

**Plan date:** 12 July 2026; **ownership revised:** 30 July 2026
**Decision:** implement a reusable, mesh-agnostic **affine
constraint/reduction system in CoupFE core**. Periodic boundary conditions are
an application-side producer of that system. Keep the periodic box, translated
node matching, relation construction, Gmsh scene construction, TSV lattice
semantics, thermal history, and validation observables in CoupFE-EDA.
**First consumer:** the corrected 40 × 50 µm Jiang Cu/oxide-cup/Si cell.
> **Release-evidence boundary:** exact errors, timings, iteration counts, and
> scale figures in this dated plan are historical local observations without
> retained raw logs and a locked environment. Rerun them before citation.
> Current public API and ownership statements are identified explicitly.

**Current status:** legacy CoupFE branch `feature/periodic-mpc` implemented the
whole prototype. For the public ownership split, `eda_multiphysics.periodic`
now owns `PeriodicBox`, strict translated-node pairing, and
corner-equivalence relation construction; it consumes only Core's generic
affine relation/compiler. CoupFE-EDA uses Gmsh periodic surfaces with equal
node counts and exact correspondence and passes homogeneous
free-expansion/fixed-box controls plus heterogeneous reduced equilibrium.
The legacy Core branch also has a bulk/history-free PETSc reference MPC solve that matches an analytic
periodic-gradient solution at 1/2/4 ranks; its constraint setup/final lift are replicated, so
production memory-local MPI remains open. The source-equivalent macro/bottom BC and corrected-scene
convergence also remain open.

The name used in APIs and documentation should be **periodic boundary condition (PBC)**, not
“periodical boundary condition.”

## 1. Why the reusable feature belongs in core

The solver operation is not TSV physics. Hanging nodes, periodic cells, cyclic symmetry, tied DOFs,
and prescribed affine fields all need the same algebra: dependent full-space degrees of freedom are
represented by independent reduced degrees of freedom. CoupFE's longer-term mesh design already
states the corresponding constraint form for hanging nodes,

\[
    U = Pq + U_0, \qquad
    R_q = P^T R(U), \qquad
    K_q = P^T K(U)P .
\]

This is a correctness-critical assembly/solver transformation and is therefore a good core
capability. The application decides which nodes are related and what physical jump `U_0` means.

## 2. MD-style periodic-box interpretation

The molecular-dynamics analogy is useful and should become the user-facing mental model:

- create one physical cell containing the actual finite elements;
- store its origin and lattice vectors as a periodic box;
- identify degrees of freedom on opposite periodic faces;
- interpret those identifications as an infinite repetition of the cell;
- do not clone image elements into the assembled continuum system.

For the TSV, the physical cell contains one Cu via, its oxide cup, and the surrounding silicon that
fills the rectangular box. It is periodic in `x=[110]` and `y=[-110]`, but **not** in `z`: the wafer
surface remains free and the bottom keeps its separately declared model condition. This is an
MD-style periodic **slab**, not a fully three-periodic torus.

The periodic box is metadata and constraint topology, not another material. Silicon, oxide, and Cu
still have ordinary physical elements inside the box. The lateral silicon boundary is simply
identified with its translated image. For local continuum mechanics, no element needs to cross the
boundary and no ghost-image volume elements contribute energy. Image shifts are useful only for
visualization and, later, for interactions whose search stencil crosses a boundary (contact,
particles, or a nonlocal model).

### The box must be allowed to deform

In MD, periodic coordinates are often expressed relative to a box matrix and the box can change
under imposed strain or a barostat. The FE analogue is central here. Let the reference lattice
vectors be columns of `A`. Under a prescribed macroscopic displacement gradient `Hbar`,

\[
    A_{current}=(I+\bar H)A,
\]

and the boundary displacement jump is `Hbar @ a_i`. Holding the box fixed means `Hbar=0`; during
cooling that would suppress overall contraction and generate a constrained thermal stress. It is
not a neutral periodic default.

The first core release should support a **prescribed box deformation**. A later stress-controlled
cell can make selected box-strain components unknown and solve them from a target average stress.
That is analogous to an MD barostat, but it is not required for the first TSV step.

### EDA-owned box object

Keep the lattice and mesh-correspondence object in the application layer,
separate from Core's constraint algebra:

```python
from eda_multiphysics.periodic import PeriodicBox

PeriodicBox(
    origin,
    lattice,                 # ndim x ndim reference box matrix
    periodic=(True, True, False),
    coordinate_frame=None,
)

box.fractional_coordinates(points)
box.wrap(points)
box.translation(axis, direction=+1)
box.image_shifts(layers=1)             # visualization/search only
box.deformed_lattice(macro_gradient)
box.pair_faces(coords, minus, plus, axis, atol=...)
```

`PeriodicBox` is deliberately not called a “cell,” because CoupFE already uses cell/element language
for physical finite elements. It validates the box and supplies translations; it does not create FE
elements, choose materials, choose `Hbar`, or apply constraints. A singular or left-handed lattice
is rejected. The
TSV result should record the reference/deformed lattice, periodic axes, and box hash.

`wrap` and `image_shifts` must never rewrite the authoritative FE mesh or clone image volumes into
assembly. They are coordinate-query/search/visualization helpers. Boundary nodes on both faces stay
in the physical mesh and are related only by the constraint transform.

### Where connectivity and state live

Material history remains exactly where CoupFE already puts it: in each physical bulk element's
quadrature/state storage. Cu plasticity state, for example, belongs to Cu elements; silicon and oxide
elements retain their own material state. Periodic identification does not merge, duplicate, or move
element state.

The periodic relation itself is normally **stateless**. It stores immutable setup/provenance data:
master/slave node IDs, lattice translation, selected components, affine jump law, equivalence class,
and constraint hash. A load-dependent offset is evaluated from the current load state; it is not a
committed constitutive history variable. Unknown box strain, if added later, is a global generalized
DOF, not element state.

The user's “element connects the nodes on two sides” picture maps cleanly to reduced connectivity.
For physical element `e` with ordinary gather `G_e`,

\[
    U_e=G_e(Pq+U_0).
\]

Thus elements touching the minus and plus faces gather the same representative reduced boundary
DOFs. They are connected across the periodic seam **algebraically**, without adding a fictitious
material element. The element residual returns through the transpose map,

\[
    R_q=\sum_e P^T G_e^T R_e.
\]

Keep two notions separate:

- **geometry connectivity:** original physical nodes and unwrapped coordinates used for element
  Jacobians, volumes, and constitutive integration;
- **solution connectivity:** full-to-reduced DOF map that identifies periodic representatives.

Do not replace a plus-face node coordinate with its minus-face coordinate inside a boundary element;
that can make an element appear to span or collapse across the full box. A future mesh that truly has
an element crossing a periodic seam would need per-element image shifts for geometry unwrapping, as
in MD. The current TSV mesh does not need seam-crossing elements: it needs opposite-face DOF
identification.

A user-facing `PeriodicLink`/constraint record may make the pairing visible in output, but it should
not be a physical energy-bearing element. An exact Lagrange-multiplier connector is a possible later
backend for cases elimination cannot cover; a penalty connector is not the reference method.

Do **not** implement the first version as:

- a penalty spring between opposite faces: it introduces a conditioning/calibration parameter and
  is not exact;
- an application-specific edit inside `tsv_local_3d`: that would duplicate the same algebra for the
  next application;
- a residual-only `Operator`: exact elimination changes the solution space and must transform every
  operator's assembled residual and tangent consistently;
- an unconditional zero displacement jump: that suppresses macroscopic thermal expansion;
- a Lagrange-multiplier saddle point as the first route: it adds DOFs and solver/preconditioner
  complexity when matching-node elimination is sufficient.

## 3. Physical and mathematical contract

For a slave/master node pair separated by lattice vector `a`, translational periodicity is

\[
  u_s-u_m=\bar H a,
\]

where `u` is displacement and `Hbar` is the declared macroscopic displacement gradient. The
periodic fluctuation is `w=u-Hbar X`, so `w_s=w_m`. For small strain, only the symmetric part of
`Hbar` contributes to strain, but the API should accept the full gradient so affine rotation tests
and future finite-strain use are unambiguous.

For a scalar field `phi`, the analogous relation is

\[
  \phi_s-\phi_m=\bar g\cdot a.
\]

The general block relation is

\[
  U_s = Q U_m + b,
\]

where `Q=I` for translated cells and a proper rotation can later represent cyclic periodicity. The
first release should support real-valued, matching-node, translated periodicity with constant `P`
and a prescribed load-dependent offset. Rotational/cyclic `Q` is designed into the data model but
deferred until translational PBC is qualified.

For a linear thermal problem `KU=f`, substitution gives

\[
  (P^T K P)q=P^T(f-KU_0).
\]

For a nonlinear problem, assemble the existing full-space operators at `U=Pq+U0`, then reduce their
sum. Operator kernels and material code do not change.

Only kinematics are imposed explicitly. With a conforming variational formulation, equilibrium in
the reduced space makes opposite-face tractions anti-periodic and scalar fluxes anti-periodic. Do
not add separate traction/flux equality equations: that would duplicate the weak equilibrium and
can overconstrain the cell. Add diagnostic gates that verify the paired resultant instead.

### Macroscopic thermal strain is a separate physical choice

PBC supplies the fluctuation relation; it does not determine `Hbar`. CoupFE-EDA must select and
record one of these modes:

1. `prescribed_macro_gradient`: a stated `Hbar`, for example silicon free contraction
   `alpha_Si*dT*I` as an isolated wafer approximation;
2. `global_transfer`: a boundary jump derived conservatively from a qualified global wafer/array
   solution;
3. `zero_average_stress` (later): promote macroscopic strain components to unknowns and impose a
   target average stress, normally zero for an unconstrained free cell.

Global transfer must not be restricted to a constant `Hbar`. Wafer membrane strain plus curvature
can make the pair jump vary with depth, for example `b=b(z)`. The generic relation therefore accepts
an offset per paired DOF (or a callback evaluated at the current load state); `Hbar@a` is convenience,
not the underlying limitation.

Mode 3 needs generalized reduced DOFs but does not require abandoning the transform. Columns
representing independent macroscopic strain modes can be added to `P`; stationarity with respect to
those columns supplies the average-stress equations, and a prescribed target stress appears as a
generalized load. This variable-box or “FE barostat” mode is outside the MVP, but the sparse transform
must allow multiple nonzeros per full DOF so the extension does not require an API rewrite. The TSV
implementation must not silently choose a macro mode merely to obtain a stable solve.

## 4. Implemented Core/EDA API split

The 30 July release worktrees implement this ownership split:

```text
# CoupFE core: mesh-independent algebra only
coupfe/constraints/__init__.py
coupfe/constraints/affine.py
tests/test_affine_constraints.py

# CoupFE-EDA: lattice, matching, and relation construction
eda_multiphysics/periodic.py
tests/test_periodic_adapter.py
```

Core public objects:

```python
ConstraintRelation(
    slave,
    masters,
    coefficients,
    offset=0.0,
    label="",
)

ConstraintTransform(
    P,                 # sparse full <- reduced prolongation
    offset,            # full-space U0 at the current load state
    independent_dofs,
    relations,         # canonical scalar equations
    sha256,             # deterministic compiled-relation digest
)

compile_affine_constraints(
    ndof,
    relations,
    *,
    dirichlet=None,
) -> ConstraintTransform
```

EDA public adapter objects:

```python
PeriodicBox(origin, lattice, periodic, coordinate_frame=None)
PeriodicNodePairs(...)
match_periodic_nodes(
    coords,
    master_nodes,
    slave_nodes,
    translation,
    *,
    atol,
    rtol=0.0,
) -> PeriodicNodePairs

periodic_relations(
    pair_sets,
    *,
    dof_per_node,
    components,
    coords=None,
    macro_gradient=None,
    scalar_gradient=None,
    label="periodic",
) -> tuple[ConstraintRelation, ...]
```

Core deliberately does not expose `PeriodicBox`, node matching, a periodic
graph, or mesh/lattice provenance. EDA translates those mesh-specific records
into the generic Core relations.

`ConstraintTransform` currently provides:

```python
transform.lift(q)                 # P @ q + offset
transform.restrict_residual(R)    # P.T @ R
transform.reduce_tangent(K)       # P.T @ K @ P
transform.reduce_linear_system(K, f)
transform.relation_matrix()       # C, g
transform.constraint_error(U)     # C @ U - g, or relation-wise equivalent
```

For an increment, use `P @ dq` directly; Core intentionally has no
`project_increment()` convenience method. Never add the affine offset to an
increment.

`P` is a general sparse prolongation, not a one-master lookup table. The matching translational MVP
will usually have one representative entry per periodic component, but macro-strain modes, hanging
nodes, and later rotational constraints may add more.

The builder must be deterministic under node renumbering and must expose provenance: source labels,
pair tolerance, lattice vectors, component selection, number of full/reduced DOFs, equivalence
classes, anchors, and a hash of the compiled relations.

### Solver compatibility and backward compatibility

Add an optional `constraints=None` argument to the serial drivers. Existing calls and the current
Dirichlet path remain byte-for-byte behaviorally unchanged when it is absent.

At each load increment:

1. combine periodic relations, rigid-mode anchors, and the current ramped Dirichlet values;
2. compile or update `U0`; `P` stays constant when topology is unchanged;
3. keep the Newton unknown in reduced coordinates `q`;
4. lift before every residual/tangent/operator call;
5. reduce the assembled residual and tangent;
6. line-search in `dq`, with trial full state `U+alpha*P*dq`;
7. commit operator state using the accepted full `U`;
8. recover the full residual/reactions for diagnostics.

`P.T@R=0` is the primary equilibrium statement. A scalar “reaction on a periodic constraint” is not
unique if redundant face equations were retained, so the compiler must first remove redundancy and
store an independent relation basis. Report full nodal residuals, paired force/flux resultants,
generalized macro forces, and the chosen independent constraint reactions separately.

The transformation should also expose a linear-system helper so CoupFE-EDA's current SciPy
small-strain solve can consume the core feature without being rewritten around CoupFE operators.

Use two implementations of the same algebra in sequence, not two competing semantics:

1. **Reference path:** assemble the current full system and apply sparse `P.T@R` / `P.T@K@P`.
   This is easiest to audit against KKT and should land first.
2. **Compiled connectivity path:** for matching translational PBC, replace each element's solution
   gather with canonical reduced DOF IDs plus its local affine offset. Elements on both box faces then
   assemble directly to the same reduced IDs. This is the natural scalable form of “the elements
   connect across the box” and avoids building a full matrix only to reduce it.

The reference and direct-reduced paths must give the same `U`, residual, energy, reactions, and
element states before the latter becomes the performance/distributed path. Do not optimize by
changing physical element connectivity or coordinates.

`Model.periodic(...)` is phase-two convenience. Per CoupFE's pipeline rule, add it only after the
hand-wired transform and solver path are tested.

## 5. Pairing, edges, and corners

### Matching-node requirement for the MVP

The original scaled TSV cell had unequal opposite-face node counts and was correctly rejected by
the strict matcher. CoupFE-EDA now requests periodic-compatible surface meshes from Gmsh: the
scaled regression has 142 nodes on each x face and 106 on each y face, and the independent core
matcher reports zero translated-coordinate mismatch. Nonmatching meshes remain ineligible for the
matching-node MVP.

`match_periodic_nodes` should:

- translate master coordinates by the declared lattice vector;
- find the slave match with a spatial index;
- require equal counts and a one-to-one bijection;
- reject missing, duplicate, or multiply claimed nodes;
- report maximum/RMS coordinate mismatch and the tolerance scale;
- be invariant to input ordering and global node renumbering;
- preserve raw Gmsh master/slave tags as provenance when supplied.

Do not silently nearest-neighbor a nonmatching mesh. Mortar/interpolation PBC is a separate feature.

### Equivalence classes

Corner and edge nodes belong to more than one periodic face pair. Naively imposing every pair can
create duplicate or contradictory slave equations. The compiler should form node/DOF equivalence
classes with a deterministic root, compose lattice offsets, and verify every closed relation cycle.

For the translational MVP, each periodic DOF has one reduced representative and an affine offset
derived from its coordinate relative to the class root. Gates must verify:

\[
  CP=0, \qquad CU_0=g,
\]

and reject inconsistent cycles. Choose roots by canonical geometric/stable-ID ordering, not by input
list order. The physical solution must be invariant under node renumbering; a DOF-index-based hash
may legitimately change, while a separate geometry/relation provenance hash should be canonical.
General weighted/rotational equivalence classes can follow later.

### Rigid modes and conflicts

Periodic displacement fluctuation retains rigid translation. The application must add an explicit
anchor (for example, all displacement components of one representative node) or a later mean-zero
fluctuation constraint. The current constraint compiler diagnoses relation-graph conflicts; it
does not inspect an assembled system for a remaining null space. Null-space diagnosis and pinning
remain the application/solver's responsibility, with a generic solver diagnostic as future work.

The compiler must reject:

- a dependent DOF with conflicting Dirichlet values;
- a master that becomes dependent through an inconsistent cycle;
- duplicate equations with different offsets;
- periodic relations across different field components unless an explicit block transform permits
  them;
- improper rotations for future cyclic-vector constraints.

## 6. Core versus CoupFE-EDA ownership

| Concern | CoupFE core | CoupFE-EDA |
|---|---|---|
| Sparse affine transform and exact reduction | Own | Consume |
| Periodic-box/lattice metadata, wrapping, and image shifts | No | Own `PeriodicBox` and define the TSV box |
| Deterministic matching-node correspondence and periodic relation construction | No | Own, validate, and supply faces/lattice vectors |
| Gmsh periodic-compatible surface generation | No | Own |
| Material regions and oxide-cup topology | No | Own |
| Crystal/global coordinate frame | Validate generic matrices | Define and record TSV frame |
| Macroscopic strain/gradient value | No physics default | Define from benchmark/global model |
| Thermal reference state and `dT` | No | Own |
| Raman plane, recovery, spot averaging, mobility/KOZ | No | Own |
| Serial reduction tests | Own | Add consumer integration gate |
| Distributed reduction and 1-vs-N invariant | Own later phase | Add TSV scale consumer after core passes |

This division preserves CoupFE's small-core philosophy: Core owns a general,
tested algebraic mechanism, not a periodic-mesh policy, TSV model, or mesher.

## 7. Validation ladder

Every level needs an independent oracle and a deliberately broken control.

### Level A — relation and transform algebra

- Pair translated 2-D and 3-D faces after random node permutation; recover the exact bijection.
- Verify periodic-box wrapping, fractional-coordinate round trip, lattice deformation, and image
  shifts independently of FE assembly; reject singular/left-handed boxes.
- Reject unequal counts, one duplicated pair, one coordinate outside tolerance, and an inconsistent
  corner cycle.
- Verify `C@P=0`, `C@U0=g`, and the adjoint identity
  `<Pq,R>=<q,P.T@R>` to roundoff.
- Compare a random symmetric-positive-definite constrained system solved by reduction against an
  independently assembled Lagrange-multiplier KKT system.
- Verify full-space reactions do work only against prohibited variations.
- Verify paired mechanical resultants and scalar fluxes are anti-periodic without imposing separate
  force/flux constraints.
- Broken controls: omit one corner relation, reverse one lattice vector, apply the offset to `dU`
  rather than `U`, or use `P` instead of `P.T` for residual restriction.

### Level B — generic physical patch tests

1. **Scalar periodic gradient:** diffusion on a square/cube reproduces
   `phi=gbar·X+constant` and the analytic uniform flux.
2. **Mechanical affine patch:** a homogeneous elastic cell reproduces `u=Hbar X` and constant
   analytic stress.
3. **Thermal free expansion:** homogeneous thermoelastic material with
   `Hbar=alpha*dT*I` has displacement error and stress near machine precision.
4. **Constrained thermal broken control:** repeat with zero jump; it must develop the analytic
   constrained thermal stress, proving the free-expansion gate can detect the wrong PBC.
5. **Heterogeneous energy gate:** verify Hill–Mandel macro/micro virtual-work consistency for a
   two-material matching-node cell under prescribed macro strain.
6. **Variable jump:** prescribe a depth-dependent pair jump and reproduce a manufactured membrane-
   plus-bending displacement field; this prevents constant-`Hbar` assumptions from entering the
   generic compiler.

### Level C — nonlinear and solver integration

- Reduced residual tangent agrees with finite difference/complex step of the reduced residual.
- Load incrementation and line search preserve constraints at every trial and accepted state.
- Operator commit receives full accepted `U`, never reduced `q`.
- Existing unconstrained/Dirichlet tests remain unchanged when `constraints=None`.

### Level D — CoupFE-EDA TSV integration

- Opposite x/y faces have exact one-to-one correspondence; corners form the expected equivalence
  classes; maximum geometric mismatch is recorded.
- Coordinate/crystal frame and lattice vectors are right-handed and consistent.
- Homogeneous-Si periodic free expansion passes before Cu/oxide mismatch is enabled.
- The heterogeneous cell passes free residual, total force, total moment, and constraint-error
  gates.
- Fourfold-symmetry error meets the frozen tolerance on a symmetry-compatible mesh.
- Corrected-scene mesh/recovery/spot convergence is rerun; old sidewall-only evidence stays
  superseded.
- Only after these gates compare specimens C/D at the exact 0.2 µm Raman plane.

Before choosing the final lateral/bottom setup, re-freeze Jiang's actual quarter-model symmetry
conditions. Demonstrate that the full-cell PBC is equivalent for the symmetric benchmark or clearly
label it as a different array model. Do not use “periodic” as a reason to overwrite source-specific
boundary semantics.

### Level E — distributed core extension

Serial qualification comes first. Then implement either a distributed sparse `P` with PETSc
`MatPtAP`/transpose reduction, or direct reduced-DOF element assembly using the compiled relation
map. Select between them by measurement; do not maintain two production paths without need.

Required gates:

- in-process partitioned reduction equals serial and the gather/reduce adjoint holds;
- real MPI serial equals 2- and 4-rank results to the direct-solver tolerance;
- corner equivalence classes spanning ranks are assembled once and without collective deadlock;
- iterative counts remain bounded across the qualified rank sweep, with any
  rank dependence explained and recorded;
- no production path gathers all full-space volume DOFs on one rank.

## 8. Implementation phases

### Phase 0 — freeze semantics before code

- Confirm generic affine relations/reduction are the Core MVP and
  matching-node translational PBC is the EDA consumer.
- Freeze EDA's `PeriodicBox` origin/lattice/periodic-axis contract and distinguish image generation
  from physical FE assembly.
- Freeze equation signs, master/slave translation direction, component ordering, tolerance scaling,
  offset scheduling, anchors, independent-reaction convention, and the rule that anti-periodic
  traction/flux is an equilibrium diagnostic rather than a second constraint.
- For the TSV consumer, freeze Jiang lateral/bottom semantics and the first macroscopic-strain mode.

**Exit:** reviewed equations and two hand-worked corner/edge examples.

### Phase 1 — serial affine core

**Prototype implemented on `feature/periodic-mpc`; only its mesh-agnostic
relation/compiler belongs in the public Core.**

- Add relation/transform data structures, compiler, validation, hashing, and linear reduction.
- Integrate optional transforms into serial Newton and incremental solve without changing the old
  path.
- Add generic algebra/solver tests and broken controls.
- Document theory, API, lessons, capability status, and the core AI skill.

**Evidence:** 15/15 focused MPC/solver/element/model tests pass. Random SPD reduction matches the
independent KKT solve; `C@P`, `C@U0`, the work adjoint, strict two-axis pairing, corner classes,
thermal free expansion, the zero-jump broken control, and full-`U` element commit are gated. The
complete core run reports 257 passed, 59 skipped, and 2 expected xfails; two untouched baseline
contact tests remain red (a missing numba edge-edge symbol and a 600 s self-contact timeout), so the
branch does not claim a globally green core suite.

### Phase 2 — EDA periodic adapter

- Deterministic translated-node pairing and equivalence-class construction are
  implemented in `eda_multiphysics.periodic`.
- Keep any future convenience API in EDA rather than adding mesh-aware
  `Model.periodic(...)` sugar to Core.
- Gate adapter ownership, strict matching, cycle rejection, and compiled
  affine-constraint behavior.

**Exit:** scalar and mechanical periodic examples work through the EDA adapter
and the generic Core affine primitive.

### Phase 3 — TSV consumer

**Serial integration implemented; physical qualification remains open.**

- Opposite Gmsh faces are periodic-compatible and retain correspondence provenance.
- Geometry now reports `matching_nodes_verified`; mechanics remains a result-level operation.
- `tsv_local_3d` uses EDA-generated relations plus the Core transform and records constraint hash, macro gradient, maximum pair
  mismatch, reduced DOFs, and constraint residual.
- Run Level D without advancing experimental scorecard categories prematurely.

**Current evidence:** free-expansion/fixed-box patch controls and heterogeneous conservation pass.
**Remaining exit:** freeze a source-equivalent macro/bottom setup, then pass symmetry and first
corrected-scene convergence gates.

### Phase 4 — distributed path

- **Legacy research prototype, not current public API:** the quarantined
  `feature/periodic-mpc` work carried `ConstraintTransform.element_map(gm_e)` and
  `solve_distributed_affine`, with historical local 1/2/4-partition checks. The
  clean public Core primitive does not expose either API, and those observations
  are not current release evidence.
- Reintroduce distributed helpers only after they can consume the minimal public
  affine transform without moving EDA mesh/lattice semantics into Core.
- Assign one deterministic global reduced DOF ID and owner to every periodic equivalence class.
- Convert each rank's full element gather to reduced global IDs plus affine offsets; a face pair may
  span ranks, but PETSc `ADD_VALUES` routes both element contributions to the representative owner.
- Ghost reduced values required by local elements; do not replicate the full volume solution or
  assemble a global full matrix followed by `MatPtAP` in the scalable production path.
- Keep full-space sparse `P.T K P` as the serial/reference oracle and require direct reduced
  connectivity to match it before MPI qualification.
- Add 1/2/4-rank invariants and scale evidence before advertising distributed PBC.

The legacy prototype is design input, not proof for this release. All distributed
items above remain production work: memory-local relation compilation/ownership,
proof that no rank replicates the full volume transform or solution, and fresh
1-vs-N gates. Stateful elements, contact, and dynamics also need separate
reduced-space designs and gates.

### Deferred extensions

- nonmatching mortar/interpolation constraints;
- unknown macroscopic strain with prescribed average stress;
- cyclic/rotational periodicity;
- complex Bloch phase periodicity;
- finite-strain cell-vector evolution;
- hanging-node use of the same affine compiler.

## 9. Main failure modes and prevention

| Failure | Prevention gate |
|---|---|
| Nearest-neighbor pairs the wrong node | Strict bijection, mismatch report, permuted-numbering test |
| Image elements are assembled and energy is counted repeatedly | Images are visualization/search only; one physical box owns all volume elements |
| A fully periodic torus is used for a free-surface wafer | Explicit per-axis periodic flags; TSV uses x/y periodic and z nonperiodic |
| A fixed box is assumed neutral during cooling | Record `Hbar` and deformed lattice; thermal free-expansion/zero-jump broken-control pair |
| Constant macro strain is forced onto a bending wafer transfer | Allow explicit pair-wise/depth-dependent offsets and gate a manufactured bending jump |
| Traction/flux periodicity is imposed twice | Enforce kinematics only; verify anti-periodic resultants from reduced equilibrium |
| Edge/corner overconstraint | Equivalence classes plus closed-cycle consistency |
| Zero jump suppresses free thermal expansion | Homogeneous thermal free-expansion oracle and zero-jump broken control |
| Offset is incorrectly applied to Newton increments | Constraint preservation during line search and affine patch test |
| Residual/tangent transforms are inconsistent | `P.T R`, `P.T K P`, reduced tangent-vs-derivative test |
| Rigid translation leaves singular system | Explicit anchor/mean-zero policy and null-space diagnostic |
| Dirichlet conflicts with PBC | Compile-time conflict rejection |
| Correct algebra, wrong benchmark setup | Frozen model/physics/units/BC/observable manifest in CoupFE-EDA |
| Old convergence data reused after topology/PBC change | Evidence invalidation rule and new manifest/hash |
| Serial-only feature described as scalable | Distributed status remains partial until 1-vs-N gates pass |

## 10. Definition of done for the first release

The periodic feature is ready for a first EDA release only when:

- the generic Core affine transform is public, documented, deterministic,
  hashed, and fail-closed;
- the EDA-owned `PeriodicBox` records a valid lattice and per-axis periodicity without duplicating FE
  energy;
- matching-node translational PBC supports selected vector/scalar components and a prescribed affine
  jump;
- edges/corners and Dirichlet conflicts are handled without duplicate equations;
- generic random algebraic tests pass in Core, while EDA's scalar-gradient,
  mechanical-affine, and thermal free-expansion oracles pass;
- every new gate has a broken control that was observed to fail;
- no new regression appears relative to the core baseline, and unrelated baseline failures are
  either repaired separately or explicitly excluded from release evidence;
- the EDA API states that nonmatching, stress-controlled macro strain, cyclic, Bloch, and distributed
  modes are not yet implemented.

The TSV consumer is a separate acceptance step. A passing generic core feature does not validate the
Jiang model, and a passing TSV example does not make CoupFE a universal homogenization package.

## 11. Immediate next action

Freeze Jiang's actual macro/bottom boundary semantics and start the corrected periodic mesh/recovery
convergence study. Separately, continue core Phase 4 from the completed in-process and PETSc
1/2/4-rank reference gates to memory-local constraint ownership/compilation. Repair the two unrelated
core contact failures in separate changes rather than mixing them into MPC work.
