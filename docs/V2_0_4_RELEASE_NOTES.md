# Version 2.0.4 - Backend Reliability and Portfolio Architecture

Version 2.0.4 is a focused reliability and documentation upgrade from the
production Version 2.0.3 release. It does not add a new product workflow.

## Changes

- Adds an English, read-only Architecture page, a maintained architecture
  overview, three Architecture Decision Records, and reproducible fictional
  three-minute demo assets.
- Replaces Python-side monitoring aggregation with bounded PostgreSQL
  aggregation while preserving the API contract. The published plans and
  measurements are synthetic engineering evidence, not production latency.
- Correlates trusted or generated Request IDs through Edge, Frontend, Backend,
  responses, safe errors, workflow observations, and History audit details.
- Gives Analyze failures a stable JSON envelope with `error_code`, `message`,
  `request_id`, and `retryable`.
- Adds optional, user-scoped `Idempotency-Key` support for synchronous Analyze.
  PostgreSQL owns the request fingerprint and state machine.
- Replays completed keyed results byte-for-byte with
  `Idempotency-Replayed: true` and without a second provider call or History
  row.
- Uses a database uniqueness constraint, row locks, leases, and attempt tokens
  so concurrent duplicates have one winner.
- Commits optional History persistence and completed idempotency state in one
  transaction.
- Records provider-started ambiguous failures as `indeterminate` and blocks
  automatic re-execution.
- Configures both OpenAI-compatible Analyze clients with `max_retries=0`; the
  application permits at most one primary call and one explicit format-only
  repair call.
- Advances the production Alembic head from `20260721_05` to `20260724_06`.
  The migration adds `analyze_idempotency_records`, its constraints, and its
  indexes.

## Upgrade

Record the Version 2.0.3 Backend and Frontend digests and save its Compose and
runtime configuration. Create and verify a PostgreSQL 16 backup, then restore
that exact backup once into an isolated PostgreSQL 16 target. Validate
`20260721_05` to `20260724_06`, unchanged existing row counts and checksums,
valid foreign keys/sequences, and an initially empty idempotency ledger.

Deploy only immutable Version 2.0.4 Backend and Frontend digests. Validate one
internal candidate on `127.0.0.1:18091` with Mock LLM before switching public
8080. Synchronize the reviewed Project Knowledge through the authenticated
replace/rebuild mechanism only after confirming the runtime copy is a known
prior Git version.

## Rollback

Restore the recorded Version 2.0.3 image digests and saved Compose/runtime
configuration while preserving all PostgreSQL and Redis volumes, backups,
private files, and both Project Knowledge copies. The additive ledger may
remain during ordinary image rollback. Do not downgrade the production schema
while Analyze traffic is active, and do not remove the ledger without a
verified backup.

## Limitations

- PostgreSQL idempotency prevents duplicate local completion and History
  persistence; it cannot guarantee exactly-once execution by an external
  provider.
- An indeterminate provider outcome requires operator review or a deliberately
  new logical submission.
- Project Knowledge retrieval remains lexical PostgreSQL full-text search, not
  embedding/vector search.
- Synthetic query plans and benchmark timings are not production latency
  measurements.
- DeepSeek output and availability remain fallible. Results require human
  review, and deterministic fallback is less nuanced than a complete model
  response.
- Production remains a single-host Docker Compose deployment without high
  availability or a zero-downtime guarantee.
