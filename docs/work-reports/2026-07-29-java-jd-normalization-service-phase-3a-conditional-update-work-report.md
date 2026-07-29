# Java JD Normalization Service Phase 3A Conditional Update Work Report

## 1. Repository

- Repository: <https://github.com/HKJoker-Z/personal-job-agent>
- Stable Personal Job Agent production version at start: `2.0.4`
- Personal Job Agent Alembic head at start: `20260724_06`
- Independent Java service: `services/jd-normalization-service/`

This report covers only Phase 3A of the independent Java JD Normalization
Service. The Personal Job Agent production application remains a separate
system.

## 2. Phase 2B PR final head

Phase 2B PR #28 ended at:

`786938f0c5db8684ad253dd8553a39547198b660`

The final head contained the mandatory Phase 2B Work Report. Its final
documentation-head Java workflow and all repository-required checks passed.
All 29 PostgreSQL integration tests ran with zero skips. V1 remained unchanged,
and no update, Docker, Compose, FastAPI integration, release, publication, or
deployment was added after the report.

## 3. Phase 2B merge commit

PR #28 was merged with a normal merge commit, without squash, rebase, admin
bypass, release, or deployment:

`be13ebc273919d628691c9474d88fedc16d5fc53`

Post-merge `main` CI and the Java service workflow passed. Local `main` and
`origin/main` both resolved to this commit before Phase 3A began.

## 4. Starting main commit

Phase 3A started from the verified post-merge `main` commit:

`be13ebc273919d628691c9474d88fedc16d5fc53`

## 5. Phase 3A branch

`feat/java-jd-normalization-service-phase-3a-conditional-update`

## 6. Exact scope

Implemented only:

- `PUT /api/v1/job-descriptions/{id}`;
- required strong `If-Match`;
- PostgreSQL-backed optimistic concurrency;
- full replacement using the existing deterministic normalization;
- immutable versions 2 and later;
- atomic root/current-version advancement;
- exact normalized-state no-op detection;
- canonical URL and deduplication conflict handling;
- version-history and rollback verification;
- MockMvc, PostgreSQL 16.14, and independent-transaction concurrency tests;
- OpenAPI, Java service README, CI, Work Report index, and this report.

Normalize preview, idempotent create and replay, all read APIs, ETag/304 reads,
keyset pagination, immutable history, authentication, request IDs, and the
stable error envelope remain available.

## 7. Scope exclusions

Not implemented:

- PATCH, DELETE, bulk update, partial update, restore, or version deletion;
- an update `Idempotency-Key` or update ledger;
- Dockerfile, Compose, application image build, or publication;
- FastAPI, React, Personal Job Agent PostgreSQL, Alembic, Redis, Dramatiq,
  Worker, Outbox, Nginx, or root production Compose integration;
- external provider, DeepSeek, or other LLM call;
- tag, release, deployment, production access, or production metadata change.

`docs/PROJECT_KNOWLEDGE.md` and production workflows were not changed.

## 8. Flyway migration decision

No migration is required, and no empty V3 was created. The reviewed V1 schema
already permits updates to the root's canonical URL, current version pointer,
current deduplication fingerprint, optimistic lock version, and update time.
Its version table accepts positive version numbers greater than one. The
deferred owner/current constraints support inserting a successor while moving
the root pointer in the same transaction, and the immutability trigger permits
INSERT while rejecting UPDATE and DELETE.

Flyway head therefore remains V2. Neither append-only migration changed:

- V1 SHA-256:
  `b73ecefbb610b06059a8e3c067f2fc874aab4e586e397739aad378aa78abcb40`;
- V2 SHA-256:
  `30bf80257a4fedfd4c125ef08adca94a840a018bba8f1d78cb1843fed55f8f7f`.

## 9. If-Match contract

PUT requires exactly one strong `If-Match` value in canonical form:

`"<nonnegative-decimal-version>"`

Zero is exactly `"0"`; nonzero values have no leading zero. The parser bounds
the encoded form to 21 characters and rejects weak tags, wildcard, unquoted,
negative, non-decimal, overflow, comma-separated, and multiple values.

- Missing: `428 PRECONDITION_REQUIRED`.
- Malformed: `400 INVALID_IF_MATCH`.
- Valid but stale: `412 PRECONDITION_FAILED`.

Authentication runs before controller parsing or resource disclosure. A stale
response does not automatically disclose the current ETag.

## 10. Update request and response

PUT reuses the bounded normalize/create request:

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

It is a full replacement. Omitted optional metadata becomes null. The existing
`jd-normalization-v1`, `skills-v1`, metadata normalization, URL normalization,
content hash, and `jd-deduplication:v1` fingerprint behavior is unchanged.

A changed update returns `200 OK`, `X-Request-ID`, the incremented strong
`ETag`, `Cache-Control: no-store`, and the existing current-resource response
representation. A subsequent authenticated GET returns the same current body.

## 11. ETag lifecycle

Create begins at optimistic version zero and ETag `"0"`. The first changed PUT
advances the version to one and returns `"1"`; the second advances it to two
and returns `"2"`. GET continues to derive its strong ETag from the same
`optimistic_lock_version`.

No-op, stale, failed-insert, and duplicate-conflict paths do not consume or
advance an ETag.

## 12. No-op behavior

After locking and validating the expected version, the transaction compares
the complete effective state: canonical URL, normalized text, content hash,
deduplication fingerprint, policy and dictionary versions, deterministic skill
snapshots, and normalized title, company, and location.

An exact match returns the already stored current resource and ETag with
`200 OK`. It inserts no version, performs no root update, and leaves
`updated_at` unchanged. The precondition check intentionally precedes this
comparison, so stale callers still receive 412 even when their replacement
would equal current state.

## 13. Transaction ordering

One READ COMMITTED PostgreSQL transaction:

1. locks the root row with `SELECT ... FOR UPDATE`;
2. loads the exact current immutable version in a fresh statement;
3. checks the expected optimistic version;
4. returns immediately for an exact no-op;
5. classifies known canonical URL and fingerprint duplicates;
6. generates a UUIDv4 and the next contiguous version number;
7. conditionally updates the root with
   `WHERE id = ? AND optimistic_lock_version = ?`;
8. inserts the immutable successor version;
9. reads back and verifies the new root/current identity;
10. commits only after deferred owner/current constraints succeed.

The root lock and current-version read are separate statements so a waiter sees
the committed current pointer after PostgreSQL grants the row lock. There is
no network or provider call in or around this transaction.

## 14. Optimistic concurrency

The row lock serializes independent database sessions for one aggregate, and
the focused root update repeats the caller's optimistic version in its WHERE
clause. Two actors using the same current ETag therefore cannot both advance
the root. The winner commits one successor; after acquiring the lock, the
loser observes the incremented version and receives 412.

No Java `synchronized`, in-process lock, single-JVM assumption, request order,
or web-server serialization is used.

## 15. JPA @Version interaction

`JobDescriptionEntity.optimisticLockVersion` remains mapped with JPA
`@Version`. Phase 3A uses focused JDBC for the write and does not attach or
write a managed JPA root in the same transaction. Its conditional SQL updates
the same mapped version column by exactly one, preserving the JPA version
contract for existing reads and any future focused JPA use.

The repository safety test proves the annotation remains present and that the
conditional repository exposes no broad save or delete method.

## 16. Immutable version creation

Every changed update creates exactly one application-generated UUIDv4
`job_description_versions` row. Existing historical rows are never updated or
deleted. The V1 trigger continues to reject both operations, while successor
INSERT remains allowed.

A forced successor insert failure rolls the preceding root update back in the
same transaction. Rolled-back attempts never appear in history.

## 17. Version numbering

The successor number is the locked current version number plus one. Tests
prove the first and second changed updates create versions 2 and 3, history
contains contiguous 1, 2, 3 numbers, and deterministic read ordering is
preserved.

Version-number and optimistic-version capacity are checked before mutation.

## 18. Root/current constraints

The transaction sets `canonical_url`, `current_version_id`,
`current_deduplication_fingerprint`, increments
`optimistic_lock_version`, and advances `updated_at`. It then inserts a
successor with the matching owner and deduplication fingerprint.

V1's deferred current-owner and current-fingerprint constraints validate the
complete aggregate at commit. Readback additionally checks the new version ID,
version number, and optimistic version before returning.

## 19. Duplicate-resource conflicts

Existing database uniqueness remains authoritative for canonical URL and
current deduplication fingerprint, including concurrent replacement races.
Known conflicts are classified in stable canonical-URL-first order. A database
uniqueness race aborts the update transaction, then a separate short
read-only transaction safely classifies the winner.

The response is `409 JOB_DESCRIPTION_ALREADY_EXISTS`. Details contain only
the authenticated existing aggregate ID and `canonical_url` or
`deduplication_fingerprint`. They contain no URL, text, fingerprint,
constraint name, SQL, or exception. The losing aggregate's root, ETag, and
history remain unchanged.

## 20. POST idempotency versus PUT preconditions

POST uses `Idempotency-Key` to suppress duplicate aggregate creation and to
replay a stored terminal create response. PUT targets an existing aggregate
and uses `If-Match` to prevent lost updates. PUT neither requires an
Idempotency-Key nor reads, creates, or changes a create-ledger row.

## 21. Historical create replay behavior

The create ledger stores the original POST status, body, Location, and ETag.
Phase 3A never rewrites that record. Replaying the same create after a later
PUT therefore returns the original creation representation and ETag `"0"`
with `Idempotency-Replayed: true`; a current GET independently returns the
latest version and ETag.

## 22. Error codes

Added:

- `PRECONDITION_REQUIRED`;
- `INVALID_IF_MATCH`;
- `PRECONDITION_FAILED`.

Existing not-found, already-exists, database-unavailable, internal,
validation, and authentication codes remain in use. Every error preserves
mandatory `code`, `message`, `request_id`, and object-valued `details`. Unknown
persistence failures remain generic.

## 23. Security and logging

Internal Bearer API-key authentication remains mandatory and precedes
resource or ETag disclosure. X-Request-ID, disabled CORS, no browser sessions,
status-only health, stable safe errors, and no-store write responses remain
unchanged.

Tests prove update logs and errors omit raw and normalized JD text, metadata,
canonical URL, Authorization, API key, hashes, SQL, constraint names, response
body, and exception detail. No new update-specific values are logged.

## 24. MockMvc tests

`JobDescriptionUpdateApiWebTest` and `StrongEtagTest` cover:

- changed and no-op 200 responses;
- ETag, no-store, and propagated request ID headers;
- missing, weak, wildcard, unquoted, negative, non-decimal, overflow,
  excessive, comma-separated, and multiple If-Match values;
- authentication precedence;
- stale, not-found, duplicate, and validation errors;
- mandatory stable error fields and sensitive-value absence;
- OpenAPI PUT, required If-Match, response headers/statuses, and absence of an
  update Idempotency-Key.

## 25. PostgreSQL tests

`PostgreSqlUpdateApiIT` uses PostgreSQL 16.14 to prove:

- version 1 to 2 and then 3 replacement;
- ETag `"0"` to `"1"` to `"2"`;
- PUT body equivalence with GET and GET 304 behavior;
- byte-for-byte unchanged historical version 1;
- expected normalized successor state and explicit-null metadata;
- correct current pointer and fingerprint;
- deterministic complete history;
- exact no-op behavior and stale-no-op rejection;
- canonical URL and fingerprint conflicts;
- unchanged ledger and historical create replay;
- authentication and sensitive-data safety.

## 26. Concurrency tests

`PostgreSqlUpdateConcurrencyIT` uses separate executor actors and independent
transactions. Two callers sharing ETag `"0"` produce exactly one 200 and one
412, exactly one version 2, no orphan version, and a valid root/current pair.

A concurrent same-fingerprint race between different aggregates produces one
200 and one safe 409. The winner advances once; the loser retains version 1
and ETag `"0"`. Latches and database synchronization are used without sleeps.

## 27. Rollback tests

A focused repository test intentionally supplies an invalid 31-byte content
hash after the root update. The version constraint rejects the INSERT, and
the transaction rollback leaves the root row byte-for-byte unchanged with one
history row.

Canonical URL and deduplication conflicts likewise preserve root, ETag,
updated time, and history. An optimistic loser creates no history row.

## 28. Regression tests

All earlier behavior remains green: normalize preview, Unicode/code-point
limits, skill dictionary, API-key authentication, request IDs, stable errors,
payload limits, Actuator, JSON-only OpenAPI, absent Swagger UI, create and
completed replay, read APIs, ETag/304, list filters, keyset pagination,
version history, immutable triggers, PostgreSQL constraints, and query plans.

No H2 or production PostgreSQL was used.

## 29. Flyway and schema validation

`FlywaySchemaIT` proves:

- the locked V1 and V2 source-file checksums;
- fresh V1+V2 migration;
- isolated V1-to-V2 upgrade;
- Flyway validation;
- a second migration executes zero changes;
- V2 is current;
- Hibernate schema validation succeeds against the migrated database.

No V3 file exists because the existing schema requires no correction.

## 30. Full Maven result

From `services/jd-normalization-service/`:

```text
./mvnw -B -ntp verify
```

Result:

- build success;
- 67 unit and MockMvc tests;
- 37 PostgreSQL integration tests across seven report classes;
- zero failures, errors, or skips;
- PostgreSQL Testcontainers image `postgres:16.14`.

Targeted If-Match, update API, concurrency, Flyway, and repository-safety
suites also passed. Runtime dependency inspection found no H2. OpenAPI
inspection, secret scan, tracked-output check, migration-diff check, and
`git diff --check` passed.

## 31. GitHub CI

PR #29 runs repository-required checks and the focused Java workflow. The Java
workflow requires Docker, runs full Maven verification, inspects the runtime
dependency tree, requires all seven PostgreSQL integration report classes,
rejects every skipped integration test, scans for obvious secrets, rejects
tracked build output, and checks whitespace.

The final documentation-head check results are recorded on the PR and in the
delivery response. No application image, publication, release, deployment, or
production credential step was added.

## 32. Changed files

Application changes:

- `persistence/create/NormalizedCreate.java`;
- focused `persistence/update/` service, repository, result, and exception
  types;
- `web/StrongEtag.java`;
- `web/JobDescriptionUpdateController.java`;
- `web/ApiExceptionHandler.java`.

Test changes:

- `FlywaySchemaIT.java`;
- `PostgreSqlUpdateApiIT.java`;
- `PostgreSqlUpdateConcurrencyIT.java`;
- `PersistenceRepositorySafetyTest.java`;
- `StrongEtagTest.java`;
- `JobDescriptionUpdateApiWebTest.java`;
- focused create/read MockMvc context updates.

Documentation and CI changes:

- `services/jd-normalization-service/README.md`;
- `.github/workflows/jd-normalization-service-ci.yml`;
- this report;
- `docs/work-reports/README.md`.

No migration, Backend/FastAPI, Frontend/React, Alembic, Redis, worker,
Compose, Nginx, release, deployment, production metadata, or Project
Knowledge file changed.

## 33. Commit SHAs

Implementation commits before this report:

- `329916e5e3d170e5794fd5541a40b884cd66ff66` —
  `feat(java): add conditional Job Description updates`;
- `b8b88523d7391c56e632dffde447aa9b445813d4` —
  `test(java): verify immutable update concurrency and rollback`.

The documentation commit containing this report cannot embed its own Git
object ID because doing so would change that ID.

## 34. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/29>

Title:

`Java: Add conditional JD updates and immutable versions`

The PR remains open and must not be merged by Phase 3A delivery.

## 35. Risks and limitations

- The service still has one internal caller security scope, not multi-tenant
  user authorization.
- PUT is protected by optimistic preconditions, not an update replay ledger;
  after an ambiguous transport failure, a caller should GET before retrying.
- Duplicate details expose an aggregate ID only within the authenticated
  internal scope.
- Version history grows without Phase 3A deletion or archival behavior.
- PostgreSQL availability remains an operational dependency.
- No PATCH, restore, external provider, or production integration is claimed.

## 36. Rollback

Before merge, close PR #29 and delete only the Phase 3A feature branch. After a
hypothetical merge, revert the Phase 3A application, test, documentation, and
workflow commits. No database downgrade is needed because no migration was
added. Existing immutable successor rows created while Phase 3A ran remain
valid data and must not be mutated or deleted as a rollback shortcut.

## 37. Confirmation that PATCH was not implemented

Confirmed. The service exposes no PATCH mapping, partial-update contract, or
partial field mutation.

## 38. Confirmation that DELETE was not implemented

Confirmed. No aggregate or version DELETE endpoint, repository operation, or
deletion behavior was added.

## 39. Confirmation that Docker was not implemented

Confirmed. No Dockerfile, Compose service, application image build, or image
publication was added. Docker is used only for local and CI PostgreSQL 16.14
Testcontainers.

## 40. Confirmation that FastAPI was untouched

Confirmed. No Backend/FastAPI code, configuration, database, Alembic migration,
or integration was changed.

## 41. Confirmation that production was untouched

Confirmed. Production was not accessed, changed, tagged, released, published,
deployed, or synchronized. Personal Job Agent production version `2.0.4`,
Alembic head `20260724_06`, production metadata, production Project Knowledge,
and release workflows remain unchanged.

## 42. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Implementation, tests, validation, documentation, and delivery made
no real DeepSeek or other external LLM/provider call.
