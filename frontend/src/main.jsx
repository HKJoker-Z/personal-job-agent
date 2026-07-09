import React, { Component, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://101.34.61.52:8000";
const APPLICATION_STATUSES = ["Saved", "Applied", "Interview", "Rejected", "Offer"];

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function clampScore(value) {
  const score = Number.parseInt(value, 10);
  if (Number.isNaN(score)) {
    return 0;
  }
  return Math.max(0, Math.min(100, score));
}

function displayCompany(value) {
  return String(value || "").trim() || "Unknown Company";
}

function displayPosition(value) {
  return String(value || "").trim() || "Unknown Position";
}

function displayText(value, fallback = "Not provided") {
  return String(value || "").trim() || fallback;
}

function formatDate(value) {
  if (!value) {
    return "Unknown";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function getBackendErrorMessage(data, fallback = "Request failed.") {
  if (!data?.detail) {
    return fallback;
  }

  if (typeof data.detail === "string") {
    return data.detail;
  }

  return fallback;
}

function getRequestErrorMessage(error, fallback) {
  if (error instanceof TypeError) {
    return "Cannot connect to backend. Please check if FastAPI server is running.";
  }

  return error.message || fallback;
}

async function requestJson(url, options, fallback) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(getBackendErrorMessage(data, fallback));
  }

  return data || {};
}

function ResultList({ title, items }) {
  const safeItems = asArray(items);

  return (
    <section className="result-section">
      <h3>{title}</h3>
      {safeItems.length ? (
        <ul>
          {safeItems.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No items found.</p>
      )}
    </section>
  );
}

function AnalysisResult({ result }) {
  const score = clampScore(result?.match_score);
  const savedToHistory = Boolean(result?.saved_to_history);

  return (
    <section className="panel results-panel">
      <div className="score-row">
        <div>
          <span className="label">Match Score</span>
          <strong>{score}/100</strong>
        </div>
        <div className="job-identity">
          <span>{displayCompany(result?.company_name)}</span>
          <strong>{displayPosition(result?.job_title)}</strong>
        </div>
      </div>

      <div className={savedToHistory ? "history-message" : "history-message muted-message"}>
        {savedToHistory
          ? `Saved to history. Application ID: ${result.application_id}`
          : "Not saved to history."}
      </div>

      <section className="result-section">
        <h3>岗位摘要</h3>
        <p>{result.job_summary || "No summary generated."}</p>
      </section>

      <section className="result-section">
        <h3>匹配原因</h3>
        <p>{result.match_reason || "No match reason generated."}</p>
      </section>

      <ResultList title="匹配技能" items={result.matched_skills} />
      <ResultList title="缺失技能" items={result.missing_skills} />
      <ResultList title="简历优化建议" items={result.resume_suggestions} />

      <section className="result-section cover-letter-section">
        <h3>English Cover Letter</h3>
        <pre>{result.cover_letter || "No cover letter generated."}</pre>
      </section>
    </section>
  );
}

function AnalyzePage() {
  const [resume, setResume] = useState(null);
  const [jobText, setJobText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [saveToHistory, setSaveToHistory] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  function handleResumeChange(event) {
    const file = event.target.files?.[0] || null;
    setResume(file);
    if (file) {
      setError("");
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    if (loading) {
      return;
    }

    setError("");
    setResult(null);

    if (!resume) {
      setError("Please upload a PDF or DOCX resume.");
      return;
    }

    const fileName = resume.name.toLowerCase();
    if (!fileName.endsWith(".pdf") && !fileName.endsWith(".docx")) {
      setError("Please upload a PDF or DOCX resume.");
      return;
    }

    if (!jobText.trim() && !jobUrl.trim()) {
      setError("Please provide at least one job description or job URL.");
      return;
    }

    const formData = new FormData();
    formData.append("resume", resume);
    formData.append("job_text", jobText);
    formData.append("job_url", jobUrl);
    formData.append("save_to_history", saveToHistory ? "true" : "false");

    setLoading(true);
    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/analyze`,
        {
          method: "POST",
          body: formData,
        },
        "Analyze request failed.",
      );

      setResult(data);
    } catch (err) {
      setError(getRequestErrorMessage(err, "Analyze request failed."));
    } finally {
      setLoading(false);
    }
  }

  const hasResult = Boolean(result);

  return (
    <>
      <form className="panel form-panel" onSubmit={handleAnalyze}>
        <label>
          Resume
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={handleResumeChange}
          />
        </label>

        <label>
          Job Description
          <textarea
            rows="10"
            value={jobText}
            onChange={(event) => setJobText(event.target.value)}
            placeholder="Paste the JD text here. This will be used before the URL if both are provided."
          />
        </label>

        <label>
          Job URL
          <input
            type="url"
            value={jobUrl}
            onChange={(event) => setJobUrl(event.target.value)}
            placeholder="https://example.com/job-posting"
          />
        </label>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={saveToHistory}
            onChange={(event) => setSaveToHistory(event.target.checked)}
          />
          Save this analysis to history
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </form>

      {error && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>Analysis failed</strong>
          <p>{error}</p>
        </section>
      )}

      {loading && (
        <section className="panel state-panel">
          <strong>Analyzing...</strong>
          <p className="muted">Parsing resume, reading job content, and calling the AI service.</p>
        </section>
      )}

      {!hasResult && !loading && !error && (
        <section className="panel state-panel">
          <p className="muted">Upload your resume and provide a job description or URL to start analysis.</p>
        </section>
      )}

      {hasResult && <AnalysisResult result={result} />}
    </>
  );
}

function HistoryPage() {
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailStatus, setDetailStatus] = useState("Saved");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  async function loadApplications() {
    if (loading) {
      return;
    }

    setLoading(true);
    setError("");

    const params = new URLSearchParams();
    params.set("limit", "50");
    params.set("offset", "0");
    if (statusFilter !== "All") {
      params.set("status", statusFilter);
    }
    if (search.trim()) {
      params.set("search", search.trim());
    }

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/applications?${params.toString()}`,
        undefined,
        "Failed to load history.",
      );
      setRecords(asArray(data.items));
      setTotal(Number.isFinite(Number(data.total)) ? Number(data.total) : 0);
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to load history."));
      setRecords([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadApplications();
  }, []);

  async function handleView(applicationId) {
    if (detailLoading) {
      return;
    }

    setDetailLoading(true);
    setDetailError("");

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/applications/${applicationId}`,
        undefined,
        "Failed to load application details.",
      );
      setSelectedRecord(data);
      setDetailStatus(data.application_status || "Saved");
      setNotes(data.notes || "");
    } catch (err) {
      setDetailError(getRequestErrorMessage(err, "Failed to load application details."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleSaveChanges() {
    if (!selectedRecord || saving) {
      return;
    }

    setSaving(true);
    setDetailError("");

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/applications/${selectedRecord.id}`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            application_status: detailStatus,
            notes,
          }),
        },
        "Failed to save changes.",
      );
      setSelectedRecord(data);
      setDetailStatus(data.application_status || "Saved");
      setNotes(data.notes || "");
      await loadApplications();
    } catch (err) {
      setDetailError(getRequestErrorMessage(err, "Failed to save changes."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(applicationId) {
    if (deletingId || !window.confirm("Delete this application record?")) {
      return;
    }

    setDeletingId(applicationId);
    setError("");
    setDetailError("");

    try {
      await requestJson(
        `${API_BASE_URL}/api/applications/${applicationId}`,
        { method: "DELETE" },
        "Failed to delete application record.",
      );
      if (selectedRecord?.id === applicationId) {
        setSelectedRecord(null);
      }
      await loadApplications();
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to delete application record."));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <section className="panel history-panel">
        <div className="history-toolbar">
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="All">All</option>
              {APPLICATION_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>

          <label>
            Search
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Company or position"
            />
          </label>

          <button type="button" onClick={loadApplications} disabled={loading}>
            {loading ? "Loading history..." : "Refresh"}
          </button>
        </div>
      </section>

      {error && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>History request failed</strong>
          <p>{error}</p>
        </section>
      )}

      {loading && (
        <section className="panel state-panel">
          <strong>Loading history...</strong>
          <p className="muted">Fetching application records from the local database.</p>
        </section>
      )}

      {!loading && !error && records.length === 0 && (
        <section className="panel state-panel">
          <p className="muted">No application records yet.</p>
        </section>
      )}

      {records.length > 0 && (
        <section className="panel list-panel">
          <div className="list-summary">
            <strong>{total}</strong>
            <span className="muted">record{total === 1 ? "" : "s"} found</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Position</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td>{displayCompany(record.company_name)}</td>
                    <td>{displayPosition(record.job_title)}</td>
                    <td>{clampScore(record.match_score)}/100</td>
                    <td>
                      <span className="status-pill">{record.application_status || "Saved"}</span>
                    </td>
                    <td>{formatDate(record.created_at)}</td>
                    <td>
                      <div className="action-row">
                        <button type="button" onClick={() => handleView(record.id)} disabled={detailLoading}>
                          View
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDelete(record.id)}
                          disabled={deletingId === record.id}
                        >
                          {deletingId === record.id ? "Deleting..." : "Delete"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {detailLoading && (
        <section className="panel state-panel">
          <strong>Loading history...</strong>
          <p className="muted">Fetching application details.</p>
        </section>
      )}

      {detailError && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>Detail request failed</strong>
          <p>{detailError}</p>
        </section>
      )}

      {selectedRecord && (
        <section className="panel detail-panel">
          <div className="detail-header">
            <div>
              <span className="label">Application #{selectedRecord.id}</span>
              <h2>{displayPosition(selectedRecord.job_title)}</h2>
              <p>{displayCompany(selectedRecord.company_name)}</p>
            </div>
            <strong>{clampScore(selectedRecord.match_score)}/100</strong>
          </div>

          <div className="detail-grid">
            <div>
              <span className="label">Status</span>
              <p>{selectedRecord.application_status || "Saved"}</p>
            </div>
            <div>
              <span className="label">Created</span>
              <p>{formatDate(selectedRecord.created_at)}</p>
            </div>
            <div>
              <span className="label">Updated</span>
              <p>{formatDate(selectedRecord.updated_at)}</p>
            </div>
            <div>
              <span className="label">Resume File</span>
              <p>{displayText(selectedRecord.resume_filename)}</p>
            </div>
            <div className="wide-field">
              <span className="label">Job URL</span>
              <p>{displayText(selectedRecord.job_url)}</p>
            </div>
          </div>

          <section className="result-section">
            <h3>Match Reason</h3>
            <p>{selectedRecord.match_reason || "No match reason generated."}</p>
          </section>

          <section className="result-section">
            <h3>Job Summary</h3>
            <p>{selectedRecord.job_summary || "No summary generated."}</p>
          </section>

          <ResultList title="Matched Skills" items={selectedRecord.matched_skills} />
          <ResultList title="Missing Skills" items={selectedRecord.missing_skills} />
          <ResultList title="Resume Suggestions" items={selectedRecord.resume_suggestions} />

          <section className="result-section cover-letter-section">
            <h3>Cover Letter</h3>
            <pre>{selectedRecord.cover_letter || "No cover letter generated."}</pre>
          </section>

          <section className="edit-section">
            <h3>Update Application</h3>
            <label>
              Status
              <select value={detailStatus} onChange={(event) => setDetailStatus(event.target.value)}>
                {APPLICATION_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Notes
              <textarea rows="4" value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
            <button type="button" onClick={handleSaveChanges} disabled={saving}>
              {saving ? "Saving changes..." : "Save Changes"}
            </button>
          </section>
        </section>
      )}
    </>
  );
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-shell">
          <section className="panel form-panel">
            <h1>Personal Job Application Agent</h1>
            <div className="error">Frontend failed to render: {this.state.error.message}</div>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

function App() {
  const [activeTab, setActiveTab] = useState("analyze");

  return (
    <main className="app-shell">
      <header className="page-header">
        <h1>Personal Job Application Agent</h1>
        <p>Upload your resume, analyze one role, and track saved application records locally.</p>
      </header>

      <nav className="tabs" aria-label="Main sections">
        <button
          type="button"
          className={activeTab === "analyze" ? "active-tab" : ""}
          onClick={() => setActiveTab("analyze")}
        >
          Analyze
        </button>
        <button
          type="button"
          className={activeTab === "history" ? "active-tab" : ""}
          onClick={() => setActiveTab("history")}
        >
          History
        </button>
      </nav>

      {activeTab === "analyze" ? <AnalyzePage /> : <HistoryPage />}

      <footer className="app-footer">API Base URL: {API_BASE_URL}</footer>
    </main>
  );
}

const rootElement = document.getElementById("root");

if (!rootElement) {
  document.body.textContent = "Frontend failed to start: missing #root element.";
} else {
  createRoot(rootElement).render(
    <ErrorBoundary>
      <App />
    </ErrorBoundary>,
  );
}
