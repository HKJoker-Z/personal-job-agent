import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

export const STAGES = ["saved", "shortlisted", "preparing", "ready_to_apply", "applied", "assessment", "interview", "final_interview", "offer", "accepted", "rejected", "withdrawn", "closed"];
export const TRANSITIONS = {
  saved: ["shortlisted", "preparing", "closed"], shortlisted: ["preparing", "rejected", "closed"],
  preparing: ["ready_to_apply", "withdrawn", "closed"], ready_to_apply: ["applied", "withdrawn", "closed"],
  applied: ["assessment", "interview", "rejected", "withdrawn", "closed"], assessment: ["interview", "rejected", "withdrawn"],
  interview: ["final_interview", "offer", "rejected", "withdrawn"], final_interview: ["offer", "rejected", "withdrawn"],
  offer: ["accepted", "rejected", "withdrawn"], accepted: [], rejected: [], withdrawn: [], closed: [],
};
const IMPORTANT = new Set(["applied", "offer", "accepted", "rejected", "withdrawn", "closed"]);
const TERMINAL = new Set(["accepted", "rejected", "withdrawn", "closed"]);
const label = (value) => value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());

export function ApplicationBoardPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const load = () => apiJson("/api/applications").then(setItems).catch((value) => setError(value.message));
  useEffect(() => { load(); }, []);
  const groups = useMemo(() => Object.fromEntries(STAGES.map((stage) => [stage, items.filter((item) => item.current_stage === stage)])), [items]);
  const move = async (application, toStage) => {
    if (!TRANSITIONS[application.current_stage]?.includes(toStage)) { setError(`Cannot move from ${label(application.current_stage)} to ${label(toStage)}.`); return; }
    if (IMPORTANT.has(toStage) && !window.confirm(`Move this Application to ${label(toStage)}?`)) return;
    const before = items;
    setItems((current) => current.map((item) => item.id === application.id ? { ...item, current_stage: toStage } : item));
    try {
      const result = await apiJson(`/api/applications/${application.id}/transition`, { method: "POST", body: { to_stage: toStage, expected_revision: application.revision, reason: "Application Board transition" } });
      setItems((current) => current.map((item) => item.id === application.id ? result.application : item));
      setError("");
    } catch (value) {
      setItems(before);
      setError(value.message);
      if (value.status === 409) await load();
    }
  };
  return <section><h2>Application Board</h2><p className="muted">Every move is validated by the server and recorded in immutable Stage History.</p>{error ? <p role="alert">{error}</p> : null}
    <div className="board" aria-label="Application stages">{STAGES.map((stage) => <section className="board-column" key={stage} aria-label={`${label(stage)} applications`} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { const item = items.find((value) => value.id === event.dataTransfer.getData("text/application-id")); if (item) move(item, stage); }}>
      <h3>{label(stage)} <span>{groups[stage].length}</span></h3>{groups[stage].map((application) => <article key={application.id} className="application-card" draggable onDragStart={(event) => event.dataTransfer.setData("text/application-id", application.id)}>
        <Link to={`/applications/${application.id}`}>{application.job?.title || "Application"}</Link><span>{application.job?.company_name || "Company needs review"}</span><span>Priority: {application.priority}</span>
        <label>Move without drag<select aria-label={`Move Application ${application.id}`} value="" onChange={(event) => move(application, event.target.value)}><option value="">Choose stage</option>{(TRANSITIONS[application.current_stage] || []).map((next) => <option key={next} value={next}>{label(next)}</option>)}</select></label>
      </article>)}</section>)}</div>
  </section>;
}

export function ApplicationDetailPage() {
  const { applicationId } = useParams();
  const [application, setApplication] = useState(null);
  const [notes, setNotes] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [note, setNote] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [error, setError] = useState("");
  const load = async () => {
    try {
      const [detail, noteItems, taskItems] = await Promise.all([
        apiJson(`/api/applications/${applicationId}`), apiJson(`/api/applications/${applicationId}/notes`),
        apiJson(`/api/tasks?application_id=${applicationId}`),
      ]);
      setApplication(detail); setNotes(noteItems); setTasks(taskItems); setError("");
    } catch (value) { setError(value.message); }
  };
  useEffect(() => { load(); }, [applicationId]);
  if (error && !application) return <p role="alert">{error}</p>;
  if (!application) return <p>Loading Application…</p>;
  const transition = async (toStage) => {
    if (IMPORTANT.has(toStage) && !window.confirm(`Move to ${label(toStage)}?`)) return;
    try { await apiJson(`/api/applications/${application.id}/transition`, { method: "POST", body: { to_stage: toStage, expected_revision: application.revision, reason: "Application Detail transition" } }); await load(); }
    catch (value) { setError(value.message); }
  };
  return <section><div className="section-heading"><div><h2>Application Detail</h2><p>{application.job?.title || "Job"} · {application.job?.company_name || "Company needs review"}</p></div><span className="status-badge">{label(application.current_stage)}</span></div>
    {error ? <p role="alert">{error}</p> : null}
    <dl className="detail-grid"><dt>Priority</dt><dd>{application.priority}</dd><dt>Applied at</dt><dd>{application.applied_at ? new Date(application.applied_at).toLocaleString() : "Not applied"}</dd><dt>Next action</dt><dd>{application.next_action_at ? new Date(application.next_action_at).toLocaleString() : "Not set"}</dd><dt>Resume Version</dt><dd>{application.resume_version_id || "Not linked"}</dd></dl>
    <p><Link className="button-link" to={`/applications/${application.id}/packages`}>Application Packages</Link></p>
    <label>Transition<select aria-label="Application transition" value="" onChange={(event) => transition(event.target.value)}><option value="">Select next stage</option>{(TRANSITIONS[application.current_stage] || []).map((stage) => <option value={stage} key={stage}>{label(stage)}</option>)}</select></label>
    {TERMINAL.has(application.current_stage) ? <button onClick={async () => { if (!window.confirm("Reopen this terminal Application?")) return; try { await apiJson(`/api/applications/${application.id}/reopen`, { method: "POST", body: { expected_revision: application.revision, reason: "User requested reopen", confirmation: "REOPEN APPLICATION" } }); await load(); } catch (value) { setError(value.message); } }}>Reopen Application</button> : null}
    <form className="inline-form" onSubmit={async (event) => { event.preventDefault(); try { const result = await apiJson(`/api/applications/${application.id}/resume`, { method: "POST", body: { resume_version_id: resumeVersionId, expected_revision: application.revision } }); setApplication((current) => ({ ...current, ...result.application })); setResumeVersionId(""); setError(result.warning || ""); } catch (value) { setError(value.message); } }}><label>Resume Version ID<input aria-label="Resume Version ID" required value={resumeVersionId} onChange={(event) => setResumeVersionId(event.target.value)} /></label><button type="submit">Link Resume Version</button></form>
    <h3>Stage History</h3><ol className="timeline">{application.history.map((item) => <li key={item.id}><strong>{label(item.from_stage)} → {label(item.to_stage)}</strong><span>{new Date(item.changed_at).toLocaleString()}</span><p>{item.reason}</p></li>)}</ol>
    <h3>Private Notes</h3><form onSubmit={async (event) => { event.preventDefault(); try { await apiJson(`/api/applications/${application.id}/notes`, { method: "POST", body: { content: note, note_type: "general" } }); setNote(""); await load(); } catch (value) { setError(value.message); } }}><label>Note<textarea aria-label="Application Note" required value={note} onChange={(event) => setNote(event.target.value)} /></label><button type="submit">Add Note</button></form><ul>{notes.map((item) => <li key={item.id} className="plain-note">{item.content}</li>)}</ul>
    <h3>Tasks</h3><form onSubmit={async (event) => { event.preventDefault(); try { await apiJson("/api/tasks", { method: "POST", body: { application_id: application.id, title: taskTitle, task_type: "other" } }); setTaskTitle(""); await load(); } catch (value) { setError(value.message); } }}><label>Task title<input aria-label="Application Task" required value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} /></label><button type="submit">Add Task</button></form><ul>{tasks.map((item) => <li key={item.id}>{item.title} — {item.status}</li>)}</ul>
    <button onClick={async () => { if (!window.confirm("Archive this Application?")) return; try { await apiJson(`/api/applications/${application.id}/archive`, { method: "POST", body: { expected_revision: application.revision } }); window.location.assign("/applications"); } catch (value) { setError(value.message); } }}>Archive Application</button>
  </section>;
}
