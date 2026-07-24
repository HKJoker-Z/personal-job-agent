# Analyze PostgreSQL Idempotency Work Report

Date: 2026-07-24  
Scope: Phase A2, synchronous `POST /api/analyze` only  
Production access: none  
Real DeepSeek calls: none

## 1. PR #20 merge commit

PR #20 was verified open at reported head
`07dd9025b307fa80b39e59125c3c1d21a37ba057`. Runtime commit
`948e25dc44d9992d1820a331f59aaca1a4801dd0` was an ancestor, the Phase A1 Work
Report existed, all ten checks passed, and GitHub reported CLEAN/MERGEABLE.
It was merged without squash, rebase, admin bypass, tag, release, or deployment.
Merge commit: `129af303cd8dfd57b670c346b27c1197ded37e3a`.

## 2. Starting main commit

Local `main` was fast-forwarded to and matched `origin/main` at
`129af303cd8dfd57b670c346b27c1197ded37e3a`. Post-merge main CI run
`30094273494` passed all jobs before implementation began.

## 3. Implementation branch

`feat/analyze-postgresql-idempotency`

## 4. Analyze flow before idempotency

Analyze synchronously authenticated and validated the multipart Resume/JD
request, acquired effective inputs, scanned them, optionally retrieved Project
Knowledge, called the OpenAI-compatible DeepSeek API, optionally repaired model
format once, normalized/scored the response, optionally inserted History, wrote
best-effort monitoring data, and returned the result. Repeated HTTP submissions
were independent.

## 5. Duplicate-request failure modes

Before Phase A2, a browser retry, double submission, reverse-proxy retry, or
unknown network outcome could repeat model work and create multiple History
rows. Concurrent processes had no shared request arbiter. A crash after provider
execution could not distinguish safe retry from ambiguous external completion.

## 6. HTTP key contract

`Idempotency-Key` is optional. Absence preserves prior behavior. Accepted keys
are 8–128 ASCII characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]{7,127}`. Malformed keys return the existing
four-field Analyze envelope with `IDEMPOTENCY_KEY_INVALID`. Keys are scoped by
authenticated user and operation and grant no authority. Only a
domain-separated SHA-256 hash is stored.

Completed replay adds `Idempotency-Replayed: true`; first execution does not.
Active work returns bounded `Retry-After`. CORS exposes only
`Idempotency-Replayed` and `X-Request-ID`.

## 7. Database schema

`analyze_idempotency_records` stores UUID ID, user, operation, hashed key,
request fingerprint, status, request ID, attempt token, response status/body,
nullable History ID, provider-start time, lease expiry, attempt count, nullable
error code, created/updated/expiry timestamps, and nullable completion time.
Response JSON is application-bounded to 512 KiB.

## 8. Migration revision

Alembic `20260724_06`, directly after `20260721_05`. Upgrade creates only the
ledger, constraints, and indexes. Downgrade drops those indexes and the new
table. Existing tables and data are neither deleted nor transformed.

## 9. Unique constraints and indexes

- `uq_analyze_idempotency_scope_key` on
  `(user_id, operation, idempotency_key_hash)`;
- `ix_analyze_idempotency_expiry_status` on `(expires_at, status)`;
- `ix_analyze_idempotency_processing_lease` on
  `(status, lease_expires_at)`;
- allowed-state and positive-attempt-count checks.

## 10. Fingerprint format and version

`analyze-request-fingerprint:v1` is SHA-256 of UTF-8 canonical JSON with sorted
keys, compact separators, explicit nulls, and a version. It includes normalized
effective Resume text hash and Resume Version ID, normalized acquired JD hash,
Job URL, RAG state/top-k, current Project Knowledge document/content hash,
History choice, `deepseek-chat`, compact-analysis contract version, and security
policy version. Request/time/session/CSRF/generated IDs are excluded. The server
fingerprint is authoritative; a changed fingerprint returns
`409 IDEMPOTENCY_KEY_REUSED`.

## 11. State machine

Allowed states are `processing`, `completed`, `failed`, and `indeterminate`.
New and safely retryable failed records can enter processing. Successful durable
finalization enters completed. A handled pre-provider failure enters failed.
An ambiguous provider-started failure or expired provider-started lease enters
indeterminate.

## 12. Claim transaction

After auth, Origin, CSRF, ownership/input validation, Resume/JD acquisition, and
RAG version resolution, a short transaction inserts the scoped claim. The
unique constraint arbitrates processes. Conflict handling locks the one ledger
row only long enough to compare fingerprints/state and either replay, reject,
or assign a new attempt token. No provider call occurs in this transaction.

## 13. Provider-start boundary

Immediately before the primary call and immediately before an optional repair
call, a short conditional update persists `provider_started_at` and extends the
lease. The condition requires processing state and the current attempt token.

## 14. Provider retry configuration

Both OpenAI-compatible clients explicitly use `max_retries=0`. The accurate
claim is at most one primary application call plus at most one explicit
format-only repair call, with no hidden SDK transport retries. Completed replay
makes zero new provider calls. External exactly-once is not claimed.

## 15. Finalization transaction

Finalization locks the ledger record, verifies processing state and attempt
token, bounds JSON size, stores status/body/History ID, and marks completed in
one transaction. A stale token fails and cannot overwrite a takeover.

## 16. History atomicity

When History is enabled, its normalized `application_records` row is inserted
and flushed in the same transaction as final ledger response/status completion.
Any error rolls back both. When disabled, bounded normalized response JSON is
still stored for exact replay. Monitoring remains a separate best-effort write.

## 17. Replay behavior

The stored status and body are returned identically with
`Idempotency-Replayed: true`. Resume/JD normalization and fingerprint
verification still occur; DeepSeek and History insertion do not.

## 18. Concurrency behavior

PostgreSQL uniqueness, row locking, leases, and attempt tokens provide
multi-process correctness. A concurrent active duplicate receives
`IDEMPOTENCY_REQUEST_IN_PROGRESS`; it cannot become a second winner. No
in-process lock is used.

## 19. Indeterminate behavior

If a processing lease expires without `provider_started_at`, a new token may
safely take over. If provider start was recorded, the state becomes
indeterminate and returns `IDEMPOTENCY_OUTCOME_UNKNOWN`; automatic provider
execution is blocked.

## 20. Frontend key lifecycle

Each logical Analyze submission gets UUIDv4. A safe in-memory payload hash
detects Resume/JD/URL/RAG/top-k/History changes and causes a new key. CSRF refresh
reuses request headers and therefore the key. Success and terminal rejection
clear pending state; in-progress, persistence unavailability, and network
unknown retain it. Resume/JD content and keys are not written to LocalStorage or
SessionStorage.

## 21. Retention and cleanup

Default retention is 24 hours, configurable by
`ANALYZE_IDEMPOTENCY_RETENTION_HOURS` (1–168). Leases default to 180 seconds,
bounded 5–300 to cover primary and optional repair timeouts. Claim-time maintenance handles at most 100 rows, marks stale
provider-started work indeterminate, marks fully expired pre-provider work
failed, and deletes only expired terminal records. The JSON cap, retention, and
indexes bound PostgreSQL growth; volume still scales with request rate and
stored response size.

## 22. Security and ownership

Authentication, active-user checks, trusted Origin, CSRF, Resume ownership, and
input validation precede replay disclosure. The key is not a credential. Raw
keys, Resume/JD text, prompts, provider bodies, cookies, CSRF values, and
secrets are not stored in the ledger, response errors, or logs.

## 23. Targeted tests

`test_analyze_idempotency.py` covers key syntax/hash, canonical fingerprints,
success/replay, replay header, changed request, user scope, no-key compatibility,
active lease, safe takeover, indeterminate state, stale token, atomic rollback,
History deduplication, no-History replay, fallback replay, auth/CSRF precedence,
cleanup, and SDK retry settings. Existing correlation/resilience tests remain
green after the CORS contract update.

## 24. PostgreSQL integration tests

An isolated PostgreSQL 16.9 container ran the full opt-in integration module.
The new barrier-synchronized two-actor test proved one database winner and one
in-progress loser with exactly one ledger row. All 10 tests passed. Migration
upgrade, downgrade, and upgrade paths ran on PostgreSQL.

## 25. Full backend tests

The complete backend discovery suite ran 431 tests with no provider network
access. Its first run exposed one obsolete CORS assertion and one order-sensitive
monitoring log assertion; the CORS assertion was corrected and both exact tests
then passed in isolation. GitHub's clean-environment full-suite result is
recorded in the CI section after delivery.

## 26. Frontend tests and build

Vitest: 9 files, 63 tests passed. Coverage includes generated UUID syntax,
non-persistence, and exact key reuse across the automatic CSRF refresh retry.
Production Vite build passed (38 modules, 334.98 kB main JS, 99.06 kB gzip).

## 27. Docker/Compose/smoke results

Only isolated local validation resources were used. Backend and frontend Docker
builds passed, non-root/sensitive-path image checks passed, Compose validation
passed, and the isolated Version 2.0.3 Mock LLM smoke passed all health, auth,
CSRF, Resume, Analyze, RAG, persistence, backup, and restore checks. No running
production service or production data was accessed.

## 28. Backup/restore validation

The backend suite covers backup/restore unit regression. The isolated Docker
smoke created, verified, restored, and compared a PostgreSQL 16/private-file
backup including the new required ledger table.

## 29. Changed files

Changes are limited to Analyze idempotency: ORM/model/migration/readiness,
idempotency service and middleware, Analyze/provider integration, focused tests,
frontend submission lifecycle/tests, backup required-table inventory,
configuration examples, API/architecture/README/Project Knowledge documents,
and Work Reports.

## 30. Commit SHAs

Implementation commit: `459861ff7bc9dfe78e4f67cbdc3b62c586d0630a`.  
Documentation and initial Work Report commit:
`269a67f7db16ffb5da52450e66726658c3487fc3`.

## 31. PR URL

PR #21: https://github.com/HKJoker-Z/personal-job-agent/pull/21

## 32. CI results

PR checks will be recorded after all required GitHub checks reach terminal
success. Required-check bypass will not be used.

## 33. Risks

- External provider execution cannot be made exactly once by a local database.
- Indeterminate rows require a deliberate new logical submission or operator
  review; automatic retry is intentionally prohibited.
- Response JSON consumes PostgreSQL capacity, bounded by 512 KiB and retention.
- Claim-time cleanup is opportunistic; low request volume can delay deletion,
  but it cannot delete active work prematurely.
- URL/Project Knowledge changes can intentionally produce a different server
  fingerprint and reject reuse.

## 34. Rollback

Before release, rollback is code reversion plus Alembic downgrade to
`20260721_05`; the downgrade removes only the new ledger. Because no release or
deployment occurred, operational rollback is not required. After any future
release, drain Analyze traffic before code/schema rollback and retain a verified
PostgreSQL backup.

## 35. Confirmation that production was untouched

Confirmed. No production API, database, filesystem, Project Knowledge,
deployment, release, tag, or running production service was accessed or
modified. Validation used temporary SQLite databases and one explicitly named
isolated PostgreSQL 16 test container.

## 36. Confirmation that real DeepSeek was not called

Confirmed. Provider behavior used deterministic mocks, deliberate exceptions,
or the repository Mock LLM mode. No real DeepSeek request was made.

## Validation summary

| Check | Result |
|---|---|
| PR #20 checks before merge | PASS, 10 checks |
| Main CI after merge | PASS, run `30094273494` |
| Targeted idempotency/backend regression | PASS |
| PostgreSQL 16 integration/concurrency | PASS, 10 tests |
| Clean migration / upgrade from `20260721_05` / downgrade | PASS |
| Frontend suite | PASS, 63 tests |
| Full backend suite | 431-test run found 2 test-state/assertion issues; both exact reruns PASS; clean CI pending |
| Frontend production build | PASS |
| Docker builds / image verification | PASS |
| Compose validation | PASS |
| Mock LLM Docker smoke | PASS |
| PostgreSQL backup/restore regression | PASS in isolated smoke |
| Repository safety / secret scan / `git diff --check` | pending |
