import React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export function AppLayout() {
  const { user } = useAuth();
  return <main className="app-shell">
    <header className="page-header">
      <div className="header-title-row"><h1>Personal Job Agent</h1><span className="version-pill">2.0.0-alpha.1</span></div>
      <p>Identity, PostgreSQL, Career Profile, and Resume Versioning foundation.</p>
      <p className="muted">Signed in as {user?.display_name}</p>
    </header>
    <nav className="tabs" aria-label="Version 2 sections">
      <NavLink to="/workspace">Workspace</NavLink>
      <NavLink to="/profile">Career Profile</NavLink>
      <NavLink to="/resumes">Resume Library</NavLink>
      <NavLink to="/resumes/import">Import Resume</NavLink>
      <NavLink to="/account">Account</NavLink>
    </nav>
    <Outlet />
  </main>;
}
