import React from "react";

const analysisStages = [
  {
    number: "01",
    title: "Deterministic application logic",
    text: "The backend validates, normalizes, bounds, and scans the selected Resume and Job Description before analysis.",
  },
  {
    number: "02",
    title: "Project Knowledge RAG",
    text: "When enabled, a bounded query retrieves top-k chunks from the reviewed project corpus stored and searched in PostgreSQL.",
  },
  {
    number: "03",
    title: "DeepSeek advisory analysis",
    text: "DeepSeek proposes compact judgments and recommendations. It does not own authorization, trusted sources, persistence, or the final score.",
  },
  {
    number: "04",
    title: "Bounded recovery",
    text: "The backend parses and normalizes the response, permits one format-only repair, and uses a deterministic local fallback when needed.",
  },
  {
    number: "05",
    title: "Evidence reconciliation",
    text: "Request-scoped evidence IDs and candidate claims are validated; unsupported references are removed and safe source metadata is rebuilt.",
  },
  {
    number: "06",
    title: "Deterministic scoring",
    text: "Backend code recalculates the weighted dimensions and final match score after evidence reconciliation.",
  },
  {
    number: "07",
    title: "Human review",
    text: "The UI exposes status, warnings, evidence, scoring, and recommendations so the user—not the model—decides what to do next.",
  },
  {
    number: "08",
    title: "Persistence and monitoring",
    text: "The user may save a normalized result to History; operational monitoring retains bounded workflow metadata.",
  },
];

const runtimeComponents = [
  ["React frontend", "Static authenticated UI served by Nginx"],
  ["FastAPI backend", "Single modular application and policy boundary"],
  ["PostgreSQL 16", "Authoritative application, evidence, and durable workflow state"],
  ["DeepSeek API", "External advisory structured analysis"],
  ["Redis 7", "Dramatiq broker and production SSE connection coordination"],
  ["Worker + Outbox", "Supporting delivery, lease, recovery, heartbeat, and dead-letter processes"],
];

const synchronousPath = [
  "Browser",
  "POST /api/analyze",
  "Validation",
  "Optional Project Knowledge",
  "DeepSeek",
  "Parse / repair / fallback",
  "Evidence reconciliation",
  "Deterministic scoring",
  "Optional History",
];

const asynchronousPath = [
  "PostgreSQL Outbox",
  "Redis / Dramatiq",
  "Worker",
  "Lease / heartbeat / retry / recovery / dead letter",
];

function ExecutionPath({ items, label }) {
  return <div className="runtime-path" aria-label={label}>
    {items.map((item, index) => <React.Fragment key={item}>
      {index ? <i aria-hidden="true">→</i> : null}
      <span>{item}</span>
    </React.Fragment>)}
  </div>;
}

export function ArchitecturePage() {
  return <section className="architecture-page" aria-labelledby="architecture-title">
    <header className="architecture-hero">
      <div>
        <span className="eyebrow">Version 2.0.3 · Read-only overview</span>
        <h1 id="architecture-title">Architecture</h1>
        <p>Personal Job Agent is a modular monolith with supporting data, worker, frontend, and operational components. The current Resume-to-JD analysis path is synchronous and designed for evidence-aware human review.</p>
      </div>
      <aside className="architecture-principle" aria-label="Architecture principle">
        <strong>One product boundary</strong>
        <span>Model advice is bounded by deterministic application controls.</span>
      </aside>
    </header>

    <section className="architecture-section" aria-labelledby="analysis-flow-title">
      <div className="architecture-section-heading">
        <div>
          <span className="eyebrow">A · Current synchronous workflow</span>
          <h2 id="analysis-flow-title">How an analysis becomes reviewable evidence</h2>
        </div>
        <p>Each stage has a distinct responsibility. AI assistance does not replace grounding, scoring, or review.</p>
      </div>
      <div className="execution-lane">
        <strong>Normal Resume-to-JD request</strong>
        <ExecutionPath items={synchronousPath} label="Current synchronous Resume-to-JD analysis path" />
        <p>This request completes synchronously through FastAPI. It does not create an Agent Run or enter the Redis and Dramatiq queue.</p>
      </div>
      <ol className="architecture-flow">
        {analysisStages.map((stage) => <li key={stage.number}>
          <span className="architecture-step-number" aria-hidden="true">{stage.number}</span>
          <div><h3>{stage.title}</h3><p>{stage.text}</p></div>
        </li>)}
      </ol>
    </section>

    <section className="architecture-section architecture-runtime" aria-labelledby="runtime-title">
      <div className="architecture-section-heading">
        <div>
          <span className="eyebrow">Runtime context</span>
          <h2 id="runtime-title">Modular monolith and supporting components</h2>
        </div>
        <p>Separate processes support one application; they are not event-driven microservices.</p>
      </div>
      <div className="runtime-path" aria-label="Primary production request path">
        <span>Browser</span><i aria-hidden="true">→</i>
        <span>HTTPS edge</span><i aria-hidden="true">→</i>
        <span>Frontend</span><i aria-hidden="true">→</i>
        <span>FastAPI</span>
      </div>
      <div className="runtime-grid">
        {runtimeComponents.map(([name, role]) => <article key={name}>
          <strong>{name}</strong>
          <p>{role}</p>
        </article>)}
      </div>
    </section>

    <section className="architecture-boundaries" aria-labelledby="boundaries-title">
      <div>
        <span className="eyebrow">B · Retained asynchronous infrastructure</span>
        <h2 id="boundaries-title">What the asynchronous foundation actually does</h2>
        <ExecutionPath items={asynchronousPath} label="Retained asynchronous Agent Run infrastructure" />
        <p>PostgreSQL owns retained Agent Run, Step, Event, Outbox, lease, heartbeat, and dead-letter state. The Outbox dispatcher publishes identifier-only messages through Redis to Dramatiq workers, which claim and update work through PostgreSQL.</p>
        <p>The direct Analyze request does not use this queue. Redis, the Worker, and the Outbox dispatcher remain operational infrastructure retained for compatibility and operational workflows.</p>
        <ul className="architecture-status-list">
          <li>New Agent Run creation, retry, and resume are disabled.</li>
          <li>Historical Agent Runs remain readable, streamable, and cancellable.</li>
          <li>Jobs, Job Rankings, Applications, Approvals, and Tasks are not current user-facing product features.</li>
        </ul>
      </div>
      <div className="boundary-note">
        <strong>Human decision required</strong>
        <p>The application does not submit job applications, contact employers, guarantee ATS or interview outcomes, or make autonomous hiring decisions.</p>
      </div>
    </section>
  </section>;
}
