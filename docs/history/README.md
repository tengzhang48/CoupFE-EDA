# Technical history

This directory preserves public technical work that shaped CoupFE-EDA. It is
included so release preparation does not erase the package's purpose, failed
experiments, corrected defects, prior API contracts, or useful rerun targets.

Every snapshot carries a banner identifying source commit `f961f5f` and its
evidence boundary. The files are historical records, not current instructions:
some names, test totals, inputs, and interpretations have since changed. The
root README, current guides, tests, and retained benchmark bundles define the
present release state. Referenced third-party data is not redistributed here.

## Project continuity

- [Project origins](PROJECT_ORIGINS.md) explains the original EDA → analysis →
  back-annotation → design-feedback loop and how the current package carries it.
- [API migrations](../API_MIGRATIONS.md) maps renamed or corrected pre-release
  entry points.
- [Current capabilities](../capabilities.md) is the present implementation and
  evidence inventory.

## Development plans and rationale

- [Open-source EDA–multiphysics integration plan](development/open_source_eda_multiphysics_integration_plan_snapshot.md)
- [EDA–multiphysics literature survey](development/open_source_eda_multiphysics_literature_survey_snapshot.md)
- [Electro-thermo-viscoplastic coupling plan](development/electro_thermo_viscoplastic_coupling_plan_snapshot.md)
- [Periodic boundary-condition plan](development/periodic_boundary_condition_plan_snapshot.md)
- [Anisotropic 3-D TSV plan](development/tsv_anisotropic_3d_plan_snapshot.md)
- [TSV device-validation release plan](development/tsv_device_validation_release_plan_snapshot.md)
- [Refactor contract](development/refactor_contract_snapshot.md)
- [External-collaboration brief](development/external_collaboration_brief_snapshot.md)
- [Detailed lessons learned](development/lessons_learned_snapshot.md)

## Audits and negative evidence

- [Code and examples review](audits/code_examples_review_snapshot.md)
- [Review evidence](audits/code_examples_review_evidence_snapshot.md)
- [TSV physics audit](audits/tsv_physics_audit_snapshot.md)
- [Validation assessment](audits/validation_assessment_snapshot.md)

## Development results

- [EDA–multiphysics results snapshot](results/eda_multiphysics_results_snapshot.md)
- [Recovered solver/scaling observations](../../benchmarks/solver_scaling/historical_unqualified.md)

Coordination records remain in the separate project-notes repository;
generated build products and third-party raw design data are not public history.
