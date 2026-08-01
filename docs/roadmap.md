# Roadmap

The next phase is evidence development, not broader positioning. Priorities are
ordered by the decisions they would enable.

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
