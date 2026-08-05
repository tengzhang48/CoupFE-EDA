import { copyFile, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "..");
const repositoryAssets = path.join(webRoot, "public", "repository-assets");
await rm(repositoryAssets, { recursive: true, force: true });

const tsvFieldOutput = path.join(
  repositoryAssets,
  "tsv_axisymmetric_field",
);
const tsvFieldSource = path.join(
  repositoryRoot,
  "examples",
  "tsv_axisymmetric_field",
  "retained",
);
await mkdir(tsvFieldOutput, { recursive: true });
for (const name of [
  "field.json",
  "summary.json",
  "contour.svg",
  "load-sweep.webm",
  "visual-evidence.json",
]) {
  await copyFile(path.join(tsvFieldSource, name), path.join(tsvFieldOutput, name));
}

const legalOutput = path.join(webRoot, "public", "legal");
await mkdir(legalOutput, { recursive: true });
for (const [source, target] of [
  ["LICENSE", "LICENSE"],
  ["LICENSES/CC-BY-4.0.txt", "CC-BY-4.0.txt"],
  ["NOTICE", "NOTICE"],
  ["THIRD_PARTY.md", "THIRD_PARTY.md"],
  ["docs/LICENSE.md", "LICENSE-SCOPE.md"],
]) {
  await copyFile(path.join(repositoryRoot, source), path.join(legalOutput, target));
}

console.log(
  "prepared one solver-field evidence bundle and five public legal records",
);
