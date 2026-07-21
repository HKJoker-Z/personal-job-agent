import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiJson } from "../api/client";

export function ResumeLibraryPage() {
  const [resumes, setResumes] = useState([]);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => apiJson("/api/resumes").then(setResumes), []);
  useEffect(() => { load().catch((value) => setError(value.message)); }, [load]);

  async function upload(event) {
    event.preventDefault();
    if (!file || !/\.(pdf|docx|txt|md|markdown)$/i.test(file.name)) {
      setError("Select a PDF, DOCX, TXT, or Markdown resume.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    setLoading(true); setError(""); setMessage("");
    try {
      const result = await apiJson("/api/resumes/upload", { method: "POST", body: form });
      setMessage(`${result.resume.title} uploaded and set as the Primary Resume.`);
      setFile(null);
      await load();
    } catch (value) {
      setError(value.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="panel resume-library"><div className="section-heading"><div><h2>Resume Library</h2><p className="muted">The latest successful upload becomes the default resume for Analyze.</p></div></div>
    <form className="resume-upload-area" onSubmit={upload}>
      <h3>Upload Resume</h3>
      <p>PDF, DOCX, TXT, or Markdown · maximum 10 MB</p>
      <input aria-label="Upload Resume file" type="file" accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      <button type="submit" disabled={loading}>{loading ? "Uploading..." : "Upload Resume"}</button>
    </form>
    {error && <div className="error" role="alert">{error}</div>}
    {message && <p className="history-message" role="status">{message}</p>}
    {!resumes.length && !error && <p>No stored resumes yet.</p>}
    <div className="history-list">{resumes.map((resume) => <article key={resume.id}><div className="section-heading"><h3><Link to={`/resumes/${resume.id}`}>{resume.title}</Link></h3>{resume.is_primary && <span className="status-badge primary-resume-badge">Primary Resume</span>}</div><p>{resume.language} · {resume.target_role || "General"} · active {resume.active_version_id || "none"}</p></article>)}</div>
  </section>;
}

export function ResumeDetailPage() {
  const { resumeId } = useParams(); const [resume, setResume] = useState(null); const [versions, setVersions] = useState([]); const [error, setError] = useState("");
  useEffect(() => { Promise.all([apiJson(`/api/resumes/${resumeId}`), apiJson(`/api/resumes/${resumeId}/versions`)]).then(([r, v]) => { setResume(r); setVersions(v); }).catch((e) => setError(e.message)); }, [resumeId]);
  async function finalize(id) { if (!window.confirm("Finalize this immutable Resume Version?")) return; try { await apiJson(`/api/resumes/${resumeId}/versions/${id}/finalize`, { method: "POST" }); setVersions(await apiJson(`/api/resumes/${resumeId}/versions`)); } catch (e) { setError(e.message); } }
  return <section className="panel"><div className="section-heading"><h2>{resume?.title || "Resume Detail"}</h2>{resume?.is_primary && <span className="status-badge primary-resume-badge">Primary Resume</span>}</div>{error && <div className="error">{error}</div>}<h3>Version History</h3>
    {versions.map((version) => <article key={version.id}><strong>Version {version.version_number}</strong> · {version.status} <button type="button" onClick={() => finalize(version.id)} disabled={version.status === "final"}>Finalize</button></article>)}
  </section>;
}

export function ResumeImportPage() {
  const [file, setFile] = useState(null); const [result, setResult] = useState(null); const [error, setError] = useState("");
  async function submit(event) { event.preventDefault(); if (!file || !/\.(pdf|docx|txt|md|markdown)$/i.test(file.name)) { setError("Select a PDF, DOCX, TXT, or Markdown resume."); return; } const form = new FormData(); form.append("file", file); try { setResult(await apiJson("/api/resumes/upload", { method: "POST", body: form })); setError(""); } catch (e) { setError(e.message); } }
  return <section className="panel form-panel"><h2>Upload Resume</h2><p>Uploaded text is parsed locally and becomes the Primary Resume after a successful upload.</p><form onSubmit={submit}><input aria-label="Resume file" type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={(e) => setFile(e.target.files?.[0] || null)} />{error && <div className="error">{error}</div>}<button type="submit">Upload Resume</button></form>{result && <p role="status">Resume uploaded and set as the Primary Resume.</p>}</section>;
}
