import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

function Alert({ value }) { return value ? <p role="alert">{value}</p> : null; }
const label = (value) => String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());

export function JobRankingPage() {
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { apiJson("/api/jobs?limit=100&sort=-created_at").then((value) => setJobs(value.items)).catch((value) => setError(value.message)); }, []);
  const run = async () => {
    setBusy(true); setError("");
    try { setResult(await apiJson("/api/jobs/rank", { method: "POST", body: { job_ids: selected } })); }
    catch (value) { setError(value.message); }
    finally { setBusy(false); }
  };
  return <section><div className="section-heading"><div><h2>Job Ranking</h2><p className="muted">Ranking is deterministic and explainable; it is not a prediction of hiring success.</p></div><button disabled={!selected.length || busy} onClick={run}>{busy ? "Ranking…" : "Rank selected Jobs"}</button></div>
    <Alert value={error} />
    {!jobs.length ? <p className="empty-state">Import Jobs before creating a Rank Run.</p> : <fieldset className="selection-list"><legend>Select Jobs</legend>{jobs.map((job) => <label key={job.id}><input type="checkbox" checked={selected.includes(job.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, job.id] : current.filter((id) => id !== job.id))} />{job.title || "Untitled"} — {job.company_name || "Unknown company"}</label>)}</fieldset>}
    {result ? <div className="ranking-list" aria-label="Ranked Jobs"><h3>Rank Results</h3>{result.items.map((item) => <article className="resource-card rank-card" key={item.id}><strong>#{item.rank_position} <Link to={`/jobs/${item.job.id}`}>{item.job.title}</Link></strong><span>{item.job.company_name}</span><span>Score {item.rank_score}</span><span className="status-badge">Hard filter: {item.hard_filter_status}</span><p>{label(item.recommendation)} · {label(item.preparation_effort)} preparation</p><div><strong>Primary reasons</strong><ul>{(item.reason_summary.primary_reasons || []).map((value) => <li key={value}>{label(value)}</li>)}</ul><strong>Primary gaps</strong><ul>{(item.reason_summary.primary_gaps || []).map((value) => <li key={value}>{label(value)}</li>)}</ul></div></article>)}</div> : null}
  </section>;
}

export function ApplicationPackagesPage() {
  const { applicationId } = useParams();
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ source_resume_version_id: "", match_analysis_id: "", title: "Application Package" });
  const [error, setError] = useState("");
  const load = () => apiJson(`/api/applications/${applicationId}/packages`).then(setItems).catch((value) => setError(value.message));
  useEffect(() => { load(); }, [applicationId]);
  const create = async (event) => {
    event.preventDefault(); setError("");
    try { await apiJson(`/api/applications/${applicationId}/packages`, { method: "POST", body: form }); setForm({ ...form, title: "Application Package" }); await load(); }
    catch (value) { setError(value.message); }
  };
  return <section><h2>Application Packages</h2><p className="muted">Each Package snapshots the Profile, Job, Resume, and Match Analysis used to create its Draft materials.</p><Alert value={error} />
    <form className="form-grid" onSubmit={create}><label>Finalized Resume Version ID<input aria-label="Package Resume Version ID" required value={form.source_resume_version_id} onChange={(event) => setForm({ ...form, source_resume_version_id: event.target.value })} /></label><label>Match Analysis ID<input aria-label="Package Match Analysis ID" required value={form.match_analysis_id} onChange={(event) => setForm({ ...form, match_analysis_id: event.target.value })} /></label><label>Package title<input aria-label="Package title" required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label><button type="submit">Create Package Draft</button></form>
    {!items.length ? <p className="empty-state">No Packages yet. Run a Job Match and finalize a source Resume first.</p> : <div className="card-list">{items.map((item) => <article className="resource-card" key={item.id}><h3><Link to={`/application-packages/${item.id}`}>{item.title}</Link></h3><span className="status-badge">{item.status}</span><p>Profile revision {item.source_profile_revision} · Job revision {item.source_job_revision}</p></article>)}</div>}
  </section>;
}

function MaterialEditor({ material, reload }) {
  const active = material.active_version;
  const [text, setText] = useState(active?.content_text || "");
  const [dirty, setDirty] = useState(false);
  const [versions, setVersions] = useState([]);
  const [error, setError] = useState("");
  useEffect(() => { setText(active?.content_text || ""); setDirty(false); }, [active?.id]);
  useEffect(() => {
    const warn = (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  if (!active) return null;
  const action = async (path, body = {}) => {
    try { await apiJson(path, { method: "POST", body }); setError(""); await reload(); }
    catch (value) { setError(value.message); if (value.status === 409) await reload(); }
  };
  const save = async () => {
    try {
      await apiJson(`/api/application-materials/${material.id}/versions`, { method: "POST", body: { expected_active_version_id: active.id, content_text: text, content_json: active.content_json || {}, change_summary: "User editor update" } });
      setDirty(false); await reload();
    } catch (value) { setError(value.message); if (value.status === 409) await reload(); }
  };
  return <article className="material-editor resource-card"><div className="section-heading"><div><h4>{material.title}</h4><span className="status-badge">{material.status}</span></div><div><strong>Evidence coverage {active.evidence_coverage}%</strong><p>{active.unsupported_claim_count} unsupported or partially supported claim(s)</p></div></div><Alert value={error} />
    {active.unsupported_claim_count ? <p className="warning-banner" role="status">Unsupported claims block approval and finalization. Edit the Draft or provide confirmed evidence through the Profile workflow.</p> : null}
    <label>Draft content<textarea aria-label={`Edit ${material.title}`} rows="14" value={text} onChange={(event) => { setText(event.target.value); setDirty(true); }} /></label>
    <div className="button-row"><button disabled={!dirty} onClick={save}>Save as New Version</button><button onClick={() => action(`/api/material-versions/${active.id}/validate`)}>Validate Evidence</button><button onClick={() => action(`/api/material-versions/${active.id}/review`, { decision: "request_changes", notes: "Changes requested in Material Editor" })}>Request Changes</button><button disabled={active.unsupported_claim_count > 0} onClick={() => action(`/api/material-versions/${active.id}/review`, { decision: "approve", notes: "User approved this evidence-grounded Draft" })}>Approve</button><button disabled={material.status !== "approved" || active.unsupported_claim_count > 0} onClick={() => { if (window.confirm("Finalize this immutable Material Version?")) action(`/api/material-versions/${active.id}/finalize`, { confirmation: "FINALIZE MATERIAL" }); }}>Finalize</button></div>
    <details><summary>Evidence Side Panel</summary>{!active.evidence?.length ? <p>No factual claims detected.</p> : <ul>{active.evidence.map((item) => <li key={item.id}><strong>{label(item.support_status)}</strong> — {item.evidence_summary}{["unsupported", "partially_supported", "needs_user_input"].includes(item.support_status) ? <button className="link-button" onClick={() => { if (window.confirm("Confirm this claim for this Material Version only? This does not update your Profile.")) action(`/api/material-versions/${active.id}/evidence/${item.id}/confirm`, { confirmation: "CONFIRM CLAIM" }); }}>Confirm claim</button> : null}</li>)}</ul>}</details>
    <details onToggle={(event) => { if (event.currentTarget.open && !versions.length) apiJson(`/api/application-materials/${material.id}/versions`).then(setVersions).catch((value) => setError(value.message)); }}><summary>Version History and Diff</summary><ol>{versions.map((item) => <li key={item.id}>Version {item.version_number} · {item.source_type} · {item.validation_status}{item.parent_version_id ? ` · derived from ${item.parent_version_id}` : ""}</li>)}</ol><pre className="untrusted-text">{active.generation_metadata?.change_summary || "Generated from immutable evidence snapshot."}</pre></details>
  </article>;
}

export function ApplicationPackageDetailPage() {
  const { packageId } = useParams();
  const navigate = useNavigate();
  const [value, setValue] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const workflowKey = useRef(`package:${packageId}:${Date.now()}`);
  const load = () => apiJson(`/api/application-packages/${packageId}`).then(setValue).catch((item) => setError(item.message));
  useEffect(() => { load(); }, [packageId]);
  const startWorkflow = async (forceNew = false) => {
    if (forceNew && !window.confirm("Force a new workflow instead of reusing the existing idempotent Run?")) return;
    setBusy("workflow"); setError("");
    if (forceNew) workflowKey.current = `package:${packageId}:force:${Date.now()}`;
    try {
      const result = await apiJson("/api/agent-runs", {
        method: "POST",
        headers: { "Idempotency-Key": workflowKey.current },
        body: {
          package_id: packageId,
          force_new: forceNew,
          force_confirmation: forceNew ? "FORCE NEW" : null,
        },
      });
      navigate(`/agent-runs/${result.run.id}`, { state: { reused: result.reused } });
    } catch (item) { setError(item.message); }
    finally { setBusy(""); }
  };
  if (error && !value) return <Alert value={error} />;
  if (!value) return <p>Loading Application Package…</p>;
  const unsupported = value.materials.reduce((count, material) => count + Number(material.active_version?.unsupported_claim_count || 0), 0);
  return <section><div className="section-heading"><div><h2>{value.title}</h2><p>Application Package</p></div><span className="status-badge">{value.status}</span></div><Alert value={error} />
    <dl className="detail-grid"><dt>Source Resume</dt><dd>{value.source_resume_version_id}</dd><dt>Profile Revision</dt><dd>{value.source_profile_revision}</dd><dt>Job Revision</dt><dd>{value.source_job_revision}</dd><dt>Match Analysis</dt><dd>{value.source_match_analysis_id}</dd></dl>
    <p className="muted">The durable workflow continues if you close this page. It pauses without occupying a Worker whenever approval is required.</p>
    <div className="button-row"><button disabled={Boolean(busy)} onClick={() => startWorkflow(false)}>{busy === "workflow" ? "Starting…" : "Start Agent Workflow"}</button><button disabled={Boolean(busy)} onClick={() => startWorkflow(true)}>Force New Workflow</button></div>
    {unsupported > 0 ? <p className="warning-banner" role="status">Existing materials contain unsupported claims. The Agent Workflow will not auto-confirm them.</p> : null}
    {!value.materials.length ? <p className="empty-state">No materials generated. The Agent Workflow creates Drafts and requests explicit approvals.</p> : <div className="material-list">{value.materials.map((material) => <MaterialEditor key={material.id} material={material} reload={load} />)}</div>}
  </section>;
}
