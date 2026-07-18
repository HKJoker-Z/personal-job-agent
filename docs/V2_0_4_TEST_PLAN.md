# Version 2.0.4 Verification Plan

## Automated backend and schema

- Preserve the complete Version 1.9–2.0.3 regression suite.
- Cover Run creation, Idempotency-Key and force-new behavior, owner isolation, revision conflicts, all legal/illegal transitions, duplicate Worker delivery, expired lease recovery, Redis/outbox recovery, bounded backoff, Dead Letter, cancellation, explicit retry/resume, Approval replay/stale/expiry, budgets, concurrency, usage idempotency, heartbeat/readiness, SSE auth/ownership/reconnect/privacy, Prompt Injection, unsupported claims, Origin, and CSRF.
- Execute the full 20-Step Package workflow using a deterministic Mock invoker; assert exactly three generated material types, no duplicate versions, and no duplicate usage entries after redelivery.
- Verify fresh Alembic upgrade, Alpha 3 (`20260713_03`) to head, downgrade to Alpha 3, re-upgrade, `heads`, `current`, and `check` on SQLite and PostgreSQL 16.

## Frontend

- Test Agent Runs list, Worker outage, detail/progress, SSE events and reconnect, Timeline de-duplication, cancellation, retry cost warning, waiting Approval, decisions, `401`/`403`/`409`, duplicate-click prevention, existing-Run reuse, and Application Package async navigation.
- Run `npm run test` and the production Vite build.

## Docker and production support

- Validate development, test-overlay, and production Compose; build both images; check image metadata and non-root runtime.
- Run Bash syntax, ShellCheck, repository generated-file checks, and credential-pattern scanning.
- Verify pre-migration backup, migration lock, PostgreSQL/Redis/Worker readiness, graceful restart, resource/security settings, backup manifest/checksums, empty-target restore, database row counts, and private file checksums.

## Isolated Mock LLM Smoke

Use only a unique `pja-v2-final-<timestamp>` Compose project and `127.0.0.1:18088`; never use or modify 8080. The Smoke creates synthetic data and covers PostgreSQL, Redis, Alembic, admin/login/CSRF, Profile, Resume, Job, Match, Package, Agent Run, queue/Worker/Outbox, all Steps, Events/SSE, three Approval gates, completion, idempotency, budget failure, explicit retry, cancellation, Redis/Worker restart, persistence, backup/restore, unauthorized access, invalid CSRF, and cleanup.

## Controlled DeepSeek validation

Use only a fully fictional Profile, Resume, Job, and company. Use a low output-token limit and at most one asynchronous Package Workflow so its three generation calls simultaneously cover tailored Resume, Cover Letter, and Application Answers. Do not log full Prompt/response text, auto-decide Approvals, submit, send, or deploy. Verify strict schemas, evidence links, unsupported-claim rejection, Worker/Approval chaining, usage recording, and safe event storage. A failure blocks a final completion claim.
