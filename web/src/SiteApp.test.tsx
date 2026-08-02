import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import SiteApp from "./SiteApp";

afterEach(() => {
  window.history.replaceState({}, "", "/");
  cleanup();
});

describe("public CoupFE-EDA site", () => {
  it("opens on repository-backed workflows rather than the interface prototype", () => {
    render(<SiteApp />);
    expect(screen.getByRole("heading", { name: /EDA-aware multiphysics workflows/i })).toBeInTheDocument();
    expect(screen.getAllByText("Checked guided workflow")).toHaveLength(5);
    expect(screen.getByText("526,338-DOF fixed-size solve")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Median solve wall time decreases/i })).toBeInTheDocument();
    expect(screen.getAllByText(/does not validate near-surface TSV stress/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/7 blocked categories and 3 not-started categories/i)).toBeInTheDocument();
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

  it("keeps the workbench behind an explicit interface-demonstration boundary", async () => {
    window.history.replaceState({}, "", "/?surface=workbench");
    render(<SiteApp />);
    expect(await screen.findByText(/Interface demonstration — no solver runs/i)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Synthetic TSV-to-device screening" })).toBeInTheDocument();
    expect(screen.getByText(/Release validation: not claimed/i)).toBeInTheDocument();
    expect(screen.queryByText(/Peak temperature/i)).not.toBeInTheDocument();
  });
});
