import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { ProfilePage } from "./ProfilePage";
import { ResumeDetailPage, ResumeImportPage, ResumeLibraryPage } from "./ResumePages";
import { apiJson } from "../api/client";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

describe("Phase 1 pages", () => {
  it("loads and saves a Career Profile", async () => {
    apiJson.mockResolvedValueOnce({ revision: 1, headline: "Engineer", current_location: "Remote", professional_summary: "Summary", completeness: { score: 50, missing_sections: ["skills"] } }).mockResolvedValueOnce({ revision: 2, headline: "Senior Engineer", current_location: "Remote", professional_summary: "Summary", completeness: { score: 50, missing_sections: ["skills"] } });
    render(<ProfilePage />); const headline = await screen.findByDisplayValue("Engineer"); fireEvent.change(headline, { target: { value: "Senior Engineer" } }); fireEvent.click(screen.getByText("Save Profile"));
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });

  it("shows a stale update error", async () => {
    apiJson.mockResolvedValueOnce({ revision: 1, headline: "Engineer", current_location: "", professional_summary: "", completeness: { score: 0, missing_sections: [] } }).mockRejectedValueOnce(new Error("This record changed elsewhere. Reload before saving again."));
    render(<ProfilePage />); await screen.findByDisplayValue("Engineer"); fireEvent.click(screen.getByText("Save Profile")); expect(await screen.findByRole("alert")).toHaveTextContent("changed elsewhere");
  });

  it("renders the Resume Library", async () => {
    apiJson.mockResolvedValueOnce([{ id: "r1", title: "Platform Resume", language: "en", target_role: "Engineer", active_version_id: "v1" }]);
    render(<MemoryRouter><ResumeLibraryPage /></MemoryRouter>); expect(await screen.findByText("Platform Resume")).toBeInTheDocument();
  });

  it("renders Resume Version history", async () => {
    apiJson.mockResolvedValueOnce({ id: "r1", title: "Resume" }).mockResolvedValueOnce([{ id: "v1", version_number: 1, status: "draft" }]);
    render(<MemoryRouter initialEntries={["/resumes/r1"]}><Routes><Route path="/resumes/:resumeId" element={<ResumeDetailPage />} /></Routes></MemoryRouter>); expect(await screen.findByText("Version 1")).toBeInTheDocument();
  });

  it("requires finalize confirmation", async () => {
    window.confirm = vi.fn().mockReturnValue(false); apiJson.mockResolvedValueOnce({ id: "r1", title: "Resume" }).mockResolvedValueOnce([{ id: "v1", version_number: 1, status: "draft" }]);
    render(<MemoryRouter initialEntries={["/resumes/r1"]}><Routes><Route path="/resumes/:resumeId" element={<ResumeDetailPage />} /></Routes></MemoryRouter>); fireEvent.click(await screen.findByText("Finalize")); expect(window.confirm).toHaveBeenCalledOnce(); expect(apiJson).toHaveBeenCalledTimes(2);
  });

  it("rejects an unsupported import before API submission", async () => {
    render(<ResumeImportPage />); const file = new File(["text"], "resume.txt", { type: "text/plain" }); fireEvent.change(screen.getByLabelText("Resume file"), { target: { files: [file] } }); fireEvent.click(screen.getByText("Import")); expect(await screen.findByText("Select a PDF or DOCX resume.")).toBeInTheDocument();
  });
});
