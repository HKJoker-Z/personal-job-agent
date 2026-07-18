import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiJson } from "../api/client";
import { AgentRunDetailPage, AgentRunsPage, ApprovalsPage, deduplicateEvents } from "./AgentPages";

vi.mock("../api/client", () => ({ apiJson: vi.fn() }));

class FakeEventSource {
  static instances = [];
  constructor(url) { this.url = url; this.listeners = new Map(); this.closed = false; FakeEventSource.instances.push(this); }
  addEventListener(type, handler) { this.listeners.set(type, handler); }
  removeEventListener(type) { this.listeners.delete(type); }
  close() { this.closed = true; }
  emit(type, value) { this.listeners.get(type)?.({ type, data: JSON.stringify(value), lastEventId: String(value?.id || "") }); }
}

const run = {
  id: "run1", workflow_type: "generate_application_package", status: "running",
  revision: 8, progress_percent: 35, current_step_key: "generate_tailored_resume",
  total_tokens: 120, estimated_cost_usd: 0.0123, token_limit: 30000, cost_limit_usd: 2,
  created_at: "2030-01-01T00:00:00Z", safe_error_summary: null,
  steps: [
    { id: "s1", step_order: 1, step_key: "validate_request", status: "completed" },
    { id: "s2", step_order: 7, step_key: "generate_tailored_resume", status: "running" },
  ],
};

const event = { id: 1, event_type: "run.created", summary: "Agent Run queued.", created_at: "2030-01-01T00:00:00Z" };

function at(path, element, initial) {
  return <MemoryRouter initialEntries={[initial]}><Routes><Route path={path} element={element} /><Route path="/approvals" element={<p>Approval destination</p>} /></Routes></MemoryRouter>;
}

describe("Version 2.0.4 Agent workspace", () => {
  beforeEach(() => {
    apiJson.mockReset();
    FakeEventSource.instances = [];
    global.EventSource = FakeEventSource;
    window.confirm = vi.fn(() => true);
  });

  it("lists Agent Runs and reports a Worker outage without losing queued work", async () => {
    apiJson.mockImplementation((path) => {
      if (path === "/api/agent-runs") return Promise.resolve([run]);
      if (path === "/api/ready") return Promise.reject(new Error("unavailable"));
      return Promise.resolve({});
    });
    render(<MemoryRouter><AgentRunsPage /></MemoryRouter>);
    expect(await screen.findByText("Generate Application Package")).toBeInTheDocument();
    expect(await screen.findByText(/Worker is currently unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/120 tokens/)).toBeInTheDocument();
  });

  it("streams live progress, reconnects, and deduplicates Timeline events", async () => {
    apiJson.mockImplementation((path) => {
      if (path.endsWith("/events")) return Promise.resolve([event, event]);
      if (path === "/api/agent-runs/run1") return Promise.resolve(run);
      return Promise.resolve({});
    });
    render(at("/agent-runs/:runId", <AgentRunDetailPage />, "/agent-runs/run1"));
    expect(await screen.findByText("Generate Tailored Resume")).toBeInTheDocument();
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = FakeEventSource.instances[0];
    act(() => { source.onopen(); });
    expect(screen.getByText("Live: Connected")).toBeInTheDocument();
    const completed = { id: 2, event_type: "step.completed", summary: "Step completed safely.", created_at: "2030-01-01T00:01:00Z" };
    act(() => { source.emit("step.completed", completed); source.emit("step.completed", completed); source.onerror(); });
    expect(await screen.findByText("Step completed safely.")).toBeInTheDocument();
    expect(screen.getAllByText("Step completed safely.")).toHaveLength(1);
    expect(screen.getByText("Live: Reconnecting")).toBeInTheDocument();
  });

  it("cancels a Run and refreshes stale 409 state", async () => {
    const conflict = Object.assign(new Error("This record changed elsewhere."), { status: 409 });
    let detailCalls = 0;
    apiJson.mockImplementation((path, options) => {
      if (path.endsWith("/events")) return Promise.resolve([]);
      if (path === "/api/agent-runs/run1/cancel" && options?.method === "POST") return Promise.reject(conflict);
      if (path === "/api/agent-runs/run1") { detailCalls += 1; return Promise.resolve({ ...run, revision: 8 + detailCalls }); }
      return Promise.resolve({});
    });
    render(at("/agent-runs/:runId", <AgentRunDetailPage />, "/agent-runs/run1"));
    fireEvent.click(await screen.findByText("Cancel"));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed elsewhere");
    await waitFor(() => expect(detailCalls).toBeGreaterThan(1));
  });

  it("warns that Retry may incur additional cost", async () => {
    const failed = { ...run, status: "failed", safe_error_summary: "Provider failed safely." };
    apiJson.mockImplementation((path, options) => {
      if (path.endsWith("/events")) return Promise.resolve([]);
      if (path === "/api/agent-runs/run1/retry" && options?.method === "POST") return Promise.resolve({ ...run, status: "queued" });
      if (path === "/api/agent-runs/run1") return Promise.resolve(failed);
      return Promise.resolve({});
    });
    render(at("/agent-runs/:runId", <AgentRunDetailPage />, "/agent-runs/run1"));
    fireEvent.click(await screen.findByText("Retry"));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("additional token usage"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith(
      "/api/agent-runs/run1/retry",
      expect.objectContaining({ body: { expected_revision: 8, acknowledge_possible_cost: true } }),
    ));
  });

  it("shows a non-blocking Waiting Approval state", async () => {
    const waiting = { ...run, status: "waiting_for_approval", current_step_key: "wait_resume_approval" };
    apiJson.mockImplementation((path) => path.endsWith("/events") ? Promise.resolve([]) : Promise.resolve(waiting));
    render(at("/agent-runs/:runId", <AgentRunDetailPage />, "/agent-runs/run1"));
    expect(await screen.findByText(/Worker is not occupied/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Review Approvals"));
    expect(screen.getByText("Approval destination")).toBeInTheDocument();
  });

  it("records an Approval decision and reloads the append-only list", async () => {
    const approval = { id: "approval1", run_id: "run1", title: "Review Resume", status: "pending", revision: 2, safe_summary: "Review the Draft.", risk_level: "normal", expires_at: "2030-01-02T00:00:00Z" };
    apiJson.mockResolvedValueOnce([approval]).mockResolvedValueOnce({ ...approval, status: "approved" }).mockResolvedValueOnce([{ ...approval, status: "approved" }]);
    render(<MemoryRouter><ApprovalsPage /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Approve"));
    await waitFor(() => expect(apiJson).toHaveBeenCalledWith(
      "/api/approvals/approval1/decide",
      expect.objectContaining({ body: expect.objectContaining({ decision: "approve", expected_revision: 2 }) }),
    ));
    expect(await screen.findByText("Approved")).toBeInTheDocument();
  });

  it("renders safe authentication and authorization failures", async () => {
    for (const [status, message] of [[401, "Your Session has expired."], [403, "This action is not permitted."], [409, "This record changed elsewhere."]]) {
      apiJson.mockReset();
      apiJson.mockImplementation((path) => path === "/api/ready"
        ? Promise.resolve({ worker: "ready" })
        : Promise.reject(Object.assign(new Error(message), { status })));
      const rendered = render(<MemoryRouter><AgentRunsPage /></MemoryRouter>);
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      rendered.unmount();
    }
  });

  it("deduplicates repeated event IDs deterministically", () => {
    expect(deduplicateEvents([{ ...event, id: 2 }, event, { ...event, id: 2 }]).map((item) => item.id)).toEqual([1, 2]);
  });
});
