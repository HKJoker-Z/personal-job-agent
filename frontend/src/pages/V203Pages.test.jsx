import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { AnalyzePage } from "../legacy-workspace";
import { ResumeLibraryPage } from "./ResumePages";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return { ...actual, apiJson: vi.fn() };
});

describe("Version 2.0.3 Resume upload", () => {
  beforeEach(() => { apiJson.mockReset(); global.fetch = vi.fn(); });

  it("shows Upload Resume and a Primary Resume badge", async () => {
    apiJson.mockResolvedValueOnce([{
      id: "r1", title: "Platform Resume", language: "en", active_version_id: "v1", is_primary: true,
    }]);
    render(<MemoryRouter><ResumeLibraryPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Upload Resume" })).toBeInTheDocument();
    expect(await screen.findByText("Primary Resume")).toBeInTheDocument();
  });

  it("shows upload loading and success states", async () => {
    let resolveUpload;
    apiJson
      .mockResolvedValueOnce([])
      .mockImplementationOnce(() => new Promise((resolve) => { resolveUpload = resolve; }))
      .mockResolvedValueOnce([{ id: "r1", title: "resume", language: "en", active_version_id: "v1", is_primary: true }]);
    render(<MemoryRouter><ResumeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/resumes"));
    fireEvent.change(screen.getByLabelText("Upload Resume file"), {
      target: { files: [new File(["Python"], "resume.txt", { type: "text/plain" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload Resume" }));
    expect(screen.getByRole("button", { name: "Uploading..." })).toBeDisabled();
    resolveUpload({ resume: { title: "resume" } });
    expect(await screen.findByText(/uploaded and set as the Primary Resume/)).toBeInTheDocument();
    expect(apiJson).toHaveBeenCalledWith("/api/resumes/upload", expect.objectContaining({ method: "POST" }));
  });

  it("shows a clear upload error", async () => {
    apiJson.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("No selectable text was found in this PDF."));
    render(<MemoryRouter><ResumeLibraryPage /></MemoryRouter>);
    await waitFor(() => expect(apiJson).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Upload Resume file"), {
      target: { files: [new File(["%PDF"], "scan.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload Resume" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No selectable text");
    expect(screen.getByRole("button", { name: "Upload Resume" })).toBeEnabled();
  });
});

describe("Version 2.0.3 Analyze primary resume", () => {
  beforeEach(() => { apiJson.mockReset(); global.fetch = vi.fn(); });

  it("auto-selects the primary resume without asking for another upload", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: "r1", title: "Primary", active_version_id: "v1", is_primary: true }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "r1", title: "Primary", active_version_id: "v1", is_primary: true }), { status: 200 }));
    render(<AnalyzePage />);
    expect(await screen.findByText("Primary Resume selected automatically: Primary")).toBeInTheDocument();
    expect(screen.getByLabelText("Stored Resume Version")).toHaveValue("v1");
    expect(screen.queryByText(/Please select a Resume Version/)).not.toBeInTheDocument();
  });

  it("allows another stored resume for only the current analysis", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([
        { id: "r1", title: "Primary", active_version_id: "v1", is_primary: true },
        { id: "r2", title: "Alternative", active_version_id: "v2", is_primary: false },
      ]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "r1", title: "Primary", active_version_id: "v1", is_primary: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ analysis_status: "complete", match_score: 70, matched_skills: [], missing_skills: [], scoring_breakdown: {} }), { status: 200 }));
    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Alternative/ });
    fireEvent.change(screen.getByLabelText("Stored Resume Version"), { target: { value: "v2" } });
    fireEvent.change(screen.getByLabelText("Job Description"), { target: { value: "Fictional role" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByText("Match Score");
    expect(global.fetch.mock.calls[2][1].body.get("resume_version_id")).toBe("v2");
  });

  it("guides the user to Resume when no primary exists", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response("[]", { status: 200 }))
      .mockResolvedValueOnce(new Response("null", { status: 200 }));
    render(<AnalyzePage />);
    expect(await screen.findByText("No primary resume is available. Upload a resume from the Resume page.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Resume" })).toHaveAttribute("href", "/resumes");
  });
});
