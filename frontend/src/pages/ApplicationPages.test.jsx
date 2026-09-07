import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { ApplicationsPage } from "./ApplicationPages";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

describe("Version 2.2.0 Applications", () => {
  beforeEach(() => {
    let applicationExists = true;
    let application = { id: "app-1", company_name: "Example Co", job_title: "Engineer", applied_at: "2026-08-20T10:00:00Z", revision: 1 };
    apiJson.mockReset();
    apiJson.mockImplementation((path, options) => {
      if (path === "/api/applications/app-1" && options?.method === "PATCH") {
        application = { ...application, company_name: options.body.company_name, job_title: options.body.job_title, revision: application.revision + 1 };
        return Promise.resolve(application);
      }
      if (path === "/api/resumes") return Promise.resolve([{ title: "Primary", active_version_id: "resume-v1", is_primary: true }]);
      if (path === "/api/applications" && options?.method === "POST") return Promise.resolve({ application: { id: "new" } });
      if (path === "/api/applications/app-1" && options?.method === "DELETE") {
        applicationExists = false;
        return Promise.resolve({ deleted: true, id: "app-1" });
      }
      if (path === "/api/applications") return Promise.resolve(applicationExists ? [application] : []);
      if (path === "/api/applications/app-1") return Promise.resolve({ id: "app-1", company_name: "Example Co", job_title: "Engineer", applied_at: "2026-08-20T10:00:00Z", job_description: "Build APIs", resume_snapshot: "Jane Doe\n\nEXPERIENCE\nBuilt APIs\nLed reliability" });
      return Promise.resolve([]);
    });
  });

  it.each([
    ["Updated Co", "Engineer"],
    ["Example Co", "Updated Role"],
    ["Updated Co", "Updated Role"],
  ])("saves Company %s and Position %s and immediately updates the list", async (company, position) => {
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Company"), { target: { value: company } });
    fireEvent.change(screen.getByLabelText("Position"), { target: { value: position } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Application updated successfully.");
    expect(screen.getByText(company)).toBeInTheDocument();
    expect(screen.getByText(position)).toBeInTheDocument();
    expect(apiJson).toHaveBeenCalledWith("/api/applications/app-1", {
      method: "PATCH", body: { company_name: company, job_title: position, expected_revision: 1 },
    });
    expect(screen.queryByLabelText("Company")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Company")).toHaveValue(company);
    expect(screen.getByLabelText("Position")).toHaveValue(position);
  });

  it("discards edits on Cancel without sending a request", async () => {
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Discard Co" } });
    fireEvent.change(screen.getByLabelText("Position"), { target: { value: "Discard Role" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(apiJson.mock.calls.some(([, options]) => options?.method === "PATCH")).toBe(false);
    expect(screen.getByText("Example Co")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Company")).toHaveValue("Example Co");
    expect(screen.getByLabelText("Position")).toHaveValue("Engineer");
  });

  it("keeps edits after a failed save and allows retry", async () => {
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Retry Co" } });
    apiJson.mockRejectedValueOnce(new Error("Save failed. Please retry."));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed. Please retry.");
    expect(screen.getByLabelText("Company")).toHaveValue("Retry Co");
    expect(screen.getByText("Example Co")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Application updated successfully.");
    expect(screen.getByText("Retry Co")).toBeInTheDocument();
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

  it("keeps an Application when deletion is cancelled", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ApplicationsPage />);
    await screen.findByText("Example Co");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Company Name: Example Co"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Job Title: Engineer"));
    expect(apiJson).not.toHaveBeenCalledWith(
      "/api/applications/app-1", { method: "DELETE" }
    );
    expect(screen.getByText("Example Co")).toBeInTheDocument();
    confirm.mockRestore();
  });
});
