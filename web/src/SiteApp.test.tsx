import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SiteApp from "./SiteApp";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  cleanup();
});

describe("public CoupFE-EDA site", () => {
  it("opens with a direct, visual multiphysics story", () => {
    render(<SiteApp />);

    expect(screen.getByRole("heading", { level: 1, name: /Find the hot spots.*See the stress.*Decide with evidence/i })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("img", { name: /semiconductor package cutaway with finite-element-style field contours/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Concept visualization.*not solver output/i).length).toBeGreaterThan(0);
    expect(screen.getByText("5", { selector: ".site-proof-strip strong" })).toBeInTheDocument();
    expect(screen.getByText("526,338", { selector: ".site-proof-strip strong" })).toBeInTheDocument();
    expect(screen.getByText("12 → 0", { selector: ".site-proof-strip strong" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Four physics. One traceable design story." })).toBeInTheDocument();
    for (const capability of ["Electrical", "Thermal", "Mechanical", "Reliability"]) {
      expect(screen.getByText(new RegExp(capability), { selector: ".site-capability-grid article > span" })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "Look at the physics before reading about it." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Don’t just read the run record. Watch the field change." })).toBeInTheDocument();
    const workbenchVideo = screen.getByLabelText(/Looping interface demonstration of the interactive TSV/i);
    expect(workbenchVideo.querySelector("source")?.getAttribute("src")).toContain("tsv-workbench-demo.webm");
    expect(screen.getByRole("heading", { name: "Clear about what works. Clear about what is still open." })).toBeInTheDocument();
  });

  it("lets visitors switch among clearly labeled simulation evidence levels", () => {
    render(<SiteApp />);
    const tabs = screen.getByRole("tablist", { name: "Simulation views" });
    const coupledTab = within(tabs).getByRole("tab", { name: /Coupled field/i });
    const screeningTab = within(tabs).getByRole("tab", { name: /Device screening/i });
    const scalingTab = within(tabs).getByRole("tab", { name: /Solver scaling/i });

    expect(coupledTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Illustrative artwork · not solver output")).toBeInTheDocument();

    fireEvent.click(screeningTab);
    expect(screeningTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("img", { name: /Retained synthetic TSV device screening result/i })).toBeInTheDocument();
    expect(screen.getByText("Retained synthetic output")).toBeInTheDocument();

    fireEvent.click(scalingTab);
    expect(scalingTab).toHaveAttribute("aria-selected", "true");
    const reel = screen.getByRole("heading", { name: "Look at the physics before reading about it." }).closest("section");
    expect(within(reel!).getByRole("img", { name: /Median solve wall time decreases/i })).toBeInTheDocument();
    expect(screen.getByText("Measured benchmark")).toBeInTheDocument();
    expect(within(tabs).getByRole("button", { name: /Pause simulation reel/i })).toBeInTheDocument();
  });

  it("keeps design-linked demonstrations distinct from focused verification cases", () => {
    render(<SiteApp />);
    for (const title of ["TSV-to-device screening", "Design-linked solder screening"]) {
      const card = screen.getByRole("heading", { name: title }).closest("article");
      expect(card).toHaveClass("site-workflow-card-integration");
      expect(within(card!).getByText("Design-linked")).toBeInTheDocument();
    }
    for (const title of ["Partitioned ETV cycle", "3-D solder dissipation field", "Plane-strain solder cycle"]) {
      const card = screen.getByRole("heading", { name: title }).closest("article");
      expect(card).toHaveClass("site-workflow-card-verification");
      expect(within(card!).getByText("Physics verification")).toBeInTheDocument();
    }
  });

  it("gives every runnable case direct guide, code, and retained-result links", () => {
    render(<SiteApp />);
    for (const title of [
      "Plane-strain solder cycle",
      "Partitioned ETV cycle",
      "3-D solder dissipation field",
      "Design-linked solder screening",
      "TSV-to-device screening",
    ]) {
      const card = screen.getByRole("heading", { name: title }).closest("article");
      expect(card).not.toBeNull();
      const links = within(card!).getAllByRole("link");
      expect(links.map((link) => link.getAttribute("href"))).toEqual(
        expect.arrayContaining([expect.stringContaining("github.com/tengzhang48/CoupFE-EDA/blob/main/")]),
      );
      expect(within(card!).getByRole("link", { name: /Guide/i })).toBeInTheDocument();
      expect(within(card!).getByRole("link", { name: /Code/i })).toBeInTheDocument();
      expect(within(card!).getByRole("link", { name: /Result/i })).toBeInTheDocument();
    }
  });

  it("orders the public story and exposes navigation and evidence destinations", () => {
    const { container } = render(<SiteApp />);
    const orderedIds = ["capabilities", "simulations", "workflow", "workbench", "examples", "performance", "evidence"];
    for (const id of orderedIds) expect(container.querySelector(`#${id}`)).not.toBeNull();
    for (let index = 0; index < orderedIds.length - 1; index += 1) {
      const current = container.querySelector(`#${orderedIds[index]}`)!;
      const next = container.querySelector(`#${orderedIds[index + 1]}`)!;
      expect(current.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }

    const navigation = screen.getByRole("navigation", { name: "Project website" });
    for (const [name, href] of [
      ["Capabilities", "#capabilities"],
      ["Simulations", "#simulations"],
      ["Workflow", "#workflow"],
      ["Evidence", "#evidence"],
    ]) {
      expect(within(navigation).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    expect(within(navigation).getByRole("link", { name: "Docs" }).getAttribute("href")).toContain("docs/README.md");
    expect(screen.getByRole("navigation", { name: "Validation records" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Project resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Launch workbench/i }).getAttribute("href")).toContain("surface=workbench");
  });

  it("keeps the visual workbench behind an explicit demonstration boundary", async () => {
    window.history.replaceState({}, "", "/?surface=workbench");
    render(<SiteApp />);

    expect(await screen.findByText(/Interactive demonstration — no solver runs/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "TSV screening workbench" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "TSV stress-to-device screening" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Baseline synthetic TSV stress field" })).toBeInTheDocument();
    expect(screen.getByText(/Release validation: not claimed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Peak temperature/i)).not.toBeInTheDocument();
  });
});
