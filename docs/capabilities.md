# Capability status

CoupFE-EDA is an experimental CoupFE-based implementation for EDA-linked
electrothermal and thermo-mechanical research. The current examples cover
PDN/electrothermal handoffs, TSV stress, solder/package global-local studies,
and design-object provenance. Evidence is limited to the tests, reference
cases, and model scopes documented below; this is not a signoff tool.

The tested Core revision is
`454f73ce2de284262b214a2b37bd676c6aca3c0a`. Geometry-specific matching and
periodic adapters remain in this repository; Core supplies mesh-agnostic finite
element and affine-constraint primitives.

## Capability and evidence boundary

| Area | Current implementation | Public evidence boundary |
|---|---|---|
| Scalar conduction | Quad4 diffusion for temperature, electric potential, and electrostatic potential; reaction-flux extraction | Patch, Ohm-law, manufactured-solution, and transient-eigenmode checks on structured meshes |
| Electrothermal coupling | Sequential and monolithic `phi`/`T` formulations with temperature-dependent conductivity and Joule heating | One-dimensional self-heating oracle, monolithic-versus-staggered comparison, power balance, and zero-power controls |
| PDN handoff | Resistor-network parser/solver, OpenROAD/OpenDB export adapter, and serial or PETSc solve paths | Independent SciPy comparison and a project-authored synthetic 3×3 fixture; no foundry design or PDK is bundled |
| EDA provenance | Versioned case metadata, stable joint IDs, coordinate/unit transforms, hashes, and explicit proxy labels | Schema and integration regressions; caller-supplied design data retains its own license and qualification burden |
| Analysis feedback | Thermal/back-annotation records and a synthetic weak-strap/reinforced-strap comparison at fixed current | Solver-side design perturbation and invariant only; no live database edit, DRC/timing rerun, or automated design optimization |
| Compiled weak-form elements | CoupFE-generated electrothermal and thermo-mechanical kernels consumed by serial, generated-mesh, and selected MPI paths | Analytic/reference and toolchain checks for the implemented elements; no general code-generation or performance guarantee |
| Thermomechanics | Two-dimensional bimetal/cylinder models and generated three-dimensional block/TSV models | Closed forms, patch/free-expansion/constrained-block checks, and selected generated-mesh comparisons |
| TSV local model | Generated blind Cu/oxide/anisotropic-Si Tet4 submodel, stress recovery, Raman sampling, mobility and KOZ proxy functions | Constitutive rotation, topology, interpolation, affine-field, hashing, and fail-closed metadata checks; experimental Raman/device comparison remains open |
| Periodic TSV cell | Gmsh-matched opposite faces and EDA-owned affine-relation construction consumed by Core constraints | Serial homogeneous and heterogeneous checked cases; source-equivalent boundary selection, mesh convergence, MPI consumption, and experiment remain open |
| Solder constitutive models | Anand material-point integrations, plane-strain SnPbAg and three-dimensional SAC305 operators, prescribed cycles, and small stateful block examples | Saturation, transient comparison, patch tests, fail-closed increment residuals, one accepted-state commit, zero-swing controls, an in-sample published calibration tie point, and four [guided result-bearing workflows](../EXAMPLES.md#guided-workflows-and-retained-example-results) |
| Solder/package geometry | Generated cylinder/profile/package regions with stable design-map handoff plus a regular 18-Hex8 stateful screening block | Geometry/topology and elastic generated-mesh regressions; stateful increments meet Core's residual rule, but load-step/mesh convergence, crack location, and predictive life are not established |
| Reliability mappings | Black/Blech screening, Syed/Darveaux mappings, and design-map propagation | Algebraic and handoff checks; life values remain calibration- and mission-profile-dependent |
| Distributed execution | PETSc paths for PDN and selected coupled examples; repeat-aware `etv_distributed_fs` measurement harness | Retained serial-versus-MPI output comparison at size 24 plus the bounded records in [`benchmarks/solver_scaling`](../benchmarks/solver_scaling/); every timing applies only to its named revision, problem, environment, hardware, and rank/thread configuration |
| Tet4 path | Native Core Tet4 consumed on generated boxes, cylinders, and local package/TSV regions | Patch and generated-geometry regression cases; imported production CAD and broad convergence studies remain open |

## Coupled workflows

The bundled synthetic case demonstrates this dataflow:

```text
placement/power metadata
        -> resistor-network voltage
        -> electrothermal temperature
        -> thermo-mechanical stress
        -> solder and electromigration screening quantities
```

Each handoff records units and provenance. The bundled case is project-authored
synthetic input; successful handoffs do not establish real-device prediction
accuracy.

The ETV work has three public levels:

- `etv_solder.py` exercises electrothermal and Anand coupling at a material or
  reduced-model level.
- `etv_fe.py` implements the spatial monolithic electrothermal element (the
  Stage-A `phi`/`T` system) and compares it with the sequential implementation.
- `etv_fe.thermoviscoplastic_cycle` combines a lumped backward-Euler
  temperature model with spatial SAC305 increments that meet Core's residual
  rule. It uses a unit Taylor–Quinney conversion of top-layer-average
  inelastic work to uniform lagged heat and is a
  partitioned sensitivity example, not a monolithic `phi-T-u` element.

The stateful spatial paths use a numerical material tangent and defer state
commit until Core's residual rule is met. The prescribed one-Hex8 cycle remains
a constitutive/operator-path check; `solder_joint_bvp_3d` separately exercises
multi-element equilibrium on an idealized regular block.

## Geometry and software handoffs

Current geometry support consists of generated reference meshes and explicit
adapters:

- structured Quad4 and Hex8 meshes for small reference problems;
- Gmsh-generated Hex8/Tet4 vias, layers, solder profiles, package regions, and
  blind-TSV cells;
- joint-map CSV/JSON inputs with stable object IDs, units, coordinate frames,
  and affine transforms;
- OpenROAD/OpenDB placement and PDN exports through a versioned, file-based
  boundary; and
- a local periodic surface matcher that emits generic affine relations for
  Core.

There is no general package-CAD importer or automatic mapping for arbitrary
mesh software. New mesh sources can connect by supplying coordinates,
connectivity, region labels, boundary sets, units, and stable source-object
identifiers in the documented contracts. See [Geometry](GEOMETRY.md).

## Evidence classes

The repository uses several kinds of checks. Their meanings are intentionally
different:

- an analytic oracle checks a specific equation and boundary condition;
- a patch or manufactured-solution test checks discretization behavior;
- an independent implementation comparison checks agreement at selected
  inputs;
- an invariant or broken control checks a sign, zero, balance, topology, or
  interface condition;
- a literature tie point checks reproduction within a stated scope and is not
  independent experimental validation; and
- a composed synthetic example checks interfaces and provenance, not every
  downstream physical prediction.

The commands and current checkpoint policy are in
[Validation guide](VALIDATION_GUIDE.md) and
[Release evidence](RELEASE_EVIDENCE.md).

## Not established by this release

This release does not establish:

- foundry/process qualification, process corners, or signoff accuracy;
- general electromagnetic, fluid, package-CAD, or optimization coverage;
- real-device TSV mobility, Raman, temperature, stress, or lifetime agreement;
- crack-location, mesh-converged dissipation, or predictive solder-life accuracy
  from the idealized stateful block;
- performance or memory scaling beyond the configurations with retained raw
  records in [`benchmarks/solver_scaling`](../benchmarks/solver_scaling/); or
- correctness for arbitrary imported CAD, mesh density, material set, or
  boundary condition.

The next evidence-producing tasks are tracked in [Roadmap](roadmap.md).
