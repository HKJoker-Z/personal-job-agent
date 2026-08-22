import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { ApplicationsPage } from "./ApplicationPages";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

describe("Version 2.1.0 Applications", () => {
  beforeEach(() => {
    let applicationExists = true;
    apiJson.mockReset();
    apiJson.mockImplementation((path, options) => {
      if (path === "/api/resumes") return Promise.resolve([{ title: "Primary", active_version_id: "resume-v1", is_primary: true }]);
      if (path === "/api/applications" && options?.method === "POST") return Promise.resolve({ application: { id: "new" } });
      if (path === "/api/applications/app-1" && options?.method === "DELETE") {
        applicationExists = false;
        return Promise.resolve({ deleted: true, id: "app-1" });
      }
      if (path === "/api/applications") return Promise.resolve(applicationExists ? [{ id: "app-1", company_name: "Example Co", job_title: "Engineer", applied_at: "2026-08-20T10:00:00Z" }] : []);
      if (path === "/api/applications/app-1") return Promise.resolve({ id: "app-1", company_name: "Example Co", job_title: "Engineer", applied_at: "2026-08-20T10:00:00Z", job_description: "Build APIs", resume_snapshot: "Jane Doe\n\nEXPERIENCE\nBuilt APIs\nLed reliability" });
      return Promise.resolve([]);
    });
  });

  it("lists and opens full Application details", async () => {
    render(<ApplicationsPage />);
    expect(await screen.findByText("Example Co")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByText("Build APIs")).toBeInTheDocument();
    const snapshot = screen.getByTestId("resume-snapshot");
    expect(snapshot).toHaveClass("resume-snapshot");
    expect(snapshot.textContent).toBe("Jane Doe\n\nEXPERIENCE\nBuilt APIs\nLed reliability");
  });

  it("creates a manual Application with an optional Resume", async () => {
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");
    fireEvent.click(screen.getByRole("button", { name: "Add Application" }));
    fireEvent.change(screen.getByLabelText("Company Name"), { target: { value: "Manual Co" } });
    fireEvent.change(screen.getByLabelText("Job Title"), { target: { value: "Developer" } });
    fireEvent.change(screen.getByLabelText("Job Description"), { target: { value: "Manual JD" } });
    fireEvent.change(screen.getByLabelText("Resume"), { target: { value: "resume-v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Application" }));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications", {
      method: "POST",
      body: {
        company_name: "Manual Co",
        job_title: "Developer",
        job_description: "Manual JD",
        resume_version_id: "resume-v1",
      },
    }));
    expect(await screen.findByText("Application recorded successfully.")).toBeInTheDocument();
  });

  it("confirms and deletes an Application before refreshing the list", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Company Name: Example Co"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Job Title: Engineer"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith(
      "/api/applications/app-1", { method: "DELETE" }
    ));
    expect(await screen.findByText("No Applications yet.")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Application deleted successfully.");
    confirm.mockRestore();
  });
});
