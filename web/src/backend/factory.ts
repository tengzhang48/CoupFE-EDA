import { FastApiBackend } from "./fastapi-backend";
import type { CoupFEBackend } from "./interface";

export function createBackend(): CoupFEBackend {
  const mode = import.meta.env.VITE_COUPFE_BACKEND ?? "retained";
  if (mode === "fastapi") {
    return new FastApiBackend(import.meta.env.VITE_COUPFE_API_BASE_URL || "/api");
  }
  throw new Error(
    mode === "retained"
      ? "The retained Pages explorer has no execution backend."
      : `Unsupported CoupFE backend mode: ${String(mode)}`,
  );
}
