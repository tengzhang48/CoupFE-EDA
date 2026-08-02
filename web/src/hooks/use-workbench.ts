import { useCallback, useEffect, useRef, useState } from "react";
import type { CoupFEBackend } from "../backend/interface";
import type { ModelFidelity, ProjectSnapshot, RunRecord } from "../domain/types";

export function useWorkbench(backend: CoupFEBackend, projectId: string) {
  const [snapshot, setSnapshot] = useState<ProjectSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const reload = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const next = await backend.getSnapshot(projectId, signal);
        if (mounted.current) {
          setSnapshot(next);
          setError(null);
        }
        return next;
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === "AbortError") return null;
        if (mounted.current) setError(cause instanceof Error ? cause.message : "Unable to load the project.");
        return null;
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [backend, projectId],
  );

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void reload(controller.signal);
    return () => {
      mounted.current = false;
      controller.abort();
    };
  }, [reload]);

  useEffect(() => {
    if (!snapshot) return;
    return backend.subscribeProjectEvents(projectId, snapshot.sequence, {
      next: () => void reload(),
      error: (cause) => {
        if (mounted.current) {
          setError(cause instanceof Error ? cause.message : "The run event stream disconnected.");
        }
      },
    });
  }, [backend, projectId, reload, snapshot?.sequence]);

  const startRun = useCallback(
    async (modelId: ModelFidelity): Promise<RunRecord> => {
      const designId = snapshot?.project.activeDesignId;
      if (!designId) throw new Error("No active design revision is available.");
      const run = await backend.startRun({
        projectId,
        designId,
        modelId,
        clientRequestId: crypto.randomUUID(),
      });
      await reload();
      return run;
    },
    [backend, projectId, reload, snapshot?.project.activeDesignId],
  );

  const startWorkflow = useCallback(
    async (workflowId: string): Promise<RunRecord> => {
      const designId = snapshot?.project.activeDesignId;
      if (!designId) throw new Error("No active design revision is available.");
      const workflow = snapshot?.approvedWorkflows.find((item) => item.id === workflowId);
      if (!workflow) throw new Error(`Unknown approved workflow: ${workflowId}`);
      const run = await backend.startRun({
        projectId,
        designId,
        workflowId,
        clientRequestId: crypto.randomUUID(),
      });
      await reload();
      return run;
    },
    [backend, projectId, reload, snapshot?.approvedWorkflows, snapshot?.project.activeDesignId],
  );

  const cancelRun = useCallback(
    async (runId: string): Promise<RunRecord> => {
      const run = await backend.cancelRun(projectId, runId);
      await reload();
      return run;
    },
    [backend, projectId, reload],
  );

  return { snapshot, loading, error, reload, startRun, startWorkflow, cancelRun };
}
