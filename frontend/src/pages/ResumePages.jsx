import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

export function ResumeLibraryPage() {
  const [resumes, setResumes] = useState([]); const [error, setError] = useState("");
  useEffect(() => { apiJson("/api/resumes").then(setResumes).catch((e) => setError(e.message)); }, []);
  return <section className="panel"><h2>Resume Library</h2>{error && <div className="error">{error}</div>}
    {!resumes.length && <p>No stored resumes yet.</p>}
    <div className="history-list">{resumes.map((resume) => <article key={resume.id}><h3><Link to={`/resumes/${resume.id}`}>{resume.title}</Link></h3><p>{resume.language} · {resume.target_role || "General"} · active {resume.active_version_id || "none"}</p></article>)}</div>
  </section>;
}

export function ResumeDetailPage() {
  const { resumeId } = useParams(); const [resume, setResume] = useState(null); const [versions, setVersions] = useState([]); const [error, setError] = useState("");
  useEffect(() => { Promise.all([apiJson(`/api/resumes/${resumeId}`), apiJson(`/api/resumes/${resumeId}/versions`)]).then(([r, v]) => { setResume(r); setVersions(v); }).catch((e) => setError(e.message)); }, [resumeId]);
  async function finalize(id) { if (!window.confirm("Finalize this immutable Resume Version?")) return; try { await apiJson(`/api/resumes/${resumeId}/versions/${id}/finalize`, { method: "POST" }); setVersions(await apiJson(`/api/resumes/${resumeId}/versions`)); } catch (e) { setError(e.message); } }
  return <section className="panel"><h2>{resume?.title || "Resume Detail"}</h2>{error && <div className="error">{error}</div>}<h3>Version History</h3>
    {versions.map((version) => <article key={version.id}><strong>Version {version.version_number}</strong> · {version.status} <button type="button" onClick={() => finalize(version.id)} disabled={version.status === "final"}>Finalize</button></article>)}
  </section>;
}

export function ResumeImportPage() {
  const [file, setFile] = useState(null); const [result, setResult] = useState(null); const [error, setError] = useState("");
  async function submit(event) { event.preventDefault(); if (!file || !/\.(pdf|docx)$/i.test(file.name)) { setError("Select a PDF or DOCX resume."); return; } const form = new FormData(); form.append("file", file); try { setResult(await apiJson("/api/resumes/import", { method: "POST", body: form })); setError(""); } catch (e) { setError(e.message); } }
  return <section className="panel form-panel"><h2>Import Resume</h2><p>Import uses deterministic local parsing and never calls AI. Parsed fields require human review.</p><form onSubmit={submit}><input aria-label="Resume file" type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files?.[0] || null)} />{error && <div className="error">{error}</div>}<button type="submit">Import</button></form>{result && <p role="status">Draft imported. Review all needs_review fields before finalizing or copying confirmed items to Profile.</p>}</section>;
}
