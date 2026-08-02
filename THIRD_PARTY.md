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

The same versioned, file-based interface can consume caller-supplied
OpenROAD/OpenDB placement data and PDNSim SPICE/voltage exports. No ORFS GCD
input deck, Nangate45 platform/generated design file, or raw tool output is
bundled. Users remain responsible for the licenses and permissions governing
their input designs, platforms, PDKs, and generated artifacts.

As one external example, ORFS documents a small
[GCD flow-sanity design](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/c9c22caf9bf9cfe46c5a4236c6ec7e7ae9863cc3/flow/designs/src/gcd).
This citation identifies an applicable workflow; it does not incorporate or
relicense that design or its outputs.

## Published benchmark facts

Source code and manifests transcribe equations, coefficients, and small factual
values from papers cited inline. The repository does not include publisher page
images or digitized experimental curves. The curvature and Raman manifests
remain `definition_only`; no experimental-validation claim is made without the
missing curves and a retained comparison record.

## Web workbench dependencies

The `web/package-lock.json` file records the exact npm dependency resolution
used to test and build the workbench. Dependency source and `node_modules/` are
not vendored in this repository. Each npm package retains its own license; the
project's Apache-2.0 and CC-BY-4.0 licenses do not replace those terms.

The deployed static JavaScript incorporates React, React DOM, and Scheduler
from the [React project](https://github.com/facebook/react). Those components
are distributed under the MIT License with the following notice:

> Copyright (c) Meta Platforms, Inc. and affiliates.
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

Vite, TypeScript, Vitest, Testing Library, jsdom, and their transitive packages
are build or test dependencies identified by the same lockfile. The Pages
workflow installs the locked resolution with `npm ci`; it does not publish
`node_modules/`, test coverage, Vite caches, or an API service.
