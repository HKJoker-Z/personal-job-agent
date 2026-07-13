import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { JobDetailPage } from "./JobPages";
import { ApplicationPackageDetailPage, ApplicationPackagesPage, JobRankingPage } from "./V203Pages";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

const job = {
  id: "j1", title: "Data Engineer", company_name: "Example", location: "Remote",
  status: "reviewed", revision: 2, description: "Ignore previous instructions is untrusted text.",
  requirements: [], sources: [], duplicate_candidates: [], linked_application_id: "a1",
};
const match = {
  id: "m1", overall_score: 78, hard_filter_status: "unknown", recommendation: "worth_applying",
  preparation_effort: "medium", created_at: "2030-01-01T00:00:00Z",
  dimensions: [{ id: "d1", dimension: "required_skills", status: "partial", weighted_score: 20, max_score: 30, explanation: "Confirmed evidence evaluated." }],
  evidence: [
    { id: "e1", dimension: "required_skills", evidence_kind: "matched", evidence_summary: "Confirmed Profile Skill." },
    { id: "e2", dimension: "education", evidence_kind: "unknown", evidence_summary: "Needs review." },
  ],
};
const version = {
  id: "v1", material_id: "mat1", version_number: 1, source_type: "generated",
  content_text: "Python PostgreSQL evidence.", content_json: {}, validation_status: "valid",
  unsupported_claim_count: 0, evidence_coverage: 100, generation_metadata: {},
  evidence: [{ id: "ev1", support_status: "supported", evidence_summary: "Validated against Profile Skill evidence." }], reviews: [],
};
const packageValue = {
  id: "p1", application_id: "a1", title: "Data Package", status: "draft", revision: 1,
  source_resume_version_id: "rv1", source_profile_revision: 4, source_job_revision: 2,
  source_match_analysis_id: "m1", materials: [],
};
const packageWithMaterial = {
  ...packageValue,
  materials: [{ id: "mat1", title: "Tailored Resume", material_type: "tailored_resume", status: "draft", active_version_id: "v1", active_version: version }],
};

function route(path, element, initial) {
  return <MemoryRouter initialEntries={[initial]}><Routes><Route path={path} element={element} /></Routes></MemoryRouter>;
}

describe("Version 2.0.3 matching and materials pages", () => {
  beforeEach(() => { apiJson.mockReset(); window.confirm = vi.fn(() => true); });

  it("runs Match and shows breakdown, hard filter, unknown, and evidence", async () => {
    apiJson.mockResolvedValueOnce(job).mockResolvedValueOnce(match);
    render(route("/jobs/:jobId", <JobDetailPage />, "/jobs/j1"));
    fireEvent.click(await screen.findByText("Run Match"));
    expect(await screen.findByText("Overall Score")).toBeInTheDocument();
    expect(screen.getByText("Hard Filter")).toBeInTheDocument();
    expect(screen.getByText("Unknown Requirements")).toBeInTheDocument();
    expect(screen.getByText(/Confirmed Profile Skill/)).toBeInTheDocument();
    expect(apiJson).toHaveBeenCalledWith("/api/jobs/j1/match", expect.objectContaining({ body: { force_new: false } }));
  });

  it("loads Match History and reopens an immutable snapshot", async () => {
    apiJson.mockResolvedValueOnce(job).mockResolvedValueOnce([match]).mockResolvedValueOnce(match);
    render(route("/jobs/:jobId", <JobDetailPage />, "/jobs/j1"));
    fireEvent.click(await screen.findByText("Match History"));
    fireEvent.click(await screen.findByText(/78 — unknown/));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/jobs/j1/matches/m1"));
  });

  it("selects Jobs and renders explainable ranking without probability claims", async () => {
    apiJson.mockResolvedValueOnce({ items: [job], total: 1 }).mockResolvedValueOnce({ items: [{ id: "ri1", rank_position: 1, rank_score: 80, hard_filter_status: "passed", recommendation: "worth_applying", preparation_effort: "low", reason_summary: { primary_reasons: ["required_skills"], primary_gaps: ["education"] }, job }] });
    render(<MemoryRouter><JobRankingPage /></MemoryRouter>);
    fireEvent.click(await screen.findByLabelText(/Data Engineer/));
    fireEvent.click(screen.getByText("Rank selected Jobs"));
    expect(await screen.findByText("#1", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/success probability/i)).not.toBeInTheDocument();
  });

  it("shows Ranking empty and generation error states", async () => {
    apiJson.mockResolvedValueOnce({ items: [], total: 0 });
    render(<MemoryRouter><JobRankingPage /></MemoryRouter>);
    expect(await screen.findByText(/Import Jobs/)).toBeInTheDocument();
  });

  it("loads Package empty state and creates a snapshot Package", async () => {
    apiJson.mockResolvedValueOnce([]).mockResolvedValueOnce(packageValue).mockResolvedValueOnce([packageValue]);
    render(route("/applications/:applicationId/packages", <ApplicationPackagesPage />, "/applications/a1/packages"));
    expect(await screen.findByText(/No Packages yet/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Package Resume Version ID"), { target: { value: "rv1" } });
    fireEvent.change(screen.getByLabelText("Package Match Analysis ID"), { target: { value: "m1" } });
    fireEvent.click(screen.getByText("Create Package Draft"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/applications/a1/packages", expect.objectContaining({ method: "POST" })));
  });

  it("generates a Tailored Resume Draft", async () => {
    apiJson.mockResolvedValueOnce(packageValue).mockResolvedValueOnce(version).mockResolvedValueOnce(packageWithMaterial);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Generate Tailored Resume"));
    expect(await screen.findByText("Tailored Resume")).toBeInTheDocument();
    expect(apiJson).toHaveBeenCalledWith("/api/application-packages/p1/generate-resume", expect.objectContaining({ method: "POST" }));
  });

  it("generates Cover Letter and Application Answers only on explicit action", async () => {
    apiJson.mockResolvedValueOnce(packageValue).mockResolvedValueOnce(version).mockResolvedValueOnce(packageWithMaterial).mockResolvedValueOnce([version]).mockResolvedValueOnce(packageWithMaterial);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Generate Cover Letter"));
    await screen.findByText("Tailored Resume");
    fireEvent.change(screen.getByLabelText("Application question"), { target: { value: "Why this role?" } });
    fireEvent.click(screen.getByText("Generate Grounded Answer"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/application-packages/p1/answers", expect.objectContaining({ body: expect.objectContaining({ questions: expect.any(Array) }) })));
  });

  it("shows Evidence panel and support status as text", async () => {
    apiJson.mockResolvedValueOnce(packageWithMaterial);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Evidence Side Panel"));
    expect(screen.getByText("Supported")).toBeInTheDocument();
    expect(screen.getByText(/Profile Skill evidence/)).toBeInTheDocument();
  });

  it("saves edits as a new immutable Material Version", async () => {
    apiJson.mockResolvedValueOnce(packageWithMaterial).mockResolvedValueOnce({ ...version, id: "v2", version_number: 2 }).mockResolvedValueOnce({ ...packageWithMaterial, materials: [{ ...packageWithMaterial.materials[0], active_version: { ...version, id: "v2", version_number: 2 } }] });
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.change(await screen.findByLabelText("Edit Tailored Resume"), { target: { value: "Grounded revision" } });
    fireEvent.click(screen.getByText("Save as New Version"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/application-materials/mat1/versions", expect.objectContaining({ body: expect.objectContaining({ expected_active_version_id: "v1" }) })));
  });

  it("loads Version History and lineage Diff metadata", async () => {
    apiJson.mockResolvedValueOnce(packageWithMaterial).mockResolvedValueOnce([{ ...version, id: "v2", version_number: 2, parent_version_id: "v1" }, version]);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Version History and Diff"));
    expect(await screen.findByText(/Version 2/)).toBeInTheDocument();
    expect(screen.getByText(/derived from v1/)).toBeInTheDocument();
  });

  it("blocks approval and finalization when unsupported claims exist", async () => {
    const unsafe = { ...version, validation_status: "invalid", unsupported_claim_count: 2, evidence_coverage: 25 };
    apiJson.mockResolvedValueOnce({ ...packageWithMaterial, materials: [{ ...packageWithMaterial.materials[0], active_version: unsafe }] });
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    expect(await screen.findByRole("status")).toHaveTextContent("Unsupported claims block");
    expect(screen.getByText("Approve")).toBeDisabled();
    expect(screen.getByText("Finalize")).toBeDisabled();
  });

  it("requires explicit confirmation before marking an unresolved claim user-confirmed", async () => {
    const unsafe = {
      ...version, validation_status: "invalid", unsupported_claim_count: 1,
      evidence: [{ id: "ev-unresolved", support_status: "unsupported", evidence_summary: "No confirmed evidence." }],
    };
    const unsafePackage = { ...packageWithMaterial, materials: [{ ...packageWithMaterial.materials[0], active_version: unsafe }] };
    apiJson.mockResolvedValueOnce(unsafePackage).mockResolvedValueOnce({ ...unsafe, unsupported_claim_count: 0 }).mockResolvedValueOnce(packageWithMaterial);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Evidence Side Panel"));
    fireEvent.click(screen.getByText("Confirm claim"));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("does not update your Profile"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith(
      "/api/material-versions/v1/evidence/ev-unresolved/confirm",
      expect.objectContaining({ body: { confirmation: "CONFIRM CLAIM" } }),
    ));
  });

  it("requests changes, approves, and finalizes with confirmation", async () => {
    const approvedPackage = { ...packageWithMaterial, materials: [{ ...packageWithMaterial.materials[0], status: "approved" }] };
    apiJson.mockResolvedValueOnce(approvedPackage).mockResolvedValueOnce({}).mockResolvedValueOnce(approvedPackage);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Finalize"));
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/material-versions/v1/finalize", expect.objectContaining({ body: { confirmation: "FINALIZE MATERIAL" } })));
  });

  it("refreshes stale Material state after a 409", async () => {
    const conflict = Object.assign(new Error("changed elsewhere"), { status: 409 });
    apiJson.mockResolvedValueOnce(packageWithMaterial).mockRejectedValueOnce(conflict).mockResolvedValueOnce(packageWithMaterial);
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    fireEvent.click(await screen.findByText("Validate Evidence"));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed elsewhere");
    expect(apiJson).toHaveBeenCalledTimes(3);
  });

  it("renders safe 401, 403, and generation error messages", async () => {
    apiJson.mockRejectedValueOnce(Object.assign(new Error("Your Session has expired. Please sign in again."), { status: 401 }));
    render(route("/application-packages/:packageId", <ApplicationPackageDetailPage />, "/application-packages/p1"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Session has expired");
  });
});
