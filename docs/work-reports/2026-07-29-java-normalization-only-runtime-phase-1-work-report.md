# Java Normalization-Only Runtime Phase I Work Report

## 1. Repository

- Repository: `HKJoker-Z/personal-job-agent`
- Personal Job Agent production baseline: `2.0.4`
- Personal Job Agent Alembic head: `20260724_06`
- Java service: `services/jd-normalization-service`
- Implementation scope: approved integration-plan Phase I only

## 2. Audit PR final head

The documentation-only integration audit PR
[#31](https://github.com/HKJoker-Z/personal-job-agent/pull/31) was verified at
final head:

`f257960f0b60dee35391e93c920f09f367a73124`

The head contained the approved integration design, its audit Work Report, and
the Work Report index. All repository and Java checks passed. GitHub reported
the PR `CLEAN` and `MERGEABLE`, and its three-file diff was documentation-only.

## 3. Audit PR merge commit

PR #31 was merged without squash, rebase, or admin bypass using normal merge
commit:

`138059d37443eb2a67950d673955b19aee7f851c`

No tag, release, image publication, deployment, production access, or Project
Knowledge synchronization accompanied the merge.

## 4. Starting main commit

The Phase I branch started from post-merge `main` at:

`138059d37443eb2a67950d673955b19aee7f851c`

Local `main` and `origin/main` matched. Post-merge main CI run
`30508697129` completed successfully before the Phase I branch was created.

## 5. Phase I branch

`feat/java-normalization-only-runtime`

## 6. Exact scope

Phase I adds one exact Spring profile, `normalization-only`, to the existing
Java JD Normalization Service. It:

- runs the existing deterministic normalize endpoint without a database;
- retains internal Bearer authentication, Request ID, stable errors, health,
  JSON OpenAPI, and disabled-CORS behavior;
- removes persistence routes and persistence/database beans from that profile;
- adds a focused profile integration test;
- adds a no-database application-container smoke;
- extends Java-specific CI; and
- documents the runtime and its evidence.

## 7. Scope exclusions

This work does not change:

- FastAPI or any backend Python file;
- React;
- Personal Job Agent PostgreSQL, Alembic, Redis, Worker, or Outbox;
- Nginx, root production Compose, production scripts/configuration, release
  workflows, or version metadata;
- Java normalization policy or skill-dictionary contents; or
- Project Knowledge.

It does not implement FastAPI integration, local/shadow/java selection,
Java-authoritative Analyze, execution fingerprints, candidate deployment, or
production rollout.

## 8. Profile configuration

`application-normalization-only.yml` sets:

- `jd-normalization.persistence.enabled=false`;
- `jd-normalization.schema-health.enabled=false`;
- `spring.flyway.enabled=false`;
- `management.health.db.enabled=false`; and
- readiness membership to `readinessState,normalizationReadiness`.

The base/default configuration is unchanged. No database property is replaced
with an embedded or dummy database.

## 9. Excluded auto-configurations

The Spring Boot `3.5.16` application and actuator auto-configuration JARs were
inspected directly. The profile excludes these actual classes:

- `org.springframework.boot.autoconfigure.data.jpa.JpaRepositoriesAutoConfiguration`
- `org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.DataSourceTransactionManagerAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.JdbcClientAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.JndiDataSourceAutoConfiguration`
- `org.springframework.boot.autoconfigure.jdbc.XADataSourceAutoConfiguration`
- `org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration`
- `org.springframework.boot.autoconfigure.sql.init.SqlInitializationAutoConfiguration`
- `org.springframework.boot.autoconfigure.transaction.TransactionAutoConfiguration`
- `org.springframework.boot.autoconfigure.transaction.TransactionManagerCustomizationAutoConfiguration`
- `org.springframework.boot.actuate.autoconfigure.jdbc.DataSourceHealthContributorAutoConfiguration`

Persistence dependencies remain in the POM and the same executable JAR. No
Maven module split or alternate application image was introduced.

## 10. Conditional persistence components

The existing property guards already covered persistence controllers, schema
health, JDBC repositories, and create/read/update services. Phase I also
guards the remaining persistence helper components:

- `CreateFingerprints`; and
- `CursorCodec`.

Persistence-specific exception and database-failure mappings moved from the
shared normalize advice to property-guarded
`PersistenceApiExceptionHandler`. The shared normalization/request error
advice remains active in both profiles. Full-profile exception precedence is
explicit and its existing tests pass.

JPA entities remain ordinary classes in the JAR but are not managed or
instantiated because JPA/Hibernate and repository auto-configuration are
excluded.

## 11. Database/JPA/Flyway bean absence

`NormalizationOnlyProfileIT` verifies absence of:

- `DataSource`;
- `JdbcTemplate`;
- `EntityManagerFactory`;
- Hibernate `SessionFactory`;
- `PlatformTransactionManager`;
- `Flyway`;
- both JPA repository interfaces;
- persistence entities as Spring beans;
- create/read/update repositories, services, helpers, and controllers;
- persistence exception advice;
- schema readiness; and
- database health contribution.

It also checks the standard `dataSource`, `entityManagerFactory`,
`transactionManager`, `flyway`, `flywayInitializer`, `dbHealthContributor`,
and `schemaReadiness` bean names are absent. A second bounded context supplies
an impossible documentation-range PostgreSQL address and dummy values;
startup succeeds with the same bean absence and without a connection attempt.

## 12. Active routes

The active product route is exactly:

`POST /api/v1/job-descriptions/normalize`

The following health routes remain unauthenticated and status-only:

- `/actuator/health`
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Protected JSON OpenAPI remains at `/v3/api-docs`.

## 13. Inactive persistence routes

With a valid internal API key, each route returns the existing
`ROUTE_NOT_FOUND` envelope:

- `POST /api/v1/job-descriptions`
- `GET /api/v1/job-descriptions`
- `GET /api/v1/job-descriptions/{id}`
- `GET /api/v1/job-descriptions/{id}/versions`
- `PUT /api/v1/job-descriptions/{id}`

No replacement endpoint or "persistence disabled" API was added.

## 14. Normalize contract regression

The implementation does not modify normalize production code, DTOs, bounds,
policy, dictionary, or dictionary artifact. Tests preserve:

- the request and response shape;
- UTF-8/body and Unicode code-point bounds;
- NFC/line/whitespace normalization;
- deterministic SHA-256 content hashing;
- `jd-normalization-v1`;
- `skills-v1`;
- deterministic required/preferred/mentioned skill extraction;
- metadata normalization; and
- no persistence, external HTTP call, or LLM use.

All pre-existing normalization tests pass.

## 15. Authentication

`normalization-only` retains the internal Bearer API key. Tests prove:

- unauthenticated normalize returns stable HTTP 401;
- `/api/v1/**` and `/v3/api-docs` remain protected;
- missing and short keys fail startup outside `dev`;
- setting authentication disabled under `normalization-only` fails startup;
  and
- the existing exception remains limited to the exact `dev` profile and
  loopback binding.

Health remains unauthenticated. CORS and browser-session authentication remain
disabled.

## 16. Request ID

Tests prove:

- an absent `X-Request-ID` produces a UUIDv4 response ID;
- a valid supplied ID is preserved;
- success and error responses retain the header; and
- the container smoke verifies propagation without logging the Authorization
  header, API key, or full body.

## 17. Error contract

Unauthorized, validation, inactive-route, invalid-OpenAPI-format, and Swagger
UI checks retain the bounded JSON error envelope:

```text
error.code
error.message
error.request_id
error.details
```

The unauthorized response does not echo raw JD input or the API key.
Persistence exception behavior is unchanged in the full profile.

## 18. OpenAPI

Under `normalization-only`:

- unauthenticated `/v3/api-docs` returns 401;
- authenticated JSON OpenAPI contains only
  `/api/v1/job-descriptions/normalize`;
- the operation documents Request ID, Bearer security, and stable errors;
- persistence routes are absent;
- Swagger UI is absent; and
- YAML OpenAPI is absent.

Existing full-profile MockMvc coverage confirms the normalize, create, read,
version-history, and update product routes remain documented there.

## 19. Liveness

The liveness group remains `livenessState` only. It reports the
JVM/application-process state and returns only:

```json
{"status":"UP"}
```

It has no database, Flyway, schema, JPA, or repository member.

## 20. Readiness

`NormalizationReadinessHealthIndicator`, active only under
`normalization-only`, is constructed from the normalize capability and the
successfully loaded `SkillDictionary`. It reports UP only when the expected
`skills-v1` dictionary is loaded with entries.

The readiness group combines it with Spring `readinessState`. Configuration
and security validation fail application startup before readiness can become
UP. Database/schema members remain unchanged in the full profile and are not
weakened.

## 21. Docker/runtime behavior

The existing Dockerfile, application target, executable JAR, numeric
`10001:10001` user, port `8080`, and stdout/stderr logging are reused.

The focused smoke starts the application with:

`SPRING_PROFILES_ACTIVE=normalization-only`

It starts one Java container, supplies a generated test key without printing
it, supplies no database environment, uses a unique isolated bridge and an
ephemeral loopback-only host port, and starts no PostgreSQL or migration
container. The container uses a read-only root filesystem, all capabilities
dropped, `no-new-privileges`, and bounded `/tmp`. No production Compose file
was added.

## 22. Resource-limit validation

The focused smoke enforced:

- 0.50 CPU;
- 384 MiB memory;
- memory-plus-swap ceiling equal to 384 MiB;
- 128 PIDs;
- JVM `-Xms64m -Xmx256m`; and
- 64 MiB noexec/nosuid/nodev `/tmp`.

Final local evidence:

- application image:
  `sha256:9f25e07b3a00a2430be755eb6d6d33fb1b94db0becaf3f16afeadef68c811ef9`;
- health: `healthy`;
- restart count: `0`;
- OOM killed: `false`; and
- point-in-time memory: `198.1MiB / 384MiB`.

This is one bounded local observation, not production sizing, performance,
high-availability, sustained-memory, or host-swap evidence.

## 23. Normalization-only integration tests

`NormalizationOnlyProfileIT` contains nine passing tests covering:

- context startup and database environment absence;
- database/JPA/Flyway/persistence bean absence;
- ignored impossible dummy database settings and no connection attempt;
- API-key startup validation and bypass rejection;
- successful normalize and deterministic versions/skills;
- unauthorized behavior and leakage rejection;
- generated/preserved Request IDs and stable validation errors;
- status-only health;
- authenticated persistence-route absence;
- normalize-only protected JSON OpenAPI, absent Swagger/YAML; and
- disabled CORS.

Result: 9 tests, 0 failures, 0 errors, 0 skipped.

## 24. Full-profile PostgreSQL regression

All seven existing PostgreSQL 16.14 Testcontainers classes ran:

- `FlywaySchemaIT`: 8 tests;
- `PostgreSqlCreateApiIT`: 5 tests;
- `PostgreSqlIdempotencyConcurrencyIT`: 7 tests;
- `PostgreSqlReadApiIT`: 5 tests;
- `PostgreSqlUpdateApiIT`: 5 tests;
- `PostgreSqlUpdateConcurrencyIT`: 3 tests; and
- `QueryPlanIT`: 4 tests.

They preserve Flyway V1/V2, Hibernate validation, create/replay,
idempotency/concurrency, reads, ETag, conditional PUT, immutable versions,
keyset pagination, constraints, query plans, and cleanup.

## 25. Full-profile container smoke

The unchanged `scripts/container-smoke.sh --ephemeral .env.compose` passed:

- application image:
  `sha256:b474c3d20006d15a56788b3bfac31a1f0ab88bfb0f7bc866c59c626b1323b19f`;
- migration image:
  `sha256:7ee986919fd53409e66f3ecca2dbe9bf0cd44fa134c4d8ce8c6838ed6ccd56c7`;
- application/PostgreSQL health: healthy;
- application/PostgreSQL automatic restart counts: zero;
- successful normalize, create, exact replay, conditional update, stale
  rejection, read, history, restart persistence, and database restart;
- exactly Flyway V1/V2; and
- successful no-op migration rerun and validation.

## 26. No-database container smoke

`scripts/normalization-only-container-smoke.sh --ephemeral` passed. It:

- built only the existing application target;
- started only the Java container;
- supplied no JDBC URL, database username/password, or Flyway credential;
- waited for status-only readiness and liveness;
- rejected unauthenticated normalize;
- completed authenticated normalize;
- preserved the supplied Request ID;
- returned safe 404 for a persistence route;
- exposed normalize-only protected JSON OpenAPI;
- kept Swagger UI and CORS absent;
- verified non-root/read-only/capability/tmpfs/resource configuration;
- verified healthy, zero restart, and no OOM state;
- found no API key or synthetic raw marker in logs/image metadata/history;
- found no database/JPA/Flyway connection-attempt signature in logs; and
- removed only its uniquely named container and network.

## 27. Maven result

Both requested `./mvnw -B -ntp verify` and a clean verification passed.

Clean result:

- Surefire: 67 tests, 0 failures, 0 errors, 0 skipped;
- Failsafe: 46 tests, 0 failures, 0 errors, 0 skipped; and
- Maven: `BUILD SUCCESS`.

Targeted normalization-only execution also passed.

## 28. PostgreSQL integration-test result

The seven PostgreSQL classes contributed 37 tests:

- 37 tests;
- 0 failures;
- 0 errors; and
- 0 skipped.

The CI workflow still explicitly rejects a missing report or any skipped
PostgreSQL integration test. PostgreSQL image version remains `16.14`.

Flyway checks and local file SHA-256 values:

- V1:
  `b73ecefbb610b06059a8e3c067f2fc874aab4e586e397739aad378aa78abcb40`;
- V2:
  `30bf80257a4fedfd4c125ef08adca94a840a018bba8f1d78cb1843fed55f8f7f`.

No migration file changed.

## 29. GitHub CI

PR #32 extends Java CI with:

- full Maven verify;
- explicit profile-integration report enforcement;
- seven PostgreSQL report/zero-skip enforcement;
- runtime dependency inspection and H2 rejection;
- the unchanged full-profile container smoke;
- the new normalization-only no-database smoke;
- OpenAPI/auth/health/runtime/resource/log/image inspection;
- patch whitespace, tracked-output, and secret checks; and
- immutable action pins and read-only contents permission.

The first draft head correctly exposed an over-broad existing source-secret
pattern matching safe runtime interpolation. Commit `28675ca` changed the
smoke to export the generated key without a source assignment and kept the
source scanner effective. The same scanner, shell syntax, ShellCheck, and
focused smoke pass locally. Fresh GitHub checks run on every pushed head; the
final authoritative status is the PR check rollup and final delivery record.

No workflow uses `pull_request_target`, registry login, publication, release,
deployment, or production credentials.

## 30. Changed files

Implementation and Java CI:

- `.github/workflows/jd-normalization-service-ci.yml`
- `services/jd-normalization-service/scripts/normalization-only-container-smoke.sh`
- `services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/config/NormalizationReadinessHealthIndicator.java`
- `services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/persistence/create/CreateFingerprints.java`
- `services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/persistence/read/CursorCodec.java`
- `services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/web/ApiExceptionHandler.java`
- `services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/web/PersistenceApiExceptionHandler.java`
- `services/jd-normalization-service/src/main/resources/application-normalization-only.yml`
- `services/jd-normalization-service/src/test/java/io/github/hkjokerz/jobagent/jdnormalization/NormalizationOnlyProfileIT.java`

Documentation:

- `services/jd-normalization-service/README.md`
- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/2026-07-29-java-normalization-only-runtime-phase-1-work-report.md`
- `docs/work-reports/README.md`

## 31. Commit SHAs

- `ef73a7b63579e4ad1f53222cb3168d8cd71bffb1` — add the stateless
  normalization-only Spring profile and integration tests.
- `65e512d7640b62dc083904dc99e65f35114d3904` — add the no-database
  container smoke and CI validation.
- `28675ca` — harden smoke secret injection against source leakage and the
  repository scanner.

The documentation/Work Report commit follows these implementation commits.
It cannot self-embed its own SHA; Git history and the PR commit list are the
authoritative delivery record.

## 32. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/32>

Title: `Java: Add stateless normalization-only runtime`

The PR is intentionally not merged by this work.

## 33. Risks and limitations

- Persistence libraries remain in the same JAR, although context and
  container evidence prove they are inactive under this profile.
- The application-level profile property is essential; removal or misspelling
  would return to default/full startup and require database configuration.
- The provisional 384 MiB ceiling has only bounded local/CI-smoke evidence.
- One point-in-time memory reading is not production sizing or load evidence.
- The focused validation uses a loopback port and isolated bridge for testing;
  a later production design must use the reviewed private-only topology and no
  host publication.
- There is no FastAPI client, fallback, shadow comparison, candidate, rollout,
  or production evidence in Phase I.

## 34. Rollback

Before merge, close PR #32 or revert its commits. After a future merge, do not
activate `normalization-only`, or revert the Phase I merge commit. The
unchanged default/full profile remains available.

No database downgrade, Alembic action, Flyway undo, data migration, FastAPI
mode change, image rollback, release rollback, or production action is
required because none occurred.

## 35. Confirmation that FastAPI was untouched

Confirmed. No FastAPI/backend Python file or FastAPI configuration changed.

## 36. Confirmation that no PostgreSQL was required in normalization-only mode

Confirmed. Both the profile context and application-container smoke started
and became ready without a PostgreSQL container, JDBC URL, database
credentials, Flyway credentials, or database network member.

PostgreSQL was used only for the separately preserved full-profile regression
tests and full-profile smoke.

## 37. Confirmation that no Flyway migration was added or modified

Confirmed. V1 and V2 are byte-unchanged, their checksum/validation tests pass,
and no V3 was created.

## 38. Confirmation that no image was published

Confirmed. Images were built only in the local Docker daemon and CI smoke
environments. There was no registry login, push, or publication.

## 39. Confirmation that no release or deployment occurred

Confirmed. No tag, GitHub release, artifact publication, deployment,
production Compose action, or environment rollout occurred.

## 40. Confirmation that production was untouched

Confirmed. No production host, container, service, network, secret,
configuration, database, data, or Project Knowledge was accessed or modified.

## 41. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Tests and smokes used synthetic JD data and called no DeepSeek,
other external LLM, or external normalization service.
