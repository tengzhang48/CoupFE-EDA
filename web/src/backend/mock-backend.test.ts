import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  demoSnapshot,
  TSV_CLAIM_BOUNDARY,
  TSV_RETAINED_ARTIFACTS,
} from "../demo/snapshot";
import type { RunEvent, StartRunRequest } from "../domain/types";
import { MockBackend } from "./mock-backend";

const projectId = demoSnapshot.project.id;
const request: StartRunRequest = {
  projectId,
  designId: demoSnapshot.project.activeDesignId,
  workflowId: "tsv_device_screening",
  clientRequestId: "sentinel-request-id",
};

function backend(overrides: ConstructorParameters<typeof MockBackend>[1] = {}) {
  return new MockBackend(demoSnapshot, {
    queueDelayMs: 100,
    runDelayMs: 1_000,
    clock: () => new Date("2026-08-01T19:00:00.000Z"),
    idGenerator: () => "run-Z9",
    ...overrides,
  });
}

describe("MockBackend", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("returns defensive snapshot copies", async () => {
    const subject = backend();
    const first = await subject.getSnapshot(projectId);
    first.approvedWorkflows.length = 0;
    first.project.name = "Mutated outside backend";

    const second = await subject.getSnapshot(projectId);
    expect(second.approvedWorkflows).toHaveLength(1);
    expect(second.project.name).toBe(demoSnapshot.project.name);
  });

  it("creates a backend-owned interface-only queued record", async () => {
    const subject = backend();
    const created = await subject.startRun(request);
    const snapshot = await subject.getSnapshot(projectId);

    expect(created).toMatchObject({
      id: "run-Z9",
      clientRequestId: request.clientRequestId,
      workflowId: request.workflowId,
      status: "queued",
      sequence: demoSnapshot.sequence + 1,
    });
    expect(snapshot.sequence).toBe(demoSnapshot.sequence + 1);
    expect(snapshot.runs).toEqual([created]);
    expect(created.input.solverVersion).toBe("Not executed (interface simulation)");
    expect(created.input.manifestSha256).toBe("not-applicable:interface-demo");
    expect(created.output).toBeUndefined();
  });

  it("deduplicates retries by client request id", async () => {
    const subject = backend();
    const first = await subject.startRun(request);
    const second = await subject.startRun(request);
    const snapshot = await subject.getSnapshot(projectId);

    expect(second).toEqual(first);
    expect(snapshot.runs.filter((run) => run.id === "run-Z9")).toHaveLength(1);
    expect(snapshot.sequence).toBe(demoSnapshot.sequence + 1);
    await expect(
      subject.startRun({ ...request, workflowId: "unknown-workflow" }),
    ).rejects.toThrow("already bound to a different run request");
  });

  it("simulates an ordered lifecycle and links the reviewed TSV record", async () => {
    const subject = backend();
    const events: RunEvent[] = [];
    const errors: unknown[] = [];
    subject.subscribeProjectEvents(projectId, demoSnapshot.sequence, {
      next: (event) => events.push(event),
      error: (error) => errors.push(error),
    });

    await subject.startRun(request);
    const queuedInput = structuredClone(events.at(-1)?.run.input);
    expect(events.at(-1)?.run.status).toBe("queued");

    await vi.advanceTimersByTimeAsync(100);
    expect(events.at(-1)?.run).toMatchObject({
      status: "running",
      progress: { phase: "loading", fraction: 0.22 },
    });

    await vi.advanceTimersByTimeAsync(350);
    expect(events.at(-1)?.run.progress?.phase).toBe("evaluating");

    await vi.advanceTimersByTimeAsync(400);
    expect(events.at(-1)?.run.progress?.phase).toBe("retaining");

    await vi.advanceTimersByTimeAsync(250);
    const completed = events.at(-1)?.run;
    expect(completed?.status).toBe("succeeded");
    expect(completed?.input).toEqual(queuedInput);
    expect(completed?.completedAt).toBe("2026-08-01T19:00:01.000Z");
    expect(completed?.output?.genericMetrics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: "baseline_violations", value: 12 }),
        expect.objectContaining({ key: "optimized_violations", value: 0 }),
        expect.objectContaining({ key: "runtime_seconds", value: 1 }),
      ]),
    );
    expect(completed?.output?.qualification).toEqual({
      releaseValidation: false,
      claimBoundary: TSV_CLAIM_BOUNDARY,
    });
    expect(events.map((event) => event.sequence)).toEqual([1, 2, 3, 4, 5]);
    expect(errors).toEqual([]);

    const snapshot = await subject.getSnapshot(projectId);
    expect(snapshot.sequence).toBe(5);
    expect(snapshot.evidence).toEqual([
      expect.objectContaining({
        id: "ev-run-Z9-tsv-screening",
        authority: "presentation",
      }),
    ]);
    expect(snapshot.artifacts.map(({ kind, sha256 }) => ({ kind, sha256 }))).toEqual(
      TSV_RETAINED_ARTIFACTS.map(({ kind, sha256 }) => ({ kind, sha256 })),
    );
    expect(snapshot.artifacts.some((item) => item.kind === "manifest")).toBe(false);
  });

  it("cancels an active simulation and keeps it terminal", async () => {
    const subject = backend();
    await subject.startRun(request);
    await vi.advanceTimersByTimeAsync(100);

    const cancelled = await subject.cancelRun(projectId, "run-Z9");
    expect(cancelled.status).toBe("cancelled");
    expect(cancelled.completedAt).toBe("2026-08-01T19:00:00.000Z");
    expect(cancelled.progress).toBeUndefined();

    await vi.advanceTimersByTimeAsync(10_000);
    const snapshot = await subject.getSnapshot(projectId);
    const stored = snapshot.runs.find((run) => run.id === "run-Z9");
    expect(stored?.status).toBe("cancelled");
    expect(stored?.output).toBeUndefined();
    expect(snapshot.artifacts.some((item) => item.runId === "run-Z9")).toBe(false);
    await expect(subject.cancelRun(projectId, "run-Z9")).rejects.toThrow(
      "already cancelled",
    );
  });

  it("supports unsubscribe and filters old events", async () => {
    const subject = backend();
    const accepted: RunEvent[] = [];
    const filtered: RunEvent[] = [];
    const unsubscribe = subject.subscribeProjectEvents(projectId, demoSnapshot.sequence, {
      next: (event) => accepted.push(event),
      error: () => undefined,
    });
    subject.subscribeProjectEvents(projectId, demoSnapshot.sequence + 1, {
      next: (event) => filtered.push(event),
      error: () => undefined,
    });

    await subject.startRun(request);
    expect(accepted).toHaveLength(1);
    expect(filtered).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(100);
    expect(accepted).toHaveLength(2);
    expect(filtered).toHaveLength(1);

    unsubscribe();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(accepted).toHaveLength(2);
    expect(filtered.at(-1)?.run.status).toBe("succeeded");
  });

  it("rejects unknown references and already-aborted requests", async () => {
    const subject = backend();
    await expect(subject.getSnapshot("wrong-project")).rejects.toThrow(
      "Unknown project",
    );
    await expect(
      subject.startRun({ ...request, designId: "missing-design" }),
    ).rejects.toThrow("unknown design, model, or approved workflow");
    await expect(
      subject.startRun({ ...request, workflowId: "unknown-workflow", clientRequestId: "other" }),
    ).rejects.toThrow("unknown design, model, or approved workflow");

    const controller = new AbortController();
    controller.abort();
    await expect(subject.getSnapshot(projectId, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("reports an invalid event subscription asynchronously", async () => {
    const subject = backend();
    const error = vi.fn();
    subject.subscribeProjectEvents("wrong-project", 0, {
      next: () => undefined,
      error,
    });

    await Promise.resolve();
    expect(error).toHaveBeenCalledOnce();
    expect(error.mock.calls[0]?.[0]).toBeInstanceOf(Error);
  });
});
