# FastAPI Java Normalization Client Phase II Work Report

## 1. Repository

- Repository: `HKJoker-Z/personal-job-agent`
- Personal Job Agent production baseline: `2.0.4`
- Personal Job Agent Alembic head: `20260724_06`
- Approved design:
  `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- Implementation scope: approved integration-plan Phase II only

## 2. Phase I PR final head

Java normalization-only Phase I PR
[#32](https://github.com/HKJoker-Z/personal-job-agent/pull/32) was verified at
final head:

`23d1ecdc1fbf3d56428f2f83ea24b16eb6260657`

The complete Phase I Work Report was present. All 13 repository and Java checks
passed, all 37 Java PostgreSQL tests and nine normalization-only profile tests
ran with zero skips, Flyway V1/V2 were unchanged, and GitHub reported the PR
`CLEAN` and `MERGEABLE`.

## 3. Phase I merge commit

PR #32 was merged without squash, rebase, or admin bypass using normal merge
commit:

`e1daa69e98a583e2667fe9c70635ada1e5a87a7c`

No tag, release, image publication, deployment, production access, or Project
Knowledge synchronization accompanied the merge.

## 4. Starting main commit

The Phase II branch started from post-merge `main` at:

`e1daa69e98a583e2667fe9c70635ada1e5a87a7c`

Local `main` and `origin/main` matched. Post-merge repository CI run
`30510820272` and Java CI run `30510820236` completed successfully first.

## 5. Phase II branch

`feat/fastapi-java-normalization-client-shadow`

## 6. Exact scope

Phase II adds:

- validated `local` and `shadow` FastAPI settings;
- a focused application-scoped async Java normalization client;
- deterministic shadow sampling from the existing Analyze input fingerprint;
- first-scan-only outbound text and trusted Request ID propagation;
- bounded one-attempt transport, response reading, parsing, and validation;
- an observation-only second security scan;
- safe structured comparison/failure observations;
- configuration, client, Analyze, lifecycle, security-ordering, and replay
  tests; and
- configuration, API, security, architecture, and Work Report documentation.

## 7. Scope exclusions

This work does not change Java runtime code, its POM, Dockerfile, Compose,
Flyway files, normalization policy, or skill dictionary. It does not change
React, Alembic, database schema, Analyze idempotency storage, production
Compose, Nginx, release/deployment workflows, production configuration,
version metadata, or `docs/PROJECT_KNOWLEDGE.md`.

It does not enable Java-authoritative Analyze, add an execution fingerprint,
change a public API, publish an image, release, deploy, or access production.

## 8. Existing Analyze placement

Repository source confirms the existing sequence remains:

1. Session, Origin, CSRF, input, Resume ownership, and safe Job URL handling.
2. Local acquisition/preprocessing and bounds.
3. The existing Analyze fingerprint and PostgreSQL idempotency claim when an
   idempotency key is supplied.
4. Immediate completed replay before security scanning or provider work.
5. The existing first untrusted-input scan.
6. Project Knowledge retrieval, safe prompt, provider/repair or deterministic
   fallback, History finalization, monitoring, and public response.

Shadow work is inserted only after a successful first scan and before RAG. The
existing idempotency claim and fingerprint inputs were not moved or changed.

## 9. Configuration

`backend/config.py` adds these validated settings:

- `ANALYSIS_JD_NORMALIZATION_MODE`
- `JD_NORMALIZATION_BASE_URL`
- `JD_NORMALIZATION_API_KEY_FILE`
- `JD_NORMALIZATION_CONNECT_TIMEOUT_MS`
- `JD_NORMALIZATION_RESPONSE_TIMEOUT_MS`
- `JD_NORMALIZATION_TOTAL_TIMEOUT_MS`
- `JD_NORMALIZATION_MAX_RESPONSE_BYTES`
- `JD_NORMALIZATION_EXPECTED_POLICY_VERSION`
- `JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION`
- `JD_NORMALIZATION_SHADOW_SAMPLE_RATE`

The shadow origin must be absolute HTTP/HTTPS with a host and no userinfo,
query, fragment, or endpoint path. The key comes only from an absolute,
readable, size-bounded file and must contain 32–512 whitespace-free UTF-8
bytes. Errors never include the key or supplied path.

Candidate bounds are 200 ms connect, 600 ms read/write, 800 ms total,
256 KiB response, 10 total connections, and five keep-alive connections.
These are failure-containment values, not production performance claims.

## 10. Supported and rejected modes

- `local`: supported and default; requires no Java origin/key, creates no Java
  client, and makes no Java request.
- `shadow`: supported when all Java configuration validates; Java remains
  observation-only.
- `java`: reserved in the type but rejected at startup with a bounded message
  requiring the Phase III execution-fingerprint contract.

Unknown modes fail startup. No bypass or candidate/production activation was
added.

## 11. Explicit httpx dependency

`backend/requirements.txt` now directly pins `httpx==0.28.1`. FastAPI no
longer relies on the OpenAI SDK's transitive dependency for this boundary.
`pip check` passed.

## 12. Client lifecycle

FastAPI's lifespan creates one `JavaNormalizationClient` only in validated
`shadow` mode, reuses its `httpx.AsyncClient` across requests, and closes it
during shutdown. Local mode does not instantiate it. The specialized
untrusted Job URL fetcher remains separate and unchanged.

## 13. Proxy and redirect behavior

The client uses `trust_env=False`, `follow_redirects=False`, an explicit
`AsyncHTTPTransport(retries=0)`, and a fixed operator-controlled origin plus
the exact normalize path. It does not inherit proxy variables. Requests are
built directly and never copy browser cookies, Session authorization, Origin,
CSRF, Job URL, or metadata. Response cookies are not forwarded later.

## 14. Timeouts

Independent client timeouts cover connect, response read, response write, and
pool acquisition. Stable shadow outcomes distinguish `connect_timeout`,
`response_timeout`, and `unavailable`.

## 15. Total deadline

An outer `asyncio.timeout` enforces the configured total application deadline.
It encloses request execution, response streaming, JSON decoding, and strict
schema validation. Expiry maps only to `total_timeout`; Analyze continues.

## 16. Response-size enforcement

The client:

- rejects a declared `Content-Length` above the configured maximum;
- rejects invalid negative/non-numeric lengths;
- streams and counts actual bytes;
- stops before appending a chunk that would cross the maximum;
- closes every response in `finally`; and
- parses JSON only from the bounded collected bytes.

It never calls unbounded `response.json()`.

## 17. Request body

The request is exactly:

```json
{"raw_text":"<first-scan sanitized bounded JD>"}
```

The client also rejects empty input, more than 100,000 code points, or an
encoded JSON request above 512 KiB before transport. It sends only JSON
content negotiation, the internal Bearer key, and FastAPI's trusted
`X-Request-ID`.

## 18. Response schema

Success requires HTTP 200 and JSON media type. The exact accepted top-level
fields are:

- `normalized_text`
- `content_hash`
- `normalization_policy_version`
- `skill_dictionary_version`
- `required_skills`
- `preferred_skills`
- `mentioned_skills`
- `metadata`

Duplicate JSON properties, missing properties, extra properties, empty text,
unbounded text/skills/metadata, or unexpected nested structure are rejected.

## 19. Hash validation

`content_hash` must be exactly 64 lowercase hexadecimal characters. FastAPI
recomputes SHA-256 from UTF-8 `normalized_text` and requires equality.
Malformed or unequal hashes map to `hash_mismatch`. Actual hashes are not
logged or persisted.

## 20. Policy/dictionary validation

The returned normalization policy and skill dictionary versions must exactly
match the validated expected settings (defaults `jd-normalization-v1` and
`skills-v1`). Mismatches map to `policy_mismatch` or
`dictionary_mismatch`.

## 21. Skill validation

Each skill object contains exactly bounded `id` and `name` fields. IDs use a
bounded safe pattern and must be unique both within and across
required/preferred/mentioned arrays, which enforces non-contradictory category
precedence. The total is limited to 256 skills.

## 22. Request ID propagation

FastAPI remains the sole Request ID authority. The current trusted/generated
ID is sent to Java. A success response must include the same valid
`X-Request-ID`; missing, invalid, or unequal values map to
`request_id_mismatch`. Correlation is not authentication, ownership, or
idempotency, and a Java disagreement never changes the public ID or response.

## 23. Deterministic shadow sampling

Sampling hashes a domain-separated constant plus the binary form of the
existing stable Analyze input fingerprint. Rate zero samples none; rate one
samples all eligible requests; intermediate rates select a stable bounded
subset. It does not use time, randomness, raw JD, Resume text, user identity,
or Request ID. Sampling does not alter the fingerprint.

## 24. First security scan

The existing local Resume/JD scan completes first. Blocked input returns the
unchanged security error and is never sent to Java. Only
`context.sanitized_job_text` from this successful scan can cross the internal
client boundary.

## 25. Observation-only second scan

A strictly valid Java `normalized_text` receives the existing untrusted-text
scanner again. The result contributes only a bounded finding count to safe
evidence. It cannot block Analyze or change RAG, prompt construction, provider
behavior, History, monitoring persistence, fingerprint, or public output.

## 26. Local authoritative behavior

The local sanitized JD remains authoritative in every supported Phase II mode.
Local mode creates no Java client and performs no Java DNS resolution or
connection. Shadow Java text, metadata, hashes, and skills are never assigned
to the Analyze context and cannot become RAG/prompt/model/History input.

## 27. Safe observations

Successful structured observations are allowlisted to bounded fields:

- request ID, `mode=shadow`, `sampled=true`, and `outcome=success`;
- bounded duration;
- text-hash equality boolean, never a hash;
- bounded second-scan finding count; and
- expected Java policy/dictionary versions.

They contain no JD/Resume text, title/company/location, URL, response body,
headers, key, key path, or arbitrary exception string.

## 28. Failure outcome mapping

Bounded outcomes are:

- `connect_timeout`
- `response_timeout`
- `total_timeout`
- `unavailable`
- `unauthorized`
- `client_error`
- `server_error`
- `oversized_response`
- `invalid_json`
- `invalid_schema`
- `hash_mismatch`
- `policy_mismatch`
- `dictionary_mismatch`
- `request_id_mismatch`

Every failure is observation-only and makes no retry.

## 29. Secret and log safety

The JSON formatter adds only explicit observation fields. Client errors contain
only stable outcome codes. No HTTP request/response body or raw exception is
logged, and `httpx` logging remains at warning. Repository, Java, and image
history credential scans passed. No secret was committed.

## 30. Configuration tests

Thirteen tests cover default/explicit local, valid shadow, missing URL/key,
short/missing/relative/oversized/whitespace/invalid-UTF-8 keys, unsafe origins,
timeout/size/sample/version bounds, unknown/reserved modes, and error
redaction.

## 31. Client tests

Seventeen async MockTransport tests cover success, exact outbound contract,
authorization log safety, Request ID ownership, request bounds, one attempt,
no redirects/proxy/cookie forwarding, connection/read/write/total timeouts,
connection failure, required HTTP failures, JSON/content-type/duplicate-field
validation, declared/streamed size limits, strict shape/bounds, hash and
version checks, skill precedence/limits, response correlation, and pool
shutdown. They make no external network request.

## 32. Analyze integration tests

Nine focused tests cover local, unsampled shadow, sampled success/failure,
security ordering, blocked input, unchanged fingerprint inputs, lifespan,
deterministic sampling, and safe logging. They prove Java receives only the
sanitized JD, the second scan is observation-only, the provider remains local,
and canonical public results are unchanged.

## 33. Idempotency replay regression

The completed-replay test proves the stored response returns before Java,
History is not rewritten, and the provider is not called. Existing claim,
conflict, lease, finalization, cleanup, and replay behavior remains green.

## 34. Provider-call regression

Existing and new tests preserve SDK `max_retries=0`, at most one primary call,
and at most one explicit repair. Shadow success/failure does not add provider
calls or call a real provider. Deterministic test/fallback behavior remains
available.

## 35. Full backend validation

Local validation completed:

- focused Phase II tests: 59 passed;
- complete backend discovery: 473 tests, 0 failures/errors, with only the 10
  opt-in PostgreSQL tests skipped in that run;
- separate PostgreSQL integration: 10 passed, 0 skipped, through Alembic
  `20260724_06`;
- Python compile: passed;
- `pip check`: passed;
- public OpenAPI inspection: passed with no internal normalization route;
- frontend: 64 tests and production build passed;
- backend/frontend image build and non-root/sensitive-path checks: passed;
- root Compose and production-runtime regression: passed; and
- Version 2.0.4 isolated mock-provider product smoke: passed.

No real external provider was configured or called.

## 36. Java regression validation

The unchanged Java service completed:

- Maven Surefire: 67 passed, 0 skipped;
- Maven Failsafe: 46 passed, 0 skipped;
- seven PostgreSQL/Flyway classes: 37 passed, 0 skipped;
- normalization-only profile integration: nine passed;
- full-profile container smoke: healthy, zero restarts, migration replay and
  persistence/update/history checks passed; and
- no-database normalization-only smoke: healthy, zero restarts, no OOM,
  no database container, persistence route absent, normalize-only OpenAPI.

The no-database smoke observed 189.6 MiB at one bounded point in time under
the provisional 384 MiB ceiling. That is not a production sizing claim.
Its local image identifier was
`sha256:9590cdb643d1aa8138bb5ce84fd46d0992d0fb68f74b77f719e084cd8348f8a4`;
no image was published.

## 37. GitHub CI

Implementation head `dc4910e4236554fec26da3edb6e98f690c8b3b67` passed all
10 repository check contexts in run `30511935784`.

The complete implementation/documentation head
`175077a39a9ff208921c0a5fc8bafd31b3c760a1` passed all 13 PR check
contexts:

- repository CI run `30512737156` completed successfully with backend tests,
  frontend build, backend PostgreSQL, Docker build, PostgreSQL backup/restore,
  Compose validation, production-runtime regression, script validation,
  repository safety, and the Version 2 Docker smoke all successful; and
- Java CI run `30512737140` completed successfully with `verify`,
  full-profile `container-smoke`, and
  `normalization-only-no-database-smoke` all successful.

This CI-delivery metadata correction triggers one final check set. The final
authoritative status remains the PR check rollup on the resulting report-only
head.

No workflow logs in to a registry, publishes, releases, deploys, uses
production credentials, or uses `pull_request_target`.

## 38. Changed files

Backend implementation and tests:

- `backend/app/analyze/normalization_client.py`
- `backend/app/analyze/normalization_shadow.py`
- `backend/config.py`
- `backend/legacy_application.py`
- `backend/logging_utils.py`
- `backend/requirements.txt`
- `backend/test_analyze_idempotency.py`
- `backend/test_analyze_normalization_shadow.py`
- `backend/test_java_normalization_client.py`
- `backend/test_java_normalization_config.py`

Documentation:

- `.env.example`
- `README.md`
- `docs/V2_0_3_API.md`
- `docs/V2_SECURITY.md`
- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/2026-07-30-fastapi-java-normalization-client-phase-2-work-report.md`
- `docs/work-reports/README.md`

## 39. Commit SHAs

- `e01598ae09c42a150c60fbb2a212e66c079f014f` — add bounded Java
  normalization configuration, direct dependency, client, and unit tests.
- `13bbfdb5231c435504c1cba69ffe75e7eb9e1567` — add observation-only
  Analyze shadow orchestration, safe logging, and integration/replay tests.
- `dc4910e4236554fec26da3edb6e98f690c8b3b67` — isolate the new
  integration-test application from the shared legacy application.
- `175077a39a9ff208921c0a5fc8bafd31b3c760a1` — document the completed
  implementation, validation evidence, risks, limitations, and rollback.

The final CI-delivery metadata commit follows these commits. It cannot
self-embed its own SHA; Git history and the PR commit list are the
authoritative delivery record.

## 40. PR URL

<https://github.com/HKJoker-Z/personal-job-agent/pull/33>

Title: `Backend: Add Java normalization shadow client`

The PR is intentionally not merged by this work.

## 41. Risks and limitations

- Shadow has isolated test/CI evidence only, not production latency, load, or
  availability evidence.
- The configured origin is operator-controlled trusted infrastructure; it is
  intentionally not a replacement for the separate untrusted Job URL SSRF and
  DNS-pinning client.
- Structured logs provide bounded comparison evidence but no durable
  analytical table or production dashboard.
- A local Java difference cannot affect the product result, so shadow can
  reveal differences but cannot validate authoritative idempotency semantics.
- Java-authoritative mode remains unavailable until Phase III adds the
  execution-fingerprint migration and compatibility rules.

## 42. Rollback

Before merge, close PR #33. After a future merge, retain or restore
`ANALYSIS_JD_NORMALIZATION_MODE=local`; this creates no client and preserves
the previous path. Revert the Phase II commits if code removal is desired.

No database downgrade, Alembic/Flyway action, data migration, image rollback,
release rollback, or production operation is required because none occurred.

## 43. Confirmation that Java-authoritative mode was not enabled

Confirmed. `java` is reserved but fails startup with the Phase III
execution-fingerprint prerequisite. No Java result becomes the effective JD.

## 44. Confirmation that Analyze fingerprint was unchanged

Confirmed. The existing fingerprint function, fields, idempotency claim, and
storage were not modified. Shadow reads the same fingerprint solely for
domain-separated sampling.

## 45. Confirmation that no Alembic migration was added

Confirmed. Alembic remains at `20260724_06`; no migration or schema file
changed.

## 46. Confirmation that Java runtime code was untouched

Confirmed. No Java source, resource, test, POM, Dockerfile, Compose, migration,
policy, or dictionary file changed in Phase II. Java was regression-tested
only.

## 47. Confirmation that production was untouched

Confirmed. No production system, credential, host, database, configuration,
deployment, or Project Knowledge was accessed or modified.

## 48. Confirmation that no image was published

Confirmed. Images were built only in the isolated local Docker daemon for
validation. There was no registry login or push.

## 49. Confirmation that no release or deployment occurred

Confirmed. No tag, release, publication, rollout, restart, or deployment
occurred. PR #33 remains unmerged.

## 50. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Tests and smokes used mocks, deterministic test providers, or
fallbacks with the provider key unset. No real DeepSeek or other external LLM
request was made.
