import React, { Component, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://101.34.61.52:8000";
const APP_VERSION = "1.6";
const APPLICATION_STATUSES = ["Saved", "Applied", "Interview", "Rejected", "Offer"];
const NEXT_ACTION_DECISIONS = [
  { value: "accepted", label: "Accept Recommendation" },
  { value: "dismissed", label: "Dismiss" },
  { value: "completed", label: "Mark Completed" },
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

function displayRagMode(value) {
  const cleanValue = String(value || "").trim();
  if (!cleanValue) {
    return "Not recorded";
  }
  return cleanValue;
}

function displayConfidence(value) {
  const confidence = Number(value);
  if (!Number.isFinite(confidence)) {
    return "0%";
  }
  return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
}

function formatDuration(durationMs, durationUs, status = "") {
  const normalizedStatus = displayText(status).toLowerCase();
  if (normalizedStatus === "skipped") {
    return "Skipped";
  }

  const parsedUs = Number(durationUs);
  if (Number.isFinite(parsedUs) && parsedUs > 0 && parsedUs < 1000) {
    return "<1 ms";
  }

  const parsedMs = Number(durationMs);
  if (!Number.isFinite(parsedMs)) {
    return "N/A";
  }
  if (parsedMs > 0 && parsedMs < 1) {
    return "<1 ms";
  }
  if (parsedMs === 0 && ["completed", "failed"].includes(normalizedStatus)) {
    return "<1 ms";
  }
  if (parsedMs < 1000) {
    return `${parsedMs.toFixed(2)} ms`;
  }
  return `${(parsedMs / 1000).toFixed(2)} s`;
}

function isRagEnabled(value) {
  return displayRagMode(value).toLowerCase() === "project";
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

function RagSourcesSection({ sources, ragMode, usedKnowledgeBase }) {
  const safeSources = asArray(sources).filter((source) => asObject(source).document_title || asObject(source).document_id);
  const ragEnabled = isRagEnabled(ragMode);
  const usedKnowledge = usedKnowledgeBase ?? safeSources.length > 0;

  return (
    <section className="result-section rag-section">
      <h3>RAG Sources</h3>
      <div className="rag-summary">
        <p>
          <strong>RAG Mode:</strong> {displayRagMode(ragMode)}
        </p>
        <p>
          <strong>Used Knowledge Base:</strong> {usedKnowledge ? "Yes" : "No"}
        </p>
        <p>
          <strong>RAG Sources Count:</strong> {safeSources.length}
        </p>
      </div>
      {ragEnabled && safeSources.length > 0 && (
        <div className="history-message">Project Knowledge evidence was used in this analysis.</div>
      )}
      {ragEnabled && safeSources.length === 0 && (
        <div className="inline-error" role="alert">
          Project Knowledge RAG was enabled, but no relevant project evidence was retrieved.
        </div>
      )}
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
                {item.content_preview && (
                  <p className="muted">{displayText(String(item.content_preview).slice(0, 320))}</p>
                )}
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

function AgentWorkflowSection({ steps, workflowDurationMs, workflowDurationUs }) {
  const safeSteps = asArray(steps);
  const hasWorkflowDuration = workflowDurationMs !== undefined && workflowDurationMs !== null;

  return (
    <section className="result-section workflow-section">
      <h3>Agent Workflow</h3>
      {safeSteps.length ? (
        <>
          {hasWorkflowDuration && (
            <p className="muted">
              Total workflow duration: {formatDuration(workflowDurationMs, workflowDurationUs, "completed")}
            </p>
          )}
          <div className="workflow-list">
            {safeSteps.map((step, index) => {
              const item = asObject(step);
              const status = displayText(item.status, "pending");
              return (
                <article className="workflow-step" key={`${item.key || "step"}-${index}`}>
                  <div className="workflow-step-header">
                    <strong>{displayText(item.name, "Unnamed Step")}</strong>
                    <span className={`status-pill workflow-${status}`}>{status}</span>
                  </div>
                  <p>{displayText(item.message, "No message recorded.")}</p>
                  <p className="muted">{formatDuration(item.duration_ms, item.duration_us, item.status)}</p>
                </article>
              );
            })}
          </div>
        </>
      ) : (
        <p className="muted">No workflow audit trail is available for this older record.</p>
      )}
    </section>
  );
}

function NextActionSection({ nextAction, decision, applicationId, canPersistDecision, onDecisionUpdated }) {
  const action = asObject(nextAction);
  const hasRecommendation = Boolean(action.action || action.label);
  const [notes, setNotes] = useState("");
  const [savingDecision, setSavingDecision] = useState("");
  const [error, setError] = useState("");
  const [localDecision, setLocalDecision] = useState(decision || "pending");

  useEffect(() => {
    setLocalDecision(decision || "pending");
  }, [decision]);

  async function updateDecision(nextDecision) {
    if (!applicationId || savingDecision) {
      return;
    }

    setSavingDecision(nextDecision);
    setError("");
    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/applications/${applicationId}/next-action`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            decision: nextDecision,
            notes,
          }),
        },
        "Failed to update next-action decision.",
      );
      setLocalDecision(data.decision || nextDecision);
      if (onDecisionUpdated) {
        onDecisionUpdated(data);
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to update next-action decision."));
    } finally {
      setSavingDecision("");
    }
  }

  return (
    <section className="result-section next-action-section">
      <h3>Recommended Next Action</h3>
      {hasRecommendation ? (
        <>
          <div className="next-action-summary">
            <div>
              <span className="label">Action</span>
              <strong>{displayText(action.label, "No Recommendation")}</strong>
            </div>
            <div>
              <span className="label">Priority</span>
              <strong>{displayText(action.priority, "low")}</strong>
            </div>
            <div>
              <span className="label">Rule-based confidence</span>
              <strong>{displayConfidence(action.confidence)}</strong>
            </div>
            <div>
              <span className="label">Decision</span>
              <strong>{displayText(localDecision, "pending")}</strong>
            </div>
          </div>
          <p>{displayText(action.reason, "No reason recorded.")}</p>
          <ResultList title="Recommended Tasks" items={action.recommended_tasks} />
          <ResultList title="Recommendation Evidence" items={action.evidence} />
        </>
      ) : (
        <p className="muted">No next-action recommendation is available for this older record.</p>
      )}

      {hasRecommendation && canPersistDecision ? (
        <div className="decision-panel">
          <label>
            Decision Notes
            <textarea
              rows="3"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Optional note about your decision"
            />
          </label>
          <div className="action-row">
            {NEXT_ACTION_DECISIONS.map((item) => (
              <button
                type="button"
                key={item.value}
                onClick={() => updateDecision(item.value)}
                disabled={Boolean(savingDecision)}
              >
                {savingDecision === item.value ? "Saving..." : item.label}
              </button>
            ))}
          </div>
          {error && (
            <div className="inline-error" role="alert">
              {error}
            </div>
          )}
        </div>
      ) : (
        hasRecommendation && (
          <p className="muted">Save the analysis to history to record your decision.</p>
        )
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
      <RagSourcesSection
        sources={result.rag_sources}
        ragMode={result.rag_mode}
        usedKnowledgeBase={Boolean(result.used_knowledge_base)}
      />
      <AgentWorkflowSection
        steps={result.workflow_steps}
        workflowDurationMs={result.workflow_duration_ms}
        workflowDurationUs={result.workflow_duration_us}
      />
      <NextActionSection
        nextAction={result.next_action}
        decision={result.next_action_decision}
        applicationId={result.application_id}
        canPersistDecision={Boolean(result.saved_to_history && result.application_id)}
      />
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
  const [ragMode, setRagMode] = useState("project");
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
    formData.append("rag_mode", ragMode);
    formData.append("use_knowledge_base", ragMode !== "off" ? "true" : "false");
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
          <label>
            RAG Mode
            <select value={ragMode} onChange={(event) => setRagMode(event.target.value)}>
              <option value="project">Project Knowledge RAG</option>
              <option value="off">Off</option>
            </select>
          </label>

          <label>
            RAG Top K
            <input
              type="number"
              min="1"
              max="10"
              value={ragTopK}
              onChange={(event) => setRagTopK(event.target.value)}
              disabled={ragMode === "off"}
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
          <strong>Agent workflow is running...</strong>
          <p className="muted">The backend is executing the analysis workflow and will return an audit trail when it finishes.</p>
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

  function handleNextDecisionUpdated(data) {
    setSelectedRecord((record) => {
      if (!record) {
        return record;
      }
      return {
        ...record,
        next_action_decision: data.decision || record.next_action_decision,
        next_action_decision_notes: data.notes,
        next_action_decided_at: data.decided_at,
      };
    });
    loadApplications();
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
                  <th>Next Action</th>
                  <th>Decision</th>
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
                    <td>{displayText(record.next_action_label, "No Recommendation")}</td>
                    <td>{displayText(record.next_action_decision, "pending")}</td>
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
          <RagSourcesSection
            sources={selectedRecord.rag_sources}
            ragMode={selectedRecord.rag_mode}
            usedKnowledgeBase={asArray(selectedRecord.rag_sources).length > 0}
          />
          <AgentWorkflowSection
            steps={selectedRecord.workflow_steps}
            workflowDurationMs={selectedRecord.workflow_duration_ms}
            workflowDurationUs={selectedRecord.workflow_duration_us}
          />
          <NextActionSection
            nextAction={selectedRecord.next_action}
            decision={selectedRecord.next_action_decision}
            applicationId={selectedRecord.id}
            canPersistDecision={Boolean(selectedRecord.id && asObject(selectedRecord.next_action).action)}
            onDecisionUpdated={handleNextDecisionUpdated}
          />
          <section className="result-section">
            <h3>Human Decision</h3>
            <p>Decision: {displayText(selectedRecord.next_action_decision, "pending")}</p>
            <p>Notes: {displayText(selectedRecord.next_action_decision_notes, "No notes recorded.")}</p>
            <p>Decided at: {displayText(selectedRecord.next_action_decided_at, "Not decided")}</p>
          </section>
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

function ProjectKnowledgePage() {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildMessage, setRebuildMessage] = useState("");
  const [rebuildError, setRebuildError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTopK, setSearchTopK] = useState(5);
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  async function loadStatus() {
    if (statusLoading) {
      return;
    }

    setStatusLoading(true);
    setStatusError("");
    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/project-knowledge/status`,
        undefined,
        "Failed to load Project Knowledge status.",
      );
      setStatus(data);
    } catch (err) {
      setStatusError(getRequestErrorMessage(err, "Failed to load Project Knowledge status."));
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  function isSupportedProjectKnowledgeFile(file) {
    const name = String(file?.name || "").toLowerCase();
    return name.endsWith(".md") || name.endsWith(".txt");
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (uploading) {
      return;
    }

    setUploadMessage("");
    setUploadError("");
    if (!uploadFile) {
      setUploadError("Please choose a .md or .txt file.");
      return;
    }
    if (!isSupportedProjectKnowledgeFile(uploadFile)) {
      setUploadError("Only .md and .txt files are supported.");
      return;
    }

    const formData = new FormData();
    formData.append("file", uploadFile);

    setUploading(true);
    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/project-knowledge/upload`,
        {
          method: "POST",
          body: formData,
        },
        "Failed to upload Project Knowledge file.",
      );
      setUploadMessage(data.message || "Project Knowledge uploaded and indexed successfully.");
      setUploadFile(null);
      setUploadInputKey((value) => value + 1);
      await loadStatus();
    } catch (err) {
      setUploadError(getRequestErrorMessage(err, "Failed to upload Project Knowledge file."));
    } finally {
      setUploading(false);
    }
  }

  async function handleRebuild() {
    if (rebuilding) {
      return;
    }

    setRebuildMessage("");
    setRebuildError("");
    setRebuilding(true);
    try {
      const data = await requestJson(
        `${API_BASE_URL}/api/project-knowledge/rebuild`,
        { method: "POST" },
        "Failed to rebuild Project Knowledge index.",
      );
      setRebuildMessage(`Rebuilt ${Number.parseInt(data.chunk_count, 10) || 0} chunks.`);
      await loadStatus();
    } catch (err) {
      setRebuildError(getRequestErrorMessage(err, "Failed to rebuild Project Knowledge index."));
    } finally {
      setRebuilding(false);
    }
  }

  async function handleProjectKnowledgeSearch(event) {
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
        `${API_BASE_URL}/api/project-knowledge/search?${params.toString()}`,
        undefined,
        "Failed to search Project Knowledge.",
      );
      setSearchResults(asArray(data.items));
    } catch (err) {
      setSearchError(getRequestErrorMessage(err, "Failed to search Project Knowledge."));
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }

  return (
    <>
      <section className="panel state-panel">
        <p className="muted">
          This project intentionally uses a curated project knowledge file instead of arbitrary knowledge uploads. It
          keeps the RAG source focused, auditable, and aligned with AI job application use cases.
        </p>
      </section>

      <section className="panel detail-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Project Knowledge</span>
            <h2>Status</h2>
          </div>
          <button type="button" onClick={loadStatus} disabled={statusLoading}>
            {statusLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {statusError && (
          <div className="inline-error" role="alert">
            {statusError}
          </div>
        )}

        {status ? (
          <div className="detail-grid">
            <div>
              <span className="label">Path</span>
              <p>{displayText(status.path, "docs/PROJECT_KNOWLEDGE.md")}</p>
            </div>
            <div>
              <span className="label">File</span>
              <p>
                <span className="status-pill">{status.exists ? "Exists" : "Missing"}</span>
              </p>
            </div>
            <div>
              <span className="label">Index</span>
              <p>
                <span className="status-pill">{status.indexed ? "Indexed" : "Not indexed"}</span>
              </p>
            </div>
            <div>
              <span className="label">Document ID</span>
              <p>{status.document_id ?? "None"}</p>
            </div>
            <div>
              <span className="label">Chunks</span>
              <p>{Number.parseInt(status.chunk_count, 10) || 0}</p>
            </div>
            <div>
              <span className="label">Updated</span>
              <p>{status.updated_at ? formatDate(status.updated_at) : "Not indexed"}</p>
            </div>
          </div>
        ) : (
          <p className="muted">Status has not loaded yet.</p>
        )}
      </section>

      <form className="panel form-panel" onSubmit={handleUpload}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Upload</span>
            <h2>Replace Project Knowledge File</h2>
          </div>
          <span className="version-pill">.md / .txt</span>
        </div>

        <label>
          Project Knowledge File
          <input
            key={uploadInputKey}
            type="file"
            accept=".md,.txt,text/plain,text/markdown"
            onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
          />
        </label>

        <button type="submit" disabled={uploading}>
          {uploading ? "Uploading..." : "Upload and Rebuild Index"}
        </button>

        {uploadMessage && <div className="history-message">{uploadMessage}</div>}
        {uploadError && (
          <div className="inline-error" role="alert">
            {uploadError}
          </div>
        )}
      </form>

      <section className="panel history-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Rebuild</span>
            <h2>Project Knowledge Index</h2>
          </div>
          <button type="button" onClick={handleRebuild} disabled={rebuilding}>
            {rebuilding ? "Rebuilding..." : "Rebuild Index from docs/PROJECT_KNOWLEDGE.md"}
          </button>
        </div>
        {rebuildMessage && <div className="history-message">{rebuildMessage}</div>}
        {rebuildError && (
          <div className="inline-error" role="alert">
            {rebuildError}
          </div>
        )}
      </section>

      <form className="panel history-panel" onSubmit={handleProjectKnowledgeSearch}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Search</span>
            <h2>Search Project Knowledge</h2>
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
              placeholder="RAG FastAPI DeepSeek workflow automation"
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
          <h2>Project Knowledge Search Results</h2>
          <div className="source-grid">
            {searchResults.map((result) => (
              <article className="source-card" key={result.chunk_id}>
                <div className="source-card-header">
                  <strong>{displayText(result.document_title, "Project Knowledge")}</strong>
                  <span>{displayText(result.category, "Other")}</span>
                </div>
                <p className="muted">
                  Chunk #{Number.parseInt(result.chunk_index, 10) || 0} · Score {Number(result.score || 0).toFixed(2)}
                </p>
                <p>{displayText(String(result.content || "").slice(0, 700), "No content preview.")}</p>
              </article>
            ))}
          </div>
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
        <p>
          Resume-JD matching, Project Knowledge RAG, ATS analysis, cover letter generation, and application tracking.
        </p>
        <div className="feature-strip" aria-label="Core product features">
          <span>Project Knowledge RAG</span>
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
          Project Knowledge
        </button>
      </nav>

      {activeTab === "analyze" && <AnalyzePage />}
      {activeTab === "history" && <HistoryPage />}
      {activeTab === "knowledge" && <ProjectKnowledgePage />}

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
