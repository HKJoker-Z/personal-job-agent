# Java JD Normalization Service Phase 2B Idempotent Create Work Report

## 1. Repository

- Repository: <https://github.com/HKJoker-Z/personal-job-agent>
- Stable Personal Job Agent production version at start: `2.0.4`
- Personal Job Agent Alembic head at start: `20260724_06`
- Java service: `services/jd-normalization-service/`

This report covers only Phase 2B of the independent Java service. The existing
Personal Job Agent production application is a separate system.

## 2. Phase 2A PR final head

Phase 2A PR #27 ended at:

`b1470659368aefffd277e8bf3ba775571a7174fc`

The final head contained the Phase 2A Work Report. Its final
documentation-head Java workflow and all repository checks passed. The
reviewed V1 schema had no later unrelated changes, and no create,
idempotency, update, Docker, Compose, FastAPI integration, release,
publication, or deployment behavior was added after the report.

## 3. Phase 2A merge commit

PR #27 was merged with a normal merge commit, without squash, rebase, or admin
bypass:

`9f2079b84b6f42f86f06834111fb1290e1d08f97`

Both parents are the prior `main` head
`7ef6db0fcbb36cb47a429ee33347f52412d7dfdb` and the reviewed Phase 2A head.
Post-merge `main` CI passed, and local `main` matched `origin/main`.

## 4. Starting main commit

Phase 2B started from the verified post-merge `main` commit:

`9f2079b84b6f42f86f06834111fb1290e1d08f97`

## 5. Phase 2B branch

`feat/java-jd-normalization-service-phase-2b-idempotent-create`

## 6. Technology and dependency changes

The service continues to use Java 21, Spring Boot 3.5.16, Spring MVC, Spring
Security, Bean Validation, Actuator, Spring Data JPA/JDBC, Hibernate,
Flyway 11.7.2, PostgreSQL JDBC, Springdoc 2.8.17, Maven Failsafe, and
Testcontainers 1.21.4.

No Maven dependency or version changed. The runtime dependency tree contains
no H2. PostgreSQL `16.14` remains the integration-test database. No Redis,
provider SDK, LLM SDK, cache, worker, messaging, Docker application, or
publication dependency was added.

## 7. Exact scope

Implemented:

- Flyway V2 request-idempotency ledger;
- one public persistence endpoint, `POST /api/v1/job-descriptions`;
- required `Idempotency-Key` validation and domain-separated hashing;
- canonical request and deduplication fingerprints;
- PostgreSQL-backed claim, lease, takeover, and conditional ownership;
- atomic root, immutable version 1, and completed-result creation;
- exact completed replay;
- deterministic, replayable duplicate-resource conflicts;
- bounded completed-result retention and best-effort cleanup;
- safe error and logging behavior;
- OpenAPI, README, CI, tests, and this Work Report.

The Phase 1 normalize preview and all Phase 2A read APIs remain available.

## 8. Scope exclusions

Not implemented:

- PUT, PATCH, DELETE, If-Match, or version 2 and later;
- any update transaction;
- Dockerfile, Compose, application image build, or publication;
- FastAPI, React, Redis, Dramatiq, Worker, Outbox, Nginx, or root production
  Compose integration;
- external provider, network, DeepSeek, or other LLM call;
- release workflow, tag, release, deployment, or production access.

Alembic, production metadata, and `docs/PROJECT_KNOWLEDGE.md` are unchanged.

## 9. Flyway V2

Created only:

`src/main/resources/db/migration/V2__create_request_idempotency.sql`

The Flyway schema head is now `2`. V1 was not edited; its locked SHA-256 is:

`b73ecefbb610b06059a8e3c067f2fc874aab4e586e397739aad378aa78abcb40`

V1 remains append-only. V2 must also be treated as append-only after merge.

## 10. Idempotency schema

`request_idempotency` stores:

- UUID identity and operation;
- 32-byte key hash and request fingerprint;
- `processing` or `completed` status;
- attempt token and processing lease expiry;
- optional response status, object-valued JSON body, Location, ETag, and Job
  Description identity;
- created, updated, expiry, and optional completion timestamps.

The raw idempotency key is not stored.

## 11. Constraints and indexes

The migration enforces:

- unique `(operation, idempotency_key_hash)`;
- nonblank operation bounded to 64 characters;
- exact 32-byte key and request hashes;
- only `processing` and `completed`;
- no response fields on processing rows;
- response status, response body, and completion time on completed rows;
- HTTP status range 100–599;
- object-valued response JSON bounded to 256 KiB;
- valid created/updated/lease/expiry/completion ordering;
- restricted, non-cascading optional foreign key to `job_descriptions`.

The unique constraint is the claim boundary. Partial indexes cover expired
completed cleanup and processing-lease lookup. No unrelated index was added.

## 12. Idempotency-Key contract

Create requires exactly one `Idempotency-Key` matching:

`[A-Za-z0-9][A-Za-z0-9._:-]{15,127}`

This is 16–128 ASCII characters. UUIDv4 is recommended but not required.
Missing keys return `400 IDEMPOTENCY_KEY_REQUIRED`. Invalid, short, long,
illegal-character, or multiple values return
`400 IDEMPOTENCY_KEY_INVALID`.

The key is not authentication, authorization, a request ID, or an object
identifier. CORS remains disabled.

## 13. Key hashing

Only this 32-byte value is stored:

`SHA-256(UTF-8("jd-normalization:idempotency-key:v1\0" + raw_key))`

The raw key and its hash are excluded from logs, errors, and responses.
Uniqueness is operation plus key hash. The service has one internal caller
security scope; this is not user-level multi-tenancy.

## 14. Request fingerprint

`jd-create-request:v1` domain-separates a SHA-256 hash over canonical JSON
that binds:

- create contract version;
- normalized text and normalized metadata, including explicit nulls;
- content hash;
- normalization-policy and skill-dictionary versions;
- deterministic required, preferred, and mentioned skill outputs.

Object field order and array order are stable. The UTF-8 input contains no
timestamp, request ID, API key, Idempotency-Key, generated UUID, or database
state.

## 15. Deduplication fingerprint

`jd-deduplication:v1` separately hashes canonical JSON containing normalized
text, normalized title/company/location/canonical URL, policy and dictionary
versions, and deterministic required/preferred/mentioned skill IDs.

It is distinct from `content_hash` and the request fingerprint.
`content_hash` remains SHA-256 of UTF-8 normalized text. Meaningfully different
metadata can therefore preserve `content_hash` while changing deduplication.

## 16. Create request and response

Create reuses the bounded normalize request:

```json
{
  "raw_text": "...",
  "metadata": {
    "title": "...",
    "company": "...",
    "location": "...",
    "canonical_url": "..."
  }
}
```

The existing `jd-normalization-v1` and `skills-v1` behavior is unchanged. A
first success returns `201 Created`, `X-Request-ID`, resource `Location`,
strong `ETag: "0"`, `Cache-Control: no-store`, and the existing current-resource
body used by the corresponding GET.

## 17. State model

The ledger uses only:

- `processing`;
- `completed`.

There is no `failed` or `indeterminate` state. Unlike the FastAPI DeepSeek
analysis flow, Phase 2B performs no external side effect. Every business
mutation is confined to PostgreSQL, so an expired processing claim can be
safely retried.

## 18. Claim transaction

After authentication, validation, normalization, and fingerprinting, a short
transaction attempts `INSERT ... ON CONFLICT DO NOTHING` for the operation and
key hash. An inserted row owns the claim through its UUID attempt token. An
existing row is locked and classified by request fingerprint, state, and
lease. The claim commits before final creation starts.

No Java lock, synchronized block, single-JVM assumption, or web-server
serialization is used.

## 19. Lease and takeover

The default processing lease is 30 seconds and configuration is constrained to
1–120 seconds. An active matching claim returns
`409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with a 1–120 second `Retry-After`.

An expired matching claim is conditionally updated with a new attempt token,
lease, and retention horizon while the row is locked. Finalization checks both
`processing` and the exact token. A stale token cannot overwrite a newer
processing or completed attempt.

## 20. Root and version creation

The winning final transaction generates application UUIDv4 identities and
inserts:

- one `job_descriptions` root;
- one immutable `job_description_versions` row with version number 1.

The root points to the exact new version, sets the current deduplication
fingerprint, and starts `optimistic_lock_version` at zero. V1 deferred
owner/current constraints validate the aggregate at commit.

## 21. Atomic finalization

In the same final PostgreSQL transaction, the service builds the exact
current-resource response, verifies the size of PostgreSQL's stored `jsonb`
form, conditionally updates the owned ledger row with status/body/Location/
ETag/resource ID, and marks it completed.

Root, version, and result either all commit or all roll back. There is no
network call or transaction held across an external operation. An oversized
result completes with a stable replayable
`500 IDEMPOTENCY_PERSISTENCE_FAILED` and creates no aggregate.

## 22. Replay

A completed row with the same request fingerprint returns the stored status,
JSON body, Location, and ETag and adds `Idempotency-Replayed: true`. The stored
PostgreSQL `jsonb` representation is read back for the first response, so first
delivery and replay use the same serialized body.

Replay performs only the bounded authentication, validation, normalization,
fingerprinting, and lookup needed to prove request identity. It creates no
root, version, or ledger row and does not rebuild the stored response.

## 23. Duplicate-resource handling

Existing V1 uniqueness remains authoritative for:

- canonical URL;
- current deduplication fingerprint;
- concurrent duplicates.

The safe terminal response is `409 JOB_DESCRIPTION_ALREADY_EXISTS`. Details
contain only the authenticated existing Job Description ID and stable
`canonical_url` or `deduplication_fingerprint` category. They never expose the
URL, text, fingerprint, constraint, SQL, or exception.

Different keys for the same request create one aggregate. The losing key is
completed with the stable conflict. The same content with different normalized
metadata can create separate aggregates when the deduplication fingerprints
differ and canonical URLs do not conflict.

## 24. Deterministic conflict finalization

The root insert uses conflict-aware `INSERT ... ON CONFLICT DO NOTHING`, then a
bounded authenticated lookup classifies canonical URL before deduplication
fingerprint. This avoids PostgreSQL's transaction-aborted state without a
savepoint. No conflicting root or version is inserted, and the still-valid
transaction completes the accepted idempotency claim with the stable 409.

Trade-off: the implementation performs a small classification query after a
conflict. In return, it does not depend on constraint names, does not leak SQL
details, and can atomically persist the replayable result.

## 25. Retention and cleanup

Defaults are:

- completed retention: 24 hours;
- processing lease: 30 seconds;
- cleanup batch: 100;
- stored response limit: 256 KiB.

Each create path performs best-effort cleanup in a separate bounded
transaction. `DELETE` selects only expired completed rows through the partial
expiry index, orders deterministically, uses `FOR UPDATE SKIP LOCKED`, and
limits the batch. Processing rows are never deleted. Cleanup failure is logged
generically and cannot fail the create response. Delayed cleanup preserves
replay correctness while the row remains.

## 26. Security and logging

Internal Bearer API-key authentication occurs before controller replay or
resource disclosure. X-Request-ID, stable errors, status-only health,
no-store create responses, disabled CORS, and absence of browser sessions are
preserved.

Logs are limited to request ID, route, status, duration, replay boolean,
stable idempotency outcome, and a created resource ID only after authenticated
creation. They omit raw and normalized JD text, metadata, canonical URL, raw
key, all hashes/fingerprints, Authorization, API key, response body, SQL,
constraint names, and exception text.

The ledger is not an authorization mechanism.

## 27. Error codes

Added:

- `IDEMPOTENCY_KEY_REQUIRED`;
- `IDEMPOTENCY_KEY_INVALID`;
- `IDEMPOTENCY_KEY_REUSED`;
- `IDEMPOTENCY_REQUEST_IN_PROGRESS`;
- `IDEMPOTENCY_PERSISTENCE_FAILED`;
- `JOB_DESCRIPTION_ALREADY_EXISTS`.

Every error retains the mandatory `error.code`, `message`, `request_id`, and
object-valued `details`. Unknown persistence failures are generic.

## 28. JPA and repository operations

No broad write repository is exposed. Existing JPA read repositories still
offer only focused reads. `IdempotencyLedgerRepository` publicly exposes only:

- `claim`;
- `finalizeCreate`;
- `cleanupExpiredCompleted`.

Focused JDBC operations perform the atomic root/version writes, conditional
ownership updates, replay reads, duplicate classification, and cleanup.
Database constraints remain the final correctness boundary.

## 29. Flyway tests

`FlywaySchemaIT` verifies:

- fresh V1+V2 migration;
- isolated V1-to-V2 upgrade;
- Flyway validation;
- second migration executes zero changes;
- V1 file checksum and migrated checksum stability;
- V2 is current;
- Hibernate schema validation at application startup.

## 30. Constraint tests

Direct PostgreSQL checks cover:

- required tables, constraints, indexes, and restricted foreign key;
- operation/key uniqueness;
- 32-byte hashes;
- operation, status, processing/completed response invariants;
- HTTP status and object-valued JSON;
- lease and expiry ordering;
- prior owner/current, immutability, version, hash, JSONB, and restricted-delete
  constraints.

## 31. API tests

MockMvc and PostgreSQL API tests cover:

- first create, headers, GET equivalence, and one root/version 1;
- missing, short, overlong, illegal, and multiple idempotency keys;
- exact success and conflict replay with no extra rows;
- same-key/different-request reuse;
- same-payload/different-key deduplication;
- canonical URL conflict;
- same content with different metadata;
- authentication before replay;
- bounded result failure;
- stable safe errors and sensitive-value absence;
- OpenAPI create path, required header, response headers, and preserved routes.

## 32. Concurrency tests

Separate executor actors and PostgreSQL transactions prove:

- same key has one winner and an in-progress loser or completed replay;
- different keys for one fingerprint create one aggregate and one completed
  replayable conflict;
- expired claims can be taken over;
- stale attempts cannot finalize;
- active claims receive bounded retry guidance;
- a forced version-insert constraint failure rolls back the root and version;
- deterministic conflicts leave no permanent processing row.

Synchronization uses latches and database state rather than sleep-based timing
assertions.

## 33. Cleanup tests

Tests insert expired completed and active processing rows, prove delayed cleanup
does not prevent replay, delete expired rows in configured batches of two, and
prove active processing survives every pass. Oversized response tests prove
that the stable completed 500 is replayable and no aggregate is created.

## 34. Regression tests

All earlier tests remain green for deterministic normalization, Unicode and
code-point limits, skills, authentication, request IDs, stable errors, payload
limits, Actuator, JSON OpenAPI, absence of Swagger UI, current/list/history
reads, ETag/304, filters, keyset pagination, immutable triggers, query plans,
and PostgreSQL constraints.

No H2 or production PostgreSQL was used.

## 35. Full Maven validation

From `services/jd-normalization-service/`:

```text
./mvnw -B -ntp verify
```

Result:

- build success;
- 60 unit and MockMvc tests;
- 29 PostgreSQL integration tests;
- zero failures, errors, or skips;
- PostgreSQL Testcontainers image `postgres:16.14`.

Targeted create, Flyway, and concurrency suites also passed. Runtime dependency
inspection rejected H2. OpenAPI inspection, repository API safety, V1 checksum,
secret scan, tracked-output check, and `git diff --check` passed.

## 36. GitHub CI

PR #28 runs the existing repository-wide checks plus the focused Java
workflow. The Java workflow requires Docker, runs full Maven verification,
inspects the runtime dependency tree, requires all five PostgreSQL integration
report classes, rejects every skipped integration test, scans for obvious
secrets, rejects tracked build output, and checks whitespace.

The implementation-head and final documentation-head check results are
recorded on the PR and in the delivery response. No production credential,
application image, publication, release, or deployment step was added.

## 37. Changed files

The PR changes only:

- `.github/workflows/jd-normalization-service-ci.yml`;
- Java service `.env.example`, `README.md`, configuration, logging/error
  handling, create controller, focused create persistence package, and V2;
- Java unit, MockMvc, migration, API, concurrency, cleanup, safety, and
  regression tests;
- this report and `docs/work-reports/README.md`.

No Backend/FastAPI, Frontend/React, Alembic, Redis, Dramatiq, Worker, Outbox,
root Compose, Nginx, release, deployment, production metadata, or Project
Knowledge file changed.

## 38. Commit SHAs

Implementation commits before this report:

- `3fe3baf20243ea00c0705615eb6394605e8ead0f` —
  `feat(java): add PostgreSQL idempotency ledger`;
- `abab501bb0bafa84d831d81af0be3878cc38c009` —
  `feat(java): add atomic idempotent Job Description creation`;
- `5fb74b0bb601930c7b5d76993c9392f65de4140b` —
  `test(java): verify idempotent create concurrency and cleanup`.

The commit containing this report cannot embed its own Git object ID because
doing so would change that ID.

## 39. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/28>

Title:

`Java: Add PostgreSQL-backed idempotent JD creation`

The PR remains open and must not be merged by Phase 2B delivery.

## 40. Risks and limitations

- Completed replay is bounded by retention; after cleanup, the key can form a
  new claim.
- Recovery of an abandoned processing claim occurs when a caller retries after
  lease expiry; no scheduler was added.
- The service has one internal caller scope, not user-level multi-tenancy.
- PostgreSQL availability and clock behavior remain operational dependencies.
- V2 becomes an append-only compatibility commitment after merge.
- No update, external-provider exactly-once, or production integration is
  claimed.

## 41. Rollback

Before merge, close PR #28 and delete only the Phase 2B feature branch. After a
hypothetical merge, revert application, test, documentation, and workflow
changes. Do not edit merged V1 or V2; correct schema behavior with a separately
reviewed forward migration. Existing immutable roots and versions must not be
mutated or deleted as a rollback shortcut.

## 42. Confirmation that update was not implemented

Confirmed. There is no PUT, PATCH, DELETE, If-Match, version-2 creation,
optimistic update service, or update transaction.

## 43. Confirmation that Docker was not implemented

Confirmed. No Dockerfile, Compose service, application image build, or image
publication was added. Docker is used only to run PostgreSQL 16.14
Testcontainers in local validation and CI.

## 44. Confirmation that FastAPI was untouched

Confirmed. No Backend/FastAPI code, configuration, database, Alembic migration,
or integration was changed.

## 45. Confirmation that production was untouched

Confirmed. Production was not accessed, changed, tagged, released, published,
deployed, or synchronized. Personal Job Agent production version `2.0.4`,
Alembic head `20260724_06`, production metadata, and Project Knowledge remain
unchanged.

## 46. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Implementation, tests, validation, documentation, and delivery made
no real DeepSeek or other external LLM/provider call.
