import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

function ErrorMessage({ value }) { return value ? <p role="alert">{value}</p> : null; }

export function JobLibraryPage() {
  const [data, setData] = useState({ items: [], total: 0 });
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("-created_at");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const load = () => {
    const parameters = new URLSearchParams({ offset: String(offset), limit: "20", sort });
    if (query) parameters.set("query", query);
    if (status) parameters.set("status", status);
    apiJson(`/api/jobs?${parameters}`).then(setData).catch((value) => setError(value.message));
  };
  useEffect(load, [query, status, sort, offset]);
  return <section>
    <div className="section-heading"><h2>Job Library</h2><Link className="button-link" to="/jobs/import">Import Jobs</Link></div>
    <div className="filter-bar">
      <label>Search<input aria-label="Search Jobs" value={query} onChange={(event) => { setOffset(0); setQuery(event.target.value); }} /></label>
      <label>Status<select aria-label="Job status filter" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All active</option><option value="new">New</option><option value="reviewed">Reviewed</option><option value="shortlisted">Shortlisted</option><option value="closed">Closed</option></select></label>
      <label>Sort<select aria-label="Job sort" value={sort} onChange={(event) => setSort(event.target.value)}><option value="-created_at">Newest</option><option value="company">Company</option><option value="title">Title</option><option value="deadline">Deadline</option></select></label>
    </div>
    <ErrorMessage value={error} />
    {!data.items.length ? <p className="empty-state">No Jobs match the current filters.</p> : <div className="card-list">{data.items.map((job) => <article className="resource-card" key={job.id}>
      <div><h3><Link to={`/jobs/${job.id}`}>{job.title || "Untitled Job"}</Link></h3><p>{job.company_name || "Company needs review"} · {job.location || "Location needs review"}</p></div>
      <div className="badge-row"><span className="status-badge">{job.status}</span>{job.application_deadline ? <span>Deadline {new Date(job.application_deadline).toLocaleDateString()}</span> : null}</div>
      <p>{job.description_summary}</p>
    </article>)}</div>}
    <div className="pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</button><span>{data.total ? `${offset + 1}–${Math.min(offset + 20, data.total)} of ${data.total}` : "0 Jobs"}</span><button disabled={offset + 20 >= data.total} onClick={() => setOffset(offset + 20)}>Next</button></div>
  </section>;
}

const blankManual = {
  company_name: "", title: "", location: "", description: "", url: "",
  employment_type: "", work_mode: "", salary_min: "", salary_max: "",
  salary_currency: "", salary_period: "", application_deadline: "", status: "new",
};

function MatchPanel({ jobId }) {
  const [match, setMatch] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (forceNew = false) => {
    setBusy(true); setError("");
    try { setMatch(await apiJson(`/api/jobs/${jobId}/match`, { method: "POST", body: { force_new: forceNew } })); }
    catch (value) { setError(value.message); }
    finally { setBusy(false); }
  };
  const loadHistory = async () => {
    try { setHistory(await apiJson(`/api/jobs/${jobId}/matches`)); }
    catch (value) { setError(value.message); }
  };
  return <section className="match-panel" aria-label="Explainable Job Match">
    <div className="section-heading"><div><h3>Explainable Match</h3><p className="muted">A deterministic score based only on confirmed facts. It is not an Offer probability.</p></div><div className="button-row"><button disabled={busy} onClick={() => run(false)}>{busy ? "Matching…" : "Run Match"}</button>{match ? <button disabled={busy} onClick={() => run(true)}>Re-run Match</button> : null}<button onClick={loadHistory}>Match History</button></div></div>
    <ErrorMessage value={error} />
    {!match ? <p className="empty-state">Run Match to see evidence, gaps, unknowns, and hard-filter risks.</p> : <>
      <div className="metric-grid match-summary"><article className="metric-card"><span>Overall Score</span><strong>{Math.round(match.overall_score)}</strong><small>out of 100</small></article><article className="metric-card"><span>Hard Filter</span><strong className="text-value">{match.hard_filter_status}</strong></article><article className="metric-card"><span>Recommendation</span><strong className="text-value">{match.recommendation.replaceAll("_", " ")}</strong></article><article className="metric-card"><span>Preparation</span><strong className="text-value">{match.preparation_effort}</strong></article></div>
      <h4>Dimension Breakdown</h4><div className="dimension-grid">{match.dimensions.map((item) => <article className="resource-card" key={item.dimension}><strong>{item.dimension.replaceAll("_", " ")}</strong><span className="status-badge">{item.status}</span><p>{item.weighted_score} / {item.max_score}</p><small>{item.explanation}</small></article>)}</div>
      <div className="evidence-columns"><article><h4>Matched Evidence</h4><ul>{match.evidence.filter((item) => item.evidence_kind === "matched").map((item) => <li key={item.id}>{item.dimension}: {item.evidence_summary}</li>)}</ul></article><article><h4>Partial Evidence</h4><ul>{match.evidence.filter((item) => item.evidence_kind === "partial").map((item) => <li key={item.id}>{item.dimension}: {item.evidence_summary}</li>)}</ul></article><article><h4>Missing Requirements</h4><ul>{match.evidence.filter((item) => item.evidence_kind === "missing").map((item) => <li key={item.id}>{item.dimension}: confirmed requirement lacks evidence</li>)}</ul></article><article><h4>Unknown Requirements</h4><ul>{match.evidence.filter((item) => item.evidence_kind === "unknown").map((item) => <li key={item.id}>{item.dimension}: needs confirmation</li>)}</ul></article></div>
    </>}
    {history.length ? <div><h4>Match History</h4><ol>{history.map((item) => <li key={item.id}><button className="text-button" onClick={async () => setMatch(await apiJson(`/api/jobs/${jobId}/matches/${item.id}`))}>{new Date(item.created_at).toLocaleString()} — {Math.round(item.overall_score)} — {item.hard_filter_status}</button></li>)}</ol></div> : null}
  </section>;
}

export function JobImportPage() {
  const [tab, setTab] = useState("manual");
  const [manual, setManual] = useState(blankManual);
  const [url, setUrl] = useState("");
  const [file, setFile] = useState(null);
  const [csv, setCsv] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const manualPayload = () => {
    const value = Object.fromEntries(Object.entries(manual).filter(([, field]) => field !== ""));
    if (value.salary_min !== undefined) value.salary_min = Number(value.salary_min);
    if (value.salary_max !== undefined) value.salary_max = Number(value.salary_max);
    if (value.application_deadline) value.application_deadline = new Date(value.application_deadline).toISOString();
    return value;
  };
  const submitJson = async (path, body) => {
    setError("");
    try { const value = await apiJson(path, { method: "POST", body }); setResult(value); if (value.job?.id) navigate(`/jobs/${value.job.id}`); }
    catch (value) { setError(value.message); }
  };
  const submitFile = async (path, selected, query = "") => {
    const body = new FormData(); body.append("file", selected);
    return apiJson(`${path}${query}`, { method: "POST", body });
  };
  const csvAction = async (validateOnly) => {
    setError("");
    try { const value = await submitFile("/api/jobs/import/csv", csv, `?validate_only=${validateOnly}`); if (validateOnly) setPreview(value); else setResult(value); }
    catch (value) { setError(value.message); }
  };
  return <section><h2>Import Jobs</h2>
    <div className="tabs compact-tabs" role="tablist">{["manual", "url", "file", "csv"].map((item) => <button role="tab" aria-selected={tab === item} key={item} onClick={() => setTab(item)}>{item.toUpperCase()}</button>)}</div>
    <ErrorMessage value={error} />
    {tab === "manual" ? <form onSubmit={(event) => { event.preventDefault(); submitJson("/api/jobs/import/manual", manualPayload()); }} className="form-grid">
      {[["Company", "company_name"], ["Title", "title"], ["Location", "location"], ["URL", "url"], ["Employment type", "employment_type"], ["Work mode", "work_mode"], ["Salary minimum", "salary_min", "number"], ["Salary maximum", "salary_max", "number"], ["Salary currency", "salary_currency"], ["Salary period", "salary_period"], ["Application deadline", "application_deadline", "datetime-local"]].map(([label, key, type = "text"]) => <label key={key}>{label}<input type={type} min={type === "number" ? "0" : undefined} required={["company_name", "title"].includes(key)} value={manual[key]} onChange={(event) => setManual({ ...manual, [key]: event.target.value })} /></label>)}
      <label className="full-width">Description<textarea required rows="10" value={manual.description} onChange={(event) => setManual({ ...manual, description: event.target.value })} /></label><button type="submit">Import Job</button>
    </form> : null}
    {tab === "url" ? <form onSubmit={(event) => { event.preventDefault(); submitJson("/api/jobs/import/url", { url }); }}><label>HTTPS Job URL<input aria-label="HTTPS Job URL" required value={url} onChange={(event) => setUrl(event.target.value)} /></label><p className="muted">Private, local, credentialed, and unsafe redirect targets are rejected.</p><button type="submit">Fetch safely</button></form> : null}
    {tab === "file" ? <form onSubmit={async (event) => { event.preventDefault(); try { const value = await submitFile("/api/jobs/import/file", file); setResult(value); if (value.job?.id) navigate(`/jobs/${value.job.id}`); } catch (value) { setError(value.message); } }}><label>PDF or DOCX<input aria-label="Job document" type="file" accept=".pdf,.docx" required onChange={(event) => setFile(event.target.files?.[0])} /></label><button type="submit">Import private document</button></form> : null}
    {tab === "csv" ? <div><a href="/api/jobs/import/csv/template">Download CSV template</a><label>CSV file<input aria-label="Job CSV" type="file" accept=".csv,text/csv" onChange={(event) => { setCsv(event.target.files?.[0]); setPreview(null); }} /></label><div className="button-row"><button disabled={!csv} onClick={() => csvAction(true)}>Validate only</button><button disabled={!csv || !preview} onClick={() => csvAction(false)}>Confirm import</button></div>{preview ? <div><h3>Validation preview</h3><ul>{preview.rows.map((row) => <li key={row.row}>Row {row.row}: {row.status}{row.error ? ` — ${row.error}` : ""}</li>)}</ul></div> : null}</div> : null}
    {result ? <p role="status">Import completed.</p> : null}
  </section>;
}

export function JobDetailPage() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [error, setError] = useState("");
  const load = () => apiJson(`/api/jobs/${jobId}`).then(setJob).catch((value) => setError(value.message));
  useEffect(() => { load(); }, [jobId]);
  const mutate = async (path, body) => { try { await apiJson(path, { method: "POST", body }); await load(); } catch (value) { setError(value.message); } };
  if (error && !job) return <ErrorMessage value={error} />;
  if (!job) return <p>Loading Job…</p>;
  return <section><div className="section-heading"><div><h2>{job.title || "Untitled Job"}</h2><p>{job.company_name || "Company needs review"} · {job.location || "Location needs review"}</p></div><span className="status-badge">{job.status}</span></div>
    <ErrorMessage value={error} />
    <div className="button-row"><button onClick={() => { setDraft({ company_name: job.company_name || "", title: job.title || "", location: job.location || "", description: job.description }); setEditing(!editing); }}>{editing ? "Cancel edit" : "Edit Job"}</button></div>
    {editing ? <form className="form-grid" onSubmit={async (event) => { event.preventDefault(); try { const updated = await apiJson(`/api/jobs/${job.id}`, { method: "PATCH", body: { ...draft, expected_revision: job.revision } }); setJob({ ...job, ...updated }); setEditing(false); setError(""); } catch (value) { setError(value.message); } }}>
      <label>Company<input required value={draft.company_name} onChange={(event) => setDraft({ ...draft, company_name: event.target.value })} /></label>
      <label>Title<input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
      <label>Location<input value={draft.location} onChange={(event) => setDraft({ ...draft, location: event.target.value })} /></label>
      <label className="full-width">Description<textarea required rows="10" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label>
      <button type="submit">Save Job</button>
    </form> : null}
    <dl className="detail-grid"><dt>Work mode</dt><dd>{job.work_mode || "Not provided"}</dd><dt>Employment type</dt><dd>{job.employment_type || "Not provided"}</dd><dt>Salary</dt><dd>{job.salary_min || job.salary_max ? `${job.salary_currency || ""} ${job.salary_min || "?"}–${job.salary_max || "?"}` : "Not provided"}</dd><dt>Deadline</dt><dd>{job.application_deadline ? new Date(job.application_deadline).toLocaleString() : "Not provided"}</dd></dl>
    <MatchPanel jobId={jobId} />
    <h3>Job Description</h3><pre className="untrusted-text">{job.description}</pre>
    <div className="section-heading"><h3>Requirements</h3><button onClick={() => mutate(`/api/jobs/${jobId}/extract-requirements`, {})}>Extract requirements</button></div>
    {!job.requirements.length ? <p>No requirements extracted.</p> : <div className="card-list">{job.requirements.map((item) => <article key={item.id} className="resource-card"><strong>{item.name}</strong><span className="status-badge">{item.verification_status}</span>{item.evidence_text ? <blockquote>{item.evidence_text}</blockquote> : null}<div className="button-row"><button onClick={() => apiJson(`/api/jobs/${jobId}/requirements/${item.id}`, { method: "PATCH", body: { verification_status: "confirmed" } }).then(load)}>Confirm</button><button onClick={() => apiJson(`/api/jobs/${jobId}/requirements/${item.id}`, { method: "PATCH", body: { verification_status: "rejected" } }).then(load)}>Reject</button></div></article>)}</div>}
    <h3>Sources</h3><ul>{job.sources.map((source) => <li key={source.id}>{source.source_type} · {source.media_type || "manual"}</li>)}</ul>
    <h3>Duplicate Candidates</h3>{job.duplicate_candidates?.length ? <ul>{job.duplicate_candidates.map((candidate) => { const candidateId = candidate.job_id === job.id ? candidate.candidate_job_id : candidate.job_id; return <li key={candidate.id}>{candidate.match_type} ({Math.round(candidate.similarity_score * 100)}%) <button onClick={() => mutate(`/api/jobs/${job.id}/duplicates/${candidateId}/resolve`, { action: "confirm_duplicate" })}>Confirm duplicate</button><button onClick={() => mutate(`/api/jobs/${job.id}/duplicates/${candidateId}/resolve`, { action: "not_duplicate" })}>Not duplicate</button></li>; })}</ul> : <p>No duplicate candidates.</p>}
    <div className="button-row">{job.linked_application_id ? <Link to={`/applications/${job.linked_application_id}`}>Open Application</Link> : <button onClick={async () => { try { const value = await apiJson("/api/applications", { method: "POST", body: { job_id: job.id } }); navigate(`/applications/${value.application.id}`); } catch (value) { setError(value.message); } }}>Create Application</button>}<button onClick={async () => { try { await apiJson(`/api/jobs/${jobId}/archive`, { method: "POST", body: { expected_revision: job.revision } }); navigate("/jobs"); } catch (value) { setError(value.message); } }}>Archive</button></div>
  </section>;
}
