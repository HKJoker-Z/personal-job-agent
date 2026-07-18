import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export function AppLayout() {
  const { user } = useAuth();
  return <main className="app-shell">
    <header className="page-header">
      <div className="header-title-row"><h1>Personal Job Agent</h1><span className="version-pill">2.0.0-alpha.4-dev+031dfa9</span></div>
      <p>Reliable Agent Workflows, explicit Approvals, and live progress.</p>
      <p className="muted">Signed in as {user?.display_name}</p>
    </header>
    <nav className="tabs" aria-label="Version 2 sections">
      <NavLink to="/dashboard">Dashboard</NavLink>
      <NavLink to="/jobs">Jobs</NavLink>
      <NavLink to="/job-ranking">Job Ranking</NavLink>
      <NavLink to="/applications">Applications</NavLink>
      <NavLink to="/agent-runs">Agent Runs</NavLink>
      <NavLink to="/approvals">Approvals</NavLink>
      <NavLink to="/tasks">Tasks</NavLink>
      <NavLink to="/analyze">Analyze</NavLink>
      <NavLink to="/history">History</NavLink>
      <NavLink to="/profile">Career Profile</NavLink>
      <NavLink to="/resumes">Resume Library</NavLink>
      <NavLink to="/resumes/import">Import Resume</NavLink>
      <NavLink to="/project-knowledge">Project Knowledge</NavLink>
      <NavLink to="/monitoring">Monitoring</NavLink>
      <NavLink to="/evaluation">Evaluation</NavLink>
      <NavLink to="/account">Account</NavLink>
    </nav>
    <Outlet />
  </main>;
}
