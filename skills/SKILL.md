---
name: develop-coupfe-eda
description: Develop, review, and validate CoupFE-EDA adapters, multiphysics models, geometry, examples, documentation, and release evidence.
---

# CoupFE-EDA contributor guide

CoupFE-EDA is experimental research software built on CoupFE. It demonstrates
one way to connect EDA data with finite-element and reliability workflows. The
repository is not a signoff tool, a universal multiphysics environment, or a
complete package-CAD system. Claims should stay within the evidence retained in
this repository.

AI agents can accelerate code navigation, adapter scaffolding, test generation,
and documentation review. Their output still requires engineering review and
executable checks. An agent's analysis or a plausible-looking result is not
validation evidence by itself.

## Repository boundary

Keep broadly reusable numerical mechanisms in CoupFE Core. Keep EDA meaning and
application policy in this repository.

CoupFE Core owns:

- generic elements, operators, assembly, and solver interfaces;
- mesh-independent affine-constraint algebra;
- reusable code-generation and compiled-element interfaces; and
- numerical utilities that have a clear cross-application contract.

CoupFE-EDA owns:

- OpenROAD, PDN, layout, and package-data adapters;
- design-object identity, units, coordinate frames, and provenance;
- Gmsh construction, mesh adaptation, region and boundary semantics;
- periodic-cell pairing and EDA-specific constraint construction;
- electrical, thermal, mechanical, and reliability model composition;
- material choices, loading scenarios, observables, and case-specific solvers;
- examples, benchmark interpretation, and application validation records.

Do not move mesh or design semantics into Core merely to share one EDA example.
If a generic abstraction emerges, propose it separately with a small
contract and Core-level tests, then qualify the EDA consumer against the chosen
public Core revision. `setup.sh` is the source of truth for that revision.

Use `docs/COMPONENTS.md` and `docs/api.md` for component and API boundaries,
`docs/GEOMETRY.md` for mesh contracts, `docs/capabilities.md` for current scope,
and `docs/VALIDATION_GUIDE.md` and `docs/RELEASE_EVIDENCE.md` for evidence.

## Evidence and claims

Classify each result before describing it:

1. **Structural check**: schema, topology, conservation, or API behavior.
2. **Analytic or manufactured verification**: comparison with a closed form,
   patch test, invariant, or manufactured solution.
3. **Independent numerical comparison**: two implementations or solvers agree
   over a stated domain and tolerance.
4. **Published benchmark comparison**: traceable parameters and observables.
5. **Experimental comparison**: declared measurement, uncertainty, and role.
6. **Composed-workflow check**: tested components preserve intended quantities,
   identity, units, and frames across a handoff.

A component check does not validate the composed device workflow. Calibration
is not held-out validation. A synthetic design checks software behavior but does
not establish accuracy for a fabricated device. Label exploratory work as
research or open when an independent reference is not yet available.

For every quantitative statement, retain or cite:

- source and dependency revisions, exact inputs, units, frames, and boundaries;
- measured quantity, extraction method, tolerance, and rationale;
- command, environment, and complete result; and
- known exclusions or unresolved discrepancies.

Use words such as “passes this check,” “agrees within the stated tolerance,” or
“demonstrated for this case.” Avoid turning one case into a general capability
or performance claim.

## Adding or changing a workflow

Start with a short case contract:

1. State the engineering question and intended fidelity.
2. Identify input sources, stable object IDs, units, and coordinate frames.
3. Declare equations, constitutive assumptions, reference states, and omissions.
4. Name loads, physical boundaries, symmetry or periodicity, and outputs.
5. Select an evidence class and an independent comparison when available.
6. Choose discretization, coupling, and solver settings appropriate to the case.
7. Implement the smallest supported path and add risk-proportional tests.
8. Record limitations next to the result and update the public claim surface.

## Units, frames, identity, and provenance

Treat metadata as part of the numerical input. A design adapter should carry:

- stable design and object identifiers plus the declared source and tool version;
- original units and explicit conversion into solver units;
- a named, right-handed frame and source-to-mesh-to-report transforms;
- region, material, layer, and boundary meanings;
- extraction settings and relevant file or record digests; and
- a fidelity label: synthetic proxy, design export, calibrated, or qualified.

Reject ambiguous units, singular transforms, duplicate IDs, and incomplete
required metadata at the adapter boundary. Avoid inferring DBU, material,
power-source meaning, or geometry fidelity from a filename or array shape.

Maintain a unit ledger through every handoff. Include electrical power sign,
temperature reference, stress and strain conventions, time units, and any
empirical constants. Boundary conditions should name the physical scenario;
for example, fixed current and fixed voltage are different models.

Project-authored synthetic fixtures are useful for deterministic tests. Label
them as synthetic and cite related published applications without implying that
the fixture is redistributed experimental or design data.

## Geometry and topology

Generated or imported geometry needs checks beyond successful meshing:

- build the FE node table from referenced volume elements and reject orphans;
- check connectivity and signed Jacobians using the chosen ordering;
- verify dimensions, material volumes, and material adjacency;
- verify conformal interfaces or the declared nonconformal transfer;
- derive boundary sets from geometry entities or explicit tags, then check
  coverage and normals; and
- retain stable mappings from design objects to regions and outputs.

Use mixed fidelity when it matches the question: graph or 2-D representations
can remain appropriate globally while a shape-sensitive region is modeled in
3-D. Gmsh is an optional application dependency for generated Hex8 or Tet4
meshes. Mesh construction and topology checks remain in CoupFE-EDA.

For periodic cells, separate four questions: geometry pairing, affine relation
construction, serial mechanics, and distributed execution. Record the lattice,
face pairing tolerance, corner/edge equivalence policy, anchor policy, macro
gradient, and constraint residual. Algebraic removal of rigid modes is not a
physical far-field boundary condition.

## Physics, coupling, and derivatives

Connect models through the quantity the downstream model actually consumes.
Preserve IDs, units, frames, interpolation rules, and conservation across the
handoff. Test each component separately, then test the composed exchange.

Choose a tangent method that fits the implementation: analytic derivatives,
automatic differentiation, complex step, or carefully controlled finite
differences may all be appropriate. Complex step requires a complex-safe code
path and does not apply universally. Compare the selected tangent with an
independent directional derivative on representative states.

State convergence criteria for residuals, increments, and conserved quantities.
A linear or nonlinear solver reporting convergence is necessary numerical
information, but it does not establish correct geometry, physics, or observable
extraction.

Life and degradation models require particular care. Separate mesh-dependent
fields, recovered local quantities, calibrated life relations, and experimental
comparisons. Report whether a parameter set is in-sample, transferred, or
held-out.

## Solver and performance work

Use the supported CoupFE operator and compiled-element interfaces before adding
a parallel application driver. Validate the serial formulation first and then
compare solver or rank variants on the same case and observable.

Keep KSP, preconditioner, load-stepping, and field-splitting choices with the EDA
case unless they form a tested generic Core contract. Select them from the
matrix structure and available PETSc build rather than from a universal recipe.

Performance statements require a retained benchmark script, hardware and
software environment, problem size, rank/thread settings, warm-up policy,
timings, and accuracy comparison. Unretained timings may guide research but
should not appear as current release claims.

## Risk-proportional testing

Match checks to the change:

- documentation: links, commands, inventories, and claim/evidence consistency;
- adapters: schemas, units, transforms, round trips, invalid inputs, and IDs;
- geometry: connectivity, Jacobians, volumes, adjacency, interfaces, and BC sets;
- physics: analytic or manufactured checks, convergence, and sign/unit controls;
- coupling: component checks plus handoff identity and conservation;
- solver changes: residuals, observables, and reference-backend comparisons;
- distributed changes: serial-versus-rank comparisons on a bounded case; and
- releases: clean-source builds, installed-artifact smoke tests, and retained
  evidence.

A broken control is useful when it demonstrates that a gate detects the failure
mode under discussion. Prefer a targeted sign, topology, boundary, or unit
perturbation over an arbitrary scaling.

## Current test commands

Run from the repository root after `./setup.sh`:

```bash
# Standalone harness and fast physics wrappers
python -m eda_multiphysics.run
pytest eda_multiphysics
# Focused default-tier groups
pytest tests/test_integration_regressions.py
pytest tests/test_tsv_device.py
pytest tests/test_tsv_local_3d.py
pytest tests/test_periodic_adapter.py
# Complete default tier; toolchain tests are excluded by pyproject.toml
pytest
# Optional Gmsh/PETSc/gfortran toolchain tier
pytest -m toolchain
# Default and toolchain tests together
pytest -o addopts=''
```

Review skips and environment-dependent backends rather than treating a zero exit
code as proof that every optional path ran. For publication evidence, use the
clean-root recorder documented in `docs/RELEASE_EVIDENCE.md`; it records commands,
dependency identity, logs, artifacts, and checksums.
