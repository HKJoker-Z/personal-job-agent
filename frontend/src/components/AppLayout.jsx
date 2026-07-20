import React, { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

const primaryItems = [
  ["Dashboard", "/dashboard"],
  ["Analyze", "/analyze"],
  ["History", "/history"],
  ["Resumes", "/resumes"],
  ["Profile", "/profile"],
  ["Project Knowledge", "/project-knowledge"],
  ["Agent Runs", "/agent-runs"],
];

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [location.pathname]);
  const items = user?.role === "admin" ? [...primaryItems, ["Monitoring", "/monitoring"]] : primaryItems;
  return <div className="authenticated-shell">
    <header className="app-header">
      <div className="nav-shell">
        <NavLink className="brand" to="/dashboard" aria-label="Personal Job Agent dashboard">
          <span className="brand-mark" aria-hidden="true">PJA</span>
          <span className="brand-copy"><strong>Personal Job Agent</strong><small>Version 2.0.1</small></span>
        </NavLink>
        <button className="menu-toggle" type="button" aria-expanded={open} aria-controls="primary-navigation" onClick={() => setOpen((value) => !value)}>
          <span aria-hidden="true">☰</span><span>Menu</span>
        </button>
        <nav id="primary-navigation" className={`primary-navigation${open ? " is-open" : ""}`} aria-label="Primary navigation">
          <div className="nav-links">{items.map(([label, path]) => <NavLink key={path} to={path}>{label}</NavLink>)}</div>
          <div className="account-actions"><NavLink to="/account">Account · {user?.display_name || "User"}</NavLink><button type="button" onClick={() => logout(false)}>Log out</button></div>
        </nav>
      </div>
    </header>
    <main className="app-shell"><Outlet /></main>
  </div>;
}
