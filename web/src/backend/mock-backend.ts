import {
  createTsvWorkflowOutput,
  demoSnapshot,
  TSV_RETAINED_ARTIFACTS,
  TSV_WORKFLOW_ID,
} from "../demo/snapshot";
import type {
  ApprovedWorkflowDefinition,
  ArtifactRecord,
  EvidenceRecord,
  RunOutput,
  ProjectSnapshot,
  RunEventObserver,
  RunRecord,
  StartRunRequest,
} from "../domain/types";
import type { CoupFEBackend } from "./interface";

interface MockBackendOptions {
  queueDelayMs?: number;
  runDelayMs?: number;
  clock?: () => Date;
  idGenerator?: (snapshot: ProjectSnapshot) => string;
}

interface Subscription {
  afterSequence: number;
  observer: RunEventObserver;
}

type RunTransitionPatch = Partial<Pick<
  RunRecord,
  "status" | "startedAt" | "completedAt" | "progress" | "output" | "failureMessage"
>>;

const terminalStatuses = new Set<RunRecord["status"]>([
  "succeeded",
  "failed",
  "cancelled",
]);

function findWorkflow(
  snapshot: ProjectSnapshot,
  workflowId: string | undefined,
): ApprovedWorkflowDefinition | undefined {
  return snapshot.approvedWorkflows.find((workflow) => workflow.id === workflowId);
}

function clone<T>(value: T): T {
  return structuredClone(value);
}

function nextRunId(snapshot: ProjectSnapshot): string {
  const largest = snapshot.runs.reduce((maximum, run) => {
    const match = /^run-(\d+)$/.exec(run.id);
    return match?.[1] ? Math.max(maximum, Number(match[1])) : maximum;
  }, 0);
  return `run-${largest + 1}`;
}

export class MockBackend implements CoupFEBackend {
  private snapshot: ProjectSnapshot;
  private readonly queueDelayMs: number;
  private readonly runDelayMs: number;
  private readonly clock: () => Date;
  private readonly idGenerator: (snapshot: ProjectSnapshot) => string;
  private readonly subscriptions = new Set<Subscription>();
  private readonly timers = new Map<string, Array<ReturnType<typeof setTimeout>>>();

  constructor(
    initialSnapshot: ProjectSnapshot = demoSnapshot,
    options: MockBackendOptions = {},
  ) {
    this.snapshot = clone(initialSnapshot);
    this.queueDelayMs = options.queueDelayMs ?? 300;
    this.runDelayMs = options.runDelayMs ?? 2400;
    this.clock = options.clock ?? (() => new Date());
    this.idGenerator = options.idGenerator ?? nextRunId;
  }

  async getSnapshot(projectId: string, signal?: AbortSignal): Promise<ProjectSnapshot> {
    signal?.throwIfAborted();
    if (projectId !== this.snapshot.project.id) {
      throw new Error(`Unknown project: ${projectId}`);
    }
    return clone(this.snapshot);
  }

  async startRun(request: StartRunRequest, signal?: AbortSignal): Promise<RunRecord> {
    signal?.throwIfAborted();
    if (request.projectId !== this.snapshot.project.id) {
      throw new Error(`Unknown project: ${request.projectId}`);
    }
    const existing = this.snapshot.runs.find(
      (run) => run.clientRequestId === request.clientRequestId,
    );
    if (existing) {
      if (
        existing.designId !== request.designId ||
        existing.modelId !== request.modelId ||
        existing.workflowId !== request.workflowId
      ) {
        throw new Error("The client request ID is already bound to a different run request.");
      }
      return clone(existing);
    }

    const design = this.snapshot.designs.find((item) => item.id === request.designId);
    const model = request.modelId
      ? this.snapshot.models.find((item) => item.id === request.modelId)
      : undefined;
    const workflow = findWorkflow(this.snapshot, request.workflowId);
    if (!design || (!model && !workflow)) {
      throw new Error("Run request references an unknown design, model, or approved workflow.");
    }

    const runId = this.idGenerator(this.snapshot);
    const requestedAt = this.clock().toISOString();
    const sequence = this.snapshot.sequence + 1;
    const target =
      request.workflowId && workflow
        ? { workflowId: request.workflowId }
        : { modelId: request.modelId! };
    const run: RunRecord = {
      id: runId,
      projectId: request.projectId,
      designId: request.designId,
      ...target,
      clientRequestId: request.clientRequestId,
      sequence,
      status: "queued",
      requestedAt,
      progress: {
        phase: "preparing",
        fraction: 0,
        message: this.snapshot.mode === "demo"
          ? "Simulation queued"
          : workflow
            ? "Queued by the approved workflow adapter"
            : "Queued by the interface-demonstration model adapter",
      },
      input: {
        designRevision: design.label,
        packageRevision: design.packageRevision,
        codeRevision: "not-applicable:static-interface-demo",
        solverVersion: workflow
          ? "Not executed (interface simulation)"
          : model?.version ?? "Not executed (interface simulation)",
        runtimeInputSet: workflow
          ? "examples/tsv_00_device_screening/device_sites.csv"
          : "not-applicable:interface-demo",
        workflowId: workflow?.id,
        executorKey: workflow?.executorKey,
        manifestSha256: "not-applicable:interface-demo",
      },
    };
    this.snapshot = {
      ...this.snapshot,
      sequence,
      runs: [run, ...this.snapshot.runs],
    };
    this.emit(run);
    this.scheduleLifecycle(run.id);
    return clone(run);
  }

  async cancelRun(projectId: string, runId: string, signal?: AbortSignal): Promise<RunRecord> {
    signal?.throwIfAborted();
    if (projectId !== this.snapshot.project.id) throw new Error(`Unknown project: ${projectId}`);
    const run = this.snapshot.runs.find((item) => item.id === runId);
    if (!run) throw new Error(`Unknown run: ${runId}`);
    if (terminalStatuses.has(run.status)) {
      throw new Error(`Run ${runId} is already ${run.status}.`);
    }
    this.clearRunTimers(runId);
    return this.transition(runId, {
      status: "cancelled",
      completedAt: this.clock().toISOString(),
      progress: undefined,
    });
  }

  subscribeProjectEvents(
    projectId: string,
    afterSequence: number,
    observer: RunEventObserver,
  ): () => void {
    if (projectId !== this.snapshot.project.id) {
      queueMicrotask(() => observer.error(new Error(`Unknown project: ${projectId}`)));
      return () => undefined;
    }
    const subscription = { afterSequence, observer };
    this.subscriptions.add(subscription);
    return () => this.subscriptions.delete(subscription);
  }

  private scheduleLifecycle(runId: string) {
    const timers: Array<ReturnType<typeof setTimeout>> = [];
    timers.push(
      setTimeout(() => {
        this.transition(runId, {
          status: "running",
          startedAt: this.clock().toISOString(),
          progress: { phase: "loading", fraction: 0.22, message: "Loading the retained synthetic device-site record" },
        });
      }, this.queueDelayMs),
    );
    timers.push(
      setTimeout(() => {
        this.transition(runId, {
          status: "running",
          progress: { phase: "evaluating", fraction: 0.63, message: "Evaluating the precomputed analytic screening record" },
        });
      }, this.queueDelayMs + this.runDelayMs * 0.35),
    );
    timers.push(
      setTimeout(() => {
        this.transition(runId, {
          status: "running",
          progress: { phase: "retaining", fraction: 0.9, message: "Linking the reviewed evidence artifacts" },
        });
      }, this.queueDelayMs + this.runDelayMs * 0.75),
    );
    timers.push(
      setTimeout(() => this.completeRun(runId),
        this.queueDelayMs + this.runDelayMs),
    );
    this.timers.set(runId, timers);
  }

  private completeRun(runId: string) {
    const run = this.snapshot.runs.find((item) => item.id === runId);
    if (!run || terminalStatuses.has(run.status)) return;
    const startedAt = run.startedAt ?? run.requestedAt;
    const completedAt = new Date(
      Date.parse(startedAt) + this.runDelayMs,
    ).toISOString();
    const output: RunOutput = run.workflowId === TSV_WORKFLOW_ID
      ? createTsvWorkflowOutput(runId, this.runDelayMs / 1000)
      : {
          metrics: [],
          fields: [],
          artifactIds: [],
          evidenceIds: [],
          conclusion: "No numerical model is connected to the public interface demonstration.",
          nextAction: "Use a connected backend with a server-approved executor.",
          qualification: {
            releaseValidation: false,
            claimBoundary: "Interface lifecycle demonstration only; no engineering result was produced.",
          },
        };
    const workflowEvidence: EvidenceRecord | undefined = run.workflowId === TSV_WORKFLOW_ID
      ? {
          id: `ev-${runId}-tsv-screening`,
          runId,
          title: "Retained TSV screening demonstration record",
          category: "result",
          authority: "presentation",
          status: "generated",
          description: "Retained project-generated screening output displayed by the static interface simulation; no solver ran in the browser.",
          source: "generated/tsv_device_screening/evidence.json",
          updatedAt: completedAt,
          artifactIds: TSV_RETAINED_ARTIFACTS.map((artifact) => `${artifact.kind}-${runId}`),
        }
      : undefined;
    const retainedArtifacts: ArtifactRecord[] = run.workflowId === TSV_WORKFLOW_ID
      ? TSV_RETAINED_ARTIFACTS.map((artifact) => ({
          id: `${artifact.kind}-${runId}`,
          runId,
          kind: artifact.kind as ArtifactRecord["kind"],
          uri: artifact.uri,
          sha256: artifact.sha256,
        }))
      : [];
    this.snapshot = {
      ...this.snapshot,
      evidence: workflowEvidence
        ? [workflowEvidence, ...this.snapshot.evidence]
        : this.snapshot.evidence,
      artifacts: [...this.snapshot.artifacts, ...retainedArtifacts],
    };
    this.transition(runId, {
      status: "succeeded",
      completedAt,
      progress: undefined,
      output,
    });
    this.clearRunTimers(runId);
  }

  private transition(runId: string, patch: RunTransitionPatch): RunRecord {
    const current = this.snapshot.runs.find((run) => run.id === runId);
    if (!current) throw new Error(`Unknown run: ${runId}`);
    if (terminalStatuses.has(current.status)) return clone(current);
    const sequence = this.snapshot.sequence + 1;
    const updated: RunRecord = { ...current, ...patch, id: current.id, sequence };
    this.snapshot = {
      ...this.snapshot,
      sequence,
      runs: this.snapshot.runs.map((run) => (run.id === runId ? updated : run)),
    };
    this.emit(updated);
    return clone(updated);
  }

  private emit(run: RunRecord) {
    const event = {
      projectId: this.snapshot.project.id,
      sequence: this.snapshot.sequence,
      emittedAt: this.clock().toISOString(),
      run: clone(run),
    };
    for (const subscription of this.subscriptions) {
      if (event.sequence > subscription.afterSequence) {
        subscription.afterSequence = event.sequence;
        subscription.observer.next(event);
      }
    }
  }

  private clearRunTimers(runId: string) {
    for (const timer of this.timers.get(runId) ?? []) clearTimeout(timer);
    this.timers.delete(runId);
  }
}
