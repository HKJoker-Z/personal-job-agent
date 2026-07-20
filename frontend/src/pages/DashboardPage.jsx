import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiJson } from "../api/client";

export function DashboardPage() {
  const [data, setData] = useState(null); const [error, setError] = useState("");
  useEffect(() => { apiJson("/api/dashboard/summary").then(setData).catch((value) => setError(value.message)); }, []);
  if (error) return <div className="error" role="alert">{error}</div>;
  if (!data) return <p>Loading Dashboard…</p>;
  const stats = [
    ["Resumes", data.resumes_total], ["Resume versions", data.resume_versions_total],
    ["Saved analyses", data.history_total], ["Historical Agent Runs", data.agent_runs_total],
  ];
  return <section><div className="section-heading"><div><span className="eyebrow">Workspace</span><h1>Dashboard</h1><p className="muted">Analyze a role directly without creating a Job or Application record.</p></div><Link className="button-link" to="/analyze">New analysis</Link></div>
    <div className="summary-grid">{stats.map(([label, value]) => <article key={label}><strong>{value || 0}</strong><span>{label}</span></article>)}</div>
    {data.agent_runs_active ? <p className="warning-banner">{data.agent_runs_active} historical Agent Run(s) remain active or waiting. Open Agent Runs to inspect or cancel them.</p> : null}
    <div className="dashboard-actions"><Link to="/resumes">Manage resumes</Link><Link to="/project-knowledge">Review Project Knowledge</Link><Link to="/history">Open analysis history</Link></div>
  </section>;
}
