import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { AnalyzePage, RagSourcesSection } from "../legacy-workspace";
import { DashboardPage } from "./DashboardPage";
import { FeatureRemovedPage, NotFoundPage } from "./FeatureStatePage";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual("../api/client");
  return { ...actual, apiJson: vi.fn() };
});

describe("Version 2.0.1 simplified workspace", () => {
  beforeEach(() => { apiJson.mockReset(); global.fetch = vi.fn(); });

  it("loads a dashboard without retired resource statistics", async () => {
    apiJson.mockResolvedValue({ resumes_total: 2, resume_versions_total: 3, history_total: 4, agent_runs_total: 1, agent_runs_active: 0 });
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(await screen.findByText("Saved analyses")).toBeInTheDocument();
    expect(screen.queryByText("Active Applications")).not.toBeInTheDocument();
    expect(screen.queryByText("Pending Tasks")).not.toBeInTheDocument();
  });

  it("renders a safe feature-removed state for old routes", () => {
    render(<MemoryRouter><FeatureRemovedPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Feature removed" })).toBeInTheDocument();
    expect(screen.getByText(/Historical database records were preserved/)).toBeInTheDocument();
  });

  it("renders a safe not-found state", () => {
    render(<MemoryRouter><NotFoundPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it("keeps Analyze independent and exposes the Project Knowledge switch", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<AnalyzePage />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const [requestUrl, requestOptions] = global.fetch.mock.calls[0];
    expect(new URL(requestUrl, "http://localhost").pathname).toBe("/api/resumes");
    expect(requestOptions.credentials).toBe("same-origin");
    expect(screen.getByLabelText("Use Project Knowledge (RAG)")).toBeChecked();
    fireEvent.click(screen.getByLabelText("Use Project Knowledge (RAG)"));
    expect(screen.getByLabelText("Project Knowledge top-k")).toBeDisabled();
  });

  it("displays only safe RAG source metadata when RAG is on", () => {
    render(<RagSourcesSection ragMode="project" usedKnowledgeBase retrievalCount={1} sources={[{
      document: "PROJECT_KNOWLEDGE.md", section: "RAG architecture", chunk_id: 7,
      relevance_score: 0.82, supported_skills: ["PostgreSQL"], content: "must not render",
    }]} />);
    expect(screen.getByText("RAG Sources")).toBeInTheDocument();
    expect(screen.getByText(/Supports: PostgreSQL/)).toBeInTheDocument();
    expect(screen.queryByText("must not render")).not.toBeInTheDocument();
  });

  it("hides RAG sources when RAG is off", () => {
    render(<RagSourcesSection ragMode="off" sources={[]} />);
    expect(screen.queryByText("RAG Sources")).not.toBeInTheDocument();
  });

  it.each([
    ["repaired", /automatically normalized/],
    ["partial", /optional analysis fields were unavailable/],
    ["fallback", /local fallback analysis is shown/],
  ])("shows usable results for %s analysis", async (analysisStatus, message) => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        analysis_status: analysisStatus, match_score: 65, matched_skills: ["FastAPI"],
        missing_skills: ["Kubernetes"], recommendations: ["Add evidence."],
        scoring_breakdown: {}, ats_analysis: {}, rag_sources: [], evidence_mapping: [],
      }), { status: 200, headers: { "Content-Type": "application/json" } }));

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
    expect(screen.getByText("Match Score")).toBeInTheDocument();
    expect(screen.queryByText("Analysis failed")).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(3);
  });

  it("shows a complete result without a normalization warning", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{ title: "Primary", active_version_id: "v1", is_primary: true }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ title: "Primary", active_version_id: "v1", is_primary: true }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ analysis_status: "complete", match_score: 80, matched_skills: [], missing_skills: [], scoring_breakdown: {} }), { status: 200 }));
    render(<AnalyzePage />);
    await screen.findByText(/Primary Resume selected automatically/);
    fireEvent.change(screen.getByLabelText("Job Description"), { target: { value: "Synthetic role" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Match Score")).toBeInTheDocument();
    expect(screen.queryByText(/automatically normalized/)).not.toBeInTheDocument();
  });

  it("prevents duplicate Analyze submissions while a request is pending", async () => {
    let resolveAnalyze;
    const pending = new Promise((resolve) => { resolveAnalyze = resolve; });
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockImplementationOnce(() => pending);

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    const button = screen.getByRole("button", { name: "Analyze" });
    fireEvent.click(button);
    fireEvent.submit(button.closest("form"));
    expect(global.fetch).toHaveBeenCalledTimes(3);

    resolveAnalyze(new Response(JSON.stringify({
      analysis_status: "fallback", match_score: 25, matched_skills: [], missing_skills: ["FastAPI"], scoring_breakdown: {},
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    expect(await screen.findByText(/local fallback analysis is shown/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });

  it("sends a bounded UUID idempotency key without browser persistence", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        analysis_status: "complete", match_score: 80, matched_skills: [],
        missing_skills: [], scoring_breakdown: {},
      }), { status: 200 }));
    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByText("Match Score");
    const headers = new Headers(global.fetch.mock.calls[2][1].headers);
    expect(headers.get("Idempotency-Key")).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("reuses an unknown-outcome key and replaces it when the resume changes", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response("[]", { status: 200 }))
      .mockResolvedValueOnce(new Response("{}", { status: 200 }))
      .mockRejectedValueOnce(new TypeError("synthetic network outcome unknown"))
      .mockRejectedValueOnce(new TypeError("synthetic network outcome still unknown"))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        analysis_status: "complete", match_score: 80, matched_skills: [],
        missing_skills: [], scoring_breakdown: {},
      }), { status: 200 }));
    render(<AnalyzePage />);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    const firstResume = new File(["first"], "resume.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      lastModified: 1,
    });
    fireEvent.change(screen.getByLabelText("Resume upload"), {
      target: { files: [firstResume] },
    });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByText(/Cannot connect to backend/);
    const unknownKey = new Headers(global.fetch.mock.calls[2][1].headers)
      .get("Idempotency-Key");
    const analyzeButton = screen.getByRole("button", { name: "Analyze" });
    await waitFor(() => expect(analyzeButton).toBeEnabled());
    fireEvent.click(analyzeButton);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(4));
    const retryKey = new Headers(global.fetch.mock.calls[3][1].headers)
      .get("Idempotency-Key");
    expect(retryKey).toBe(unknownKey);

    const changedResume = new File(["other"], "resume.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      lastModified: 1,
    });
    fireEvent.change(screen.getByLabelText("Resume upload"), {
      target: { files: [changedResume] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByText("Match Score");
    const changedKey = new Headers(global.fetch.mock.calls[4][1].headers)
      .get("Idempotency-Key");
    expect(changedKey).not.toBe(unknownKey);
  });

  it("maps stable Analyze errors, shows the support reference, and hides raw details", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: {
          code: "ANALYZE_PERSISTENCE_FAILED",
          message: "PRIVATE_INTERNAL_MESSAGE",
          request_id: "support-request-123",
          details: {
            internal_exception: "PRIVATE_INTERNAL_DETAIL",
            security_status: "not_blocked",
          },
        },
      }), { status: 503, headers: { "Content-Type": "application/json", "X-Request-ID": "support-request-123" } }));

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByText(/could not be saved safely/)).toBeInTheDocument();
    expect(screen.getByText("support-request-123")).toBeInTheDocument();
    expect(screen.queryByText("PRIVATE_INTERNAL_MESSAGE")).not.toBeInTheDocument();
    expect(screen.queryByText("PRIVATE_INTERNAL_DETAIL")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });

  it("renders only allowlisted security metadata from a stable Analyze error", async () => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: "Synthetic Resume", active_version_id: "resume-version-1", is_primary: true,
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: {
          code: "INPUT_SECURITY_BLOCKED",
          message: "PRIVATE_INTERNAL_MESSAGE",
          request_id: "security-request-123",
          details: {
            security_status: "blocked",
            security_scan: {
              risk_level: "critical",
              blocked: true,
              sensitive_data_detected: true,
              findings: [{
                code: "secret_api_key",
                category: "secret",
                severity: "critical",
                source: "resume",
                message: "PRIVATE_RAW_FINDING",
              }],
            },
            workflow_steps: [{ message: "PRIVATE_WORKFLOW_DETAIL" }],
          },
        },
      }), { status: 422, headers: { "Content-Type": "application/json" } }));

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));

    expect((await screen.findAllByText(/Credential-like content was detected/)).length).toBeGreaterThan(0);
    expect(screen.getByText("Security finding detected.")).toBeInTheDocument();
    expect(screen.queryByText("PRIVATE_RAW_FINDING")).not.toBeInTheDocument();
    expect(screen.queryByText("PRIVATE_WORKFLOW_DETAIL")).not.toBeInTheDocument();
    expect(screen.queryByText("PRIVATE_INTERNAL_MESSAGE")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });
});
