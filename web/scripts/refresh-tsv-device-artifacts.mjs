import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "..");
const output = path.join(webRoot, "public", "generated", "tsv_device_screening");
const artifactContract = path.join(webRoot, "contracts", "retained-tsv-artifacts.json");
const scratch = await mkdtemp(path.join(tmpdir(), "coupfe-eda-tsv-site-"));
const python = process.env.PYTHON || "python";

try {
  await mkdir(output, { recursive: true });
  const completed = spawnSync(
    python,
    [
      path.join(repositoryRoot, "examples", "tsv_00_device_screening", "run.py"),
      "--output-dir",
      scratch,
    ],
    {
      cwd: repositoryRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "inherit"],
    },
  );
  if (completed.status !== 0) {
    throw new Error(`TSV device runner exited with status ${String(completed.status)}`);
  }
  const evidence = JSON.parse(await readFile(path.join(scratch, "evidence.json"), "utf8"));
  if (evidence.release_validation !== false || !evidence.claim_boundary) {
    throw new Error("TSV device runner omitted the required non-validation boundary");
  }
  for (const name of ["device_screening.csv", "device_screening.svg", "evidence.json"]) {
    await copyFile(path.join(scratch, name), path.join(output, name));
  }
  const definitions = [
    ["evidence.json", "report"],
    ["device_screening.svg", "render"],
    ["device_screening.csv", "data"],
  ];
  const artifacts = await Promise.all(definitions.map(async ([name, kind]) => ({
    name,
    kind,
    uri: `generated/tsv_device_screening/${name}`,
    sha256: createHash("sha256")
      .update(await readFile(path.join(output, name)))
      .digest("hex"),
  })));
  await writeFile(
    artifactContract,
    `${JSON.stringify({
      schemaVersion: 1,
      generatedBy: "examples/tsv_00_device_screening/run.py",
      releaseValidation: false,
      artifacts,
    }, null, 2)}\n`,
    "utf8",
  );
  console.log("refreshed public TSV device artifacts from the repository runner");
} finally {
  await rm(scratch, { recursive: true, force: true });
}
