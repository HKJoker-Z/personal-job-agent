import React from "react";
import { Link } from "react-router-dom";

export function FeatureRemovedPage() {
  return <section className="panel state-panel feature-state" aria-labelledby="feature-removed-title">
    <span className="eyebrow">Version 2.0.3</span>
    <h1 id="feature-removed-title">Feature removed</h1>
    <p>This workspace no longer provides Jobs, Job Rankings, Applications, Approvals, or Tasks. Historical database records were preserved for rollback and recovery.</p>
    <Link className="button-link" to="/analyze">Run a resume and job description analysis</Link>
  </section>;
}

export function NotFoundPage() {
  return <section className="panel state-panel feature-state"><span className="eyebrow">404</span><h1>Page not found</h1><p>The requested page does not exist.</p><Link className="button-link" to="/dashboard">Return to Dashboard</Link></section>;
}
