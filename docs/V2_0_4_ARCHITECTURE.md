# Version 2.0.4 Reliable Agent Workflow Architecture

Version 2.0.4 is the final functional foundation for the future formal Version 2 release. PostgreSQL 16 is the business system of record. Redis 7.4.1 is only a queue and short-lived coordination layer; losing Redis does not lose Run state. Dramatiq 2.2.0 consumes allow-listed JSON identifiers and does not use pickle. Celery, RQ, and ARQ are not present.

## Durable data model

Alembic revision `20260717_04` follows the unchanged `20260713_03` revision and adds:

1. `agent_runs`: owner-scoped workflow state, immutable input references, snapshot revisions, optimistic revision, safe failure, limits, usage totals, cancellation, and progress.
2. `agent_steps`: ordered idempotent steps, revision, retry schedule, Worker lease, safe result references, usage totals, and partial/cancellation state.
3. `agent_run_events`: append-only safe progress and transition summaries with a monotonic event ID for SSE reconnect.
4. `approval_requests` and `approval_decisions`: explicit pending gates and append-only idempotent decisions.
5. `agent_outbox_events`: PostgreSQL Transactional Outbox rows whose state survives Redis or dispatcher interruption.
6. `user_ai_budgets` and `ai_usage_ledger`: daily/user/Run/Step limits and exactly-once usage keys.
7. `worker_heartbeats`: readiness-visible Worker capacity and graceful shutdown state.
8. `dead_letter_records`: safe terminal records for exhausted queue or step delivery.

Foreign keys, ownership fields, UTC timestamps, status constraints, indexes, and uniqueness constraints are defined in the migration. Full Prompts, model responses, Resume/JD/Material bodies, Profile PII, credentials, Session state, and database URLs are not stored in these workflow tables.

## Delivery and recovery

Run creation and its first Outbox record commit in one database transaction. The dispatcher locks available Outbox rows with `SKIP LOCKED`, publishes only `run_id`, `step_id`, `workflow_type`, `attempt`, and `correlation_id`, then records publication. A Worker claims one Step using a row lock, expected attempt, execution token, and lease. Duplicate or stale deliveries cannot run the Step twice.

The dispatcher retries Redis publication with bounded exponential backoff and jitter. Stale publishing rows are recovered. Published rows whose Step remains queued are republished after a bounded interval, allowing PostgreSQL to reconstruct transient queue work after Redis data loss. Exhausted delivery creates a Dead Letter record. Expired Worker leases are recovered and explicitly resumed. Completed Steps and existing generated Material Versions are reused, so recovery does not repeat model calls or usage accounting.

## Transactional state machine

Run transitions are restricted to the documented queued/running/waiting/retry/failed/completed/cancelled/dead-letter graph. Step transitions have a corresponding pending/queued/running/waiting/completed/skipped/failed/cancelled/retry graph. Each transition:

- locks the current row;
- verifies the current state and expected revision where user initiated;
- increments the revision;
- appends an Agent Event;
- appends a safe Audit Event;
- commits the state and any next Outbox work atomically.

Queued and waiting Runs cancel immediately. A running Run records `cancel_requested`; Workers stop at a Step boundary and keep produced Drafts marked partial. Automatic retry is limited to three retries and applies only to transient provider/network failures. Validation, permission, policy, and budget failures are not automatically retried. Explicit retry warns that already-recorded usage remains and additional billing may occur.

## 20-step Application Package workflow

`generate_application_package` executes the following idempotent sequence:

1. validate request
2. snapshot Profile
3. snapshot Job
4. load Resume
5. run or reuse Match
6. select grounded evidence
7. generate tailored Resume
8. validate tailored Resume
9. request Resume approval
10. wait for Resume approval
11. generate Cover Letter
12. validate Cover Letter
13. request Cover Letter approval
14. wait for Cover Letter approval
15. generate Application Answers
16. validate Application Answers
17. build Package summary
18. request Package approval
19. wait for Package approval
20. finalize Run

Approval wait Steps do not occupy a Worker. The browser can close after the API returns `202`; the Run continues from PostgreSQL and Redis/Dramatiq. An approved Draft still passes independent evidence validation. Unsupported claims are never auto-confirmed. Package approval is explicit, and no Step submits an application or sends email.

## Budgets and concurrency

Creation enforces a per-user active Run limit. Worker thread count enforces global execution concurrency. Before every model call, the service checks projected input/output tokens and estimated cost against the daily, Run, and Step limits. A configured high-cost threshold inserts an Approval before the call. Provider-reported tokens are recorded even when a call later fails, and the unique usage key prevents duplicate cost under redelivery.

## Live progress and UI

Agent Events are streamed through an authenticated, owner-scoped SSE endpoint. `Last-Event-ID` resumes after a monotonic event ID, comment heartbeats keep idle connections alive, and per-user connection limits are coordinated through Redis in production. The React workspace deduplicates replayed events, displays reconnect state, current Step, progress, usage/cost, safe error, retry/cancel/resume, and pending Approvals.

## Non-goals

This milestone does not merge or deploy itself, create a `v2.0.0` Tag/Release, expose backend/PostgreSQL/Redis publicly, send email, or submit applications. Interview Center, Mock Interview, formal STAR Stories, browser extension, and multi-model intelligent routing are Version 2.1.x work.
