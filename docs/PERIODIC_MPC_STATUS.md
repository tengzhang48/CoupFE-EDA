# Periodic TSV and affine-constraint status

The current dependency target is public Core revision
`e2f42ed5772850a0a23a2ce434f430c287eae5c8`. CoupFE-EDA owns periodic geometry,
surface-node matching, edge/corner equivalence construction, macroscopic
gradient semantics, and TSV-specific checks. Core owns mesh-agnostic affine
relations and reduced residual/tangent algebra.

## Current status

| Item | Status | Evidence boundary |
|---|---|---|
| Rectangular TSV cell geometry | Implemented | generated Cu/oxide-cup/Si cell with declared axes, dimensions, regions, and no direct Cu/Si contact |
| Opposite-face matching | Implemented | Gmsh correspondence plus EDA strict translated-node bijection and pair metadata |
| Affine relation construction | Implemented | face/edge/corner equivalence classes, explicit offsets, representative anchor, and fail-closed inconsistency checks |
| Core reduction | Consumed from pinned Core | `U=Pq+U0`, `P.T R`, and `P.T K P` through generic constraint primitives |
| Serial local-TSV consumer | Implemented at selected cases | homogeneous free-expansion and fixed-box controls plus a heterogeneous equilibrium case |
| Distributed local-TSV consumer | Open | no current public MPI periodic-TSV consumer checkpoint |
| Source-equivalent model selection | Open | macroscopic and bottom-boundary semantics have not been selected by comparison with the cited experimental setup |
| Mesh/domain/recovery convergence | Open | corrected oxide-cup periodic scene needs a retained convergence study |
| Raman/device comparison | Open | measured curves, uncertainty contract, and transistor comparison are absent |

The current serial acceptance is defined by the periodic-adapter and
local-TSV tests. Release evidence must record their actual result against the
pinned Core revision; this status page does not replace a test log.

## Mechanics contract

For matched points separated by lattice vector `a`, the adapter creates

```text
u_plus - u_minus = Hbar a.
```

`Hbar` is required. Setting it silently to zero would impose a fixed periodic
box, which is not equivalent to free thermal expansion. The adapter merges
face, edge, and corner constraints into consistent equivalence classes before
calling Core. A representative node is anchored to remove rigid translation.

Opposite-face traction anti-periodicity follows from reduced weak equilibrium
for the accepted displacement. It is evaluated as a diagnostic and is not
added as a second displacement constraint.

## Status labels

Geometry and mechanics use separate labels:

- `periodic_pairing_status="matching_nodes_verified"` means the generated face
  meshes met the translated-node correspondence criterion for that result.
- `periodic_mechanics_status="not_solved"` means no mechanics result has been
  attached yet.
- a mechanics result must additionally record the macro gradient, boundary
  label, Core identity, reduced residual, constraint error, and input hashes.

An isolated-cylinder result cannot be relabeled as a periodic-cell result.

## Use sequence

1. Generate `tsv_periodic_cell(...)` and check region/topology metadata.
2. Require the recorded matching status and inspect maximum pair mismatch.
3. Supply a declared `macro_gradient` to
   `solve_local_tsv(..., boundary_condition="periodic_macro_gradient")`.
4. Record the Core revision/import path and EDA revision.
5. Check reduced residual, affine-constraint error, stress recovery choice, and
   mesh/material hashes.
6. Keep the result at numerical/model-check scope until convergence and
   experimental comparisons are complete.

## Next evidence-producing work

- Define the macroscopic and bottom boundary conditions corresponding to the
  cited Jiang setup and retain the mapping rationale.
- Repeat domain, local mesh, and recovery studies on the corrected oxide-cup
  periodic scene.
- Add an MPI consumer only after the serial contract and acceptance values are
  frozen.
- Compare Raman line/spot observables with permitted measured data and record
  uncertainty and alignment choices.
- Propagate a checked field to ID-preserving device observables and compare with
  real device measurements before making a device-prediction claim.

See [Theory](theory.md), [Geometry](GEOMETRY.md), and
[Roadmap](roadmap.md).
