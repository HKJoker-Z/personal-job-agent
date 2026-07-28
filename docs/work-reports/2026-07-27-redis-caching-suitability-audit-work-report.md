# Redis Caching Suitability Audit Work Report

## 1. Executive decision

**Recommendation: do not implement a Redis read cache in the current
production design.**

Project Knowledge search is the strongest future candidate. Its current
checked-in corpus produced a 49.629 ms median and 55.227 ms p95 authenticated
application response, while the PostgreSQL full-text query itself produced a
6.954 ms median and 9.392 ms p95. A raw isolated Redis lookup of the same
5,913-byte response took 0.250 ms median and 0.359 ms p95. The latency
opportunity is measurable, but the repository does not show a repeated-query
workload likely to produce a useful hit rate:

- the Project Knowledge UI searches only after an explicit form submission;
- Analyze builds queries from variable Resume and Job Description input;
- Analyze idempotency already replays completed identical requests without
  repeating the provider operation; and
- the current corpus is only 35 indexed chunks.

There is also a material operational objection. The current Redis instance is
the critical Dramatiq queue and SSE coordination service. It is configured with
256 MiB, `maxmemory-policy noeviction`, no persistence, and database 0. An
authenticated caller can create many distinct search queries. Even with a TTL
and value limit, adding unbounded cache-key creation to this shared
`noeviction` instance could consume memory needed for queue publication. A
logical Redis database would not isolate memory.

The other candidates either have negligible origin work, lack realistic
short-window reuse, contain user-scoped private data, require broad
invalidation, or should receive a PostgreSQL/query-shape improvement before a
cache. No implementation candidate is selected.

This is a documentation and benchmark audit only. Runtime behavior, schemas,
configuration, Docker assets, authentication, Analyze idempotency, Worker and
Outbox behavior were not changed.

## 2. Repository and audit boundary

| Item | Verified value |
|---|---|
| Repository | `HKJoker-Z/personal-job-agent` |
| Starting branch | `main` |
| Starting commit | `087332f94684762ab53923617a23c20779c91706` |
| `origin/main` at audit start | `087332f94684762ab53923617a23c20779c91706` |
| Audit branch | `audit/redis-caching-suitability` |
| Application version | `2.0.4` |
| Alembic head | `20260724_06` |
| Stable GitHub release | `v2.0.4`, non-draft and non-prerelease |
| Starting worktree | Clean |
| Audit date | 2026-07-27 |

Version evidence is in
[`backend/config.py`](../../backend/config.py#L10),
[`backend/app/__init__.py`](../../backend/app/__init__.py#L6), and
[`README.md`](../../README.md#L16-L17). The head declaration is in
[`backend/app/readiness.py`](../../backend/app/readiness.py#L22), and the
migration declares revision `20260724_06` in
[`backend/alembic/versions/20260724_06_add_analyze_idempotency.py`](../../backend/alembic/versions/20260724_06_add_analyze_idempotency.py#L3-L14).
The fetched `v2.0.4` tag points at the starting commit, and GitHub reported
`v2.0.4` as the latest stable release.

The audit did not inspect production data, row counts, traffic, logs, Redis
keys, query plans, credentials, or runtime configuration. Consequently, all
reuse rates and current production volumes below are explicit assumptions, not
claims about observed production traffic.

## 3. Current Redis responsibilities

### 3.1 Redis as queue infrastructure

Dramatiq 2.2.0 and redis-py 7.4.1 are pinned in
[`backend/requirements.txt`](../../backend/requirements.txt#L14-L15).
[`backend/app/agent_runs/broker.py`](../../backend/app/agent_runs/broker.py#L14-L20)
creates one memoized `RedisBroker`, selects JSON encoding, uses
`settings.redis_url`, and applies the configured queue namespace.

The only actor queue is `agent-workflows`. The actor disables Dramatiq retries
and accepts only five safe identifiers; see
[`backend/app/agent_runs/tasks.py`](../../backend/app/agent_runs/tasks.py#L28-L38).
The allow-list and 64-character identifier bounds are enforced by
[`backend/app/agent_runs/definitions.py`](../../backend/app/agent_runs/definitions.py#L49-L68).
Resume text, Job Description text, credentials, prompts, and provider output
are not queue payload fields.

PostgreSQL remains the durable owner of work. `_enqueue` creates a
deduplicated Outbox row before publication
([`backend/app/agent_runs/service.py`](../../backend/app/agent_runs/service.py#L677-L698)).
The dispatcher locks eligible Outbox rows with `SKIP LOCKED`, publishes the
safe payload, and marks the durable row published
([`backend/app/agent_runs/outbox.py`](../../backend/app/agent_runs/outbox.py#L16-L67)).
Redis is therefore transient delivery, not the source of truth.

### 3.2 Worker connectivity and readiness

The Worker supervisor starts Dramatiq with one process and configured threads,
writes liveness to PostgreSQL, and runs Outbox/recovery maintenance
([`backend/app/agent_runs/worker.py`](../../backend/app/agent_runs/worker.py#L103-L152)).
The Worker health check requires both a Redis `PING` and a recent PostgreSQL
Worker heartbeat; Redis connect and socket timeouts are two seconds
([`backend/app/agent_runs/healthcheck.py`](../../backend/app/agent_runs/healthcheck.py#L15-L43)).

Production settings require Redis and Worker readiness by default
([`backend/app/core/config.py`](../../backend/app/core/config.py#L202-L207)).
Application readiness sends a two-second-bounded `PING` and returns 503 when a
required Redis or Worker dependency is not ready
([`backend/app/readiness.py`](../../backend/app/readiness.py#L73-L155)).
The standalone dispatcher health check also requires its file heartbeat,
PostgreSQL, and a two-second-bounded Redis `PING`
([`backend/app/agent_runs/dispatcher_healthcheck.py`](../../backend/app/agent_runs/dispatcher_healthcheck.py#L16-L30)).

Health and readiness endpoints must not be cached.

### 3.3 Redis as transient SSE coordination

Production SSE connection counts use a SHA-256 digest of the owner UUID in the
key, an atomic increment, a counter TTL, and Lua decrement/delete
([`backend/app/agent_runs/sse.py`](../../backend/app/agent_runs/sse.py#L27-L69)).
The TTL is `max(SSE_HEARTBEAT_SECONDS * 4, 60)`, which is 60 seconds under the
default 15-second heartbeat. Stream heartbeats refresh the TTL
([`backend/app/api/routers/agent_runs.py`](../../backend/app/api/routers/agent_runs.py#L144-L174)).

If Redis is not required, tests/development use a process-local locked counter.
If Redis is required and acquisition fails, the endpoint returns 503.
Touch/release failures are best effort and are swallowed. This is transient
coordination, not caching.

### 3.4 Retry and recovery

On queue publication failure, the Outbox records
`safe_error_code=redis_unavailable`, clears the publication lease, and retries
with bounded exponential backoff plus deterministic jitter. The default Outbox
budget is ten attempts; exhaustion moves the work to durable dead-letter state
([`backend/app/agent_runs/outbox.py`](../../backend/app/agent_runs/outbox.py#L70-L109),
[`backend/app/db/models.py`](../../backend/app/db/models.py#L1016-L1038)).

Interrupted `publishing` rows are returned to `failed`. A `published` row whose
step remains queued/retry-scheduled is returned to `pending`, allowing
PostgreSQL-owned work to be republished after Redis loses transient queue state
([`backend/app/agent_runs/outbox.py`](../../backend/app/agent_runs/outbox.py#L112-L163)).
The one-second dispatcher loop retries after exceptions
([`backend/app/agent_runs/outbox.py`](../../backend/app/agent_runs/outbox.py#L166-L174)).

### 3.5 Redis infrastructure configuration

[`compose.yaml`](../../compose.yaml#L36-L65) defines Redis 7.4.1 with:

- private port 6379;
- database 0 in every application `REDIS_URL`;
- no RDB snapshots and no AOF;
- 256 MiB `maxmemory`;
- `noeviction`;
- read-only container filesystem with `/data` and `/tmp` on `tmpfs`; and
- a `redis-cli ping` health check.

The URL default is `redis://127.0.0.1:6379/0`, while the production Compose
services use `redis://redis:6379/0`
([`backend/app/core/config.py`](../../backend/app/core/config.py#L146-L153),
[`compose.yaml`](../../compose.yaml#L147-L178)).
The queue namespace defaults to `personal-job-agent-v2`, is bounded to 80
characters, and is shared by Dramatiq and SSE
([`backend/app/core/config.py`](../../backend/app/core/config.py#L187-L190)).

The memoized Dramatiq broker owns a redis-py connection pool created from the
URL. The repository does not configure a Redis pool maximum or broker socket
timeouts. Readiness, health, and SSE instead construct short-lived clients,
set two-second connect/socket timeouts, and close them after each operation.
There is no dedicated cache client or cache connection pool.

## 4. Existing Redis key inventory

There are **no application cache keys** and no cache serialization contract in
the current repository.

The following inventory distinguishes persistent key shapes during queue
activity from keys that appear only for particular Dramatiq states:

| Responsibility | Key shape | Redis type | Lifetime/serialization |
|---|---|---|---|
| Queue | `personal-job-agent-v2:agent-workflows` | list | Redis message IDs; no application TTL |
| Queue message body | `personal-job-agent-v2:agent-workflows.msgs` | hash | Dramatiq JSON-encoded message bytes keyed by Redis message ID |
| Broker heartbeat | `personal-job-agent-v2:__heartbeats__` | sorted set | Broker UUID scored by timestamp; maintained by Dramatiq |
| In-flight acknowledgements | `personal-job-agent-v2:__acks__.<broker-id>.agent-workflows` | set | Present only while messages are fetched and unacknowledged |
| Delay queue | `personal-job-agent-v2:agent-workflows.DQ` and `.DQ.msgs` | sorted/list/hash as managed by Dramatiq | Present only for delayed messages |
| Dead message queue | `personal-job-agent-v2:agent-workflows.XQ` and `.XQ.msgs` | sorted set/hash | Dramatiq dead-message retention |
| SSE count | `personal-job-agent-v2:sse:<sha256(owner UUID)>` | string integer | Default 60-second TTL, refreshed by stream heartbeat |

An isolated Redis observation after one synthetic enqueue showed the queue
list, message hash, and broker heartbeat sorted set under this namespace. A
separate isolated production-mode SSE acquisition showed one hashed-owner
counter with value `1` and a 60-second TTL. These observations used Redis
database 0 in the audit-only container and were deleted immediately afterward.
They were not observations of production Redis.

## 5. Current Redis failure behavior

| Consumer | Redis outage behavior |
|---|---|
| Application readiness | Required production readiness becomes 503/not ready |
| Worker health | Health check fails if `PING` fails |
| Dispatcher health | Health check fails if Redis, PostgreSQL, or heartbeat is unavailable |
| Dramatiq consumption | Transient queue transport stops until connectivity returns |
| Outbox publication | Durable row becomes failed, receives bounded backoff, and is retried or dead-lettered |
| Lost published delivery | PostgreSQL recovery makes the Outbox row pending for republish |
| SSE acquisition | Fails closed with 503 when Redis coordination is required |
| SSE touch/release | Best effort; Redis exceptions are ignored |
| Ordinary database reads | They do not currently contact Redis |
| Cache fallback | Not applicable because no cache exists |

A future cache must catch cache lookup/write failures and execute the normal
PostgreSQL path. This would preserve feature-level behavior during an in-flight
Redis failure, although the deployment can independently stop routing new
traffic after readiness becomes unhealthy.

## 6. Candidate endpoint and query inventory

Every listed API route is authenticated by the default-deny middleware except
health, readiness, login, and session status
([`backend/app/auth/middleware.py`](../../backend/app/auth/middleware.py#L19-L24),
[`backend/app/auth/middleware.py`](../../backend/app/auth/middleware.py#L81-L105)).
Authentication and authorization must complete before any future cache access.

Frequency descriptions are derived from frontend call sites, not traffic
telemetry:

| Candidate | Endpoint and user visibility | Current query/path | Expected volume and frequency |
|---|---|---|---|
| Project Knowledge search | `GET /api/project-knowledge/search`; global curated content visible to authenticated users | Status lookup, then document-scoped PostgreSQL FTS using `to_tsvector`, `websearch_to_tsquery`, `ts_rank`, rank order and top-k; zero FTS hits invoke a document-scoped Python fallback. Sources: [`legacy_application.py`](../../backend/legacy_application.py#L1684-L1693), [`database.py`](../../backend/database.py#L1692-L1763). | Current checked-in source becomes 35 chunks. Explicit UI submit only; Analyze query varies by Resume/JD. |
| Project Knowledge status | `GET /api/project-knowledge/status`; global authenticated view | File existence plus `knowledge_documents` lookup by source filename or title, ordered by ID, limit 1. Sources: [`legacy_application.py`](../../backend/legacy_application.py#L1572-L1602), [`database.py`](../../backend/database.py#L1387-L1412). | One row; loaded once on page mount and after upload/rebuild. |
| Monitoring workflow steps | `GET /api/monitoring/workflow-steps?days=N`; global authenticated metadata | Existing PostgreSQL grouped aggregate computes counts, average/min/max, `percentile_disc` p50/p95, six step groups in the fixture. Sources: [`monitoring_service.py`](../../backend/monitoring_service.py#L27-L53), [`monitoring_service.py`](../../backend/monitoring_service.py#L397-L425). | Grows per analysis step; page mount, manual refresh, or post-management refresh. |
| Monitoring overview | `GET /api/monitoring/overview?days=N`; global authenticated metadata | Selects all `analysis_metrics` rows in the period ordered newest first; Python calculates counts, means, and rates. Sources: [`monitoring_service.py`](../../backend/monitoring_service.py#L352-L394). | Grows per analysis; same page refresh behavior as workflow steps. |
| Evaluation summaries | `GET /api/evaluations/runs`; global authenticated metadata | Count plus ordered summary projection with limit/offset. Sources: [`evaluation_service.py`](../../backend/evaluation_service.py#L386-L407). | One row per manually started offline suite; latest page loaded with Monitoring. |
| History list/detail | `GET /api/history` and `/api/history/{id}`; owner-scoped, with admins also seeing unowned legacy rows | Count plus owner/admin predicate, ordered summary projection and page; detail uses primary key plus owner predicate. Sources: [`legacy_application.py`](../../backend/legacy_application.py#L2289-L2312), [`database.py`](../../backend/database.py#L954-L1036). | One row per saved Analyze result; list on page mount/search, detail on click. |
| Resume list | `GET /api/resumes`; strictly user-scoped | SQLAlchemy `Resume.user_id`, not archived, ordered primary then updated/created. Sources: [`resumes/repository.py`](../../backend/app/resumes/repository.py#L17-L24), [`resumes.py`](../../backend/app/api/routers/resumes.py#L37-L44). | Normally a small personal library; page mount and Analyze mount. |
| Primary Resume | `GET /api/resumes/primary`; strictly user-scoped and contains active structured/raw parsed text | Partial-unique primary lookup followed by active version lookup. Sources: [`resumes/repository.py`](../../backend/app/resumes/repository.py#L26-L33), [`resumes/service.py`](../../backend/app/resumes/service.py#L100-L113). | One Resume/version; requested with the list when Analyze mounts. |
| Security policy | `GET /api/security/policy`; global authenticated static response | In-memory literal, no PostgreSQL query. Source: [`legacy_application.py`](../../backend/legacy_application.py#L2010-L2022). | Deploy-time volatility only; no current frontend call was found. |

The Monitoring page loads overview, workflow steps, RAG, security,
recommendations, traces, evaluation status/runs, and management status in
parallel once on mount and on explicit refresh
([`frontend/src/legacy-workspace.jsx`](../../frontend/src/legacy-workspace.jsx#L1578-L1634)).
This is not polling. Project Knowledge status/search behavior is similarly
explicit
([`frontend/src/legacy-workspace.jsx`](../../frontend/src/legacy-workspace.jsx#L2361-L2385),
[`frontend/src/legacy-workspace.jsx`](../../frontend/src/legacy-workspace.jsx#L2456-L2487)).

Retired Jobs, Job Rankings, Applications, Approvals, and Tasks were excluded.
`/api/history` remains a current route and was assessed only as History.

## 7. Benchmark environment and method

### 7.1 Isolation

The audit created two temporary containers that were independent of every
running application service:

| Service | Image/version | Audit-only endpoint |
|---|---|---|
| PostgreSQL | `postgres:16.9-alpine`, PostgreSQL 16.9 | `127.0.0.1:25432/redis_cache_audit_test` |
| Redis | `redis:7.4.1-alpine`, Redis 7.4.1 | `127.0.0.1:26379/0` |

The isolated PostgreSQL database was created empty and upgraded through the
repository migrations to `20260724_06`. PostgreSQL used 128 MiB
`shared_buffers`, 4 MiB `work_mem`, 4 GiB `effective_cache_size`, JIT on, and at
most two parallel workers per gather. The benchmark host exposed four CPUs.
The isolated Redis used no persistence, 64 MiB, and `noeviction`.

No production hostname, port, container, database, Redis server, data, or
credentials were used. The host container list was consulted only to avoid
name and port collisions; no running application container was inspected or
contacted.

### 7.2 Execution method

- Dataset generation used deterministic SQL series and deterministic synthetic
  text. The only non-synthetic content was the checked-in
  `docs/PROJECT_KNOWLEDGE.md`.
- Personal-scale cases received three warm-ups and 25 measured executions.
- Growth/stress cases received three warm-ups and 15 measured executions.
- Application timing used `time.perf_counter_ns` around a full authenticated
  FastAPI TestClient GET, including middleware, the origin path, and JSON
  encoding.
- PostgreSQL timing used `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` with the same
  warm-up/measurement policy.
- p95 uses nearest-rank.
- Redis timing used a persistent redis-py client over isolated loopback TCP.
  The raw Redis numbers are an upper bound on potential cache lookup/write
  cost; they do not pretend that middleware, authorization, validation,
  deserialization, or error handling is free.
- All response sizes are UTF-8 JSON body bytes.
- No DeepSeek or other provider was called.

### 7.3 Exact datasets

The assumed personal-scale fixture is deliberately not labeled as production
statistics:

| Domain | Personal-scale rows |
|---|---:|
| Analysis metrics | 500 |
| Analysis step metrics | 3,000 |
| History records for the audit owner | 1,000 |
| Evaluation runs | 100 |
| Resumes | 10 |
| Resume versions | 1 active Primary Resume version |
| Project Knowledge documents | 1 |
| Project Knowledge chunks | 35 |

The checked-in Project Knowledge file was 33,356 bytes and 33,270 cleaned
characters, with SHA-256
`77c61e521964a2ca3c8d0812e8427ace76794513062ee8a7084aaff15327fd52`.
Current ingestion indexes at most 30,000 characters in 1,000-character chunks
with 125-character overlap
([`backend/knowledge_utils.py`](../../backend/knowledge_utils.py#L8-L10),
[`backend/knowledge_utils.py`](../../backend/knowledge_utils.py#L33-L57)).
It produced 35 chunks.

The growth/stress fixture contained:

| Domain | Growth/stress rows |
|---|---:|
| Analysis metrics | 50,000 |
| Analysis step metrics | 50,000 |
| History records | 50,000 total; 35,000 owner and 15,000 unowned/admin-visible |
| Evaluation runs | 10,000 |
| Resumes | 400 |
| Project Knowledge growth case | 350 chunks, 332,500 total chunk characters, 88 matching chunks |

The 350-chunk Project Knowledge case is a future-capacity experiment. It is ten
times the current 35-chunk corpus and cannot be produced by the current
30,000-character ingestion cap. It is not presented as current production
performance.

## 8. Baseline latency and response sizes

### 8.1 Personal-scale authenticated application baseline

| Endpoint/case | Median | p95 | Response |
|---|---:|---:|---:|
| Project Knowledge search, 35 chunks, top 5 | 49.629 ms | 55.227 ms | 5,913 B |
| Project Knowledge status | 23.444 ms | 26.730 ms | 129 B |
| Monitoring workflow-step aggregate, 3,000 rows | 27.409 ms | 31.080 ms | 1,342 B |
| Monitoring overview, 500 rows | 29.656 ms | 33.796 ms | 394 B |
| Evaluation run summaries, 100 rows | 24.533 ms | 26.547 ms | 6,369 B |
| History first page, 1,000 owner rows | 27.202 ms | 30.517 ms | 22,465 B |
| History detail | 22.923 ms | 31.689 ms | 1,767 B |
| Resume list, 10 rows | 8.253 ms | 10.147 ms | 2,945 B |
| Primary Resume plus active version | 8.541 ms | 9.516 ms | 7,842 B |
| Security policy | 5.525 ms | 6.469 ms | 281 B |

The authenticated application numbers include session/user checks that a cache
must not bypass. For comparison, the static policy object itself serialized in
0.004 ms median, confirming that caching it would add work rather than remove
meaningful origin work.

### 8.2 PostgreSQL execution baseline

| Query | Dataset | Median execution | p95 execution | Returned rows |
|---|---:|---:|---:|---:|
| Project Knowledge FTS | 35 chunks | 6.954 ms | 9.392 ms | 5 |
| Existing workflow-step SQL aggregate | 3,000 step rows | 2.741 ms | 3.306 ms | 6 |
| Monitoring overview row load | 500 metric rows | 0.320 ms | 0.475 ms | 500 |
| History page query | 1,000 rows | 0.838 ms | 1.059 ms | 50 |
| Evaluation summary page | 100 rows | 0.046 ms | 0.067 ms | 20 |

The workflow-step baseline is the existing SQL aggregation. The audit did not
replace it with a Python aggregation or regress the optimization.

Monitoring overview illustrates why caching should not be the first fix at
growth scale: PostgreSQL loaded 50,000 rows in 22.170 ms median, but the full
application path took 768.760 ms median and 870.124 ms p95 because it transfers,
materializes, and aggregates all rows in Python. A server-side PostgreSQL
aggregate would address the origin cost for every request and preserve one
source of correctness; a cache would only hide it after a hit.

### 8.3 Project Knowledge growth baseline

| Corpus | App median | App p95 | PostgreSQL median | PostgreSQL p95 | Response |
|---|---:|---:|---:|---:|---:|
| Current checked-in, 35 chunks | 49.629 ms | 55.227 ms | 6.954 ms | 9.392 ms | 5,913 B |
| Future growth, 350 chunks | 85.234 ms | 101.439 ms | 39.955 ms | 41.651 ms | 5,554 B |

The larger corpus shows a measurable growth cost but does not change the
current-product reuse evidence or make the 350-chunk case current.

### 8.4 Raw Redis upper-bound comparison

| Value | Bytes | GET median/p95 | `SET EX` median/p95 |
|---|---:|---:|---:|
| Current Project Knowledge result | 5,913 | 0.250 / 0.359 ms | 0.267 / 0.326 ms |
| Monitoring workflow steps | 1,342 | 0.230 / 0.349 ms | 0.258 / 0.325 ms |
| Monitoring overview | 394 | 0.224 / 0.314 ms | 0.250 / 0.345 ms |
| 350-chunk Project Knowledge result | 5,554 | 0.193 / 0.294 ms | 0.240 / 0.284 ms |

These numbers prove that Redis is faster than the origins in isolation. They do
not prove a beneficial cache because hit rate, invalidation, security, memory
isolation, and operational failure modes remain decision gates.

## 9. Volatility, reuse, invalidation, and security

| Candidate | Volatility and invalidation events | Stale tolerance | Security/privacy and correctness |
|---|---|---|---|
| Project Knowledge search | Upload, explicit rebuild, or automatic rebuild replaces chunks. | A result must not survive a successful rebuild; a versioned key can enforce this. | Current document is global to authenticated users. Results include chunk text and object IDs. Cache must follow auth and must not incorporate Resume/JD/query text in keys or logs. |
| Project Knowledge status | Same events plus file presence. | Very low: users expect rebuild/upload status immediately. | Global authenticated metadata. Caching duplicates file/DB reconciliation logic for negligible benefit. |
| Monitoring workflow steps | Every persisted analysis step; monitoring deletion. | A few seconds may be acceptable on a dashboard. | Global authenticated metadata, but the existing SQL is already the correctness implementation and must remain the miss path. |
| Monitoring overview | Every persisted analysis; monitoring deletion. | A few seconds may be acceptable. | Global metadata. Current Python aggregation is an origin query-shape problem; caching would duplicate/hide correctness logic. |
| Evaluation summaries | Offline evaluation run insert/update/results; evaluation deletion. | Short staleness may be acceptable after a run. | Global authenticated metadata; result failures can contain bounded summaries. Low reuse and near-zero SQL cost. |
| History list/detail | Saved Analyze result, delete, next-action decision, and relevant migrations/restores. | Low after a user mutation. | Owner-specific; admin visibility includes unowned rows. Keys and values could leak across users if ownership is mishandled. Detail contains private analysis fields. |
| Resume list/Primary | Create/update/archive, upload/import, version create/finalize, active-version and Primary changes. | Low; Analyze must see the selected current Resume. | Strictly user-specific. Primary response includes structured content and raw parsed Resume text, which this phase explicitly must not cache. |
| Security policy | Code/deploy only. | High. | Static and safe, but origin work is effectively zero. Authentication decisions must never be cached. |

Logout does not change the underlying global data, but it must prevent future
access; therefore authorization always precedes cache lookup. User deactivation
or role changes have the same requirement. A cached global response cannot be
treated as proof that a requester is authorized.

The amount of correctness logic a cache would duplicate is also a decision
factor:

| Candidate | Would a cache duplicate correctness logic? |
|---|---|
| Project Knowledge search | A minimal cache-aside wrapper can preserve the existing PostgreSQL search unchanged, but document/request versioning and strict response validation become new correctness logic. |
| Project Knowledge status | Yes. It would duplicate the current file-existence and PostgreSQL-index reconciliation for almost no origin benefit. |
| Monitoring workflow steps | Not if the existing SQL aggregate remains the only miss implementation; TTL semantics are still additional dashboard correctness. |
| Monitoring overview | It would preserve a response calculated by the current Python aggregation, but would mask the inefficient origin and add staleness before that origin is improved. |
| Evaluation summaries | Limited, but count/page invalidation and run completion/deletion state would need to be mirrored for a near-zero SQL query. |
| History list/detail | Yes. Ownership/admin visibility, paging/filter variants, and every write/delete/decision invalidation would be duplicated. |
| Resume list/Primary | Yes. Ownership, Primary selection, active-version changes, and sensitive-value handling would be duplicated. |
| Security policy | No PostgreSQL logic exists to duplicate, but a Redis round trip is more work than constructing the literal. |

## 10. Candidate scoring

Scores are 1 (poor for caching) to 5 (strong for caching). “Low complexity” and
“outage safety” score higher when a simple, safe implementation is possible.
Scores are comparative; the hard decision rules still apply.

| Candidate | Latency benefit | Reuse | Realism | Simple invalidation | Staleness OK | Auth safety | Low complexity | Outage safety | Interview value | Product relevance | Total / 50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Project Knowledge search | 3 | 1 | 5 | 5 | 5 | 4 | 3 | 5 | 4 | 5 | **40** |
| Monitoring workflow steps | 2 | 2 | 4 | 4 | 4 | 4 | 4 | 5 | 3 | 4 | **38** |
| Security policy | 1 | 1 | 5 | 5 | 5 | 5 | 5 | 5 | 1 | 2 | **35** |
| Monitoring overview | 3 | 2 | 2 | 3 | 4 | 4 | 3 | 5 | 4 | 4 | **34** |
| Project Knowledge status | 1 | 2 | 5 | 4 | 2 | 4 | 4 | 5 | 2 | 4 | **33** |
| Evaluation summaries | 1 | 1 | 4 | 4 | 3 | 4 | 4 | 5 | 2 | 3 | **31** |
| History list/detail | 2 | 2 | 4 | 2 | 2 | 2 | 2 | 5 | 3 | 5 | **29** |
| Resume list/Primary | 1 | 2 | 5 | 2 | 1 | 1 | 2 | 5 | 2 | 5 | **26** |

Project Knowledge search ranks first but fails hard rule 1: a measured or
strongly justified repeated-read workload is absent. Security policy
demonstrates why total score cannot override a hard gate: it is safe and easy,
but its origin is already negligible.

## 11. Selected candidate and rejected candidates

### Selected implementation candidate

**None.**

No candidate satisfies all eight implementation rules. In particular:

1. Project Knowledge search has measurable cost and clean invalidation, but no
   demonstrated reuse and a shared-Redis memory-isolation risk.
2. Monitoring workflow steps preserve correctness cleanly, but the existing SQL
   aggregate is fast at personal scale and the UI does not poll.
3. Monitoring overview has a growth problem, but the first correction should be
   a PostgreSQL aggregate, not caching the current row-transfer/Python
   aggregation.
4. History and Resume data are user-specific, mutable, and privacy-sensitive.
5. Evaluation summaries and policy/status endpoints have negligible origin
   work or low reuse.

### Honest current-production relevance

The audit provides no production hit-rate or row-count evidence because
production was intentionally untouched. The frontend establishes one-shot and
manual-refresh call patterns, and the current checked-in Project Knowledge
corpus is small. Those facts support “do not implement now,” not a claim that a
future deployment can never benefit.

Reassess Project Knowledge search only after bounded telemetry shows a repeated
normalized-query hit opportunity, for example:

- at least 10% of authenticated Project Knowledge searches repeat within five
  minutes;
- origin p95 remains above an agreed threshold such as 50 ms at the then-current
  supported corpus;
- the cache has memory isolation from the `noeviction` queue service, or an
  enforceable global key/value budget; and
- a version calculation is proven correct across concurrent upload/rebuild.

## 12. Deferred reference design for Project Knowledge search

This section is a reviewable contingency design, **not** an implementation
recommendation or authorization to add caching.

### 12.1 Key and request contract

The existing `personal-job-agent-v2` namespace was verified. A compatible
cache-specific key would be:

```text
personal-job-agent-v2:cache:project-knowledge:search:v1:
<document-content-sha256>:<max-chunk-id>:<chunk-count>:
<request-sha256>:<top-k>
```

The physical key is one ASCII line with no whitespace; the line breaks above
are only for readability.

- `v1` is the cache schema/serialization version.
- The document component combines SHA-256 of the exact canonical 30,000
  indexed characters with PostgreSQL `max(chunk_id)` and `chunk_count`.
  The chunk generation prevents a concurrent file replacement followed by a
  rebuild from reusing a value computed against the prior chunk set.
- The current Project Knowledge document is global, so the key is global only
  **after** successful authentication. If Project Knowledge becomes
  user-owned, a one-way owner-scope digest must be added and ownership must be
  checked before lookup.
- Normalize the request by validating UTF-8, trimming outer whitespace, and
  preserving the remaining exact Unicode text. Hash that normalized byte
  sequence with SHA-256. Conservative normalization avoids collisions between
  requests unless response equivalence is proven.
- Never place query text, Resume/JD text, user IDs, session tokens, CSRF values,
  credentials, provider data, or Idempotency-Key values in the key or logs.
- Bypass the cache, without changing the existing PostgreSQL response, when
  normalized query length exceeds 8,192 Unicode code points.
- Preserve the existing `top_k` range 1–10.
- Reject or bypass any constructed key over 256 ASCII bytes.

### 12.2 Value, TTL, and invalidation

- Serialize the exact response payload as compact UTF-8 JSON inside a wrapper
  containing `cache_schema_version=1`.
- Deserialize with strict type/field/size validation. A malformed value is a
  miss and is best-effort deleted.
- Maximum stored value: 32 KiB. Larger correct responses return normally from
  PostgreSQL but are not cached.
- TTL: 300 seconds, with no sliding refresh.
- A successful rebuild changes the document generation and content hash, so it
  causes a natural miss. Old keys are unreachable and expire within five
  minutes. Broad key deletion is unnecessary.
- A failed rebuild does not publish a new generation. PostgreSQL remains the
  authority.

The 300-second TTL and 32 KiB value bound are insufficient by themselves to
protect a shared `noeviction` broker from many distinct keys. Before
implementation, use a separate cache Redis with an appropriate eviction and
memory policy or add an enforceable global cache budget. Selecting Redis
database 1 on the current server would not solve shared memory exhaustion.

### 12.3 Cache-aside flow and PostgreSQL fallback

1. Authenticate the session and complete all authorization checks.
2. Validate `query` and `top_k`; do not cache auth decisions.
3. Obtain the current authoritative document generation.
4. Build and hash the bounded key.
5. Attempt a cache `GET` with a dedicated bounded pool and very short
   cache-only timeouts.
6. On a valid hit, return the decoded payload.
7. On miss, timeout, connection error, malformed data, or oversized data,
   execute the unchanged `search_knowledge_chunks` PostgreSQL/fallback path.
8. Return the PostgreSQL result regardless of cache-write success.
9. Best-effort `SET` only valid values at or below 32 KiB with `EX 300`.

Redis is never the source of truth. PostgreSQL search and its fallback remain
the source implementation.

### 12.4 Connection and failure behavior

A future cache should not reuse the Dramatiq broker object. Use a dedicated
redis-py pool, for example a maximum of 10 connections, with approximately
25 ms connect and 25 ms command timeouts. Pool exhaustion, Redis
`noeviction` errors, timeouts, malformed values, and serialization errors all
increment an error/fallback metric and continue through PostgreSQL.

The precise timeout must be load-tested; it must be far below the origin p95 so
an outage does not add a long delay before fallback.

## 13. Stampede and concurrency decision

For Project Knowledge search, allow duplicate computation on simultaneous
misses.

The measured current PostgreSQL median was 6.954 ms and even the deliberately
larger case was 39.955 ms. A distributed lock introduces ownership tokens,
lease sizing, renewal, timeout, stale-lock recovery, and another failure path.
That complexity is not justified for a small bounded query. A few duplicate
queries are safer.

Do not use stale-while-revalidate: versioned keys already make successful
rebuilds miss, and serving prior-document results would weaken the simple
correctness contract. If a future scale test proves a stampede problem, first
consider a short process-local single-flight keyed by the bounded hash. Do not
introduce a general distributed-lock framework.

## 14. Metrics and logging

Proposed bounded metrics for a future implementation:

- `cache_requests_total{cache="project_knowledge_search",result="hit|miss|error"}`
- `cache_postgresql_fallback_total{cache="project_knowledge_search",reason="miss|timeout|connection|malformed|oversize|write_error"}`
- `cache_lookup_duration_seconds{cache="project_knowledge_search"}`
- `cache_origin_duration_seconds{cache="project_knowledge_search"}`
- `cache_write_duration_seconds{cache="project_knowledge_search"}`
- `cache_response_total{cache="project_knowledge_search",source="cache|postgresql"}`

Do not label metrics with user ID, query hash, document hash, request ID, key,
top-k, or exception text. The fixed cache name, bounded result/reason, and
source labels avoid high cardinality.

Structured logs may include the fixed cache name, hit/miss/error, top-k,
result count, value-size bucket, duration, and at most a short one-way hash
prefix for debugging. They must not contain query text, cache values, Resume/JD
text, Project Knowledge chunks, secrets, prompts, provider responses, session
data, CSRF data, or Idempotency-Key values.

## 15. Security and isolation requirements

- Authentication and current user state are checked before cache access.
- Redis never grants authority.
- Current Project Knowledge data is global within the authenticated
  application. The cached result contains global document/chunk identifiers and
  chunk text. Any future ownership change requires an owner-scoped key and
  ownership predicate before lookup.
- Logout, user deactivation, password/session changes, or role changes must
  prevent access before a cached response is read.
- Raw Resume text and raw Job Description text are not cached. Primary Resume
  and complete Analyze responses are explicitly excluded.
- The query is represented only by a SHA-256 digest. Document content is also
  represented by a digest/generation, not raw text.
- Query length is at most 8,192 code points for cache participation; top-k is
  at most 10; key length is at most 256 bytes; value size is at most 32 KiB;
  TTL is 300 seconds.
- A cache lookup is at most one GET per request. A miss permits at most one
  origin computation and one best-effort SET.
- A separate memory boundary or enforceable global key budget is required
  before implementation so an authenticated attacker cannot starve the
  Dramatiq broker with distinct cache keys.

## 16. Failure and correctness test plan

All tests use isolated PostgreSQL and Redis and a fake/mock provider. DeepSeek
must not be called.

1. A cache miss returns the unchanged PostgreSQL result.
2. A valid hit returns a byte/structure-equivalent response to the origin.
3. Mutating/rebuilding Project Knowledge proves PostgreSQL remains
   authoritative.
4. Redis connection refusal falls back to PostgreSQL.
5. Redis command timeout falls back within the bounded timeout.
6. Malformed JSON, wrong schema version, wrong field types, and truncated values
   are ignored and treated as misses.
7. Values above 32 KiB are returned from PostgreSQL but not stored.
8. Document content hash, max chunk ID, chunk count, or cache schema version
   change causes a miss.
9. TTL expiration causes a miss and correct recomputation.
10. Concurrent misses return identical correct values; duplicate origin queries
    are permitted.
11. Rebuild concurrent with lookup never serves old chunks under the new
    generation.
12. Authentication occurs before lookup; anonymous, expired, revoked, and
    deactivated sessions cannot access a cached result.
13. A future user-owned knowledge test uses two users and proves no cross-user
    hit or object-ID leakage.
14. Keys, logs, and metrics contain no query text, Resume/JD text, secrets,
    session/CSRF values, prompts, provider data, or Idempotency-Key values.
15. Oversized query and invalid top-k behavior preserve the existing API
    contract while bypassing cache as designed.
16. Redis `noeviction`/OOM write errors do not fail the request.
17. Existing Analyze idempotency tests pass unchanged and no cache key contains
    an Analyze Idempotency-Key.
18. Dramatiq enqueue/consume, Outbox publication failure/backoff/recovery,
    Worker health, readiness, and SSE connection-limit tests pass unchanged.
19. Cache keys cannot collide with queue, acknowledgement, heartbeat, delay,
    dead-letter, or SSE keys.
20. A bounded-load test verifies pool size, timeouts, key count, memory, hit
    rate, origin fallback rate, and queue latency.

## 17. Expected implementation files if the decision changes

No implementation files are approved by this audit. A later, evidence-backed
Project Knowledge cache would likely touch only:

- a new bounded cache-aside module such as
  `backend/app/cache/project_knowledge.py`;
- `backend/app/core/config.py` for explicit cache TTL, size, timeout, and pool
  bounds;
- `backend/legacy_application.py` to wrap only the Project Knowledge search
  origin after authentication;
- a new isolated cache correctness/failure test module;
- existing Redis/Outbox/SSE regression tests; and
- documentation/metrics contract updates.

The existing redis-py dependency is sufficient. The current PostgreSQL search,
Dramatiq broker, Outbox, SSE module, readiness endpoints, Analyze idempotency,
Compose configuration, and schema should not be rewritten merely to add the
cache. A separate cache Redis would require a separately reviewed
infrastructure change and is outside this task.

## 18. Risks and rollback

### Risks

- Low hit rate can make Redis slower overall after serialization, network, and
  error-handling overhead.
- Shared `noeviction` memory can allow cache keys to disrupt queue publication.
- Incorrect document versioning can serve pre-rebuild chunks.
- Cache access before auth can disclose private project evidence.
- User/query labels can create telemetry cardinality or privacy problems.
- Long Redis timeouts can add latency before PostgreSQL fallback.
- Caching Monitoring overview can hide an inefficient origin rather than fix
  it.
- Caching History/Resume responses can serve stale or cross-user private data.
- A portfolio-motivated cache without workload evidence would distort the
  product and weaken the operational story.

### Rollback

This audit is documentation-only, so rollback is a revert of the audit commit.
No runtime key cleanup or data migration is needed.

For any later cache implementation, rollback must make the route bypass the
cache and execute PostgreSQL directly. PostgreSQL remains authoritative, so no
data restoration is required. Versioned keys can be left to expire within 300
seconds; broad deletion is unnecessary. Queue, SSE, Worker, Outbox, readiness,
and Analyze idempotency behavior must be unchanged before and after rollback.

## 19. Validation

| Check | Result |
|---|---|
| `git diff --check` | Passed |
| Relative Markdown source-link validation | 48 links checked; no missing targets |
| `test_readiness` and `test_monitoring_service` | 32 tests passed |
| `test_v2_postgres_integration` against isolated PostgreSQL 16.9 | 10 tests passed; no new Alembic upgrade operations detected |

One preliminary readiness invocation incorrectly supplied
`TEST_DATABASE_URL`, which intentionally selected the Version 2 readiness
wrapper instead of the SQLite readiness path expected by that test module. Its
six failures were discarded as invalid test setup. The command was rerun with
both database URL variables unset and all 32 tests passed. No repository file
was changed by either invocation.

## 20. Audit confirmations

- Production was untouched.
- No production service, endpoint, database, Redis server, data, logs,
  credentials, configuration, container filesystem, or volume was accessed.
- Only temporary isolated PostgreSQL 16.9 and Redis 7.4.1 containers were used
  for synthetic benchmarking.
- Both temporary audit containers were stopped and removed after validation;
  their test data did not persist.
- Real user, Resume, Job Description, evaluation, monitoring, History, and
  Redis data were not used.
- No runtime Backend or Frontend application behavior was changed.
- No PostgreSQL schema or Alembic migration was changed.
- No Redis, Docker, Compose, production, authentication, Analyze idempotency,
  Worker, or Outbox configuration was changed.
- No cache was implemented.
- No release, deploy, merge, or tag was performed.
- Real DeepSeek was not called.
