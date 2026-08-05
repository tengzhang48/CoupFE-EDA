import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import siteData from "../site-data.json";
import App, { validateTsvFieldBundle } from "./App";
import type { CoupFEBackend } from "./backend/interface";
import type { ProjectSnapshot, RunRecord } from "./domain/types";

function fieldBundle() {
  const nodes = Array.from({ length: siteData.tsvField.nodes }, (_, index) =>
    index * siteData.tsvField.outerRadiusUm / (siteData.tsvField.nodes - 1));
  const centers = nodes.slice(0, -1).map((value, index) => (value + nodes[index + 1]!) / 2);
  const regionByElement = centers.map((radius) => radius < siteData.tsvField.diameterUm / 2 ? "copper" : "silicon");
  const fieldFor = (deltaTemperature: number) => {
    const scale = Math.abs(deltaTemperature / siteData.tsvField.deltaTemperatureK);
    return {
      radial_displacement_nm: nodes.map((radius) => -scale * radius * .5),
      sigma_rr_MPa: centers.map((radius) => scale * 630 / (1 + (radius / 18) ** 2)),
      sigma_theta_MPa: centers.map((radius) => -scale * 635 / (1 + (radius / 18) ** 2)),
    };
  };
  const solver = (deltaTemperature: number) => ({
    newton_iterations: deltaTemperature === 0 ? 1 : 2,
    final_relative_residual: deltaTemperature === 0 ? 0 : 5.45e-12,
    residual_fraction_of_acceptance_limit: deltaTemperature === 0 ? 0 : .00545,
    converged: true,
  });
  const comparison = (deltaTemperature: number) => {
    const scale = Math.abs(deltaTemperature / siteData.tsvField.deltaTemperatureK);
    return {
      reference: "published_Lame_equation",
      query_radius_um: siteData.tsvField.queryRadiusUm,
      fe_sigma_rr_MPa: siteData.tsvField.sigmaRrAtQueryMpa * scale,
      lame_sigma_rr_MPa: siteData.tsvField.lameAtQueryMpa * scale,
      absolute_error_MPa: Math.abs(siteData.tsvField.sigmaRrAtQueryMpa - siteData.tsvField.lameAtQueryMpa) * scale,
      relative_error: deltaTemperature === 0 ? null : siteData.tsvField.relativeErrorPercent / 100,
      acceptance_threshold: 0.03,
      passed: true,
    };
  };
  const temperatures = [0, -50, -100, -150, -200, -250, -300, -350, -400];
  return {
    schema_version: 1,
    case_id: siteData.tsvField.caseId,
    claim_boundary: siteData.tsvField.claimBoundary,
    units: { radius: "um", radial_displacement: "nm", stress: "MPa", temperature_change: "K", residual_norm: "N/m" },
    inputs: {
      diameter_um: siteData.tsvField.diameterUm,
      delta_temperature_K: siteData.tsvField.deltaTemperatureK,
      outer_radius_um: siteData.tsvField.outerRadiusUm,
      mesh_points_requested: siteData.tsvField.nodes,
      liner_nm: 0,
      formulation: "axisymmetric_plane_strain",
      load: "uniform_thermal_eigenstrain",
    },
    topology: { type: "Line2", spatial_dimension: 1, dof_per_node: 1 },
    mesh: {
      radius_nodes_um: nodes,
      element_centers_um: centers,
      connectivity: centers.map((_, index) => [index, index + 1]),
      region_by_element: regionByElement,
      region_element_indices: {
        copper: regionByElement.flatMap((region, index) => region === "copper" ? [index] : []),
        silicon: regionByElement.flatMap((region, index) => region === "silicon" ? [index] : []),
      },
      via_radius_um: siteData.tsvField.diameterUm / 2,
      outer_radius_um: siteData.tsvField.outerRadiusUm,
    },
    final_field: { delta_temperature_K: -400, ...fieldFor(-400) },
    solver: solver(-400),
    comparison: comparison(-400),
    load_sweep: {
      sweep_kind: "independent_static_prescribed_load_cases",
      is_transient: false,
      description: "Nine independent actual CoupFE static solves; not a transient simulation.",
      delta_temperature_K: temperatures,
      steps: temperatures.map((deltaTemperature, index) => ({
        step_index: index,
        delta_temperature_K: deltaTemperature,
        solve_kind: "independent_static_coupfe_solve",
        is_transient: false,
        solver: solver(deltaTemperature),
        results: {},
        comparison: comparison(deltaTemperature),
        field: fieldFor(deltaTemperature),
      })),
    },
  };
}

function mockFieldFetch(value = fieldBundle()) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => structuredClone(value),
  }));
}

function renderExplorer(backend?: CoupFEBackend) {
  return render(
    <App
      backend={backend}
      retainedFieldUrl="/field.json"
      summaryUrl="/summary.json"
      manifestUrl="/visual-evidence.json"
      runnerUrl="https://github.test/run.py"
    />,
  );
}

function completedConnectedSnapshot(coreRevision = "c".repeat(40)): ProjectSnapshot {
  return {
    schemaVersion: 1,
    sequence: 3,
    mode: "connected",
    project: { id: "coupfe-eda-local", name: "Local real field", studyType: "Axisymmetric verification", activeDesignId: "fixed-tsv" },
    designs: [{ id: "fixed-tsv", label: "Fixed 30 µm TSV", packageRevision: "v1", createdAt: "2026-08-05T00:00:00Z", parameters: {} }],
    approvedWorkflows: [],
    models: [], decisions: [], evidence: [], layers: [], candidates: [],
    runs: [{
      id: "run-local-1", projectId: "coupfe-eda-local", designId: "fixed-tsv",
      workflowId: "tsv_axisymmetric_field", clientRequestId: "request-local", sequence: 3,
      status: "succeeded", requestedAt: "2026-08-05T00:00:01Z", completedAt: "2026-08-05T00:00:03Z",
      input: {
        designRevision: "Fixed 30 µm TSV", packageRevision: "v1", codeRevision: "a".repeat(40),
        solverVersion: coreRevision, manifestSha256: "pending",
      },
    }],
    artifacts: [
      { id: "field", runId: "run-local-1", kind: "field", uri: "/api/runs/run-local-1/artifacts/field.json", sha256: "a".repeat(64) },
      { id: "summary", runId: "run-local-1", kind: "report", uri: "/api/runs/run-local-1/artifacts/summary.json", sha256: "b".repeat(64) },
      { id: "manifest", runId: "run-local-1", kind: "manifest", uri: "/api/runs/run-local-1/artifacts/manifest.json", sha256: "c".repeat(64) },
    ],
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("real CoupFE field explorer", () => {
  it("loads arrays and exposes the retained-run boundary", async () => {
    mockFieldFetch();
    renderExplorer();

    expect(screen.getByRole("heading", { name: "TSV field workbench" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Retained solver run" })).toHaveTextContent(
      "GitHub Pages reads the checked field bundle",
    );
    expect(await screen.findByRole("heading", { name: "Radial stress versus radius" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Axisymmetric radial stress at delta temperature -400 kelvin/i })).toBeInTheDocument();
    expect(screen.getByText(siteData.tsvField.claimBoundary)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "field.json" })).toHaveAttribute("href", "/field.json");
    expect(screen.getByRole("heading", { name: "Retained source record" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /simulate/i })).not.toBeInTheDocument();
    const meshButton = screen.getByRole("button", { name: "Mesh nodes" });
    fireEvent.click(meshButton);
    expect(meshButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("slider", { name: "Silicon probe radius" }))
      .toHaveAttribute("aria-valuetext", "20.00 micrometres");
  });

  it("moves only among the nine actual solved states", async () => {
    mockFieldFetch();
    renderExplorer();
    await screen.findByRole("heading", { name: "Radial stress versus radius" });

    const slider = screen.getByRole("slider", { name: "Solved cooling-load state" });
    expect(slider).toHaveAttribute("aria-valuetext", "-400 kelvin; load case 9 of 9");
    fireEvent.change(slider, { target: { value: "4" } });
    expect(slider).toHaveAttribute("aria-valuetext", "-200 kelvin; load case 5 of 9");
    expect(screen.getByText("ΔT = -200 K")).toBeInTheDocument();
    expect(screen.getByText(/Case 5 of 9 · independent static solve · not transient/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Play actual states/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select load case 2: -50 K" }));
    expect(screen.getByText("ΔT = -50 K")).toBeInTheDocument();
  });

  it("switches among retained stress and displacement outputs", async () => {
    mockFieldFetch();
    const { container } = renderExplorer();
    await screen.findByRole("heading", { name: "Radial stress versus radius" });
    expect(container.querySelector(".field-colorbar i")).toHaveClass("is-positive");

    fireEvent.click(screen.getByRole("button", { name: /Hoop stress/ }));
    expect(screen.getByRole("heading", { name: "Hoop stress versus radius" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Axisymmetric hoop stress at delta temperature -400 kelvin/i })).toBeInTheDocument();
    expect(container.querySelector(".field-colorbar i")).toHaveClass("is-negative");

    fireEvent.click(screen.getByRole("button", { name: /Radial displacement/ }));
    expect(screen.getByRole("heading", { name: "Radial displacement versus radius" })).toBeInTheDocument();
    expect(screen.getByText(/Visible minimum/).closest("div")).toHaveTextContent("nm");
    expect(container.querySelector(".field-colorbar i")).toHaveClass("is-negative");
  });

  it("keeps the field scale fixed across every solved load case", async () => {
    const bundle = fieldBundle();
    const firstSilicon = bundle.mesh.region_element_indices.silicon[0]!;
    bundle.load_sweep.steps[1]!.field.sigma_rr_MPa[firstSilicon] = 1111;
    mockFieldFetch(bundle);
    renderExplorer();
    await screen.findByRole("heading", { name: "Radial stress versus radius" });
    expect(screen.getByText("1111")).toBeInTheDocument();
  });

  it("fails closed on a field that does not come from the reviewed case", () => {
    const invalid = fieldBundle();
    invalid.case_id = "concept-art-case";
    expect(() => validateTsvFieldBundle(invalid)).toThrow(/unexpected solver case/i);
    const synthetic = fieldBundle();
    synthetic.load_sweep.steps[3]!.solve_kind = "browser_interpolation";
    expect(() => validateTsvFieldBundle(synthetic)).toThrow(/not an actual CoupFE solve/i);
    const inventedMesh = fieldBundle();
    inventedMesh.mesh.connectivity[4] = [0, 1];
    expect(() => validateTsvFieldBundle(inventedMesh)).toThrow(/not the reviewed Line2 chain/i);
    const roundedGeometry = fieldBundle();
    roundedGeometry.mesh.via_radius_um = 14.999999999999998;
    expect(() => validateTsvFieldBundle(roundedGeometry)).not.toThrow();
    const wrongGeometry = fieldBundle();
    wrongGeometry.mesh.via_radius_um = 14.9;
    expect(() => validateTsvFieldBundle(wrongGeometry)).toThrow(/geometric radii/i);
  });

  it("submits only the named workflow in connected mode", async () => {
    mockFieldFetch();
    const snapshot: ProjectSnapshot = {
      schemaVersion: 1,
      sequence: 0,
      mode: "connected",
      project: { id: "coupfe-eda-local", name: "Local real field", studyType: "Axisymmetric verification", activeDesignId: "fixed-tsv" },
      designs: [{ id: "fixed-tsv", label: "Fixed 30 µm TSV", packageRevision: "v1", createdAt: "2026-08-05T00:00:00Z", parameters: {} }],
      approvedWorkflows: [{
        id: "tsv_axisymmetric_field",
        executorKey: "tsv.axisymmetric-field.v1",
        name: "Axisymmetric TSV stress field",
        description: "Fixed real CoupFE solve",
        driverPath: "examples/tsv_axisymmetric_field/run.py",
        releaseValidation: false,
        claimBoundary: siteData.tsvField.claimBoundary,
        expectedMetricKeys: [],
      }],
      models: [], decisions: [], runs: [], evidence: [], artifacts: [], layers: [], candidates: [],
    };
    const accepted: RunRecord = {
      id: "run-real-1", projectId: "coupfe-eda-local", designId: "fixed-tsv",
      workflowId: "tsv_axisymmetric_field", clientRequestId: "request-1", sequence: 1,
      status: "queued", requestedAt: "2026-08-05T00:00:01Z",
      input: {
        designRevision: "Fixed 30 µm TSV", packageRevision: "v1", codeRevision: "a".repeat(40),
        solverVersion: `CoupFE Core ${siteData.tsvField.coreRevision}`, manifestSha256: "pending",
      },
    };
    const backend: CoupFEBackend = {
      getSnapshot: vi.fn().mockResolvedValue(snapshot),
      startRun: vi.fn().mockResolvedValue(accepted),
      cancelRun: vi.fn(),
      subscribeProjectEvents: vi.fn().mockReturnValue(() => undefined),
    };
    renderExplorer(backend);
    const button = await screen.findByRole("button", { name: /Run the fixed 2,400-DOF case/i });
    fireEvent.click(button);
    await waitFor(() => expect(backend.startRun).toHaveBeenCalledTimes(1));
    expect(backend.startRun).toHaveBeenCalledWith(expect.objectContaining({
      projectId: "coupfe-eda-local",
      designId: "fixed-tsv",
      workflowId: "tsv_axisymmetric_field",
    }));
  });

  it("atomically switches field, summary, manifest, and Core revision after local validation", async () => {
    mockFieldFetch();
    let resolveSnapshot!: (snapshot: ProjectSnapshot) => void;
    const backend: CoupFEBackend = {
      getSnapshot: vi.fn().mockImplementation(() => new Promise<ProjectSnapshot>((resolve) => { resolveSnapshot = resolve; })),
      startRun: vi.fn(), cancelRun: vi.fn(), subscribeProjectEvents: vi.fn().mockReturnValue(() => undefined),
    };
    renderExplorer(backend);
    await screen.findByRole("heading", { name: "Radial stress versus radius" });
    expect(screen.getByText(/retained release bundle/i)).toBeInTheDocument();

    await act(async () => { resolveSnapshot(completedConnectedSnapshot()); });
    await waitFor(() => expect(screen.getByText(/local run run-local-1/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "field.json" })).toHaveAttribute("href", "/api/runs/run-local-1/artifacts/field.json");
    expect(screen.getByRole("link", { name: "summary.json" })).toHaveAttribute("href", "/api/runs/run-local-1/artifacts/summary.json");
    expect(screen.getByRole("link", { name: "run manifest.json" })).toHaveAttribute("href", "/api/runs/run-local-1/artifacts/manifest.json");
    expect(screen.getByText("cccccccccc")).toBeInTheDocument();
  });

  it("keeps retained attribution when a connected field is rejected", async () => {
    const retained = fieldBundle();
    const rejected = fieldBundle();
    rejected.case_id = "wrong-local-case";
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => Promise.resolve({
      ok: true,
      status: 200,
      json: async () => structuredClone(String(input).includes("/api/runs/") ? rejected : retained),
    })));
    let resolveSnapshot!: (snapshot: ProjectSnapshot) => void;
    const backend: CoupFEBackend = {
      getSnapshot: vi.fn().mockImplementation(() => new Promise<ProjectSnapshot>((resolve) => { resolveSnapshot = resolve; })),
      startRun: vi.fn(), cancelRun: vi.fn(), subscribeProjectEvents: vi.fn().mockReturnValue(() => undefined),
    };
    renderExplorer(backend);
    await screen.findByRole("heading", { name: "Radial stress versus radius" });
    await act(async () => { resolveSnapshot(completedConnectedSnapshot()); });
    expect(await screen.findByRole("alert")).toHaveTextContent(/local run run-local-1 was rejected/i);
    expect(screen.getByText(/retained release bundle/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "field.json" })).toHaveAttribute("href", "/field.json");
    expect(screen.getByRole("link", { name: "visual-evidence.json" })).toHaveAttribute("href", "/visual-evidence.json");
    expect(screen.queryByRole("link", { name: "run manifest.json" })).not.toBeInTheDocument();
  });
});
