import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "..");
const python = process.env.PYTHON || "python";
const completed = spawnSync(
  python,
  [path.join(webRoot, "scripts", "render-simulation-media.py")],
  { cwd: repositoryRoot, encoding: "utf8", stdio: "inherit" },
);

if (completed.error) throw completed.error;
if (completed.status !== 0) {
  throw new Error(`simulation-media renderer exited with status ${String(completed.status)}`);
}
