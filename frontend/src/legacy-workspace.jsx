import React, { Component, useEffect, useState } from "react";
import { apiFetch } from "./api/client";

const API_BASE_URL = import.meta.env.DEV ? (import.meta.env.VITE_API_BASE_URL || "") : "";
const APP_VERSION = "2.0.0-alpha.4-dev+031dfa9";
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

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "0%";
  }
  return `${Math.round(Math.max(0, number) * 100)}%`;
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

  if (typeof data.detail === "object") {
    return data.detail.message || fallback;
  }

  return fallback;
}

function getRequestErrorMessage(error, fallback) {
  if (error instanceof TypeError) {
    return "Cannot connect to backend. Please check if FastAPI server is running.";
  }

  return error.message || fallback;
}

function getRequestErrorPayload(error) {
  return error?.payload && typeof error.payload === "object" ? error.payload : null;
}

async function requestJson(url, options, fallback) {
  const response = await apiFetch(url, options);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(getBackendErrorMessage(data, fallback));
    error.payload = data?.detail;
    throw error;
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
  const response = await apiFetch(url);
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

function securityStatusLabel(status) {
  const cleanStatus = String(status || "not_available").toLowerCase();
  if (cleanStatus === "passed") {
    return "Passed";
  }
  if (cleanStatus === "passed_with_warnings") {
    return "Passed with Warnings";
  }
  if (cleanStatus === "blocked") {
    return "Blocked";
  }
  return "Not Available";
}

function securityStatusClassName(status) {
  const cleanStatus = String(status || "not_available").toLowerCase();
  return `status-pill security-${cleanStatus}`;
}

function SecurityBadge({ status }) {
  return <span className={securityStatusClassName(status)}>{securityStatusLabel(status)}</span>;
}

function SecurityAuditSection({ scan, status, policyVersion }) {
  const safeScan = asObject(scan);
  const summary = asObject(safeScan.redaction_summary);
  const findings = asArray(safeScan.findings).map((item) => asObject(item));
  const redactionTotal =
    (Number.parseInt(summary.email_count, 10) || 0) +
    (Number.parseInt(summary.phone_count, 10) || 0) +
    (Number.parseInt(summary.address_count, 10) || 0) +
    (Number.parseInt(summary.secret_count, 10) || 0) +
    (Number.parseInt(summary.private_key_count, 10) || 0);
  const safeStatus = status || "not_available";

  return (
    <section className="result-section security-section">
      <div className="section-heading-row">
        <h3>AI Security Check</h3>
        <SecurityBadge status={safeStatus} />
      </div>
      {safeScan.prompt_injection_detected && (
        <div className="history-message">
          Suspicious instructions were detected and removed before the job description was sent to the LLM.
        </div>
      )}
      {safeStatus === "blocked" && (
        <div className="inline-error" role="alert">
          Credential-like content was detected. Remove secrets before retrying.
        </div>
      )}
      <div className="security-grid">
        <div>
          <span className="label">Security Status</span>
          <p>{securityStatusLabel(safeStatus)}</p>
        </div>
        <div>
          <span className="label">Risk Level</span>
          <p>{displayText(safeScan.risk_level, "not_available")}</p>
        </div>
        <div>
          <span className="label">Prompt Injection Detected</span>
          <p>{safeScan.prompt_injection_detected ? "Yes" : "No"}</p>
        </div>
        <div>
          <span className="label">Sensitive Credential Detected</span>
          <p>{safeScan.sensitive_data_detected ? "Yes" : "No"}</p>
        </div>
        <div>
          <span className="label">PII Redactions</span>
          <p>{redactionTotal}</p>
        </div>
        <div>
          <span className="label">Policy Version</span>
          <p>{displayText(policyVersion || safeScan.policy_version, "not_available")}</p>
        </div>
      </div>
      <div className="findings-list">
        <h4>Findings</h4>
        {findings.length ? (
          findings.map((finding, index) => (
            <article className="finding-card" key={`${finding.code || "finding"}-${index}`}>
              <span>{displayText(finding.category, "security")}</span>
              <strong>{displayText(finding.severity, "info")}</strong>
              <p>{displayText(finding.message, "Security finding detected.")}</p>
              <p className="muted">Source: {displayText(finding.source, "unknown")}</p>
            </article>
          ))
        ) : (
          <p className="muted">No security findings recorded.</p>
        )}
      </div>
    </section>
  );
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
  const securityStatus = result?.security_status || "not_available";
  const blockedBySecurity = securityStatus === "blocked";

  if (blockedBySecurity) {
    return (
      <section className="panel results-panel">
        <SecurityAuditSection
          scan={result.security_scan}
          status={securityStatus}
          policyVersion={result.security_policy_version}
        />
        <AgentWorkflowSection
          steps={result.workflow_steps}
          workflowDurationMs={result.workflow_duration_ms}
          workflowDurationUs={result.workflow_duration_us}
        />
      </section>
    );
  }

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

      <SecurityAuditSection
        scan={result.security_scan}
        status={securityStatus}
        policyVersion={result.security_policy_version}
      />

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
  const [securityError, setSecurityError] = useState(null);
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
    setSecurityError(null);
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
      if (err.payload?.security_status === "blocked") {
        setSecurityError(err.payload);
      }
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

      {securityError && (
        <section className="panel results-panel">
          <SecurityAuditSection
            scan={securityError.security_scan}
            status={securityError.security_status}
            policyVersion={securityError.security_scan?.policy_version}
          />
          <AgentWorkflowSection
            steps={securityError.workflow_steps}
            workflowDurationMs={securityError.workflow_duration_ms}
            workflowDurationUs={securityError.workflow_duration_us}
          />
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
                  <th>Security</th>
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
                    <td>
                      <SecurityBadge status={record.security_status} />
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
            <div>
              <span className="label">Security</span>
              <p>
                <SecurityBadge status={selectedRecord.security_status} />
              </p>
            </div>
            <div className="wide-field">
              <span className="label">Job URL</span>
              <p>{displayText(selectedRecord.job_url)}</p>
            </div>
          </div>

          <SecurityAuditSection
            scan={selectedRecord.security_scan}
            status={selectedRecord.security_status}
            policyVersion={selectedRecord.security_policy_version}
          />

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

function MetricCard({ label, value }) {
  return (
    <div className="metric-card">
      <span className="label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MonitoringPage() {
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [traceLoadingId, setTraceLoadingId] = useState("");
  const [evaluationRun, setEvaluationRun] = useState(null);
  const [evaluationRunning, setEvaluationRunning] = useState(false);
  const [adminToken, setAdminToken] = useState("");
  const [managementPreview, setManagementPreview] = useState(null);
  const [managementBusy, setManagementBusy] = useState("");
  const [managementError, setManagementError] = useState("");
  const [managementMessage, setManagementMessage] = useState("");
  const [monitoringCleanupMode, setMonitoringCleanupMode] = useState("all");
  const [monitoringDateFrom, setMonitoringDateFrom] = useState("");
  const [monitoringDateTo, setMonitoringDateTo] = useState("");
  const [monitoringOutcomes, setMonitoringOutcomes] = useState([]);
  const [monitoringSecurityStatuses, setMonitoringSecurityStatuses] = useState([]);
  const [monitoringRiskLevels, setMonitoringRiskLevels] = useState([]);
  const [monitoringConfirmation, setMonitoringConfirmation] = useState("");
  const [evaluationCleanupMode, setEvaluationCleanupMode] = useState("all");
  const [evaluationDateFrom, setEvaluationDateFrom] = useState("");
  const [evaluationDateTo, setEvaluationDateTo] = useState("");
  const [evaluationStatuses, setEvaluationStatuses] = useState([]);
  const [evaluationConfirmation, setEvaluationConfirmation] = useState("");
  const [traceConfirmation, setTraceConfirmation] = useState("");

  async function loadMonitoring() {
    if (loading) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const params = `days=${days}`;
      const [
        status,
        overview,
        workflowSteps,
        rag,
        security,
        recommendations,
        traces,
        evaluationStatus,
        evaluationRuns,
        dataManagementStatus,
      ] = await Promise.all([
        requestJson(`${API_BASE_URL}/api/monitoring/status`, undefined, "Failed to load monitoring status."),
        requestJson(`${API_BASE_URL}/api/monitoring/overview?${params}`, undefined, "Failed to load monitoring overview."),
        requestJson(`${API_BASE_URL}/api/monitoring/workflow-steps?${params}`, undefined, "Failed to load workflow metrics."),
        requestJson(`${API_BASE_URL}/api/monitoring/rag?${params}`, undefined, "Failed to load RAG metrics."),
        requestJson(`${API_BASE_URL}/api/monitoring/security?${params}`, undefined, "Failed to load security metrics."),
        requestJson(`${API_BASE_URL}/api/monitoring/recommendations?${params}`, undefined, "Failed to load recommendation metrics."),
        requestJson(`${API_BASE_URL}/api/monitoring/traces?${params}&limit=20`, undefined, "Failed to load traces."),
        requestJson(`${API_BASE_URL}/api/evaluations/status`, undefined, "Failed to load evaluation status."),
        requestJson(`${API_BASE_URL}/api/evaluations/runs?limit=1&offset=0`, undefined, "Failed to load evaluation runs."),
        requestJson(`${API_BASE_URL}/api/monitoring/data-management/status`, undefined, "Failed to load data management status."),
      ]);
      setData({
        status,
        overview,
        workflowSteps,
        rag,
        security,
        recommendations,
        traces,
        evaluationStatus,
        evaluationRuns,
        dataManagementStatus,
      });
      const latestRun = asArray(evaluationRuns.items)[0] || null;
      if (latestRun && !evaluationRun) {
        setEvaluationRun(latestRun);
      }
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to load monitoring data."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMonitoring();
  }, []);

  async function loadTrace(workflowId) {
    if (!workflowId || traceLoadingId) {
      return;
    }
    setTraceLoadingId(workflowId);
    setError("");
    try {
      const trace = await requestJson(
        `${API_BASE_URL}/api/monitoring/traces/${workflowId}`,
        undefined,
        "Failed to load trace.",
      );
      setSelectedTrace(trace);
    } catch (err) {
      setError(getRequestErrorMessage(err, "Failed to load trace."));
    } finally {
      setTraceLoadingId("");
    }
  }

  async function runEvaluation() {
    if (evaluationRunning) {
      return;
    }
    setEvaluationRunning(true);
    setError("");
    try {
      const run = await requestJson(
        `${API_BASE_URL}/api/evaluations/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ suite_name: "default", mode: "offline" }),
        },
        "Failed to run offline evaluation.",
      );
      setEvaluationRun(run);
      await loadMonitoring();
    } catch (err) {
      const payload = getRequestErrorPayload(err);
      const workflowNote = payload?.workflow_id ? ` Workflow ID: ${payload.workflow_id}` : "";
      setError(`${getRequestErrorMessage(err, "Failed to run offline evaluation.")}${workflowNote}`);
    } finally {
      setEvaluationRunning(false);
    }
  }

  function toggleSelection(setter, value) {
    setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]));
  }

  function dataManagementHeaders() {
    return {
      "Content-Type": "application/json",
      "X-Monitoring-Admin-Token": adminToken,
    };
  }

  function managementErrorMessage(err, fallback) {
    const payload = getRequestErrorPayload(err);
    const errorCode = displayText(payload?.error_code, "");
    return errorCode ? `${getRequestErrorMessage(err, fallback)} (${errorCode})` : getRequestErrorMessage(err, fallback);
  }

  function monitoringPayload(includeConfirmation = false) {
    const payload = {
      mode: monitoringCleanupMode,
      date_from: monitoringCleanupMode === "filtered" ? monitoringDateFrom || null : null,
      date_to: monitoringCleanupMode === "filtered" ? monitoringDateTo || null : null,
      outcomes: monitoringCleanupMode === "filtered" ? monitoringOutcomes : [],
      security_statuses: monitoringCleanupMode === "filtered" ? monitoringSecurityStatuses : [],
      risk_levels: monitoringCleanupMode === "filtered" ? monitoringRiskLevels : [],
    };
    return includeConfirmation ? { ...payload, confirmation: monitoringConfirmation } : payload;
  }

  function evaluationPayload(includeConfirmation = false) {
    const payload = {
      mode: evaluationCleanupMode,
      date_from: evaluationCleanupMode === "filtered" ? evaluationDateFrom || null : null,
      date_to: evaluationCleanupMode === "filtered" ? evaluationDateTo || null : null,
      statuses: evaluationCleanupMode === "filtered" ? evaluationStatuses : [],
    };
    return includeConfirmation ? { ...payload, confirmation: evaluationConfirmation } : payload;
  }

  async function previewManagement(kind, url, payload) {
    if (!adminToken || managementBusy) {
      return;
    }
    setManagementBusy(`${kind}-preview`);
    setManagementError("");
    setManagementMessage("");
    try {
      const preview = await requestJson(
        `${API_BASE_URL}${url}`,
        { method: "POST", headers: dataManagementHeaders(), body: JSON.stringify(payload) },
        "Failed to preview cleanup.",
      );
      setManagementPreview({ kind, data: preview });
    } catch (err) {
      setManagementPreview(null);
      setManagementError(managementErrorMessage(err, "Failed to preview cleanup."));
    } finally {
      setManagementBusy("");
    }
  }

  async function deleteManagedData(kind, url, payload, setConfirmation, successMessage) {
    if (!adminToken || managementBusy) {
      return;
    }
    if (!window.confirm("This permanent cleanup cannot be undone. Continue?")) {
      return;
    }
    setManagementBusy(`${kind}-delete`);
    setManagementError("");
    setManagementMessage("");
    try {
      const result = await requestJson(
        `${API_BASE_URL}${url}`,
        { method: "DELETE", headers: dataManagementHeaders(), body: JSON.stringify(payload) },
        "Failed to delete data.",
      );
      setManagementMessage(successMessage(result));
      setSelectedTrace(null);
      if (kind.startsWith("evaluation")) {
        setEvaluationRun(null);
      }
      await loadMonitoring();
    } catch (err) {
      setManagementError(managementErrorMessage(err, "Failed to delete data."));
    } finally {
      setAdminToken("");
      setConfirmation("");
      setMonitoringConfirmation("");
      setEvaluationConfirmation("");
      setTraceConfirmation("");
      setManagementPreview(null);
      setManagementBusy("");
    }
  }

  async function deleteSelectedTrace() {
    if (!selectedTrace?.workflow_id || !adminToken || managementBusy || traceConfirmation !== "DELETE TRACE") {
      return;
    }
    if (!window.confirm("Delete this trace metadata permanently? Application history will be preserved.")) {
      return;
    }
    setManagementBusy("trace-delete");
    setManagementError("");
    setManagementMessage("");
    try {
      const result = await requestJson(
        `${API_BASE_URL}/api/monitoring/traces/${encodeURIComponent(selectedTrace.workflow_id)}`,
        {
          method: "DELETE",
          headers: dataManagementHeaders(),
          body: JSON.stringify({ confirmation: traceConfirmation, notes: null }),
        },
        "Failed to delete trace metadata.",
      );
      setManagementMessage(`Deleted trace metadata: ${result.analysis_metrics_deleted || 0} analysis and ${result.analysis_step_metrics_deleted || 0} step metrics.`);
      setSelectedTrace(null);
      await loadMonitoring();
    } catch (err) {
      setManagementError(managementErrorMessage(err, "Failed to delete trace metadata."));
    } finally {
      setAdminToken("");
      setTraceConfirmation("");
      setMonitoringConfirmation("");
      setEvaluationConfirmation("");
      setManagementBusy("");
    }
  }

  useEffect(() => {
    setManagementPreview(null);
  }, [
    monitoringCleanupMode,
    monitoringDateFrom,
    monitoringDateTo,
    monitoringOutcomes,
    monitoringSecurityStatuses,
    monitoringRiskLevels,
    evaluationCleanupMode,
    evaluationDateFrom,
    evaluationDateTo,
    evaluationStatuses,
  ]);

  const overview = asObject(data?.overview);
  const workflowItems = asArray(data?.workflowSteps?.items);
  const rag = asObject(data?.rag);
  const security = asObject(data?.security);
  const recommendations = asObject(data?.recommendations);
  const actionDistribution = asObject(recommendations.action_distribution);
  const decisionDistribution = asObject(recommendations.decision_distribution);
  const traces = asArray(data?.traces?.items);
  const findingCodes = asObject(security.finding_codes);
  const latestRun = evaluationRun || asArray(data?.evaluationRuns?.items)[0] || null;
  const latestResults = asArray(latestRun?.results);
  const dataManagementStatus = asObject(data?.dataManagementStatus);
  const destructiveOperationsAllowed = Boolean(dataManagementStatus.data_management_enabled)
    && (Boolean(dataManagementStatus.request_is_local) || Boolean(dataManagementStatus.remote_admin_allowed));
  const monitoringPreviewKind = monitoringCleanupMode === "all" ? "monitoring-all" : "monitoring-filtered";
  const evaluationPreviewKind = evaluationCleanupMode === "all" ? "evaluation-all" : "evaluation-filtered";
  const monitoringPreview = managementPreview?.kind === monitoringPreviewKind ? asObject(managementPreview.data) : null;
  const evaluationPreview = managementPreview?.kind === evaluationPreviewKind ? asObject(managementPreview.data) : null;
  const monitoringConfirmationText = monitoringCleanupMode === "all"
    ? "DELETE ALL MONITORING DATA"
    : "DELETE FILTERED MONITORING DATA";
  const evaluationConfirmationText = evaluationCleanupMode === "all"
    ? "DELETE EVALUATION HISTORY"
    : "DELETE FILTERED EVALUATION HISTORY";

  return (
    <>
      <section className="panel history-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Monitoring</span>
            <h2>AI Monitoring and Behavioral Evaluation</h2>
          </div>
          <span className="version-pill">v{APP_VERSION}</span>
        </div>
        <div className="history-toolbar monitoring-toolbar">
          <label>
            Date Range
            <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
            </select>
          </label>
          <button type="button" onClick={loadMonitoring} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <p className="muted">
          Trace metadata does not include resumes, job descriptions, prompts, model responses, or detected secrets.
        </p>
      </section>

      {error && (
        <section className="panel state-panel error-panel" role="alert">
          <strong>Monitoring request failed</strong>
          <p>{error}</p>
        </section>
      )}

      {!data && !loading && !error && (
        <section className="panel state-panel">
          <p className="muted">Monitoring data has not loaded yet.</p>
        </section>
      )}

      {data && (
        <>
          <section className="panel results-panel data-management-panel">
            <div className="section-heading-row">
              <div>
                <span className="eyebrow">Danger zone</span>
                <h3>Data Management</h3>
              </div>
              <span className="status-pill security-blocked">Permanent cleanup</span>
            </div>
            <p className="muted">
              Monitoring cleanup deletes monitoring and trace metadata only. It does not delete application history or Project Knowledge.
            </p>
            <div className="metrics-grid">
              <MetricCard label="Admin Token" value={dataManagementStatus.admin_token_configured ? "Configured" : "Not configured"} />
              <MetricCard label="Remote Administration" value={dataManagementStatus.remote_admin_allowed ? "Allowed" : "Disabled"} />
              <MetricCard label="Current Request" value={dataManagementStatus.request_is_local ? "Local" : "Remote"} />
              <MetricCard label="Test Database Isolation" value={dataManagementStatus.test_database_isolation ? "Enabled" : "Unavailable"} />
            </div>
            {!dataManagementStatus.data_management_enabled && (
              <div className="inline-error" role="alert">
                Data management is disabled until MONITORING_ADMIN_TOKEN is configured on the backend.
              </div>
            )}
            {!dataManagementStatus.remote_admin_allowed && !dataManagementStatus.request_is_local && (
              <div className="inline-error" role="alert">
                Remote destructive operations are disabled. Use the API locally through SSH, or explicitly enable remote administration behind HTTPS.
              </div>
            )}
            <label className="admin-token-field">
              Administrator Token
              <input
                type="password"
                value={adminToken}
                onChange={(event) => setAdminToken(event.target.value)}
                autoComplete="off"
                placeholder="Enter token for preview or deletion"
              />
            </label>
            <p className="muted">The token is held in this page's memory only and is cleared after every deletion attempt.</p>
            {managementError && <div className="inline-error" role="alert">{managementError}</div>}
            {managementMessage && <div className="history-message">{managementMessage}</div>}

            <div className="cleanup-grid">
              <article className="cleanup-card">
                <h4>Monitoring Cleanup</h4>
                <p>Delete analysis and step metadata. Application history, Project Knowledge, and evaluation history are preserved.</p>
                <label>
                  Cleanup Scope
                  <select value={monitoringCleanupMode} onChange={(event) => setMonitoringCleanupMode(event.target.value)}>
                    <option value="all">Clear all monitoring data</option>
                    <option value="filtered">Delete filtered monitoring data</option>
                  </select>
                </label>
                {monitoringCleanupMode === "filtered" && (
                  <div className="cleanup-filters">
                    <label>Date From<input type="date" value={monitoringDateFrom} onChange={(event) => setMonitoringDateFrom(event.target.value)} /></label>
                    <label>Date To<input type="date" value={monitoringDateTo} onChange={(event) => setMonitoringDateTo(event.target.value)} /></label>
                    <fieldset>
                      <legend>Outcome</legend>
                      {["completed", "completed_with_warnings", "failed", "blocked"].map((value) => (
                        <label className="checkbox-label" key={value}>
                          <input type="checkbox" checked={monitoringOutcomes.includes(value)} onChange={() => toggleSelection(setMonitoringOutcomes, value)} />{value}
                        </label>
                      ))}
                    </fieldset>
                    <fieldset>
                      <legend>Security Status</legend>
                      {["passed", "passed_with_warnings", "blocked", "not_available"].map((value) => (
                        <label className="checkbox-label" key={value}>
                          <input type="checkbox" checked={monitoringSecurityStatuses.includes(value)} onChange={() => toggleSelection(setMonitoringSecurityStatuses, value)} />{value}
                        </label>
                      ))}
                    </fieldset>
                    <fieldset>
                      <legend>Risk Level</legend>
                      {["low", "medium", "high", "critical"].map((value) => (
                        <label className="checkbox-label" key={value}>
                          <input type="checkbox" checked={monitoringRiskLevels.includes(value)} onChange={() => toggleSelection(setMonitoringRiskLevels, value)} />{value}
                        </label>
                      ))}
                    </fieldset>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => previewManagement(monitoringPreviewKind, "/api/monitoring/data/preview", monitoringPayload())}
                  disabled={!destructiveOperationsAllowed || !adminToken || Boolean(managementBusy)}
                >
                  {managementBusy === `${monitoringPreviewKind}-preview` ? "Previewing..." : "Preview Monitoring Cleanup"}
                </button>
                {monitoringPreview && (
                  <div className="cleanup-preview">
                    <strong>Preview</strong>
                    <span>Analyses: {monitoringPreview.analysis_metrics_count ?? 0}</span>
                    <span>Step metrics: {monitoringPreview.analysis_step_metrics_count ?? 0}</span>
                    <span>Affected workflows: {monitoringPreview.affected_workflow_count ?? 0}</span>
                  </div>
                )}
                <label>
                  Type {monitoringConfirmationText} to confirm
                  <input value={monitoringConfirmation} onChange={(event) => setMonitoringConfirmation(event.target.value)} />
                </label>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => deleteManagedData(
                    monitoringPreviewKind,
                    "/api/monitoring/data",
                    monitoringPayload(true),
                    setMonitoringConfirmation,
                    (result) => `Deleted ${result.analysis_metrics_deleted || 0} analyses and ${result.analysis_step_metrics_deleted || 0} step metrics.`,
                  )}
                  disabled={!destructiveOperationsAllowed || !adminToken || Boolean(managementBusy) || !monitoringPreview || !(monitoringPreview.analysis_metrics_count > 0) || monitoringConfirmation !== monitoringConfirmationText}
                >
                  {managementBusy === `${monitoringPreviewKind}-delete` ? "Deleting..." : "Delete Monitoring Data"}
                </button>
              </article>

              <article className="cleanup-card">
                <h4>Evaluation History Cleanup</h4>
                <p>Delete evaluation runs and results. Offline cases remain available and can be run again.</p>
                <label>
                  Cleanup Scope
                  <select value={evaluationCleanupMode} onChange={(event) => setEvaluationCleanupMode(event.target.value)}>
                    <option value="all">Clear all evaluation history</option>
                    <option value="filtered">Delete filtered evaluation history</option>
                  </select>
                </label>
                {evaluationCleanupMode === "filtered" && (
                  <div className="cleanup-filters">
                    <label>Date From<input type="date" value={evaluationDateFrom} onChange={(event) => setEvaluationDateFrom(event.target.value)} /></label>
                    <label>Date To<input type="date" value={evaluationDateTo} onChange={(event) => setEvaluationDateTo(event.target.value)} /></label>
                    <fieldset>
                      <legend>Run Status</legend>
                      {["running", "completed", "completed_with_failures", "failed"].map((value) => (
                        <label className="checkbox-label" key={value}>
                          <input type="checkbox" checked={evaluationStatuses.includes(value)} onChange={() => toggleSelection(setEvaluationStatuses, value)} />{value}
                        </label>
                      ))}
                    </fieldset>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => previewManagement(evaluationPreviewKind, "/api/evaluations/data/preview", evaluationPayload())}
                  disabled={!destructiveOperationsAllowed || !adminToken || Boolean(managementBusy)}
                >
                  {managementBusy === `${evaluationPreviewKind}-preview` ? "Previewing..." : "Preview Evaluation Cleanup"}
                </button>
                {evaluationPreview && (
                  <div className="cleanup-preview">
                    <strong>Preview</strong>
                    <span>Evaluation runs: {evaluationPreview.evaluation_runs_count ?? 0}</span>
                    <span>Evaluation results: {evaluationPreview.evaluation_results_count ?? 0}</span>
                    <span>Evaluation cases are preserved.</span>
                  </div>
                )}
                <label>
                  Type {evaluationConfirmationText} to confirm
                  <input value={evaluationConfirmation} onChange={(event) => setEvaluationConfirmation(event.target.value)} />
                </label>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => deleteManagedData(
                    evaluationPreviewKind,
                    "/api/evaluations/data",
                    evaluationPayload(true),
                    setEvaluationConfirmation,
                    (result) => `Deleted ${result.evaluation_runs_deleted || 0} evaluation runs and ${result.evaluation_results_deleted || 0} results.`,
                  )}
                  disabled={!destructiveOperationsAllowed || !adminToken || Boolean(managementBusy) || !evaluationPreview || !(evaluationPreview.evaluation_runs_count > 0) || evaluationConfirmation !== evaluationConfirmationText}
                >
                  {managementBusy === `${evaluationPreviewKind}-delete` ? "Deleting..." : "Delete Evaluation History"}
                </button>
              </article>
            </div>
          </section>

          <section className="panel results-panel">
            <div className="section-heading-row">
              <h3>Overview</h3>
              <span className="muted">{displayText(data.status?.privacy_mode, "metadata_only")}</span>
            </div>
            <div className="metrics-grid">
              <MetricCard label="Total Analyses" value={overview.total_analyses ?? 0} />
              <MetricCard label="Completion Rate" value={formatPercent(overview.completion_rate)} />
              <MetricCard label="Clean Success Rate" value={formatPercent(overview.clean_success_rate)} />
              <MetricCard label="Blocked" value={overview.blocked ?? 0} />
              <MetricCard label="Average Workflow Duration" value={formatDuration(overview.average_workflow_duration_ms)} />
              <MetricCard label="Average LLM Duration" value={formatDuration(overview.average_llm_duration_ms)} />
              <MetricCard label="RAG Hit Rate" value={formatPercent(overview.rag_hit_rate)} />
              <MetricCard label="Security Warning Rate" value={formatPercent(overview.security_warning_rate)} />
              <MetricCard label="JSON Parse Failures" value={overview.json_parse_failure_count ?? 0} />
            </div>
          </section>

          <section className="panel list-panel">
            <h3>Workflow Performance</h3>
            {workflowItems.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Completed</th>
                      <th>Failed</th>
                      <th>Skipped</th>
                      <th>Average</th>
                      <th>P50</th>
                      <th>P95</th>
                      <th>Maximum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workflowItems.map((item) => (
                      <tr key={item.step_key}>
                        <td>{displayText(item.step_key)}</td>
                        <td>{item.completed_count}</td>
                        <td>{item.failed_count}</td>
                        <td>{item.skipped_count}</td>
                        <td>{formatDuration(item.average_ms)}</td>
                        <td>{formatDuration(item.p50_ms)}</td>
                        <td>{formatDuration(item.p95_ms)}</td>
                        <td>{formatDuration(item.maximum_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">No workflow step metrics found for this period.</p>
            )}
          </section>

          <section className="panel results-panel">
            <h3>RAG Monitoring</h3>
            <div className="metrics-grid">
              <MetricCard label="RAG Enabled Runs" value={rag.rag_enabled_runs ?? 0} />
              <MetricCard label="RAG Hit Runs" value={rag.rag_hit_runs ?? 0} />
              <MetricCard label="RAG No-Hit Runs" value={rag.rag_no_hit_runs ?? 0} />
              <MetricCard label="Hit Rate" value={formatPercent(rag.rag_hit_rate)} />
              <MetricCard label="Average Sources" value={Number(rag.average_source_count || 0).toFixed(2)} />
              <MetricCard label="Average Retrieval Duration" value={formatDuration(rag.average_retrieval_duration_ms)} />
              <MetricCard label="Reconciliation Runs" value={rag.reconciliation_runs ?? 0} />
              <MetricCard label="Skills Reconciled" value={rag.reconciliation_total ?? 0} />
            </div>
          </section>

          <section className="panel results-panel">
            <h3>Security Monitoring</h3>
            <div className="metrics-grid">
              <MetricCard label="Passed" value={security.passed ?? 0} />
              <MetricCard label="Passed with Warnings" value={security.passed_with_warnings ?? 0} />
              <MetricCard label="Blocked" value={security.blocked ?? 0} />
              <MetricCard label="Prompt Injection Detections" value={security.prompt_injection_detection_count ?? 0} />
              <MetricCard label="Sensitive Credential Detections" value={security.sensitive_data_detection_count ?? 0} />
              <MetricCard label="Output Leakage Detections" value={security.output_leakage_detection_count ?? 0} />
              <MetricCard label="Email Redactions" value={security.total_email_redactions ?? 0} />
              <MetricCard label="Phone Redactions" value={security.total_phone_redactions ?? 0} />
              <MetricCard label="Address Redactions" value={security.total_address_redactions ?? 0} />
            </div>
            <div className="findings-list">
              <h4>Finding Code Distribution</h4>
              {Object.keys(findingCodes).length ? (
                Object.entries(findingCodes).map(([code, count]) => (
                  <article className="finding-card" key={code}>
                    <span>{code}</span>
                    <strong>{count}</strong>
                  </article>
                ))
              ) : (
                <p className="muted">No security finding codes recorded.</p>
              )}
            </div>
          </section>

          <section className="panel results-panel">
            <h3>Recommendation Monitoring</h3>
            <div className="metrics-grid">
              <MetricCard label="Apply Now" value={actionDistribution.apply_now ?? 0} />
              <MetricCard label="Improve Resume First" value={actionDistribution.improve_resume_first ?? 0} />
              <MetricCard label="Upskill First" value={actionDistribution.upskill_first ?? 0} />
              <MetricCard label="Save for Later" value={actionDistribution.save_for_later ?? 0} />
              <MetricCard label="Skip" value={actionDistribution.skip ?? 0} />
              <MetricCard label="Pending" value={decisionDistribution.pending ?? 0} />
              <MetricCard label="Accepted" value={decisionDistribution.accepted ?? 0} />
              <MetricCard label="Dismissed" value={decisionDistribution.dismissed ?? 0} />
              <MetricCard label="Completed" value={decisionDistribution.completed ?? 0} />
              <MetricCard label="Acceptance Rate" value={formatPercent(recommendations.recommendation_acceptance_rate)} />
            </div>
          </section>

          <section className="panel list-panel">
            <h3>Trace Explorer</h3>
            {traces.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Workflow ID</th>
                      <th>Time</th>
                      <th>Outcome</th>
                      <th>Duration</th>
                      <th>LLM Duration</th>
                      <th>RAG Sources</th>
                      <th>Security</th>
                      <th>Risk</th>
                      <th>Next Action</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {traces.map((trace) => (
                      <tr key={trace.workflow_id}>
                        <td>
                          <button type="button" className="link-button" onClick={() => loadTrace(trace.workflow_id)}>
                            {traceLoadingId === trace.workflow_id ? "Loading..." : trace.workflow_id.slice(0, 8)}
                          </button>
                        </td>
                        <td>{formatDate(trace.created_at)}</td>
                        <td>{displayText(trace.outcome)}</td>
                        <td>{formatDuration(trace.workflow_duration_ms)}</td>
                        <td>{formatDuration(trace.llm_duration_ms)}</td>
                        <td>{trace.rag_source_count ?? 0}</td>
                        <td>{displayText(trace.security_status)}</td>
                        <td>{displayText(trace.security_risk_level)}</td>
                        <td>{displayText(trace.next_action, "None")}</td>
                        <td>{displayText(trace.error_code, "None")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">No monitoring traces are available.</p>
            )}
          </section>

          {selectedTrace && (
            <section className="panel detail-panel">
              <h3>Trace Detail</h3>
              <div className="detail-grid">
                <div>
                  <span className="label">Workflow ID</span>
                  <p>{selectedTrace.workflow_id}</p>
                </div>
                <div>
                  <span className="label">Outcome</span>
                  <p>{displayText(selectedTrace.outcome)}</p>
                </div>
                <div>
                  <span className="label">Duration</span>
                  <p>{formatDuration(selectedTrace.workflow_duration_ms)}</p>
                </div>
                <div>
                  <span className="label">LLM Duration</span>
                  <p>{formatDuration(selectedTrace.llm_duration_ms)}</p>
                </div>
              </div>
              <AgentWorkflowSection steps={selectedTrace.steps} workflowDurationMs={selectedTrace.workflow_duration_ms} />
              <div className="metrics-grid">
                <MetricCard label="RAG Mode" value={displayText(selectedTrace.rag?.mode, "None")} />
                <MetricCard label="RAG Sources" value={selectedTrace.rag?.source_count ?? 0} />
                <MetricCard label="RAG Hit" value={selectedTrace.rag?.hit ? "Yes" : "No"} />
                <MetricCard label="Reconciliations" value={selectedTrace.rag?.reconciliation_count ?? 0} />
                <MetricCard label="Security Status" value={displayText(selectedTrace.security?.status, "not_available")} />
                <MetricCard label="Security Risk" value={displayText(selectedTrace.security?.risk_level, "not_available")} />
                <MetricCard label="Error Stage" value={displayText(selectedTrace.error_stage, "None")} />
                <MetricCard label="Error Code" value={displayText(selectedTrace.error_code, "None")} />
              </div>
              <div className="trace-delete-panel">
                <h4>Delete Trace Metadata</h4>
                <p className="muted">Workflow ID: {selectedTrace.workflow_id}. Application history remains preserved.</p>
                <label>
                  Type DELETE TRACE to confirm
                  <input value={traceConfirmation} onChange={(event) => setTraceConfirmation(event.target.value)} />
                </label>
                <button
                  type="button"
                  className="danger-button"
                  onClick={deleteSelectedTrace}
                  disabled={!destructiveOperationsAllowed || !adminToken || Boolean(managementBusy) || traceConfirmation !== "DELETE TRACE"}
                >
                  {managementBusy === "trace-delete" ? "Deleting..." : "Delete Trace Metadata"}
                </button>
              </div>
            </section>
          )}

          <section className="panel results-panel">
            <div className="section-heading-row">
              <h3>Behavioral Evaluation Suite</h3>
              <button type="button" onClick={runEvaluation} disabled={evaluationRunning}>
                {evaluationRunning ? "Running..." : "Run Offline Evaluation"}
              </button>
            </div>
            <p className="muted">
              Evaluation pass rate measures deterministic behavioral and rule compliance checks. It is not model accuracy or hiring success probability.
            </p>
            <div className="metrics-grid">
              <MetricCard label="Evaluation Mode" value={displayText(data.evaluationStatus?.mode, "offline")} />
              <MetricCard label="Suite Version" value={displayText(data.evaluationStatus?.suite_version, "1.8.0")} />
              <MetricCard label="Total Cases" value={latestRun?.total_cases ?? 0} />
              <MetricCard label="Passed" value={latestRun?.passed_cases ?? 0} />
              <MetricCard label="Failed" value={latestRun?.failed_cases ?? 0} />
              <MetricCard label="Errors" value={latestRun?.error_cases ?? 0} />
              <MetricCard label="Pass Rate" value={formatPercent(latestRun?.pass_rate)} />
              <MetricCard label="Duration" value={formatDuration(latestRun?.duration_ms)} />
            </div>
            {latestResults.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Category</th>
                      <th>Status</th>
                      <th>Duration</th>
                      <th>Checks</th>
                      <th>Failure Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latestResults.map((item) => (
                      <tr key={item.case_id}>
                        <td>{displayText(item.case_name)}</td>
                        <td>{displayText(item.category)}</td>
                        <td>{displayText(item.status)}</td>
                        <td>{formatDuration(item.duration_ms)}</td>
                        <td>{Object.entries(asObject(item.checks)).filter(([, passed]) => passed).length}/{Object.keys(asObject(item.checks)).length}</td>
                        <td>{displayText(item.failure_summary, "None")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="muted">No evaluation runs are available. Run the offline evaluation suite to create a new result.</p>
            )}
          </section>
        </>
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
              <p>{displayText(status.path, "PROJECT_KNOWLEDGE.md")}</p>
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
            {rebuilding ? "Rebuilding..." : "Rebuild Project Knowledge Index"}
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

export function LegacyWorkspace({ initialTab = "analyze" }) {
  const [activeTab, setActiveTab] = useState(initialTab);

  useEffect(() => { setActiveTab(initialTab); }, [initialTab]);

  return (
    <main className="app-shell">
      <header className="page-header">
        <div className="header-title-row">
          <h1>Personal Job Application Agent</h1>
          <span className="version-pill">v{APP_VERSION}</span>
        </div>
        <p>
          Resume-JD matching, Project Knowledge RAG, AI security checks, monitoring, behavioral evaluation, ATS analysis, cover letter generation, and application tracking.
        </p>
        <p className="security-notice">
          This tool uses heuristic security controls and cannot guarantee complete protection against every prompt injection attack. Users should review generated content before use.
        </p>
        <div className="feature-strip" aria-label="Core product features">
          <span>Project Knowledge RAG</span>
          <span>AI Security</span>
          <span>Monitoring</span>
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
        <button
          type="button"
          className={activeTab === "monitoring" ? "active-tab" : ""}
          onClick={() => setActiveTab("monitoring")}
        >
          Monitoring
        </button>
      </nav>

      {activeTab === "analyze" && <AnalyzePage />}
      {activeTab === "history" && <HistoryPage />}
      {activeTab === "knowledge" && <ProjectKnowledgePage />}
      {activeTab === "monitoring" && <MonitoringPage />}

      <footer className="app-footer">API: {API_BASE_URL || "same origin"}</footer>
    </main>
  );
}

export { ErrorBoundary };
