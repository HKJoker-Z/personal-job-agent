# Java JD Normalization Service Phase 3B Containerization Work Report

## 1. Repository

- Repository: <https://github.com/HKJoker-Z/personal-job-agent>
- Stable Personal Job Agent production version at start: `2.0.4`
- Personal Job Agent Alembic head at start: `20260724_06`
- Independent Java service: `services/jd-normalization-service/`

This report covers only the independently isolated Phase 3B container
environment. The Personal Job Agent production application remains a separate
system.

## 2. Phase 3A PR final head

Phase 3A PR #29 ended at:

`19881b0605c42030b6fe6e006ded68bb22801c2d`

The final head contained the mandatory Phase 3A Work Report. Its final Java
workflow passed with all 37 PostgreSQL integration tests executed and zero
failures, errors, or skips. Every repository-required check passed, the PR was
CLEAN and MERGEABLE, V1 and V2 retained their reviewed checksums, and no
Docker, Compose, FastAPI integration, publication, release, or deployment was
added after the report.

## 3. Phase 3A merge commit

PR #29 was merged with a normal merge commit, without squash, rebase, admin
bypass, tag, publication, release, or deployment:

`52e60f41506a98175f0f1f9cd2028205b6768e28`

Post-merge Java workflow run `30446490070` passed. Repository CI run
`30446491742`, including all required jobs and the existing repository Docker
smoke, also passed. Local `main` and `origin/main` both resolved to the merge
commit before Phase 3B began.

## 4. Starting main commit

Phase 3B started from:

`52e60f41506a98175f0f1f9cd2028205b6768e28`

## 5. Phase 3B branch

`feat/java-jd-normalization-service-phase-3b-containerization`

## 6. Exact scope

Implemented only:

- pinned multi-stage application and migration images;
- an independent service-local Compose environment;
- dedicated PostgreSQL 16.14 and a named volume;
- a one-shot Flyway V1/V2 migrate-and-validate service;
- health-gated PostgreSQL, migration, and application startup ordering;
- generated ignored local-only secrets and distinct database roles;
- non-root/read-only application execution and focused container hardening;
- a bounded synthetic API, restart, persistence, migration-rerun, health,
  inspection, and history smoke test;
- a Java CI container job;
- the Java README, Work Report index, and this Work Report.

All existing normalize, create/replay, read, conditional update, ETag,
pagination, and immutable-history APIs remain unchanged.

## 7. Scope exclusions

Not implemented:

- a new product API, PATCH, DELETE, or Flyway migration;
- FastAPI, React, Personal Job Agent PostgreSQL, Alembic, Redis, Dramatiq,
  Worker, Outbox, Nginx, or root production Compose integration;
- public reverse proxy, TLS, DNS, Kubernetes, k3s, cache, or queue;
- external provider, DeepSeek, or other LLM call;
- registry login, image publication, tag, GitHub Release, deployment,
  production access, or production metadata change.

`docs/PROJECT_KNOWLEDGE.md`, root production Compose, production backup and
deployment scripts, and production release workflows were not changed.

## 8. Dockerfile design

One service-local multi-stage `Dockerfile` defines `builder`, `application`,
and `migration` stages. The build context is deny-by-default through
`.dockerignore` and includes only the Maven Wrapper, POM, source tree, two
migrations, and migration helper required by those targets. Git metadata,
environment files, reports, documentation, and the rest of the repository are
not sent.

OCI source and revision labels accept non-secret build arguments. No ARG,
ENV, layer, certificate, credential, or configuration file contains a secret
default.

## 9. Builder image

The builder uses pinned Eclipse Temurin Java 21 JDK on Ubuntu 22.04:

`eclipse-temurin:21-jdk-jammy@sha256:9d8dcf999b0bce2453e913823595a5ff2a4e8e9e5d5241b45280d0ff069818ec`

It invokes the repository Maven Wrapper noninteractively with
`-Dmaven.test.skip=true package`; tests run separately before the container
job. Normal dependency resolution is the only required build-time network
access. No production credential is required.

## 10. Runtime image

The application target uses pinned Eclipse Temurin Java 21 JRE on Ubuntu
22.04:

`eclipse-temurin:21-jre-jammy@sha256:d63bd8d9b171999cbed8576f2c76e874dd4856791a358536e5c4d407e77edc13`

It copies only the executable application JAR into
`/opt/jd-normalization/application.jar`, exposes only 8080, logs to
stdout/stderr, and uses an exec-form Java entrypoint. The verified runtime
`curl` client supplies a readiness health check.

## 11. Migration image

The migration target uses:

`flyway/flyway:11.7.2-alpine@sha256:a493a5ef0700f6d1ef4f7b83320f79601071b20749c2eca1d73dd2e352948656`

It contains exactly V1, V2, and a fixed helper that runs `flyway migrate`
followed by `flyway validate`. Clean remains disabled, baseline-on-migrate is
false, and a validation failure returns nonzero. It runs as numeric user
`10002:10002`.

## 12. Base-image digests

All four external runtime/build references are immutable:

- builder:
  `sha256:9d8dcf999b0bce2453e913823595a5ff2a4e8e9e5d5241b45280d0ff069818ec`;
- runtime:
  `sha256:d63bd8d9b171999cbed8576f2c76e874dd4856791a358536e5c4d407e77edc13`;
- migration:
  `sha256:a493a5ef0700f6d1ef4f7b83320f79601071b20749c2eca1d73dd2e352948656`;
- PostgreSQL 16.14 Bookworm:
  `sha256:92620daddcd947f8d5ab5ba66e848702fe443d87fed30c4cea8e389fd78dfc55`.

Registry manifests were inspected for exact version and Linux amd64/arm64
support. The selected Java 21 and PostgreSQL 16 lines are maintained upstream
release lines at implementation time.

## 13. Application artifact

The image contains
`jd-normalization-service-0.1.0-SNAPSHOT.jar`, renamed to
`/opt/jd-normalization/application.jar`. Inspection found one regular file in
the application work directory and no source, tests, compiler, Maven
repository, test report, `.git`, or environment file in the final target.

## 14. Non-root runtime

The Dockerfile creates and selects the dedicated numeric application user
`10001:10001`. Compose repeats that identity explicitly. Image and running
container inspection both proved PID 1 executes as this non-root identity.

## 15. Read-only filesystem

The application runs with `read_only: true`; only a 64 MiB `/tmp` tmpfs is
writable for JVM temporary data. Compose also drops every Linux capability,
sets `no-new-privileges:true`, disables privileged/host networking by design,
mounts no host path or Docker socket, and applies bounded CPU, memory, PID,
stop, and init settings. The full API and health smoke passed under these
restrictions.

PostgreSQL intentionally retains its required writable named data volume and
is not forced into an unsafe read-only-root configuration.

## 16. Compose services

`compose.yml` defines only:

1. `postgres`, dedicated PostgreSQL 16.14;
2. `migration`, the one-shot Flyway target;
3. `app`, the existing Java API.

The project name defaults to `jd-normalization-local`. The smoke overrides it
with a unique, validated `jd-normalization-smoke-*` name. No production
service, network, container name, or environment file is reused.

## 17. Network and port isolation

PostgreSQL and migration attach only to an internal project-scoped `backend`
network. The application also attaches to a project-scoped `edge` bridge so
Docker can publish exactly `127.0.0.1:18082:8080` by default. PostgreSQL and
migration publish no host port. There is no host network, public port 8080,
`pja-br0`, Nginx, reverse proxy, or production network attachment.

## 18. PostgreSQL volume

PostgreSQL stores its dedicated synthetic database in the project-scoped
`postgres-data` named volume. The smoke proved the rows survive application
restart and PostgreSQL container stop/start. Normal `compose down` preserves
the volume. Only the explicit `--ephemeral` smoke trap deletes its exact
unique project and volume; no broad prune or unrelated-volume deletion is
used.

## 19. Secret handling

`.env.compose.example` contains placeholders only. The generator creates
ignored `.env.compose` mode `0600` with a 64-hex-character internal API key and
separate generated bootstrap, migration, and runtime database passwords. Role
names use a bounded identifier grammar and the roles must be distinct.

The initialization script creates non-superuser migrator and runtime roles.
The application receives only runtime credentials. Scripts validate values
without printing them, failure logs are bounded and redacted, and no real
Personal Job Agent or production secret was used.

## 20. Migration startup ordering

Compose uses:

1. PostgreSQL `service_healthy`;
2. migration `service_completed_successfully`;
3. application image readiness health.

There is no arbitrary startup sleep. The migration service is the only schema
owner in this runtime; application Flyway is disabled and Hibernate remains
`ddl-auto=validate`. Multiple application containers therefore do not race to
migrate.

Neither append-only migration changed:

- V1 SHA-256:
  `b73ecefbb610b06059a8e3c067f2fc874aab4e586e397739aad378aa78abcb40`;
- V2 SHA-256:
  `30bf80257a4fedfd4c125ef08adca94a840a018bba8f1d78cb1843fed55f8f7f`.

No V3 was created; Flyway head remains V2.

## 21. Health behavior

The image and Compose application health check use
`/actuator/health/readiness`. Both readiness and
`/actuator/health/liveness` returned status-only `{"status":"UP"}` after
startup. During a controlled PostgreSQL outage readiness stopped returning
200 while liveness remained status-only 200, so database unavailability was
not misrepresented as a dead JVM. Readiness recovered after PostgreSQL
restart without restarting the application.

## 22. Smoke-test flow

`scripts/container-smoke.sh` uses `set -euo pipefail`, validated inputs, safe
quoting, unique project/volume names, bounded HTTP and health waits, synthetic
payloads, database synchronization, a cleanup trap, and sanitized failure
logs. It:

- validates/builds/inspects both images and Compose;
- migrates, starts, and probes the service;
- exercises authentication, normalize, create/replay, GET, PUT/stale PUT,
  and history;
- restarts the application and PostgreSQL;
- reruns migration and validates persistent data;
- checks container content, history, users, health, restart counts, mounts,
  networks, capabilities, root-filesystem mode, and loopback publication.

## 23. Normalize result

An unauthenticated normalize request returned 401. The same bounded synthetic
request with the generated internal key returned 200 and
`jd-normalization-v1`. No external provider or LLM was contacted.

## 24. Create and replay result

The first keyed synthetic create returned 201 with Location and ETag `"0"`.
The same request/key replayed the identical status, body, Location, and ETag
and added `Idempotency-Replayed: true`. Direct PostgreSQL counts proved one
root and one version only.

## 25. PUT and stale-update result

One full replacement with `If-Match: "0"` returned 200 and advanced the ETag
to `"1"`. Reusing stale `"0"` returned 412. The GET after update matched the
new current representation.

## 26. Version-history result

The authenticated history endpoint returned exactly immutable versions 1 and
2 in deterministic descending order. PostgreSQL counts likewise showed two
versions and no orphan row.

## 27. Restart persistence result

Restarting only the application container preserved the created/updated
resource. Stopping and starting PostgreSQL preserved the same data through
the named volume, and the still-running application recovered readiness and
returned the resource.

## 28. Migration rerun result

Rerunning the one-shot migration reported the schema already at V2, executed
no new migration, and validated both migrations. The schema-history success
count remained exactly two.

## 29. Container health and restart counts

At final inspection:

- application: `healthy`, automatic restart count `0`;
- PostgreSQL: `healthy`, automatic restart count `0`;
- migration: exited `0`.

The deliberate `compose restart app` does not increment Docker's automatic
restart counter.

## 30. Application image ID/digest

The final local validation image identifier, built without publishing, is:

`sha256:2fe2dffd99fe63b7c90a5a2d56c9b9cbec157d3887207e155a797693c96f12bc`

It was built from the application target with OCI source and the tested
repository implementation revision
`02735bb7a0911b8a9075dc6de4ee48d5b353cc3f`.

## 31. Migration image ID/digest

The final local validation migration image identifier, built without
publishing, is:

`sha256:f5e2f9da8790040762e4341766056a157173f731f43aa9975c676ee4f6485d60`

Application and migration targets used the same implementation revision
`02735bb7a0911b8a9075dc6de4ee48d5b353cc3f`.

## 32. Image inspection

Inspection proved:

- numeric image users `10001:10001` and `10002:10002`;
- application exec entrypoint, readiness health command, and exposed 8080;
- migration fixed entrypoint and exactly V1/V2 with matching host hashes;
- application runtime contains no source, Maven, compiler, tests, `.git`,
  `.env`, or Maven repository;
- OCI source/revision labels contain no secret;
- running application is read-only, non-root, tmpfs-backed, capability-free,
  no-new-privileges, and loopback-only;
- PostgreSQL has one named volume and no published port.

Dockerfile BuildKit `--check` completed for both targets with no warnings.

## 33. Image-history secret scan

Full untruncated history and image configuration for both targets were
searched for every generated local secret. No match occurred. Dockerfile
defaults and OCI labels were also checked; no API key, password, certificate,
production configuration, or environment file is embedded.

## 34. Maven tests

`./mvnw -B -ntp verify` completed successfully:

- 67 unit and MockMvc tests;
- 37 PostgreSQL integration tests;
- zero failures, errors, or skips;
- PostgreSQL Testcontainers image `postgres:16.14`.

Normalization, API-key authentication, request IDs, stable errors, read
model, ETag/304, pagination, immutable versions, create/replay, duplicates,
PUT/no-op/stale update, concurrency, Flyway, and Hibernate validation remained
green.

## 35. PostgreSQL tests

All seven required Failsafe report classes ran against PostgreSQL 16.14:

- `FlywaySchemaIT`;
- `PostgreSqlCreateApiIT`;
- `PostgreSqlIdempotencyConcurrencyIT`;
- `PostgreSqlReadApiIT`;
- `PostgreSqlUpdateApiIT`;
- `PostgreSqlUpdateConcurrencyIT`;
- `QueryPlanIT`.

The aggregate result was 37 tests and zero skips. No H2 or production database
was used. V1/V2 fresh migration, V1-to-V2 upgrade, validation, no-op rerun,
checksums, and Hibernate schema validation remain covered.

## 36. Container tests

Passed:

- Dockerfile parser/BuildKit checks;
- clean-context application and migration builds;
- Compose config validation;
- complete ephemeral container smoke;
- migration success and no-op rerun;
- non-root/read-only/tmpfs/security inspection;
- status-only liveness/readiness and outage differentiation;
- create/replay, read, conditional update, stale update, history;
- application and PostgreSQL restart persistence;
- bounded image-content, label, history, and secret scans;
- exact isolated project/volume teardown.

## 37. GitHub CI

PR #30 runs the existing full Maven/PostgreSQL `verify` job and a new bounded
`container-smoke` job after it. The container job validates all shell scripts
and Compose configuration, generates CI-only secrets, builds both local
targets, performs the full ephemeral smoke, and removes only its unique
project and volume.

The workflow has read-only repository permission, concurrency cancellation, a
25-minute container timeout, immutable third-party action SHAs, no
`pull_request_target`, no registry login, no publication, no release, no
deployment, and no production credential. The repository-safety allowlist was
extended narrowly for the mandated tracked `.env.compose.example`; actual
`.env.compose` remains rejected and ignored. Final documentation-head check
results are authoritative on the PR and in the delivery response.

## 38. Changed files

Container implementation:

- `services/jd-normalization-service/Dockerfile`;
- `services/jd-normalization-service/.dockerignore`;
- `services/jd-normalization-service/compose.yml`;
- `services/jd-normalization-service/.env.compose.example`;
- `services/jd-normalization-service/.gitignore`;
- `services/jd-normalization-service/docker/migrate-and-validate.sh`;
- `services/jd-normalization-service/docker/postgres-init.sh`;
- `services/jd-normalization-service/scripts/generate-compose-env.sh`;
- `services/jd-normalization-service/scripts/container-smoke.sh`.

CI and documentation:

- `.github/workflows/jd-normalization-service-ci.yml`;
- `.github/workflows/ci.yml` (repository-safety template allowlist only);
- `services/jd-normalization-service/README.md`;
- `docs/work-reports/README.md`;
- this report.

No API implementation, migration, Backend/FastAPI, Frontend/React, root
Compose, Alembic, Redis, worker, Nginx, release, deployment, production
metadata, or Project Knowledge file changed.

## 39. Commit SHAs

Implementation commits before this report:

- `af9a839313bd250e7f9a4980be6fefece583e8f5` —
  `Add Java application and migration container images`;
- `2a5747ad5b906630dcc2d06cf0f7995212f5d302` —
  `Add isolated Compose environment and container smoke`;
- `308c8e617d99f065daaaaa0510f4e0c5dcaad982` —
  `Extend Java CI with container validation`;
- `02735bb7a0911b8a9075dc6de4ee48d5b353cc3f` —
  `Harden container input validation`;
- `ad8bc497175dcda6c4a792c5fd82a57b56007dec` —
  `Document Java Phase 3B containerization`;
- `8903c7dde8bfbb72e85f71f8ffd04db9b6bf0641` —
  `Allow service Compose environment template`.

The documentation commit containing this report cannot embed its own Git
object ID because doing so would change that ID.

## 40. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/30>

Title:

`Java: Containerize the JD normalization service`

The PR remains open and must not be merged by Phase 3B delivery.

## 41. Risks and limitations

- This is a single-node local/CI environment, not production or high
  availability.
- A clean build needs network access for pinned base retrieval and Maven
  dependency resolution.
- PostgreSQL availability remains required for readiness and all persistent
  APIs.
- Local operators remain responsible for protecting `.env.compose` and
  confirming exact project scope before deleting a synthetic volume.
- The runtime base includes a verified health client, increasing the image
  surface compared with a distroless JRE.
- Separate local credentials demonstrate the privilege boundary, but this
  phase does not implement a production secret manager or credential rotation.
- No public reverse proxy, TLS, multi-tenant authentication, orchestration, or
  deployment is claimed.

## 42. Rollback

Before merge, close PR #30 and delete only the Phase 3B feature branch. After
a hypothetical merge, revert the seven Phase 3B commits. No database downgrade
or migration rollback is required because V1/V2 were unchanged and no V3 was
added.

For local synthetic state, first verify the exact isolated Compose project.
Normal `compose down` preserves data; an explicitly chosen project-scoped
volume removal may delete only that local volume. Never prune broad Docker
state or remove an unrelated/production volume.

## 43. Confirmation that FastAPI was untouched

Confirmed. No Backend/FastAPI code, configuration, database, Alembic
migration, HTTP integration, or production application wiring was changed.

## 44. Confirmation that production Compose was untouched

Confirmed. The repository-root production Compose file, its networks,
containers, volumes, ports, and environment files were not modified or used.

## 45. Confirmation that no image was published

Confirmed. Both images exist only in the local Docker engine and ephemeral CI
engines. No registry login, push, package, artifact publication, or image
release occurred.

## 46. Confirmation that no release or deployment occurred

Confirmed. No tag, GitHub Release, image publication, release workflow,
deployment workflow, server operation, or external environment change
occurred.

## 47. Confirmation that production was untouched

Confirmed. Production was not accessed, changed, synchronized, backed up,
tagged, released, published, or deployed. Personal Job Agent version `2.0.4`,
Alembic head `20260724_06`, production metadata, production Project Knowledge,
and production credentials remain untouched.

## 48. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Implementation, tests, image builds, container smoke, validation,
documentation, and delivery made no DeepSeek or other external LLM/provider
call.
