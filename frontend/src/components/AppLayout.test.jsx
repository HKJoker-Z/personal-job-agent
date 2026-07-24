import React from "react";
import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppLayout } from "./AppLayout";

const styles = readFileSync("src/styles.css", "utf8");

const logout = vi.fn();
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ user: { display_name: "Admin", role: "admin" }, logout }),
}));

function view(path = "/analyze") {
  return render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route element={<AppLayout />}><Route path="*" element={<p>Page body</p>} /></Route>
  </Routes></MemoryRouter>);
}

describe("unified navigation", () => {
  it("renders one primary navigation with a clear active state", () => {
    view();
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Analyze" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Analyze" })).toHaveClass("active");
  });

  it("keeps the existing navigation destinations and adds Architecture", () => {
    view("/architecture");
    const expectedLinks = {
      Dashboard: "/dashboard",
      Analyze: "/analyze",
      History: "/history",
      Resumes: "/resumes",
      Profile: "/profile",
      "Project Knowledge": "/project-knowledge",
      "Agent Runs": "/agent-runs",
      Architecture: "/architecture",
      Monitoring: "/monitoring",
    };
    for (const [label, path] of Object.entries(expectedLinks)) {
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", path);
    }
    expect(screen.getByRole("link", { name: "Architecture" })).toHaveAttribute("aria-current", "page");
  });

  it("uses the same component for its collapsible mobile menu", () => {
    view();
    const menu = screen.getByRole("button", { name: /Menu/ });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation")).toHaveClass("is-open");
  });

  it("does not expose retired module navigation", () => {
    view();
    for (const label of ["Jobs", "Job Rankings", "Applications", "Approvals", "Tasks"]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
  });

  it("uses a rounded active navigation treatment instead of underlined text", () => {
    expect(styles).toMatch(/\.nav-links a[\s\S]*?border-radius:\s*10px/);
    expect(styles).toMatch(/\.nav-links a[\s\S]*?text-decoration:\s*none/);
    expect(styles).toMatch(/\.nav-links a\.active[\s\S]*?background:/);
  });

  it("bounds account actions and collapses before the navigation can overflow", () => {
    expect(styles).toMatch(/\.nav-shell[\s\S]*?width:\s*min\(1320px,/);
    expect(styles).toMatch(/\.account-actions a[\s\S]*?max-width:\s*180px/);
    expect(styles).toMatch(/@media \(max-width:\s*1360px\)[\s\S]*?\.primary-navigation/);
    expect(styles).toMatch(/\.summary-grid[\s\S]*?repeat\(4, minmax\(0, 1fr\)\)/);
  });
});
