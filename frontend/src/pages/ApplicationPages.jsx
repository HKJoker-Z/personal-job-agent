import React, { useCallback, useEffect, useState } from "react";
import { apiJson } from "../api/client";

function formatAppliedTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value || "Unknown") : date.toLocaleString();
}

export function ApplicationsPage() {
  const [applications, setApplications] = useState([]);
  const [resumes, setResumes] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const [applicationItems, resumeItems] = await Promise.all([
      apiJson("/api/applications"),
      apiJson("/api/resumes"),
    ]);
    setApplications(Array.isArray(applicationItems) ? applicationItems : []);
    setResumes(Array.isArray(resumeItems) ? resumeItems : []);
  }, []);

  useEffect(() => {
    load().catch((value) => setError(value.message)).finally(() => setLoading(false));
  }, [load]);

  async function createApplication(event) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true); setError(""); setMessage("");
    try {
      await apiJson("/api/applications", {
        method: "POST",
        body: {
          company_name: companyName,
          job_title: jobTitle,
          job_description: jobDescription,
          resume_version_id: resumeVersionId || null,
        },
      });
      setCompanyName(""); setJobTitle(""); setJobDescription(""); setResumeVersionId("");
      setShowForm(false);
      setMessage("Application recorded successfully.");
      await load();
    } catch (value) {
      setError(value.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function viewApplication(applicationId) {
    setError("");
    try {
      setSelected(await apiJson(`/api/applications/${applicationId}`));
    } catch (value) {
      setError(value.message);
    }
  }

  return <section className="applications-page">
    <section className="panel">
      <div className="section-heading"><div><span className="eyebrow">Applications</span><h1>Applications</h1><p className="muted">Jobs you have actually applied to.</p></div><button type="button" onClick={() => setShowForm((value) => !value)}>Add Application</button></div>
      {showForm && <form className="form-panel" onSubmit={createApplication}>
        <label>Company Name<input value={companyName} onChange={(event) => setCompanyName(event.target.value)} required maxLength="500" /></label>
        <label>Job Title<input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} required maxLength="500" /></label>
        <label>Job Description<textarea rows="8" value={jobDescription} onChange={(event) => setJobDescription(event.target.value)} /></label>
        <label>Resume<select aria-label="Resume" value={resumeVersionId} onChange={(event) => setResumeVersionId(event.target.value)}><option value="">No Resume</option>{resumes.filter((resume) => resume.active_version_id).map((resume) => <option key={resume.active_version_id} value={resume.active_version_id}>{resume.title}{resume.is_primary ? " · Primary Resume" : ""}</option>)}</select></label>
        <div className="action-row"><button type="submit" disabled={submitting}>{submitting ? "Saving..." : "Confirm Application"}</button><button type="button" className="secondary-button" onClick={() => setShowForm(false)}>Cancel</button></div>
      </form>}
      {error && <div className="error" role="alert">{error}</div>}
      {message && <p className="history-message" role="status">{message}</p>}
    </section>

    {selected ? <section className="panel detail-panel">
      <div className="detail-header"><div><span className="label">Application</span><h2>{selected.job_title}</h2><p>{selected.company_name}</p></div><button type="button" onClick={() => setSelected(null)}>Back to Applications</button></div>
      <div className="detail-grid"><div><span className="label">Applied Time</span><p>{formatAppliedTime(selected.applied_at)}</p></div><div><span className="label">Resume</span><p>{selected.resume_snapshot ? "Saved snapshot" : "Not provided"}</p></div></div>
      <section className="result-section"><h3>Job Description</h3><p className="plain-note">{selected.job_description || "Not provided"}</p></section>
      <section className="result-section"><h3>Resume Snapshot</h3><p className="plain-note">{selected.resume_snapshot || "Not provided"}</p></section>
    </section> : <section className="panel list-panel">
      {loading ? <p>Loading Applications...</p> : applications.length === 0 ? <p>No Applications yet.</p> : <div className="table-wrap"><table><thead><tr><th>Company</th><th>Job Title</th><th>Applied Time</th><th>Actions</th></tr></thead><tbody>{applications.map((application) => <tr key={application.id}><td>{application.company_name}</td><td>{application.job_title}</td><td>{formatAppliedTime(application.applied_at)}</td><td><button type="button" onClick={() => viewApplication(application.id)}>View</button></td></tr>)}</tbody></table></div>}
    </section>}
  </section>;
}
