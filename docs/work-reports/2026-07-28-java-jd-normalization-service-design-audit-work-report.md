# Java JD Normalization Service Design Audit Work Report

## Executive recommendation

Proceed with a small, independent **JD Normalization Service** only after the
Phase 1 file set in this report is reviewed and approved. The first
implementation should use Java 21, Spring Boot 3.5, Spring MVC, Maven, and
deterministic normalization. Persistence, idempotency, immutable versions,
and Docker Compose should arrive in bounded later phases. A focused Java
unit/web CI job belongs in Phase 1 and expands with each later phase.

The service is justified as a portfolio boundary because normalization and
versioned Job Description intake form a cohesive capability that can be
demonstrated independently. It is not a reason to rewrite Personal Job Agent,
split the current backend into many services, share database tables, or restore
the retired Jobs product module.

The honest architecture description is:

> One existing FastAPI modular-monolith application, plus one small bounded
> Java portfolio service.

This audit is design and documentation only. No Java service, runtime
application change, database migration, deployment, release, cache, queue, or
cloud resource was created.

## 1. Repository and starting commit

| Item | Verified state |
|---|---|
| Repository | `HKJoker-Z/personal-job-agent` |
| Starting branch | Remote `main` |
| Starting commit | `fb09f058240757762dd7028c64482a65d2e506e2` |
| Starting commit subject | `Merge pull request #24 from HKJoker-Z/audit/redis-caching-suitability` |
| Local/remote equality | Local `main` and `origin/main` both resolved to the starting commit |
| Worktree before audit | Clean |
| Stable release | `2.0.4` |
| Stable tag target | `v2.0.4` at `b7ee8643d556638622afff526e53fe254824482b` |
| GitHub release | Published, non-draft, non-prerelease Version 2.0.4 release |
| Alembic head | `20260724_06 (head)` |
| Changes after the release tag | Work Reports and their index only |

The version was cross-checked in `README.md`, Backend configuration, Frontend
package metadata, Docker build arguments, Compose defaults, release notes, and
the GitHub release. Alembic itself reported one head,
`20260724_06`.

The current architecture documentation remains accurate for the checked-in
production release:

- Personal Job Agent is a FastAPI modular monolith with a React/Vite client.
- Nginx provides the HTTPS edge and same-origin `/api` proxy.
- PostgreSQL 16 is authoritative.
- Redis supports the retained Dramatiq/Outbox foundation and SSE coordination;
  it is not an application read cache.
- synchronous `POST /api/analyze` does not execute through Redis/Dramatiq;
- the DeepSeek call is bounded and advisory, while reconciliation and scoring
  remain application-controlled;
- Jobs, Job Rankings, Applications, Approvals, and Tasks are retired from the
  public product flow; their compatibility models/tables do not make them
  active features; and
- production remains a single-host Docker Compose deployment, not Kubernetes
  and not a broad microservice platform.

All ten jobs in the main CI run created by the prior audit merge passed:
Backend tests, PostgreSQL integration, Frontend test/build, Docker build,
PostgreSQL 16 backup/restore, Compose validation, production-runtime
regression, script validation, repository safety, and the isolated Version
2.0.4 Docker smoke. Evidence:
[main CI run 30328494766](https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30328494766).

## 2. Previous audit PR status

The Redis caching suitability audit was open as
[PR #24, `Docs: Audit Redis caching suitability`](https://github.com/HKJoker-Z/personal-job-agent/pull/24).

Before merge, the following were verified:

- the diff contained only
  `docs/work-reports/2026-07-27-redis-caching-suitability-audit-work-report.md`
  and `docs/work-reports/README.md`;
- the report still concluded, “do not implement a Redis read cache in the
  current production design,” which is equivalent to “do not add an
  application read cache now”;
- GitHub reported the PR mergeable and clean; and
- all ten PR checks completed successfully.

PR #24 was merged with a merge commit, as requested. The merge commit is
`fb09f058240757762dd7028c64482a65d2e506e2`. The resulting main CI run also
completed successfully before this audit branch was created. No Redis caching
was implemented.

## 3. Audit branch

The documentation-only audit branch is:

`audit/java-jd-normalization-service-design`

It was created directly from the verified remote main starting commit in
Section 1.

## 4. Service objective

The conceptual service name is **JD Normalization Service**. Its bounded
responsibility is to:

- accept raw Job Description text and explicitly supplied bounded metadata;
- normalize text and metadata deterministically;
- extract deterministic skill keywords with a versioned dictionary;
- classify keyword matches as required, preferred, or merely mentioned using
  documented lexical rules;
- calculate SHA-256 hashes and duplicate fingerprints;
- persist an immutable sequence of Job Description versions;
- expose safe create, read, list, update, and version-history operations; and
- provide a stable versioned HTTP API.

The service is not a semantic Job Description understanding engine. Dictionary
matching and lexical section cues are deterministic heuristics. Responses and
documentation must say so.

## 5. Scope exclusions

The service must not:

- apply for a job or submit an application;
- rank a candidate, Resume, Job, or employer;
- contact an employer or any third party;
- send email or notifications;
- create an Application, Approval, Task, or Agent Run;
- call DeepSeek or any other LLM;
- make an autonomous screening, hiring, or employment decision;
- replace or proxy the FastAPI Analyze pipeline;
- fetch arbitrary URLs or become a scraping service;
- own Resumes, Career Profiles, History, Project Knowledge, monitoring, or
  evaluation;
- restore the retired Jobs, Job Rankings, Applications, Approvals, or Tasks
  modules;
- read or write any SQLAlchemy-owned table;
- use Redis, Kafka, RabbitMQ, Elasticsearch, Kubernetes, a service mesh, or a
  message broker in its first implementation; or
- add Spring AI or another Java AI framework.

The initial service accepts text supplied by its caller. A canonical URL is
metadata only; the service never dereferences it.

## 6. Current FastAPI boundary

Personal Job Agent continues to own:

- browser authentication, server-side Sessions, CSRF/Origin enforcement, and
  user ownership;
- Career Profiles and Resume/File Asset/Resume Version data;
- synchronous Resume-to-JD Analyze orchestration;
- guarded Job Description URL acquisition already present in Analyze;
- prompt safety, optional Project Knowledge retrieval, model invocation,
  tolerant parsing/repair/fallback, evidence reconciliation, and deterministic
  scoring;
- optional History persistence and exports;
- Monitoring, offline Evaluation, Account/Session controls; and
- retained Agent Run/Outbox/Worker compatibility infrastructure.

Analyze remains independent of the retired Job/Application/Task entities.
Nothing in this proposal changes its current endpoint, persistence, or model
contract.

## 7. Proposed Java boundary

The Java service owns only:

- its versioned `/api/v1/job-descriptions` HTTP contract;
- deterministic normalization policy and skill dictionaries;
- its own Job Description aggregate and immutable versions;
- its own idempotency records;
- its own Flyway history; and
- its own PostgreSQL database and database roles.

The preferred deployment boundary is a dedicated database named
`jd_normalization`. If infrastructure later requires one PostgreSQL server, the
service still receives a separate database, migration role, application role,
credentials, backup inventory, and Flyway history. It receives no grants on
the Personal Job Agent database.

Future integration, if approved, is through a versioned HTTP client behind a
FastAPI feature flag. FastAPI would remain the browser-facing policy boundary.
The Java service must not receive browser Session cookies, query SQLAlchemy
tables, or share ORM entities.

This boundary is preferable to the alternatives:

- **Rewriting FastAPI in Java** would risk mature authentication, Analyze,
  reliability, monitoring, and operational behavior without adding portfolio
  evidence proportional to the risk.
- **Sharing ORM-managed tables** would create two migration owners, ambiguous
  transaction boundaries, and coupling between Hibernate and SQLAlchemy.
- **Introducing many microservices** would add networking, deployment,
  observability, and data-consistency overhead without independent product
  domains or team ownership.
- **Restoring the Jobs module** would contradict the deliberately retired
  product scope. A normalized JD record is an intake artifact, not a restored
  Job workflow.

## 8. Technology choices

### Version-selection policy

Version facts were checked on 2026-07-28 against primary project
documentation. “Latest upstream” and “recommended baseline” are deliberately
separate. The baseline keeps one Spring Boot-tested dependency set instead of
overriding every library to an unrelated newest release.

| Technology | Current evidence | Recommended first baseline | Decision |
|---|---|---|---|
| Java | OpenJDK tagged `jdk-21.0.12-ga` on 2026-07-21 | Java 21.0.12 LTS toolchain and runtime | Java 21 is the requested LTS portfolio target. Pin the container image by digest during implementation. |
| Spring Boot | Stable lines include 4.1.0 and 3.5.16 | Spring Boot 3.5.16 | 3.5.16 supports Java 21 and keeps the requested JUnit 5 line. Boot 4.1.0 is evaluated but currently manages JUnit 6 and newer framework majors. Treat a Boot 4 upgrade as a later focused change. |
| Spring Web/MVC | Boot 3.5.16 manages Spring Framework 6.2.19 | `spring-boot-starter-web` / Spring MVC 6.2.19 | Use servlet MVC, not WebFlux; requests and PostgreSQL operations are synchronous. |
| Spring Data JPA | Boot 3.5.16 manages Spring Data JPA 3.5.13 and Hibernate ORM 6.6.53.Final | `spring-boot-starter-data-jpa` with managed versions | Demonstrates JPA while keeping SQL constraints and Flyway authoritative. |
| Bean Validation | Boot 3.5.16 manages Jakarta Validation 3.0.2 and Hibernate Validator 8.0.3.Final | `spring-boot-starter-validation` | Use record/DTO constraints plus custom code-point and cross-field validators. |
| PostgreSQL | Current supported releases include 18.4 and 16.14; PostgreSQL recommends the current minor of a supported major | PostgreSQL 16.14 | Keeps the repository’s PostgreSQL 16 major while moving the independent service to the current security/bug-fix minor. Do not copy the repository’s older 16.9 CI pin into a new service. |
| PostgreSQL JDBC | Boot 3.5.16 manages 42.7.11 | 42.7.11 | Let the Boot BOM manage it. |
| Flyway | Flyway 13.0.0 is current upstream; Boot 3.5.16 manages 11.7.2 | Flyway 11.7.2 plus `flyway-database-postgresql` | Prefer the Boot-tested line. Do not override to Flyway 13 in the first PR. |
| Testcontainers | 2.0.5 is current upstream; Boot 3.5.16 manages 1.21.4 | Testcontainers 1.21.4 | Use Boot-managed JUnit 5/PostgreSQL modules. Evaluate the 2.x artifact migration with a future Boot major upgrade. |
| JUnit | JUnit 5.14.4 is the current JUnit 5 maintenance release; Boot 3.5.16 manages 5.12.2 | JUnit Jupiter 5.12.2 through `spring-boot-starter-test` | Meeting the requested JUnit 5 baseline without overriding Boot’s tested platform is more valuable than chasing 5.14.4 in Phase 1. |
| Mockito | Boot 3.5.16 manages Mockito 5.17.0; Boot 4.1 manages 5.23.0 | Mockito 5.17.0 through `spring-boot-starter-test` | Use mocks only at unit/web boundaries; do not mock PostgreSQL integration behavior. |
| Springdoc OpenAPI | Springdoc 2.8.x supports Boot 3.5.x; 2.8.17 is the documented stable 2.x release | `springdoc-openapi-starter-webmvc-api` 2.8.17 | Generate OpenAPI JSON without exposing Swagger UI by default. Enable UI only in the local development profile. |
| Maven | Apache Maven 3.9.16 is the current recommended Maven 3 release; Maven 4 remains preview | Maven Wrapper 3.9.16 | Maven is conventional, readable to junior interviewers, is Spring Initializr’s default, and needs less build DSL than Gradle for one module. |
| Gradle | Current Gradle is 9.6.1, while Boot 3.5 explicitly supports Gradle 7.6.4+ or 8.4+ rather than Gradle 9 | Not selected | Selecting Gradle would require an older supported Gradle line or a Boot-major change and offers no repository-specific advantage. |
| Docker | Docker documents multi-stage builds as a way to copy only the built artifact into a smaller runtime image | Multi-stage Maven/Temurin 21 build | Run a non-root JRE image with an immutable executable JAR and no build tools in the runtime stage. |

Primary version references:

- [OpenJDK 21.0.12 GA tag](https://github.com/openjdk/jdk21u/releases/tag/jdk-21.0.12-ga)
- [Spring Boot 3.5.16 system requirements and stable lines](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 managed dependency coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [PostgreSQL versioning and supported minors](https://www.postgresql.org/support/versioning/)
- [JUnit 5.14.4 release notes](https://docs.junit.org/5.14.4/release-notes.html)
- [Springdoc compatibility matrix](https://springdoc.org/faq.html#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot)
- [Apache Maven downloads](https://maven.apache.org/download.cgi)
- [Gradle releases](https://gradle.org/releases/)
- [Flyway Engine release notes](https://documentation.red-gate.com/flyway/release-notes-and-older-versions/release-notes-for-flyway-engine)
- [Testcontainers PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)

## 9. API design

### Shared API conventions

- Base path: `/api/v1`.
- Media type: `application/json`.
- JSON field naming: `snake_case`, matching the existing portfolio API style.
- IDs: server-generated UUIDv4 strings.
- Times: UTC RFC 3339 strings with `Z`.
- Authentication: the bounded internal API key in Section 19 for every
  `/api/v1/**` operation.
- Correlation: `X-Request-ID` on every request/response.
- Current aggregate concurrency: a strong quoted decimal ETag, for example
  `ETag: "3"`, equal to `optimistic_lock_version`.
- The API never returns a raw idempotency key, API key, database error, stack
  trace, or unbounded rejected value.

### Shared request

`JobDescriptionInput`:

```json
{
  "raw_text": "Senior Backend Engineer\r\n\r\nRequired:\r\n- Java 21",
  "metadata": {
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "location": "Shanghai, China",
    "canonical_url": "https://jobs.example.test/backend-engineer"
  }
}
```

`raw_text` is required. `metadata` and each metadata property are optional.
The update request may omit `canonical_url`; if it is present, it must
normalize to the aggregate’s immutable canonical URL.

### Shared normalization result

```json
{
  "normalized_text": "Senior Backend Engineer\n\nRequired:\n- Java 21",
  "content_hash": "3d...64-lowercase-hex-characters",
  "normalization_policy_version": "jd-normalization-v1",
  "skill_dictionary_version": "skills-v1",
  "required_skills": [
    {"id": "java", "name": "Java"}
  ],
  "preferred_skills": [],
  "mentioned_skills": [],
  "metadata": {
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "location": "Shanghai, China",
    "canonical_url": "https://jobs.example.test/backend-engineer"
  }
}
```

The three skill arrays contain bounded `{id, name}` objects in deterministic
canonical-ID order.

### Shared persisted response

```json
{
  "id": "8e81ae83-9a92-4d7a-ac31-ed2c11b66f34",
  "canonical_url": "https://jobs.example.test/backend-engineer",
  "optimistic_lock_version": 0,
  "created_at": "2026-07-28T04:30:00Z",
  "updated_at": "2026-07-28T04:30:00Z",
  "current_version": {
    "id": "ba228af5-f8f2-4cca-b343-e46c481f9b09",
    "version_number": 1,
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "location": "Shanghai, China",
    "normalized_text": "Senior Backend Engineer\n\nRequired:\n- Java 21",
    "content_hash": "3d...64-lowercase-hex-characters",
    "normalization_policy_version": "jd-normalization-v1",
    "skill_dictionary_version": "skills-v1",
    "required_skills": [{"id": "java", "name": "Java"}],
    "preferred_skills": [],
    "mentioned_skills": [],
    "created_at": "2026-07-28T04:30:00Z"
  }
}
```

### `POST /api/v1/job-descriptions/normalize`

- **Purpose:** preview the exact deterministic result without persistence.
- **Request:** `JobDescriptionInput`.
- **Response:** the shared normalization result.
- **Validation:** Section 10 limits, HTTPS canonical URL rules, metadata
  bounds, and dictionary startup validity.
- **Authorization assumption:** internal API key; development-only disabled
  authentication is permitted only on loopback.
- **Success:** `200 OK`.
- **Errors:** `400 INVALID_REQUEST`,
  `400 INVALID_REQUEST_ID`, `401 UNAUTHORIZED`,
  `413 PAYLOAD_TOO_LARGE`, `422 VALIDATION_FAILED`,
  `422 EMPTY_JOB_DESCRIPTION`, and safe `500 INTERNAL_ERROR`.
- **Pagination/sorting:** not applicable to a single deterministic operation.
- **Idempotency:** no `Idempotency-Key`. The endpoint is side-effect free and
  identical policy/dictionary/input bytes produce an identical body.
- **Concurrency:** requests are independent; there is no shared mutable state
  after the dictionary has been validated and loaded.

This is the only Phase 1 product endpoint.

### `POST /api/v1/job-descriptions`

- **Purpose:** normalize and persist a new aggregate and immutable version 1.
- **Request:** `JobDescriptionInput`.
- **Response:** shared persisted response.
- **Validation:** identical to the preview endpoint plus a required
  `Idempotency-Key` matching
  `[A-Za-z0-9][A-Za-z0-9._:-]{15,127}`.
- **Authorization assumption:** one internal service principal; idempotency is
  scoped by operation because the service has no user identity.
- **Success:** `201 Created`, `Location:
  /api/v1/job-descriptions/{id}`, ETag `"0"`. A completed replay also returns
  the stored `201` result and adds `Idempotency-Replayed: true`.
- **Errors:** shared errors plus `400 IDEMPOTENCY_KEY_INVALID`,
  `409 IDEMPOTENCY_KEY_REUSED`, `409 DUPLICATE_JOB_DESCRIPTION`,
  `409 IDEMPOTENCY_REQUEST_IN_PROGRESS`, and
  `503 DATABASE_UNAVAILABLE`.
- **Pagination/sorting:** not applicable.
- **Idempotency:** required; Section 15 defines fingerprint comparison,
  completed replay, expiry, and different-input conflict.
- **Concurrency:** the database unique constraints select one idempotency-key
  winner and one current duplicate-content owner. Losing transactions do not
  leave a root or version row.

### `GET /api/v1/job-descriptions/{id}`

- **Purpose:** retrieve one aggregate with its current immutable version.
- **Request:** UUID path parameter; optional `If-None-Match`.
- **Response:** shared persisted response and current ETag.
- **Validation:** malformed UUID returns `400 INVALID_REQUEST`.
- **Authorization assumption:** internal API key.
- **Success:** `200 OK`; matching `If-None-Match` returns `304 Not Modified`
  without a body.
- **Errors:** shared errors plus `404 JOB_DESCRIPTION_NOT_FOUND`.
- **Pagination/sorting:** not applicable.
- **Idempotency:** safe read; no key.
- **Concurrency:** one database statement/read-only transaction resolves the
  root and the version referenced by `current_version_id`. The response is one
  committed version, never a mix of two versions.

HTTP conditional reads do not add an application read cache and do not change
the Redis audit conclusion.

### `GET /api/v1/job-descriptions`

- **Purpose:** bounded discovery and exact metadata/hash/URL lookup.
- **Request query:** `limit` default 20, range 1–100; opaque `cursor`;
  `sort=created_at_desc` default or `created_at_asc`; optional exact
  case-insensitive `title`, `company`, and `location`; optional exact
  lowercase-hex `content_hash`; optional canonical URL.
- **Response:**

```json
{
  "items": [
    {
      "id": "8e81ae83-9a92-4d7a-ac31-ed2c11b66f34",
      "canonical_url": "https://jobs.example.test/backend-engineer",
      "optimistic_lock_version": 0,
      "current_version_number": 1,
      "title": "Senior Backend Engineer",
      "company": "Example Ltd",
      "location": "Shanghai, China",
      "content_hash": "3d...64-lowercase-hex-characters",
      "created_at": "2026-07-28T04:30:00Z",
      "updated_at": "2026-07-28T04:30:00Z"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

  Each item is this bounded summary representation. Normalized text and skill
  arrays are available through the single-resource endpoint and are not
  repeated across a 100-item list page.
- **Validation:** bounded filter lengths, valid sort enum, valid 64-character
  SHA-256 hex, valid canonical URL, and a cursor whose embedded sort/filter
  fingerprint matches the current request.
- **Authorization assumption:** internal API key.
- **Success:** `200 OK`, including an empty page.
- **Errors:** shared errors plus `400 INVALID_CURSOR`.
- **Pagination:** keyset pagination on immutable `(created_at, id)`. Fetch
  `limit + 1`; never calculate an unrequested total count.
- **Sorting:** only creation time ascending/descending, always tied by UUID in
  the same direction. Mutable `updated_at` is intentionally not a cursor sort.
- **Idempotency:** safe read; no key.
- **Concurrency:** inserts before/after a cursor can appear on later refreshes,
  but the cursor order remains deterministic. The endpoint does not claim
  snapshot pagination across multiple HTTP requests.

There is no broad `q` search in the first implementation.

### `PUT /api/v1/job-descriptions/{id}`

- **Purpose:** replace normalized content/metadata by appending an immutable
  version and moving the aggregate’s current pointer.
- **Request:** `JobDescriptionInput`; required `If-Match: "{current version}"`.
- **Response:** shared persisted response with the new current version.
- **Validation:** all normalization validation; canonical URL is immutable and
  may only be omitted or unchanged after normalization; `If-Match` must contain
  exactly one strong decimal ETag.
- **Authorization assumption:** internal API key.
- **Success:** `200 OK`. A request whose full derived result equals the current
  version is a no-op `200` with the unchanged ETag and no new version.
- **Errors:** shared errors plus `404 JOB_DESCRIPTION_NOT_FOUND`,
  `422 IMMUTABLE_FIELD`, `428 PRECONDITION_REQUIRED`,
  `400 INVALID_PRECONDITION`, `412 OPTIMISTIC_LOCK_CONFLICT`, and
  `409 DUPLICATE_JOB_DESCRIPTION`.
- **Pagination/sorting:** not applicable.
- **Idempotency:** HTTP PUT is logically idempotent for the same current
  representation. No `Idempotency-Key` is added. After an uncertain outcome,
  the client reads the resource and compares the intended representation.
- **Concurrency:** JPA `@Version`, the SQL update predicate, unique version
  number, and current duplicate fingerprint arbitrate. Two updates with the
  same old ETag cannot both commit.

### `GET /api/v1/job-descriptions/{id}/versions`

- **Purpose:** retrieve immutable version history and prove the audit trail.
- **Request query:** `limit` default 10, range 1–25; opaque `cursor`;
  `sort=version_desc` default or `version_asc`.
- **Response:** `items` of the complete version object shown in the persisted
  response, plus `next_cursor` and `has_more`.
- **Validation:** UUID, limit, sort, and cursor validation.
- **Authorization assumption:** internal API key.
- **Success:** `200 OK`; a valid aggregate always has at least version 1.
- **Errors:** shared errors plus `404 JOB_DESCRIPTION_NOT_FOUND` and
  `400 INVALID_CURSOR`.
- **Pagination:** keyset on `(job_description_id, version_number)`.
- **Sorting:** version number ascending/descending only.
- **Idempotency:** safe read; no key.
- **Concurrency:** committed newer versions may appear on a later first page;
  already returned version rows never change.

The maximum of 25 full versions bounds a worst-case response. If the 100,000
code-point text limit proves too large for history pages, a version-detail
endpoint and summary page can be proposed in a later API version based on
measured payloads.

### Rejected initial endpoints

- `DELETE /api/v1/job-descriptions/{id}` is rejected because retention and
  legal/privacy deletion semantics are not defined. Adding it would conflict
  with immutable history unless a deliberate aggregate-erasure policy,
  authorization, audit, backup, and idempotency design existed.
- an endpoint to upload files is rejected; this service accepts text only;
- an endpoint to fetch/scrape a URL is rejected;
- skill dictionary mutation endpoints are rejected; dictionaries are reviewed
  versioned artifacts in Git;
- ranking, matching, application, approval, and task endpoints are rejected;
- fuzzy/full-text search is rejected until a caller demonstrates a need; and
- bulk ingestion is rejected from the first implementation because it
  complicates partial failure and idempotency without proving an additional
  portfolio skill.

## 10. Normalization policy

### Limits and encoding

- Maximum `raw_text`: 100,000 Unicode code points.
- Maximum JSON request body: 512 KiB before parsing.
- Metadata title/company/location: 200 Unicode code points each.
- Canonical URL: 2,048 ASCII characters after normalization.
- Maximum skill results: 256 unique canonical skills across all categories.
- Input JSON must be valid UTF-8. Invalid JSON/UTF-8 is `400 INVALID_REQUEST`.
- Java validation counts Unicode code points, not UTF-16 `String.length()`.

### `jd-normalization-v1` order

1. Reject a request over the byte/code-point limits.
2. Remove U+0000 NUL characters.
3. normalize Unicode to NFC; preserve non-ASCII scripts, emoji, accents, and
   case;
4. convert CRLF, CR, U+0085, U+2028, and U+2029 line separators to LF;
5. on every line, convert horizontal Unicode whitespace runs to one ASCII
   space, then remove leading/trailing horizontal whitespace;
6. keep every nonblank line boundary and its original heading punctuation or
   bullet marker;
7. collapse multiple blank lines to one blank line;
8. remove leading/trailing blank lines; and
9. produce no trailing newline.

This preserves headings and bullet lines while deliberately discarding visual
indentation. It does not rewrite capitalization, reorder lines, spell-check,
translate, stem words, or infer missing content.

After normalization, text with no non-whitespace code point is
`422 EMPTY_JOB_DESCRIPTION`. NUL-only input is therefore empty.

### Metadata

Title, company, and location are normalized by NUL removal, NFC, trimming, and
collapsing all internal whitespace to one ASCII space. An explicitly supplied
value that becomes blank is invalid rather than silently converted to null.
The service does not infer these fields from Job Description text.

Canonical URL normalization:

- requires absolute HTTPS;
- lowercases scheme and IDNA ASCII host;
- removes the default port, fragment, and dot segments;
- converts an empty path to `/`;
- preserves path case and query parameter order/meaning;
- normalizes percent-encoding hex case; and
- does not remove tracking parameters or contact the host.

The normalized canonical URL is immutable after create.

### Skills and aliases

`skills-v1.json` contains:

- a unique canonical skill ID;
- a display name;
- one or more explicit aliases;
- match type (`token` or `phrase`); and
- the dictionary version.

Startup fails if IDs or normalized aliases collide. Ambiguous short aliases
such as `go`, `r`, or `js` are not accepted without a safer boundary rule.
Dictionary phrases are treated as data and regex-quoted.

Matching uses NFC plus locale-independent Unicode case folding. Boundary rules
support names such as `C++`, `C#`, `.NET`, and `Node.js` without interpreting
dictionary values as regular expressions.

Classification is lexical:

- a match below a recognized required heading or on a line with a required
  cue is `required`;
- otherwise, a match below a recognized preferred heading or with a preferred
  cue is `preferred`;
- otherwise it is `mentioned`.

Recognized headings/cues live in the normalization policy and are versioned.
If the same canonical skill appears more than once, it is emitted once.
Precedence is `required` over `preferred` over `mentioned`. Each final array is
sorted by canonical ID. Aliases always emit their canonical ID/display name.

Changing an alias, heading rule, precedence rule, Unicode step, or whitespace
step requires a new immutable dictionary or policy version. Historical rows
retain the versions used when they were created.

This is deterministic keyword extraction, not semantic understanding.

### Hashes

- `content_hash` is SHA-256 over UTF-8 `normalized_text` only and is exposed as
  64 lowercase hex characters.
- `deduplication_fingerprint` is SHA-256 over a versioned, length-prefixed byte
  format containing normalized text, title, company, and location. It excludes
  canonical URL, policy version, dictionary version, timestamps, IDs, and
  extracted skill arrays.
- `request_fingerprint` is separately defined in Section 15 and represents
  exact create-request semantics, not content identity.

Length-prefixing and explicit null markers prevent field-boundary ambiguity.

## 11. Data model

The service uses UUIDv4 primary keys, PostgreSQL `timestamptz`, UTC Java
`Instant`, and lower-level database constraints even when Bean Validation
checks the same invariant.

### `job_descriptions`

| Column | Type | Rules |
|---|---|---|
| `id` | `uuid` | Primary key; application-generated UUIDv4 |
| `canonical_url` | `varchar(2048)` | Nullable; normalized HTTPS; unique when non-null; immutable |
| `current_version_id` | `uuid` | Not null; composite deferred FK to a version owned by this aggregate |
| `current_deduplication_fingerprint` | `bytea` | Not null, exactly 32 bytes; unique among current aggregates |
| `optimistic_lock_version` | `bigint` | Not null default 0; nonnegative; JPA `@Version` |
| `created_at` | `timestamptz` | Not null; database default current transaction timestamp |
| `updated_at` | `timestamptz` | Not null; application sets on successful aggregate update |

Constraints/indexes:

- primary key on `id`;
- unique `canonical_url` (PostgreSQL naturally permits multiple nulls);
- unique `current_deduplication_fingerprint`;
- composite foreign key
  `(current_version_id, id, current_deduplication_fingerprint)` to
  `job_description_versions(id, job_description_id,
  deduplication_fingerprint)`, `DEFERRABLE INITIALLY DEFERRED`;
- check fingerprint length and nonnegative optimistic version; and
- keyset index `(created_at DESC, id DESC)`.

The deferred FK permits pre-generating both UUIDs and inserting root/version in
one transaction without a nullable current pointer. It also proves that the
current version belongs to that root and has the recorded current fingerprint.

### `job_description_versions`

| Column | Type | Rules |
|---|---|---|
| `id` | `uuid` | Primary key; application-generated UUIDv4 |
| `job_description_id` | `uuid` | Not null; deferred FK to `job_descriptions(id)`, delete restricted |
| `version_number` | `integer` | Not null, greater than zero |
| `title` | `varchar(200)` | Nullable |
| `company` | `varchar(200)` | Nullable |
| `location` | `varchar(200)` | Nullable |
| `normalized_text` | `text` | Not null; 1–100,000 code points |
| `content_hash` | `bytea` | Not null, exactly 32 bytes |
| `deduplication_fingerprint` | `bytea` | Not null, exactly 32 bytes |
| `normalization_policy_version` | `varchar(64)` | Not null |
| `skill_dictionary_version` | `varchar(64)` | Not null |
| `required_skills` | `jsonb` | Not null; bounded JSON array of `{id,name}` |
| `preferred_skills` | `jsonb` | Not null; bounded JSON array of `{id,name}` |
| `mentioned_skills` | `jsonb` | Not null; bounded JSON array of `{id,name}` |
| `created_at` | `timestamptz` | Not null; database default; never updated |

Constraints/indexes:

- primary key on `id`;
- unique `(job_description_id, version_number)`;
- unique `(id, job_description_id, deduplication_fingerprint)` to support the
  root composite FK;
- checks for text length, hash lengths, positive version, nonblank policy/
  dictionary versions, and JSON array types;
- index `(job_description_id, version_number DESC)`;
- B-tree index on `content_hash`;
- expression indexes on `lower(title)`, `lower(company)`, and
  `lower(location)` only because the proposed API has those exact filters; and
- a database trigger rejects `UPDATE` and `DELETE` on version rows.

The application maps versions as immutable entities and exposes no mutation
repository method. The trigger makes immutability a database invariant rather
than a convention. There is no cascade delete.

### `request_idempotency`

| Column | Type | Rules |
|---|---|---|
| `id` | `uuid` | Primary key |
| `operation` | `varchar(80)` | Not null; initial value `create-job-description-v1` |
| `key_hash` | `bytea` | Not null, exactly 32 bytes |
| `request_fingerprint` | `bytea` | Not null, exactly 32 bytes |
| `status` | `varchar(20)` | `in_progress` or `completed` |
| `resource_id` | `uuid` | Nullable until completion; FK to `job_descriptions`, delete restricted |
| `response_status` | `smallint` | Nullable until completion |
| `response_body` | `jsonb` | Nullable until completion; application-capped at 256 KiB serialized |
| `created_at` | `timestamptz` | Not null |
| `expires_at` | `timestamptz` | Not null |
| `completed_at` | `timestamptz` | Nullable until completion |

Constraints/indexes:

- unique `(operation, key_hash)`;
- status/check constraints requiring all completion fields together;
- hash-length and HTTP-status checks;
- index `(expires_at, status)` for bounded cleanup; and
- index on `resource_id`.

No external provider side effect exists, so there are no provider-start,
attempt-token, or indeterminate states. The insert, resource creation, response
storage, and completion occur in one database transaction. A crash rolls the
whole transaction back.

### JSONB versus relational skills

JSONB arrays are recommended because:

- results are small, bounded snapshots read with a version;
- dictionary entries are reviewed application artifacts, not database-owned
  entities;
- no initial endpoint filters or joins by skill; and
- immutable JSON preserves the exact name associated with the historical
  dictionary.

Do not add a GIN index. If a measured API later requires skill-centric search,
propose a relational `job_description_version_skills` table in a separate
migration. Do not silently make JSON containment a product search contract.

### Content-hash uniqueness scope

`content_hash` is not globally unique. The same normalized text can
legitimately have different explicitly supplied title/company/location.
It is indexed for exact lookup.

The root’s unique current `deduplication_fingerprint` prevents two current
aggregates from representing the same normalized text and metadata. It changes
when the current version changes, so reverting to a historical representation
is possible. Canonical URL uniqueness independently prevents two current
aggregates from claiming one normalized URL.

Hash equality is followed by byte/string equality before returning a friendly
duplicate response. The database uniqueness constraint remains the concurrent
correctness mechanism.

## 12. Flyway strategy

The Java service has its own Flyway migration history. It never imports,
invokes, or edits the FastAPI Alembic history.

Initial settings:

- location: `classpath:db/migration`;
- `V1__create_job_description_schema.sql` creates the root/version schema,
  deferred foreign keys, indexes, and immutable trigger;
- `V2__add_request_idempotency.sql` is added only with the idempotent create
  phase;
- `spring.jpa.hibernate.ddl-auto=validate`;
- `spring.flyway.validate-on-migrate=true`;
- `spring.flyway.clean-disabled=true`;
- no baseline-on-migrate;
- no repeatable migration for core tables; and
- merged versioned migrations are append-only and never edited.

Use `flyway-core` and `flyway-database-postgresql`. A migration role owns DDL;
the runtime application role receives only required CRUD/sequence privileges.
Production-like configuration supplies separate Flyway credentials through
the environment. Local Compose may bootstrap both roles in an initialization
script, but no credential is committed.

CI starts an empty PostgreSQL 16.14 Testcontainer, runs migrate and validate,
restarts an application context against the migrated schema with Hibernate
validation, and proves a second migrate is a no-op. Flyway documents that
`validate` compares applied migration names/types/checksums with the available
migrations:
[Flyway validate documentation](https://documentation.red-gate.com/flyway/reference/commands/validate).

## 13. Request ID

- Header: `X-Request-ID`.
- Accepted client value: 1–64 ASCII characters matching
  `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}`.
- Missing value: generate UUIDv4.
- More than one header value or an invalid value:
  `400 INVALID_REQUEST_ID`, using a newly generated safe request ID.
- Put the trusted value in SLF4J MDC for the request and clear it in `finally`.
- Return it on success, validation/auth errors, 404, conflict, and safe 500.
- Forward it in any future FastAPI HTTP integration.

Request ID is correlation only. It grants no authority, does not identify a
user, does not deduplicate work, and is not stored as the idempotency key.

## 14. Error contract

Every API error uses:

```json
{
  "error": {
    "code": "JOB_DESCRIPTION_NOT_FOUND",
    "message": "The requested job description was not found.",
    "request_id": "0fb99e24-4f85-43df-ae8c-6484b1457ee2",
    "details": {}
  }
}
```

Rules:

- `code` is stable machine-readable uppercase snake case.
- `message` is safe, stable English.
- `request_id` equals the trusted response header.
- `details` is always an object and is bounded.
- validation details contain field and rule, never the complete rejected text.
- duplicate details may contain the existing Job Description UUID and content
  hash because the same authenticated internal principal can already read it.
- database constraint names, SQL, stack traces, class names, hostnames,
  credentials, raw JD text, keys, and fingerprints are never returned.
- unexpected exceptions map to `500 INTERNAL_ERROR` and are logged once with
  request ID, exception class, and stack trace on the server.

Core status/code mapping:

| HTTP | Code |
|---|---|
| 400 | `INVALID_REQUEST`, `INVALID_REQUEST_ID`, `INVALID_CURSOR`, `INVALID_PRECONDITION`, `IDEMPOTENCY_KEY_INVALID` |
| 401 | `UNAUTHORIZED` |
| 404 | `JOB_DESCRIPTION_NOT_FOUND` |
| 409 | `DUPLICATE_JOB_DESCRIPTION`, `IDEMPOTENCY_KEY_REUSED`, `IDEMPOTENCY_REQUEST_IN_PROGRESS` |
| 412 | `OPTIMISTIC_LOCK_CONFLICT` |
| 413 | `PAYLOAD_TOO_LARGE` |
| 422 | `VALIDATION_FAILED`, `EMPTY_JOB_DESCRIPTION`, `IMMUTABLE_FIELD` |
| 428 | `PRECONDITION_REQUIRED` |
| 500 | `INTERNAL_ERROR` |
| 503 | `DATABASE_UNAVAILABLE` |

## 15. Idempotency design

Idempotency applies only to persisted create.

### Key and hash

- Client sends `Idempotency-Key`.
- Syntax is defined in Section 9 and encourages high-entropy opaque keys.
- The raw key is never logged or stored.
- Stored `key_hash` is
  `SHA-256("create-job-description-v1" || 0x00 || UTF-8(key))`.
- The key is not an authentication factor.

### Request fingerprint

`create-job-description-request:v1` hashes a length-prefixed representation of:

- exact raw text after JSON decoding but before normalization;
- explicit null/present state and exact values of title, company, location,
  and canonical URL; and
- request fingerprint format version.

Request ID, API key, Idempotency-Key, timestamps, generated IDs, and current
policy/dictionary versions are excluded. Thus a delayed replay after a
dictionary deployment returns the originally completed response; it does not
quietly produce a different resource.

### Behavior

1. Validate authorization, headers, payload limits, and normalize outside a
   transaction.
2. Attempt the idempotency row and resource transaction in Section 16.
3. Same key and same fingerprint after completion returns stored status/body,
   `Location`, ETag, current `X-Request-ID`, and
   `Idempotency-Replayed: true`.
4. Same key and different fingerprint returns
   `409 IDEMPOTENCY_KEY_REUSED`.
5. A visible `in_progress` row returns
   `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with bounded `Retry-After`, although
   the single-transaction design normally prevents other transactions from
   seeing that intermediate state.
6. Default retention is 24 hours, configurable from 1–168 hours.
7. Claim-time maintenance deletes at most 100 expired completed rows. Low
   traffic may delay cleanup; it cannot delete an uncommitted request.

This provides completed local-result replay and one local committed resource.
It does not claim external exactly-once; the first implementation has no
external provider side effect.

## 16. Transaction design

PostgreSQL `READ COMMITTED`, short Spring `@Transactional` application-service
methods, database constraints, and explicit flush points are recommended.
Java `synchronized`, local maps, and process locks are prohibited as
correctness mechanisms.

### Idempotent create

1. Outside transaction: authenticate, validate, normalize, calculate content/
   deduplication/request fingerprints, and generate aggregate/version UUIDs.
2. In one transaction, insert the `in_progress` idempotency row and flush.
3. Insert root and version 1 with pre-generated UUIDs. Deferred constraints
   validate their cyclic ownership at commit.
4. The root unique canonical URL/current deduplication fingerprint arbitrates
   duplicates. A pre-query improves the error, but the unique constraint is
   authoritative.
5. Build the bounded `201` body from persisted values.
6. Set idempotency resource/status/body/completion fields.
7. Flush and commit once.

If the idempotency unique insert loses, let that transaction roll back, then
load the winning row in a new read transaction. PostgreSQL may block the
conflicting insert until the winner commits; this is expected.

If the canonical URL or current fingerprint unique insert loses, roll the
whole transaction back. Query the winning aggregate in a fresh transaction and
return `DUPLICATE_JOB_DESCRIPTION`. Do not keep an orphan root, version, or
idempotency record.

### Creating a new immutable version

1. Outside transaction: validate/normalize and parse `If-Match`.
2. In transaction: load root/current version.
3. Compare supplied ETag with `optimistic_lock_version`.
4. If every derived version field is equal, return current state without a
   write.
5. Otherwise insert version `current.version_number + 1`.
6. Set root current version, current fingerprint, and `updated_at`.
7. JPA flush updates root with
   `WHERE id = ? AND optimistic_lock_version = ?` and increments `@Version`.
8. Commit; deferred FK verifies the pointer.

### Two simultaneous updates

Both actors may calculate the same next version number. One commits. The other
loses either the unique `(job_description_id, version_number)` insert or the
`@Version` root update. Its transaction rolls back the inserted version. Map
either stale-write path to `412 OPTIMISTIC_LOCK_CONFLICT`, unless a different
aggregate now owns the target duplicate fingerprint, which maps to
`409 DUPLICATE_JOB_DESCRIPTION`.

### Failed version creation

Any validation, constraint, optimistic-lock, serialization, or response-build
failure before commit rolls back:

- the new version;
- root pointer/fingerprint/timestamp changes; and
- optimistic version increment.

An integration test must prove the old current pointer and exact version count.

### Replaying a completed request

Replay is a short read-only transaction. It compares the 32-byte fingerprint
in constant time, verifies completion/not-expired, loads stored status/body and
resource metadata, then returns without normalization persistence or another
insert. Authentication still runs before replay disclosure.

### Pessimistic locking

Do not use a pessimistic root lock initially. Optimistic locking is the
portfolio requirement and expected contention is low. A targeted
`SELECT ... FOR UPDATE` may be considered only if measurements show repeated
late optimistic failures. Idempotent create uses unique-insert arbitration, not
a long-held row lock.

## 17. Optimistic locking

`JobDescription.optimisticLockVersion` is a `long` field annotated with
`jakarta.persistence.Version`. Jakarta Persistence defines `@Version` as the
entity optimistic-lock value and requires stale updates to fail rather than
lose an intervening update:
[Jakarta Persistence `@Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version).

HTTP maps it as follows:

- GET returns `ETag: "{value}"`.
- PUT requires exactly one matching strong `If-Match`.
- missing precondition is 428;
- stale precondition or commit-time `OptimisticLockException` is 412;
- the error includes the resource ID but does not disclose the new content;
- clients GET the current representation before deciding whether to retry.

Tests must force flush inside the application service so the exception is
mapped inside the HTTP error boundary, not after the controller has returned.

## 18. Search and pagination

First implementation queries are limited to:

- current aggregate by UUID;
- versions by aggregate/version number;
- exact normalized canonical URL;
- exact current content hash;
- exact case-insensitive current title, company, and location;
- current duplicate fingerprint; and
- created-time keyset pages.

The list query joins root to its `current_version_id`; it never scans all
historical versions to build a current page.

Keyset pagination is selected over OFFSET because:

- it has stable work as page depth grows;
- it uses the `(created_at, id)` index;
- the tie-breaking UUID makes order deterministic; and
- it avoids OFFSET’s shifting-page behavior under inserts.

The opaque cursor is Base64URL-encoded versioned JSON containing sort
direction, last timestamp, last UUID, and SHA-256 of normalized filters. It is
not authorization and does not need secrecy. Invalid structure or a filter/sort
mismatch returns `INVALID_CURSOR`.

Do not add:

- Elasticsearch;
- Redis caching;
- PostgreSQL full-text search;
- trigram extensions/indexes;
- fuzzy title/company/location search; or
- a total-count query.

Add one only after a real caller contract and measured PostgreSQL plan justify
it.

## 19. Security scope

### Options

| Option | Trade-off | Decision |
|---|---|---|
| No authentication, localhost only | Smallest demo, but easy to expose accidentally and does not demonstrate an internal-service boundary | Development-only opt-in, never the default container mode |
| Static internal API key | Small, understandable, appropriate to one internal caller; no user identity or fine-grained authorization | Recommended first portfolio mode |
| Existing FastAPI Session | Would copy browser cookies/CSRF/user coupling into the service and require shared session state | Rejected |
| OAuth/JWT | Appropriate for multiple independently identified clients/public exposure, but requires issuer, validation, rotation, claims, and operational ownership | Defer until a real public/multi-client requirement |

### Recommended mode

- `Authorization: Bearer <internal key>`.
- At least 32 random bytes, delivered only through
  `JD_NORMALIZATION_API_KEY`.
- Fail startup outside the development profile if missing/short.
- Compare fixed-length SHA-256 byte arrays with
  `MessageDigest.isEqual`; never log either value.
- A development-only `auth.mode=disabled` requires the `dev` profile and
  loopback host binding documented in local commands.
- API docs UI is development-only; OpenAPI JSON requires the API key outside
  development.
- Liveness/readiness endpoints are unauthenticated but expose only status.
  Other Actuator endpoints are unexposed.
- CORS is disabled by default because the service is not browser-facing.
- Do not accept or forward browser Session cookies.
- Do not put secrets in Git, Docker build arguments, images, error responses,
  Compose files, or command output.

The service must not be publicly exposed until a separate authentication,
TLS/reverse-proxy, rate-limit, abuse, privacy, and operational design is
approved.

## 20. Package structure

Package-by-feature is preferred over a strict package-by-layer tree:

```text
services/jd-normalization-service/
  pom.xml
  README.md
  src/main/java/io/github/hkjokerz/jobagent/jdnormalization/
    JdNormalizationServiceApplication.java
    config/
    normalization/
    jobdescription/
    idempotency/
    pagination/
    security/
    web/
  src/main/resources/
    application.yml
    skills/
    db/migration/
  src/test/java/io/github/hkjokerz/jobagent/jdnormalization/
    normalization/
    jobdescription/
    idempotency/
    web/
    support/
```

Why:

- a junior interviewer can find normalization, Job Description persistence,
  and idempotency without following four layers for every change;
- pure normalization stays framework-light and unit-testable;
- JPA entities/repositories/application service can live together under
  `jobdescription`;
- cross-cutting HTTP/security/configuration remains visibly separated; and
- the structure scales to this bounded service without pretending to implement
  full Domain-Driven Design.

Use one concrete Spring Data repository per aggregate/entity as required. Do
not create ports, adapters, factories, mappers, interfaces, or “domain
services” unless two implementations or a real boundary exists. No dozens of
empty abstractions, CQRS, event sourcing, or internal event bus.

## 21. Testing strategy

### Unit tests

- every normalization step and ordering;
- CRLF/CR/Unicode separators, NUL removal, NFC, whitespace, headings, bullets,
  blank lines, Unicode code-point limits, and empty results;
- alias matching for Java/C++/C#/.NET/Node.js and boundary false positives;
- alias collision/startup failure;
- required/preferred/mentioned cues and precedence;
- duplicate skill elimination and deterministic canonical-ID order;
- metadata and canonical URL normalization;
- SHA-256 content/deduplication/request fingerprint known vectors;
- same logical input repeatability;
- cursor encode/decode/filter mismatch;
- no-op version comparison; and
- exception-to-error mapping without rejected raw content.

### Web/API tests

Use MockMvc with the real request ID/security/error filters and mocked
application service where the database is irrelevant:

- JSON/content type/size and Bean Validation;
- 401 precedence before resource disclosure;
- stable error envelope for parsing, validation, 404, 409, 412, 413, 428, and
  500;
- accepted/generated/rejected Request IDs and MDC cleanup;
- API key not included in logs;
- create `Location`, ETag, replay header;
- conditional GET;
- list limits, sort enum, cursor mismatch, deterministic page contract;
- missing/malformed/stale `If-Match`; and
- OpenAPI contains only the approved endpoints/schemas.

### PostgreSQL integration tests

Use PostgreSQL 16.14 Testcontainers, Flyway, JPA, and real HTTP/service calls:

- fresh Flyway migration, validate, second migrate no-op, Hibernate schema
  validation;
- create and retrieve exact normalized data;
- immutable trigger rejects update/delete;
- all unique/check/foreign-key constraints;
- circular current-version FK ownership;
- canonical URL and current fingerprint duplicate races;
- content hash may repeat when metadata differs;
- create/retrieve/update/version pagination;
- keyset query behavior and stable tie ordering;
- idempotent completed replay;
- same key/different payload conflict;
- two simultaneous same-key creates;
- two simultaneous same-ETag updates with exactly one commit;
- duplicate update conflict;
- rollback after failed version creation;
- no orphan root/version/idempotency rows;
- expiry cleanup bound; and
- index presence plus `EXPLAIN (FORMAT JSON)` plan evidence against a seeded
  dataset. `enable_seqscan=off` may be used only to prove index eligibility,
  not to claim production performance.

### Docker smoke

- build without publishing;
- run PostgreSQL and service in an isolated Compose project;
- verify non-root UID, health, readiness, DB health, and Flyway migration;
- create, replay, GET, update, and history;
- restart the application container and read the same resource;
- confirm no real DeepSeek/network provider call; and
- remove only the CI-created project/volume.

H2 is not a dependency and is not accepted as a PostgreSQL correctness
substitute.

## 22. Testcontainers usage

Use Boot-managed Testcontainers 1.21.4:

- one `PostgreSQLContainer` with the exact PostgreSQL 16.14 image pin;
- Spring Boot `@ServiceConnection` or `DynamicPropertySource`;
- Flyway runs against that container before tests;
- shared container lifecycle aligned with the cached Spring context;
- Maven Failsafe names integration tests `*IT`;
- unit/MockMvc tests do not require Docker; and
- concurrency occurs inside a test with `ExecutorService`, two transactions,
  and a barrier, not by enabling unsupported parallel JUnit container
  lifecycle.

Spring Boot documents Testcontainers as a real backing-service integration
tool and warns about container lifetime versus cached application contexts:
[Spring Boot Testcontainers documentation](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html).

Testcontainers PostgreSQL tests prove SQL behavior. They do not prove a
production backup, high availability, or load capacity.

## 23. Docker design

The future Dockerfile has:

1. a Maven 3.9.16/Eclipse Temurin 21 builder stage;
2. wrapper/dependency cache layers before source copy;
3. `./mvnw -B -ntp verify` and executable-JAR packaging;
4. a Temurin 21 JRE runtime stage pinned by digest at implementation time;
5. only the JAR and a small health-check client in the final image;
6. fixed UID/GID 10001, owned `/app`, and `USER 10001:10001`;
7. JSON-array `ENTRYPOINT`;
8. port 8081;
9. OCI source/revision/version labels; and
10. a health check against Actuator readiness.

The image contains no Maven cache, source tree, compiler, Git, credentials, or
shell initialization secret. The JAR name is fixed during build and copied as
`/app/service.jar`.

Compose applies:

- `read_only: true`;
- `tmpfs: /tmp`;
- `cap_drop: [ALL]`;
- `security_opt: [no-new-privileges:true]`;
- explicit memory/CPU/PID bounds appropriate to local development;
- no privileged mode or Docker socket; and
- the application waits for PostgreSQL health, while readiness remains false
  until Flyway/database checks succeed.

Base-image digests must be selected and recorded during implementation because
digest facts are time-sensitive. Do not invent them in this audit.

## 24. CI design

Add a focused path-filtered
`.github/workflows/jd-normalization-service-ci.yml`; do not alter the production
release workflow.

Jobs:

1. **java-test**
   - checkout;
   - Temurin Java 21;
   - Maven Wrapper cache;
   - `./mvnw -B -ntp verify`;
   - unit/MockMvc plus Testcontainers/Failsafe;
   - upload Surefire/Failsafe reports on failure.
2. **flyway-postgres**
   - may remain inside `java-test` initially;
   - fresh PostgreSQL 16.14, migrate/validate/schema checks;
   - fail if Hibernate attempts schema creation.
3. **docker-build**
   - BuildKit build;
   - no push;
   - inspect configured non-root user and sensitive paths.
4. **docker-smoke**
   - depends on Docker build;
   - create test-only random credentials in runner temp;
   - isolated Compose project and volume;
   - readiness/migration/create/replay/read/update/restart;
   - guaranteed cleanup.
5. **dependency-security**
   - keep `permissions: contents: read`;
   - Maven dependency tree/SBOM;
   - OWASP Dependency-Check or GitHub dependency review with an explicitly
     pinned action and documented vulnerability threshold;
   - repository secret/path scan extended to Java `.env`, `target`, test
     reports, keys, and credentials.

Follow current conventions: no `pull_request_target`, no real provider key, no
production deploy, bounded permissions, concurrency cancellation, test-only
credentials, and repository-safety checks.

Do not publish a container, create a GitHub Release, tag a release, or change
`.github/workflows/release-images.yml` in the first implementation.

## 25. Observability

- Spring Boot structured JSON console logs using built-in structured logging.
- SLF4J MDC `request_id`.
- request completion event: route template, method, status, duration, and
  response size; no query string with sensitive values.
- domain counters: normalization outcome, create/replay/conflict, update/
  optimistic conflict, and normalization duration.
- Actuator liveness and readiness groups.
- readiness includes database/Flyway availability after persistence is added.
- expose only `health`, `health/liveness`, and `health/readiness`.
- health response outside authenticated diagnostics contains status only.

Never log:

- raw or normalized JD text;
- title/company/location or canonical URL by default;
- API or idempotency keys;
- request/duplicate fingerprints;
- response bodies;
- Authorization/Cookie headers; or
- JDBC URLs with credentials.

Prometheus, Grafana, OpenTelemetry export, distributed tracing, and a metrics
stack are rejected from the first implementation. Bounded Actuator/Micrometer
metrics are sufficient evidence.

## 26. Local development

The independent local Compose file will live under
`services/jd-normalization-service/compose.yaml`; it does not modify root
production Compose.

Proposed local topology:

```text
localhost:18082 -> jd-normalization-service:8081
                         |
                         +-> jd-normalization-postgres:5432
```

- Host port 18082 avoids the current public 8080 and FastAPI 8000 conventions.
- PostgreSQL has no host-published port by default.
- PostgreSQL 16.14 has its own named volume and private network.
- `.env.example` contains variable names/placeholders only.
- the real `.env` is ignored and mode-restricted by the developer.
- local startup uses a generated API key and database passwords.
- the service database is not the Personal Job Agent database.
- `docker compose down -v` is documented only for this disposable local
  project, never for Personal Job Agent production.

Phase 1 runs with Maven and no database. Phase 2 adds PostgreSQL through
Testcontainers; Phase 3 adds the isolated service/PostgreSQL Compose project.
No root production Compose or k3s file changes are part of these phases.

## 27. Portfolio value

After implementation, the service should provide evidence of:

- Java 21 records, immutable values, Unicode/code-point handling, and
  cryptographic hashing;
- Spring Boot configuration and Actuator;
- Spring MVC REST contracts, validation, stable errors, headers, conditional
  requests, and OpenAPI;
- Spring Data JPA aggregate persistence;
- PostgreSQL constraints, JSONB, indexes, deferred foreign keys, and query
  plans;
- Flyway-owned schema evolution;
- short transactions and rollback;
- JPA optimistic locking mapped to HTTP;
- database-backed idempotency and completed replay;
- Testcontainers real-database integration and concurrency testing;
- non-root multi-stage Docker images;
- isolated Compose development/smoke; and
- focused GitHub Actions CI and dependency/repository safety.

The strongest evidence is executable tests and migrations, not the presence of
framework names in `pom.xml`.

## 28. Proposed résumé bullets

These bullets are **proposed and must not be used as implemented achievements
until the corresponding code, tests, and CI exist**:

- **Proposed:** Built an independent Java 21/Spring Boot REST service that
  deterministically normalized bounded Job Description text, versioned skill
  dictionaries, and SHA-256 content identities without LLM dependencies.
- **Proposed:** Designed PostgreSQL/Flyway persistence for immutable Job
  Description versions using JPA, database constraints, JSONB skill snapshots,
  and keyset pagination.
- **Proposed:** Implemented database-backed create idempotency and JPA
  optimistic locking, proving replay, conflict, rollback, and two-client race
  behavior with PostgreSQL Testcontainers.
- **Proposed:** Delivered a non-root multi-stage Docker image, isolated local
  Compose environment, Actuator health/readiness, and GitHub Actions build,
  integration, security, and smoke gates.
- **Proposed:** Defined an HTTP-only boundary between a FastAPI modular
  monolith and one bounded Java service, avoiding shared ORM tables and
  preserving retired product-module scope.

## 29. Interview questions

| Likely question | Expected implementation evidence |
|---|---|
| Why is this a service instead of another FastAPI module? | Boundary README/report, independent database/Flyway, no FastAPI dependency, and optional Phase 4 feature flag |
| Why not rewrite the backend in Java? | Scope exclusions and unchanged mature FastAPI behavior |
| Why Spring Boot 3.5 instead of 4.1? | POM/BOM plus documented JUnit 5/Testcontainers compatibility decision and later upgrade path |
| How is normalization deterministic? | Versioned policy/dictionary files, known-vector unit tests, repeatability tests, and no network/LLM dependency |
| Is keyword extraction “AI”? | Response docs and tests showing alias/section heuristics and false-positive limits |
| Why JSONB skills? | Whole-version read contract, bounded immutable arrays, absence of skill search, migration checks, and no GIN index |
| How are duplicate creates race-safe? | Unique current fingerprint/URL constraints and two-transaction integration test |
| How does idempotency differ from Request ID? | Separate filters/table/fingerprints and same-key replay/different-input tests |
| Do you guarantee exactly-once? | Explicit “local committed result only” contract and absence of an external provider side effect |
| How do two updates avoid lost writes? | ETag/If-Match, JPA `@Version`, SQL predicate, and barrier-synchronized Testcontainers test |
| What happens when version insert succeeds but root update fails? | One transaction and rollback test proving no orphan version |
| Why keyset pagination? | Cursor implementation, deterministic tie order, index, seeded page tests, and plan evidence |
| Why not H2? | PostgreSQL-only integration profile and Testcontainers/Flyway tests |
| How is the container hardened? | Dockerfile UID, final-image contents, read-only Compose, dropped capabilities, and smoke inspection |
| How would FastAPI integrate later? | Versioned HTTP client behind a disabled feature flag, no table/session sharing |

An interview answer is not considered evidenced until the referenced artifact
exists and passes CI.

## 30. Implementation phases

### Phase 1: deterministic HTTP core

- Maven/Java 21/Spring Boot skeleton;
- normalization preview endpoint only;
- policy `jd-normalization-v1` and `skills-v1`;
- static internal API key plus safe development mode;
- Request ID, stable errors, validation, OpenAPI, and Actuator;
- unit and MockMvc tests;
- a path-filtered Java unit/web CI job; and
- no PostgreSQL, Flyway, JPA, Docker, or FastAPI change yet.

One PR. Review the exact file set in Section 31 before implementation.

### Phase 2: PostgreSQL persistence and idempotent create

- JPA/Flyway/PostgreSQL dependencies;
- dedicated schema/database configuration;
- root and immutable version model;
- required create idempotency ledger/replay;
- create/read/list/version-history endpoints;
- duplicate fingerprint and canonical URL constraints;
- keyset pagination;
- PostgreSQL Testcontainers migration/repository/API/idempotency tests; and
- extension of the focused Java CI job for Testcontainers.

Use two PRs if needed: Phase 2A for schema/entities/reads and Phase 2B for the
public idempotent create contract. Do not expose a non-idempotent transitional
POST. Do not add concurrent update merely to fill these PRs.

### Phase 3: optimistic update, Docker, and CI

- PUT with ETag/If-Match and JPA `@Version`;
- two-client concurrency and rollback tests;
- bounded idempotency cleanup;
- multi-stage non-root Dockerfile;
- independent local Compose with the service and PostgreSQL;
- Docker smoke;
- expansion of the focused Java workflow for Docker/dependency safety.

Split reliability from Docker/CI if review becomes broad. Do not publish
images.

### Phase 4: optional FastAPI HTTP integration

Only after the independent service proves value:

- disabled-by-default FastAPI feature flag;
- bounded timeout/retry/circuit behavior;
- service-to-service API key delivered outside Git;
- Request ID forwarding;
- no browser cookies or shared database;
- fallback keeps the current Analyze pipeline operational; and
- separate integration contract tests and rollback.

Phase 4 is optional and requires a new design/approval. It is not part of the
first Java implementation.

## 31. Exact Phase 1 file set

No Phase 1 implementation begins until this list is reviewed and approved.
Phase 1 creates exactly these files:

```text
.github/workflows/
  jd-normalization-service-ci.yml
services/jd-normalization-service/
  .env.example
  .gitignore
  README.md
  pom.xml
  mvnw
  mvnw.cmd
  .mvn/
    wrapper/
      maven-wrapper.properties
  src/
    main/
      java/io/github/hkjokerz/jobagent/jdnormalization/
        JdNormalizationServiceApplication.java
        config/
          ServiceProperties.java
        normalization/
          JobDescriptionNormalizer.java
          NormalizationPolicy.java
          NormalizationResult.java
          SkillDictionary.java
          SkillDictionaryLoader.java
          SkillExtractor.java
          TextNormalizer.java
          UrlNormalizer.java
        security/
          InternalApiKeyFilter.java
          SecurityConfiguration.java
        web/
          ApiExceptionHandler.java
          NormalizationController.java
          RequestIdFilter.java
          dto/
            ApiErrorResponse.java
            NormalizeJobDescriptionRequest.java
            NormalizeJobDescriptionResponse.java
      resources/
        application.yml
        skills/
          skills-v1.json
    test/
      java/io/github/hkjokerz/jobagent/jdnormalization/
        JdNormalizationServiceApplicationTest.java
        normalization/
          JobDescriptionNormalizerTest.java
          SkillDictionaryLoaderTest.java
          SkillExtractorTest.java
          TextNormalizerTest.java
          UrlNormalizerTest.java
        web/
          NormalizationApiWebTest.java
          RequestIdAndErrorWebTest.java
          SecurityWebTest.java
      resources/
        application-test.yml
        skills/
          invalid-duplicate-aliases.json
```

`pom.xml` Phase 1 dependencies are limited to Boot Web, Validation, Security,
Actuator, configuration processor, Springdoc WebMVC API, and Boot Test.
JPA/Flyway/PostgreSQL/Testcontainers are deliberately absent until Phase 2.

Phase 1 changes no existing Backend, Frontend, Alembic, Compose, deployment,
release, or production workflow file. It adds only the new path-filtered Java
workflow named above.

## 32. Expected later files

Names are proposed and may be refined in the specific phase review, but they
are separate from Phase 1.

### Phase 2 additions/updates

```text
services/jd-normalization-service/
  src/main/java/io/github/hkjokerz/jobagent/jdnormalization/
    jobdescription/
      JobDescription.java
      JobDescriptionVersion.java
      JobDescriptionRepository.java
      JobDescriptionVersionRepository.java
      JobDescriptionService.java
      JobDescriptionView.java
    idempotency/
      IdempotencyRecord.java
      IdempotencyRepository.java
      IdempotencyService.java
      RequestFingerprint.java
    pagination/
      CursorCodec.java
    web/
      JobDescriptionController.java
      dto/
        CreateJobDescriptionRequest.java
        JobDescriptionPageResponse.java
        JobDescriptionResponse.java
        JobDescriptionVersionResponse.java
        JobDescriptionVersionPageResponse.java
  src/main/resources/db/migration/
    V1__create_job_description_schema.sql
    V2__add_request_idempotency.sql
  src/test/java/io/github/hkjokerz/jobagent/jdnormalization/
    support/
      PostgresContainerConfiguration.java
      PostgresIntegrationTest.java
    jobdescription/
      FlywayMigrationIT.java
      JobDescriptionApiIT.java
      JobDescriptionRepositoryIT.java
      PaginationIT.java
    idempotency/
      IdempotentCreateIT.java
      RequestFingerprintTest.java
```

Expected updates: Phase 1 `pom.xml`, `README.md`, `.env.example`,
`application.yml`, error handler, OpenAPI/controller DTOs, service tests, and
the focused Java workflow.

### Phase 3 additions/updates

```text
services/jd-normalization-service/
  .dockerignore
  Dockerfile
  compose.yaml
  docker/
    postgres/
      001-create-roles.sh
  scripts/
    docker-smoke.sh
  src/main/java/io/github/hkjokerz/jobagent/jdnormalization/
    web/dto/
      UpdateJobDescriptionRequest.java
  src/test/java/io/github/hkjokerz/jobagent/jdnormalization/
    jobdescription/
      ConcurrentUpdateIT.java
      TransactionRollbackIT.java
      QueryPlanIT.java
```

Expected updates: `pom.xml`, Compose, README, application configuration,
JobDescription service/controller/entities, security/error/OpenAPI tests, and
the focused Java workflow. The root repository-safety workflow changes only if
its path rules require a focused Java addition.

### Optional Phase 4 files

```text
backend/app/integrations/
  jd_normalization_client.py
backend/
  test_jd_normalization_integration.py
```

Potential updates would include Backend configuration/example environment,
Analyze orchestration behind a default-off flag, Project Knowledge/
architecture documentation, and isolated Compose test support. Exact Phase 4
files require a new audit; this report does not authorize them.

## 33. Risks

- A second language/build/runtime increases maintenance and CI time.
- The capability may remain too small to justify a network boundary; Phase 1
  evidence should be reviewed before persistence work.
- Deterministic aliases create false positives/negatives and lexical
  required/preferred classification can misread prose.
- Unicode and URL normalization changes can alter hashes; policy versions and
  known vectors are essential.
- A root-level current duplicate fingerprint is a product rule. Same text and
  metadata cannot coexist as two current resources even with different URLs.
- Canonical URL immutability may be too strict if source URLs are frequently
  corrected; do not relax it without version-history semantics.
- The deferred cyclic FK is strong but less familiar; migration and fresh
  schema tests must prove Hibernate insert/flush behavior.
- JSONB skills are poor for future skill-centric analytics; no such API exists
  now.
- Full historical text pages can be large despite limits.
- Static API key mode has one principal, no per-user ownership, and is not
  appropriate for public exposure.
- Stored JD text may be sensitive or copyrighted. Retention/deletion/privacy
  requirements must be decided before real multi-user or public use.
- Idempotency response JSON consumes database space; size/retention/cleanup
  bounds must be tested.
- Spring Boot 3.5 is selected for a compatible JUnit 5 baseline rather than the
  newest framework major. A future upgrade needs its own dependency/test PR.
- Testcontainers and Docker require a working container runtime in CI/local
  development.
- No FastAPI integration in initial phases means the service is portfolio
  evidence, not a production dependency. That is intentional.

## 34. Rejected alternatives

- Redis application read cache: rejected by the merged audit and unnecessary
  here.
- Kafka, RabbitMQ, another broker, or asynchronous ingestion: no external side
  effect or throughput requirement.
- Elasticsearch or PostgreSQL full-text search: no product search requirement.
- Kubernetes, k3s, service mesh, or sidecars: staging is intentionally deferred
  and the independent local service does not justify them.
- Java AI framework or LLM call: normalization must be deterministic.
- Java rewrite of FastAPI: disproportionate risk and no bounded need.
- shared SQLAlchemy/Hibernate tables or one migration history: two schema
  owners and unsafe coupling.
- restored Jobs/Rankings/Applications/Approvals/Tasks: contradicts the product
  retirement boundary.
- one broad “microservices architecture” claim: inaccurate for one modular
  monolith plus one bounded service.
- Gradle: no repository evidence outweighs Maven’s simpler conventional POM.
- Spring Boot 4.1 in Phase 1: would change the requested JUnit 5 baseline and
  several ecosystem majors at once.
- H2 integration tests: cannot prove PostgreSQL JSONB, deferred constraints,
  expression indexes, locking, or Flyway SQL.
- in-process synchronization: fails with multiple JVMs and process restarts.
- pessimistic locking by default: unnecessary at expected contention and hides
  the optimistic-lock portfolio evidence.
- global uniqueness on `content_hash`: would incorrectly reject identical text
  with different explicit metadata.
- relational skill catalog and GIN index: no initial query uses them.
- OFFSET pagination: degrades with page depth and shifts under inserts.
- DELETE endpoint: retention/erasure semantics are not approved.
- browser Session cookie forwarding: violates the service boundary.
- new OAuth/user-management system: no public/multi-client requirement.
- modifying current production Compose/release workflow: explicitly out of
  scope.

## 35. Confirmation that runtime application code was not changed

Confirmed. This audit changes only this Work Report and
`docs/work-reports/README.md`. Backend, Frontend, Java runtime code, tests,
dependencies, schema migrations, Docker assets, Compose files, scripts, and
workflows were not changed.

## 36. Confirmation that production was untouched

Confirmed. No production host, API, database, Redis instance, container,
volume, runtime file, credential, log, backup, deployment, release, tag, or
traffic route was accessed or modified. The prior documentation PR merge
changed GitHub repository history only and its main CI used isolated test
resources.

## 37. Confirmation that no cloud resource was created

Confirmed. No cloud compute, storage, database, network, Kubernetes, managed
service, DNS, certificate, or other infrastructure resource was created.
The authorized GitHub documentation branch/PR is repository metadata, not a
deployed cloud resource.

## 38. Confirmation that real DeepSeek was not called

Confirmed. This was a repository/documentation audit. No DeepSeek credential
was read and no real DeepSeek or other LLM provider request was made.

## Audit validation

| Check | Result |
|---|---|
| Local `main` equals `origin/main` at the recorded starting commit | Passed |
| Version 2.0.4 code/docs/tag/release evidence | Passed |
| Alembic heads command | Passed: `20260724_06 (head)` |
| Prior Redis audit changed only Work Report documentation | Passed |
| Prior audit PR checks before merge | Passed: 10 of 10 |
| Main CI after the prior audit merge | Passed: 10 of 10 |
| Required Work Report sections 1–38 present in order | Passed |
| Relative Work Report index links resolve | Passed |
| Thirteen primary/reference source URLs return successful HTTP responses | Passed |
| Markdown trailing-whitespace scan | Passed |
| `git diff --check` | Passed |
| Current audit file scope | Passed: this Work Report and its index only |

No application test suite was run locally because this branch changes no
runtime, dependency, schema, test, Docker, Compose, script, or workflow file.
The documentation pull request must still complete all repository-required
GitHub checks before handoff and must not be merged as part of this audit.
