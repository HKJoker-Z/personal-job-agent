import React, { useEffect, useState } from "react";
import { apiJson } from "../api/client";

export function DashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { apiJson("/api/dashboard/summary").then(setData).catch((value) => setError(value.message)); }, []);
  if (error) return <section><h2>Job Search Dashboard</h2><p role="alert">{error}</p></section>;
  if (!data) return <section><h2>Job Search Dashboard</h2><p>Loading dashboard…</p></section>;
  const cards = [
    ["Jobs", data.jobs_total], ["Active Applications", data.active_applications],
    ["Pending Tasks", data.tasks_pending], ["Overdue Tasks", data.tasks_overdue],
  ];
  return <section>
    <h2>Job Search Dashboard</h2>
    <div className="metric-grid">{cards.map(([label, value]) => <article className="metric-card" key={label}><strong>{value}</strong><span>{label}</span></article>)}</div>
    {!data.jobs_total && !data.applications_total && !data.tasks_pending ? <p className="empty-state">Import a Job to begin tracking your search.</p> : null}
    <div className="dashboard-columns">
      <article><h3>Applications by Stage</h3><ul>{Object.entries(data.applications_by_stage || {}).map(([stage, count]) => <li key={stage}>{stage.replaceAll("_", " ")}: {count}</li>)}</ul></article>
      <article><h3>Upcoming Deadlines</h3>{data.upcoming_deadlines?.length ? <ul>{data.upcoming_deadlines.map((item) => <li key={item.job_id}>{item.title || "Untitled Job"} — {new Date(item.deadline).toLocaleDateString()}</li>)}</ul> : <p>No upcoming deadlines.</p>}</article>
      <article><h3>Recent Activity</h3>{data.recent_activity?.length ? <ul>{data.recent_activity.map((item, index) => <li key={`${item.resource_id}-${index}`}>{item.event_type}</li>)}</ul> : <p>No recent activity.</p>}</article>
    </div>
  </section>;
}
