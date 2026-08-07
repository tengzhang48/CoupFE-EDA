import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import siteData from "../site-data.json";
import SiteApp, { formatSignedPercent } from "./SiteApp";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
  cleanup();
});

describe("public CoupFE-EDA site", () => {
  it("formats comparison percentages from their actual sign", () => {
    expect(formatSignedPercent(-66.8476348734628, 2)).toBe("−66.85%");
    expect(formatSignedPercent(12.345, 2)).toBe("+12.35%");
  });

  it("keeps the evidence-first narrative and leads with one real solver field", () => {
    const { container } = render(<SiteApp />);
    expect(screen.getByRole("heading", { level: 1, name: /EDA-aware multiphysics, with results you can inspect/i })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const heroResult = screen.getByRole("figure", { name: "Solver-derived TSV stress field" });
    expect(within(heroResult).getByRole("img", { name: /Axisymmetric TSV radial stress field/i })).toBeInTheDocument();
    expect(heroResult).toHaveTextContent("30 µm TSV · σrr(20 µm) = 354.172 MPa");
    expect(heroResult).toHaveTextContent("0.0633% from the declared Lamé reference · 2,400 DOFs · 9 static solves");
    expect(heroResult).toHaveTextContent("Measured-device comparison: not performed.");
    expect(heroResult).toHaveTextContent("not a finite-depth 3-D model, transient simulation, or experimental result");
    expect(within(heroResult).getByRole("link", { name: /Open the complete solver-derived TSV contour/i })).toHaveAttribute("href", expect.stringContaining("contour.svg"));
    expect(screen.getByRole("link", { name: /Explore retained field/i })).toHaveAttribute("href", expect.stringContaining("surface=workbench"));
    expect(screen.getByRole("heading", { name: /From design record to checked result\./i })).toBeInTheDocument();
    const processFigure = screen.getByRole("figure", { name: /From design record to checked result\./i });
    const handoffList = within(processFigure).getByRole("list", { name: "Analysis handoffs" });
    expect(handoffList.querySelectorAll(":scope > li")).toHaveLength(4);
    expect(processFigure).toHaveTextContent("Upper rail: identity and provenance remain attached across the forward handoffs.");
    expect(processFigure).toHaveTextContent("Dashed path: only declared screening quantities return.");
    expect(screen.getByRole("region", { name: "Information retained across every handoff" })).toHaveTextContent("Identity and provenance");
    const returnPath = screen.getByRole("complementary", { name: "Bounded return path to source identity" });
    expect(returnPath).toHaveTextContent("Return to source ID");
    expect(returnPath).toHaveTextContent("No live database edits");
    expect(screen.getByRole("region", { name: "Record rules" })).toBeInTheDocument();
    for (const step of [
      "Design and case inputs",
      "Identity and provenance",
      "Analysis representation",
      "Selected analysis",
      "Reviewable evidence",
      "Bounded feedback",
    ]) {
      expect(screen.getByText(step)).toBeInTheDocument();
    }

    expect(screen.getByRole("heading", { name: /Inspect the run behind the field/i })).toBeInTheDocument();
    expect(screen.getByText(siteData.tsvField.caseId)).toBeInTheDocument();
    expect(screen.getByText(/2,400 radial nodes/i)).toBeInTheDocument();
    const video = container.querySelector("#solver-field video");
    expect(video).not.toBeNull();
    expect(video).toHaveAttribute("src", expect.stringContaining("load-sweep.webm"));
    expect(video).not.toHaveAttribute("poster");
    expect(video).not.toHaveAttribute("autoplay");
    expect(video).not.toHaveAttribute("loop");
    expect(video).toHaveAttribute("aria-describedby", "tsv-load-sweep-caption");
    expect(screen.getByText(siteData.tsvField.videoInterpretation)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open solver-derived contour/i })).toHaveAttribute("href", expect.stringContaining("contour.svg"));
    expect(screen.getByRole("link", { name: "Raw field JSON" })).toHaveAttribute("href", expect.stringContaining("field.json"));
    expect(screen.getByRole("link", { name: "SHA-256 manifest" })).toHaveAttribute("href", expect.stringContaining("visual-evidence.json"));

    expect(screen.getByText("526,338-DOF fixed-size solve")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Median solve wall time decreases/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Checked foundations; real-device validation remains open/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3-D TSV reference case" })).toBeInTheDocument();
  }, 15_000);

  it("features a separate checked ETV result and keeps supporting outputs in proportion", () => {
    render(<SiteApp />);
    expect(screen.getByRole("heading", { name: /How does a 0.1 mm solder block respond to a one-second thermal cycle/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /More views generated from checked CoupFE-EDA runs/i })).not.toBeInTheDocument();

    const etvResult = screen.getByRole("article", { name: "Thermal-mismatch shear in SAC305" });
    const etvMedia = siteData.simulationMedia.find((media) => media.id === siteData.etvComparison.mediaId)!;
    expect(within(etvResult).getByRole("heading", { level: 3, name: "Thermal-mismatch shear in SAC305" })).toBeInTheDocument();
    expect(within(etvResult).getByRole("heading", { level: 4, name: "What is being solved" })).toBeInTheDocument();
    expect(within(etvResult).getByRole("heading", { level: 4, name: /two alternative uniform-temperature treatments/i })).toBeInTheDocument();
    expect(within(etvResult).getByRole("heading", { level: 4, name: /Temperature histories and end-cycle inelastic-energy fields/i })).toBeInTheDocument();
    expect(etvResult).toHaveTextContent(siteData.etvComparison.caseId);
    expect(etvResult).toHaveTextContent("0.1 × 0.1 mm");
    expect(etvResult).toHaveTextContent("20 × 20 Quad4 plane strain · 441 nodes · 882 DOFs");
    expect(etvResult).toHaveTextContent("20 elements · 5 µm row depth");
    expect(etvResult).toHaveTextContent("400 Quad4 elements");
    expect(etvResult).toHaveTextContent("2 cycles · 8 increments/cycle");
    expect(etvResult).toHaveTextContent("bottom:");
    expect(etvResult).toHaveTextContent("uₓ = uᵧ = 0");
    expect(within(etvResult).getAllByRole("img", { name: /Plane-strain solder-block model setup/i })).toHaveLength(2);
    const meshGrids = etvResult.querySelectorAll('[data-etv-mesh-grid="20x20"]');
    expect(meshGrids).toHaveLength(2);
    for (const grid of meshGrids) {
      expect(grid).toHaveAttribute("data-etv-top-row-elements", "20");
      expect(grid.querySelector(".site-etv-schematic-grid")?.getAttribute("d")?.match(/M/g)).toHaveLength(38);
    }
    const fieldFigure = within(etvResult).getByRole("img", { name: /accumulated inelastic-energy-density fields/i });
    expect(fieldFigure).toBeInTheDocument();
    expect(fieldFigure.closest("picture")?.querySelector("source")).toHaveAttribute("srcset", expect.stringContaining(siteData.etvComparison.mobileAsset));
    expect(fieldFigure.closest("picture")?.querySelector("source")).toHaveAttribute("media", "(max-width: 900px)");
    expect(within(etvResult).getByRole("note", { name: "Simulation setup carried into the output" })).toHaveTextContent("bottom fixed · top thermal-mismatch shear · sides free");
    expect(within(etvResult).getByRole("link", { name: /Desktop SVG/i })).toHaveAttribute("href", expect.stringContaining(etvMedia.asset));
    expect(within(etvResult).getByRole("link", { name: /Portrait SVG/i })).toHaveAttribute("href", expect.stringContaining(siteData.etvComparison.mobileAsset));
    expect(etvResult).toHaveTextContent("two actual end-cycle solver snapshots");
    expect(etvResult).toHaveTextContent("Both fields use one common scale with no interpolation or smoothing");
    expect(etvResult).toHaveTextContent("deformation is magnified 10×");
    expect(etvResult).toHaveTextContent("Selected single mesh; no mesh-convergence study");
    expect(etvResult).toHaveTextContent("does not establish mesh convergence");
    expect(etvResult).not.toHaveTextContent("peak states");
    expect(etvResult).toHaveTextContent(formatSignedPercent(siteData.etvComparison.slow.relativeDifferencePercent, 4));
    expect(etvResult).toHaveTextContent(formatSignedPercent(siteData.etvComparison.fast.relativeDifferencePercent, 2));
    expect(etvResult).toHaveTextContent(`${siteData.etvComparison.fast.lumpedTransientPeakTemperatureC.toFixed(2)} °C`);
    expect(etvResult).toHaveTextContent(`${siteData.etvComparison.fast.quasisteadyPeakTemperatureC.toFixed(2)} °C`);
    expect(etvResult).toHaveTextContent("100 × (lumped transient − quasisteady) / quasisteady");
    expect(etvResult).toHaveTextContent(`${siteData.etvComparison.fast.quasisteadyEnergyMPa.toFixed(6)} → ${siteData.etvComparison.fast.lumpedTransientEnergyMPa.toFixed(6)} MPa`);
    expect(etvResult).toHaveTextContent("−40 → 125 → −40 °C");
    expect(etvResult).toHaveTextContent("This comparison does not establish which treatment is more accurate");
    expect(within(etvResult).getByRole("note", { name: "ETV regression status" })).toHaveTextContent("Regression oracle passed");
    expect(within(etvResult).getByRole("note", { name: "ETV regression status" })).toHaveTextContent("python examples/etv_partitioned_cycle/run.py --mesh-size 20 --check");
    expect(within(etvResult).getByText("Claim boundary")).toBeInTheDocument();
    const retainedSvgLink = within(etvResult).getByRole("link", { name: "Retained dW-field SVG" });
    expect(retainedSvgLink).toHaveAttribute("href", expect.stringContaining(etvMedia.asset));
    expect(within(etvResult).getByRole("link", { name: "Retained state JSON" })).toHaveAttribute("href", expect.stringContaining(siteData.etvComparison.recordAsset));
    expect(within(etvResult).getByRole("link", { name: "Runner" })).toHaveAttribute("href", expect.stringContaining(etvMedia.runnerPath));
    expect(within(etvResult).getByRole("link", { name: "Regression oracle" })).toHaveAttribute("href", expect.stringContaining(etvMedia.resultPath));
    expect(within(etvResult).getByRole("link", { name: "SHA-256 record" })).toHaveAttribute("href", expect.stringContaining(etvMedia.evidencePath));

    const register = screen.getByRole("region", { name: "Two additional checks, kept in proportion" });
    expect(within(register).getAllByRole("listitem")).toHaveLength(2);
    expect(register).toHaveTextContent("same-block loading variant is not repeated here");
    expect(register).toHaveTextContent("Analytic EDA handoff · not FE");
    expect(register).toHaveTextContent("12 → 0");
    expect(within(register).getAllByText("Claim boundary")).toHaveLength(2);
    for (const mediaId of ["solder_3d_dissipation", "tsv_device_screening"]) {
      const media = siteData.simulationMedia.find((candidate) => candidate.id === mediaId)!;
      const output = within(register).getByRole("img", { name: media.alt }).closest("li");
      expect(output).not.toBeNull();
      expect(within(output!).getByRole("link", { name: "Runner" })).toHaveAttribute("href", expect.stringContaining(media.runnerPath));
      expect(within(output!).getByRole("link", { name: "Regression oracle" })).toHaveAttribute("href", expect.stringContaining(media.resultPath));
      expect(within(output!).getByRole("link", { name: "SHA-256 record" })).toHaveAttribute("href", expect.stringContaining(media.evidencePath));
    }
    const omittedVariant = siteData.simulationMedia.find((media) => media.id === "design_linked_solder_screening")!;
    expect(within(register).queryByRole("img", { name: omittedVariant.alt })).not.toBeInTheDocument();
  });

  it("groups integration demonstrations separately from real and focused verification", () => {
    render(<SiteApp />);
    const integrationGroup = screen.getByRole("heading", { name: /Design identities carried into engineering screens/i }).closest("section");
    const verificationGroup = screen.getByRole("heading", { name: /Selected physics and solver examples/i }).closest("section");
    expect(integrationGroup).not.toBeNull();
    expect(verificationGroup).not.toBeNull();

    for (const title of ["TSV-to-device screening", "Design-linked solder screening"]) {
      expect(within(integrationGroup!).getByRole("heading", { name: title })).toBeInTheDocument();
      expect(within(verificationGroup!).queryByRole("heading", { name: title })).not.toBeInTheDocument();
    }
    for (const title of ["Axisymmetric TSV stress field", "Partitioned ETV cycle", "Hex8 dissipation by layer"]) {
      expect(within(verificationGroup!).getByRole("heading", { name: title })).toBeInTheDocument();
      expect(within(integrationGroup!).queryByRole("heading", { name: title })).not.toBeInTheDocument();
    }
  });

  it("gives every displayed workflow guide, runner, retained result, and claim boundary", () => {
    render(<SiteApp />);
    const examples = document.querySelector<HTMLElement>("#examples")!;
    for (const title of [
      "Axisymmetric TSV stress field",
      "Partitioned ETV cycle",
      "Hex8 dissipation by layer",
      "Design-linked solder screening",
      "TSV-to-device screening",
    ]) {
      const card = within(examples).getByRole("heading", { name: title }).closest("article");
      expect(card).not.toBeNull();
      expect(within(card!).getByRole("link", { name: "Guide" })).toHaveAttribute("href", expect.stringContaining("github.com/tengzhang48/CoupFE-EDA/blob/main/"));
      expect(within(card!).getByRole("link", { name: "Code" })).toHaveAttribute("href", expect.stringContaining("/run.py"));
      expect(within(card!).getByRole("link", { name: "Retained result" }).getAttribute("href")).toMatch(/expected_(?:results|metrics)(?:_20x20)?\.json$/);
      expect(within(card!).getByText("Claim boundary")).toBeInTheDocument();
    }
  });

  it("orders the public sections and exposes navigation and evidence destinations", () => {
    const { container } = render(<SiteApp />);
    const orderedIds = ["how-it-works", "solver-field", "simulations", "interface", "examples", "performance", "validation"];
    for (const id of orderedIds) expect(container.querySelector(`#${id}`)).not.toBeNull();
    for (let index = 0; index < orderedIds.length - 1; index += 1) {
      const current = container.querySelector(`#${orderedIds[index]}`)!;
      const next = container.querySelector(`#${orderedIds[index + 1]}`)!;
      expect(current.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }

    const desktopNavigation = screen.getByRole("navigation", { name: "Project website" });
    for (const [name, href] of [
      ["How it works", "#how-it-works"],
      ["Simulations", "#simulations"],
      ["Examples", "#examples"],
      ["Evidence", "#validation"],
      ["Performance", "#performance"],
    ]) {
      expect(within(desktopNavigation).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    const mobileNavigation = screen.getByRole("navigation", { name: "Mobile project website" });
    const mobileDetails = mobileNavigation.closest("details")!;
    mobileDetails.setAttribute("open", "");
    const mobileExamplesLink = within(mobileNavigation).getByRole("link", { name: "Examples" });
    mobileExamplesLink.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(mobileExamplesLink);
    expect(mobileDetails).not.toHaveAttribute("open");
    expect(screen.getByRole("navigation", { name: "Real field workbench" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Validation records" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Project resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main-content");
  });

  it("labels Pages as retained evidence and does not expose a fake run action", () => {
    window.history.replaceState({}, "", "/?surface=workbench");
    render(<SiteApp />);
    expect(screen.getByText(/Retained evidence · read only/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "TSV field workbench" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Retained solver run" })).toHaveTextContent(/cannot execute Python or CoupFE/i);
    expect(screen.queryByRole("button", { name: /run the fixed/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /simulate/i })).not.toBeInTheDocument();
  });

  it("does not autoplay or loop solver media when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { container } = render(<SiteApp />);
    const video = container.querySelector("#solver-field video");
    await waitFor(() => expect(video).not.toHaveAttribute("autoplay"));
    expect(video).not.toHaveAttribute("loop");
  });
});
