# Validation guide

This guide explains what the public checks exercise and how to interpret their
results. A successful test supports the named equation, implementation path,
inputs, mesh, and tolerance. It does not qualify a different device, process,
or signoff use.

## Evidence classes

| Class | Meaning | Examples |
|---|---|---|
| Analytic oracle | comparison with a closed solution for the same model and boundary conditions | Ohm law, slab self-heating, Lamé cylinder, free expansion |
| Manufactured/patch | discretization reproduces an affine or manufactured field and, where stated, its refinement trend | scalar patch, Quad4 convergence, Hex8/Tet4 affine fields |
| Independent implementation | two separately assembled or solved paths agree at selected inputs | PDN versus SciPy, monolithic versus sequential electrothermal |
| Balance/invariant | a conservation, topology, unit, hash, or identity property holds | electrical/thermal power balance, conformal interfaces, stable IDs |
| Broken control | a known wrong sign, source, parameter, or zero-input case is rejected | no-power, no-temperature-swing, wrong-source, wrong-parameter controls |
| Literature reproduction | code reproduces a cited equation, digitized curve, or calibration point within a stated tolerance | SAC305 saturation, in-sample PBGA life tie point |
| Synthetic integration | project-authored data traverses several interfaces with declared provenance | placement/PDN/temperature/stress/reliability pipeline |

Literature reproduction is not independent experiment. Synthetic integration
checks handoffs and regression behavior; it does not validate every downstream
prediction.

## Environment and Core identity

The qualified Core revision is
`454f73ce2de284262b214a2b37bd676c6aca3c0a`. Use `./setup.sh` to obtain and
verify that checkout. Before recording evidence, confirm that Python imports
`coupfe` from the intended checkout and record its Git revision. A successful
run against a different or dirty Core tree is not release evidence for this
candidate.

The optional toolchain also needs the dependencies used by the selected tests,
which may include Gmsh, a Fortran compiler, Meson/Ninja, PETSc, mpi4py, and an
MPI launcher. Solver features such as distributed direct factorization depend
on the PETSc build.

## Commands

```bash
# install this repository and the exact Core dependency
./setup.sh

# NumPy/SciPy/CoupFE gate harness
python -m eda_multiphysics.run

# default public tests; repository configuration excludes toolchain cases
python -m pytest -q

# optional generated-mesh/compiled/PETSc/MPI cases
python -m pytest -q -m toolchain
```

Run release commands from a clean candidate root. Save the command, exit code,
complete output, Python/platform information, package versions, EDA revision,
Core revision/import path, and artifact hashes. See
[Release evidence](RELEASE_EVIDENCE.md).

## Fast gate families

The `eda_multiphysics.gates` harness covers:

- scalar transport: patch, manufactured refinement, Ohm-law current, and
  one-way Joule heating;
- TSV/cylinder mechanics: Lamé-family stress and thermo-mechanical references;
- Anand models: saturation, selected SAC305 literature values, plane-strain
  return-map behavior, three-dimensional transient comparison, and elastic
  patch behavior;
- a prescribed one-Hex8 state-update cycle and its zero-swing control;
- PDN graph assembly versus an independent SciPy solve;
- bimetal, thermal-gradient cylinder, capacitance, transient, creep, runaway,
  Black, and Blech equations;
- material/reduced ETV self-heating, current-crowding context, staggered and
  coupled consistency checks; and
- the Stage-A monolithic Quad4 electrothermal element versus a slab oracle and
  sequential solve; and
- repaired plane, partitioned ETV, and 3D stateful demonstrations with
  fail-closed residual checks and no-swing controls.

The crowding check uses a simplified fixed mesh and a cited context range. It
does not reproduce an external device geometry. The life tie point reuses a
published calibration case and is labeled in-sample.

## Integration and provenance tests

The default pytest suite adds checks for:

- the project-authored synthetic PDN fixture, closed-form voltage identity,
  power balance, and claim labels;
- explicit joint-map precedence, unit normalization, affine transforms,
  duplicate-ID rejection, and labeled PDN proxy fallback;
- required CLI arguments and output metadata;
- anisotropic silicon stiffness rotation and device-proxy equations;
- local Tet4 affine strain, field sampling, recovery, and fail-closed geometry
  inputs;
- periodic face matching, edge/corner relations, lossy-index rejection, and
  the Core/EDA ownership boundary;
- one accepted-state commit for stateful increments that meet Core's residual
  rule and zero commits for a forced failure;
- Quad4 and Hex8 numerical-tangent agreement with a separate assembled-residual
  directional difference after a nonzero history preload; and
- identity preservation from one maximum-DNP joint-map object into the
  stateful 3D screening block, including the complete tie set and deterministic
  row-order selection rule.

Earlier versions of the plane, ETV, and 3D drivers did not meet this boundary.
Their old outputs are not release evidence. The repaired public examples use a
numerical material tangent, Core's existing residual rule, deferred commit,
and failure regressions.

## Optional toolchain families

When their dependencies are available, toolchain tests exercise selected:

- three-dimensional Hex8 electrothermal cylinder, annulus, and layer-stack
  models;
- three-dimensional thermo-mechanical free-expansion, constrained-block, and
  composite-TSV comparisons;
- serial-versus-MPI coupled solve results at checked sizes;
- solder-profile and conformal package geometry, region assembly, and
  stateless elastic strain extraction;
- explicit design-map propagation through generated regions; and
- native Core Tet4 patch and self-heating cases on generated meshes.

These are correctness/regression cases at stated sizes. They do not support a
general timing, memory, scaling, arbitrary-CAD, or package-life claim.

Performance measurements are a separate evidence type. The study definition,
complete sanitized process records, environment inventory, and summaries for the distributed
electrothermal solver are kept under
[`benchmarks/solver_scaling`](../benchmarks/solver_scaling/). A scaling table
supports only its recorded revision, matrix/problem size, solver options,
hardware, rank/thread placement, timed interval, and repeat policy; it does not
extend the correctness tests to unmeasured configurations.

## TSV local/device evidence

The TSV local tests separate four layers:

1. geometry: conformal Cu/oxide/Si regions, a complete oxide cup, and positive
   Tet4 volumes;
2. mechanics: cubic silicon rotation, thermal eigenstrain assembly, affine
   strain recovery, boundary labels, and mesh/material hashes;
3. observation: element/nodal/L2 field recovery and Raman line/spot sampling;
4. device transformation: piezoresistive mobility/KOZ equations with stable
   device IDs.

Passing these layers shows that the implemented transformations and contracts
behave at the tested inputs. It does not show corrected-scene mesh/domain
convergence, source-equivalent boundary selection, Raman agreement, transistor
agreement, array interaction, or signoff KOZ.

`tsv_validation` treats missing measured curves and missing required evidence
as open status. A `definition_only` manifest records equations and inputs; it
does not become experimental evidence because the schema is valid.

## Periodic MPC evidence

Periodic testing is split intentionally:

- Gmsh generates matching opposite-face meshes;
- `eda_multiphysics.periodic` independently checks the translated bijection and
  builds EDA-specific equivalence relations;
- Core compiles generic affine relations into the reduced system; and
- `tsv_local_3d` consumes the result for selected serial homogeneous and
  heterogeneous controls.

A fixed-box control is not a neutral substitute for thermal free expansion.
The macroscopic gradient must be explicit. MPI consumption, corrected-scene
convergence, and experimental comparison remain open; see
[Periodic MPC status](PERIODIC_MPC_STATUS.md).

## Reading a failure

When a check fails:

1. confirm the imported Core path and revision;
2. identify whether the failure is in the default or optional toolchain tier;
3. identify the evidence class and named tolerance;
4. inspect units, coordinate frame, boundary sets, region IDs, and fixture
   provenance before changing a numerical tolerance;
5. for stateful problems, inspect increment convergence and commit count; and
6. retain the failed output when it changes a public capability statement.

A tolerance should reflect a documented analytic, discretization, or
calibration error. It should not be loosened merely to turn a candidate green.

## Required release interpretation

A release checkpoint is acceptable for review when:

- the candidate and Core revisions are immutable and recorded;
- required commands return zero with complete retained output;
- default and toolchain scope are stated separately;
- source and built artifacts pass their inventory/provenance checks;
- failed, skipped, or unavailable paths are disclosed; and
- documentation claims match the retained evidence.

Model equations and literature sources are in [Theory](theory.md). Work still
needed for real-device evidence is in [Roadmap](roadmap.md).
