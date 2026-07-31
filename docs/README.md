# docs/ — index

Documentation for CoupFE-EDA, grouped by purpose. Start with the [top-level README](../README.md)
for what the project is and how to run it, and [`../EXAMPLES.md`](../EXAMPLES.md) for the runnable
demos. Per-entry-point provenance and claim status live in
[`../examples/REFERENCES.md`](../examples/REFERENCES.md).

## Release and licensing

| Doc | What's in it |
|---|---|
| [`LICENSE.md`](LICENSE.md) | Apache-2.0 code versus CC-BY-4.0 documentation scope. |
| [`RELEASE_EVIDENCE.md`](RELEASE_EVIDENCE.md) | Clean-root release run, immutable private logs, artifact checksums, and transient-build policy. |
| [`../THIRD_PARTY.md`](../THIRD_PARTY.md) | OpenROAD container notice, first-party synthetic-fixture provenance, and the caller-supplied data boundary. |

## Reference — how it works, how to use it
| Doc | What's in it |
|---|---|
| [`theory.md`](theory.md) | Governing equations, weak forms, and the analytic/published references, independent comparisons, invariants, and structural checks used as evidence. |
| [`api.md`](api.md) | The `eda_multiphysics` call surface: every public function/module, grouped by domain. |
| [`COMPONENTS.md`](COMPONENTS.md) | Authoritative 12-component / 44-module architecture inventory and count rules. |
| [`GEOMETRY.md`](GEOMETRY.md) | Mixed-dimensional geometry strategy; parametric solder barrel/hourglass API, validation, and remaining CAD/schema gaps. |
| [`capabilities.md`](capabilities.md) | Honest capability matrix plus the fixed-denominator gap-closure scorecard: what works, what these rounds advanced, and what remains open. |
| [`lessons_learned.md`](lessons_learned.md) | Hard-won pitfalls (units, BCs, solver traps) — read before extending. Pairs with [`../skills/SKILL.md`](../skills/SKILL.md). |

## Validation & assessment — the trust posture
| Doc | What's in it |
|---|---|
| [`VALIDATION_GUIDE.md`](VALIDATION_GUIDE.md) | Per-gate guide: the evidence or assertion each gate uses + how to run it (`validation_guide/` holds the figures + their generator). |
| [`VALIDATION_ASSESSMENT.md`](VALIDATION_ASSESSMENT.md) | Frank overall assessment — strengths, weaknesses (with what's since been closed), and next investments. |
| [`CODE_EXAMPLES_REVIEW.md`](CODE_EXAMPLES_REVIEW.md) | Code and runnable-example audit — resolved integration defects, reproduction data, and remaining research boundaries. |
| [`TET_FEASIBILITY.md`](TET_FEASIBILITY.md) | Tet4 consumer qualification and native-core dependency boundary. |
| [`REFACTOR_CONTRACT.md`](REFACTOR_CONTRACT.md) | The frozen public API and oracle numbers used to protect implementation changes. |
| [`../CoupFE_EDA_TSV_Device_Validation_Release_Plan.md`](../CoupFE_EDA_TSV_Device_Validation_Release_Plan.md) | Release-blocking TSV→device validation contract, current implementation amendment, and ten-category scorecard. |
| [`TSV_ANISOTROPIC_3D_PLAN.md`](TSV_ANISOTROPIC_3D_PLAN.md) | Executable next-stage plan for Cu/oxide/anisotropic-Si geometry, Raman-depth extraction, numerical qualification, and held validation. |
| [`TSV_PHYSICS_AUDIT.md`](TSV_PHYSICS_AUDIT.md) | Equation, geometry, boundary, measurement, and benchmark audit; bug/fix/prevention ledger, physics-first debugging order, accepted foundation, and ordered corrections. |
| [`PERIODIC_BOUNDARY_CONDITION_PLAN.md`](PERIODIC_BOUNDARY_CONDITION_PLAN.md) | Generic Core affine-constraint design, EDA-owned periodic adapter, TSV/Core ownership boundary, validation ladder, rollout, and failure controls. |
| [`PERIODIC_MPC_STATUS.md`](PERIODIC_MPC_STATUS.md) | Current periodic geometry, serial TSV mechanics, core MPI-reference evidence, unsupported modes, and next status-changing gates. |

## Plans & background — design decisions and prior art
| Doc | What's in it |
|---|---|
| [`electro_thermo_viscoplastic_coupling_plan.md`](electro_thermo_viscoplastic_coupling_plan.md) | The ETV study plan + the τ/period coupling finding. |
| [`open_source_eda_multiphysics_integration_plan.md`](open_source_eda_multiphysics_integration_plan.md) | The original phase-by-phase integration plan (EDA → multiphysics). |
| [`open_source_eda_multiphysics_literature_survey.md`](open_source_eda_multiphysics_literature_survey.md) | Prior-art survey (commercial + open) with confidence tags. |

Distributed/MPI specifics live next to the code in [`../eda_multiphysics/DISTRIBUTED.md`](../eda_multiphysics/DISTRIBUTED.md)
(the **canonical** scaling home) and [`../eda_multiphysics/RESULTS.md`](../eda_multiphysics/RESULTS.md).
