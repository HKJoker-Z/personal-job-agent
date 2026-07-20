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
    ["MODEL_OUTPUT_TRUNCATED", /cut off before completion/],
    ["MODEL_OUTPUT_INVALID_JSON", /invalid structured response/],
    ["MODEL_OUTPUT_SCHEMA_INVALID", /did not match the required analysis format/],
  ])("shows a safe retry state for %s without a partial result", async (errorCode, message) => {
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1",
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        detail: { message: "Safe backend summary.", error_code: errorCode },
      }), { status: 502, headers: { "Content-Type": "application/json" } }));

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Stored Resume Version"), {
      target: { value: "resume-version-1" },
    });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
    expect(screen.queryByText("Match Score")).not.toBeInTheDocument();
    expect(screen.queryByText(/Saved to history/)).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it("prevents duplicate Analyze submissions while a request is pending", async () => {
    let resolveAnalyze;
    const pending = new Promise((resolve) => { resolveAnalyze = resolve; });
    global.fetch
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        title: "Synthetic Resume", active_version_id: "resume-version-1",
      }]), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockImplementationOnce(() => pending);

    render(<AnalyzePage />);
    await screen.findByRole("option", { name: /Synthetic Resume/ });
    fireEvent.change(screen.getByLabelText("Stored Resume Version"), {
      target: { value: "resume-version-1" },
    });
    fireEvent.change(screen.getByLabelText("Job Description"), {
      target: { value: "Synthetic FastAPI role" },
    });
    const button = screen.getByRole("button", { name: "Analyze" });
    fireEvent.click(button);
    fireEvent.submit(button.closest("form"));
    expect(global.fetch).toHaveBeenCalledTimes(2);

    resolveAnalyze(new Response(JSON.stringify({
      detail: { error_code: "MODEL_PROVIDER_ERROR", message: "Safe failure." },
    }), { status: 502, headers: { "Content-Type": "application/json" } }));
    expect(await screen.findByText(/provider request failed safely/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });
});
