import { copyFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "..");
const site = JSON.parse(await readFile(path.join(webRoot, "site-data.json"), "utf8"));
const output = path.join(webRoot, "public", "repository-assets", "validation-guide");
await mkdir(output, { recursive: true });

for (const figure of site.figures) {
  const source = path.resolve(repositoryRoot, figure.sourcePath);
  const target = path.join(output, figure.assetName);
  await copyFile(source, target);
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

console.log(`prepared ${site.figures.length} project-authored figures and five public legal records`);
