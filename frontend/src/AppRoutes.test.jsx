import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "./AppRoutes";

vi.mock("./auth/AuthProvider", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({ user: { display_name: "Admin", role: "admin" }, logout: vi.fn(), loading: false }),
}));

vi.mock("./api/client", () => ({
  apiJson: vi.fn().mockResolvedValue([]),
}));

describe("application routes", () => {
  it("renders the static Architecture page", () => {
    render(<MemoryRouter initialEntries={["/architecture"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Architecture", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/modular monolith with supporting data, worker, frontend/i)).toBeInTheDocument();
    expect(screen.getByText("POST /api/analyze")).toBeInTheDocument();
    expect(screen.getByText(/does not create an Agent Run or enter the Redis and Dramatiq queue/i)).toBeInTheDocument();
    expect(screen.getByText(/New Agent Run creation, retry, and resume are disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/Jobs, Job Rankings, Applications, Approvals, and Tasks are not current/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Architecture" })).toHaveAttribute("aria-current", "page");
  });

  it("keeps an existing authenticated route available", async () => {
    render(<MemoryRouter initialEntries={["/resumes"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Resume Library" })).toBeInTheDocument();
    expect(await screen.findByText("No stored resumes yet.")).toBeInTheDocument();
  });

  it.each([
    "/jobs", "/jobs/old", "/job-ranking", "/applications", "/application-packages/old",
    "/approvals/old", "/tasks",
  ])("renders Feature Removed for %s", (path) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Feature removed" })).toBeInTheDocument();
  });

  it("renders Not Found for an unknown URL", () => {
    render(<MemoryRouter initialEntries={["/does-not-exist"]}><App /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
