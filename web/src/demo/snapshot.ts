import retainedTsvArtifacts from "../../contracts/retained-tsv-artifacts.json";
import siteData from "../../site-data.json";
import type { ProjectSnapshot, RunOutput } from "../domain/types";

export const TSV_WORKFLOW_ID = "tsv_device_screening";
export const TSV_CLAIM_BOUNDARY = siteData.tsvScreening.claimBoundary;
export const TSV_RETAINED_ARTIFACTS = retainedTsvArtifacts.artifacts;

export function createTsvWorkflowOutput(
  runId: string,
  interfaceRuntimeSeconds: number,
): RunOutput {
  const resultEvidenceId = `ev-${runId}-tsv-screening`;
  return {
    genericMetrics: [
      { key: "baseline_violations", label: "Baseline violations", value: siteData.tsvScreening.baselineViolations, unit: "devices", assessment: "observed", evidenceIds: [resultEvidenceId] },
      { key: "optimized_violations", label: "Post-action violations", value: siteData.tsvScreening.optimizedViolations, unit: "devices", assessment: "observed", evidenceIds: [resultEvidenceId] },
      { key: "baseline_peak_abs_mobility_proxy", label: "Baseline peak |mobility proxy|", value: siteData.tsvScreening.baselinePeakAbsMobilityProxy, unit: "1", assessment: "observed", evidenceIds: [resultEvidenceId] },
      { key: "optimized_peak_abs_mobility_proxy", label: "Optimized peak |mobility proxy|", value: siteData.tsvScreening.optimizedPeakAbsMobilityProxy, unit: "1", assessment: "observed", evidenceIds: [resultEvidenceId] },
      { key: "runtime_seconds", label: "Simulated interface runtime", value: interfaceRuntimeSeconds, unit: "s", assessment: "observed", evidenceIds: [] },
    ],
    artifactIds: TSV_RETAINED_ARTIFACTS.map((artifact) => `${artifact.kind}-${runId}`),
    evidenceIds: [resultEvidenceId],
    conclusion: "The public interface simulated the approved-workflow contract and displayed the retained project-generated TSV demonstration record.",
    nextAction: "Use the local FastAPI mode to execute the server-allowlisted workflow and retain a new run record.",
    qualification: {
      releaseValidation: false,
      claimBoundary: TSV_CLAIM_BOUNDARY,
    },
  };
}

export const demoSnapshot: ProjectSnapshot = {
  schemaVersion: 1,
  sequence: 0,
  mode: "demo",
  project: {
    id: "tsv-thermal-001",
    name: "CoupFE-EDA interface demonstration",
    studyType: "Approved workflow contract; no browser solver execution",
    activeDesignId: "tsv-synthetic-device-sites-v1",
  },
  designs: [
    {
      id: "tsv-synthetic-device-sites-v1",
      label: "Synthetic TSV device-screening inputs",
      packageRevision: "examples/tsv_00_device_screening",
      createdAt: "2026-08-01T00:00:00.000Z",
      parameters: {
        tsv_diameter: { value: 10, unit: "µm" },
        device_count: { value: siteData.tsvScreening.nDevices, unit: "1" },
      },
    },
  ],
  models: [],
  approvedWorkflows: [
    {
      id: TSV_WORKFLOW_ID,
      executorKey: "tsv.device-screening.v1",
      name: "Synthetic TSV-to-device screening",
      description: "Identity-preserving screening through the approved local executor boundary.",
      driverPath: "examples/tsv_00_device_screening/run.py",
      releaseValidation: false,
      claimBoundary: TSV_CLAIM_BOUNDARY,
      expectedMetricKeys: [
        "baseline_violations",
        "optimized_violations",
        "baseline_peak_abs_mobility_proxy",
        "optimized_peak_abs_mobility_proxy",
        "runtime_seconds",
      ],
    },
  ],
  decisions: [],
  runs: [],
  evidence: [],
  artifacts: [],
  layers: [],
  candidates: [],
};
