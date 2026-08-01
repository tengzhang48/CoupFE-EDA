# Project origins and technical continuity

This is a dated continuity record, not a second capability or status page.
Current behavior and evidence are defined by the top-level README,
[`docs/capabilities.md`](../capabilities.md), the tests, and retained benchmark
records.

## Initial purpose

CoupFE-EDA began as an EDA-aware integration layer built on CoupFE. Its central
engineering loop was:

```text
EDA design data
    → electrical/thermal/mechanical analysis
    → identity-preserving back-annotation
    → candidate design change
    → rerun and compare
```

The intended foundation included versioned file contracts, stable design-object
identity, unit and coordinate-frame handling, checked multiphysics handoffs,
generated and imported-mesh extension points, compiled weak-form elements, and
serial/distributed solver experiments. CoupFE was the selected FE backend for
this implementation; the interface ideas do not require other projects to use
the same backend.

That purpose remains in the current package. The public synthetic cases exercise
parts of the loop, including PDN/electrothermal handoffs, thermo-mechanical TSV
analysis, solder/package screening, back-annotation records, and a solver-side
fixed-current design perturbation. A live OpenROAD design modification and
DRC/timing rerun, a qualified imported package, and real-device validation have
not yet been completed.

## Historical technical records

The longer records from the first public source snapshot,
[`f961f5f886b6722abdb0fd05c9e5912427bc3550`](https://github.com/tengzhang48/CoupFE-EDA/tree/f961f5f886b6722abdb0fd05c9e5912427bc3550),
are restored locally in this [history index](README.md), including:

- `development/open_source_eda_multiphysics_integration_plan_snapshot.md` — the original
  integration and back-annotation plan;
- `development/open_source_eda_multiphysics_literature_survey_snapshot.md` — the initial
  literature and ecosystem survey;
- `development/electro_thermo_viscoplastic_coupling_plan_snapshot.md` — the staged ETV plan;
- `development/periodic_boundary_condition_plan_snapshot.md` and the current
  `../PERIODIC_MPC_STATUS.md` — periodic-cell design history;
- `development/tsv_anisotropic_3d_plan_snapshot.md` and
  `audits/tsv_physics_audit_snapshot.md` — local TSV
  mechanics and validation planning;
- `audits/validation_assessment_snapshot.md` and
  `results/eda_multiphysics_results_snapshot.md` — the
  development evidence inventory; and
- `../../benchmarks/solver_scaling/petsc_coo_gamg_reproducer.py` — the original
  PETSc assembly diagnostic, retained as runnable benchmark support.

Those files are not presented as current instructions because several contain
superseded API names, stale test totals, early GCD/AES assumptions, roadmap
targets, or performance observations without retained raw records. Their
technical content has not been treated as nonexistent:

- current interfaces and boundaries are consolidated in the API, geometry,
  capability, validation, and periodic-MPC guides;
- recovered performance tables are preserved under
  [`benchmarks/solver_scaling`](../../benchmarks/solver_scaling/);
- the PETSc diagnostic is restored beside those benchmark records; and
- public API changes are listed in [`docs/API_MIGRATIONS.md`](../API_MIGRATIONS.md).

Coordination and agent-review records are kept outside the public source
artifact in the project notes repository. This keeps the public tree focused
without destroying the work or confusing historical discussion with current
evidence.

## Release curation rule

An unlocated result is not a failed result. Before omitting a technical path,
search current files, Git refs, known worktrees, notes, and authorized storage;
then rerun the case when practical. Preserve incomplete observations as dated
historical records with explicit limits. Remove material from the public source
only for a concrete reason such as credentials/private paths, personal data,
unreviewed third-party redistribution, generated build products, or superseded
instructions that would mislead a user. Retain the original material in an
appropriate history or notes record.
