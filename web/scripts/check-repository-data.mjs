import { readFile, readdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(webRoot, "..");

function fail(message) {
  throw new Error(`repository-data check failed: ${message}`);
}

async function readJson(filePath) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    fail(`cannot parse ${path.relative(repositoryRoot, filePath)}: ${error.message}`);
  }
}

function repositoryPath(relativePath) {
  if (
    typeof relativePath !== "string" ||
    relativePath.length === 0 ||
    path.isAbsolute(relativePath) ||
    relativePath.split(/[\\/]/).includes("..")
  ) {
    fail(`unsafe repository path: ${String(relativePath)}`);
  }
  return path.resolve(repositoryRoot, relativePath);
}

async function requireFile(relativePath) {
  const resolved = repositoryPath(relativePath);
  let info;
  try {
    info = await stat(resolved);
  } catch {
    fail(`linked source does not exist: ${relativePath}`);
  }
  if (!info.isFile()) fail(`linked source is not a file: ${relativePath}`);
  return resolved;
}

async function sha256(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function equal(actual, expected, label) {
  if (actual !== expected) {
    fail(`${label}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`);
  }
}

function close(actual, expected, label, tolerance = 1e-12) {
  if (
    typeof actual !== "number" ||
    !Number.isFinite(actual) ||
    Math.abs(actual - expected) > tolerance
  ) {
    fail(`${label}: expected ${expected}, received ${String(actual)}`);
  }
}

function metricValue(record, metricPath) {
  const metric = record.metrics?.find((candidate) => candidate.path === metricPath);
  if (!metric) fail(`missing retained metric ${metricPath}`);
  return metric.value;
}

async function collectTextFiles(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (["node_modules", "dist", "repository-assets"].includes(entry.name)) continue;
    const child = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      result.push(...(await collectTextFiles(child)));
    } else if (
      /\.(?:css|html|json|md|mjs|svg|ts|tsx|txt|ya?ml)$/.test(entry.name) ||
      entry.name.startsWith(".env")
    ) {
      result.push(child);
    }
  }
  return result;
}

const site = await readJson(path.join(webRoot, "site-data.json"));
equal(site.schemaVersion, 1, "site-data schemaVersion");
equal(site.recordDate, "2026-08-02", "public-record date");
equal(site.repository.url, "https://github.com/tengzhang48/CoupFE-EDA", "repository URL");
equal(site.repository.branch, "main", "repository branch");
equal(site.workflows.length, 5, "guided workflow count");

const expectedWorkflowIds = [
  "solder_plane_cycle",
  "etv_partitioned_cycle",
  "solder_3d_cycle",
  "design_linked_solder_screening",
  "tsv_device_screening",
];
equal(
  site.workflows.map((workflow) => workflow.id).join(","),
  expectedWorkflowIds.join(","),
  "guided workflow order",
);
for (const workflow of site.workflows) {
  await requireFile(workflow.readmePath);
  await requireFile(workflow.runnerPath);
  await requireFile(workflow.resultPath);
  if (!workflow.boundary || workflow.boundary.length < 40) {
    fail(`workflow ${workflow.id} does not expose a qualification boundary`);
  }
}
const workflows = Object.fromEntries(
  site.workflows.map((workflow) => [workflow.id, workflow]),
);

const plane = await readJson(
  await requireFile("examples/solder_plane_cycle/expected_results.json"),
);
close(metricValue(plane, "result.dW_last_MPa"), 0.33188439070681297, "plane-cycle energy");
equal(metricValue(plane, "result.element_count"), 6, "plane-cycle element count");
equal(
  workflows.solder_plane_cycle.result,
  `${metricValue(plane, "result.dW_last_MPa").toFixed(6)} MPa cycle dW observable`,
  "plane-cycle displayed result",
);
equal(
  workflows.solder_plane_cycle.detail,
  `Increment-summed mean inelastic energy density · ${metricValue(plane, "result.element_count")} Quad4 elements`,
  "plane-cycle displayed detail",
);
equal(workflows.solder_plane_cycle.command, "python examples/solder_plane_cycle/run.py --check", "plane-cycle command");
equal(workflows.solder_plane_cycle.tier, "NumPy / SciPy / CoupFE", "plane-cycle tier");

const etv = await readJson(
  await requireFile("examples/etv_partitioned_cycle/expected_results.json"),
);
close(
  metricValue(etv, "results.fast_cycle.relative_energy_difference_percent"),
  -66.8476348734628,
  "ETV fast-cycle energy sensitivity",
);
equal(
  workflows.etv_partitioned_cycle.result,
  `−${Math.abs(metricValue(etv, "results.fast_cycle.relative_energy_difference_percent")).toFixed(2)}% fast-cycle energy sensitivity`,
  "ETV displayed result",
);
equal(
  workflows.etv_partitioned_cycle.detail,
  `${metricValue(etv, "results.fast_cycle.lumped_transient.temperature_C_max").toFixed(2)} °C transient peak · ${metricValue(etv, "results.fast_cycle.quasisteady.temperature_C_max").toFixed(2)} °C quasisteady peak`,
  "ETV displayed detail",
);
equal(workflows.etv_partitioned_cycle.command, "python examples/etv_partitioned_cycle/run.py --check", "ETV command");
equal(workflows.etv_partitioned_cycle.tier, "NumPy / SciPy / CoupFE", "ETV tier");
close(
  metricValue(etv, "results.fast_cycle.lumped_transient.temperature_C_max"),
  98.60146223882845,
  "ETV transient peak temperature",
);
close(
  metricValue(etv, "results.fast_cycle.quasisteady.temperature_C_max"),
  144.93974955858192,
  "ETV quasisteady peak temperature",
);

const solder3d = await readJson(
  await requireFile("examples/solder_3d_cycle/expected_results.json"),
);
close(solder3d.expected.results.dW_peak_MPa, 0.389021354837, "3-D peak dissipation");
close(solder3d.expected.results.dW_mean_MPa, 0.34336417811, "3-D mean dissipation");
equal(solder3d.expected.configuration.n_elements, 18, "3-D element count");
equal(
  workflows.solder_3d_cycle.result,
  `${solder3d.expected.results.dW_peak_MPa.toFixed(6)} MPa peak dissipation`,
  "3-D displayed result",
);
equal(
  workflows.solder_3d_cycle.detail,
  `${solder3d.expected.results.dW_mean_MPa.toFixed(6)} MPa mean · peak/mean ${solder3d.expected.results.peak_to_mean.toFixed(5)}`,
  "3-D displayed detail",
);
equal(workflows.solder_3d_cycle.command, "python examples/solder_3d_cycle/run.py --check", "3-D command");
equal(workflows.solder_3d_cycle.tier, "NumPy / SciPy / CoupFE", "3-D tier");

const designLinked = await readJson(
  await requireFile("examples/design_linked_solder_screening/expected_results.json"),
);
close(
  designLinked.expected.results.Syed_calibration_screen_cycles,
  47273.1000783,
  "design-linked calibration screen",
);
equal(
  designLinked.expected.selected_design_object.joint_id,
  "SYNTH_J00",
  "design-linked selected joint",
);
equal(
  workflows.design_linked_solder_screening.result,
  `${Math.round(designLinked.expected.results.Syed_calibration_screen_cycles).toLocaleString("en-US")}-cycle calibration screen`,
  "design-linked displayed result",
);
equal(
  workflows.design_linked_solder_screening.detail,
  `${designLinked.expected.selected_design_object.joint_id} retained · ${designLinked.expected.selected_design_object.L_D_um.toFixed(4)} µm DNP`,
  "design-linked displayed detail",
);
equal(workflows.design_linked_solder_screening.command, "python examples/design_linked_solder_screening/run.py --check", "design-linked command");
equal(workflows.design_linked_solder_screening.tier, "NumPy / SciPy / CoupFE", "design-linked tier");

const expectedTsv = await readJson(await requireFile(site.tsvScreening.expectedPath));
const tsvCase = await readJson(
  await requireFile("examples/tsv_00_device_screening/case.json"),
);
close(site.tsvScreening.threshold, tsvCase.koz_threshold, "TSV displayed threshold");
equal(site.tsvScreening.nDevices, expectedTsv.n_devices, "TSV device count");
equal(
  site.tsvScreening.baselineViolations,
  expectedTsv.baseline_violations,
  "TSV baseline violations",
);
equal(
  site.tsvScreening.optimizedViolations,
  expectedTsv.optimized_violations,
  "TSV optimized violations",
);
close(
  site.tsvScreening.baselinePeakAbsMobilityProxy,
  expectedTsv.baseline_peak_abs_mobility_change,
  "TSV baseline peak proxy",
);
close(
  site.tsvScreening.optimizedPeakAbsMobilityProxy,
  expectedTsv.optimized_peak_abs_mobility_change,
  "TSV optimized peak proxy",
);
equal(site.tsvScreening.releaseValidation, false, "TSV release-validation flag");
equal(
  workflows.tsv_device_screening.result,
  `${expectedTsv.baseline_violations} → ${expectedTsv.optimized_violations} threshold violations`,
  "TSV displayed result",
);
equal(
  workflows.tsv_device_screening.detail,
  `${expectedTsv.n_devices} synthetic devices · ${tsvCase.koz_threshold * 100}% screening threshold`,
  "TSV displayed detail",
);
equal(workflows.tsv_device_screening.command, "python examples/tsv_00_device_screening/run.py --output-dir /tmp/tsv_device_preview", "TSV command");
equal(workflows.tsv_device_screening.tier, "NumPy / CoupFE-EDA analytic path", "TSV tier");

for (const asset of [
  site.tsvScreening.figureAsset,
  site.tsvScreening.evidenceAsset,
  site.tsvScreening.csvAsset,
]) {
  await requireFile(`web/public/${asset}`);
}
const publicEvidence = await readJson(
  repositoryPath(`web/public/${site.tsvScreening.evidenceAsset}`),
);
equal(publicEvidence.release_validation, false, "public TSV release-validation flag");
equal(
  publicEvidence.claim_boundary,
  site.tsvScreening.claimBoundary,
  "public TSV claim boundary",
);
equal(publicEvidence.n_devices, expectedTsv.n_devices, "public TSV device count");
equal(
  publicEvidence.baseline_violations,
  expectedTsv.baseline_violations,
  "public TSV baseline violations",
);
equal(
  publicEvidence.optimized_violations,
  expectedTsv.optimized_violations,
  "public TSV optimized violations",
);
close(
  publicEvidence.baseline_peak_abs_mobility_change,
  expectedTsv.baseline_peak_abs_mobility_change,
  "public TSV baseline peak proxy",
);
close(
  publicEvidence.optimized_peak_abs_mobility_change,
  expectedTsv.optimized_peak_abs_mobility_change,
  "public TSV optimized peak proxy",
);
const publicSvg = await readFile(
  repositoryPath(`web/public/${site.tsvScreening.figureAsset}`),
  "utf8",
);
if (!publicSvg.includes("Synthetic TSV-to-device") || !publicSvg.includes("demonstration")) {
  fail("public TSV SVG is not visibly labeled as a synthetic demonstration");
}

for (const source of [
  site.scaling.readmePath,
  site.scaling.summaryPath,
  site.scaling.tablePath,
  site.scaling.manifestPath,
]) {
  await requireFile(source);
}
const scalingSummary = await readJson(repositoryPath(site.scaling.summaryPath));
equal(scalingSummary.status, "complete", "scaling status");
equal(scalingSummary.configuration.expected_ndof, site.scaling.ndof, "scaling DOF");
equal(
  scalingSummary.configuration.repeats_per_rank,
  site.scaling.repeatsPerRank,
  "scaling repeats",
);
equal(scalingSummary.aggregate.length, site.scaling.ranks.length, "scaling rank rows");
scalingSummary.aggregate.forEach((row, index) => {
  equal(row.ranks, site.scaling.ranks[index], `scaling rank row ${index}`);
  close(
    row.wall_seconds.median,
    site.scaling.medianSeconds[index],
    `scaling median row ${index}`,
  );
  close(
    row.speedup_from_smallest_rank_median,
    site.scaling.speedup[index],
    `scaling speedup row ${index}`,
  );
  equal(
    row.last_ksp_iterations.maximum,
    site.scaling.iterations[index],
    `scaling iteration row ${index}`,
  );
});

for (const figure of site.figures) {
  await requireFile(figure.sourcePath);
  if (!/^[A-Za-z0-9._-]+\.png$/.test(figure.assetName)) {
    fail(`unsafe generated figure asset name: ${figure.assetName}`);
  }
}
for (const notice of [
  "LICENSE",
  "LICENSES/CC-BY-4.0.txt",
  "NOTICE",
  "THIRD_PARTY.md",
  "docs/LICENSE.md",
]) {
  await requireFile(notice);
}

await requireFile(site.scorecard.sourcePath);
await requireFile(site.scorecard.evidenceGuidePath);
const scorecard = await readJson(repositoryPath(site.scorecard.sourcePath));
equal(scorecard.record_date, site.recordDate, "scorecard record date");
for (const [status, label] of Object.entries(site.scorecard.statusLabels)) {
  equal(label, scorecard.public_status_labels[status], `roadmap public label ${status}`);
}
equal(
  site.scorecard.stages.length,
  scorecard.roadmap_stages.length,
  "roadmap stage count",
);
for (const [index, displayed] of site.scorecard.stages.entries()) {
  const source = scorecard.roadmap_stages[index];
  equal(displayed.id, source.id, `roadmap stage ${index} ID`);
  equal(displayed.title, source.title, `roadmap stage ${displayed.id} title`);
  equal(displayed.goal, source.goal, `roadmap stage ${displayed.id} goal`);
  equal(
    displayed.categoryIds.join(","),
    source.categories.join(","),
    `roadmap stage ${displayed.id} categories`,
  );
}
equal(
  site.scorecard.categories.length,
  Object.keys(scorecard.categories).length,
  "scorecard category count",
);
for (const displayed of site.scorecard.categories) {
  const source = scorecard.categories[displayed.id];
  if (!source) fail(`scorecard category is absent: ${displayed.id}`);
  equal(displayed.status, source.status, `scorecard status ${displayed.id}`);
  equal(displayed.reason, source.blocking_reason, `scorecard reason ${displayed.id}`);
}
equal(
  site.scorecard.stages.flatMap((stage) => stage.categoryIds).sort().join(","),
  Object.keys(scorecard.categories).sort().join(","),
  "roadmap category coverage",
);

const connected = await readJson(
  path.join(webRoot, "contracts", "connected-project-snapshot.json"),
);
equal(connected.schemaVersion, 1, "connected snapshot schema");
equal(connected.mode, "connected", "connected snapshot mode");
equal(connected.models.length, 0, "connected snapshot fictional-model count");
equal(connected.runs.length, 0, "connected snapshot initial-run count");
equal(connected.approvedWorkflows.length, 1, "connected approved-workflow count");
const approved = connected.approvedWorkflows[0];
equal(approved.id, "tsv_device_screening", "approved workflow ID");
equal(approved.executorKey, "tsv.device-screening.v1", "approved executor key");
equal(approved.releaseValidation, false, "approved workflow release-validation flag");
equal(approved.claimBoundary, site.tsvScreening.claimBoundary, "approved workflow boundary");
await requireFile(approved.driverPath);

const retainedArtifacts = await readJson(
  path.join(webRoot, "contracts", "retained-tsv-artifacts.json"),
);
equal(retainedArtifacts.schemaVersion, 1, "retained TSV artifact schema");
equal(retainedArtifacts.releaseValidation, false, "retained TSV artifact validation flag");
equal(
  retainedArtifacts.generatedBy,
  site.tsvScreening.readmePath.replace("README.md", "run.py"),
  "retained TSV artifact generator",
);
equal(retainedArtifacts.artifacts.length, 3, "retained TSV artifact count");
const expectedArtifactNames = [
  "evidence.json",
  "device_screening.svg",
  "device_screening.csv",
];
equal(
  retainedArtifacts.artifacts.map((artifact) => artifact.name).join(","),
  expectedArtifactNames.join(","),
  "retained TSV artifact order",
);
for (const artifact of retainedArtifacts.artifacts) {
  equal(
    artifact.uri,
    `generated/tsv_device_screening/${artifact.name}`,
    `retained TSV URI ${artifact.name}`,
  );
  const filePath = repositoryPath(`web/public/${artifact.uri}`);
  await requireFile(`web/public/${artifact.uri}`);
  equal(await sha256(filePath), artifact.sha256, `retained TSV SHA-256 ${artifact.name}`);
}

const forbiddenPrototypeMarkers = [
  ["8a3", "d91e"].join(""),
  ["thermal-validation", "-v2.json"].join(""),
  ["mesh-study", "-04.json"].join(""),
  ["margin-validation", "-v1.json"].join(""),
  ["package-steady", "-v3"].join(""),
  ["tsv-materials", "-v2"].join(""),
];
for (const file of await collectTextFiles(webRoot)) {
  const text = await readFile(file, "utf8");
  for (const marker of forbiddenPrototypeMarkers) {
    if (text.includes(marker)) {
      fail(`obsolete fictional prototype marker ${JSON.stringify(marker)} remains in ${path.relative(webRoot, file)}`);
    }
  }
}

console.log(
  `repository-data check passed: ${site.workflows.length} workflows, ${site.figures.length} figures, ${site.scorecard.categories.length} scorecard categories`,
);
