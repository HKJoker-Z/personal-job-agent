import React, { Component, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://101.34.61.52:8000";

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

function getBackendErrorMessage(data) {
  if (!data?.detail) {
    return "Analyze request failed.";
  }

  if (typeof data.detail === "string") {
    return data.detail;
  }

  return "Analyze request failed. Please check the form and try again.";
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
  const [resume, setResume] = useState(null);
  const [jobText, setJobText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
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

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getBackendErrorMessage(data));
      }

      setResult(data);
    } catch (err) {
      if (err instanceof TypeError) {
        setError("Cannot connect to backend. Please check if FastAPI server is running.");
      } else {
        setError(err.message || "Analyze request failed.");
      }
    } finally {
      setLoading(false);
    }
  }

  const hasResult = Boolean(result);
  const score = clampScore(result?.match_score);

  return (
    <main className="app-shell">
      <header className="page-header">
        <h1>Personal Job Application Agent</h1>
        <p>Upload your resume, paste a JD or enter one job URL, then generate fit analysis and an English cover letter.</p>
      </header>

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

      {hasResult && (
        <section className="panel results-panel">
          <div className="score-row">
            <div>
              <span className="label">Match Score</span>
              <strong>{score}/100</strong>
            </div>
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
      )}

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
