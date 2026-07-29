# JD Normalization Service

The JD Normalization Service is a small, independent Java 21 portfolio
service. It deterministically normalizes bounded Job Description text and owns
a dedicated PostgreSQL database for an immutable read model.

The honest repository architecture remains one existing FastAPI modular
monolith plus this one bounded Java service. The Java service does not connect
to the Personal Job Agent database, share SQLAlchemy tables, replace the
FastAPI Analyze pipeline, or constitute a broad microservice platform.

## Implemented scope

Phase 1 remains unchanged:

```text
POST /api/v1/job-descriptions/normalize
```

Phase 2A adds read-only database APIs:

```text
GET /api/v1/job-descriptions/{id}
GET /api/v1/job-descriptions
GET /api/v1/job-descriptions/{id}/versions
```

There is no public persistence `POST`, `PUT`, `PATCH`, or `DELETE` endpoint.
There is no idempotency key, request-idempotency table, update path, seed
endpoint, Dockerfile, Compose service, FastAPI integration, Redis cache,
DeepSeek/LLM call, image publication, release, or deployment.

Phase 2B public idempotent create behavior is planned and not implemented.
This service is not approved for public or production exposure.

## Requirements

- Java 21
- PostgreSQL 16 for manual runtime use
- Docker access for the PostgreSQL 16.14 Testcontainers integration suite
- POSIX shell or Windows PowerShell/Command Prompt
- Internet access for the Maven Wrapper's first dependency download

The repository-safe Maven Wrapper downloads Maven 3.9.16 and does not commit a
wrapper JAR.

## Dedicated database

The service conceptually owns a database named `jd_normalization`. It must use
database roles and credentials separate from the Personal Job Agent
application.

Required runtime configuration:

```text
JD_NORMALIZATION_JDBC_URL
JD_NORMALIZATION_DB_USERNAME
JD_NORMALIZATION_DB_PASSWORD
JD_NORMALIZATION_FLYWAY_USERNAME
JD_NORMALIZATION_FLYWAY_PASSWORD
```

The application credentials are used by JPA reads. The Flyway credentials may
be a separate migration role. No password has a repository default. The
tracked `.env.example` contains names only.

Flyway migration `V1__create_job_description_schema.sql` owns:

- `job_descriptions`, the mutable aggregate pointer;
- `job_description_versions`, immutable committed snapshots;
- deferred ownership and exact-current-version foreign keys;
- unique canonical URL and current deduplication fingerprint constraints;
- hash, version, policy, JSONB-array, and lock-version checks;
- keyset, version-history, canonical URL, content hash, and metadata indexes;
- a trigger rejecting every version-row `UPDATE` and `DELETE`.

Flyway migrations are append-only after merge. Hibernate uses
`ddl-auto=validate`; it does not generate the schema. Timestamps use UTC,
open-in-view is disabled, Flyway clean and baseline are disabled, and SQL
logging is off by default.

## Safe local startup

Create the dedicated database and least-privilege roles outside this
repository. Export only local credentials, then generate a fresh API key of at
least 32 random bytes:

```bash
export JD_NORMALIZATION_JDBC_URL='jdbc:postgresql://127.0.0.1:5432/jd_normalization'
export JD_NORMALIZATION_DB_USERNAME='jd_normalization_app'
export JD_NORMALIZATION_FLYWAY_USERNAME='jd_normalization_migrator'
# Load JD_NORMALIZATION_DB_PASSWORD and JD_NORMALIZATION_FLYWAY_PASSWORD from
# a local secret manager without echoing or committing either value.
export JD_NORMALIZATION_API_KEY="$(openssl rand -base64 32)"
./mvnw -B -ntp spring-boot:run
```

Do not put real values in Git, shell history, screenshots, or examples.

The default binding is `127.0.0.1:8091`. Authentication can be disabled only
when the active Spring profile is exactly `dev` and binding remains loopback:

```bash
SPRING_PROFILES_ACTIVE=dev \
JD_NORMALIZATION_AUTH_DISABLED=true \
JD_NORMALIZATION_BIND_ADDRESS=127.0.0.1 \
./mvnw -B -ntp spring-boot:run
```

The development-only mode is unsafe for public or shared-network exposure.
CORS is disabled, and browser session cookies are not authentication.

## Normalize preview

Requests are UTF-8 JSON no larger than 512 KiB:

```json
{
  "raw_text": "Senior Backend Engineer\r\nRequired:\r\n- Java 21",
  "metadata": {
    "title": "Senior Backend Engineer",
    "company": "Example Ltd",
    "location": "Hong Kong",
    "canonical_url": "https://jobs.example.test/backend-engineer"
  }
}
```

`raw_text` is required and limited to 100,000 Unicode code points. Title,
company, and location are limited to 200 code points. Canonical URLs must
normalize to absolute HTTPS with at most 2,048 ASCII characters; normalization
never contacts the host.

```bash
curl --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-normalize-1" \
  --data '{"raw_text":"Required:\r\n- Java 21"}' \
  http://127.0.0.1:8091/api/v1/job-descriptions/normalize
```

`jd-normalization-v1` removes NUL, applies NFC, normalizes line separators,
collapses bounded whitespace, preserves headings/bullets/line order, collapses
blank lines, and emits no trailing newline. It does not translate, spell-check,
infer metadata, rewrite prose, use network access, or claim semantic
understanding. The content hash is
`SHA-256(UTF-8(normalized_text))`.

The reviewed `skills-v1` Git artifact provides deterministic lexical matching.
Required overrides preferred, preferred overrides mentioned, and each list is
sorted by canonical skill ID. This is bounded keyword classification, not AI.

## Current resource and ETag

```bash
curl --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H "X-Request-ID: local-read-1" \
  -D - \
  http://127.0.0.1:8091/api/v1/job-descriptions/00000000-0000-4000-8000-000000000001
```

The response joins the aggregate to its exact current immutable version. It
contains the aggregate ID, normalized canonical URL, optimistic lock version,
current version number, normalized text, lowercase SHA-256 content hash,
policy/dictionary versions, bounded skill snapshots, normalized metadata, and
timestamps. Internal fingerprints and byte arrays are never exposed.

The endpoint returns a strong ETag derived from
`optimistic_lock_version`—initially `"0"`. One matching strong
`If-None-Match` returns `304` with no body:

```bash
curl \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H 'If-None-Match: "0"' \
  http://127.0.0.1:8091/api/v1/job-descriptions/00000000-0000-4000-8000-000000000001
```

## Keyset list

The list endpoint returns summaries only; normalized text and skill arrays are
excluded. `limit` defaults to 20 and is bounded to 1–100. Supported sort values
are `created_at_desc` (default) and `created_at_asc`.

Exact filters:

- case-insensitive normalized `title`, `company`, and `location`;
- lowercase 64-character `content_hash`;
- normalized absolute-HTTPS `canonical_url`.

```bash
curl --get --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  --data-urlencode 'limit=20' \
  --data-urlencode 'sort=created_at_desc' \
  --data-urlencode 'company=Example Ltd' \
  http://127.0.0.1:8091/api/v1/job-descriptions
```

Pagination uses `(created_at,id)` keysets and fetches `limit + 1`; it never uses
`OFFSET` and does not calculate an unrequested total. `next_cursor` is
Base64URL-encoded versioned JSON containing the sort, last timestamp/UUID, and
a SHA-256 fingerprint of normalized filters. It contains no secret or
authorization meaning. Changing filters or sort returns
`400 INVALID_CURSOR`.

## Immutable version history

Version history defaults to `limit=10`, is bounded to 1–25, and supports
`version_desc` (default) or `version_asc`. Its opaque versioned cursor performs
keyset pagination by `version_number`.

```bash
curl --get --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  --data-urlencode 'limit=10' \
  --data-urlencode 'sort=version_desc' \
  http://127.0.0.1:8091/api/v1/job-descriptions/00000000-0000-4000-8000-000000000001/versions
```

The API returns committed immutable versions only. It provides no mutation or
deletion operation.

## Request IDs and errors

Clients may send exactly one `X-Request-ID` matching:

```text
[A-Za-z0-9][A-Za-z0-9._:-]{0,63}
```

Otherwise the service creates a trusted UUIDv4. The value is returned on every
response and placed in logging MDC. It is correlation metadata, not
authentication or deduplication.

Every API error uses:

```json
{
  "error": {
    "code": "INVALID_CURSOR",
    "message": "The pagination cursor is invalid.",
    "request_id": "local-read-1",
    "details": {}
  }
}
```

Read-specific codes are `JOB_DESCRIPTION_NOT_FOUND`, `INVALID_CURSOR`, and
`DATABASE_UNAVAILABLE`. Errors and logs omit SQL, constraint names, JDBC URLs,
database users/hosts, exception text, JD content, metadata values, canonical
URLs, hashes, API keys, authorization headers, request/response bodies,
filesystem paths, and stack traces.

## Health and OpenAPI

Unauthenticated status-only probes:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Liveness contains only application liveness state and is not failed by a
temporary database outage. Readiness requires PostgreSQL plus the migrated V1
schema. No other Actuator endpoint is exposed.

OpenAPI JSON is `GET /v3/api-docs`, protected by the internal key outside
`dev`. It documents only the normalize and three approved read endpoints,
Bearer authentication, `X-Request-ID`, conditional ETag behavior, and shared
errors. Swagger UI is not included.

## Tests

Unit, normalization, cursor, MockMvc, security, and application-context tests
run without Docker:

```bash
./mvnw -B -ntp test
```

Full verification requires Docker and runs PostgreSQL 16.14 Testcontainers
through Maven Failsafe:

```bash
./mvnw -B -ntp verify
```

Target only integration tests:

```bash
./mvnw -B -ntp -DskipTests -Dit.test='*IT' failsafe:integration-test failsafe:verify
```

The integration suite performs fresh Flyway migration/validation, Hibernate
schema validation, direct constraint/trigger checks, current and history
reads, ETag/304, exact filters, keyset pagination, rollback checks, and
`EXPLAIN (FORMAT JSON)` index-eligibility evidence. It uses deterministic
synthetic rows and never connects to production. No H2, Redis, DeepSeek, or
arbitrary external network service is used.

## Logging

The console uses Spring Boot structured ECS JSON. Request completion records
include trusted request ID, method, route template where available, status,
duration, and bounded response size. Normalization outcome records contain
only policy versions, counts, code-point count, and duration. JD text,
metadata, URLs, content hashes, credentials, SQL, and complete bodies are not
logged.
