# JD Normalization Service

The JD Normalization Service is a small, independent Java 21 portfolio
service. It deterministically normalizes bounded Job Description text and owns
a dedicated PostgreSQL database for idempotent creation, conditional updates,
and immutable version history.

The honest repository architecture remains one existing FastAPI modular
monolith plus this one bounded Java service. The Java service does not connect
to the Personal Job Agent database, share SQLAlchemy tables, replace the
FastAPI Analyze pipeline, or constitute a broad microservice platform.

## Implemented scope

Phase 1 remains unchanged:

```text
POST /api/v1/job-descriptions/normalize
```

Phase 2A read APIs remain:

```text
GET /api/v1/job-descriptions/{id}
GET /api/v1/job-descriptions
GET /api/v1/job-descriptions/{id}/versions
```

Phase 2B create remains:

```text
POST /api/v1/job-descriptions
```

Phase 3A adds exactly one conditional replacement endpoint:

```text
PUT /api/v1/job-descriptions/{id}
```

There is no `PATCH`, `DELETE`, bulk update, restore, version deletion, seed
endpoint, FastAPI integration, Redis cache, DeepSeek/LLM call, image
publication, release, or deployment. Phase 3B adds a local, independently
scoped container environment without changing any HTTP API.
This service is not approved for public or production exposure.

## Requirements

- Java 21
- PostgreSQL 16 for manual runtime use
- Docker access for the PostgreSQL 16.14 Testcontainers integration suite
- Docker Engine with Compose v2 for the isolated container environment
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

Flyway migration `V2__create_request_idempotency.sql` owns:

- the `request_idempotency` processing/completed ledger;
- operation plus SHA-256 key-hash uniqueness;
- exact 32-byte hash, state/response, JSON-object, HTTP-status, lease, and
  retention checks;
- a restricted optional Job Description foreign key;
- partial indexes for expired completed cleanup and processing leases.

Flyway migrations are append-only after merge. Hibernate uses
`ddl-auto=validate`; it does not generate the schema. Timestamps use UTC,
open-in-view is disabled, Flyway clean and baseline are disabled, and SQL
logging is off by default.

Phase 3A requires no migration. V1 already permits updates to the aggregate
pointer and version numbers greater than one, its deferred constraints verify
the exact current immutable version at commit, and its trigger permits INSERT
while rejecting version UPDATE/DELETE. V2 is limited to create idempotency.
Flyway head therefore remains V2; no empty V3 was created.

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

## Independent container environment

The Phase 3B environment lives entirely in this service directory. It does
not join a Personal Job Agent network, mount a host directory, expose
PostgreSQL, reuse production credentials, or modify the repository-root
production Compose project. The application is published only on loopback at
`127.0.0.1:18082` by default.

The container architecture has three services:

- PostgreSQL 16.14 owns the dedicated `jd_normalization` database in an
  isolated named volume and is healthy before migration starts.
- A one-shot Flyway 11.7.2 migration image contains exactly append-only V1 and
  V2, runs `migrate` followed by `validate`, and must exit successfully.
- The application image starts only after migration succeeds, disables its
  embedded Flyway runner, and retains Hibernate `ddl-auto=validate`.

The application and migration targets are built from the same multi-stage
`Dockerfile` and repository revision. The builder uses Java 21 and the Maven
Wrapper. The runtime image contains only the executable Spring Boot JAR and a
Java 21 JRE; it contains no source tree, compiler, Maven repository, test
reports, Git metadata, or environment file. The migration image contains only
the compatible Flyway runtime, the two SQL migrations, and its fixed
`migrate`/`validate` entrypoint. All builder, runtime, migration, and
PostgreSQL base references are pinned to immutable multi-architecture
digests.

Generate fresh local-only credentials without printing them:

```bash
cd services/jd-normalization-service
./scripts/generate-compose-env.sh
```

The command creates ignored `.env.compose` mode `0600`. Its application API
key and three database credentials are generated independently. The tracked
`.env.compose.example` contains placeholders only. Never copy Personal Job
Agent or production credentials into this file.

Validate and start the isolated environment:

```bash
docker compose --env-file .env.compose config --quiet
docker compose --env-file .env.compose up --build --wait app
```

Compose orders startup as PostgreSQL health, successful one-shot migration,
then application readiness; it does not use arbitrary sleeps. The migration
role can create and alter this dedicated schema. The runtime role receives
only schema usage and table/sequence data privileges. Rerunning migration is
a no-op followed by validation:

```bash
docker compose --env-file .env.compose run --rm migration
```

Inspect the status-only health endpoints:

```bash
curl --fail http://127.0.0.1:18082/actuator/health/liveness
curl --fail http://127.0.0.1:18082/actuator/health/readiness
```

Readiness includes database availability and schema validation. Liveness
continues to describe the JVM/application process during a transient database
outage. No probe returns credentials or database details.

Use the existing normalize/create/read/update examples below by replacing
port `8091` with `18082`. The same authentication, Idempotency-Key, If-Match,
ETag, replay, immutable-history, and error contracts apply; containerization
adds no endpoint or API shortcut.

The application runs as numeric user `10001:10001` with a read-only root
filesystem, a bounded `/tmp` tmpfs, all Linux capabilities dropped,
`no-new-privileges`, no host network, no privileged mode, no Docker socket,
and no host mounts. Compose provides a 768 MiB memory limit, 1 CPU, 256 PID
limit, and a bounded graceful stop by default. These are local safety
defaults, not production sizing or a high-availability claim. PostgreSQL
retains its required writable data volume and has a bounded 512 MiB/256 PID
configuration.

Run the deterministic end-to-end validation in an explicitly ephemeral,
uniquely named project:

```bash
./scripts/container-smoke.sh --ephemeral .env.compose
```

It builds and inspects both images, starts PostgreSQL, migrates, verifies
unauthorized and authorized normalize behavior, creates and exactly replays a
resource, performs a conditional update and stale-write check, verifies
versions 1 and 2, restarts the application, reruns migration, restarts
PostgreSQL, confirms persisted data, and inspects health/restart/security
state. It uses synthetic data only, prints no secret or full response body,
and removes only its unique ephemeral Compose project and volume.

For ordinary local use, an application restart and normal Compose stop/start
preserve the named database volume:

```bash
docker compose --env-file .env.compose restart app
docker compose --env-file .env.compose stop
docker compose --env-file .env.compose start
```

`docker compose --env-file .env.compose down` removes containers and networks
but preserves data. Delete the named volume only after verifying that it is
the isolated local project and that its synthetic data is no longer needed.
Never use broad Docker prune commands, and do not use `down --volumes` against
any production or unrelated project.

This environment is for local and CI validation. No image is published, no
registry login is required, there is no reverse proxy/TLS/public DNS,
Kubernetes, FastAPI integration, production deployment, or claim of public
Internet readiness.

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

## Idempotent create

`POST /api/v1/job-descriptions` accepts the same bounded body as normalize and
requires exactly one:

```text
Idempotency-Key: [A-Za-z0-9][A-Za-z0-9._:-]{15,127}
```

The total length is 16–128 ASCII characters. UUIDv4 is recommended but is not
required. The key is not authentication, authorization, a request ID, or an
object ID. Its raw value is never stored, logged, or returned. PostgreSQL stores:

```text
SHA-256(UTF-8("jd-normalization:idempotency-key:v1\0" + raw_key))
```

Example:

```bash
curl --fail-with-body \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H "Idempotency-Key: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-create-1" \
  --data '{"raw_text":"Required:\n- Java 21","metadata":{"title":"Backend Engineer"}}' \
  -D - \
  http://127.0.0.1:8091/api/v1/job-descriptions
```

The first success returns `201 Created`, `Location`, strong `ETag: "0"`,
`Cache-Control: no-store`, and the same current-resource JSON shape as
`GET /api/v1/job-descriptions/{id}`. One PostgreSQL transaction creates the
root, immutable version 1, and completed replay record. No network or provider
call occurs.

A completed retry with the same key and canonical request returns the stored
status, JSON body, `Location`, and `ETag` and adds
`Idempotency-Replayed: true`. The request is still authenticated, validated,
normalized, and fingerprinted before replay; normalization, inserts, and
response construction are not repeated after the ledger lookup.

The ledger uses only `processing` and `completed`. A short committed claim
transaction prevents process-local locking assumptions. An active lease
returns `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with bounded `Retry-After`.
An expired lease can be atomically taken over with a new attempt token, and a
stale token cannot finalize. This differs from the FastAPI DeepSeek
indeterminate state: Phase 2B has no external side effect, so every business
mutation can safely occur inside the final PostgreSQL transaction.

Same-key/different-request returns `409 IDEMPOTENCY_KEY_REUSED`. Canonical URL
or current deduplication uniqueness returns
`409 JOB_DESCRIPTION_ALREADY_EXISTS` with only an authenticated resource ID
and `canonical_url` or `deduplication_fingerprint` category. Conflict-aware
`INSERT ... ON CONFLICT DO NOTHING` plus a bounded lookup avoids PostgreSQL's
aborted-transaction state, rolls back no committed aggregate, and completes
the accepted key with a replayable stable 409.

The three hashes are separate:

- `content_hash` is SHA-256 of UTF-8 normalized text;
- `jd-deduplication:v1` hashes canonical JSON covering normalized text,
  normalized metadata, policy/dictionary versions, and ordered skill IDs;
- `jd-create-request:v1` hashes separate canonical JSON covering the create
  contract and all effective deterministic normalization inputs/outputs.

Canonical JSON has stable key/array order and explicit nulls. It contains no
timestamp, request ID, credential, idempotency key, generated UUID, or database
state. Metadata changes may preserve `content_hash` while changing the
deduplication and request fingerprints.

Completed results default to 24-hour retention, processing leases default to
30 seconds, cleanup deletes at most 100 expired completed rows per best-effort
create-path pass, and processing rows are never cleanup targets. Stored JSON is
limited to 256 KiB by application and database checks. Cleanup delay does not
change replay correctness.

Idempotency uniqueness is scoped to operation plus key hash. The service has
one internal caller security scope; this is not user-level multi-tenancy and
the ledger is not an authorization mechanism.

## Conditional full replacement

`PUT /api/v1/job-descriptions/{id}` accepts the same bounded body as normalize
and create, but it represents the complete replacement state. Optional metadata
omitted from the request becomes `null`; PUT is not a partial patch.

PUT requires exactly one strong `If-Match` value in canonical quoted
nonnegative-decimal form:

```text
If-Match: "0"
```

`"0"`, `"1"`, and `"42"` are examples. Missing If-Match returns
`428 PRECONDITION_REQUIRED`. Weak, wildcard, unquoted, negative, non-decimal,
overflowing, comma-separated, excessive-length, or multiple values return
`400 INVALID_IF_MATCH`. A well-formed stale value returns
`412 PRECONDITION_FAILED` without disclosing the current ETag; an authenticated
GET can retrieve current state.

Example:

```bash
curl --fail-with-body \
  -X PUT \
  -H "Authorization: Bearer ${JD_NORMALIZATION_API_KEY}" \
  -H 'If-Match: "0"' \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: local-update-1" \
  --data '{"raw_text":"Required:\n- Java 21\n- PostgreSQL","metadata":{"title":"Platform Engineer"}}' \
  -D - \
  http://127.0.0.1:8091/api/v1/job-descriptions/00000000-0000-4000-8000-000000000001
```

The update path authenticates and normalizes the full replacement, locks the
root row, then loads its exact current immutable version using a fresh
READ COMMITTED statement. It rejects a stale aggregate version before no-op
detection. For a change, one transaction:

1. generates one UUIDv4 and assigns the next contiguous version number;
2. conditionally updates the root with
   `WHERE id = ? AND optimistic_lock_version = ?`;
3. increments the same column mapped by JPA `@Version`;
4. changes canonical URL, current version, fingerprint, and `updated_at`;
5. inserts exactly one immutable successor;
6. reads back the exact current identity before deferred constraints commit.

Two processes using the same ETag cannot both commit. A root update or version
insert failure rolls the entire transaction back, so no orphan history row or
partially advanced pointer remains. There is no network or provider call in
the transaction.

A changed update returns `200 OK`, the incremented strong ETag,
`Cache-Control: no-store`, and the same current-resource representation as GET.
The first update changes ETag `"0"` to `"1"` and creates version 2; later
changed updates create contiguous immutable versions. Previous versions remain
byte-for-byte unchanged and readable through history.

If the normalized replacement and root state are already identical, PUT still
requires a current If-Match but returns the existing 200 body and ETag without
inserting a version, incrementing the lock, changing `updated_at`, or issuing a
database write. Stale If-Match is never accepted as a no-op.

Canonical URL and current-deduplication uniqueness remain PostgreSQL
correctness boundaries. A conflict returns
`409 JOB_DESCRIPTION_ALREADY_EXISTS` with only the authenticated existing ID
and `canonical_url` or `deduplication_fingerprint` category. The target root,
history, and ETag remain unchanged.

POST and PUT solve different retry problems:

- POST requires `Idempotency-Key` to suppress duplicate aggregate creation;
- PUT requires `If-Match` to prevent lost replacement updates and does not use
  the create ledger.

Updating an aggregate never rewrites its completed create record. Replaying
the original POST after later updates intentionally returns the historical
stored creation response, Location, and ETag `"0"`, not the latest current
state.

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
`DATABASE_UNAVAILABLE`. Create adds `IDEMPOTENCY_KEY_REQUIRED`,
`IDEMPOTENCY_KEY_INVALID`, `IDEMPOTENCY_KEY_REUSED`,
`IDEMPOTENCY_REQUEST_IN_PROGRESS`, `IDEMPOTENCY_PERSISTENCE_FAILED`, and
`JOB_DESCRIPTION_ALREADY_EXISTS`. Conditional update adds
`PRECONDITION_REQUIRED`, `INVALID_IF_MATCH`, and `PRECONDITION_FAILED`.
Errors and logs omit SQL, constraint names, JDBC URLs, database users/hosts,
exception text, JD content, metadata values, canonical URLs, hashes, API keys,
authorization headers, request/response bodies, filesystem paths, and stack
traces.

## Health and OpenAPI

Unauthenticated status-only probes:

```text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Liveness contains only application liveness state and is not failed by a
temporary database outage. Readiness requires PostgreSQL plus the migrated V2
schema. No other Actuator endpoint is exposed.

OpenAPI JSON is `GET /v3/api-docs`, protected by the internal key outside
`dev`. It documents only normalize, idempotent create, conditional full
replacement, and the three approved read endpoints, including Idempotency-Key
and If-Match grammar, replay/conflict behavior, response headers, Bearer
authentication, `X-Request-ID`, conditional ETag behavior, and shared errors.
Swagger UI is not included and CORS remains disabled.

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
./mvnw -B -ntp test-compile \
  -Dit.test='*IT' \
  failsafe:integration-test failsafe:verify
```

The integration suite performs fresh V1+V2 migration, isolated V1-to-V2
upgrade, Flyway validation/no-op migration, V1/V2 checksum locking, Hibernate
schema validation, ledger constraints/indexes, create/replay/duplicate API
behavior, If-Match parsing, changed/no-op replacement, immutable version 2 and
3 history, separate-session create/update concurrency, lease takeover,
stale-token rejection, duplicate update races, bounded cleanup, transaction
rollback, all prior reads, ETag/304, filters, pagination, and
`EXPLAIN (FORMAT JSON)` index evidence. It uses PostgreSQL 16.14 with
deterministic synthetic rows and never connects to production. No H2, Redis,
DeepSeek, or arbitrary external network service is used.

CI also validates the Compose model and runs the isolated ephemeral container
smoke after Maven verification. It builds local application and migration
images, generates CI-only secrets, proves non-root/read-only execution,
readiness ordering, migration idempotence, API behavior, restart persistence,
and targeted cleanup. It performs no registry login, image publication,
release, or deployment.

## Logging

The console uses Spring Boot structured ECS JSON. Request completion records
contain trusted request ID, route template, status, duration, replay boolean,
stable idempotency outcome, and a created resource ID only for a newly created
authenticated resource. Normalization records contain duration only. JD text,
metadata, URLs, all fingerprints/hashes, raw idempotency keys, credentials,
SQL, constraint names, and request/response bodies are not logged.
