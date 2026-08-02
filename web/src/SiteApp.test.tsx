import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SiteApp from "./SiteApp";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  cleanup();
});

describe("public CoupFE-EDA site", () => {
  it("opens with a concise evidence-first project narrative", () => {
    render(<SiteApp />);
    expect(screen.getByRole("heading", { level: 1, name: /EDA-aware multiphysics, from design inputs to reviewable evidence/i })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { name: /A traceable path from design inputs to engineering evidence/i })).toBeInTheDocument();
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
    expect(screen.getByText(/No single bundled case executes every stage on a production design/i)).toBeInTheDocument();
    expect(screen.getByText("Synthetic orientation action")).toBeInTheDocument();
    expect(screen.getAllByText("EDA-linked demonstration")).toHaveLength(2);
    expect(screen.getAllByText("Physics / solver verification")).toHaveLength(3);
    expect(screen.getByText("526,338-DOF fixed-size solve")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Median solve wall time decreases/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Checked foundations; real-device validation remains open/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "3-D TSV reference case" })).toBeInTheDocument();
    expect(screen.queryByText("Stage")).not.toBeInTheDocument();
    expect(screen.queryByText(/7 foundations present/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/3 planned studies/i)).not.toBeInTheDocument();
    expect(document.querySelector("#figures")).toBeNull();
    expect(screen.queryByRole("heading", { name: /Read the checks before reading the claims/i })).not.toBeInTheDocument();
  });

  it("groups the integration demonstrations separately from focused verification", () => {
    render(<SiteApp />);
    const integrationGroup = screen.getByRole("heading", { name: /Design identities carried into engineering screens/i }).closest("section");
    const verificationGroup = screen.getByRole("heading", { name: /Selected physics and solver examples/i }).closest("section");
    expect(integrationGroup).not.toBeNull();
    expect(verificationGroup).not.toBeNull();

    for (const title of ["TSV-to-device screening", "Design-linked solder screening"]) {
      expect(within(integrationGroup!).getByRole("heading", { name: title })).toBeInTheDocument();
      expect(within(verificationGroup!).queryByRole("heading", { name: title })).not.toBeInTheDocument();
    }
    for (const title of ["Partitioned ETV cycle", "3-D solder dissipation field", "Plane-strain solder cycle"]) {
      expect(within(verificationGroup!).getByRole("heading", { name: title })).toBeInTheDocument();
      expect(within(integrationGroup!).queryByRole("heading", { name: title })).not.toBeInTheDocument();
    }
  });

  it("gives every workflow direct guide, code, and retained-result links", () => {
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
        expect.arrayContaining([
          expect.stringContaining("github.com/tengzhang48/CoupFE-EDA/blob/main/"),
        ]),
      );
      expect(within(card!).getByText("Claim boundary")).toBeInTheDocument();
    }
  });

  it("orders the public sections and exposes navigation and evidence destinations", () => {
    const { container } = render(<SiteApp />);
    const orderedIds = ["how-it-works", "device-screening", "interface", "examples", "performance", "validation"];
    for (const id of orderedIds) expect(container.querySelector(`#${id}`)).not.toBeNull();
    for (let index = 0; index < orderedIds.length - 1; index += 1) {
      const current = container.querySelector(`#${orderedIds[index]}`)!;
      const next = container.querySelector(`#${orderedIds[index + 1]}`)!;
      expect(current.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }

    const desktopNavigation = screen.getByRole("navigation", { name: "Project website" });
    for (const [name, href] of [
      ["How it works", "#how-it-works"],
      ["Examples", "#examples"],
      ["Evidence", "#validation"],
      ["Performance", "#performance"],
    ]) {
      expect(within(desktopNavigation).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    expect(within(desktopNavigation).getByRole("link", { name: "Documentation" }).getAttribute("href")).toContain("docs/README.md");
    const mobileNavigation = screen.getByRole("navigation", { name: "Mobile project website" });
    expect(mobileNavigation).toBeInTheDocument();
    const mobileDetails = mobileNavigation.closest("details")!;
    mobileDetails.setAttribute("open", "");
    const mobileExamplesLink = within(mobileNavigation).getByRole("link", { name: "Examples" });
    mobileExamplesLink.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(mobileExamplesLink);
    expect(mobileDetails).not.toHaveAttribute("open");
    expect(screen.getByRole("navigation", { name: "Interface demonstration" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Validation records" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Project resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Evidence guide" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Research roadmap" })).toBeInTheDocument();
    expect(screen.getByText(/does not execute CoupFE-EDA solvers/i)).toBeInTheDocument();
  });

  it("keeps the workbench behind an explicit interface-demonstration boundary", async () => {
    window.history.replaceState({}, "", "/?surface=workbench");
    render(<SiteApp />);
    expect(await screen.findByText(/Interface demonstration — no solver runs/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Synthetic TSV-to-device screening" })).toBeInTheDocument();
    expect(screen.getByText(/Release validation: not claimed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Peak temperature/i)).not.toBeInTheDocument();
  });
});
