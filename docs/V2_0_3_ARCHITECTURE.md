# Version 2.0.3 Architecture

Version 2.0.3 is the `2.0.0-alpha.3` development milestone. It builds on the published `v2.0.0-alpha.2` schema and remains undeployed. The synchronous flow is deliberately user-controlled:

```text
confirmed Profile + immutable Resume Version + confirmed Job Requirements
  -> deterministic Match snapshot
  -> reproducible Rank Run
  -> Application Package snapshot
  -> grounded Material Draft
  -> independent claim validation
  -> user review / edit / explicit claim confirmation
  -> immutable finalized Material Version
```

The matching engine is pure deterministic Python. It owns all numeric scores and hard-filter results. An optional DeepSeek adapter may select, order, and rephrase a locally constructed grounded Draft, but it cannot change scores or introduce evidence. Tests and isolated Smoke use the deterministic provider; model-path tests inject a Mock invoker.

Routers validate requests and translate safe errors. Ownership-scoped repositories perform database access. Services own transactions, revision checks, snapshots, audits, and business gates. Existing Authentication, CSRF, Storage, Prompt Injection scanning, output scanning, Monitoring, and PostgreSQL backup/restore are reused.

All resource queries are scoped to `owner_user_id` or validated through an owned parent. Match Analyses and their dimensions/evidence are immutable. Material edits create a new Version. Full Profile, Resume, Job Description, questions, generated content, and review notes are excluded from ordinary logs.

There is no Worker, queue, Scheduler, WebSocket/SSE, automated application, email sender, production migration, or deployment in this milestone.
