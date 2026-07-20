import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "./AppRoutes";

vi.mock("./auth/AuthProvider", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({ user: { display_name: "Admin", role: "admin" }, logout: vi.fn(), loading: false }),
}));

describe("application routes", () => {
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
