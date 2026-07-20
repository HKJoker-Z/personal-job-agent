import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "dead_letter"]);
const eventTypes = [
  "run.created", "run.started", "run.waiting_for_approval", "run.approval_received",
  "run.approval_rejected", "run.approval_expired", "run.retry_due",
  "run.retry_scheduled", "run.retry_requested", "run.resume_requested", "run.cancel_requested",
  "run.cancelled", "run.failed", "run.completed", "run.dead_letter", "run.crash_recovered",
  "run.dispatch_started", "run.dispatch_failed",
  "step.queued", "step.started", "step.completed", "step.failed", "step.retry_scheduled",
  "step.retry_queued", "step.cancelled", "step.duplicate_delivery", "step.stale_delivery",
  "step.crash_recovered", "step.lease_expired",
  "approval.created", "approval.requested", "approval.approved", "approval.rejected",
  "approval.expired", "stream.complete",
];

const label = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const money = (value) => `$${Number(value || 0).toFixed(4)}`;
const dateTime = (value) => value ? new Date(value).toLocaleString() : "—";
function Alert({ value }) { return value ? <p role="alert">{value}</p> : null; }

export function AgentRunsPage() {
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState("");
  const [worker, setWorker] = useState("checking");
  useEffect(() => {
    apiJson("/api/agent-runs").then(setRuns).catch((value) => setError(value.message));
    apiJson("/api/ready").then((value) => setWorker(value.worker || "not_required"))
      .catch(() => setWorker("unavailable"));
  }, []);
  return <section><div className="section-heading"><div><h2>Agent Runs</h2><p className="muted">Durable workflows continue after this page closes.</p></div><span className={`connection-state ${worker === "ready" || worker === "not_required" ? "connected" : "reconnecting"}`}>Worker: {label(worker)}</span></div>
    <Alert value={error} />
    {worker === "unavailable" || worker === "not_ready" ? <p className="warning-banner" role="status">The Worker is currently unavailable. Queued Runs remain durable and will resume after recovery.</p> : null}
    {!runs.length && !error ? <p className="empty-state">No historical Agent Runs.</p> : <div className="card-list">{runs.map((run) => <article className="resource-card" key={run.id}><div className="section-heading"><div><h3><Link to={`/agent-runs/${run.id}`}>{label(run.workflow_type)}</Link></h3><p>{dateTime(run.created_at)}</p></div><span className="status-badge">{label(run.status)}</span></div><progress max="100" value={run.progress_percent || 0}>{run.progress_percent || 0}%</progress><p>{run.progress_percent || 0}% · {run.total_tokens || 0} tokens · {money(run.estimated_cost_usd)}</p>{run.safe_error_summary ? <p className="safe-error">{run.safe_error_summary}</p> : null}</article>)}</div>}
  </section>;
}

export function useAgentRunEvents(runId, onRunChanged) {
  const [events, setEvents] = useState([]);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  useEffect(() => {
    let source;
    let closed = false;
    apiJson(`/api/agent-runs/${runId}/events`).then((values) => {
      if (!closed) setEvents((current) => deduplicateEvents([...current, ...values]));
    }).catch((value) => setError(value.message));
    if (typeof EventSource === "undefined") {
      setConnection("unavailable");
      return () => { closed = true; };
    }
    source = new EventSource(`/api/agent-runs/${runId}/events/stream`);
    source.onopen = () => setConnection("connected");
    source.onerror = () => setConnection("reconnecting");
    const receive = (message) => {
      if (message.type === "stream.complete") {
        setConnection("complete");
        source.close();
        return;
      }
      try {
        const value = JSON.parse(message.data);
        setEvents((current) => deduplicateEvents([...current, value]));
        onRunChanged?.();
      } catch {
        setError("Live progress returned an invalid safe event.");
      }
    };
    eventTypes.forEach((type) => source.addEventListener(type, receive));
    return () => {
      closed = true;
      eventTypes.forEach((type) => source.removeEventListener(type, receive));
      source.close();
    };
  }, [runId, onRunChanged]);
  return { events, connection, error };
}

export function deduplicateEvents(events) {
  const byId = new Map();
  events.forEach((event) => {
    if (event && event.id !== undefined && event.id !== null) byId.set(String(event.id), event);
  });
  return [...byId.values()].sort((left, right) => Number(left.id) - Number(right.id));
}

export function AgentRunDetailPage() {
  const { runId } = useParams();
  const [run, setRun] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => apiJson(`/api/agent-runs/${runId}`).then(setRun).catch((value) => setError(value.message)), [runId]);
  useEffect(() => { load(); }, [load]);
  const live = useAgentRunEvents(runId, load);
  const mutate = async (action, body) => {
    setBusy(action); setError("");
    try { setRun(await apiJson(`/api/agent-runs/${runId}/${action}`, { method: "POST", body })); }
    catch (value) { setError(value.message); if (value.status === 409) await load(); }
    finally { setBusy(""); }
  };
  if (!run) return <section><h2>Agent Run</h2><Alert value={error || live.error} />{!error ? <p>Loading durable Run…</p> : null}</section>;
  const current = run.steps?.find((step) => step.step_key === run.current_step_key);
  const canCancel = !terminalStatuses.has(run.status);
  return <section><div className="section-heading"><div><h2>Agent Run</h2><p className="muted">{run.id}</p></div><div><span className="status-badge">{label(run.status)}</span> <span className={`connection-state ${live.connection}`}>Live: {label(live.connection)}</span></div></div><Alert value={error || live.error} />
    {run.status === "waiting_for_approval" ? <p className="warning-banner" role="status">This historical Run is waiting for a retired approval workflow. It is read-only and may be safely cancelled.</p> : null}
    {run.safe_error_summary ? <p className="safe-error" role="alert">{run.safe_error_summary}</p> : null}
    <div className="run-summary-grid"><article><strong>Progress</strong><progress max="100" value={run.progress_percent || 0}>{run.progress_percent || 0}%</progress><span>{run.progress_percent || 0}%</span></article><article><strong>Current Step</strong><span>{label(current?.step_key || run.current_step_key || "complete")}</span></article><article><strong>Tokens</strong><span>{run.total_tokens || 0} / {run.token_limit}</span></article><article><strong>Estimated Cost</strong><span>{money(run.estimated_cost_usd)} / {money(run.cost_limit_usd)}</span></article></div>
    <div className="button-row"><button disabled={!canCancel || Boolean(busy)} onClick={() => mutate("cancel", { expected_revision: run.revision })}>Cancel</button></div>
    <div className="agent-detail-grid"><div><h3>Steps</h3><ol className="step-list">{(run.steps || []).map((step) => <li key={step.id} className={step.status === "running" ? "current" : ""}><span>{step.step_order}. {label(step.step_key)}</span><span className="status-badge">{label(step.status)}</span>{step.safe_error_summary ? <small>{step.safe_error_summary}</small> : null}</li>)}</ol></div><div><h3>Timeline</h3>{!live.events.length ? <p className="empty-state">Waiting for the first safe event…</p> : <ol className="timeline">{live.events.map((event) => <li key={event.id}><strong>{label(event.event_type)}</strong><span>{event.summary}</span><time>{dateTime(event.created_at)}</time></li>)}</ol>}</div></div>
  </section>;
}
