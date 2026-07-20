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
  beforeEach(() => { apiJson.mockReset(); });

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
});
