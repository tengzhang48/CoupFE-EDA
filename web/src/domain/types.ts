export type Id = string;
export type ISODateTime = string;

export type ModelFidelity = "compact" | "reduced" | "full";
export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type MetricKey = "temperature" | "warpage" | "margin" | "runtime";
export type WorkflowStageId = "layout" | "thermal" | "mechanical" | "reliability";

export interface Quantity {
  value: number;
  unit: "°C" | "µm" | "s" | "mm" | "1";
}

interface UncertaintyBase {
  method: string;
  domain: string;
  evidenceIds: Id[];
}

export type UncertaintyAssessment =
  | (UncertaintyBase & {
      kind: "validation-error";
      statistic: "RMSE" | "MAE" | "maximum-relative-error";
      relativePercent: number;
      sampleCount: number;
    })
  | (UncertaintyBase & {
      kind: "conservative-bound";
      direction: "lower" | "upper" | "two-sided";
      relativePercent: number;
    });

export interface ProjectRecord {
  id: Id;
  name: string;
  studyType: string;
  activeDesignId: Id;
  activeDecisionId?: Id;
}

export interface DesignRevision {
  id: Id;
  label: string;
  packageRevision: string;
  createdAt: ISODateTime;
  parameters: Record<string, Quantity>;
}

export interface ValidityRange {
  parameterKey: string;
  label: string;
  minimum?: Quantity;
  maximum?: Quantity;
}

export interface ModelDefinition {
  id: ModelFidelity;
  version: string;
  name: string;
  shortName: string;
  description: string;
  validityClass: "screening" | "calibrated" | "reference";
  costClass: "very-low" | "moderate" | "high";
  expectedRuntimeSeconds: number;
  executorKey: string;
  assumptions: string[];
  validityRanges: ValidityRange[];
}

export interface MetricResult {
  key: MetricKey;
  label: string;
  quantity: Quantity;
  assessment: "nominal" | "watch" | "pass" | "fail";
  location?: string;
  uncertainty?: UncertaintyAssessment;
  evidenceIds: Id[];
}

export interface FieldResult {
  key: "temperature-field";
  label: string;
  unit: "°C";
  minimum: number;
  maximum: number;
  hotspotValue: number;
  hotspotComponentId: Id;
  sharedScale: boolean;
  artifactId: Id;
  evidenceIds: Id[];
}

export interface RunOutput {
  metrics?: MetricResult[];
  fields?: FieldResult[];
  genericMetrics?: GenericMetricResult[];
  artifactIds: Id[];
  evidenceIds: Id[];
  conclusion: string;
  nextAction: string;
  qualification?: QualificationBoundary;
}

export interface GenericMetricResult {
  key: string;
  label: string;
  value: number;
  unit: string;
  assessment: "observed" | "measured" | "demonstration" | "pass" | "watch" | "fail";
  evidenceIds: Id[];
}

export interface QualificationBoundary {
  releaseValidation: boolean;
  claimBoundary: string;
}

export interface ApprovedWorkflowDefinition extends QualificationBoundary {
  id: Id;
  executorKey: string;
  name: string;
  description: string;
  driverPath: string;
  expectedMetricKeys: string[];
}

export interface RunInputManifest {
  designRevision: string;
  packageRevision: string;
  codeRevision: string;
  solverVersion: string;
  runtimeInputSet?: string;
  materialSet?: string;
  boundaryConditionSet?: string;
  workflowId?: Id;
  executorKey?: string;
  manifestSha256: string;
}

export interface RunProgress {
  phase: "preparing" | "loading" | "meshing" | "evaluating" | "solving" | "retaining" | "postprocessing";
  fraction: number;
  message: string;
}

interface RunRecordBase {
  id: Id;
  projectId: Id;
  designId: Id;
  clientRequestId: string;
  sequence: number;
  status: RunStatus;
  requestedAt: ISODateTime;
  startedAt?: ISODateTime;
  completedAt?: ISODateTime;
  progress?: RunProgress;
  input: RunInputManifest;
  output?: RunOutput;
  failureMessage?: string;
}

export type RunRecord = RunRecordBase &
  (
    | { modelId: ModelFidelity; workflowId?: never }
    | { modelId?: never; workflowId: Id }
  );

export interface EvidenceRecord {
  id: Id;
  runId?: Id;
  title: string;
  category: "input" | "verification" | "result" | "provenance";
  authority: "computational-output" | "solver-output" | "validation" | "input-provenance" | "presentation";
  status: "verified" | "review" | "generated";
  description: string;
  source: string;
  updatedAt: ISODateTime;
  artifactIds: Id[];
}

export interface ArtifactRecord {
  id: Id;
  runId?: Id;
  kind: "field" | "mesh" | "manifest" | "report" | "render" | "log" | "data";
  uri: string;
  sha256: string;
}

export interface EmbeddedFeature {
  id: Id;
  name: string;
  material: string;
  role: string;
}

export interface PackageLayer {
  id: Id;
  name: string;
  material: string;
  thickness: Quantity;
  role: string;
  embeddedFeatures?: EmbeddedFeature[];
}

export interface DecisionPolicy {
  maximumModelErrorPercent: number;
  minimumFailureMargin: number;
  maximumTemperatureDifference: Quantity;
  maximumMarginRelativeDifferencePercent: number;
}

export interface ModelSelectionDecision {
  id: Id;
  designId: Id;
  selectedModelId: ModelFidelity;
  status: "proposed" | "approved" | "superseded";
  createdAt: ISODateTime;
  createdBy: "policy" | "user";
  policyVersion: string;
  policy: DecisionPolicy;
  sourceRunIds: Id[];
}

export interface DesignCandidate {
  id: Id;
  name: string;
  designId: Id;
  revision: string;
  metrics: {
    peakTemperature: Quantity;
    warpage: Quantity;
    failureMargin: Quantity;
    runtime: Quantity;
  };
}

export interface ProjectSnapshot {
  schemaVersion: 1;
  sequence: number;
  mode: "demo" | "connected";
  project: ProjectRecord;
  designs: DesignRevision[];
  models: ModelDefinition[];
  approvedWorkflows: ApprovedWorkflowDefinition[];
  decisions: ModelSelectionDecision[];
  runs: RunRecord[];
  evidence: EvidenceRecord[];
  artifacts: ArtifactRecord[];
  layers: PackageLayer[];
  candidates: DesignCandidate[];
}

interface StartRunRequestBase {
  projectId: Id;
  designId: Id;
  clientRequestId: string;
}

export type StartRunRequest = StartRunRequestBase &
  (
    | { modelId: ModelFidelity; workflowId?: never }
    | { modelId?: never; workflowId: Id }
  );

export interface RunEvent {
  projectId: Id;
  sequence: number;
  emittedAt: ISODateTime;
  run: RunRecord;
}

export interface RunEventObserver {
  next: (event: RunEvent) => void;
  error: (error: unknown) => void;
}
