import type {
  DesignCandidate,
  DesignRevision,
  EvidenceRecord,
  FieldResult,
  MetricKey,
  MetricResult,
  ModelDefinition,
  ModelFidelity,
  ModelSelectionDecision,
  ProjectSnapshot,
  Quantity,
  RunRecord,
  WorkflowStageId,
} from "./types";

export type GateStatus = "pass" | "fail" | "review" | "not-evaluable";

export interface GateEvaluation {
  id: string;
  label: string;
  status: GateStatus;
  observed: string;
  threshold: string;
  explanation: string;
  sourceRunIds: string[];
  evidenceIds: string[];
}

export interface WorkflowStageView {
  id: WorkflowStageId;
  name: string;
  state: "complete" | "active" | "review" | "blocked" | "pending";
  summary: string;
  timestamp?: string;
}

export const DISPLAY_TIME_ZONE = "America/New_York";

export function selectActiveDesign(snapshot: ProjectSnapshot): DesignRevision | undefined {
  return snapshot.designs.find((design) => design.id === snapshot.project.activeDesignId);
}

export function selectActiveDecision(snapshot: ProjectSnapshot): ModelSelectionDecision | undefined {
  return snapshot.decisions.find((decision) => decision.id === snapshot.project.activeDecisionId);
}

export function selectModel(
  snapshot: ProjectSnapshot,
  modelId: ModelFidelity,
): ModelDefinition | undefined {
  return snapshot.models.find((model) => model.id === modelId);
}

export function selectLatestRun(
  snapshot: ProjectSnapshot,
  modelId?: ModelFidelity,
): RunRecord | undefined {
  const designId = snapshot.project.activeDesignId;
  return [...snapshot.runs]
    .filter((run) => run.designId === designId && (!modelId || run.modelId === modelId))
    .sort((a, b) => Date.parse(b.requestedAt) - Date.parse(a.requestedAt))[0];
}

export function selectLatestSuccessfulRun(
  snapshot: ProjectSnapshot,
  modelId: ModelFidelity,
): RunRecord | undefined {
  return [...snapshot.runs]
    .filter(
      (run) =>
        run.designId === snapshot.project.activeDesignId &&
        run.modelId === modelId &&
        run.status === "succeeded" &&
        run.output,
    )
    .sort((a, b) => Date.parse(b.completedAt ?? b.requestedAt) - Date.parse(a.completedAt ?? a.requestedAt))[0];
}

export function selectLastCompletedRun(snapshot: ProjectSnapshot): RunRecord | undefined {
  return [...snapshot.runs]
    .filter((run) => run.status === "succeeded" && run.completedAt)
    .sort((a, b) => Date.parse(b.completedAt ?? "") - Date.parse(a.completedAt ?? ""))[0];
}

export function selectMetric(run: RunRecord | undefined, key: MetricKey): MetricResult | undefined {
  return run?.output?.metrics?.find((metric) => metric.key === key);
}

export function selectTemperatureField(run: RunRecord | undefined): FieldResult | undefined {
  return run?.output?.fields?.find((field) => field.key === "temperature-field");
}

export function selectEvidenceByIds(
  snapshot: ProjectSnapshot,
  evidenceIds: string[],
): EvidenceRecord[] {
  const requested = new Set(evidenceIds);
  return snapshot.evidence.filter((evidence) => requested.has(evidence.id));
}

export function selectEvidenceIntegrity(
  snapshot: ProjectSnapshot,
  evidenceIds: string[],
): { valid: boolean; missingIds: string[] } {
  const known = new Set(snapshot.evidence.map((evidence) => evidence.id));
  const missingIds = evidenceIds.filter((id) => !known.has(id));
  return { valid: missingIds.length === 0, missingIds };
}

export function selectEvidenceSummary(snapshot: ProjectSnapshot) {
  return snapshot.evidence.reduce(
    (summary, evidence) => {
      summary[evidence.status] += 1;
      return summary;
    },
    { verified: 0, review: 0, generated: 0 },
  );
}

export function formatDateTime(value: string | undefined): string {
  if (!value || Number.isNaN(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatTime(value: string | undefined): string {
  if (!value || Number.isNaN(Date.parse(value))) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function runDurationSeconds(run: RunRecord): number | undefined {
  if (!run.startedAt || !run.completedAt) return undefined;
  return Math.max(0, Math.round((Date.parse(run.completedAt) - Date.parse(run.startedAt)) / 1000));
}

export function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function formatQuantity(quantity: Quantity, digits = quantity.unit === "1" ? 2 : 1): string {
  const value = Number.isInteger(quantity.value)
    ? quantity.value.toFixed(0)
    : quantity.value.toFixed(digits).replace(/\.0$/, "");
  return quantity.unit === "1" ? value : `${value} ${quantity.unit}`;
}

export function uncertaintyPercent(metric: MetricResult | undefined): number | undefined {
  return metric?.uncertainty?.relativePercent;
}

export function formatUncertainty(metric: MetricResult | undefined): string {
  const uncertainty = metric?.uncertainty;
  if (!uncertainty) return "Not assessed";
  if (uncertainty.kind === "validation-error") {
    return `±${uncertainty.relativePercent}% · ${uncertainty.statistic.replaceAll("-", " ")}`;
  }
  return uncertainty.direction === "two-sided"
    ? `±${uncertainty.relativePercent}% · conservative guard bound`
    : `${uncertainty.relativePercent}% ${uncertainty.direction} guard bound`;
}

function compatibleUnits(a: Quantity | undefined, b: Quantity | undefined): boolean {
  return Boolean(a && b && a.unit === b.unit);
}

function evaluateValidity(
  snapshot: ProjectSnapshot,
  model: ModelDefinition | undefined,
): GateEvaluation {
  const design = selectActiveDesign(snapshot);
  if (!model || !design) {
    return {
      id: "validity",
      label: "Model validity",
      status: "not-evaluable",
      observed: "Missing model or design",
      threshold: "Defined validity domain",
      explanation: "The model validity gate cannot be evaluated.",
      sourceRunIds: [],
      evidenceIds: [],
    };
  }
  if (model.validityRanges.length === 0) {
    return {
      id: "validity",
      label: "Model validity",
      status: "pass",
      observed: model.validityClass,
      threshold: "No bounded parameter range",
      explanation: `${model.shortName} has no parameter-range violation for this demonstration.`,
      sourceRunIds: [],
      evidenceIds: [],
    };
  }

  const failures: string[] = [];
  const observations: string[] = [];
  for (const range of model.validityRanges) {
    const observed = design.parameters[range.parameterKey];
    if (!observed) {
      failures.push(`${range.label} is missing`);
      continue;
    }
    observations.push(`${range.label} ${formatQuantity(observed)}`);
    if (range.minimum && (!compatibleUnits(observed, range.minimum) || observed.value < range.minimum.value)) {
      failures.push(`${range.label} is below ${formatQuantity(range.minimum)}`);
    }
    if (range.maximum && (!compatibleUnits(observed, range.maximum) || observed.value > range.maximum.value)) {
      failures.push(`${range.label} is above ${formatQuantity(range.maximum)}`);
    }
  }

  return {
    id: "validity",
    label: "Model validity",
    status: failures.length ? "fail" : "pass",
    observed: observations.join("; ") || "Not available",
    threshold: model.validityRanges
      .map((range) => `${range.label} ${range.minimum ? formatQuantity(range.minimum) : "−∞"}–${range.maximum ? formatQuantity(range.maximum) : "+∞"}`)
      .join("; "),
    explanation: failures.length ? failures.join("; ") : "All bounded model parameters are inside the calibrated domain.",
    sourceRunIds: [],
    evidenceIds: [],
  };
}

function evaluateModelError(run: RunRecord | undefined, limit: number): GateEvaluation {
  const assessed = (run?.output?.metrics ?? [])
    .filter((metric) => metric.key !== "runtime" && metric.uncertainty)
    .map((metric) => ({ metric, value: metric.uncertainty?.relativePercent ?? Number.NaN }));
  const allDecisionMetrics = new Set<MetricKey>(["temperature", "warpage", "margin"]);
  assessed.forEach(({ metric }) => allDecisionMetrics.delete(metric.key));
  if (!run || assessed.length === 0 || allDecisionMetrics.size > 0) {
    return {
      id: "model-error",
      label: "Assessed model error",
      status: "not-evaluable",
      observed: "Not assessed for every decision metric",
      threshold: `≤ ${limit}%`,
      explanation: "Temperature, warpage, and failure margin each require a documented assessment.",
      sourceRunIds: run ? [run.id] : [],
      evidenceIds: [],
    };
  }
  const worst = assessed.reduce((current, item) => (item.value > current.value ? item : current));
  return {
    id: "model-error",
    label: "Assessed model error",
    status: lessThanOrEqualWithinRoundoff(worst.value, limit) ? "pass" : "fail",
    observed: `${worst.metric.label} ±${worst.value}%`,
    threshold: `≤ ${limit}%`,
    explanation:
      lessThanOrEqualWithinRoundoff(worst.value, limit)
        ? "Every decision metric has a documented assessment within the policy limit."
        : `${worst.metric.label} exceeds the policy limit; escalate fidelity.`,
    sourceRunIds: [run.id],
    evidenceIds: [...new Set(assessed.flatMap(({ metric }) => metric.uncertainty?.evidenceIds ?? []))],
  };
}

function evaluateFailureMargin(run: RunRecord | undefined, minimum: number): GateEvaluation {
  const margin = selectMetric(run, "margin");
  if (!run || !margin || margin.quantity.unit !== "1" || !Number.isFinite(margin.quantity.value)) {
    return {
      id: "failure-margin",
      label: "Failure margin",
      status: "not-evaluable",
      observed: "Missing or incompatible margin",
      threshold: `≥ ${minimum}`,
      explanation: "A dimensionless failure margin is required.",
      sourceRunIds: run ? [run.id] : [],
      evidenceIds: margin?.evidenceIds ?? [],
    };
  }
  if (margin.uncertainty?.kind !== "conservative-bound" || margin.uncertainty.direction !== "lower") {
    return {
      id: "failure-margin",
      label: "Failure margin",
      status: "not-evaluable",
      observed: "Conservative lower bound not assessed",
      threshold: `≥ ${minimum}`,
      explanation: "The active reliability policy requires a documented conservative lower bound.",
      sourceRunIds: [run.id],
      evidenceIds: [...new Set([...margin.evidenceIds, ...(margin.uncertainty?.evidenceIds ?? [])])],
    };
  }
  const bound = margin.quantity.value * (1 - margin.uncertainty.relativePercent / 100);
  return {
    id: "failure-margin",
    label: "Failure margin",
    status: lessThanOrEqualWithinRoundoff(minimum, bound) ? "pass" : "fail",
    observed: `${bound.toFixed(2)} conservative lower bound`,
    threshold: `≥ ${minimum}`,
    explanation:
      lessThanOrEqualWithinRoundoff(minimum, bound)
        ? "The evaluated margin remains above the reliability threshold."
        : "The evaluated margin crosses the reliability threshold.",
    sourceRunIds: [run.id],
    evidenceIds: [...new Set([...margin.evidenceIds, ...(margin.uncertainty?.evidenceIds ?? [])])],
  };
}

function evaluateEvidenceLinks(
  snapshot: ProjectSnapshot,
  run: RunRecord | undefined,
): GateEvaluation {
  if (!run?.output) {
    return {
      id: "evidence-integrity",
      label: "Evidence integrity",
      status: "not-evaluable",
      observed: "No completed output",
      threshold: "All evidence and artifact links resolve",
      explanation: "A completed run output is required before evidence integrity can be evaluated.",
      sourceRunIds: run ? [run.id] : [],
      evidenceIds: [],
    };
  }

  const evidenceIds = [...new Set([
    ...run.output.evidenceIds,
    ...(run.output.metrics ?? []).flatMap((metric) => [
      ...metric.evidenceIds,
      ...(metric.uncertainty?.evidenceIds ?? []),
    ]),
    ...(run.output.fields ?? []).flatMap((field) => field.evidenceIds),
  ])];
  const records = selectEvidenceByIds(snapshot, evidenceIds);
  const recordById = new Map(records.map((record) => [record.id, record]));
  const missingEvidence = evidenceIds.filter((id) => !recordById.has(id));
  const artifactIds = [...new Set([
    ...run.output.artifactIds,
    ...records.flatMap((record) => record.artifactIds),
  ])];
  const artifactById = new Map(snapshot.artifacts.map((artifact) => [artifact.id, artifact]));
  const missingArtifacts = artifactIds.filter((id) => {
    const artifact = artifactById.get(id);
    return !artifact || !artifact.sha256;
  });
  const invalidAssessmentEvidence = (run.output.metrics ?? []).flatMap((metric) =>
    (metric.uncertainty?.evidenceIds ?? []).filter((id) => {
      const record = recordById.get(id);
      return !record || record.authority !== "validation" || record.status !== "verified";
    }),
  );
  const missing = [...missingEvidence, ...missingArtifacts];
  const invalid = [...new Set(invalidAssessmentEvidence)];
  const status: GateStatus = missing.length
    ? "not-evaluable"
    : invalid.length
      ? "review"
      : "pass";
  return {
    id: "evidence-integrity",
    label: "Evidence integrity",
    status,
    observed: `${records.length} evidence records · ${artifactIds.length} checksummed artifacts`,
    threshold: "All links resolve; assessments use verified validation evidence",
    explanation: missing.length
      ? `Missing evidence or artifacts: ${missing.join(", ")}.`
      : invalid.length
        ? `Assessment evidence requires review: ${invalid.join(", ")}.`
        : "Every evidence and artifact link resolves, and numerical assessments cite verified validation records.",
    sourceRunIds: [run.id],
    evidenceIds,
  };
}

function evaluateTemperatureDiscrepancy(
  approximate: RunRecord | undefined,
  reference: RunRecord | undefined,
  maximum: Quantity,
): GateEvaluation {
  const approxMetric = selectMetric(approximate, "temperature");
  const refMetric = selectMetric(reference, "temperature");
  if (!approximate || !reference || !approxMetric || !refMetric || !compatibleUnits(approxMetric.quantity, refMetric.quantity) || refMetric.quantity.unit !== maximum.unit) {
    return {
      id: "temperature-discrepancy",
      label: "Temperature discrepancy",
      status: "not-evaluable",
      observed: "Missing or incompatible temperature results",
      threshold: `≤ ${formatQuantity(maximum)}`,
      explanation: "Comparable approximate and reference temperature results are required.",
      sourceRunIds: [approximate?.id, reference?.id].filter((id): id is string => Boolean(id)),
      evidenceIds: [],
    };
  }
  const difference = Math.abs(approxMetric.quantity.value - refMetric.quantity.value);
  return {
    id: "temperature-discrepancy",
    label: "Temperature discrepancy",
    status: lessThanOrEqualWithinRoundoff(difference, maximum.value) ? "pass" : "fail",
    observed: `${difference.toFixed(1)} ${maximum.unit}`,
    threshold: `≤ ${formatQuantity(maximum)}`,
    explanation:
      lessThanOrEqualWithinRoundoff(difference, maximum.value)
        ? "Absolute hotspot difference is within the cross-fidelity tolerance."
        : "Hotspot difference exceeds the cross-fidelity tolerance.",
    sourceRunIds: [approximate.id, reference.id],
    evidenceIds: [...new Set([...approxMetric.evidenceIds, ...refMetric.evidenceIds])],
  };
}

export function relativeDiscrepancyPercent(
  approximate: number,
  reference: number,
  denominatorFloor = 1e-12,
): number | undefined {
  if (![approximate, reference, denominatorFloor].every(Number.isFinite) || denominatorFloor <= 0) return undefined;
  return (Math.abs(approximate - reference) / Math.max(Math.abs(reference), denominatorFloor)) * 100;
}

function lessThanOrEqualWithinRoundoff(observed: number, threshold: number): boolean {
  const tolerance = 32 * Number.EPSILON * Math.max(1, Math.abs(observed), Math.abs(threshold));
  return observed <= threshold + tolerance;
}

function evaluateMarginDiscrepancy(
  approximate: RunRecord | undefined,
  reference: RunRecord | undefined,
  maximumPercent: number,
): GateEvaluation {
  const approxMetric = selectMetric(approximate, "margin");
  const refMetric = selectMetric(reference, "margin");
  const difference = approxMetric && refMetric && compatibleUnits(approxMetric.quantity, refMetric.quantity)
    ? relativeDiscrepancyPercent(approxMetric.quantity.value, refMetric.quantity.value)
    : undefined;
  if (!approximate || !reference || difference === undefined) {
    return {
      id: "margin-discrepancy",
      label: "Margin discrepancy",
      status: "not-evaluable",
      observed: "Missing or incompatible margin results",
      threshold: `≤ ${maximumPercent}%`,
      explanation: "Comparable dimensionless margins are required.",
      sourceRunIds: [approximate?.id, reference?.id].filter((id): id is string => Boolean(id)),
      evidenceIds: [],
    };
  }
  return {
    id: "margin-discrepancy",
    label: "Margin discrepancy",
    status: lessThanOrEqualWithinRoundoff(difference, maximumPercent) ? "pass" : "fail",
    observed: `${difference.toFixed(1)}%`,
    threshold: `≤ ${maximumPercent}%`,
    explanation:
      lessThanOrEqualWithinRoundoff(difference, maximumPercent)
        ? "Relative failure-margin discrepancy is within tolerance."
        : "Failure-margin discrepancy exceeds tolerance.",
    sourceRunIds: [approximate.id, reference.id],
    evidenceIds: [...new Set([...(approxMetric?.evidenceIds ?? []), ...(refMetric?.evidenceIds ?? [])])],
  };
}

export function selectGateEvaluations(
  snapshot: ProjectSnapshot,
  modelId: ModelFidelity,
): GateEvaluation[] {
  const decision = selectActiveDecision(snapshot);
  const model = selectModel(snapshot, modelId);
  const run = selectLatestSuccessfulRun(snapshot, modelId);
  if (!decision) {
    return [
      {
        id: "decision",
        label: "Decision policy",
        status: "not-evaluable",
        observed: "Missing decision",
        threshold: "Active policy",
        explanation: "No active model-selection decision is recorded.",
        sourceRunIds: [],
        evidenceIds: [],
      },
    ];
  }

  const reference = selectLatestSuccessfulRun(snapshot, "full");
  return [
    evaluateValidity(snapshot, model),
    evaluateModelError(run, decision.policy.maximumModelErrorPercent),
    evaluateFailureMargin(run, decision.policy.minimumFailureMargin),
    evaluateTemperatureDiscrepancy(run, reference, decision.policy.maximumTemperatureDifference),
    evaluateMarginDiscrepancy(run, reference, decision.policy.maximumMarginRelativeDifferencePercent),
    evaluateEvidenceLinks(snapshot, run),
  ];
}

export function selectModelAdequacy(snapshot: ProjectSnapshot, modelId: ModelFidelity) {
  const gates = selectGateEvaluations(snapshot, modelId);
  const failures = gates.filter((gate) => gate.status === "fail");
  const unresolved = gates.filter((gate) => gate.status === "review" || gate.status === "not-evaluable");
  if (failures.length) {
    return {
      status: "escalate" as const,
      label: "Escalation required",
      summary: failures.map((gate) => gate.explanation).join(" "),
      gates,
    };
  }
  if (unresolved.length) {
    return {
      status: "review" as const,
      label: "Engineering review required",
      summary: unresolved.map((gate) => gate.explanation).join(" "),
      gates,
    };
  }
  return {
    status: "adequate" as const,
    label: "Adequate for this decision",
    summary: "All live validity, error, discrepancy, and reliability gates pass.",
    gates,
  };
}

export function selectWorkflow(
  snapshot: ProjectSnapshot,
  modelId: ModelFidelity,
): { stages: WorkflowStageView[]; readyCount: number } {
  const design = selectActiveDesign(snapshot);
  const latest = selectLatestRun(snapshot, modelId);
  const successful = selectLatestSuccessfulRun(snapshot, modelId);
  const adequacy = selectModelAdequacy(snapshot, modelId);
  const decision = selectActiveDecision(snapshot);
  const runActive = latest?.status === "queued" || latest?.status === "running";
  const thermalMetric = selectMetric(successful, "temperature");
  const mechanicalMetric = selectMetric(successful, "warpage");

  const stages: WorkflowStageView[] = [
    {
      id: "layout",
      name: "Layout",
      state: design ? "complete" : "pending",
      summary: design ? `${design.label} imported` : "Waiting for a design revision",
      timestamp: formatTime(design?.createdAt),
    },
    {
      id: "thermal",
      name: "Thermal",
      state: runActive ? "active" : thermalMetric ? "complete" : latest?.status === "failed" ? "blocked" : "pending",
      summary: runActive ? latest.progress?.message ?? "Thermal analysis queued" : thermalMetric ? `${thermalMetric.label} ${formatQuantity(thermalMetric.quantity)}` : "No completed thermal result",
      timestamp: runActive ? formatTime(latest.startedAt ?? latest.requestedAt) : formatTime(successful?.completedAt),
    },
    {
      id: "mechanical",
      name: "Mechanical",
      state: runActive ? "active" : mechanicalMetric ? "complete" : latest?.status === "failed" ? "blocked" : "pending",
      summary: runActive ? latest.progress?.phase ?? "Waiting for coupled response" : mechanicalMetric ? `${mechanicalMetric.label} ${formatQuantity(mechanicalMetric.quantity)}` : "No completed mechanical result",
      timestamp: runActive ? formatTime(latest.startedAt ?? latest.requestedAt) : formatTime(successful?.completedAt),
    },
    {
      id: "reliability",
      name: "Reliability",
      state: runActive
        ? "pending"
        : adequacy.status === "escalate"
          ? "blocked"
          : decision?.status === "approved" && adequacy.status === "adequate"
            ? "complete"
            : successful
              ? "review"
              : "pending",
      summary: runActive ? "Waiting for completed evidence" : adequacy.label,
      timestamp: successful ? formatTime(decision?.createdAt) : undefined,
    },
  ];
  return { stages, readyCount: stages.filter((stage) => stage.state === "complete").length };
}

export function selectCandidateComparison(snapshot: ProjectSnapshot) {
  const decision = selectActiveDecision(snapshot);
  const minimumMargin = decision?.policy.minimumFailureMargin ?? Number.POSITIVE_INFINITY;
  const feasible = snapshot.candidates.filter(
    (candidate) => candidate.metrics.failureMargin.value >= minimumMargin,
  );
  const preferred = [...feasible].sort(
    (a, b) => a.metrics.peakTemperature.value - b.metrics.peakTemperature.value,
  )[0];
  return snapshot.candidates.map((candidate) => ({
    candidate,
    recommendation:
      candidate.id === preferred?.id
        ? ("preferred" as const)
        : candidate.metrics.failureMargin.value >= minimumMargin
          ? ("feasible" as const)
          : ("reject" as const),
  }));
}

export function selectPreferredCandidate(snapshot: ProjectSnapshot): DesignCandidate | undefined {
  return selectCandidateComparison(snapshot).find((item) => item.recommendation === "preferred")?.candidate;
}

export function selectStackThicknessMicrometers(snapshot: ProjectSnapshot): number {
  return snapshot.layers.reduce((sum, layer) => {
    const factor = layer.thickness.unit === "mm" ? 1000 : layer.thickness.unit === "µm" ? 1 : 0;
    return sum + layer.thickness.value * factor;
  }, 0);
}
