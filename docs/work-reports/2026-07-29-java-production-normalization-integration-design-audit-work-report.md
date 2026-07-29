# Java Production Normalization Integration Design Audit Work Report

## 1. Repository

- Repository: `HKJoker-Z/personal-job-agent`
- Production baseline: Personal Job Agent `2.0.4`
- Alembic head: `20260724_06`
- Audit date: 2026-07-29
- Audit type: repository design review plus bounded, read-only production
  capacity inspection

## 2. Phase 3B PR final head

Phase 3B pull request
[#30](https://github.com/HKJoker-Z/personal-job-agent/pull/30) was verified
at final head:

`ee802c113617d334bb3922aa511ed7b720220762`

The final head contained the mandatory Phase 3B Work Report. Its 12 GitHub
checks were successful, including the Maven/PostgreSQL and container-smoke
jobs. The Maven logs reported:

- 67 unit/MockMvc tests;
- 37 PostgreSQL integration tests;
- zero failures;
- zero errors; and
- zero skipped tests.

The explicit skipped-PostgreSQL-test rejection step also passed. The Phase 3B
container smoke job passed.

The Flyway V1 and V2 blobs matched the starting `main` blobs:

- V1 blob: `d2e503...`; and
- V2 blob: `2278c4...`.

The Phase 3B report also recorded unchanged SHA-256 checksums. The changes
after that report were limited to a CI path allowlist and a report correction;
no FastAPI integration, publication, release, deployment, or production
change was added. GitHub reported the PR `CLEAN` and `MERGEABLE`.

## 3. Phase 3B merge commit

PR #30 was merged with a normal merge commit, without squash, rebase, admin
bypass, tag, release, publication, or deployment:

`f01a392a4548a87cc44050b5b415f114ba180485`

Local `main` was updated with `git pull --ff-only origin main`. Local `main`
and `origin/main` both resolved to that merge commit.

Post-merge GitHub CI passed:

- repository CI run `30454193171`: all 10 jobs successful; and
- Java CI run `30454200474`: Maven/PostgreSQL and container smoke successful.

## 4. Starting main commit

The pre-merge Phase 3B base was:

`52e60f41506a98175f0f1f9cd2028205b6768e28`

The audit branch started from the verified post-merge `main`:

`f01a392a4548a87cc44050b5b415f114ba180485`

## 5. Audit branch

`audit/java-production-normalization-integration`

## 6. Audit scope

The audit:

- traced the real `POST /api/analyze` implementation;
- inspected the merged deterministic Java normalize contract;
- compared four production deployment choices;
- assessed a narrow FastAPI-to-Java integration boundary;
- defined security ordering, modes, timeouts, fallback, correlation, and
  idempotency behavior;
- inspected sanitized production resource and Docker topology evidence;
- designed one candidate, staged rollout, rollback, tests, phases, and exact
  proposed files; and
- produced the focused supporting architecture document.

## 7. Scope exclusions

This audit did not:

- change FastAPI, Java, React, PostgreSQL, Redis, Alembic, Flyway, Docker,
  Compose, Nginx, release, deployment, production configuration, or version
  metadata;
- implement or activate the integration;
- add Java persistence APIs to the Personal Job Agent workflow;
- restart, stop, create, or reconfigure a production service;
- inspect production application records or request bodies;
- call a mutation endpoint;
- call DeepSeek or any external LLM;
- publish a Java image;
- create a tag or release; or
- deploy anything.

## 8. Production read-only access performed

The current production host was inspected locally with bounded read-only
commands. Evidence was limited to:

- memory, disk, uptime, and CPU count;
- running-container names, images, health, ports, restart counts, resource
  limits, and aggregate point-in-time resource use;
- Docker network names and sanitized membership/driver/internal status;
- Docker volume names and aggregate Docker disk accounting;
- container security metadata that does not expose environment values; and
- service/routing status for the existing Mihomo and `pja-br0` path.

No container environment was printed. No `.env`, Docker secret, credential,
raw Compose rendering, log body, database row, Resume, JD, History, or user
data was read.

## 9. Sanitized production resource evidence

Observed on 2026-07-29:

| Resource | Sanitized evidence |
|---|---|
| CPU | 4 online CPUs |
| RAM | 3.6 GiB total; 1.3 GiB used; 221 MiB free; 2.3 GiB available |
| Swap | 1.9 GiB total; 115 MiB used; 1.8 GiB available |
| Load | 0.40, 0.54, 0.44 |
| Root disk | 40 GiB total; 27 GiB used; 12 GiB available; 70% used |
| Uptime | 2 days, 4 hours, 13 minutes at inspection |
| Running-container memory | About 442–450 MiB aggregate across three bounded samples |
| Running-container CPU | Usually low, with short bursts in application containers |
| Docker images | 7.881 GB total; 4.233 GB reported reclaimable |
| Docker build cache | 5.188 GB total; 1.664 GB reported reclaimable |
| Docker volumes | 652 MB total; 542.6 MB reported reclaimable |

No cleanup was performed or authorized. The samples are capacity indicators,
not a load test or long-term performance study.

## 10. Current container topology

Eight containers were running, healthy, and had zero restart count:

- Personal Job Agent v2 edge;
- frontend;
- backend;
- outbox dispatcher;
- worker;
- Redis;
- PostgreSQL; and
- one legacy `job-agent-backend-1` container.

Observed limits were:

| Role | Memory limit | CPU limit |
|---|---:|---:|
| v2 edge | 128 MiB | 0.25 |
| frontend | 256 MiB | 0.50 |
| backend | 768 MiB | 1.00 |
| outbox | 256 MiB | 0.25 |
| worker | 768 MiB | 1.00 |
| Redis | 320 MiB | 0.50 |
| PostgreSQL | 768 MiB | 1.00 |
| legacy backend | not configured | not configured |

The observed production containers were non-privileged. All except PostgreSQL
had a read-only root filesystem.

## 11. Current network and port topology

- The only public host binding was the v2 edge on `0.0.0.0:8080`.
- Backend port 8000, PostgreSQL 5432, and Redis 6379 were container-internal
  exposures, not host bindings.
- `personal-job-agent-v2_application` contains the v2 application containers
  and uses bridge `pja-br0`.
- `personal-job-agent-v2_data` is internal and contains PostgreSQL, Redis,
  backend, worker, and outbox.
- `job-agent_application` contains the legacy backend and v2 edge.
- `mihomo.service` and the Personal Job Agent routing service were active.
- `pja-br0` was up. A verified policy rule handles TCP source port 8080 from
  that bridge.

The Java service must not receive a public port, attach to `pja-br0`, inherit
Mihomo proxy routing, or join the data network. The selected design adds one
explicitly shared internal bridge containing only FastAPI and Java.

## 12. Current Analyze flow

The public route and form fields are defined at
`backend/legacy_application.py:2526-2540`.

The effective flow is:

1. request logging creates or accepts a trusted Request ID
   (`backend/logging_utils.py:19-26`, `backend/logging_utils.py:91-124`);
2. middleware bounds Content-Length
   (`backend/app/auth/middleware.py:59-80`);
3. Session authentication runs
   (`backend/app/auth/middleware.py:84-104`);
4. Origin and CSRF checks run
   (`backend/app/auth/middleware.py:105-124`);
5. the route validates exactly one Resume source and exactly one JD source
   (`backend/legacy_application.py:2553-2619`);
6. the owned Resume Version is resolved or an uploaded PDF/DOCX is parsed
   (`backend/legacy_application.py:2630-2686`,
   `backend/app/resumes/service.py:155-177`, and
   `backend/legacy_application.py:437-485`);
7. pasted text is accepted or a URL is safely acquired
   (`backend/legacy_application.py:2718-2746`);
8. the current Analyze fingerprint is computed and PostgreSQL idempotency is
   claimed (`backend/legacy_application.py:2757-2804`);
9. Resume and JD security scanning runs
   (`backend/legacy_application.py:2806-2843`);
10. Project Knowledge is retrieved and scanned
    (`backend/legacy_application.py:2860-2949`);
11. the safe prompt is constructed
    (`backend/legacy_application.py:2951-2957`);
12. the primary DeepSeek call runs
    (`backend/legacy_application.py:2972-2985`);
13. at most one explicit format-only repair may run
    (`backend/legacy_application.py:3058-3106`);
14. an existing deterministic fallback is available
    (`backend/legacy_application.py:3092-3113`);
15. deterministic scoring and result reconciliation run
    (`backend/legacy_application.py:3162-3173`);
16. History and idempotency are finalized atomically
    (`backend/legacy_application.py:3240-3347`);
17. monitoring is persisted best-effort
    (`backend/legacy_application.py:3349-3354`); and
18. existing public error mapping and Request ID behavior apply
    (`backend/app/api/errors.py:184-220`,
    `backend/app/api/errors.py:251-283`).

The React screen, not the Analyze API, resolves Primary Resume and chooses its
active version (`frontend/src/legacy-workspace.jsx:952-978`). The API enforces
ownership of the submitted Resume Version.

## 13. Current JD preprocessing

Pasted JD input uses `.strip()`. URL input goes through
`SafeJobUrlFetcher` (`backend/legacy_application.py:488-496`,
`backend/app/jobs/acquisition.py:76-165`), which:

- canonicalizes the URL;
- rejects credentials, local/private/reserved/obfuscated destinations;
- resolves and pins globally routable addresses;
- revalidates each redirect, with at most five redirects;
- uses three-second connect and seven-second read bounds with no retries;
- bounds compressed input to 2 MiB and expanded text to 4 MiB; and
- restricts media types.

Both sources then pass through `structure_aware_truncate`
(`backend/analysis_fallback.py:40-111`), which removes NUL, normalizes line
endings, converts HTML to text, collapses whitespace, and applies
section-aware truncation. The configured JD default is 60,000 characters,
with an allowed configuration range of 1,000–120,000
(`backend/config.py:145-151`). The request Content-Length default is 12 MiB
(`backend/app/core/config.py:203-205`).

## 14. Current security-scan placement

The existing security scan runs after local preprocessing and after the
current fingerprint/idempotency claim
(`backend/legacy_application.py:2757-2843`). It produces
`context.sanitized_job_text`.

For the later Java integration, the safe order is:

1. perform URL safety and local bounds first;
2. scan the local effective JD;
3. never send a blocked local input to Java;
4. send only that scan's bounded sanitized text;
5. validate Java output; and
6. in `java` mode, scan Java normalized output again before RAG or prompting.

This dual scan is the smallest design that preserves current controls while
guarding against normalization transforming a security signal. In `shadow`,
the second scan is comparison-only and cannot change the user result.

## 15. Current Analyze fingerprint

The fingerprint is currently computed from the locally preprocessed
`context.job_text`, before JD security sanitization
(`backend/legacy_application.py:2757-2804`). Canonicalization is at
`backend/app/analyze/idempotency.py:116-152`.

Its current domain version is `analyze-request-fingerprint:v1`, with operation
`analyze:v1`. It includes the acquired/local JD hash and relevant
Resume/version, RAG/top-k, Project Knowledge, History choice, model, analysis
contract, and security policy inputs.

The safe later design retains that value as the stable input fingerprint and
adds a separate execution fingerprint for the authoritative normalization
result. Completed rows replay their stored response by matching the stable
input and are never recomputed or mutated.

## 16. Java normalize contract

The only proposed endpoint is:

`POST /api/v1/job-descriptions/normalize`

The controller is
`services/jd-normalization-service/src/main/java/io/github/hkjokerz/jobagent/jdnormalization/web/NormalizationController.java:27-75`.

Request:

- required `raw_text`;
- optional metadata `title`, `company`, and `location`, each at most 200
  characters; and
- optional `canonical_url`, at most 2,048 characters.

Response:

- `normalized_text`;
- SHA-256 hexadecimal `content_hash`;
- `normalization_policy_version`;
- `skill_dictionary_version`;
- required, preferred, and mentioned skill arrays containing stable ID/name
  pairs; and
- normalized optional metadata.

Contract bounds from `NormalizationPolicy.java:5-13` are:

- 512 KiB request body;
- 100,000 Unicode code points for text;
- 200 metadata characters;
- 2,048 canonical-URL characters; and
- at most 256 skills per bounded skill result.

Current versions are:

- normalization policy: `jd-normalization-v1`; and
- skill dictionary: `skills-v1`.

Normalization is deterministic: NFC normalization, NUL removal, Unicode line
ending normalization to LF, horizontal whitespace collapse, at most one blank
line, and no leading/trailing blank line. Skill output is dictionary-versioned
and stably sorted. The content hash is SHA-256 over normalized UTF-8 text.

The request filter accepts the same bounded Request ID grammar as FastAPI,
creates a trusted UUID when absent, returns a fresh trusted ID on invalid
input, and returns the trusted ID in the response. Errors use:

```json
{"error":{"code":"...","message":"...","request_id":"...","details":{}}}
```

Internal access uses one Bearer API key with constant-time digest comparison.
The service disables browser state, form login, Basic authentication, CSRF,
and CORS. Outside exact development loopback behavior, the key must be at
least 32 bytes.

No outbound HTTP/LLM client is present in the normalize path. The controller
calls in-process normalization and dictionary extraction. Calling normalize
does not call DeepSeek, make an external network request, or persist a JD.
Determinism applies to the same versioned text, metadata, policy, and
dictionary inputs.

Existing CI gives only bounded smoke evidence: an authorized normalize call
uses a 10-second curl maximum and the overall smoke passes. It does not
establish a production latency target or performance improvement.

## 17. Java runtime dependency analysis

The current full profile declares datasource, JPA, and Flyway configuration
and has database/schema readiness
(`services/jd-normalization-service/src/main/resources/application.yml:9-30`,
`:64-89`). Current Compose orders application startup after database migration
(`services/jd-normalization-service/compose.yml:76-115`).

Persistence controllers and services are already conditional on
`jd-normalization.persistence.enabled`, but setting that flag false is not
enough: database/JPA/Flyway auto-configuration would still start. A future
`normalization-only` profile must exclude those auto-configurations, disable
database health and schema health, and expose status-only readiness.

The current application image uses Java 21, UID 10001, a read-only Compose
filesystem, `MaxRAMPercentage=75`, 768 MiB/1 CPU for the application, 512 MiB
for PostgreSQL, and 384 MiB transiently for migration. Local images observed
during prior validation were approximately 527 MB for the application and
710 MB for migration; neither was published.

The current profile behavior contains an exact development-loopback
authentication exception. There is no current normalization-only Spring
profile.

## 18. Deployment option comparison

| Dimension | A: full Java + dedicated PostgreSQL | B: normalization-only | C: complete Java persistence | D: portfolio-only |
|---|---|---|---|---|
| Product need | Normalize is useful; DB is not | Exact fit | No evidence | Keeps current product |
| Architecture | Carries unused persistence | Narrow and honest | Unnecessary second data owner | Honest but disconnected |
| Complexity | App, DB, migration, backup | One stateless container | Highest | None |
| Memory/CPU | 768 MiB/1 CPU app + 512 MiB DB; migration transient | Candidate ceiling 384 MiB/0.5 CPU | Higher and usage-growing | None |
| Disk/backup | Images, DB, volume, backup, restore | Image only; no persistent data | Full retention/reconciliation | None |
| Security | More credentials/endpoints | Smallest surface | Largest data surface | No new surface |
| Failure isolation | DB/migration can block normalize | Local fallback isolates service | Cross-owner failures | Existing behavior |
| Rollback | Mode local, retain DB volume | Mode local, stop one container | Data-owner rollback | None |
| Development/tests | Deployment/DB operations | Focused profile/client/workflow | Large product program | None |
| Résumé/interview | Breadth but “why unused DB?” | Strong boundary and fallback evidence | Broad but weak justification | Limited integration evidence |
| Retired Jobs risk | Low but APIs present | Persistence absent | High | None |
| Distributed ownership | Operational DB without need | No new JD owner | High | None |

Option A remains only a fallback if a time-boxed profile spike proves Option B
requires disproportionate restructuring. Existing conditional persistence
components make that unlikely.

Option C is explicitly rejected. The repository shows no current product
requirement for Java-owned JD create/read/update/version storage. FastAPI
already owns Analyze History, and reviving a broad Jobs domain would create
unnecessary distributed ownership.

Option D remains the no-deployment choice if the bounded candidate cannot
meet reviewed resource, isolation, or latency requirements.

## 19. Selected option

Select **Option B: add a future stateless `normalization-only` Spring profile,
then integrate only the deterministic normalize endpoint behind FastAPI**.

This is a design recommendation, not deployment authorization.

## 20. Integration boundary

Java may own only:

- deterministic JD text normalization;
- deterministic explicitly supplied metadata normalization;
- deterministic lexical skill extraction;
- content hash; and
- policy and dictionary versions.

FastAPI retains:

- public authentication, Session, Origin, and CSRF;
- Resume ownership and Primary Resume behavior;
- upload handling;
- Job URL acquisition and SSRF protection;
- bounds and security scanning;
- Project Knowledge RAG and evidence scanning;
- safe prompt construction;
- Analyze idempotency;
- primary/repair provider behavior and deterministic fallback;
- History, user ownership, monitoring, error mapping, and public contract.

Java must not own users, browser sessions, History, Resume ownership, DeepSeek,
Project Knowledge, applications, rankings, tasks, approvals, or autonomous
actions. This is one private internal normalization service used by one
workflow, not a broad microservice migration.

## 21. Analyze placement

Recommended exact order:

1. establish the trusted FastAPI Request ID;
2. authenticate and validate the browser request;
3. enforce Resume and JD source rules;
4. resolve/parse the bounded Resume;
5. safely acquire pasted or URL JD, completing SSRF protections;
6. run existing local preprocessing and JD bound;
7. compute stable input identity and replay a matching completed result;
8. security-scan the local JD;
9. in sampled `shadow` or `java`, make one Java attempt with sanitized bounded
   text and propagated Request ID;
10. validate bytes, JSON, schema, hash, versions, skills, and Request ID;
11. security-scan successful Java normalized text;
12. choose effective source `local`, `java`, or `fallback`;
13. retrieve and scan Project Knowledge;
14. construct the safe prompt;
15. compute execution fingerprint and atomically claim idempotency;
16. execute the existing provider/repair or deterministic fallback;
17. finalize History/result/idempotency and best-effort monitoring.

Java normalization never precedes URL safety.

## 22. Feature-flag modes

Exactly three modes:

| Mode | Authoritative behavior |
|---|---|
| `local` | Preserve v2.0.4 behavior; make no Java call; immediate rollback |
| `shadow` | Local remains authoritative; deterministically sampled Java call; failure cannot fail Analyze |
| `java` | Valid Java output is effective; every Java boundary failure falls back locally |

Proposed names, aligned with current Analyze configuration conventions:

- `ANALYSIS_JD_NORMALIZATION_MODE`;
- `JD_NORMALIZATION_BASE_URL`;
- `JD_NORMALIZATION_API_KEY_FILE`;
- `JD_NORMALIZATION_CONNECT_TIMEOUT_MS`;
- `JD_NORMALIZATION_RESPONSE_TIMEOUT_MS`;
- `JD_NORMALIZATION_TOTAL_TIMEOUT_MS`;
- `JD_NORMALIZATION_MAX_RESPONSE_BYTES`;
- `JD_NORMALIZATION_EXPECTED_POLICY_VERSION`;
- `JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION`; and
- `JD_NORMALIZATION_SHADOW_SAMPLE_RATE`.

`local` starts without Java. `shadow` and `java` require valid private URL,
key source, bounds, and expected versions. Unknown modes fail startup.
Sampling is deterministic from a domain-separated stable-input hash, not user
identity or raw text.

## 23. Internal client

Use one application-scoped `httpx.AsyncClient`. `httpx` is already a
transitive dependency through the pinned OpenAI stack and is used in tests,
but it must become a direct backend requirement. It matches the async route.
The specialized `urllib3` Job URL client remains separate because it performs
DNS/IP pinning against untrusted destinations.

Candidate starting budgets:

- 200 ms connect;
- 600 ms read/write response;
- 800 ms application total;
- one application-level attempt;
- no automatic retry;
- no redirects;
- 256 KiB response limit; and
- pool limit 10, keep-alive 5.

These are containment values to validate, not measured performance targets.
Use `trust_env=False` so the private request does not traverse Mihomo. Close
the client during application shutdown.

Validate body size before JSON parsing, strict JSON schema, content hash,
versions, skill/metadata bounds, and response Request ID. Never log the
Authorization header, key, raw or normalized JD, title, company, location,
canonical URL, request body, or complete response.

## 24. Request ID propagation

Send the authoritative trusted FastAPI `X-Request-ID` to Java. Require Java's
response header to match exactly. On an error envelope, require
`error.request_id` to match the header too.

Missing, mismatched, invalid, or internally inconsistent Java IDs invalidate
the Java result and trigger local fallback. Record only a bounded reason such
as `request_id_missing`, `request_id_mismatch`, or `request_id_invalid`.

The FastAPI Request ID remains public-authoritative and observational only. It
is not authentication, authorization, idempotency, ownership, or user
identity.

## 25. Timeout and retry decision

Use one Java attempt. Do not configure transport or application retries.
Although normalize is deterministic and retry-safe, another synchronous
attempt adds latency and complicates the initial failure budget.

The candidate must measure actual latency before rollout values are accepted.
No performance improvement is claimed.

## 26. Fallback behavior

In `java`, any DNS, connection, timeout, HTTP, response-size, JSON, schema,
hash, version, skill-bound, metadata-bound, authentication, or Request ID
failure uses the current locally sanitized JD and records source `fallback`.

In `shadow`, current local behavior remains source `local` regardless of Java
outcome. Java cannot change RAG, prompt, History, response, or public errors.

A Java failure is never exposed directly. The user sees the normal Analyze
path or an existing FastAPI error unrelated to internal Java detail.

## 27. Fingerprint changes

Keep the current `analyze-request-fingerprint:v1` as a stable input
fingerprint for compatibility. Add a nullable execution fingerprint to the
existing PostgreSQL idempotency ledger; do not add a table.

The execution fingerprint includes:

- stable input fingerprint;
- effective normalized JD content hash;
- source `local`, `java`, or `fallback`;
- Java policy and dictionary versions when Java is authoritative;
- an integration-contract version; and
- existing Resume/RAG/model/security/scoring inputs through the stable value.

Safe transitions:

- local to shadow: no authoritative fingerprint change;
- shadow to java: new keys use Java identity;
- policy/dictionary update: new keys record new versions;
- Java failure: new work records fallback/local content;
- rollback: new keys use local;
- matching completed requests: replay stored results exactly across every
  transition, without calling Java or mutating History;
- unfinished same-key work with different source/version/content: reject it;
  and
- legacy null execution fingerprints: conservatively treat as legacy-local,
  never silently upgrade.

This prevents the same non-completed key from treating local and Java
normalization as equivalent while preserving completed replay.

## 28. Shadow comparison

Store no text, full metadata, Authorization, key, complete response, or actual
content hash. Compute hashes in memory and discard them after equality
comparison.

Emit one bounded structured observation containing only:

- attempt outcome;
- duration;
- local/Java normalized hash equality boolean;
- returned policy and dictionary versions;
- required/preferred/mentioned skill-ID difference counts;
- validation outcome; and
- bounded rejection/fallback reason.

Use structured logs initially, not a new table. A later demonstrated analytics
need may justify reviewed low-cardinality additions to existing monitoring,
but not a high-cardinality metric design.

## 29. Metrics

Low-cardinality evidence:

- mode and authoritative source;
- Java attempt, success, timeout, unavailable, and invalid-response counts;
- local fallback count;
- Java duration;
- shadow equality count;
- policy and dictionary mismatch counts; and
- Request ID propagation failure count.

Do not label metrics with Request ID, hash, JD, URL, metadata, or skill IDs.

Deployment review should report observed call count, success/fallback rate,
median and p95 latency, shadow comparison rate, Analyze failure correlation,
and Request ID propagation failures. Thresholds must follow candidate/shadow
measurement rather than invention.

## 30. Same-host resource feasibility

The observed 2.3 GiB available RAM, low baseline aggregate container memory,
four CPUs, zero restart counts, and 12 GiB disk headroom support one bounded
stateless candidate. They do not justify an unused PostgreSQL/migration/backup
stack.

Provisional candidate ceiling:

- 0.50 CPU;
- 384 MiB container memory;
- 128 PIDs;
- JVM `-Xms64m -Xmx256m`, with bounded metaspace/native allowance; and
- 64 MiB bounded `/tmp`.

Stop if Java approaches its memory ceiling, causes material swap growth,
restarts, affects host load, or cannot meet reviewed latency. Candidate
measurement may revise the budget before production activation.

The result is **feasible for Option B subject to candidate evidence**, not a
general claim that the host can safely absorb arbitrary Java/PostgreSQL work.

## 31. Production topology

Choose a separate stateless Java Compose project attached to one explicit
shared internal network also joined by FastAPI.

Java requirements:

- private service name only, no host port;
- no `pja-br0`;
- no FastAPI data network, PostgreSQL, Redis, volume, or credentials;
- non-root UID;
- read-only root filesystem;
- no-new-privileges and dropped capabilities;
- resource, PID, JVM, and bounded `/tmp` limits;
- status-only health/readiness;
- internal Bearer key; and
- independent start/stop/rollback.

This strategy gives a clearer lifecycle than adding the full stack to root
Compose, a production override/profile, or coupling Java to every application
cutover. Network ownership must be explicit so a generic project teardown
cannot remove a bridge still required by FastAPI.

If Option A were ever forced, it would additionally require a dedicated Java
PostgreSQL and volume, Flyway migration job, separate migration/runtime
credentials, database limits, backup retention, and restore validation. It
must never reuse FastAPI PostgreSQL/Alembic, Redis, credentials, ports, or
network.

## 32. Secret handling

Generate at least 32 random bytes through a secure mechanism that does not put
the value in shell history or logs. Store it outside Git in a root-controlled
0600 secret file. Inject it through a read-only file/config-tree mechanism,
not a Compose literal or environment inspection path.

Rotation:

1. set mode `local`;
2. retain the old key through rollback validation;
3. install the new secret file securely;
4. recreate/restart only Java with the new key;
5. recreate/restart FastAPI with the matching client key;
6. validate with synthetic data;
7. resume shadow/java only on evidence; and
8. remove the old key after rollback validation.

On compromise, select `local`, rotate, restart only the two consumers, and
inspect safe aggregate evidence. Do not write the key to Git, images, Compose
literals, command history, reports, logs, or `docker inspect` output.

## 33. Failure matrix

In `java`, every row falls back and records source `fallback`. In `shadow`,
source stays `local`. No Java detail is exposed to the user.

| Condition | Safe observation | Rollout action |
|---|---|---|
| DNS failure | `dns_failure` | fallback |
| Connection refused | `connection_refused` | fallback |
| Connect timeout | `connect_timeout` | fallback |
| Response timeout | `response_timeout` | fallback |
| HTTP 400 | `http_400` | fallback; contract/config review |
| HTTP 401 | `unauthorized` | fallback; stop rollout and repair secret |
| HTTP 413 | `payload_too_large` | fallback; review bounds |
| HTTP 422 | `validation_failed` | fallback; review contract |
| HTTP 500 | `java_internal` | fallback |
| HTTP 503 | `java_unavailable` | fallback |
| Malformed JSON | `malformed_json` | fallback |
| Oversized response | `oversized_response` | stop reading; fallback |
| Unsupported policy | `policy_mismatch` | fallback; stop rollout |
| Unsupported dictionary | `dictionary_mismatch` | fallback; stop rollout |
| Missing/mismatched/invalid Request ID | bounded Request ID reason | fallback |
| Java restart | unavailable/timeout counter | fallback |
| Java permanently disabled | mode `local` | no Java attempt |

Each new attempt's execution fingerprint records the selected authoritative
source. Completed replays retain their prior stored response.

## 34. Candidate validation

Run one isolated candidate with:

- synthetic Resume and JD;
- Mock DeepSeek or forced deterministic fallback;
- no production user data;
- no real DeepSeek or external LLM;
- normalization-only Java without PostgreSQL; and
- private-only connectivity.

Validate:

- local, shadow, and java;
- unknown-mode startup failure;
- Java authentication and Request ID propagation;
- success, timeout, unavailable, malformed, oversized, and unsupported-version
  behavior;
- local fallback and no automatic retry;
- effective JD selection and raw/local-before-normalized scan order;
- RAG, prompt, History, monitoring, and fingerprint inputs;
- same-key/different-source protection;
- completed replay after mode change;
- provider not called twice;
- health, limits, restart, and resource use; and
- absence of secrets or sensitive text in images, config, and logs.

One bounded candidate is sufficient.

## 35. Rollout

| Stage | Action | Progress evidence | Stop condition |
|---|---|---|---|
| 0 | Merge implementation in `local` | CI and public behavior unchanged | security, contract, History, or idempotency regression |
| 1 | Deploy private Java, FastAPI still `local` | health, private connectivity, synthetic auth/correlation, limits | public port, DB dependency, restart, resource or secret issue |
| 2 | Enable bounded sampled `shadow` | calls, success/fallback, median/p95, equality, no result change | correlated Analyze failure, ID failure, resource pressure |
| 3 | Review and correct measured incompatibilities | documented version/latency/validation evidence | unexplained mismatch or insufficient evidence |
| 4 | Switch to `java` with fallback | synthetic then normal authorized validation | Java-caused Analyze failure, version mismatch, unexplained fallback |
| 5 | Continue bounded monitoring | success/fallback/latency/resources, zero ID failures | any reviewed stop condition |

No calendar duration is invented. Evidence volume and reviewed stop conditions
govern progression.

## 36. Rollback

Primary rollback:

`ANALYSIS_JD_NORMALIZATION_MODE=local`

This requires no database rollback, image rebuild, Java data transformation,
Personal Job Agent schema downgrade, or History mutation. After local behavior
is verified, Java may be stopped independently.

Preserve prior Personal Job Agent image digests, existing Compose
configuration, Java configuration backup, prior internal key until rollback
validation, and candidate/rollout evidence. If Option A were ever used, retain
its volume during immediate rollback.

Matching completed idempotency rows replay their exact stored response across
the mode change. New requests use local execution identity. Historical results
are never mutated.

## 37. Test plan

FastAPI unit tests:

- local/shadow/java and unknown-mode startup rejection;
- Request ID propagation;
- API-key and sensitive-field redaction;
- timeout/unavailable/invalid/oversized/version fallback;
- no automatic retry;
- safe logs and shutdown cleanup.

Analyze integration tests:

- effective JD selection;
- dual scan ordering;
- RAG, prompt, History, and fingerprint inputs;
- completed replay;
- same key with different normalization source;
- fallback result; and
- provider not called twice.

Java profile tests:

- startup without PostgreSQL/JPA/Flyway;
- persistence endpoints unavailable;
- normalize, health, security, and Request ID;
- no database readiness; and
- full-profile regression.

Container/candidate tests:

- private-only connectivity and no host port;
- resource limits, health, and restart;
- secret absence; and
- synthetic local/shadow/java flow with no real provider.

## 38. Implementation phases

1. **Phase I — Java normalization-only runtime:** profile, database
   auto-configuration exclusion, status-only readiness, profile tests, and
   container smoke.
2. **Phase II — FastAPI client and modes:** direct `httpx` dependency,
   application client, configuration, local/shadow/java selection, Request ID,
   timeout, fallback, dual scan, observations, and tests.
3. **Phase III — idempotency and candidate:** execution fingerprint migration,
   replay/source compatibility, one isolated candidate, and documentation.
4. **Phase IV — production rollout:** explicit private network, separate
   stateless project, local-first deployment, evidence-gated shadow/java, and
   separate production report.

Do not combine implementation and production deployment into one PR.

## 39. Exact proposed files

No implementation begins until this set and its phase boundaries are reviewed.

Phase I — Java runtime/profile:

- `services/jd-normalization-service/src/main/resources/application.yml`
- `services/jd-normalization-service/src/main/resources/application-normalization-only.yml`
- `services/jd-normalization-service/Dockerfile`
- `services/jd-normalization-service/README.md`
- `services/jd-normalization-service/scripts/container-smoke.sh`
- `.github/workflows/jd-normalization-service-ci.yml`

Java tests:

- `services/jd-normalization-service/src/test/java/io/github/hkjokerz/jobagent/jdnormalization/NormalizationOnlyProfileIT.java`
- `services/jd-normalization-service/src/test/java/io/github/hkjokerz/jobagent/jdnormalization/web/SecurityWebTest.java`
- `services/jd-normalization-service/src/test/java/io/github/hkjokerz/jobagent/jdnormalization/web/NormalizationApiWebTest.java`

Phase II — FastAPI client/configuration/Analyze:

- `backend/requirements.txt`
- `backend/config.py`
- `backend/app/application.py`
- `backend/app/analyze/normalization_client.py`
- `backend/agent_workflow.py`
- `backend/legacy_application.py`
- `backend/logging_utils.py`
- `backend/test_config.py`
- `backend/test_jd_normalization_client.py`
- `backend/test_v203_analysis_resilience.py`
- `backend/test_v201_rag.py`
- `backend/test_analyze_request_correlation.py`
- `.env.example`
- `docs/V2_0_4_API.md` or the then-current API document

Phase III — fingerprint/candidate/monitoring:

- `backend/app/analyze/idempotency.py`
- `backend/app/db/models.py`
- `backend/alembic/versions/<next_revision>_add_analyze_execution_fingerprint.py`
- `backend/test_analyze_idempotency.py`
- `backend/test_v2_postgres_integration.py`
- `backend/monitoring_service.py` only if structured-observation support needs
  it
- `compose.java-candidate.yaml`
- `scripts/java-normalization-candidate.sh`
- `.github/workflows/ci.yml` if candidate validation belongs in CI

Phase IV — deployment:

- `compose.yaml` for the explicit FastAPI private-network attachment only
- `compose.java-normalization.yaml`
- `scripts/deploy-java-normalization.sh`
- `.env.production.example` or the repository's then-current placeholder-only
  convention
- operations/runbook documentation

Each phase also updates this design as evidence requires and adds a focused
Work Report plus `docs/work-reports/README.md`.

## 40. Go/no-go recommendation

**GO with normalization-only production integration**, implemented later in
bounded phases and activated only after the isolated candidate and shadow
evidence pass review.

Basis:

- repository evidence shows a deterministic, non-persisting normalize
  endpoint and conditional persistence components;
- product need is only deterministic JD normalization;
- production evidence supports one constrained stateless candidate;
- no product requirement justifies Java-owned JD persistence;
- FastAPI local fallback provides failure isolation and immediate rollback;
  and
- the narrow integration has honest portfolio/interview value because its
  boundary, security ordering, idempotency, and operations are defensible.

This is not a recommendation to integrate merely for résumé value, and it is
not authorization to deploy.

## 41. Risks and limitations

- Java and local normalization may differ meaningfully; shadow evidence must
  measure it.
- The current JAR still contains persistence dependencies; profile tests must
  prove they are inactive.
- JVM resident memory may exceed the provisional 384 MiB ceiling.
- Synchronous internal I/O adds latency.
- Stable/execution fingerprint separation changes claim ordering and needs
  PostgreSQL compatibility tests.
- Structured container logs are not a durable analytics warehouse.
- Production observations were short, aggregate samples, not a load test.
- Disk is finite; cleanup was neither performed nor authorized.
- No real provider-path Analyze or production user request was exercised.
- Existing CI establishes correctness/smoke evidence, not a production
  performance target.

## 42. Changed documentation files

- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/2026-07-29-java-production-normalization-integration-design-audit-work-report.md`
- `docs/work-reports/README.md`

No other file is allowed in the audit PR.

## 43. Commit SHA

The initial documentation commit SHA will be recorded here in a metadata-only
correction after the pull request is created. The correction commit cannot
self-embed its own SHA; the authoritative audit head remains visible in the
pull request and final delivery record.

## 44. Audit PR URL

The audit PR URL will be recorded here in the metadata-only correction after
the documentation branch is pushed and the pull request is created.

## 45. GitHub CI

The initial documentation head and final metadata-correction head will be
waited to completion. Final authoritative check status will be recorded in the
pull request and delivery record. The audit PR will not be merged.

## 46. Confirmation that runtime code was unchanged

Confirmed. The audit changes only the three documentation files in Section 42.

## 47. Confirmation that production configuration was unchanged

Confirmed. No production or repository runtime configuration was changed.

## 48. Confirmation that no production service was restarted

Confirmed. No production container or host service was restarted, stopped,
created, or reconfigured.

## 49. Confirmation that no production data was inspected

Confirmed. No Resume, JD, History, user, raw request, database row, or other
production application data was inspected.

## 50. Confirmation that no Java image was published

Confirmed. No application or migration image was published.

## 51. Confirmation that no release or deployment occurred

Confirmed. No tag, release, image publication, deployment, migration, or
Project Knowledge synchronization occurred.

## 52. Confirmation that no real DeepSeek or external LLM was called

Confirmed. No DeepSeek or other external LLM call was made during this audit.

## Supporting design

The complete sequence, diagrams, failure behavior, candidate design, rollout,
rollback, and exact file set are maintained in
[`../architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`](../architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md).
