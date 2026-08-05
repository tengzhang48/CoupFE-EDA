import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import siteData from "../site-data.json";
import type { CoupFEBackend } from "./backend/interface";
import { useWorkbench } from "./hooks/use-workbench";

const WORKFLOW_ID = "tsv_axisymmetric_field";
const EXPECTED_LOADS_K = [0, -50, -100, -150, -200, -250, -300, -350, -400] as const;
const VIEWBOX_SIZE = 500;
const FIELD_CENTER = VIEWBOX_SIZE / 2;
const FIELD_RADIUS = 214;
const NEAR_FIELD_RADIUS_UM = 60;
const PALETTE = ["#101b43", "#234b8f", "#227f9d", "#2aa889", "#78c679", "#d8d85f", "#f2b84b"];

interface SolverRecord {
  newton_iterations: number;
  final_relative_residual: number;
  residual_fraction_of_acceptance_limit: number;
  converged: boolean;
}

interface ComparisonRecord {
  query_radius_um: number;
  fe_sigma_rr_MPa: number;
  lame_sigma_rr_MPa: number;
  relative_error: number | null;
  passed: boolean;
}

interface FieldArrays {
  radial_displacement_nm: number[];
  sigma_rr_MPa: number[];
  sigma_theta_MPa: number[];
}

interface LoadStep {
  step_index: number;
  delta_temperature_K: number;
  solve_kind: string;
  is_transient: false;
  solver: SolverRecord;
  comparison: ComparisonRecord;
  field: FieldArrays;
}

export interface TsvFieldBundle {
  schema_version: 1;
  case_id: string;
  claim_boundary: string;
  units: Record<string, string>;
  inputs: {
    diameter_um: number;
    delta_temperature_K: number;
    outer_radius_um: number;
    mesh_points_requested: number;
  };
  topology: {
    type: "Line2";
    spatial_dimension: 1;
    dof_per_node: 1;
  };
  mesh: {
    radius_nodes_um: number[];
    element_centers_um: number[];
    connectivity: number[][];
    region_by_element: string[];
    region_element_indices: Record<string, number[]>;
    via_radius_um: number;
    outer_radius_um: number;
  };
  final_field: FieldArrays & { delta_temperature_K: number };
  solver: SolverRecord;
  comparison: ComparisonRecord;
  load_sweep: {
    sweep_kind: string;
    is_transient: false;
    description: string;
    delta_temperature_K: number[];
    steps: LoadStep[];
  };
}

interface AppProps {
  backend?: CoupFEBackend;
  projectId?: string;
  retainedFieldUrl: string;
  summaryUrl: string;
  manifestUrl: string;
  runnerUrl: string;
}

interface FieldEvidenceSource {
  fieldUrl: string;
  summaryUrl: string;
  manifestUrl: string;
  manifestLabel: string;
  coreRevision: string;
  label: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown, location: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${location} must be a finite number`);
  }
  return value;
}

function finiteArray(value: unknown, location: string, length: number): number[] {
  if (!Array.isArray(value) || value.length !== length) {
    throw new Error(`${location} must contain exactly ${length} values`);
  }
  return value.map((item, index) => finiteNumber(item, `${location}[${index}]`));
}

function solverRecord(value: unknown, location: string): SolverRecord {
  if (!isRecord(value)) throw new Error(`${location} must be an object`);
  const iterations = finiteNumber(value.newton_iterations, `${location}.newton_iterations`);
  const relativeResidual = finiteNumber(value.final_relative_residual, `${location}.final_relative_residual`);
  const acceptanceFraction = finiteNumber(
    value.residual_fraction_of_acceptance_limit,
    `${location}.residual_fraction_of_acceptance_limit`,
  );
  if (!Number.isInteger(iterations) || iterations < 1 || value.converged !== true) {
    throw new Error(`${location} must describe a converged CoupFE solve`);
  }
  if (relativeResidual < 0 || acceptanceFraction < 0 || acceptanceFraction >= 1) {
    throw new Error(`${location} residual evidence is outside its acceptance boundary`);
  }
  return {
    newton_iterations: iterations,
    final_relative_residual: relativeResidual,
    residual_fraction_of_acceptance_limit: acceptanceFraction,
    converged: true,
  };
}

function comparisonRecord(value: unknown, location: string): ComparisonRecord {
  if (!isRecord(value)) throw new Error(`${location} must be an object`);
  if (value.reference !== "published_Lame_equation") {
    throw new Error(`${location} does not identify the reviewed Lamé reference`);
  }
  const queryRadius = finiteNumber(value.query_radius_um, `${location}.query_radius_um`);
  const acceptanceThreshold = finiteNumber(value.acceptance_threshold, `${location}.acceptance_threshold`);
  const absoluteError = finiteNumber(value.absolute_error_MPa, `${location}.absolute_error_MPa`);
  const feStress = finiteNumber(value.fe_sigma_rr_MPa, `${location}.fe_sigma_rr_MPa`);
  const lameStress = finiteNumber(value.lame_sigma_rr_MPa, `${location}.lame_sigma_rr_MPa`);
  const relative = value.relative_error;
  const relativeNumber = relative === null
    ? null
    : finiteNumber(relative, `${location}.relative_error`);
  if (
    queryRadius !== siteData.tsvField.queryRadiusUm ||
    acceptanceThreshold !== 0.03 ||
    absoluteError < 0 ||
    (relativeNumber !== null && (relativeNumber < 0 || relativeNumber > acceptanceThreshold))
  ) {
    throw new Error(`${location} is outside the reviewed 20 µm / 3% comparison contract`);
  }
  const calculatedAbsoluteError = Math.abs(feStress - lameStress);
  if (Math.abs(absoluteError - calculatedAbsoluteError) > 1e-9 * Math.max(1, calculatedAbsoluteError)) {
    throw new Error(`${location} absolute error is inconsistent with its FE/Lamé values`);
  }
  if (lameStress === 0) {
    if (feStress !== 0 || relativeNumber !== null) {
      throw new Error(`${location} zero-load comparison is inconsistent`);
    }
  } else {
    const calculatedRelativeError = calculatedAbsoluteError / Math.abs(lameStress);
    if (relativeNumber === null || Math.abs(relativeNumber - calculatedRelativeError) > 1e-12) {
      throw new Error(`${location} relative error is inconsistent with its FE/Lamé values`);
    }
  }
  if (value.passed !== true) throw new Error(`${location} did not pass its declared comparison`);
  return {
    query_radius_um: queryRadius,
    fe_sigma_rr_MPa: feStress,
    lame_sigma_rr_MPa: lameStress,
    relative_error: relativeNumber,
    passed: true,
  };
}

function fieldArrays(value: unknown, location: string, nodes: number, elements: number): FieldArrays {
  if (!isRecord(value)) throw new Error(`${location} must be an object`);
  return {
    radial_displacement_nm: finiteArray(value.radial_displacement_nm, `${location}.radial_displacement_nm`, nodes),
    sigma_rr_MPa: finiteArray(value.sigma_rr_MPa, `${location}.sigma_rr_MPa`, elements),
    sigma_theta_MPa: finiteArray(value.sigma_theta_MPa, `${location}.sigma_theta_MPa`, elements),
  };
}

export function validateTsvFieldBundle(value: unknown): TsvFieldBundle {
  if (!isRecord(value) || value.schema_version !== 1) {
    throw new Error("field.json must use schema_version 1");
  }
  if (value.case_id !== siteData.tsvField.caseId) {
    throw new Error(`unexpected solver case: ${String(value.case_id)}`);
  }
  if (typeof value.claim_boundary !== "string" || value.claim_boundary !== siteData.tsvField.claimBoundary) {
    throw new Error("field.json claim boundary does not match the reviewed public boundary");
  }
  if (!isRecord(value.mesh) || !isRecord(value.topology) || !isRecord(value.inputs)) {
    throw new Error("field.json is missing mesh, topology, or input records");
  }
  if (
    value.inputs.diameter_um !== siteData.tsvField.diameterUm ||
    value.inputs.delta_temperature_K !== siteData.tsvField.deltaTemperatureK ||
    value.inputs.outer_radius_um !== siteData.tsvField.outerRadiusUm ||
    value.inputs.mesh_points_requested !== siteData.tsvField.nodes ||
    value.inputs.formulation !== "axisymmetric_plane_strain" ||
    value.inputs.load !== "uniform_thermal_eigenstrain"
  ) {
    throw new Error("field.json inputs do not match the fixed reviewed case");
  }
  if (
    !isRecord(value.units) ||
    value.units.radius !== "um" ||
    value.units.radial_displacement !== "nm" ||
    value.units.stress !== "MPa" ||
    value.units.temperature_change !== "K" ||
    value.units.residual_norm !== "N/m"
  ) {
    throw new Error("field.json units do not match the displayed µm/nm/MPa/K contract");
  }
  if (
    value.topology.type !== "Line2" ||
    value.topology.spatial_dimension !== 1 ||
    value.topology.dof_per_node !== 1
  ) {
    throw new Error("field.json does not describe the reviewed radial Line2 topology");
  }

  const radiusNodes = Array.isArray(value.mesh.radius_nodes_um) ? value.mesh.radius_nodes_um : [];
  const centers = Array.isArray(value.mesh.element_centers_um) ? value.mesh.element_centers_um : [];
  const nodeCount = radiusNodes.length;
  const elementCount = centers.length;
  if (nodeCount !== siteData.tsvField.nodes || elementCount !== siteData.tsvField.elements) {
    throw new Error("field.json mesh size does not match the reviewed case");
  }
  const nodes = finiteArray(radiusNodes, "mesh.radius_nodes_um", nodeCount);
  const elementCenters = finiteArray(centers, "mesh.element_centers_um", elementCount);
  if (!nodes.every((item, index) => index === 0 || item > nodes[index - 1]!) ||
      !elementCenters.every((item, index) => index === 0 || item > elementCenters[index - 1]!)) {
    throw new Error("field.json radial coordinates must be strictly increasing");
  }
  if (!Array.isArray(value.mesh.connectivity) || value.mesh.connectivity.length !== elementCount) {
    throw new Error("field.json connectivity length is invalid");
  }
  value.mesh.connectivity.forEach((connection, index) => {
    if (!Array.isArray(connection) || connection.length !== 2 || connection[0] !== index || connection[1] !== index + 1) {
      throw new Error(`field.json connectivity[${index}] is not the reviewed Line2 chain`);
    }
  });
  if (!Array.isArray(value.mesh.region_by_element) || value.mesh.region_by_element.length !== elementCount) {
    throw new Error("field.json region labels are invalid");
  }
  const regions = value.mesh.region_by_element.map((item, index) => {
    if (item !== "copper" && item !== "silicon") {
      throw new Error(`mesh.region_by_element[${index}] is not reviewed`);
    }
    return item;
  });
  const viaRadius = finiteNumber(value.mesh.via_radius_um, "mesh.via_radius_um");
  const outerRadius = finiteNumber(value.mesh.outer_radius_um, "mesh.outer_radius_um");
  if (viaRadius !== siteData.tsvField.diameterUm / 2 || outerRadius !== siteData.tsvField.outerRadiusUm) {
    throw new Error("field.json geometric radii do not match the reviewed case");
  }
  if (
    !regions.includes("copper") ||
    !regions.includes("silicon") ||
    regions.some((region, index) => region !== (elementCenters[index]! < viaRadius ? "copper" : "silicon"))
  ) {
    throw new Error("field.json regions do not match the reviewed copper/silicon interface");
  }

  const finalFieldValue = value.final_field;
  if (!isRecord(finalFieldValue)) throw new Error("field.json final_field is missing");
  const finalField = {
    delta_temperature_K: finiteNumber(finalFieldValue.delta_temperature_K, "final_field.delta_temperature_K"),
    ...fieldArrays(finalFieldValue, "final_field", nodeCount, elementCount),
  };
  if (finalField.delta_temperature_K !== siteData.tsvField.deltaTemperatureK) {
    throw new Error("field.json final field does not use the reviewed prescribed load");
  }
  const finalSolver = solverRecord(value.solver, "solver");
  const finalComparison = comparisonRecord(value.comparison, "comparison");

  if (
    !isRecord(value.load_sweep) ||
    value.load_sweep.is_transient !== false ||
    value.load_sweep.sweep_kind !== "independent_static_prescribed_load_cases" ||
    typeof value.load_sweep.description !== "string" ||
    !/not (?:a )?transient/i.test(value.load_sweep.description)
  ) {
    throw new Error("field.json load sweep must be explicitly non-transient");
  }
  if (!Array.isArray(value.load_sweep.steps) || value.load_sweep.steps.length !== siteData.tsvField.loadSteps) {
    throw new Error("field.json must contain all nine solved load states");
  }
  const temperatures = finiteArray(
    value.load_sweep.delta_temperature_K,
    "load_sweep.delta_temperature_K",
    siteData.tsvField.loadSteps,
  );
  if (temperatures.some((temperature, index) => temperature !== EXPECTED_LOADS_K[index])) {
    throw new Error("field.json load sweep does not contain the reviewed prescribed loads");
  }
  const steps = value.load_sweep.steps.map((item, index): LoadStep => {
    if (!isRecord(item) || item.step_index !== index || item.is_transient !== false) {
      throw new Error(`load_sweep.steps[${index}] is not an ordered static solve`);
    }
    if (item.solve_kind !== "independent_static_coupfe_solve") {
      throw new Error(`load_sweep.steps[${index}] is not an actual CoupFE solve`);
    }
    const temperature = finiteNumber(item.delta_temperature_K, `load_sweep.steps[${index}].delta_temperature_K`);
    if (temperature !== temperatures[index]) {
      throw new Error(`load_sweep.steps[${index}] temperature is inconsistent`);
    }
    return {
      step_index: index,
      delta_temperature_K: temperature,
      solve_kind: item.solve_kind,
      is_transient: false,
      solver: solverRecord(item.solver, `load_sweep.steps[${index}].solver`),
      comparison: comparisonRecord(item.comparison, `load_sweep.steps[${index}].comparison`),
      field: fieldArrays(item.field, `load_sweep.steps[${index}].field`, nodeCount, elementCount),
    };
  });
  if (steps.at(-1)?.delta_temperature_K !== finalField.delta_temperature_K) {
    throw new Error("final field and last solved load state are inconsistent");
  }
  const lastStep = steps.at(-1)!;
  for (const key of ["radial_displacement_nm", "sigma_rr_MPa", "sigma_theta_MPa"] as const) {
    if (finalField[key].some((item, index) => item !== lastStep.field[key][index])) {
      throw new Error(`final field ${key} differs from the last actual solved state`);
    }
  }
  if (
    finalComparison.fe_sigma_rr_MPa !== lastStep.comparison.fe_sigma_rr_MPa ||
    finalComparison.lame_sigma_rr_MPa !== lastStep.comparison.lame_sigma_rr_MPa ||
    finalComparison.relative_error !== lastStep.comparison.relative_error
  ) {
    throw new Error("final comparison differs from the last actual solved state");
  }

  return {
    schema_version: 1,
    case_id: value.case_id,
    claim_boundary: value.claim_boundary,
    units: isRecord(value.units) ? value.units as Record<string, string> : {},
    inputs: value.inputs as TsvFieldBundle["inputs"],
    topology: { type: "Line2", spatial_dimension: 1, dof_per_node: 1 },
    mesh: {
      radius_nodes_um: nodes,
      element_centers_um: elementCenters,
      connectivity: value.mesh.connectivity as number[][],
      region_by_element: regions,
      region_element_indices: isRecord(value.mesh.region_element_indices)
        ? value.mesh.region_element_indices as Record<string, number[]>
        : {},
      via_radius_um: viaRadius,
      outer_radius_um: outerRadius,
    },
    final_field: finalField,
    solver: finalSolver,
    comparison: finalComparison,
    load_sweep: {
      sweep_kind: String(value.load_sweep.sweep_kind),
      is_transient: false,
      description: String(value.load_sweep.description),
      delta_temperature_K: temperatures,
      steps,
    },
  };
}

function parseHex(value: string): [number, number, number] {
  return [1, 3, 5].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16)) as [number, number, number];
}

function fieldColor(value: number, maximum: number): string {
  const scaled = Math.min(1, Math.max(0, maximum > 0 ? value / maximum : 0)) * (PALETTE.length - 1);
  const index = Math.min(PALETTE.length - 2, Math.floor(scaled));
  const local = scaled - index;
  const left = parseHex(PALETTE[index]!);
  const right = parseHex(PALETTE[index + 1]!);
  const channel = (position: number) => Math.round(left[position]! + (right[position]! - left[position]!) * local);
  return `rgb(${channel(0)} ${channel(1)} ${channel(2)})`;
}

function interpolateAt(radius: number, coordinates: number[], values: number[]): number {
  if (radius <= coordinates[0]!) return values[0]!;
  if (radius >= coordinates.at(-1)!) return values.at(-1)!;
  let low = 0;
  let high = coordinates.length - 1;
  while (high - low > 1) {
    const middle = Math.floor((low + high) / 2);
    if (coordinates[middle]! <= radius) low = middle;
    else high = middle;
  }
  const fraction = (radius - coordinates[low]!) / (coordinates[high]! - coordinates[low]!);
  return values[low]! + (values[high]! - values[low]!) * fraction;
}

function linePath(
  coordinates: number[],
  values: number[],
  minimumRadius: number,
  maximumRadius: number,
  maximumValue: number,
): string {
  const samples = coordinates
    .map((radius, index) => ({ radius, value: values[index]! }))
    .filter(({ radius }) => radius >= minimumRadius && radius <= maximumRadius);
  const stride = Math.max(1, Math.ceil(samples.length / 220));
  return samples
    .filter((_, index) => index % stride === 0 || index === samples.length - 1)
    .map(({ radius, value }, index) => {
      const x = 54 + ((radius - minimumRadius) / (maximumRadius - minimumRadius)) * 500;
      const y = 238 - (Math.max(0, value) / maximumValue) * 190;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function ConnectedRunControl({
  backend,
  projectId,
  onEvidenceAvailable,
}: {
  backend: CoupFEBackend;
  projectId: string;
  onEvidenceAvailable: (source: FieldEvidenceSource) => void;
}) {
  const { snapshot, loading, error, startWorkflow } = useWorkbench(backend, projectId);
  const [starting, setStarting] = useState(false);
  const latest = snapshot?.runs[0];
  const latestField = latest?.status === "succeeded" ? snapshot?.artifacts.find((item) => item.runId === latest.id && item.kind === "field") : undefined;
  const latestSummary = latest?.status === "succeeded" ? snapshot?.artifacts.find((item) => item.runId === latest.id && item.kind === "report") : undefined;
  const latestManifest = latest?.status === "succeeded" ? snapshot?.artifacts.find((item) => item.runId === latest.id && item.kind === "manifest") : undefined;
  const latestCoreRevision = latest?.input.solverVersion;

  useEffect(() => {
    if (
      latestField &&
      latestSummary &&
      latestManifest &&
      latest &&
      typeof latestCoreRevision === "string" &&
      /^[0-9a-f]{40}$/.test(latestCoreRevision)
    ) {
      onEvidenceAvailable({
        fieldUrl: latestField.uri,
        summaryUrl: latestSummary.uri,
        manifestUrl: latestManifest.uri,
        manifestLabel: "run manifest.json",
        coreRevision: latestCoreRevision,
        label: `local run ${latest.id}`,
      });
    }
  }, [latest?.id, latestCoreRevision, latestField?.uri, latestManifest?.uri, latestSummary?.uri, onEvidenceAvailable]);

  const run = async () => {
    setStarting(true);
    try {
      await startWorkflow(WORKFLOW_ID);
    } finally {
      setStarting(false);
    }
  };
  const active = latest?.status === "queued" || latest?.status === "running";
  return (
    <section className="field-run-control field-run-control-connected" aria-label="Connected CoupFE solver">
      <div><span className="field-status-dot" /><strong>Local solver connected</strong><p>One fixed server-owned case; no browser-supplied command or solver arguments.</p></div>
      <button type="button" onClick={() => void run()} disabled={loading || starting || active}>
        {active ? `CoupFE ${latest.status}` : starting ? "Submitting…" : "Run the fixed 2,400-DOF case"}
      </button>
      {latest && <small>Latest run: <b>{latest.id}</b> · {latest.status}{latest.input.solverVersion ? ` · ${latest.input.solverVersion}` : ""}</small>}
      {error && <small className="field-run-error">{error}</small>}
    </section>
  );
}

function RetainedRunBoundary() {
  return (
    <section className="field-run-control" aria-label="Retained solver run">
      <div><span className="field-status-dot" /><strong>Retained solver output</strong><p>GitHub Pages reads the checked field bundle; it cannot execute Python or CoupFE.</p></div>
      <span className="field-mode-label">Explore, probe, verify</span>
    </section>
  );
}

export default function App({
  backend,
  projectId = "coupfe-eda-local",
  retainedFieldUrl,
  summaryUrl,
  manifestUrl,
  runnerUrl,
}: AppProps) {
  const retainedSource = useMemo<FieldEvidenceSource>(() => ({
    fieldUrl: retainedFieldUrl,
    summaryUrl,
    manifestUrl,
    manifestLabel: "visual-evidence.json",
    coreRevision: siteData.tsvField.coreRevision,
    label: "retained release bundle",
  }), [manifestUrl, retainedFieldUrl, summaryUrl]);
  const [requestedSource, setRequestedSource] = useState<FieldEvidenceSource>(retainedSource);
  const [loadedSource, setLoadedSource] = useState<FieldEvidenceSource | null>(null);
  const [bundle, setBundle] = useState<TsvFieldBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingSource, setLoadingSource] = useState(true);
  const [selectedStep, setSelectedStep] = useState(siteData.tsvField.loadSteps - 1);
  const [playing, setPlaying] = useState(false);
  const [playDirection, setPlayDirection] = useState<1 | -1>(-1);
  const [fullDomain, setFullDomain] = useState(false);
  const [meshVisible, setMeshVisible] = useState(false);
  const [probeRadius, setProbeRadius] = useState(siteData.tsvField.queryRadiusUm);
  const fieldSurfaceRef = useRef<SVGSVGElement>(null);

  const selectConnectedEvidence = useCallback((source: FieldEvidenceSource) => {
    setRequestedSource((current) => current.fieldUrl === source.fieldUrl ? current : source);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    setLoadingSource(true);
    fetch(requestedSource.fieldUrl, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`field request failed with HTTP ${response.status}`);
        return response.json() as Promise<unknown>;
      })
      .then((value) => {
        const validated = validateTsvFieldBundle(value);
        if (controller.signal.aborted) return;
        setBundle(validated);
        setLoadedSource(requestedSource);
        setSelectedStep(siteData.tsvField.loadSteps - 1);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        if (controller.signal.aborted) return;
        const detail = cause instanceof Error ? cause.message : "Unable to load solver field evidence.";
        setLoadError(`${requestedSource.label} was rejected: ${detail}`);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingSource(false);
      });
    return () => controller.abort();
  }, [requestedSource]);

  const activeSource = loadedSource ?? retainedSource;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setSelectedStep((current) => {
        let next = current + playDirection;
        if (next <= 0) {
          next = 0;
          setPlayDirection(1);
        } else if (next >= siteData.tsvField.loadSteps - 1) {
          next = siteData.tsvField.loadSteps - 1;
          setPlayDirection(-1);
        }
        return next;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [playDirection, playing]);

  const step = bundle?.load_sweep.steps[selectedStep];
  const viewRadius = fullDomain ? siteData.tsvField.outerRadiusUm : NEAR_FIELD_RADIUS_UM;
  const siliconElementIndices = useMemo(() => bundle
    ? bundle.mesh.region_by_element.flatMap((region, index) => region === "silicon" ? [index] : [])
    : [], [bundle]);
  const siliconCenters = useMemo(() => bundle
    ? siliconElementIndices.map((index) => bundle.mesh.element_centers_um[index]!)
    : [], [bundle, siliconElementIndices]);
  const probeMinimum = siliconCenters[0] ?? siteData.tsvField.diameterUm / 2;

  useEffect(() => {
    setProbeRadius((current) => Math.min(viewRadius, Math.max(probeMinimum, current)));
  }, [probeMinimum, viewRadius]);

  const maximumStress = useMemo(() => {
    if (!bundle) return 1;
    const final = bundle.load_sweep.steps.at(-1)!;
    return Math.max(
      1,
      ...final.field.sigma_rr_MPa.filter((_, index) => bundle.mesh.region_by_element[index] === "silicon"),
    );
  }, [bundle]);

  const rings = useMemo(() => {
    if (!bundle || !step) return [];
    const indices = siliconElementIndices
      .map((index) => ({ radius: bundle.mesh.element_centers_um[index]!, index }))
      .filter(({ radius }) => radius <= viewRadius);
    const stride = Math.max(1, Math.ceil(indices.length / 150));
    const sampled = indices.filter((_, index) => index % stride === 0 || index === indices.length - 1);
    return sampled.map(({ radius, index }, sampleIndex) => {
      const nextRadius = sampled[sampleIndex + 1]?.radius ?? Math.min(viewRadius, bundle.mesh.radius_nodes_um[index + 1]!);
      const widthUm = Math.max(nextRadius - radius, viewRadius / 500);
      return {
        radius: (radius / viewRadius) * FIELD_RADIUS,
        width: Math.max(1, (widthUm / viewRadius) * FIELD_RADIUS * 1.25),
        color: fieldColor(step.field.sigma_rr_MPa[index]!, maximumStress),
      };
    }).reverse();
  }, [bundle, maximumStress, siliconElementIndices, step, viewRadius]);

  const meshRings = useMemo(() => {
    if (!bundle) return [];
    const visibleNodes = bundle.mesh.radius_nodes_um.filter(
      (radius) => radius > 0 && radius <= viewRadius,
    );
    const stride = Math.max(1, Math.ceil(visibleNodes.length / 48));
    return visibleNodes.filter(
      (_, index) => index % stride === 0 || index === visibleNodes.length - 1,
    );
  }, [bundle, viewRadius]);

  const handleProbe = (clientX: number, clientY: number) => {
    if (!bundle || !fieldSurfaceRef.current) return;
    const rect = fieldSurfaceRef.current.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const x = (clientX - rect.left) * (VIEWBOX_SIZE / rect.width) - FIELD_CENTER;
    const y = (clientY - rect.top) * (VIEWBOX_SIZE / rect.height) - FIELD_CENTER;
    const radius = Math.hypot(x, y) / FIELD_RADIUS * viewRadius;
    setProbeRadius(Math.min(viewRadius, Math.max(probeMinimum, radius)));
  };

  const siliconSigmaRr = bundle && step
    ? siliconElementIndices.map((index) => step.field.sigma_rr_MPa[index]!)
    : [];
  const siliconSigmaTheta = bundle && step
    ? siliconElementIndices.map((index) => step.field.sigma_theta_MPa[index]!)
    : [];
  const probe = bundle && step ? {
    sigmaRr: interpolateAt(probeRadius, siliconCenters, siliconSigmaRr),
    sigmaTheta: interpolateAt(probeRadius, siliconCenters, siliconSigmaTheta),
    displacement: interpolateAt(probeRadius, bundle.mesh.radius_nodes_um, step.field.radial_displacement_nm),
  } : null;
  const chartPath = bundle && step
    ? linePath(siliconCenters, siliconSigmaRr, probeMinimum, viewRadius, maximumStress)
    : "";
  const queryX = bundle
    ? 54 + ((siteData.tsvField.queryRadiusUm - probeMinimum) / (viewRadius - probeMinimum)) * 500
    : 0;
  const queryFe = step ? step.comparison.fe_sigma_rr_MPa : 0;
  const queryLame = step ? step.comparison.lame_sigma_rr_MPa : 0;
  const queryFeY = 238 - Math.max(0, queryFe) / maximumStress * 190;
  const queryLameY = 238 - Math.max(0, queryLame) / maximumStress * 190;

  return (
    <main className="field-workbench">
      <header className="field-workbench-hero">
        <div>
          <p className="field-kicker">CoupFE Core field explorer · {activeSource.label}</p>
          <h1>Inspect the field behind the claim.</h1>
          <p>The color bands, curves, probe values, and animation below are read from the named solver artifact. No CSS contour, invented mesh, or simulated lifecycle is used.</p>
        </div>
        <aside><span>Case</span><strong>{siteData.tsvField.caseId}</strong><small>D = {siteData.tsvField.diameterUm} µm · ΔT = {siteData.tsvField.deltaTemperatureK} K · Line2</small></aside>
      </header>

      {backend
        ? <ConnectedRunControl backend={backend} projectId={projectId} onEvidenceAvailable={selectConnectedEvidence} />
        : <RetainedRunBoundary />}

      {loadError && <div className="field-load-state field-load-error" role="alert"><strong>Field evidence rejected</strong><span>{loadError}</span></div>}
      {loadingSource && <div className={`field-load-state ${bundle ? "field-load-pending" : ""}`} role="status">Loading and validating {requestedSource.label} field.json…{bundle ? ` The ${activeSource.label} remains displayed until validation succeeds.` : ""}</div>}

      {bundle && step && (
        <>
          <section className="field-stage" aria-label="Solver field and radial profile">
            <article className="field-contour-panel">
              <header><div><span>Recovered field</span><h2>Silicon radial stress σrr</h2></div><nav aria-label="Field view"><button aria-pressed={!fullDomain} className={!fullDomain ? "is-active" : ""} onClick={() => setFullDomain(false)}>Near field</button><button aria-pressed={fullDomain} className={fullDomain ? "is-active" : ""} onClick={() => setFullDomain(true)}>Full domain</button><button aria-pressed={meshVisible} className={meshVisible ? "is-active" : ""} onClick={() => setMeshVisible((value) => !value)}>Mesh nodes</button></nav></header>
              <div className="field-contour-wrap">
                <svg
                  ref={fieldSurfaceRef}
                  viewBox={`0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}`}
                  role="img"
                  aria-label={`Axisymmetric radial stress at delta temperature ${step.delta_temperature_K} kelvin`}
                  onPointerMove={(event) => handleProbe(event.clientX, event.clientY)}
                  onPointerDown={(event) => handleProbe(event.clientX, event.clientY)}
                >
                  <circle cx={FIELD_CENTER} cy={FIELD_CENTER} r={FIELD_RADIUS} fill="#0b1730" stroke="#31425e" />
                  {rings.map((ring, index) => <circle key={index} cx={FIELD_CENTER} cy={FIELD_CENTER} r={ring.radius} fill="none" stroke={ring.color} strokeWidth={ring.width} />)}
                  <circle cx={FIELD_CENTER} cy={FIELD_CENTER} r={(bundle.mesh.via_radius_um / viewRadius) * FIELD_RADIUS} fill="#c57847" stroke="#f4d0b5" strokeWidth="2" />
                  {meshVisible && meshRings.map((radiusUm) => (
                    <circle key={radiusUm} cx={FIELD_CENTER} cy={FIELD_CENTER} r={(radiusUm / viewRadius) * FIELD_RADIUS} fill="none" stroke="#f8fafc" strokeOpacity=".18" strokeWidth=".7" />
                  ))}
                  <line x1={FIELD_CENTER} y1={FIELD_CENTER} x2={FIELD_CENTER + (probeRadius / viewRadius) * FIELD_RADIUS} y2={FIELD_CENTER} stroke="#fff" strokeWidth="1.5" />
                  <circle cx={FIELD_CENTER + (probeRadius / viewRadius) * FIELD_RADIUS} cy={FIELD_CENTER} r="5" fill="#fff" stroke="#07101f" strokeWidth="2" />
                  <text x={FIELD_CENTER} y={FIELD_CENTER + 5} textAnchor="middle">Cu</text>
                  <text x="22" y="476">Axisymmetric reconstruction · {meshVisible ? "sampled actual Line2 nodes" : `solved radius 0–${viewRadius} µm`}</text>
                </svg>
                <div className="field-colorbar"><span>{maximumStress.toFixed(0)} MPa</span><i /><span>0</span></div>
              </div>
              <dl className="field-probe">
                <div><dt>Si-side probe radius</dt><dd>{probeRadius.toFixed(2)} µm</dd></div>
                <div><dt>σrr</dt><dd>{probe?.sigmaRr.toFixed(3)} MPa</dd></div>
                <div><dt>σθθ</dt><dd>{probe?.sigmaTheta.toFixed(3)} MPa</dd></div>
                <div><dt>u<sub>r</sub></dt><dd>{probe?.displacement.toFixed(3)} nm</dd></div>
              </dl>
              <label className="field-probe-slider">
                <span>Silicon probe radius</span>
                <input aria-label="Silicon probe radius" type="range" min={probeMinimum} max={viewRadius} step="0.05" value={probeRadius} onChange={(event) => setProbeRadius(Number(event.target.value))} />
                <output>{probeRadius.toFixed(2)} µm</output>
              </label>
            </article>

            <article className="field-profile-panel">
              <header><span>Element-center values</span><h2>Stress versus radius</h2><p>Fixed y-scale across every solved load state.</p></header>
              <svg viewBox="0 0 600 290" role="img" aria-label="Finite element radial stress profile with Lamé reference at 20 micrometres">
                {[0, .25, .5, .75, 1].map((fraction) => {
                  const y = 238 - fraction * 190;
                  return <g key={fraction}><line x1="54" y1={y} x2="554" y2={y} /><text x="44" y={y + 4} textAnchor="end">{(fraction * maximumStress).toFixed(0)}</text></g>;
                })}
                <line x1="54" y1="238" x2="554" y2="238" className="field-axis" />
                <path d={chartPath} className="field-profile-line" />
                {queryX >= 54 && queryX <= 554 && <>
                  <line x1={queryX} y1="42" x2={queryX} y2="238" className="field-query-line" />
                  <circle cx={queryX} cy={queryFeY} r="5" className="field-fe-point" />
                  <path d={`M${queryX - 6},${queryLameY} h12 M${queryX},${queryLameY - 6} v12`} className="field-lame-point" />
                </>}
                <text x="304" y="278" textAnchor="middle">radius r (µm)</text>
                <text x="14" y="24">σrr (MPa)</text>
              </svg>
              <div className="field-profile-legend"><span><i className="field-fe-key" />CoupFE field</span><span><i className="field-lame-key" />Lamé at 20 µm</span></div>
              <dl className="field-comparison">
                <div><dt>CoupFE</dt><dd>{queryFe.toFixed(4)} MPa</dd></div>
                <div><dt>Lamé</dt><dd>{queryLame.toFixed(4)} MPa</dd></div>
                <div><dt>Relative difference</dt><dd>{step.comparison.relative_error === null ? "zero-load identity" : `${(step.comparison.relative_error * 100).toFixed(4)}%`}</dd></div>
              </dl>
            </article>
          </section>

          <section className="field-timeline" aria-label="Actual solved load states">
            <div><span>Prescribed load sweep</span><strong>ΔT = {step.delta_temperature_K.toFixed(0)} K</strong><small>State {selectedStep + 1} of {bundle.load_sweep.steps.length} · independent static CoupFE solve · not transient</small></div>
            <button type="button" onClick={() => setPlaying((value) => !value)}>{playing ? "Pause actual states" : "Play actual states"}</button>
            <input aria-label="Solved cooling-load state" type="range" min="0" max={bundle.load_sweep.steps.length - 1} step="1" value={selectedStep} onChange={(event) => { setPlaying(false); setSelectedStep(Number(event.target.value)); }} />
            <div className="field-step-dots" aria-hidden="true">{bundle.load_sweep.steps.map((item, index) => <i key={item.step_index} className={index === selectedStep ? "is-active" : ""} />)}</div>
          </section>

          <section className="field-metrics" aria-label="Solver evidence">
            <article><span>Mesh / DOF</span><strong>{bundle.mesh.element_centers_um.length.toLocaleString()} / {bundle.mesh.radius_nodes_um.length.toLocaleString()}</strong><small>radial Line2 / displacement unknowns</small></article>
            <article><span>Newton iterations</span><strong>{step.solver.newton_iterations}</strong><small>actual selected-state solve</small></article>
            <article><span>Final relative residual</span><strong>{step.solver.final_relative_residual.toExponential(2)}</strong><small>{(step.solver.residual_fraction_of_acceptance_limit * 100).toFixed(2)}% of acceptance limit</small></article>
            <article><span>Core revision</span><strong>{activeSource.coreRevision.slice(0, 10)}</strong><small>full SHA in matching manifest</small></article>
          </section>

          <section className="field-evidence">
            <div><span>Evidence bundle</span><h2>Every plotted field value has a route back to solver arrays.</h2><p>{bundle.claim_boundary}</p></div>
            <nav aria-label="Field evidence artifacts"><a href={activeSource.fieldUrl}>field.json</a><a href={activeSource.summaryUrl}>summary.json</a><a href={activeSource.manifestUrl}>{activeSource.manifestLabel}</a><a href={runnerUrl}>runner source ↗</a></nav>
          </section>
        </>
      )}
    </main>
  );
}
