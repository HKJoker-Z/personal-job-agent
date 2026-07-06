import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://101.34.61.52:8000";

function ResultList({ title, items }) {
  return (
    <section className="result-section">
      <h3>{title}</h3>
      {items?.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No items returned.</p>
      )}
    </section>
  );
}

function App() {
  const [resume, setResume] = useState(null);
  const [jobText, setJobText] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleAnalyze(event) {
    event.preventDefault();
    setError("");
    setResult(null);

    if (!resume) {
      setError("Please upload a PDF or DOCX resume.");
      return;
    }

    if (!jobText.trim() && !jobUrl.trim()) {
      setError("Please paste a job description or enter a single job URL.");
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
        throw new Error(data?.detail || "Analyze request failed.");
      }

      setResult(data);
    } catch (err) {
      setError(err.message || "Analyze request failed.");
    } finally {
      setLoading(false);
    }
  }

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
            onChange={(event) => setResume(event.target.files?.[0] || null)}
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

        {error && <div className="error">{error}</div>}

        <button type="submit" disabled={loading}>
          {loading ? "Analyzing..." : "Analyze"}
        </button>
      </form>

      {result && (
        <section className="panel results-panel">
          <div className="score-row">
            <div>
              <span className="label">Match Score</span>
              <strong>{result.match_score}/100</strong>
            </div>
          </div>

          <section className="result-section">
            <h3>岗位摘要</h3>
            <p>{result.job_summary}</p>
          </section>

          <section className="result-section">
            <h3>匹配原因</h3>
            <p>{result.match_reason}</p>
          </section>

          <ResultList title="匹配技能" items={result.matched_skills} />
          <ResultList title="缺失技能" items={result.missing_skills} />
          <ResultList title="简历优化建议" items={result.resume_suggestions} />

          <section className="result-section">
            <h3>English Cover Letter</h3>
            <pre>{result.cover_letter}</pre>
          </section>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
