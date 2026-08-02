import type {
  Id,
  ProjectSnapshot,
  RunEventObserver,
  RunRecord,
  StartRunRequest,
} from "../domain/types";

/**
 * The only boundary used by React. Implementations may use in-memory demo data
 * or a real FastAPI service, but views never read files or construct commands.
 */
export interface CoupFEBackend {
  getSnapshot(projectId: Id, signal?: AbortSignal): Promise<ProjectSnapshot>;
  startRun(request: StartRunRequest, signal?: AbortSignal): Promise<RunRecord>;
  cancelRun(projectId: Id, runId: Id, signal?: AbortSignal): Promise<RunRecord>;
  subscribeProjectEvents(
    projectId: Id,
    afterSequence: number,
    observer: RunEventObserver,
  ): () => void;
}
