import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import App from "./App";
import { MockBackend } from "./backend/mock-backend";
import { demoSnapshot, TSV_CLAIM_BOUNDARY } from "./demo/snapshot";

function renderWorkbench(mode: "demo" | "connected" = "demo") {
  const snapshot = structuredClone(demoSnapshot);
  snapshot.mode = mode;
  const backend = new MockBackend(snapshot, {
    queueDelayMs: 2,
    runDelayMs: 12,
  });
  render(<App backend={backend} projectId={snapshot.project.id} />);
  return backend;
}

function renderRunningWorkbench(mode: "demo" | "connected") {
  const snapshot = structuredClone(demoSnapshot);
  snapshot.mode = mode;
  snapshot.sequence = 2;
  snapshot.runs = [{
    id: `run-${mode}`,
    projectId: snapshot.project.id,
    designId: snapshot.project.activeDesignId,
    workflowId: "tsv_device_screening",
    clientRequestId: `request-${mode}`,
    sequence: 2,
    status: "running",
    requestedAt: "2026-08-01T19:00:00.000Z",
    startedAt: "2026-08-01T19:00:00.100Z",
    progress: { phase: "evaluating", fraction: 0.5, message: "Running retained check" },
    input: {
      designRevision: snapshot.designs[0]!.label,
      packageRevision: snapshot.designs[0]!.packageRevision,
      codeRevision: "test-only-running-snapshot",
      solverVersion: "not-applicable: analytic screening",
      runtimeInputSet: "examples/tsv_00_device_screening/device_sites.csv",
      manifestSha256: "pending",
    },
  }];
  const backend = new MockBackend(snapshot, { queueDelayMs: 60_000, runDelayMs: 60_000 });
  render(<App backend={backend} projectId={snapshot.project.id} />);
}

afterEach(cleanup);

describe("CoupFE–EDA public interface demonstration", () => {
  it("shows only the approved real workflow and its qualification boundary", async () => {
    renderWorkbench();

    expect((await screen.findAllByText(demoSnapshot.project.name)).length).toBeGreaterThan(0);
    expect(screen.getByRole("note")).toHaveTextContent("Demonstration data");
    expect(screen.getByRole("note")).toHaveTextContent("No engineering solver runs");
    expect(screen.getByRole("heading", { name: "Approved workflow simulation" })).toBeInTheDocument();
    expect(screen.getByText("Browser simulation", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Synthetic TSV-to-device screening" })).toBeInTheDocument();
    expect(screen.getByText(TSV_CLAIM_BOUNDARY)).toBeInTheDocument();
    expect(screen.getByText(/Release validation: not claimed/i)).toBeInTheDocument();
    expect(screen.getByText(/No simulation is recorded yet/i)).toBeInTheDocument();
    expect(screen.getByText(/No simulated records have been created/i)).toBeInTheDocument();
    expect(screen.getByText(/No solver executes; reviewed evidence is precomputed/i)).toBeInTheDocument();
    expect(screen.getByText("Approved simulation contract", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(screen.queryByText("Server-approved workflow", { selector: ".eyebrow" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Simulate approved workflow/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review simulation/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Simulated run history" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run approved workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Review and run/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Recent analyses" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Models" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Peak temperature/i)).not.toBeInTheDocument();
  });

  it("simulates the workflow lifecycle without presenting it as solver evidence", async () => {
    const backend = renderWorkbench();
    expect((await screen.findAllByText(demoSnapshot.project.name)).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Review simulation/i }));
    const dialog = screen.getByRole("dialog", { name: /Simulate Synthetic TSV-to-device screening/i });
    expect(within(dialog).getByText("Browser simulation boundary", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(within(dialog).queryByText("Approved execution boundary", { selector: ".eyebrow" })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/The browser models lifecycle events/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/does not contact a solver or execute/i)).toBeInTheDocument();
    expect(within(dialog).queryByText(/The service maps it/i)).not.toBeInTheDocument();
    expect(within(dialog).getByText("Not claimed")).toBeInTheDocument();
    expect(within(dialog).getByText(TSV_CLAIM_BOUNDARY)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /Start simulation/i }));

    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Simulation queued · run-1");
    await waitFor(async () => {
      const snapshot = await backend.getSnapshot(demoSnapshot.project.id);
      expect(snapshot.runs.find((run) => run.id === "run-1")?.status).toBe("succeeded");
    });

    await waitFor(() => {
      expect(screen.getByText("Baseline violations")).toBeInTheDocument();
      expect(screen.getByText("Post-action violations")).toBeInTheDocument();
      expect(screen.getByText("Simulated interface runtime")).toBeInTheDocument();
    });
    expect(screen.getByText("Interface-only history")).toBeInTheDocument();
    expect(screen.getByText(/does not create a solver manifest/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));
    expect(await screen.findByRole("heading", { name: "Retained TSV screening demonstration record" })).toBeInTheDocument();
    expect(screen.getByText(/no solver ran in the browser/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /provenance manifest/i })).not.toBeInTheDocument();
  });

  it("retains execution wording for the connected API mode", async () => {
    const backend = renderWorkbench("connected");
    expect((await screen.findAllByText(demoSnapshot.project.name)).length).toBeGreaterThan(0);

    expect(screen.getByRole("button", { name: /Run approved workflow/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review and run/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Approved runs" })).toBeInTheDocument();
    expect(screen.getByText("Execution history", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(screen.getByText("Server-approved workflow", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(screen.queryByText("Approved simulation contract", { selector: ".eyebrow" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent analyses" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Simulate approved workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Review simulation/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Simulated run history" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Review and run/i }));
    const dialog = screen.getByRole("dialog", { name: /Run Synthetic TSV-to-device screening/i });
    expect(within(dialog).getByText("Approved execution boundary", { selector: ".eyebrow" })).toBeInTheDocument();
    expect(within(dialog).queryByText("Browser simulation boundary", { selector: ".eyebrow" })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/The service maps it/i)).toBeInTheDocument();
    expect(within(dialog).queryByText(/does not contact a solver/i)).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /Start approved workflow/i })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /Start simulation/i })).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /Start approved workflow/i }));

    expect(await screen.findByText("run-1")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Approved workflow queued · run-1");
    await waitFor(async () => {
      const snapshot = await backend.getSnapshot(demoSnapshot.project.id);
      expect(snapshot.runs.find((run) => run.id === "run-1")?.status).toBe("succeeded");
    });
  });

  it("does not offer cancellation after a connected executor has started", async () => {
    renderRunningWorkbench("connected");

    expect(await screen.findByText("run-connected")).toBeInTheDocument();
    expect(screen.getByText("Cannot cancel after start")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("keeps active cancellation available in the browser-only simulation", async () => {
    renderRunningWorkbench("demo");

    expect(await screen.findByText("run-demo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});
