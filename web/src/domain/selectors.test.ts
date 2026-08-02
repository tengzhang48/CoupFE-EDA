import { describe, expect, it } from "vitest";

import { createTsvWorkflowOutput, demoSnapshot } from "../demo/snapshot";
import {
  formatDateTime,
  formatDuration,
  relativeDiscrepancyPercent,
  selectActiveDesign,
  selectCandidateComparison,
  selectEvidenceIntegrity,
  selectEvidenceSummary,
  selectGateEvaluations,
  selectLastCompletedRun,
  selectLatestRun,
  selectLatestSuccessfulRun,
  selectMetric,
  selectModelAdequacy,
  selectPreferredCandidate,
  selectStackThicknessMicrometers,
  selectTemperatureField,
  selectWorkflow,
} from "./selectors";
import type {
  MetricKey,
  MetricResult,
  ModelFidelity,
  ProjectSnapshot,
  RunOutput,
  RunRecord,
} from "./types";

function completedTsvRun(): RunRecord {
  return {
    id: "run-retained-tsv-interface",
    projectId: demoSnapshot.project.id,
    designId: demoSnapshot.project.activeDesignId,
    workflowId: "tsv_device_screening",
    clientRequestId: "selector-contract-test",
    sequence: 1,
    status: "succeeded",
    requestedAt: "2026-08-01T19:00:00.000Z",
    startedAt: "2026-08-01T19:00:00.000Z",
    completedAt: "2026-08-01T19:00:01.000Z",
    input: {
      designRevision: "Synthetic TSV device-screening inputs",
      packageRevision: "examples/tsv_00_device_screening",
      codeRevision: "not-applicable:static-interface-demo",
      solverVersion: "Not executed (interface simulation)",
      workflowId: "tsv_device_screening",
      executorKey: "tsv.device-screening.v1",
      manifestSha256: "not-applicable:interface-demo",
    },
    output: createTsvWorkflowOutput("run-retained-tsv-interface", 1),
  };
}

function snapshotWithRun(): ProjectSnapshot {
  const snapshot = structuredClone(demoSnapshot);
  snapshot.sequence = 1;
  snapshot.runs = [completedTsvRun()];
  return snapshot;
}

// This fixture exists only to exercise the retained model-policy selectors. It
// is deliberately local to this test module and must not seed either public
// browser mode or the connected-project contract.
const TEST_PROJECT_ID = "test-only-policy-project";
const TEST_DESIGN_ID = "test-only-active-design";
const TEST_DECISION_ID = "test-only-decision";
const TEST_EVIDENCE = {
  temperature: "test-only-temperature-validation",
  warpage: "test-only-warpage-validation",
  marginInput: "test-only-margin-input",
  marginValidation: "test-only-margin-validation",
} as const;

function policyMetric(
  key: MetricKey,
  label: string,
  value: number,
  unit: MetricResult["quantity"]["unit"],
  assessment: MetricResult["assessment"],
  evidenceIds: string[],
  uncertainty?: MetricResult["uncertainty"],
): MetricResult {
  return {
    key,
    label,
    quantity: { value, unit },
    assessment,
    evidenceIds,
    uncertainty,
  };
}

function validationError(relativePercent: number, evidenceId: string): NonNullable<MetricResult["uncertainty"]> {
  return {
    kind: "validation-error",
    statistic: "maximum-relative-error",
    relativePercent,
    sampleCount: 6,
    method: "Test-only comparison against the reference fixture",
    domain: "Test-only bounded package family",
    evidenceIds: [evidenceId],
  };
}

function conservativeLowerBound(relativePercent: number): NonNullable<MetricResult["uncertainty"]> {
  return {
    kind: "conservative-bound",
    direction: "lower",
    relativePercent,
    method: "Test-only conservative reduced/reference guard band",
    domain: "Test-only bounded package family",
    evidenceIds: [TEST_EVIDENCE.marginValidation],
  };
}

function policyOutput(modelId: ModelFidelity, runId: string): RunOutput {
  const values = {
    compact: {
      temperature: 82.8,
      warpage: 36,
      margin: 1.54,
      errors: { temperature: 9.2, warpage: 12.4, margin: 11 },
    },
    reduced: {
      temperature: 86.4,
      warpage: 42,
      margin: 1.38,
      errors: { temperature: 2.8, warpage: 4.8, margin: 5 },
    },
    full: {
      temperature: 87.2,
      warpage: 44,
      margin: 1.31,
      errors: { temperature: 0.9, warpage: 1.6, margin: 2 },
    },
  }[modelId];
  const manifestEvidenceId = `test-only-${runId}-manifest`;
  const marginUncertainty = modelId === "compact"
    ? validationError(values.errors.margin, TEST_EVIDENCE.marginValidation)
    : conservativeLowerBound(values.errors.margin);

  return {
    metrics: [
      policyMetric(
        "temperature",
        "Peak temperature",
        values.temperature,
        "°C",
        "watch",
        [TEST_EVIDENCE.temperature],
        validationError(values.errors.temperature, TEST_EVIDENCE.temperature),
      ),
      policyMetric(
        "warpage",
        "Warpage",
        values.warpage,
        "µm",
        "nominal",
        [TEST_EVIDENCE.warpage],
        validationError(values.errors.warpage, TEST_EVIDENCE.warpage),
      ),
      policyMetric(
        "margin",
        "Failure margin",
        values.margin,
        "1",
        "pass",
        [TEST_EVIDENCE.marginInput],
        marginUncertainty,
      ),
      policyMetric("runtime", "Runtime", modelId === "compact" ? 12 : modelId === "reduced" ? 198 : 2872, "s", "nominal", [manifestEvidenceId]),
    ],
    fields: [
      {
        key: "temperature-field",
        label: "Temperature",
        unit: "°C",
        minimum: 24,
        maximum: values.temperature,
        hotspotValue: values.temperature,
        hotspotComponentId: "test-only-die",
        sharedScale: false,
        artifactId: `test-only-field-${runId}`,
        evidenceIds: [TEST_EVIDENCE.temperature],
      },
    ],
    artifactIds: [`test-only-field-${runId}`, `test-only-manifest-${runId}`],
    evidenceIds: [
      TEST_EVIDENCE.temperature,
      TEST_EVIDENCE.warpage,
      TEST_EVIDENCE.marginInput,
      TEST_EVIDENCE.marginValidation,
      manifestEvidenceId,
    ],
    conclusion: "Test-only selector output.",
    nextAction: "Continue the test-only policy evaluation.",
  };
}

function policyInput(runId: string) {
  return {
    designRevision: TEST_DESIGN_ID,
    packageRevision: "test-only-package",
    codeRevision: "test-only-code",
    solverVersion: "test-only-solver",
    manifestSha256: `test-only-sha-${runId}`,
  };
}

function policyRun(
  id: string,
  modelId: ModelFidelity,
  requestedAt: string,
  sequence: number,
  designId = TEST_DESIGN_ID,
): RunRecord {
  return {
    id,
    projectId: TEST_PROJECT_ID,
    designId,
    modelId,
    clientRequestId: `test-only-request-${id}`,
    sequence,
    status: "succeeded",
    requestedAt,
    startedAt: requestedAt,
    completedAt: requestedAt,
    input: policyInput(id),
    output: policyOutput(modelId, id),
  };
}

function policySnapshot(): ProjectSnapshot {
  const runs = [
    policyRun("test-run-reduced", "reduced", "2026-08-01T18:24:18.000Z", 104),
    policyRun("test-run-compact", "compact", "2026-08-01T17:58:12.000Z", 103),
    policyRun("test-run-full", "full", "2026-08-01T17:35:52.000Z", 102),
    policyRun("test-run-old-design", "reduced", "2026-07-31T19:57:11.000Z", 97, "test-only-old-design"),
  ];
  const runIds = runs.map((run) => run.id);
  const evidence: ProjectSnapshot["evidence"] = [
    {
      id: TEST_EVIDENCE.temperature,
      title: "Test-only thermal validation",
      category: "verification",
      authority: "validation",
      status: "verified",
      description: "Test-only evidence for selector regression coverage.",
      source: "test-only/temperature.json",
      updatedAt: "2026-08-01T12:00:00.000Z",
      artifactIds: ["test-only-report-temperature"],
    },
    {
      id: TEST_EVIDENCE.warpage,
      title: "Test-only warpage validation",
      category: "verification",
      authority: "validation",
      status: "verified",
      description: "Test-only evidence for selector regression coverage.",
      source: "test-only/warpage.json",
      updatedAt: "2026-08-01T12:00:00.000Z",
      artifactIds: ["test-only-report-warpage"],
    },
    {
      id: TEST_EVIDENCE.marginInput,
      title: "Test-only failure criterion",
      category: "input",
      authority: "input-provenance",
      status: "review",
      description: "Test-only policy input.",
      source: "test-only/margin-input.json",
      updatedAt: "2026-08-01T12:00:00.000Z",
      artifactIds: ["test-only-report-margin-input"],
    },
    {
      id: TEST_EVIDENCE.marginValidation,
      title: "Test-only margin validation",
      category: "verification",
      authority: "validation",
      status: "verified",
      description: "Test-only evidence for selector regression coverage.",
      source: "test-only/margin-validation.json",
      updatedAt: "2026-08-01T12:00:00.000Z",
      artifactIds: ["test-only-report-margin-validation"],
    },
    ...runIds.map((runId) => ({
      id: `test-only-${runId}-manifest`,
      runId,
      title: `${runId} test-only manifest`,
      category: "provenance" as const,
      authority: "input-provenance" as const,
      status: "generated" as const,
      description: "Test-only run provenance.",
      source: `test-only/${runId}/manifest.json`,
      updatedAt: "2026-08-01T18:30:00.000Z",
      artifactIds: [`test-only-manifest-${runId}`],
    })),
  ];
  const artifacts: ProjectSnapshot["artifacts"] = [
    "temperature",
    "warpage",
    "margin-input",
    "margin-validation",
  ].map((name) => ({
    id: `test-only-report-${name}`,
    kind: "report" as const,
    uri: `test-only/${name}.json`,
    sha256: `test-only-sha-${name}`,
  }));
  artifacts.push(
    ...runIds.flatMap((runId) => [
      {
        id: `test-only-field-${runId}`,
        runId,
        kind: "field" as const,
        uri: `test-only/${runId}/temperature.vtu`,
        sha256: `test-only-sha-field-${runId}`,
      },
      {
        id: `test-only-manifest-${runId}`,
        runId,
        kind: "manifest" as const,
        uri: `test-only/${runId}/manifest.json`,
        sha256: `test-only-sha-manifest-${runId}`,
      },
    ]),
  );

  return {
    schemaVersion: 1,
    sequence: 104,
    mode: "demo",
    project: {
      id: TEST_PROJECT_ID,
      name: "Test-only selector policy fixture",
      studyType: "Test-only model decision",
      activeDesignId: TEST_DESIGN_ID,
      activeDecisionId: TEST_DECISION_ID,
    },
    designs: [
      {
        id: TEST_DESIGN_ID,
        label: "Test-only active design",
        packageRevision: "test-only-package",
        createdAt: "2026-08-01T16:00:00.000Z",
        parameters: {
          tsv_pitch: { value: 60, unit: "µm" },
          die_thickness: { value: 180, unit: "µm" },
        },
      },
    ],
    models: [
      {
        id: "compact",
        version: "test-only-1",
        name: "Test-only compact model",
        shortName: "Compact",
        description: "Test-only screening model.",
        validityClass: "screening",
        costClass: "very-low",
        expectedRuntimeSeconds: 12,
        executorKey: "test-only.compact",
        assumptions: [],
        validityRanges: [],
      },
      {
        id: "reduced",
        version: "test-only-1",
        name: "Test-only reduced model",
        shortName: "Reduced",
        description: "Test-only calibrated model.",
        validityClass: "calibrated",
        costClass: "moderate",
        expectedRuntimeSeconds: 198,
        executorKey: "test-only.reduced",
        assumptions: [],
        validityRanges: [
          {
            parameterKey: "tsv_pitch",
            label: "TSV pitch",
            minimum: { value: 40, unit: "µm" },
            maximum: { value: 80, unit: "µm" },
          },
        ],
      },
      {
        id: "full",
        version: "test-only-1",
        name: "Test-only reference model",
        shortName: "Full",
        description: "Test-only reference model.",
        validityClass: "reference",
        costClass: "high",
        expectedRuntimeSeconds: 2872,
        executorKey: "test-only.full",
        assumptions: [],
        validityRanges: [],
      },
    ],
    approvedWorkflows: [],
    decisions: [
      {
        id: TEST_DECISION_ID,
        designId: TEST_DESIGN_ID,
        selectedModelId: "reduced",
        status: "proposed",
        createdAt: "2026-08-01T18:25:00.000Z",
        createdBy: "policy",
        policyVersion: "test-only-policy-v1",
        policy: {
          maximumModelErrorPercent: 5,
          minimumFailureMargin: 1.15,
          maximumTemperatureDifference: { value: 2, unit: "°C" },
          maximumMarginRelativeDifferencePercent: 7,
        },
        sourceRunIds: ["test-run-compact", "test-run-reduced", "test-run-full"],
      },
    ],
    runs,
    evidence,
    artifacts,
    layers: [
      { id: "test-only-die", name: "Die", material: "test", thickness: { value: 180, unit: "µm" }, role: "test" },
      { id: "test-only-bumps", name: "Bumps", material: "test", thickness: { value: 28, unit: "µm" }, role: "test" },
      {
        id: "test-only-interposer",
        name: "Interposer",
        material: "test",
        thickness: { value: 100, unit: "µm" },
        role: "test",
        embeddedFeatures: [{ id: "test-only-tsv", name: "TSV", material: "test", role: "test" }],
      },
      { id: "test-only-substrate", name: "Substrate", material: "test", thickness: { value: 420, unit: "µm" }, role: "test" },
      { id: "test-only-spreader", name: "Spreader", material: "test", thickness: { value: 520, unit: "µm" }, role: "test" },
      { id: "test-only-sink", name: "Sink", material: "test", thickness: { value: 1.8, unit: "mm" }, role: "test" },
    ],
    candidates: [
      {
        id: "A",
        name: "Test candidate A",
        designId: "test-only-candidate-a",
        revision: "test-only-a",
        metrics: {
          peakTemperature: { value: 91.8, unit: "°C" },
          warpage: { value: 47, unit: "µm" },
          failureMargin: { value: 1.12, unit: "1" },
          runtime: { value: 201, unit: "s" },
        },
      },
      {
        id: "B",
        name: "Test candidate B",
        designId: "test-only-candidate-b",
        revision: "test-only-b",
        metrics: {
          peakTemperature: { value: 87.9, unit: "°C" },
          warpage: { value: 45, unit: "µm" },
          failureMargin: { value: 1.27, unit: "1" },
          runtime: { value: 192, unit: "s" },
        },
      },
      {
        id: "C",
        name: "Test candidate C",
        designId: TEST_DESIGN_ID,
        revision: "test-only-c",
        metrics: {
          peakTemperature: { value: 86.4, unit: "°C" },
          warpage: { value: 42, unit: "µm" },
          failureMargin: { value: 1.38, unit: "1" },
          runtime: { value: 198, unit: "s" },
        },
      },
    ],
  };
}

function requirePolicyRun(snapshot: ProjectSnapshot, runId: string): RunRecord {
  const run = snapshot.runs.find((candidate) => candidate.id === runId);
  if (!run) throw new Error(`Test-only fixture is missing ${runId}`);
  return run;
}

function setPolicyMetric(
  snapshot: ProjectSnapshot,
  runId: string,
  metricKey: MetricKey,
  value: number,
): void {
  const metric = requirePolicyRun(snapshot, runId).output?.metrics?.find(
    (candidate) => candidate.key === metricKey,
  );
  if (!metric) throw new Error(`Test-only fixture is missing ${metricKey} on ${runId}`);
  metric.quantity.value = value;
}

function policyGate(snapshot: ProjectSnapshot, modelId: ModelFidelity, gateId: string) {
  const result = selectGateEvaluations(snapshot, modelId).find((candidate) => candidate.id === gateId);
  if (!result) throw new Error(`Test-only gate ${gateId} was not evaluated`);
  return result;
}

describe("repository-backed snapshot selectors", () => {
  it("selects the active synthetic design without inventing model records", () => {
    expect(selectActiveDesign(demoSnapshot)?.id).toBe("tsv-synthetic-device-sites-v1");
    expect(selectLatestRun(demoSnapshot)).toBeUndefined();
    expect(selectLatestSuccessfulRun(demoSnapshot, "reduced")).toBeUndefined();
    expect(selectLastCompletedRun(demoSnapshot)).toBeUndefined();

    const withRun = snapshotWithRun();
    expect(selectLatestRun(withRun)?.id).toBe("run-retained-tsv-interface");
    expect(selectLastCompletedRun(withRun)?.id).toBe("run-retained-tsv-interface");
    expect(selectLatestSuccessfulRun(withRun, "reduced")).toBeUndefined();
  });

  it("reports absent evidence and model-policy inputs explicitly", () => {
    expect(selectEvidenceSummary(demoSnapshot)).toEqual({
      verified: 0,
      review: 0,
      generated: 0,
    });
    expect(selectEvidenceIntegrity(demoSnapshot, [])).toEqual({
      valid: true,
      missingIds: [],
    });
    expect(selectEvidenceIntegrity(demoSnapshot, ["missing-record"])).toEqual({
      valid: false,
      missingIds: ["missing-record"],
    });
    expect(selectGateEvaluations(demoSnapshot, "reduced")).toEqual([
      expect.objectContaining({ id: "decision", status: "not-evaluable" }),
    ]);
    expect(selectModelAdequacy(demoSnapshot, "reduced").status).toBe("review");
  });

  it("derives the empty model workflow, candidates, and stack honestly", () => {
    const workflow = selectWorkflow(demoSnapshot, "reduced");
    expect(workflow.readyCount).toBe(1);
    expect(workflow.stages.map(({ id, state }) => ({ id, state }))).toEqual([
      { id: "layout", state: "complete" },
      { id: "thermal", state: "pending" },
      { id: "mechanical", state: "pending" },
      { id: "reliability", state: "pending" },
    ]);
    expect(selectCandidateComparison(demoSnapshot)).toEqual([]);
    expect(selectPreferredCandidate(demoSnapshot)).toBeUndefined();
    expect(selectStackThicknessMicrometers(demoSnapshot)).toBe(0);
  });
});

describe("test-only model-policy selector regression", () => {
  it("selects only the active design and requested model fidelity", () => {
    const snapshot = policySnapshot();
    expect(selectLatestRun(snapshot)?.id).toBe("test-run-reduced");
    expect(selectLatestRun(snapshot, "compact")?.id).toBe("test-run-compact");
    expect(selectLatestSuccessfulRun(snapshot, "reduced")?.id).toBe("test-run-reduced");
    expect(selectLastCompletedRun(snapshot)?.id).toBe("test-run-reduced");
    expect(selectLatestSuccessfulRun(snapshot, "reduced")?.designId).toBe(TEST_DESIGN_ID);
  });

  it("retains the latest successful output while a newer attempt is active", () => {
    const snapshot = policySnapshot();
    snapshot.runs.unshift({
      ...structuredClone(requirePolicyRun(snapshot, "test-run-reduced")),
      id: "test-run-active",
      clientRequestId: "test-only-active-request",
      sequence: 105,
      status: "running",
      requestedAt: "2026-08-01T19:00:00.000Z",
      completedAt: undefined,
      output: undefined,
      progress: {
        phase: "solving",
        fraction: 0.5,
        message: "Test-only active solve",
      },
    });

    expect(selectLatestRun(snapshot, "reduced")?.id).toBe("test-run-active");
    expect(selectLatestSuccessfulRun(snapshot, "reduced")?.id).toBe("test-run-reduced");
  });

  it("uses the selected model run as the single source for metrics and fields", () => {
    const snapshot = policySnapshot();
    const compact = selectLatestSuccessfulRun(snapshot, "compact");
    const reduced = selectLatestSuccessfulRun(snapshot, "reduced");
    const full = selectLatestSuccessfulRun(snapshot, "full");

    expect(selectMetric(compact, "temperature")?.quantity.value).toBe(82.8);
    expect(selectTemperatureField(compact)?.hotspotValue).toBe(82.8);
    expect(selectMetric(reduced, "temperature")?.quantity.value).toBe(86.4);
    expect(selectTemperatureField(reduced)?.maximum).toBe(86.4);
    expect(selectMetric(full, "temperature")?.quantity.value).toBe(87.2);
    expect(selectTemperatureField(full)?.maximum).toBe(87.2);
  });

  it("passes the calibrated reduced model only when every live gate is supported", () => {
    const snapshot = policySnapshot();
    const evaluations = selectGateEvaluations(snapshot, "reduced");
    expect(evaluations.map(({ id, status }) => ({ id, status }))).toEqual([
      { id: "validity", status: "pass" },
      { id: "model-error", status: "pass" },
      { id: "failure-margin", status: "pass" },
      { id: "temperature-discrepancy", status: "pass" },
      { id: "margin-discrepancy", status: "pass" },
      { id: "evidence-integrity", status: "pass" },
    ]);
    expect(policyGate(snapshot, "reduced", "model-error").evidenceIds).toEqual(
      expect.arrayContaining([
        TEST_EVIDENCE.temperature,
        TEST_EVIDENCE.warpage,
        TEST_EVIDENCE.marginValidation,
      ]),
    );
    expect(policyGate(snapshot, "reduced", "failure-margin").observed).toContain(
      "conservative lower bound",
    );
    expect(selectModelAdequacy(snapshot, "reduced").status).toBe("adequate");
  });

  it("preserves every compact-model reason that requires escalation", () => {
    const result = selectModelAdequacy(policySnapshot(), "compact");
    expect(result.status).toBe("escalate");
    expect(
      result.gates.filter((item) => item.status === "fail").map((item) => item.id),
    ).toEqual([
      "model-error",
      "temperature-discrepancy",
      "margin-discrepancy",
    ]);
    expect(result.summary).toContain("exceeds the policy limit");
    expect(result.summary).toContain("Hotspot difference exceeds");
    expect(result.summary).toContain("Failure-margin discrepancy exceeds");
  });

  it("passes exact and roundoff-level thresholds but fails a true exceedance", () => {
    const atLimit = policySnapshot();
    setPolicyMetric(atLimit, "test-run-reduced", "margin", 107);
    setPolicyMetric(atLimit, "test-run-full", "margin", 100);
    expect(policyGate(atLimit, "reduced", "margin-discrepancy").status).toBe("pass");

    const roundoff = policySnapshot();
    setPolicyMetric(roundoff, "test-run-reduced", "margin", 107.00000000000001);
    setPolicyMetric(roundoff, "test-run-full", "margin", 100);
    expect(policyGate(roundoff, "reduced", "margin-discrepancy").status).toBe("pass");

    const overLimit = policySnapshot();
    setPolicyMetric(overLimit, "test-run-reduced", "margin", 107.0000000001);
    setPolicyMetric(overLimit, "test-run-full", "margin", 100);
    expect(policyGate(overLimit, "reduced", "margin-discrepancy").status).toBe("fail");
  });

  it("fails the failure-margin gate when its conservative lower bound crosses policy", () => {
    const snapshot = policySnapshot();
    setPolicyMetric(snapshot, "test-run-reduced", "margin", 1.2);

    const result = policyGate(snapshot, "reduced", "failure-margin");
    expect(result.status).toBe("fail");
    expect(result.observed).toBe("1.14 conservative lower bound");
    expect(result.explanation).toContain("crosses the reliability threshold");
  });

  it("does not pass model error when a decision metric lacks uncertainty provenance", () => {
    const snapshot = policySnapshot();
    const warpage = requirePolicyRun(snapshot, "test-run-reduced").output?.metrics?.find(
      (metric) => metric.key === "warpage",
    );
    if (!warpage) throw new Error("Test-only fixture is missing reduced warpage");
    warpage.uncertainty = undefined;

    const result = policyGate(snapshot, "reduced", "model-error");
    expect(result.status).toBe("not-evaluable");
    expect(result.explanation).toContain("documented assessment");
    expect(selectModelAdequacy(snapshot, "reduced").status).toBe("review");
  });

  it("does not pass evidence integrity when validation provenance is missing", () => {
    const snapshot = policySnapshot();
    snapshot.evidence = snapshot.evidence.filter(
      (record) => record.id !== TEST_EVIDENCE.marginValidation,
    );

    const result = policyGate(snapshot, "reduced", "evidence-integrity");
    expect(result.status).toBe("not-evaluable");
    expect(result.explanation).toContain(TEST_EVIDENCE.marginValidation);
  });

  it("does not pass discrepancy gates when a required reference result is missing", () => {
    const snapshot = policySnapshot();
    const reference = requirePolicyRun(snapshot, "test-run-full");
    if (!reference.output?.metrics) throw new Error("Test-only fixture is missing full output");
    reference.output.metrics = reference.output.metrics.filter(
      (metric) => metric.key !== "temperature" && metric.key !== "margin",
    );

    expect(policyGate(snapshot, "reduced", "temperature-discrepancy").status).toBe(
      "not-evaluable",
    );
    expect(policyGate(snapshot, "reduced", "margin-discrepancy").status).toBe(
      "not-evaluable",
    );
    expect(selectModelAdequacy(snapshot, "reduced").status).toBe("review");
  });

  it("fails validity when the active design leaves the bounded model domain", () => {
    const snapshot = policySnapshot();
    const design = snapshot.designs.find((candidate) => candidate.id === TEST_DESIGN_ID);
    if (!design) throw new Error("Test-only fixture is missing the active design");
    design.parameters.tsv_pitch = { value: 81, unit: "µm" };

    const result = policyGate(snapshot, "reduced", "validity");
    expect(result.status).toBe("fail");
    expect(result.explanation).toContain("above 80 µm");
  });

  it("derives completed workflow stages from the selected successful run", () => {
    const workflow = selectWorkflow(policySnapshot(), "reduced");
    expect(workflow.readyCount).toBe(3);
    expect(workflow.stages.map(({ id, state }) => ({ id, state }))).toEqual([
      { id: "layout", state: "complete" },
      { id: "thermal", state: "complete" },
      { id: "mechanical", state: "complete" },
      { id: "reliability", state: "review" },
    ]);
    expect(workflow.stages[1]?.summary).toContain("86.4 °C");
    expect(workflow.stages[2]?.summary).toContain("42 µm");
  });

  it("derives active workflow stages without replacing the last successful output", () => {
    const snapshot = policySnapshot();
    snapshot.runs.unshift({
      ...structuredClone(requirePolicyRun(snapshot, "test-run-reduced")),
      id: "test-run-queued",
      clientRequestId: "test-only-queued-request",
      sequence: 105,
      status: "queued",
      requestedAt: "2026-08-01T19:00:00.000Z",
      startedAt: undefined,
      completedAt: undefined,
      output: undefined,
      progress: {
        phase: "preparing",
        fraction: 0,
        message: "Test-only queue message",
      },
    });

    const workflow = selectWorkflow(snapshot, "reduced");
    expect(workflow.readyCount).toBe(1);
    expect(workflow.stages.map(({ id, state }) => ({ id, state }))).toEqual([
      { id: "layout", state: "complete" },
      { id: "thermal", state: "active" },
      { id: "mechanical", state: "active" },
      { id: "reliability", state: "pending" },
    ]);
    expect(workflow.stages[1]?.summary).toBe("Test-only queue message");
    expect(selectLatestSuccessfulRun(snapshot, "reduced")?.id).toBe("test-run-reduced");
  });

  it("computes the preferred feasible candidate from the active policy", () => {
    const snapshot = policySnapshot();
    expect(selectPreferredCandidate(snapshot)?.id).toBe("C");
    expect(
      selectCandidateComparison(snapshot).map(({ candidate, recommendation }) => ({
        id: candidate.id,
        recommendation,
      })),
    ).toEqual([
      { id: "A", recommendation: "reject" },
      { id: "B", recommendation: "feasible" },
      { id: "C", recommendation: "preferred" },
    ]);
  });

  it("counts package layers once and excludes embedded features from stack thickness", () => {
    const snapshot = policySnapshot();
    expect(selectStackThicknessMicrometers(snapshot)).toBe(3048);
    const interposer = snapshot.layers.find((layer) => layer.id === "test-only-interposer");
    expect(interposer?.embeddedFeatures?.map((feature) => feature.id)).toContain(
      "test-only-tsv",
    );
    expect(snapshot.layers.some((layer) => layer.id === "test-only-tsv")).toBe(false);
  });
});

describe("formatting and discrepancy helpers", () => {
  it("uses the reference magnitude as the discrepancy denominator", () => {
    expect(relativeDiscrepancyPercent(1.38, 1.31)).toBeCloseTo(
      (0.07 / 1.31) * 100,
      10,
    );
    expect(relativeDiscrepancyPercent(107, 100)).toBeCloseTo(7, 12);
    expect(relativeDiscrepancyPercent(Number.NaN, 1)).toBeUndefined();
    expect(relativeDiscrepancyPercent(1, 0, 0)).toBeUndefined();
  });

  it("formats explicit missing and recorded durations", () => {
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(1)).toBe("1 s");
    expect(formatDateTime(undefined)).toBe("Not recorded");
    expect(formatDateTime("not-a-date")).toBe("Not recorded");
  });
});
