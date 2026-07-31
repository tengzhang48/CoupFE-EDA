# Engineering lessons

This document summarizes implementation lessons that remain relevant to the
public code. It is not a development diary or a record of release status.

## Evidence follows the claim

Different checks answer different questions. An analytic slab can check Joule
heating, a patch test can check element consistency, and a synthetic pipeline
can check data handoffs. None of those establishes real-device accuracy by
itself. Public results should name the equation, geometry, boundary condition,
mesh, input provenance, and tolerance they exercise.

Broken controls are useful when they target a plausible error: removing power,
removing a temperature swing, changing an activation parameter, or imposing a
fixed periodic box. A control that cannot reject the corresponding error adds
little evidence.

## Dependency identity is part of the result

CoupFE-EDA depends on a precise Core contract. A Python environment can import
a different local checkout even when its package name matches. Setup and
release evidence therefore record the imported path, Git origin, branch, full
revision, and cleanliness. The release candidate pins
`454f73ce2de284262b214a2b37bd676c6aca3c0a`.

Geometry-specific adapters stay in EDA. Core receives coordinates,
connectivity, operators, and generic affine relations without EDA object or
periodic-face policy.

## Stateful solves need explicit convergence and commit semantics

A stateful constitutive operator must update history once per accepted
increment. CoupFE's `newton_solve` calls `commit` after its iteration loop even
though the returned iteration count is not a convergence flag; an EDA driver
must establish convergence independently and must not call `commit` again.
Duplicate commits can change accumulated work even when a basic finite-value
test remains green.

Likewise, returning an iterate is not evidence of increment convergence. A
public stateful cycle/BVP driver needs an explicit convergence result, a
fail-closed policy, and a regression that exercises failure. The previous
plane-strain ETV cycle and multi-element stateful solder BVP functions were
removed because they did not meet that boundary. The retained
`prescribed_hex8_cycle` fixes every face displacement and checks the material
state path; it is labeled as a one-element exercise.

## Coupling should be checked in limiting cases

Coupled implementations are easier to review when they reduce to a known
limit. The electrothermal examples use constant-conductivity slab heating,
zero-voltage/zero-power controls, power balance, and monolithic-versus-
sequential agreement. A coupling effect measured on a reduced or fixed mesh
should remain labeled with that model; it does not transfer automatically to a
package geometry.

Complex-step tangents are useful for smooth residuals. They are not applicable
through root finders, `abs`, `sign`, or other non-analytic operations in an
Anand return map. Those paths need an explicitly documented tangent and
increment-convergence strategy.

## Geometry is more than connectivity

A usable EDA/mesh handoff needs:

- units and coordinate frame;
- stable design-object identifiers;
- material-region identity;
- boundary sets and their physical meaning;
- transform and source provenance; and
- mesh-quality and input digests.

The blind-TSV geometry exposed why topology checks matter: a sidewall liner
without a bottom cap can create an unintended Cu/Si interface. The corrected
generator fails closed on that contact. Conformal package fragmentation and
volume-node filtering similarly prevent disconnected regions or orphan CAD
nodes from silently entering an FE system.

## Periodic pairing and periodic mechanics are separate

Matching opposite surface nodes establishes geometry correspondence. It does
not select a macroscopic strain, bottom boundary, or experimental setup. The
mechanics API requires `Hbar` explicitly and records pairing and solve status
separately. Homogeneous free expansion and fixed-box behavior form a useful
control pair, while physical TSV interpretation still requires corrected-scene
convergence and source-equivalent boundaries.

## Recovery is a modeling choice

Constant-element stress, volume-weighted nodal averaging, P1 L2 projection,
point sampling, and Gaussian spot averaging are different numerical
observables. They should not be interchanged without a sensitivity study.
Raman depth, spot size, line direction, coordinate alignment, and uncertainty
must be recorded with any measured comparison.

## Distributed evidence needs retained context

A serial-versus-MPI comparison at selected ranks can check a distributed path.
It does not establish general scaling. Timing, memory, and iteration claims
also require the matrix size, partition, solver options, PETSc/MPI/compiler
versions, hardware, rank placement, raw output, and repeated-run policy.
Unretained exploratory timing should not appear as a release claim.

## Synthetic data should be explicit

The bundled PDN and joint-map files are project-authored regression fixtures.
Their manifests state how values were generated, include hashes, and label the
composed workflow as synthetic. External designs, PDKs, and generated tool
outputs remain caller-supplied unless their redistribution terms are clear.

This boundary keeps the demo runnable without implying permission to
redistribute third-party design data. Citations can show that the same
framework applies to external data without bundling that data.

## Release records are separate from the worktree

Build directories, caches, bytecode, and generated kernels are disposable.
Release evidence is a new immutable checkpoint containing source identities,
environment, complete logs, artifacts, and checksums. A public status document
summarizes that record but cannot replace it.

AI agents can assist with code, tests, and documentation. Agent review is not
an oracle; checked source, tests, cited references, retained logs, and
engineering judgment remain the evidence.
