# Java JD Normalization Service Phase 2A PostgreSQL Read Model Work Report

## 1. Repository

- Repository: <https://github.com/HKJoker-Z/personal-job-agent>
- Stable Personal Job Agent production version at start: `2.0.4`
- Personal Job Agent Alembic head at start: `20260724_06`
- Java service path: `services/jd-normalization-service/`

This report covers only the independent Java service. The production FastAPI
modular monolith remains a separate application.

## 2. Phase 1 PR final head

Phase 1 PR #26 ended at:

`c85b1dfde99671359dfe153ee9e881f1ac022d51`

The final head contained the Phase 1 Work Report and passed the Java workflow
plus every repository-required check.

## 3. Phase 1 merge commit

PR #26 was merged with a normal merge commit, without squash, rebase, admin
bypass, tag, release, or deployment:

`7ef6db0fcbb36cb47a429ee33347f52412d7dfdb`

Both post-merge `main` workflows passed.

## 4. Starting main commit

Phase 2A started from the same verified `main` commit:

`7ef6db0fcbb36cb47a429ee33347f52412d7dfdb`

Local `main` and `origin/main` matched before the feature branch was created.

## 5. Phase 2A branch

`feat/java-jd-normalization-service-phase-2a-postgresql-read-model`

## 6. Technology and dependency changes

The service preserves Java 21, Spring Boot 3.5.16, Spring MVC, Bean Validation,
Spring Security, Actuator, Springdoc 2.8.17, Maven Wrapper 3.9.16, and the
Phase 1 normalization stack.

Spring Boot-managed Phase 2A dependencies resolve to:

| Component | Version | Scope |
|---|---:|---|
| Spring Data JPA starter | 3.5.16 | runtime |
| Hibernate ORM | 6.6.53.Final | transitive runtime |
| Flyway Core | 11.7.2 | runtime |
| Flyway PostgreSQL support | 11.7.2 | runtime |
| PostgreSQL JDBC | 42.7.11 | runtime |
| Spring Boot Testcontainers | 3.5.16 | test |
| Testcontainers PostgreSQL | 1.21.4 | test |
| Testcontainers JUnit Jupiter | 1.21.4 | test |
| PostgreSQL container image | 16.14 | integration test |

Maven Failsafe 3.5.6 runs `*IT` during `verify`. No transitive version was
overridden. H2, Redis, Kafka, Lombok, MapStruct, QueryDSL, Liquibase, and
Hypersistence Utils were not added.

## 7. Exact Phase 2A scope

Implemented:

- service-owned PostgreSQL configuration;
- Flyway V1;
- JPA root and immutable version mappings;
- JSONB skill snapshots;
- repositories exposing reads but no normal save/delete API;
- focused current, list, and version-history query service;
- current-resource ETag and conditional GET;
- exact bounded filters and keyset pagination;
- stable read/database error mapping;
- schema-sensitive readiness;
- PostgreSQL 16.14 Testcontainers coverage;
- query-plan index-eligibility evidence;
- Java CI enforcement;
- README and this Work Report.

The existing normalize preview endpoint is unchanged.

## 8. Scope exclusions

Not implemented:

- public persistence `POST /api/v1/job-descriptions`;
- Idempotency-Key or an idempotency table;
- Flyway V2;
- PUT, PATCH, DELETE, or If-Match;
- cleanup jobs;
- Dockerfile or Compose;
- image build/publication;
- FastAPI integration;
- Redis or application caching;
- full-text, fuzzy, or Elasticsearch search;
- release, deployment, or production access.

## 9. Dedicated database boundary

The Java service conceptually owns `jd_normalization`. Its environment
configuration is independent of the Personal Job Agent PostgreSQL database.
No SQLAlchemy table, Alembic migration, Python entity, or production database
credential is shared or accessed.

## 10. Database configuration

Supported environment values:

- `JD_NORMALIZATION_JDBC_URL`;
- `JD_NORMALIZATION_DB_USERNAME`;
- `JD_NORMALIZATION_DB_PASSWORD`;
- `JD_NORMALIZATION_FLYWAY_USERNAME`;
- `JD_NORMALIZATION_FLYWAY_PASSWORD`.

Runtime and migration roles can differ. There is no default password.
Hibernate uses UTC JDBC timestamps, `open-in-view=false`, and
`ddl-auto=validate`. Flyway uses validate-on-migrate, clean disabled,
baseline-on-migrate disabled, and the V1 location. SQL/bind logging and
database startup information that could contain a JDBC URL are disabled by
default.

Liveness contains only application liveness state. Readiness requires
readiness state, database health, both Phase 2A tables, and a successful V1
Flyway history row. Health bodies remain status-only.

## 11. Flyway version and migration

- Flyway: 11.7.2
- Migration version: `V1`
- File:
  `src/main/resources/db/migration/V1__create_job_description_schema.sql`

No V2 exists. After merge, V1 is append-only and must never be edited.

## 12. `job_descriptions` schema

The aggregate root stores:

- UUID primary key;
- optional normalized canonical URL;
- exact current version UUID;
- 32-byte current deduplication fingerprint;
- nonnegative optimistic lock version, default zero;
- UTC-aware created and updated timestamps.

The current pointer is verified by a deferred composite foreign key, not by an
unchecked application convention.

## 13. `job_description_versions` schema

Each immutable snapshot stores:

- UUID identity and owning aggregate UUID;
- positive version number;
- optional bounded title, company, and location;
- bounded nonblank normalized text;
- 32-byte content hash and deduplication fingerprint;
- bounded nonblank normalization-policy and dictionary versions;
- required, preferred, and mentioned skill JSONB arrays;
- UTC-aware creation timestamp.

## 14. Constraints and indexes

V1 includes:

- partial unique canonical URL;
- unique current deduplication fingerprint;
- unique aggregate/version number;
- unique version/owner/fingerprint identity;
- deferred owner and exact-current composite foreign keys;
- positive version and nonnegative lock checks;
- exact 32-byte hash/fingerprint checks;
- nonblank policy/dictionary checks;
- JSONB array and total skill-count checks;
- restricted, non-cascading deletes.

Indexes cover `(created_at DESC,id DESC)`, version history, content hash,
case-insensitive metadata fields, and the partial canonical URL uniqueness
path.

## 15. Immutable trigger

`trg_job_description_versions_immutable` calls
`reject_job_description_version_mutation()` before every UPDATE or DELETE and
raises SQLSTATE `55000`. Java also marks the entity `@Immutable` and exposes no
version save/delete repository method.

## 16. JPA mappings

`JobDescription` maps the root and uses `@Version` on
`optimistic_lock_version`. `JobDescriptionVersion` maps scalar owner/current
identities without a broad bidirectional graph or cascade. Both use UUID and
`Instant`; writes in future phases must supply application-generated UUIDv4
values. Hibernate schema generation is never used.

Current reads join root and exact current version in one statement. List
projection construction selects only summary fields. History reads issue one
bounded version query after one aggregate-existence query. There is no EAGER
collection or N+1 entity graph.

## 17. JSONB mapping

Skill snapshots use Hibernate-managed JSON through
`@JdbcTypeCode(SqlTypes.JSON)` and PostgreSQL `jsonb`. Each value contains only
canonical `id` and display `name`. No database skill-dictionary table was
added; `skills-v1.json` remains the versioned Git artifact.

## 18. Current-resource API

`GET /api/v1/job-descriptions/{id}`:

- parses UUID safely;
- authenticates before any resource disclosure;
- joins the root to its exact current version;
- returns normalized metadata/text, lowercase content hash, skills, policy
  versions, aggregate/version numbers, canonical URL, and timestamps;
- omits fingerprints, raw byte arrays, SQL details, and constraint names;
- returns `404 JOB_DESCRIPTION_NOT_FOUND` when absent.

## 19. List API

`GET /api/v1/job-descriptions`:

- default limit 20, allowed 1–100;
- `created_at_desc` default or `created_at_asc`;
- optional exact normalized title/company/location;
- optional exact lowercase SHA-256 content hash;
- optional normalized absolute-HTTPS canonical URL;
- summary rows only, with no normalized text or skill arrays;
- `limit + 1` fetch and no total count.

## 20. Version-history API

`GET /api/v1/job-descriptions/{id}/versions`:

- default limit 10, allowed 1–25;
- `version_desc` default or `version_asc`;
- keyset pagination by version number;
- committed immutable versions only;
- no mutation or deletion behavior;
- missing aggregate mapped to `JOB_DESCRIPTION_NOT_FOUND`.

## 21. ETag and conditional GET

The current endpoint returns a strong quoted decimal ETag based on
`optimistic_lock_version`, initially `"0"`. Exactly one valid strong
`If-None-Match` is accepted. A match returns 304 with no body. Malformed,
weak, comma-separated, or multiple values return safe `400 INVALID_REQUEST`.

## 22. Cursor format

List and history cursors are bounded, unpadded Base64URL encodings of
versioned JSON. A list cursor contains:

- cursor version;
- sort direction;
- last UTC timestamp;
- last UUID;
- SHA-256 fingerprint of normalized filters.

The history cursor contains cursor version, sort direction, and last version
number. Cursors contain no secret, credential, raw filter value, or
authorization meaning.

## 23. Keyset pagination

List pagination compares the tuple `(created_at,id)` in the requested
direction and orders by the same tuple, giving deterministic UUID tie order.
History compares `version_number`. `OFFSET` is never used. Cursor sort/filter
mismatch returns `400 INVALID_CURSOR`.

## 24. Error codes

Added codes:

- `JOB_DESCRIPTION_NOT_FOUND`;
- `INVALID_CURSOR`;
- `DATABASE_UNAVAILABLE`.

Existing stable codes remain. Every error has `code`, `message`, `request_id`,
and object-valued `details`. Connection failures return a bounded 503.
Unexpected data-access failures return safe `INTERNAL_ERROR`. Responses do not
include SQL, JDBC URL, database identity, exception text, entities,
credentials, content, metadata, or internal paths.

## 25. Test fixture strategy

There is no runtime seed. Test-only `PostgreSqlFixture` inserts deterministic
synthetic roots and versions inside transactions with deferred constraints.
No test row is loaded during normal startup. The fixture has no production
component annotation and is compiled only in test scope.

## 26. Flyway tests

`FlywaySchemaIT` verifies:

- fresh V1 migration;
- Flyway validation;
- second migrate executes zero migrations;
- successful Flyway history;
- Hibernate entity-manager startup/schema validation;
- safe startup failure when Flyway is disabled against an empty schema.

## 27. Constraint tests

Direct PostgreSQL assertions cover:

- required tables, constraints, trigger, and indexes;
- deferred atomic aggregate ownership;
- wrong-owner rejection;
- UPDATE and DELETE trigger rejection;
- restricted root deletion;
- canonical URL and current-fingerprint uniqueness;
- positive version, exact hash length, and JSONB array checks;
- permitted repeated content hash with different metadata/fingerprint.

## 28. Repository/service tests

PostgreSQL integration coverage verifies exact current projection, JSONB skill
mapping, exact filters, ascending/descending keysets, UUID tie order,
filter-bound cursor mismatch, version-history pagination, one bounded list
statement with zero entity fetches, and rollback without orphan rows.

`CursorCodecTest` separately verifies deterministic encoding, bounds, version,
sort/filter binding, URL/metadata normalization, and lowercase SHA-256 filter
validation.

## 29. MockMvc/API tests

Docker-free MockMvc tests cover:

- current response and strong ETag;
- 304 with empty body;
- malformed UUID and conditional header;
- authentication-before-disclosure;
- not found;
- bounded list/history responses and limits;
- invalid cursor;
- missing public POST returns stable 405;
- database-unavailable response without connection-detail leakage;
- OpenAPI read paths/security and absent write/Swagger UI.

All Phase 1 MockMvc, security, Request ID, normalization, payload, error,
Actuator, and OpenAPI regression tests continue to pass.

## 30. Query-plan evidence

`QueryPlanIT` seeds 65 aggregates plus bounded immutable history, runs
`ANALYZE`, and captures real `EXPLAIN (FORMAT JSON)` default planner output
for:

- current list keyset;
- version history;
- exact canonical URL;
- exact content hash.

Separate transaction-local `enable_seqscan=off` evidence proves index
eligibility. It is not used as the primary default-plan claim. The tests make
no latency threshold or production-performance claim.

The successful CI run recorded these real default planner results for the
small analyzed fixture:

| Query | Default planner result | Separate index-eligibility result |
|---|---|---|
| current keyset list | hash join with sequential scans and explicit sort | bitmap scan on `idx_job_descriptions_created_at_id` |
| version history | sequential scan and explicit sort | bitmap scan on `idx_job_description_versions_history` |
| canonical URL | sequential scan | index scan on `uq_job_descriptions_canonical_url` |
| content hash | sequential scan | index scan on `idx_job_description_versions_content_hash` |

The default sequential choices are expected for this deliberately small
fixture and are documented without being presented as a production plan.

## 31. Full Maven validation

Local environment:

- Eclipse Temurin 21.0.12;
- Maven Wrapper 3.9.16;
- `mvn test`: 53 tests initially, then 54 after the database-error case, all
  passing;
- targeted read/context/security tests: 11 passing;
- `mvn verify`: build passed locally; 15 PostgreSQL tests were explicitly
  skipped because the current user cannot access `/var/run/docker.sock`;
- test compilation of all `*IT`: passed;
- dependency tree inspection: passed;
- OpenAPI inspection through MockMvc: passed;
- `git diff --check`: passed.

The local skip is reported, not treated as PostgreSQL evidence. GitHub CI is
the authoritative Docker/Testcontainers validation.

## 32. GitHub CI

The Java workflow requires Docker, runs `./mvnw -B -ntp verify`, requires at
least three Failsafe XML reports, and rejects any skipped PostgreSQL IT.
Surefire/Failsafe reports upload only on failure.

During implementation, CI correctly caught test-configuration issues:
readiness contributor registration order and Testcontainers lifecycle for the
query-plan class, plus isolation of the missing-schema negative case. The
authoritative Java run
[#30416141242](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30416141242)
passed at `3c31474fb7d3bfe044ded3ff81d01eff8dba6e6e`:

- 54 Surefire tests, zero failures/errors/skips;
- 15 PostgreSQL 16.14 Failsafe tests, zero failures/errors/skips;
- Flyway V1 fresh migrate, validate, and no-op second migrate;
- Hibernate validation and isolated missing-schema startup failure;
- direct constraints, deferred ownership, immutable triggers, and rollback;
- read API, ETag, filters, keysets, version history, and query counts;
- four default/forced `EXPLAIN (FORMAT JSON)` evidence cases;
- Docker preflight and the no-skipped-IT gate.

The repository-wide PR run at the initial implementation head also passed all
ten existing jobs. Final documentation-head checks are recorded in the PR and
delivery response.

## 33. Changed files

The final PR is confined to:

- the Java service POM, README, environment example, configuration, Java
  runtime classes, V1 migration, and tests;
- the existing Java-only CI workflow;
- this Work Report and `docs/work-reports/README.md`.

No Backend, Frontend, Alembic, Compose, Nginx, Redis, Worker, Outbox, release,
backup, production version, deployment, or Project Knowledge file changed.

## 34. Commit SHAs

Implementation commits before this report:

- `06d763c17d61b2a6202c43980705fd2eba40cc77` —
  `feat(java): add PostgreSQL schema and JPA read model`
- `9e9c4bce799ff0b5de65e0c429edb687f5c50922` —
  `feat(java): add immutable Job Description read APIs`
- `3caa3f81bdfabd30a300c106c0c6e268d7110206` —
  `test(java): verify PostgreSQL read model with Testcontainers`
- `9fbd960a1c028c3f1e0be71a021b54899cfd49c9` —
  `fix(java): register schema readiness after database startup`
- `2dc9594331cf97ab8e49afac486c29ddd162e97a` —
  `test(java): isolate PostgreSQL constraint and plan fixtures`
- `4c0fef6b5ada0876569dfe3e47ec02aa9f42504a` —
  `test(java): isolate missing-schema startup validation`
- `3c31474fb7d3bfe044ded3ff81d01eff8dba6e6e` —
  `test(java): target isolated schema validation failure`

The commit containing this report cannot embed its own Git object ID because
doing so would change that ID.

## 35. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/27>

Title:

`Java: Add PostgreSQL read model and immutable JD versions`

The PR remains open and is not merged by this work.

## 36. Risks and limitations

- Phase 2A has no supported public population path.
- PostgreSQL is required for readiness and all read endpoints.
- Large but bounded version-history pages can still carry substantial text.
- Cursor JSON/version and Flyway V1 become compatibility commitments.
- Case-insensitive exact metadata behavior follows PostgreSQL `lower` under the
  database collation after application NFC/whitespace normalization.
- Query-plan evidence uses bounded synthetic data and does not predict
  production latency or every default planner choice.

## 37. Rollback

Before merge, close PR #27 and delete only the feature branch. After a
hypothetical merge, revert Java/config/workflow changes without editing merged
V1. Database reversal or schema correction requires a separately reviewed
forward migration; immutable version rows must not be mutated or deleted.

## 38. Confirmation that public create was not implemented

Confirmed. `POST /api/v1/job-descriptions` is absent and returns the stable
method-not-allowed envelope.

## 39. Confirmation that idempotency was not implemented

Confirmed. There is no Idempotency-Key handling, request-idempotency table,
idempotent persistence logic, or V2 migration.

## 40. Confirmation that update was not implemented

Confirmed. There is no PUT/PATCH, If-Match, optimistic update service, or
version mutation API.

## 41. Confirmation that Docker was not implemented

Confirmed. No Dockerfile, Compose change, image build, or image publication was
implemented. Docker is used only by CI/local tests to run PostgreSQL 16.14
Testcontainers.

## 42. Confirmation that FastAPI was untouched

Confirmed. No existing Backend/FastAPI file or integration was changed.

## 43. Confirmation that production was untouched

Confirmed. Production was not accessed, changed, released, tagged, deployed,
or synchronized. Production version metadata and `docs/PROJECT_KNOWLEDGE.md`
remain unchanged.

## 44. Confirmation that real DeepSeek was not called

Confirmed. No real DeepSeek or other LLM call was made by implementation,
tests, validation, or delivery.
