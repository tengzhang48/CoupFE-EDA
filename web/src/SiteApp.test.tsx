import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import siteData from "../site-data.json";
import SiteApp from "./SiteApp";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  vi.unstubAllGlobals();
  cleanup();
});

describe("public CoupFE-EDA site", () => {
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

  it("shows only provenance-linked CoupFE-EDA simulation media", () => {
    render(<SiteApp />);
    expect(screen.getByRole("heading", { name: /More views generated from checked CoupFE-EDA runs/i })).toBeInTheDocument();
    for (const media of siteData.simulationMedia) {
      const card = screen.getByRole("heading", { name: media.title }).closest("article");
      expect(card).not.toBeNull();
      expect(within(card!).getByRole("img", { name: media.alt })).toHaveAttribute("src", expect.stringContaining(media.asset));
      expect(within(card!).getByRole("link", { name: "Runner" })).toHaveAttribute("href", expect.stringContaining(media.runnerPath));
      expect(within(card!).getByRole("link", { name: "Oracle" })).toHaveAttribute("href", expect.stringContaining(media.resultPath));
      expect(within(card!).getByRole("link", { name: "SHA-256 record" })).toHaveAttribute("href", expect.stringContaining(media.evidencePath));
      expect(within(card!).getByText("Claim boundary")).toBeInTheDocument();
    }
    const designLinkedCard = screen.getByRole("heading", { name: "Design-linked solder response" }).closest("article");
    const comparisonNote = within(designLinkedCard!).getByRole("note");
    expect(comparisonNote).toHaveTextContent("Why this field is lower");
    expect(comparisonNote).toHaveTextContent("L_D/h is 0.8485 versus 6.0");
    expect(comparisonNote).toHaveTextContent("same 3 × 3 × 2 mesh and SAC305 material model");
    expect(comparisonNote).toHaveTextContent("about 34.9× lower peak dissipation");
    expect(screen.getByText(/not stock imagery or AI-generated concepts/i)).toBeInTheDocument();
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
      expect(within(card!).getByRole("link", { name: "Retained result" }).getAttribute("href")).toMatch(/expected_(?:results|metrics)\.json$/);
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
