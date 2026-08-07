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

function finiteArray(value, expectedLength, label) {
  if (!Array.isArray(value) || value.length !== expectedLength) {
    fail(`${label}: expected ${expectedLength} values`);
  }
  value.forEach((item, index) => {
    if (typeof item !== "number" || !Number.isFinite(item)) {
      fail(`${label}[${index}] is not finite`);
    }
  });
  return value;
}

function exactNumericArrays(left, right, label) {
  if (left.length !== right.length || left.some((value, index) => value !== right[index])) {
    fail(`${label}: retained arrays differ`);
  }
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
equal(site.recordDate, "2026-08-05", "public-record date");
equal(site.repository.url, "https://github.com/tengzhang48/CoupFE-EDA", "repository URL");
equal(site.repository.branch, "main", "repository branch");
equal(site.repository.version, "0.1.0", "project version");
equal(site.repository.releaseStatus, "Active alpha", "project release status");
equal(site.repository.author, "Teng Zhang", "project author");
equal(site.repository.issuesUrl, `${site.repository.url}/issues`, "project issues URL");
const pyproject = await readFile(await requireFile("pyproject.toml"), "utf8");
if (!pyproject.includes(`version = "${site.repository.version}"`)) {
  fail("displayed project version does not match pyproject.toml");
}
if (!pyproject.includes(`authors = [{ name = "${site.repository.author}" }]`)) {
  fail("displayed project author does not match pyproject.toml");
}
const webPackage = await readJson(path.join(webRoot, "package.json"));
const webPackageLock = await readJson(path.join(webRoot, "package-lock.json"));
equal(webPackage.version, site.repository.version, "frontend/project version alignment");
equal(webPackageLock.version, webPackage.version, "frontend lockfile version");
equal(webPackageLock.packages[""].version, webPackage.version, "frontend lockfile root version");
if (!site.projectBoundary || site.projectBoundary.length < 80) {
  fail("project-level claim boundary is missing or too short");
}
equal(site.process.steps.length, 6, "public process step count");
equal(
  site.process.steps.map((step) => step.id).join(","),
  "design_inputs,identity_provenance,analysis_representation,selected_analysis,retained_evidence,bounded_feedback",
  "public process step order",
);
if (!site.process.boundary || site.process.boundary.length < 80) {
  fail("public process boundary is missing or too short");
}
equal(site.workflows.length, 5, "guided workflow count");

const expectedWorkflowIds = [
  "tsv_axisymmetric_field",
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

equal(
  workflows.tsv_axisymmetric_field.result,
  `${site.tsvField.sigmaRrAtQueryMpa.toFixed(3)} MPa at r = ${site.tsvField.queryRadiusUm} µm`,
  "axisymmetric TSV displayed result",
);
equal(
  workflows.tsv_axisymmetric_field.detail,
  `${site.tsvField.relativeErrorPercent.toFixed(4)}% from Lamé · ${site.tsvField.elements.toLocaleString("en-US")} radial Line2 elements`,
  "axisymmetric TSV displayed detail",
);
equal(
  workflows.tsv_axisymmetric_field.command,
  "python examples/tsv_axisymmetric_field/run.py --output-dir /tmp/tsv_axisymmetric_field",
  "axisymmetric TSV command",
);
equal(workflows.tsv_axisymmetric_field.tier, "NumPy / SciPy / CoupFE", "axisymmetric TSV tier");
equal(workflows.tsv_axisymmetric_field.boundary, site.tsvField.claimBoundary, "axisymmetric TSV workflow boundary");

const retainedFieldDirectory = repositoryPath("examples/tsv_axisymmetric_field/retained");
const retainedFieldNames = (await readdir(retainedFieldDirectory, { withFileTypes: true }))
  .map((entry) => {
    if (!entry.isFile()) fail(`retained field bundle contains non-file entry: ${entry.name}`);
    return entry.name;
  })
  .sort();
const expectedRetainedFieldNames = [
  "contour.svg",
  "field.json",
  "load-sweep.webm",
  "summary.json",
  "visual-evidence.json",
];
equal(
  retainedFieldNames.join(","),
  expectedRetainedFieldNames.join(","),
  "retained field exact file inventory",
);

const fieldManifest = await readJson(
  await requireFile("examples/tsv_axisymmetric_field/retained/visual-evidence.json"),
);
const retainedField = await readJson(
  await requireFile("examples/tsv_axisymmetric_field/retained/field.json"),
);
const retainedFieldSummary = await readJson(
  await requireFile("examples/tsv_axisymmetric_field/retained/summary.json"),
);
equal(fieldManifest.schema_version, 1, "field manifest schema");
equal(fieldManifest.case?.id, site.tsvField.caseId, "field manifest case ID");
equal(fieldManifest.claim_boundary, site.tsvField.claimBoundary, "field manifest boundary");
if (!/^[0-9a-f]{40}$/.test(fieldManifest.revisions?.eda ?? "")) {
  fail("field manifest EDA revision is not a full lowercase Git SHA");
}
equal(fieldManifest.revisions?.core, site.tsvField.coreRevision, "field manifest Core revision");
equal(
  JSON.stringify(fieldManifest.command),
  JSON.stringify(["python", "examples/tsv_axisymmetric_field/run.py", "--output-dir", "<OUTPUT_DIR>"]),
  "field manifest command",
);
equal(fieldManifest.field?.topology, "Line2 axisymmetric plane strain", "field manifest topology");
equal(fieldManifest.field?.mesh?.node_count, site.tsvField.nodes, "field manifest nodes");
equal(fieldManifest.field?.mesh?.element_count, site.tsvField.elements, "field manifest elements");
equal(fieldManifest.field?.degree_of_freedom_count, site.tsvField.degreesOfFreedom, "field manifest DOF");
equal(fieldManifest.field?.load_steps?.length, site.tsvField.loadSteps, "field manifest load-step count");
equal(
  fieldManifest.field?.components?.map((component) => `${component.name}:${component.unit}:${component.location}`).join(","),
  "radial_displacement_nm:nm:node,sigma_rr_MPa:MPa:element_center,sigma_theta_MPa:MPa:element_center",
  "field manifest component grain",
);
const temporalMapping = fieldManifest.renderer?.configuration?.temporal_mapping;
equal(temporalMapping?.interpolation, "none", "field video temporal interpolation");
equal(temporalMapping?.is_transient, false, "field video transient flag");
equal(
  temporalMapping?.step_indices?.join(","),
  "0,1,2,3,4,5,6,7,8,7,6,5,4,3,2,1",
  "field video actual-state sequence",
);
equal(fieldManifest.renderer?.configuration?.output?.width_px, 960, "field video width");
equal(fieldManifest.renderer?.configuration?.output?.height_px, 540, "field video height");
equal(fieldManifest.renderer?.configuration?.output?.codec, "libvpx-vp9", "field video codec");
equal(fieldManifest.renderer?.configuration?.output?.pixel_format, "yuv420p", "field video pixel format");
if (!/not (?:a )?transient/i.test(fieldManifest.renderer?.interpretation ?? "")) {
  fail("field video interpretation does not explicitly deny a transient simulation");
}

const expectedBoundArtifacts = new Map([
  ["field.json", "raw-field"],
  ["summary.json", "summary"],
  ["contour.svg", "image"],
  ["load-sweep.webm", "video"],
]);
equal(fieldManifest.artifacts?.length, expectedBoundArtifacts.size, "field manifest artifact count");
for (const [name, role] of expectedBoundArtifacts) {
  const records = fieldManifest.artifacts.filter((artifact) => artifact.path === name);
  equal(records.length, 1, `field manifest ${name} record count`);
  const record = records[0];
  equal(record.role, role, `field manifest ${name} role`);
  const artifactPath = await requireFile(`examples/tsv_axisymmetric_field/retained/${name}`);
  equal((await stat(artifactPath)).size, record.size_bytes, `field manifest ${name} size`);
  equal(await sha256(artifactPath), record.sha256, `field manifest ${name} SHA-256`);
}

equal(retainedField.schema_version, 1, "retained field schema");
equal(retainedField.case_id, site.tsvField.caseId, "retained field case ID");
equal(retainedField.claim_boundary, site.tsvField.claimBoundary, "retained field boundary");
equal(retainedField.topology?.type, "Line2", "retained field topology");
equal(retainedField.topology?.spatial_dimension, 1, "retained field dimension");
equal(retainedField.topology?.dof_per_node, 1, "retained field DOF per node");
close(retainedField.inputs?.diameter_um, site.tsvField.diameterUm, "retained field diameter");
close(retainedField.inputs?.delta_temperature_K, site.tsvField.deltaTemperatureK, "retained field final load");
close(retainedField.inputs?.outer_radius_um, site.tsvField.outerRadiusUm, "retained field outer radius");
equal(retainedField.inputs?.mesh_points_requested, site.tsvField.nodes, "retained field requested nodes");
equal(retainedField.inputs?.formulation, "axisymmetric_plane_strain", "retained field formulation");
equal(retainedField.inputs?.load, "uniform_thermal_eigenstrain", "retained field load type");
const fieldNodes = finiteArray(retainedField.mesh?.radius_nodes_um, site.tsvField.nodes, "retained field nodes");
const fieldCenters = finiteArray(retainedField.mesh?.element_centers_um, site.tsvField.elements, "retained field centers");
equal(retainedField.mesh?.connectivity?.length, site.tsvField.elements, "retained field connectivity count");
retainedField.mesh.connectivity.forEach((connection, index) => {
  if (!Array.isArray(connection) || connection.length !== 2 || connection[0] !== index || connection[1] !== index + 1) {
    fail(`retained field connectivity[${index}] is not the ordered Line2 chain`);
  }
});
equal(retainedField.mesh?.region_by_element?.length, site.tsvField.elements, "retained field region count");
if (retainedField.mesh.region_by_element.some((region) => region !== "copper" && region !== "silicon")) {
  fail("retained field contains a region outside the reviewed copper/silicon case");
}
if (!fieldNodes.every((radius, index) => index === 0 || radius > fieldNodes[index - 1])) {
  fail("retained field nodes are not strictly increasing");
}
if (!fieldCenters.every((radius, index) => index === 0 || radius > fieldCenters[index - 1])) {
  fail("retained field element centers are not strictly increasing");
}
const expectedLoads = [0, -50, -100, -150, -200, -250, -300, -350, -400];
equal(retainedField.load_sweep?.sweep_kind, "independent_static_prescribed_load_cases", "retained field sweep kind");
equal(retainedField.load_sweep?.is_transient, false, "retained field transient flag");
equal(retainedField.load_sweep?.delta_temperature_K?.join(","), expectedLoads.join(","), "retained field load values");
equal(retainedField.load_sweep?.steps?.length, expectedLoads.length, "retained field actual solve count");
for (const [index, step] of retainedField.load_sweep.steps.entries()) {
  equal(step.step_index, index, `retained field step ${index} index`);
  close(step.delta_temperature_K, expectedLoads[index], `retained field step ${index} load`);
  equal(step.solve_kind, "independent_static_coupfe_solve", `retained field step ${index} solve kind`);
  equal(step.is_transient, false, `retained field step ${index} transient flag`);
  equal(step.solver?.converged, true, `retained field step ${index} convergence`);
  equal(step.comparison?.passed, true, `retained field step ${index} comparison`);
  finiteArray(step.field?.radial_displacement_nm, site.tsvField.nodes, `retained field step ${index} displacement`);
  finiteArray(step.field?.sigma_rr_MPa, site.tsvField.elements, `retained field step ${index} radial stress`);
  finiteArray(step.field?.sigma_theta_MPa, site.tsvField.elements, `retained field step ${index} hoop stress`);
}
const finalSolvedField = retainedField.load_sweep.steps.at(-1).field;
const finalDisplacement = finiteArray(retainedField.final_field?.radial_displacement_nm, site.tsvField.nodes, "retained final displacement");
const finalRadialStress = finiteArray(retainedField.final_field?.sigma_rr_MPa, site.tsvField.elements, "retained final radial stress");
const finalHoopStress = finiteArray(retainedField.final_field?.sigma_theta_MPa, site.tsvField.elements, "retained final hoop stress");
exactNumericArrays(finalDisplacement, finalSolvedField.radial_displacement_nm, "final displacement identity");
exactNumericArrays(finalRadialStress, finalSolvedField.sigma_rr_MPa, "final radial-stress identity");
exactNumericArrays(finalHoopStress, finalSolvedField.sigma_theta_MPa, "final hoop-stress identity");

equal(retainedFieldSummary.schema_version, 1, "retained field summary schema");
equal(retainedFieldSummary.case_id, site.tsvField.caseId, "retained field summary case ID");
equal(retainedFieldSummary.claim_boundary, site.tsvField.claimBoundary, "retained field summary boundary");
equal(retainedFieldSummary.provenance?.eda_revision, fieldManifest.revisions.eda, "summary/manifest EDA revision");
equal(retainedFieldSummary.provenance?.core_revision, fieldManifest.revisions.core, "summary/manifest Core revision");
equal(retainedFieldSummary.mesh?.nodes, site.tsvField.nodes, "retained summary nodes");
equal(retainedFieldSummary.mesh?.elements, site.tsvField.elements, "retained summary elements");
equal(retainedFieldSummary.mesh?.degrees_of_freedom, site.tsvField.degreesOfFreedom, "retained summary DOF");
close(retainedFieldSummary.results?.sigma_rr_at_20um_MPa, site.tsvField.sigmaRrAtQueryMpa, "retained summary radial stress");
close(retainedFieldSummary.comparison?.lame_sigma_rr_MPa, site.tsvField.lameAtQueryMpa, "retained summary Lamé stress");
close(retainedFieldSummary.comparison?.relative_error * 100, site.tsvField.relativeErrorPercent, "retained summary Lamé relative error percent");
equal(retainedFieldSummary.comparison?.passed, true, "retained summary comparison pass");
equal(retainedFieldSummary.solver?.newton_iterations, site.tsvField.newtonIterations, "retained summary Newton iterations");
equal(retainedFieldSummary.load_sweep?.steps, site.tsvField.loadSteps, "retained summary load-step count");
equal(retainedFieldSummary.load_sweep?.is_transient, false, "retained summary transient flag");
for (const [key, expected] of Object.entries({
  fieldAsset: "repository-assets/tsv_axisymmetric_field/field.json",
  summaryAsset: "repository-assets/tsv_axisymmetric_field/summary.json",
  contourAsset: "repository-assets/tsv_axisymmetric_field/contour.svg",
  videoAsset: "repository-assets/tsv_axisymmetric_field/load-sweep.webm",
  manifestAsset: "repository-assets/tsv_axisymmetric_field/visual-evidence.json",
})) {
  equal(site.tsvField[key], expected, `public field asset ${key}`);
}

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
  `−${Math.abs(metricValue(etv, "results.fast_cycle.relative_energy_difference_percent")).toFixed(2)}% energy-density change (lumped vs quasisteady)`,
  "ETV displayed result",
);
equal(
  workflows.etv_partitioned_cycle.detail,
  `${metricValue(etv, "results.fast_cycle.lumped_transient.temperature_C_max").toFixed(2)} °C transient peak · ${metricValue(etv, "results.fast_cycle.quasisteady.temperature_C_max").toFixed(2)} °C quasisteady peak`,
  "ETV displayed detail",
);
equal(workflows.etv_partitioned_cycle.command, "python examples/etv_partitioned_cycle/run.py --check", "ETV command");
equal(workflows.etv_partitioned_cycle.tier, "NumPy / SciPy / CoupFE", "ETV tier");
equal(site.etvComparison.caseId, "etv_partitioned_cycle", "featured ETV case ID");
equal(site.etvComparison.mediaId, "etv_partitioned_comparison", "featured ETV media ID");
equal(
  etv.configuration,
  "2x2 Quad4, two -40 to 125 to -40 C cycles, eight increments per cycle; 1600 s and 1 s periods",
  "ETV retained configuration",
);
equal(site.etvComparison.mesh, "2 × 2 Quad4 plane strain", "featured ETV mesh");
equal(site.etvComparison.cycles, 2, "featured ETV cycle count");
equal(site.etvComparison.incrementsPerCycle, 8, "featured ETV increments per cycle");
equal(site.etvComparison.command, workflows.etv_partitioned_cycle.command, "featured ETV command");
equal(site.etvComparison.boundary, workflows.etv_partitioned_cycle.boundary, "featured ETV boundary");
equal(site.etvComparison.oraclePassed, true, "featured ETV oracle status");
close(site.etvComparison.temperatureCycleC.low, -40.0, "featured ETV low temperature");
close(site.etvComparison.temperatureCycleC.high, 125.0, "featured ETV high temperature");
equal(
  site.etvComparison.relativeDifferenceDefinition,
  "100 × (lumped transient − quasisteady) / quasisteady",
  "featured ETV relative-difference definition",
);
equal(
  site.etvComparison.energyQuantity,
  "last-cycle accumulated inelastic energy density",
  "featured ETV quantity",
);
equal(site.etvComparison.energyUnit, "MPa", "featured ETV energy-density unit");
equal(site.etvComparison.slow.periodSeconds, 1600.0, "featured ETV slow period");
equal(site.etvComparison.fast.periodSeconds, 1.0, "featured ETV fast period");
for (const [displayPath, oraclePath] of [
  ["slow.quasisteadyEnergyMPa", "results.slow_cycle.quasisteady.dW_last_MPa"],
  ["slow.lumpedTransientEnergyMPa", "results.slow_cycle.lumped_transient.dW_last_MPa"],
  ["slow.relativeDifferencePercent", "results.slow_cycle.relative_energy_difference_percent"],
  ["fast.quasisteadyEnergyMPa", "results.fast_cycle.quasisteady.dW_last_MPa"],
  ["fast.lumpedTransientEnergyMPa", "results.fast_cycle.lumped_transient.dW_last_MPa"],
  ["fast.relativeDifferencePercent", "results.fast_cycle.relative_energy_difference_percent"],
  ["fast.quasisteadyPeakTemperatureC", "results.fast_cycle.quasisteady.temperature_C_max"],
  ["fast.lumpedTransientPeakTemperatureC", "results.fast_cycle.lumped_transient.temperature_C_max"],
  ["fast.quasisteadyPeakTopDisplacementUm", "results.fast_cycle.quasisteady.last_cycle.peak_top_edge_displacement_x_m"],
  ["fast.lumpedTransientPeakTopDisplacementUm", "results.fast_cycle.lumped_transient.last_cycle.peak_top_edge_displacement_x_m"],
]) {
  const displayed = displayPath.split(".").reduce((record, key) => record[key], site.etvComparison);
  const oracleValue = metricValue(etv, oraclePath);
  close(
    displayed,
    displayPath.endsWith("DisplacementUm") ? oracleValue * 1e6 : oracleValue,
    `featured ETV ${displayPath}`,
  );
}
const etvMedia = site.simulationMedia.find(
  (media) => media.id === site.etvComparison.mediaId,
);
if (!etvMedia) fail("featured ETV media record is missing");
equal(
  site.etvComparison.recordAsset,
  "generated/simulation-media/etv-partitioned-record.json",
  "featured ETV retained-state asset",
);
equal(
  site.etvComparison.mobileAsset,
  "generated/simulation-media/etv-partitioned-comparison-mobile.svg",
  "featured ETV portrait asset",
);
const etvRecord = await readJson(
  await requireFile(`web/public/${site.etvComparison.recordAsset}`),
);
equal(etvRecord.schema_version, 2, "featured ETV retained-state schema");
equal(etvRecord.verification?.passed, true, "featured ETV retained-state verification");
equal(etvRecord.inputs?.mesh?.nodes, site.etvComparison.setup.nodes, "featured ETV retained node count");
equal(etvRecord.inputs?.mesh?.elements, site.etvComparison.setup.elements, "featured ETV retained element count");
equal(site.etvComparison.setup.displacementDofs, 2 * etvRecord.inputs.mesh.nodes, "featured ETV displacement DOFs");
close(site.etvComparison.setup.widthMm, etvRecord.inputs.geometry_mm.width, "featured ETV width");
close(site.etvComparison.setup.heightMm, etvRecord.inputs.geometry_mm.height, "featured ETV height");
close(site.etvComparison.setup.elasticModulusMPa, etvRecord.inputs.representative_elastic_modulus_MPa, "featured ETV elastic modulus");
close(site.etvComparison.setup.poissonRatio, etvRecord.inputs.representative_poisson_ratio, "featured ETV Poisson ratio");
close(site.etvComparison.setup.temperatureReferenceC, 42.5, "featured ETV reference temperature");
close(site.etvComparison.setup.cteMismatchPerK, etvRecord.inputs.cte_mismatch_per_K, "featured ETV CTE mismatch");
close(site.etvComparison.setup.distanceToNeutralPointOverHeight, etvRecord.inputs.distance_to_neutral_point_over_height, "featured ETV L_D / h");
close(site.etvComparison.setup.jouleDensityWPerM3, etvRecord.inputs.dandu_context.derived_joule_density_W_per_m3, "featured ETV Joule density", 1e-3);
close(site.etvComparison.setup.thermalConductanceDensityWPerM3K, etvRecord.inputs.thermal_conductance_density_W_per_m3K, "featured ETV thermal conductance density");
close(site.etvComparison.setup.volumetricHeatCapacityJPerM3K, etvRecord.inputs.volumetric_heat_capacity_J_per_m3K, "featured ETV heat capacity");
close(site.etvComparison.setup.inelasticHeatFraction, etvRecord.inputs.inelastic_heat_fraction, "featured ETV inelastic heat fraction");
for (const model of ["quasisteady", "lumped_transient"]) {
  const retained = etvRecord.results.fast_cycle[model].last_cycle;
  finiteArray(retained.phase_fraction, 9, `featured ETV ${model} phase`);
  finiteArray(retained.chamber_temperature_C, 9, `featured ETV ${model} chamber temperature`);
  finiteArray(retained.local_temperature_C, 9, `featured ETV ${model} local temperature`);
  finiteArray(retained.peak_displacement_m, 18, `featured ETV ${model} peak displacement`);
  equal(retained.displacement_m.length, 9, `featured ETV ${model} retained displacement states`);
  retained.displacement_m.forEach((state, index) => finiteArray(state, 18, `featured ETV ${model} displacement state ${index}`));
}
const etvSvg = await readFile(
  await requireFile(`web/public/${etvMedia.asset}`),
  "utf8",
);
const etvMobileSvg = await readFile(
  await requireFile(`web/public/${site.etvComparison.mobileAsset}`),
  "utf8",
);
for (const requiredText of [
  "One-second solder-cycle response",
  "Computed local-temperature path",
  "cycle phase",
  "Peak-temperature mechanics states",
  `${site.etvComparison.fast.quasisteadyPeakTemperatureC.toFixed(2)} °C`,
  `${site.etvComparison.fast.lumpedTransientPeakTemperatureC.toFixed(2)} °C`,
  site.etvComparison.fast.quasisteadyEnergyMPa.toFixed(6),
  site.etvComparison.fast.lumpedTransientEnergyMPa.toFixed(6),
  `-${Math.abs(site.etvComparison.fast.relativeDifferencePercent).toFixed(2)}%`,
  "Energy-density change",
  "lumped relative to quasisteady",
  "prescribed uₓ",
  "deformation ×10",
  "not a spatial thermal field",
]) {
  if (!etvSvg.includes(requiredText)) {
    fail(`featured ETV SVG is missing checked content: ${requiredText}`);
  }
}
for (const requiredText of [
  "One-second partitioned solder-cycle response, portrait layout",
  "Computed local-temperature path",
  "cycle phase",
  "Peak-temperature mechanics states",
  site.etvComparison.fast.quasisteadyEnergyMPa.toFixed(6),
  site.etvComparison.fast.lumpedTransientEnergyMPa.toFixed(6),
  `-${Math.abs(site.etvComparison.fast.relativeDifferencePercent).toFixed(2)}%`,
  "Energy-density change",
  "lumped relative to quasisteady",
  "prescribed uₓ",
  "deformation ×10",
  "not a spatial thermal field",
]) {
  if (!etvMobileSvg.includes(requiredText)) {
    fail(`featured ETV portrait SVG is missing checked content: ${requiredText}`);
  }
}
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
equal(solder3d.expected.solver_evidence.all_increments_accepted, true, "3-D accepted increments");
close(site.solderComparison.baselineMeanDissipationMPa, solder3d.expected.results.dW_mean_MPa, "solder comparison mean dissipation");
close(site.solderComparison.baselinePeakToMean, solder3d.expected.results.peak_to_mean, "solder comparison peak/mean");
equal(site.solderComparison.elements, solder3d.expected.configuration.n_elements, "solder comparison element count");
equal(site.solderComparison.acceptedIncrements, solder3d.expected.configuration.increments_per_cycle, "solder comparison accepted increments");
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
equal(site.solderComparison.baselineMediaId, "solder_3d_dissipation", "solder comparison baseline ID");
equal(site.solderComparison.designLinkedMediaId, "design_linked_solder_screening", "solder comparison design-linked ID");
close(site.solderComparison.baselineLDOverH, solder3d.expected.configuration.L_D_over_h, "solder comparison baseline L_D/h");
close(site.solderComparison.designLinkedLDOverH, designLinked.expected.configuration.L_D_over_h, "solder comparison design-linked L_D/h");
close(site.solderComparison.baselineShearRange, solder3d.expected.results.engineering_shear_range, "solder comparison baseline shear range");
close(site.solderComparison.designLinkedShearRange, designLinked.expected.results.engineering_shear_range, "solder comparison design-linked shear range");
close(site.solderComparison.baselinePeakDissipationMPa, solder3d.expected.results.dW_peak_MPa, "solder comparison baseline peak dissipation");
close(site.solderComparison.designLinkedPeakDissipationMPa, designLinked.expected.results.dW_peak_MPa, "solder comparison design-linked peak dissipation");
equal(
  solder3d.expected.configuration.mesh_elements_xyz.join(","),
  designLinked.expected.configuration.mesh_elements_xyz.join(","),
  "solder comparison mesh alignment",
);
close(
  solder3d.expected.input_provenance.representative_elastic_modulus_MPa,
  designLinked.expected.input_provenance.representative_elastic_modulus_MPa,
  "solder comparison elastic-modulus alignment",
);
close(
  solder3d.expected.input_provenance.representative_poisson_ratio,
  designLinked.expected.input_provenance.representative_poisson_ratio,
  "solder comparison Poisson-ratio alignment",
);

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
if (
  !site.tsvScreening.displayBoundary.includes("project-authored synthetic sites") ||
  !site.tsvScreening.displayBoundary.includes("near-surface 3-D TSV stress field") ||
  !site.tsvScreening.displayBoundary.includes("signoff keep-out zone")
) {
  fail("public TSV display boundary omits required synthetic/3-D/signoff limits");
}
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

equal(site.simulationMedia.length, 4, "simulation-media figure count");
equal(
  site.simulationMedia.map((media) => media.id).join(","),
  "solder_3d_dissipation,design_linked_solder_screening,etv_partitioned_comparison,tsv_device_screening",
  "simulation-media figure order",
);
for (const media of site.simulationMedia) {
  if (!media.alt || media.alt.length < 60) {
    fail(`simulation media ${media.id} has an inadequate text alternative`);
  }
  if (!media.boundary || media.boundary.length < 80) {
    fail(`simulation media ${media.id} has an inadequate evidence boundary`);
  }
  await requireFile(`web/public/${media.asset}`);
  await requireFile(media.runnerPath);
  await requireFile(media.resultPath);
  await requireFile(media.evidencePath);
}
equal(
  site.simulationMedia.find((media) => media.id === site.etvComparison.mediaId)?.boundary,
  site.etvComparison.boundary,
  "featured ETV/media boundary",
);
equal(
  site.simulationMedia.find((media) => media.id === "tsv_device_screening")?.asset,
  site.tsvScreening.figureAsset,
  "simulation-media TSV asset",
);

const simulationMediaContract = await readJson(
  path.join(webRoot, "contracts", "simulation-media.json"),
);
equal(simulationMediaContract.schemaVersion, 3, "simulation-media contract schema");
equal(
  simulationMediaContract.generatedBy,
  "web/scripts/render-simulation-media.py",
  "simulation-media generator",
);
equal(
  simulationMediaContract.generatorSha256,
  await sha256(await requireFile(simulationMediaContract.generatedBy)),
  "simulation-media generator hash",
);
equal(
  simulationMediaContract.core?.revision,
  site.tsvField.coreRevision,
  "simulation-media Core revision",
);
equal(
  simulationMediaContract.core?.url,
  "https://github.com/tengzhang48/CoupFE.git",
  "simulation-media Core URL",
);
equal(simulationMediaContract.sources?.length, 3, "simulation-media source count");
equal(
  simulationMediaContract.sources.map((source) => source.caseId).join(","),
  "solder_3d_cycle,design_linked_solder_screening,etv_partitioned_cycle",
  "simulation-media source order",
);
for (const source of simulationMediaContract.sources) {
  equal(source.oraclePassed, true, `simulation-media oracle status ${source.caseId}`);
  const runnerPath = await requireFile(source.runner);
  const oraclePath = await requireFile(source.oracle);
  equal(await sha256(runnerPath), source.runnerSha256, `simulation-media runner hash ${source.caseId}`);
  equal(await sha256(oraclePath), source.oracleSha256, `simulation-media oracle hash ${source.caseId}`);
  if (!Array.isArray(source.dependencies) || source.dependencies.length === 0) {
    fail(`simulation-media source dependencies are missing for ${source.caseId}`);
  }
  for (const dependency of source.dependencies) {
    const dependencyPath = await requireFile(dependency.path);
    equal(
      await sha256(dependencyPath),
      dependency.sha256,
      `simulation-media dependency hash ${source.caseId}:${dependency.path}`,
    );
  }
}
const etvSourceContract = simulationMediaContract.sources.find(
  (source) => source.caseId === site.etvComparison.caseId,
);
equal(
  etvSourceContract?.dependencies.some(
    (dependency) => dependency.path === "eda_multiphysics/etv_fe.py",
  ),
  true,
  "featured ETV solver implementation hash",
);
equal(
  etvSourceContract?.oraclePassed,
  site.etvComparison.oraclePassed,
  "featured ETV/contract oracle status",
);
equal(simulationMediaContract.artifacts?.length, 5, "simulation-media artifact count");
equal(
  simulationMediaContract.artifacts.map((artifact) => artifact.name).join(","),
  "solder-3d-dissipation.svg,design-linked-solder-screening.svg,etv-partitioned-comparison.svg,etv-partitioned-comparison-mobile.svg,etv-partitioned-record.json",
  "simulation-media artifact order",
);
for (const artifact of simulationMediaContract.artifacts) {
  if (!/^[a-z0-9-]+\.(?:svg|json)$/.test(artifact.name)) {
    fail(`unsafe simulation-media artifact name: ${String(artifact.name)}`);
  }
  equal(
    artifact.mediaType,
    artifact.name.endsWith(".svg") ? "image/svg+xml" : "application/json",
    `simulation-media type ${artifact.name}`,
  );
  equal(
    artifact.uri,
    `generated/simulation-media/${artifact.name}`,
    `simulation-media URI ${artifact.name}`,
  );
  const assetPath = await requireFile(`web/public/${artifact.uri}`);
  equal(await sha256(assetPath), artifact.sha256, `simulation-media artifact hash ${artifact.name}`);
  if (artifact.name.endsWith(".svg")) {
    const accessibleSvg = await readFile(assetPath, "utf8");
    if (
      !accessibleSvg.includes('role="img"') ||
      !accessibleSvg.includes("<title id=\"figure-title\">") ||
      !accessibleSvg.includes("<desc id=\"figure-description\">")
    ) {
      fail(`simulation-media SVG lacks an accessible title/description: ${artifact.name}`);
    }
  } else {
    const retainedRecord = await readJson(assetPath);
    equal(retainedRecord.verification?.passed, true, `simulation-media JSON verification ${artifact.name}`);
  }
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
await requireFile(site.scorecard.roadmapPath);
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
equal(approved.id, "tsv_axisymmetric_field", "approved workflow ID");
equal(approved.executorKey, "tsv.axisymmetric-field.v1", "approved executor key");
equal(approved.releaseValidation, false, "approved workflow release-validation flag");
equal(approved.claimBoundary, site.tsvField.claimBoundary, "approved workflow boundary");
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
  `repository-data check passed: ${site.workflows.length} workflows, ${site.simulationMedia.length} simulation figures, ${site.scorecard.categories.length} scorecard categories`,
);
