import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentRunDetailPage, AgentRunsPage, deduplicateEvents } from "./AgentPages";
import { apiJson } from "../api/client";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

const run = { id: "run1", workflow_type: "legacy_package", status: "waiting_for_approval", revision: 8, progress_percent: 50, total_tokens: 0, estimated_cost_usd: 0, token_limit: 1000, cost_limit_usd: 1, current_step_key: "wait", steps: [] };

describe("historical Agent Runs", () => {
  beforeEach(() => { apiJson.mockReset(); global.EventSource = undefined; });

  it("lists historical runs without a creation workflow", async () => {
    apiJson.mockImplementation((path) => path === "/api/ready" ? Promise.resolve({ worker: "ready" }) : Promise.resolve([run]));
    render(<MemoryRouter><AgentRunsPage /></MemoryRouter>);
    expect(await screen.findByText("Legacy Package")).toBeInTheDocument();
    expect(screen.queryByText(/Create/)).not.toBeInTheDocument();
  });

  it("keeps waiting approval runs read-only except cancellation", async () => {
    apiJson.mockImplementation((path, options) => {
      if (path.endsWith("/events")) return Promise.resolve([]);
      if (path.endsWith("/cancel") && options?.method === "POST") return Promise.resolve({ ...run, status: "cancelled", revision: 9 });
      return Promise.resolve(run);
    });
    render(<MemoryRouter initialEntries={["/agent-runs/run1"]}><Routes><Route path="/agent-runs/:runId" element={<AgentRunDetailPage />} /></Routes></MemoryRouter>);
    expect(await screen.findByText(/retired approval workflow/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Resume Now/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith("/api/agent-runs/run1/cancel", expect.objectContaining({ method: "POST" })));
  });

  it("deduplicates repeated event IDs deterministically", () => {
    expect(deduplicateEvents([{ id: 2 }, { id: 1 }, { id: 2 }]).map((item) => item.id)).toEqual([1, 2]);
  });
});
