# Historical snapshot: Open-source EDA–multiphysics integration plan

> Archived from the public source snapshot `f961f5f886b6722abdb0fd05c9e5912427bc3550`
> (2026-07-31), original path `docs/open_source_eda_multiphysics_integration_plan.md`. This preserves development plans,
> observations, negative findings, and terminology as they were recorded. It is
> not current usage guidance or release qualification: APIs, test totals, inputs,
> and numerical records may be superseded, and referenced third-party data is not
> redistributed here. Use the root README, current documentation, tests, and
> retained benchmark bundles for the present release state. Relative links below
> retain their original source context and may point to the historical layout.

---

# Open-Source EDA–Multiphysics Integration Demonstration Plan

## 1. Project objective

Demonstrate that a flexible multiphysics solver can be integrated with an open-source electronic-design-automation flow and used in a **closed engineering loop**:

> EDA design data → multiphysics model → coupled electrothermal results → EDA back-annotation → design modification → verified improvement

The first demonstration should focus on **steady-state electrothermal analysis of an integrated-circuit power-delivery network**, because it provides a clear connection between physical design, electrical resistance, Joule heating, temperature, voltage drop, and reliability.

A successful demonstration should prove that the integration can:

1. construct a simulation model automatically from EDA data;
2. preserve EDA object identities such as instances, nets, layers, vias, and power-grid segments;
3. perform bidirectional electrical–thermal coupling;
4. return results to the EDA environment in machine-readable and visual forms;
5. recommend or apply a design modification; and
6. quantify the improvement after rerunning the analysis.

---

## 2. Recommended demonstration scope

### Primary demonstration

Use an OpenROAD-based digital IC flow and connect it to the multiphysics solver.

Recommended cases:

| Case | Purpose | Example design |
|---|---|---|
| Small integration case | Fast debugging, unit tests, and CI | Project-authored synthetic PDN; caller-supplied GCD remains an optional external exercise |
| Flagship case | Realistic open-source demonstration | Ibex RISC-V core on SKY130HD |

### Secondary demonstration

After the IC integration is stable, create a KiCad PCB electrothermal case that can be experimentally validated with thermocouples or infrared imaging.

---

## 3. Demonstration architecture

```text
RTL and workload/activity data
             │
             ▼
Open-source EDA flow
Yosys / OpenROAD / OpenSTA / OpenRCX / PDNSim
             │
             ├── physical geometry and hierarchy
             ├── placed instances and macros
             ├── power-grid wires and vias
             ├── extracted resistance and capacitance
             ├── timing and activity information
             └── baseline voltage-drop results
             │
             ▼
EDA–multiphysics adapter
             │
             ├── geometry conversion
             ├── layer-stack construction
             ├── source and load mapping
             ├── stable object identifiers
             ├── material assignment
             └── boundary-condition generation
             │
             ▼
Multiphysics solver
Electrical conduction ↔ Joule heating ↔ thermal conduction
             │
             ▼
Result mapper and design-feedback layer
             │
             ├── temperature and voltage maps
             ├── updated conductor resistance
             ├── hotspot reports
             ├── KLayout/OpenROAD overlays
             └── EDA modification candidates
             │
             └──────────────► rerun EDA and verify improvement
```

---

## 4. Technical strategy

### 4.1 Use a mixed-dimensional model

Avoid creating a fully volumetric mesh of every routed wire during the first implementation. Use:

- a **1D graph model** for power-grid wires and vias;
- a **2D power-density map** for standard cells and macros; and
- a **3D thermal model** for silicon, package, heat spreader, and boundary conditions.

For each electrical edge \(e\):

\[
R_e(T_e)=R_{e,\mathrm{ref}}\left[1+\alpha_e(T_e-T_{\mathrm{ref}})\right]
\]

and the conductor heat source is:

\[
Q_e=I_e^2R_e(T_e)
\]

This approach preserves segment-level EDA identity while keeping the model computationally manageable.

### 4.2 Build the coupling progressively

Implement the physics in the following order:

1. fixed-power thermal analysis;
2. fixed-temperature power-grid electrical analysis;
3. one-way electrical-to-thermal coupling;
4. temperature-dependent metal resistance;
5. iterative closed-loop electrothermal coupling;
6. temperature-dependent cell leakage;
7. workload-dependent transient power;
8. temperature-aware timing and reliability.

Do not begin with full timing, leakage, and transient coupling. The first release should establish trustworthy data exchange, field mapping, and convergence.

---

## 5. Data-exchange contract

Introduce a solver-neutral, versioned case format rather than coupling the solver directly to every OpenROAD internal class.

Suggested directory structure:

```text
case/
├── manifest.yaml
├── stack.yaml
├── materials.yaml
├── boundary_conditions.yaml
├── geometry.h5
├── sources.h5
├── object_map.csv
└── results/
    ├── fields.xdmf
    ├── instance_results.csv
    ├── pdn_segment_results.csv
    ├── hotspot_regions.json
    └── convergence.json
```

Recommended formats:

- YAML for metadata, units, materials, and configuration;
- HDF5 for geometry, mesh, source arrays, and field data;
- CSV for human-readable EDA object mappings;
- XDMF or VTK for field visualization.

Every exported object should include at least:

```text
eda_id
object_type
hierarchical_name
net_name
layer_name
material_name
parent_object_id
x_min, y_min, x_max, y_max
z_min, z_max
source_power or source_current
```

The `eda_id` must remain stable through export, meshing, solving, result mapping, and design feedback.

---

## 6. Work packages and phases

## Phase 0 — Project setup and requirements

### Tasks

- Select the small and flagship reference designs.
- Freeze supported OpenROAD and PDK versions.
- Define coordinate systems, unit conventions, layer naming, and object identifiers.
- Define initial solver capabilities and API boundaries.
- Create a version-controlled repository and reproducible environment.
- Define baseline metrics and acceptance criteria.

### Deliverables

- architecture document;
- supported-tool matrix;
- case-format specification;
- risk register;
- reproducible container or environment file.

### Exit criteria

- reference EDA cases run successfully from clean environments;
- expected baseline outputs are archived;
- units and coordinate transformations are documented and tested.

---

## Phase 1 — Reproducible EDA baseline

### Tasks

Run the selected design through the open-source EDA flow and preserve:

- OpenDB database;
- LEF and DEF files;
- GDS or OASIS layout;
- SPEF parasitics;
- Liberty libraries;
- SDC constraints;
- VCD or SAIF activity data;
- OpenSTA reports;
- power estimates;
- PDNSim voltage-drop and current-density reports;
- exact tool and PDK revisions.

### Baseline metrics

| Category | Metrics |
|---|---|
| Physical design | area, utilization, wire length, DRC count |
| Timing | worst negative slack and total negative slack |
| Power | dynamic, internal, leakage, and total power |
| Power integrity | worst voltage drop and maximum current density |
| Runtime | wall time and peak memory |

### Deliverables

- immutable baseline case;
- one-command EDA reproduction script;
- baseline report and archived outputs.

### Exit criteria

- two consecutive runs produce equivalent reports within documented tolerances;
- all files required by the adapter are present and versioned.

---

## Phase 2 — OpenROAD geometry and data exporter

### Tasks

Create a Python-first exporter that reads OpenDB and associated analysis outputs.

Export:

- die and core boundaries;
- placed standard cells and macros;
- hierarchy and instance names;
- power and ground nets;
- PDN metal segments;
- PDN vias;
- power-source or bump locations;
- extracted segment resistance;
- instance-level power;
- layer thickness and elevation references;
- optional routing-density information.

### Required tests

- coordinate conversion;
- unit conversion;
- hierarchy preservation;
- object-count agreement;
- stable identifier generation;
- total-power conservation;
- net and layer mapping.

### Deliverables

- OpenROAD/OpenDB exporter;
- versioned exchange schema;
- schema validator;
- unit tests and reference export files.

### Exit criteria

- every exported EDA entity can be traced back to the source database;
- at least 99% of reported instance power is mapped to simulation sources;
- repeated exports produce stable identifiers.

---

## Phase 3 — One-way thermal model

### Tasks

- Construct the silicon and package geometry.
- Build the layer stack from `stack.yaml`.
- Assign thermal materials.
- Map instance power to surface or volumetric heat sources.
- Add package, heat-spreader, convection, and ambient boundary conditions.
- Generate or import the thermal mesh.
- Solve the steady-state heat equation.
- Map temperatures back to instances and PDN segments.

### Validation

- compare against simple analytical thermal-resistance cases;
- verify thermal energy balance;
- perform mesh-refinement studies;
- verify source conservation;
- test symmetric layouts for symmetric temperature fields.

### Deliverables

- thermal-model generator;
- solver input generator or API client;
- thermal result mapper;
- KLayout or OpenROAD temperature overlay;
- thermal validation report.

### Exit criteria

- energy imbalance below approximately 1%;
- peak-temperature change below approximately 2% after mesh refinement;
- every placed instance receives an average and maximum temperature.

---

## Phase 4 — Electrical model validation

### Tasks

- Import the PDN as a graph or embedded conductor network.
- Apply voltage sources and current or power loads.
- Solve the DC electrical-conduction problem at a fixed reference temperature.
- Calculate current, voltage drop, current density, and resistive loss.
- Compare results with PDNSim.

### Comparison metrics

- voltage at selected nodes;
- worst voltage drop;
- current through selected wires and vias;
- current-density hotspot locations;
- total resistive loss;
- voltage-drop spatial pattern.

### Deliverables

- electrical PDN model;
- PDNSim comparison utility;
- difference maps and validation report.

### Exit criteria

Suggested demonstration targets:

- major voltage-drop metrics within approximately 5% of PDNSim;
- matching hotspot regions;
- total resistive loss within a documented tolerance;
- all discrepancies explained by modeling assumptions.

---

## Phase 5 — Closed-loop electrothermal coupling

### Coupling sequence

```text
1. Read reference-temperature resistance.
2. Solve the electrical power-grid problem.
3. Calculate conductor Joule loss.
4. Combine conductor loss and instance power.
5. Solve the 3D thermal problem.
6. Map temperature to wires, vias, instances, and macros.
7. Update temperature-dependent resistance.
8. Optionally update leakage power.
9. Repeat until converged.
```

### Example algorithm

```python
temperature = initial_temperature_field()

for iteration in range(max_iterations):
    segment_resistance = resistance_model(temperature)
    cell_power = cell_power_model(temperature)

    voltage, current = solve_electrical(
        resistance=segment_resistance,
        sources=voltage_sources,
        loads=cell_power,
    )

    joule_heat = current**2 * segment_resistance

    new_temperature = solve_thermal(
        cell_heat=cell_power,
        conductor_heat=joule_heat,
        boundary_conditions=thermal_boundaries,
    )

    relaxed_temperature = (
        (1.0 - relaxation) * temperature
        + relaxation * new_temperature
    )

    if converged(temperature, relaxed_temperature, voltage):
        break

    temperature = relaxed_temperature
```

### Suggested convergence criteria

\[
\max |T^{k+1}-T^k| < 0.5\ \mathrm{K}
\]

and

\[
\frac{|V_{\mathrm{drop}}^{k+1}-V_{\mathrm{drop}}^k|}
{V_{\mathrm{drop}}^k} < 1\%
\]

Use under-relaxation when leakage or temperature-dependent resistance causes oscillation.

### Deliverables

- coupling controller;
- convergence monitor;
- restart and checkpoint capability;
- coupled electrothermal report;
- sensitivity study for relaxation and convergence tolerance.

### Exit criteria

- stable convergence for both reference cases;
- repeatable coupled results;
- documented difference between isothermal and coupled voltage-drop predictions.

---

## Phase 6 — Result visualization and EDA back-annotation

### Visual outputs

Create overlays for:

- instance temperature;
- PDN temperature;
- voltage drop;
- current density;
- Joule loss;
- thermal gradient;
- combined electrothermal risk.

A selected object should display its original EDA identity and simulation values, for example:

```text
Instance: core/alu/u_add_104
Average temperature: 347.2 K
Maximum temperature: 351.8 K
Power: 0.83 mW
Local supply voltage: 1.742 V
Nearest PDN segment: M4/VDD/segment_10342
```

### Machine-readable outputs

```text
instance_temperature.csv
pdn_segment_temperature.csv
resistance_scale.csv
voltage_map.csv
current_density.csv
hotspot_regions.json
convergence.json
```

### Deliverables

- KLayout or OpenROAD result viewer;
- result-query API;
- automated HTML or Markdown report generator;
- back-annotation files.

### Exit criteria

- any hotspot can be traced to its instance, net, layer, and PDN segment;
- visual and tabular results agree;
- output files are consumable by scripts without manual editing.

---

## Phase 7 — Closed-loop design modification

Limit the first optimization to one design-variable family so that improvement can be attributed clearly.

Recommended first choice: **PDN reinforcement**.

Candidate modifications:

- add or widen power straps;
- add PDN vias;
- alter power-source or bump locations;
- insert local decoupling capacitance where supported;
- create placement keep-out zones around hotspots;
- reduce local placement density;
- move a high-power macro;
- spread high-activity cells.

### Demonstration runs

| Run | Description |
|---|---|
| A | Isothermal EDA baseline |
| B | One-way thermal analysis |
| C | Fully coupled electrothermal analysis |
| D | Coupled analysis after automatic EDA modification |

### Compare

- maximum and average temperature;
- worst voltage drop;
- maximum current density;
- total resistive loss;
- total power;
- worst and total negative slack;
- area and wire length;
- DRC count;
- solver iterations, runtime, and memory.

### Deliverables

- rule-based design-modification generator;
- before-and-after layouts;
- comparative report;
- regression test proving that the modification is reproducible.

### Exit criteria

- at least one automatic modification is applied successfully;
- the modified design passes the selected EDA checks;
- at least one electrothermal metric improves without an unacceptable timing, area, or DRC regression.

---

## Phase 8 — Packaging, reproducibility, and release

Provide a single top-level command such as:

```bash
mpeda run cases/ibex_sky130hd/case.yaml
```

Internally, the command should execute:

```text
eda-build
eda-export
solver-prepare
solver-run
result-import
eda-modify
eda-evaluate
report-generate
```

Suggested repository layout:

```text
eda-multiphysics/
├── adapters/
│   ├── openroad/
│   ├── klayout/
│   └── kicad/
├── schema/
├── coupling/
├── solver_interface/
├── visualization/
├── optimization/
├── cases/
│   ├── synthetic_pdn/
│   └── ibex_sky130hd/
├── validation/
├── tests/
├── containers/
├── documentation/
└── reports/
```

### Deliverables

- public or internal repository;
- one-command reference cases;
- pinned environment or container;
- automated tests;
- tutorial documentation;
- demonstration video or scripted presentation;
- final benchmark report.

---

## 7. Proposed milestone schedule

The schedule below is expressed in project weeks and can be adjusted to team size.

| Milestone | Target | Main output |
|---|---:|---|
| M0: Requirements frozen | Week 1 | Architecture, schema draft, reference cases |
| M1: Reproducible EDA baseline | Week 2 | Archived OpenROAD cases and reports |
| M2: OpenDB exporter complete | Week 4 | Stable geometry, source, and object mapping |
| M3: One-way thermal analysis | Week 6 | Temperature field and EDA overlay |
| M4: Electrical model validated | Week 8 | Agreement with PDNSim |
| M5: Closed electrothermal loop | Week 10 | Converged temperature-dependent PDN analysis |
| M6: Back-annotation and reporting | Week 12 | Interactive overlays and machine-readable results |
| M7: Automatic design modification | Week 14 | Improved PDN or placement result |
| M8: Packaged demonstration | Week 16 | Reproducible release and flagship presentation |

A smaller team may treat the schedule as a sequence rather than a strict calendar commitment.

---

## 8. Acceptance criteria

| Area | Suggested acceptance criterion |
|---|---|
| Reproducibility | Reference cases run from a clean, version-locked environment |
| Data integrity | Every simulation object has a stable EDA identifier |
| Power mapping | At least 99% of reported power is mapped to the thermal model |
| Electrical validation | Major PDN metrics within approximately 5% of PDNSim |
| Thermal conservation | Energy imbalance below approximately 1% |
| Mesh sensitivity | Peak-temperature change below approximately 2% after refinement |
| Coupling | Stable convergence under documented tolerances |
| Traceability | Hotspots can be located by instance, net, layer, wire, and via |
| Design feedback | At least one automatically generated modification is implemented |
| EDA quality | No unresolved new DRC violations caused by the modification |
| Reporting | Before-and-after electrical, thermal, timing, and runtime metrics are generated automatically |

These values are demonstration targets, not universal signoff requirements.

---

## 9. Risk register and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Incomplete thermal properties in the PDK | Incorrect temperature prediction | Maintain a separate, documented material and package database; support parameter sweeps |
| Excessive geometric complexity | Large mesh and long runtime | Use mixed-dimensional and homogenized models; refine only hotspots |
| Loss of EDA identity during meshing | Results cannot be back-annotated | Use persistent `eda_id` values and mapping validation at every stage |
| Power-estimation uncertainty | Misleading hotspot magnitude | Report assumptions; support multiple activity and power scenarios |
| Difference from PDNSim | Reduced credibility | Separate topology, boundary-condition, and numerical differences; provide node-level comparisons |
| Coupling oscillation | Non-convergence | Add relaxation, damping, residual monitoring, and continuation in temperature coefficient |
| Tool-version drift | Broken reproducibility | Pin commits, PDK revisions, dependencies, and container images |
| Scope expansion into timing, mechanics, and CFD | Delayed initial demonstration | Freeze Version 1 to steady-state electrothermal PDN analysis |
| Confidential or production PDK restrictions | Limited open publication | Use Nangate45 and SKY130 for public cases; keep proprietary adapters separate |

---

## 10. Team roles

A compact implementation team could use the following responsibilities:

| Role | Main responsibility |
|---|---|
| EDA integration engineer | OpenROAD/OpenDB export, PDNSim comparison, design modification |
| Multiphysics engineer | electrical and thermal models, meshing, convergence, validation |
| Software engineer | exchange schema, APIs, orchestration, packaging, CI |
| Physical-design engineer | reference designs, timing/PDN interpretation, quality checks |
| Validation engineer | analytical tests, regression suite, uncertainty and sensitivity studies |

One person may cover multiple roles for a prototype.

---

## 11. Flagship demonstration narrative

The final presentation should tell a simple engineering story:

1. Run an open-source physical-design flow and show the baseline layout.
2. Run conventional isothermal power-integrity analysis.
3. Export the EDA database automatically to the multiphysics solver.
4. Show the 3D temperature field and electrical Joule-heating distribution.
5. Demonstrate that hotter conductors produce higher resistance and worse local voltage drop.
6. Identify the instances, wires, vias, and layers associated with the hotspot.
7. Generate and apply a PDN reinforcement or placement modification.
8. Rerun EDA and coupled simulation.
9. Compare temperature, voltage drop, current density, timing, DRC, and runtime before and after.
10. Reproduce the complete case with one command.

The key message should be:

> The solver is not merely viewing an EDA layout. It participates directly in the electronic-design loop and produces actionable, traceable design changes.

---

## 12. Follow-on roadmap

After the first release, extend the platform in this order:

1. workload-windowed transient electrothermal analysis;
2. temperature-dependent leakage and timing;
3. electromigration and thermomigration indicators;
4. chiplet, package, interposer, and TSV hierarchy;
5. thermomechanical stress and warpage;
6. KiCad PCB electrothermal analysis with experimental correlation;
7. enclosure airflow and conjugate heat transfer;
8. electromagnetic-loss-to-thermal coupling;
9. surrogate models and design-space optimization;
10. standardized interfaces to additional open-source EDA tools.

---

## 13. Immediate next actions

1. Use the project-authored synthetic PDN as the redistributable debug case and a
   caller-owned OpenROAD design as the external integration exercise.
2. Archive reproducible OpenROAD baseline outputs only when their input/output rights are recorded.
3. Define the first version of `manifest.yaml`, `object_map.csv`, and `stack.yaml`.
4. Implement the OpenDB exporter for instances, PDN wires, vias, and power.
5. Build and validate a one-way thermal model.
6. Reproduce PDNSim results with the solver's electrical model.
7. Add temperature-dependent resistance and the coupling controller.
8. Implement KLayout or OpenROAD overlays.
9. Add one rule-based PDN modification.
10. Package the complete flow behind a single command and generate a before-and-after report.
