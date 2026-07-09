import React, { Component, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://101.34.61.52:8000";
const APP_VERSION = "1.5";
const APPLICATION_STATUSES = ["Saved", "Applied", "Interview", "Rejected", "Offer"];
const KNOWLEDGE_CATEGORIES = [
  "Resume",
  "Project Experience",
  "Skill Profile",
  "Past Cover Letter",
  "Company Research",
  "Other",
];
const SCORING_DIMENSIONS = [
  { key: "skills_match", label: "Skills Match" },
  { key: "project_experience", label: "Project Experience" },
  { key: "education", label: "Education" },
  { key: "work_experience", label: "Work Experience" },
  { key: "keyword_match", label: "Keyword Match" },
];

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
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

function getDownloadFilename(response, fallback) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/i) || disposition.match(/filename=([^;]+)/i);
  if (!match) {
    return fallback;
  }

  return match[1].trim() || fallback;
}

async function downloadBlob(url, fallbackFilename, fallbackError) {
  const response = await fetch(url);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(getBackendErrorMessage(data, fallbackError));
  }

  const blob = await response.blob();
  const filename = getDownloadFilename(response, fallbackFilename);
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

function statusClassName(status) {
  const cleanStatus = String(status || "Saved").toLowerCase();
  return `status-pill status-${cleanStatus}`;
}

function StatusBadge({ status }) {
  const displayStatus = APPLICATION_STATUSES.includes(status) ? status : "Saved";
  return <span className={statusClassName(displayStatus)}>{displayStatus}</span>;
}

function ScoreSummary({ score }) {
  const safeScore = clampScore(score);

  return (
    <div className="score-summary" aria-label={`Match score ${safeScore} out of 100`}>
      <strong>{safeScore}</strong>
      <span>/100</span>
      <div className="score-meter" aria-hidden="true">
        <div style={{ width: `${safeScore}%` }} />
      </div>
    </div>
  );
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

function ExportActions({ applicationId, enabled = true }) {
  const [loadingType, setLoadingType] = useState("");
  const [error, setError] = useState("");
  const canDownload = enabled && Boolean(applicationId);

  async function handleDownload(type) {
    if (!canDownload || loadingType) {
      return;
    }

    const isDocx = type === "docx";
    const endpoint = isDocx ? "cover-letter.docx" : "report.pdf";
    const fallbackFilename = isDocx
      ? `cover-letter-${applicationId}.docx`
      : `analysis-report-${applicationId}.pdf`;
    const fallbackError = isDocx
      ? "Failed to download cover letter DOCX."
      : "Failed to download analysis report PDF.";

    setLoadingType(type);
    setError("");
    try {
      await downloadBlob(
        `${API_BASE_URL}/api/applications/${applicationId}/${endpoint}`,
        fallbackFilename,
        fallbackError,
      );
    } catch (err) {
      setError(getRequestErrorMessage(err, fallbackError));
    } finally {
      setLoadingType("");
    }
  }

  return (
    <section className="result-section export-section">
      <div className="section-heading-row">
        <h3>Exports</h3>
        {loadingType && <span className="muted">Preparing download...</span>}
      </div>
      {canDownload ? (
        <div className="export-actions">
          <button type="button" onClick={() => handleDownload("docx")} disabled={Boolean(loadingType)}>
            {loadingType === "docx" ? "Preparing DOCX..." : "Download Cover Letter DOCX"}
          </button>
          <button type="button" onClick={() => handleDownload("pdf")} disabled={Boolean(loadingType)}>
            {loadingType === "pdf" ? "Preparing PDF..." : "Download Analysis Report PDF"}
          </button>
        </div>
      ) : (
        <p className="muted">Enable save to history to download DOCX/PDF exports.</p>
      )}
      {error && (
        <div className="inline-error" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}

function ScoringBreakdownSection({ breakdown }) {
  const safeBreakdown = asObject(breakdown);
  const dimensions = SCORING_DIMENSIONS.map((dimension) => {
    const section = asObject(safeBreakdown[dimension.key]);
    return {
      ...dimension,
      score: clampScore(section.score),
      reason: displayText(section.reason, "No reason generated."),
      evidence: asArray(section.evidence),
    };
  });

  return (
    <section className="result-section scoring-section">
      <h3>Scoring Breakdown</h3>
      <div className="breakdown-grid">
        {dimensions.map((dimension) => (
          <article className="breakdown-card" key={dimension.key}>
            <div className="breakdown-card-header">
              <strong>{dimension.label}</strong>
              <span>{dimension.score}/100</span>
            </div>
            <p>{dimension.reason}</p>
            {dimension.evidence.length ? (
              <ul>
                {dimension.evidence.map((item, index) => (
                  <li key={`${dimension.key}-evidence-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">No evidence provided.</p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function KeywordGroup({ title, items, variant = "neutral" }) {
  const safeItems = asArray(items);

  return (
    <div className="keyword-group">
      <h4>{title}</h4>
      {safeItems.length ? (
        <div className="keyword-list">
          {safeItems.map((item, index) => (
            <span className={`keyword-chip ${variant}`} key={`${title}-${index}`}>
              {item}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted">No keywords found.</p>
      )}
    </div>
  );
}

function ATSAnalysisSection({ analysis }) {
  const safeAnalysis = asObject(analysis);

  return (
    <section className="result-section ats-section">
      <h3>ATS Keyword Analysis</h3>
      <div className="ats-grid">
        <KeywordGroup title="Important Keywords" items={safeAnalysis.important_keywords} />
        <KeywordGroup title="Matched Keywords" items={safeAnalysis.matched_keywords} variant="matched" />
        <KeywordGroup title="Missing Keywords" items={safeAnalysis.missing_keywords} variant="missing" />
        <div className="keyword-group suggestions-group">
          <h4>Keyword Suggestions</h4>
          {asArray(safeAnalysis.keyword_suggestions).length ? (
            <ul>
              {asArray(safeAnalysis.keyword_suggestions).map((item, index) => (
                <li key={`keyword-suggestion-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No keyword suggestions generated.</p>
          )}
        </div>
      </div>
    </section>
  );
}

function UpgradedResumeBulletsSection({ bullets }) {
  const safeBullets = asArray(bullets).filter((item) => asObject(item).original);

  return (
    <section className="result-section bullet-section">
      <h3>Upgraded Resume Bullets</h3>
      {safeBullets.length ? (
        <div className="bullet-grid">
          {safeBullets.map((item, index) => {
            const bullet = asObject(item);
            return (
              <article className="bullet-card" key={`bullet-${index}`}>
                <div>
                  <span className="label">Original</span>
                  <p>{displayText(bullet.original)}</p>
                </div>
                <div>
                  <span className="label">Improved</span>
                  <p>{displayText(bullet.improved, "No improved version generated.")}</p>
                </div>
                <div>
                  <span className="label">Reason</span>
                  <p>{displayText(bullet.reason, "No reason generated.")}</p>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="muted">No bullet improvements generated.</p>
      )}
    </section>
  );
}

function RagSourcesSection({ sources }) {
  const safeSources = asArray(sources).filter((source) => asObject(source).document_title || asObject(source).document_id);

  return (
    <section className="result-section rag-section">
      <h3>RAG Sources</h3>
      {safeSources.length ? (
        <div className="source-grid">
          {safeSources.map((source, index) => {
            const item = asObject(source);
            return (
              <article className="source-card" key={`rag-source-${index}`}>
                <div className="source-card-header">
                  <strong>{displayText(item.document_title, "Untitled knowledge document")}</strong>
                  <span>{displayText(item.category, "Other")}</span>
                </div>
                <p className="muted">Chunk #{Number.parseInt(item.chunk_index, 10) || 0}</p>
                <p>{displayText(item.relevance_reason, "No relevance reason provided.")}</p>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="muted">No RAG sources used.</p>
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
          <ScoreSummary score={score} />
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
      <ScoringBreakdownSection breakdown={result.scoring_breakdown} />
      <ATSAnalysisSection analysis={result.ats_analysis} />
      <UpgradedResumeBulletsSection bullets={result.upgraded_resume_bullets} />
      <RagSourcesSection sources={result.rag_sources} />
      <ExportActions applicationId={result.application_id} enabled={savedToHistory} />

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
  const [useKnowledgeBase, setUseKnowledgeBase] = useState(true);
  const [ragTopK, setRagTopK] = useState(5);
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
    formData.append("use_knowledge_base", useKnowledgeBase ? "true" : "false");
    formData.append("rag_top_k", String(Math.max(1, Math.min(10, Number(ragTopK) || 5))));

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
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Analyze</span>
            <h2>Resume-JD Matching</h2>
          </div>
          <span className="version-pill">v{APP_VERSION}</span>
        </div>
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

        <div className="rag-controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={useKnowledgeBase}
              onChange={(event) => setUseKnowledgeBase(event.target.checked)}
            />
            Use Knowledge Base RAG
          </label>

          <label>
            RAG Top K
            <input
              type="number"
              min="1"
              max="10"
              value={ragTopK}
              onChange={(event) => setRagTopK(event.target.value)}
              disabled={!useKnowledgeBase}
            />
          </label>
        </div>

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
          <strong>Ready for one focused application analysis.</strong>
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
        <div className="panel-heading">
          <div>
            <span className="eyebrow">History</span>
            <h2>Application Records</h2>
          </div>
          <span className="version-pill">{total} saved</span>
        </div>
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
          <strong>No application records yet.</strong>
          <p className="muted">Save an analysis result to build your application history.</p>
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
                      <StatusBadge status={record.application_status} />
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
              <p>
                <StatusBadge status={selectedRecord.application_status} />
              </p>
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
          <ScoringBreakdownSection breakdown={selectedRecord.scoring_breakdown} />
          <ATSAnalysisSection analysis={selectedRecord.ats_analysis} />
          <UpgradedResumeBulletsSection bullets={selectedRecord.upgraded_resume_bullets} />
          <RagSourcesSection sources={selectedRecord.rag_sources} />
          <ExportActions applicationId={selectedRecord.id} />

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

function KnowledgeBasePage() {
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [documentSearch, setDocumentSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("Project Experience");
  const [contentText, setContentText] = useState("");
  const [file, setFile] = useState(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTopK, setSearchTopK] = useState(5);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  async function loadDocuments() {
    if (loading) {
      return;
    }

    setLoading(true);
    setError("");

    const params = new URLSearchParams();
    params.set("limit", "50");
    params.set("offset", "0");
    if (categoryFilter !== "All") {
      params.set("category", categoryFilter);
    }
    if (documentSearch.trim()) {
      params.set("search", documentSearch.trim());
    }

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/knowledge/documents?${params.toString()}`,
        undefined,
        "Failed to load knowledge documents.",
      );
      setDocuments(asArray(data.items));
      setTotal(Number.isFinite(Number(data.total)) ? Number(data.total) : 0);
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to load knowledge documents."));
      setDocuments([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocuments();
  }, []);

  async function handleAddDocument(event) {
    event.preventDefault();
    if (adding) {
      return;
    }

    setAddError("");
    if (!title.trim()) {
      setAddError("Please provide a document title.");
      return;
    }
    if (!contentText.trim() && !file) {
      setAddError("Please provide text content or upload a supported file.");
      return;
    }

    const formData = new FormData();
    formData.append("title", title.trim());
    formData.append("category", category);
    formData.append("content_text", contentText);
    if (file) {
      formData.append("file", file);
    }

    setAdding(true);
    try {
      await requestJson(
        `${API_BASE_URL}/api/knowledge/documents`,
        {
          method: "POST",
          body: formData,
        },
        "Failed to add knowledge document.",
      );
      setTitle("");
      setCategory("Project Experience");
      setContentText("");
      setFile(null);
      setFileInputKey((value) => value + 1);
      await loadDocuments();
    } catch (err) {
      setAddError(getRequestErrorMessage(err, "Failed to add knowledge document."));
    } finally {
      setAdding(false);
    }
  }

  async function handleViewDocument(documentId) {
    if (detailLoading) {
      return;
    }

    setDetailLoading(true);
    setDetailError("");

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/knowledge/documents/${documentId}`,
        undefined,
        "Failed to load knowledge document.",
      );
      setSelectedDocument(data);
    } catch (err) {
      setDetailError(getRequestErrorMessage(err, "Failed to load knowledge document."));
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleDeleteDocument(documentId) {
    if (deletingId || !window.confirm("Delete this knowledge document?")) {
      return;
    }

    setDeletingId(documentId);
    setError("");
    setDetailError("");

    try {
      await requestJson(
        `${API_BASE_URL}/api/knowledge/documents/${documentId}`,
        { method: "DELETE" },
        "Failed to delete knowledge document.",
      );
      if (selectedDocument?.id === documentId) {
        setSelectedDocument(null);
      }
      await loadDocuments();
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to delete knowledge document."));
    } finally {
      setDeletingId(null);
    }
  }

  async function handleKnowledgeSearch(event) {
    event.preventDefault();
    if (searchLoading) {
      return;
    }

    setSearchError("");
    setHasSearched(true);
    if (!searchQuery.trim()) {
      setSearchError("Please enter a search query.");
      setSearchResults([]);
      return;
    }

    setSearchLoading(true);
    const params = new URLSearchParams();
    params.set("query", searchQuery.trim());
    params.set("top_k", String(Math.max(1, Math.min(10, Number(searchTopK) || 5))));

    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/knowledge/search?${params.toString()}`,
        undefined,
        "Failed to search knowledge base.",
      );
      setSearchResults(asArray(data.items));
    } catch (err) {
      setSearchError(getRequestErrorMessage(err, "Failed to search knowledge base."));
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }

  return (
    <>
      <form className="panel form-panel" onSubmit={handleAddDocument}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Knowledge Base</span>
            <h2>Add Knowledge Document</h2>
          </div>
          <span className="version-pill">{total} docs</span>
        </div>

        <label>
          Title
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Stock prediction project, Cloud skills profile, Company research..."
          />
        </label>

        <label>
          Category
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            {KNOWLEDGE_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>

        <label>
          Content Text
          <textarea
            rows="7"
            value={contentText}
            onChange={(event) => setContentText(event.target.value)}
            placeholder="Paste project notes, skill profile, company research, or previous cover letter content."
          />
        </label>

        <label>
          Upload File
          <input
            key={fileInputKey}
            type="file"
            accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
        </label>

        <button type="submit" disabled={adding}>
          {adding ? "Adding..." : "Add to Knowledge Base"}
        </button>

        {addError && (
          <div className="inline-error" role="alert">
            {addError}
          </div>
        )}
      </form>

      <section className="panel history-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Browse</span>
            <h2>Knowledge Documents</h2>
          </div>
          <button type="button" onClick={loadDocuments} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
        <div className="history-toolbar">
          <label>
            Category
            <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="All">All</option>
              {KNOWLEDGE_CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search
            <input
              type="search"
              value={documentSearch}
              onChange={(event) => setDocumentSearch(event.target.value)}
              placeholder="Title, filename, or preview"
            />
          </label>
          <button type="button" onClick={loadDocuments} disabled={loading}>
            Apply
          </button>
        </div>
      </section>

      {error && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>Knowledge request failed</strong>
          <p>{error}</p>
        </section>
      )}

      {!loading && !error && documents.length === 0 && (
        <section className="panel state-panel">
          <strong>No knowledge documents yet.</strong>
          <p className="muted">Add project, skill, resume, cover letter, or company research notes.</p>
        </section>
      )}

      {documents.length > 0 && (
        <section className="panel list-panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Category</th>
                  <th>Source</th>
                  <th>Chunks</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td>{displayText(document.title, "Untitled")}</td>
                    <td>
                      <span className="status-pill">{displayText(document.category, "Other")}</span>
                    </td>
                    <td>{displayText(document.source_filename)}</td>
                    <td>{Number.parseInt(document.chunk_count, 10) || 0}</td>
                    <td>{formatDate(document.created_at)}</td>
                    <td>
                      <div className="action-row">
                        <button type="button" onClick={() => handleViewDocument(document.id)} disabled={detailLoading}>
                          View
                        </button>
                        <button
                          type="button"
                          className="danger-button"
                          onClick={() => handleDeleteDocument(document.id)}
                          disabled={deletingId === document.id}
                        >
                          {deletingId === document.id ? "Deleting..." : "Delete"}
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

      <form className="panel history-panel" onSubmit={handleKnowledgeSearch}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Search</span>
            <h2>Test Retrieval</h2>
          </div>
          {searchLoading && <span className="muted">Searching...</span>}
        </div>
        <div className="history-toolbar">
          <label>
            Query
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Python LSTM stock prediction"
            />
          </label>
          <label>
            Top K
            <input
              type="number"
              min="1"
              max="10"
              value={searchTopK}
              onChange={(event) => setSearchTopK(event.target.value)}
            />
          </label>
          <button type="submit" disabled={searchLoading}>
            {searchLoading ? "Searching..." : "Search"}
          </button>
        </div>
        {searchError && (
          <div className="inline-error" role="alert">
            {searchError}
          </div>
        )}
      </form>

      {hasSearched && !searchLoading && !searchError && searchResults.length === 0 && (
        <section className="panel state-panel">
          <p className="muted">No relevant chunks found.</p>
        </section>
      )}

      {searchResults.length > 0 && (
        <section className="panel detail-panel">
          <h2>Search Results</h2>
          <div className="source-grid">
            {searchResults.map((result) => (
              <article className="source-card" key={result.chunk_id}>
                <div className="source-card-header">
                  <strong>{displayText(result.document_title, "Untitled knowledge document")}</strong>
                  <span>{displayText(result.category, "Other")}</span>
                </div>
                <p className="muted">
                  Chunk #{Number.parseInt(result.chunk_index, 10) || 0} · Score {Number(result.score || 0).toFixed(2)}
                </p>
                <p>{displayText(String(result.content || "").slice(0, 600), "No content preview.")}</p>
              </article>
            ))}
          </div>
        </section>
      )}

      {detailLoading && (
        <section className="panel state-panel">
          <strong>Loading document...</strong>
          <p className="muted">Fetching parsed chunks.</p>
        </section>
      )}

      {detailError && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>Document detail failed</strong>
          <p>{detailError}</p>
        </section>
      )}

      {selectedDocument && (
        <section className="panel detail-panel">
          <div className="detail-header">
            <div>
              <span className="label">Knowledge Document #{selectedDocument.id}</span>
              <h2>{displayText(selectedDocument.title, "Untitled")}</h2>
              <p>{displayText(selectedDocument.category, "Other")}</p>
            </div>
            <strong>{Number.parseInt(selectedDocument.chunk_count, 10) || 0} chunks</strong>
          </div>
          <div className="detail-grid">
            <div>
              <span className="label">Source File</span>
              <p>{displayText(selectedDocument.source_filename)}</p>
            </div>
            <div>
              <span className="label">Created</span>
              <p>{formatDate(selectedDocument.created_at)}</p>
            </div>
            <div>
              <span className="label">Updated</span>
              <p>{formatDate(selectedDocument.updated_at)}</p>
            </div>
            <div>
              <span className="label">Category</span>
              <p>{displayText(selectedDocument.category, "Other")}</p>
            </div>
          </div>
          <section className="result-section">
            <h3>Content Preview</h3>
            <p>{displayText(selectedDocument.content_preview)}</p>
          </section>
          <section className="result-section">
            <h3>Chunks</h3>
            {asArray(selectedDocument.chunks).length ? (
              <div className="chunk-list">
                {asArray(selectedDocument.chunks).map((chunk) => (
                  <article className="chunk-card" key={chunk.id}>
                    <strong>Chunk #{Number.parseInt(chunk.chunk_index, 10) || 0}</strong>
                    <p>{displayText(chunk.content)}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">No chunks found.</p>
            )}
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
        <div className="header-title-row">
          <h1>Personal Job Application Agent</h1>
          <span className="version-pill">v{APP_VERSION}</span>
        </div>
        <p>Resume-JD matching, RAG knowledge retrieval, ATS analysis, cover letter generation, and application tracking.</p>
        <div className="feature-strip" aria-label="Core product features">
          <span>RAG knowledge base</span>
          <span>Explainable scoring</span>
          <span>ATS keywords</span>
          <span>DOCX/PDF exports</span>
          <span>SQLite history</span>
        </div>
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
        <button
          type="button"
          className={activeTab === "knowledge" ? "active-tab" : ""}
          onClick={() => setActiveTab("knowledge")}
        >
          Knowledge Base
        </button>
      </nav>

      {activeTab === "analyze" && <AnalyzePage />}
      {activeTab === "history" && <HistoryPage />}
      {activeTab === "knowledge" && <KnowledgeBasePage />}

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
