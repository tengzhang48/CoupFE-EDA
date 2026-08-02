# Roadmap toward real-device use

The next phase is evidence development, not broader positioning. Priorities are
ordered by the decisions they would enable.

This is a forward technical-validation plan for the TSV-to-device path. It is
not a software-test summary, a release-readiness score, or a claim that the
current examples are ready for manufacturing decisions. The current code,
tests, examples, and retained scaling benchmark remain documented separately.

The machine-readable record is
[`benchmarks/tsv_release_scorecard.json`](../benchmarks/tsv_release_scorecard.json).
Its conservative internal status `blocked` means that a useful foundation is
present but the named qualification evidence is incomplete. `not_started`
means that the specific study has no retained record; it does not mean that
the package or its existing tests failed.

## Staged path

| Stage | Evidence goal |
|---|---|
| 1. Reference case | Freeze permitted geometry or layout, materials, loads, stable identifiers, measurements, uncertainty, and immutable manifests. |
| 2. Numerical qualification | Complete experiment-matched boundary conditions, convergence and element comparisons, MPI qualification, multilevel accuracy, conservation, and matched-fidelity studies. |
| 3. Experimental comparison | Compare global curvature and local Raman observables with declared alignment, uncertainty, tolerances, and held comparison data. |
| 4. Device mapping | Propagate an accepted 3-D field to device observables and reproduce the cited isolated-TSV and array cases. |
| 5. EDA design loop | Round-trip design identities and coordinates, back-annotate results, execute a legal design action, and report its penalties. |
| 6. Reproducible case release | Retain a locked environment, immutable inputs and results, release artifacts, checksums, and an external reproduction record. |

Completing these stages would establish a documented real-device research
case. Manufacturing signoff or production use would require
application-specific process data, acceptance criteria, and qualification
beyond this repository.

## Real-device reference case

Establish one permitted, versioned device/package case with:

- geometry and process dimensions with redistribution or access terms;
- material-property sources, temperature dependence, and uncertainty;
- stable placement, TSV, and joint identifiers across every handoff;
- measured electrical, thermal, stress/Raman, or reliability observables;
- a written train/calibration versus held-comparison split; and
- immutable input and result manifests.

The public synthetic fixture should remain as the installation and integration
example. A real-device case should be added or referenced separately so its
license, confidentiality, and evidence scope are unambiguous.

## TSV convergence and experiment

For the corrected Cu/oxide-cup/anisotropic-Si model:

1. freeze coordinate, material, and observation conventions;
2. define the macroscopic and bottom boundary conditions corresponding to the
   cited experimental setup;
3. run domain-size, local-mesh, and recovery/spot-size studies;
4. retain raw profiles, alignment choices, uncertainty, and manifests;
5. compare a calibration subset and a held Raman subset; and
6. propagate the checked stress field to stable-ID device observables and
   compare with transistor measurements.

Until these steps are complete, the local TSV path remains a numerical and
model-integration foundation.

## Stateful solder/package analysis

The public plane and regular-block examples now provide fail-closed increments,
one state commit per accepted increment, numerical material tangents, and
zero-swing controls. The next steps toward a package result are:

- load-step and mesh convergence studies;
- energy/work balance beyond the existing zero-swing controls;
- generated-profile and conformal-package material mapping; and
- a measured package case that is separate from calibration when possible.

The current prescribed one-Hex8 cycle, regular-block stateful examples, and
elastic generated-package path should remain clearly bounded while this work
continues.

## Mesh and design adapters

Add adapters when a concrete case requires them. Candidate work includes:

- STEP/BREP or external Tet4 import with named volume/surface mapping;
- package-tool joint exports mapped to the existing stable-ID schema;
- OpenROAD/OpenDB case export with explicit power provenance; and
- a common scene manifest after multiple adapters demonstrate the required
  units, transforms, region, boundary, and identity fields.

Connectivity conversion without boundary/material/provenance preservation is
not sufficient.

## Distributed and larger cases

After serial equations and evidence are stable:

- add a distributed periodic-TSV consumer;
- compare serial and MPI results at selected sizes;
- extend the retained `etv_distributed_fs` benchmark to additional machines,
  sizes, and rank-placement policies without combining unlike records;
- add memory and partition metrics when they can be captured reproducibly; and
- report scaling only for the retained measured configurations.

## Release and usability

- keep Core/EDA API ownership tests and exact dependency provenance;
- keep source, wheel, and sdist inventories fail-closed;
- maintain a small public example for each supported workflow;
- label unavailable optional dependencies and skipped toolchain cases;
- document schema migrations before changing public data contracts; and
- update claims only after a clean retained release checkpoint supports them.

If later releases accumulate real-device comparisons, cross-case uncertainty,
and external use, the project scope can be reassessed from that evidence.
