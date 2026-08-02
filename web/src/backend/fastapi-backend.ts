import type {
  ProjectSnapshot,
  RunEvent,
  RunEventObserver,
  RunRecord,
  StartRunRequest,
} from "../domain/types";
import type { CoupFEBackend } from "./interface";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`CoupFE API request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

/**
 * Thin transport adapter for the same-repository loopback service. HTTP status
 * handling is enforced here; runtime response-schema validation remains open
 * before this adapter can trust an independently deployed service.
 */
export class FastApiBackend implements CoupFEBackend {
  constructor(private readonly baseUrl = "/api") {}

  async getSnapshot(projectId: string, signal?: AbortSignal): Promise<ProjectSnapshot> {
    const response = await fetch(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}`, { signal });
    return readJson<ProjectSnapshot>(response);
  }

  async startRun(request: StartRunRequest, signal?: AbortSignal): Promise<RunRecord> {
    const response = await fetch(`${this.baseUrl}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
      signal,
    });
    return readJson<RunRecord>(response);
  }

  async cancelRun(projectId: string, runId: string, signal?: AbortSignal): Promise<RunRecord> {
    const response = await fetch(
      `${this.baseUrl}/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST", signal },
    );
    return readJson<RunRecord>(response);
  }

  subscribeProjectEvents(
    projectId: string,
    afterSequence: number,
    observer: RunEventObserver,
  ): () => void {
    const url = `${this.baseUrl}/projects/${encodeURIComponent(projectId)}/events?after=${afterSequence}`;
    const source = new EventSource(url);
    source.onmessage = (message) => {
      try {
        observer.next(JSON.parse(message.data) as RunEvent);
      } catch (error) {
        observer.error(error);
      }
    };
    source.onerror = () => observer.error(new Error("CoupFE event stream disconnected."));
    return () => source.close();
  }
}
