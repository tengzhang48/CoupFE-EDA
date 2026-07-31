# Third-party software, data, and provenance

This file records the explicitly redistributed OpenROAD binary and the boundary
between project-authored examples and caller-supplied EDA data. Other operating
system and environment packages in the container retain their own package
metadata and licenses. The project license does not replace an external
component's license.

## OpenROAD

The Python wheel and source distribution do not bundle the OpenROAD executable.
The container recipe downloads the pinned Precision Innovations OpenROAD binary
`2.0-17598-ga008522d8` dated 2024-12-14. OpenROAD is BSD-3-Clause; the retained
license is the exact notice from pinned revision
`a008522d88b669ac4c985609533cf5a3d2649222` and is stored at
`LICENSES/OpenROAD-BSD-3-Clause.txt`.

The project-authored `eda_multiphysics/openroad/export_case.tcl` adapter uses
OpenROAD/OpenDB's public database interface. OpenROAD's official
[OpenDB documentation](https://openroad.readthedocs.io/en/latest/main/src/odb/README.html)
describes the LEF/DEF/database object model, and its
[IR-drop documentation](https://openroad.readthedocs.io/en/latest/main/src/psm/README.html)
documents PDNSim and `write_pg_spice`.

## Bundled synthetic fixture

`eda_multiphysics/cases/synthetic_pdn/` is a deterministic,
project-authored 3×3 resistor-network fixture. It was not generated from an
external RTL design, PDK, standard-cell library, OpenROAD database, or PDNSim
run. Its generator, assumptions, closed-form voltage oracle, metadata, and
artifact hashes are distributed beside the data. It is Apache-2.0 project
material and is labeled as synthetic integration evidence, not real-design
validation.

## Caller-supplied designs and data

The same solver-neutral interface can consume caller-supplied OpenROAD/OpenDB
placement data and PDNSim SPICE/voltage exports. No ORFS GCD input deck,
Nangate45 platform/generated design file, or raw tool output is bundled. Dated
documents retain attributed numerical summaries as historical, non-release
evidence. Users remain responsible for the licenses and permissions governing
their input designs, platforms, PDKs, and generated artifacts.

As one external example, ORFS documents a small
[GCD flow-sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd).
This citation identifies an applicable workflow; it does not incorporate or
relicense that design or its outputs.

## Published benchmark facts

Source code and manifests transcribe equations, coefficients, and small factual
values from the papers cited inline. The repository does not include publisher
page images or digitized experimental curves. The curvature and Raman manifests
remain `definition_only`, and the missing curves remain release-blocking for
experimental-validation claims.
