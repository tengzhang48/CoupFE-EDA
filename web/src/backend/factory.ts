import { FastApiBackend } from "./fastapi-backend";
import type { CoupFEBackend } from "./interface";
import { MockBackend } from "./mock-backend";

export function createBackend(): CoupFEBackend {
  const mode = import.meta.env.VITE_COUPFE_BACKEND ?? "mock";
  if (mode === "mock") return new MockBackend();
  if (mode === "fastapi") {
    return new FastApiBackend(import.meta.env.VITE_COUPFE_API_BASE_URL || "/api");
  }
  throw new Error(`Unsupported CoupFE backend mode: ${String(mode)}`);
}
