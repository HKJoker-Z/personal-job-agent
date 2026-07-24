# HTTP Request Correlation and Analyze Idempotency Design Audit

Date: 2026-07-24

Repository: `https://github.com/HKJoker-Z/personal-job-agent`

Application version: `2.0.3`

Schema head: `20260721_05`

Audit type: documentation-only, read-only design review

## Executive conclusion

The next portfolio phase should preserve the request-correlation code that
already exists, close its security-middleware coverage gap, define a stable
error envelope only for the Analyze workflow, and add opt-in PostgreSQL-backed
idempotency for `POST /api/analyze`. A dedicated PostgreSQL table should be the
source of truth and should be unique by authenticated user, operation, and
hashed idempotency key. The winner should claim the key in a short transaction,
perform the synchronous Analyze pipeline without holding a database lock, and
atomically persist the optional History row and terminal idempotency response.
A request whose process disappears after the provider call starts must become
`indeterminate`; automatically calling the provider again would make an
unsupported exactly-once claim.

This audit did not change runtime code, migrations, frontend behavior,
configuration, or infrastructure. It did not access production and did not
call DeepSeek.

## 1. Repository

- Repository: `HKJoker-Z/personal-job-agent`
- Starting `main` commit before the performance merge:
  `f731c24c75a81d9c7cbda86963067a39dbf09b86`
- PR #18 expected head:
  `38c0ca30c059d2e2dccca97ee00001beae328f44`
- PR #18 URL:
  `https://github.com/HKJoker-Z/personal-job-agent/pull/18`
- Application version: `2.0.3`, from
  `backend/config.py:10` and confirmed by a local import.
- Alembic head: `20260721_05`, confirmed with
  `backend/.venv/bin/alembic heads`.

## 2. PR #18 merge verification

PR #18 was open at the expected head when it was reviewed. GitHub reported it
mergeable and clean, and all ten checks were successful:

1. `backend-tests`
2. `frontend-build`
3. `backend-postgres`
4. `docker-build`
5. `postgres16-backup-restore`
6. `compose-validation`
7. `production-runtime-regression`
8. `script-validation`
9. `repository-safety`
10. `docker-smoke-v2`

The PR description, PostgreSQL case study, and Phase 1 Work Report agreed on
the measured results:

| Evidence | Before | After |
|---|---:|---:|
| SQL median execution time | 541.065 ms | 185.212 ms |
| Application median time | 1,308.238 ms | 163.765 ms |
| Rows reaching aggregation | 194,399 | 6 |
| External merge sort | 17,656 KiB | Removed |

The benchmark recorded `RESULTS_IDENTICAL=true`. The changed-file review
confirmed that the PR changed the aggregate query, its PostgreSQL regression
test, plan artifacts, and documentation. It did not add a migration, index,
cache, production configuration, release, tag, deployment, or frontend
behavior change.

PR #18 was merged with a merge commit, without squash, rebase, or admin
bypass.

## 3. PR #18 merge commit and main CI

- Merge commit:
  `8d1cb3a837ba4242a8ed0f82d5ab2113a47d2466`
- Merge parents:
  `f731c24c75a81d9c7cbda86963067a39dbf09b86` and
  `38c0ca30c059d2e2dccca97ee00001beae328f44`
- Merge time: `2026-07-24T15:28:55+08:00`
- Main CI run:
  `https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30075604538`
- Main CI result: all ten jobs completed successfully.
- After `git pull --ff-only origin main`, local `main`, `origin/main`, and
  `HEAD` all resolved to the merge commit.

No release, tag, deployment, production Project Knowledge synchronization, or
production access followed the merge.

## 4. Audit branch

- Branch: `audit/http-idempotency-request-correlation`
- Branch point:
  `8d1cb3a837ba4242a8ed0f82d5ab2113a47d2466`
- Allowed scope used: this Work Report and the Work Report index only.
- Runtime application behavior was not changed.

## 5. Current Analyze request flow

The production composition extends the legacy FastAPI application with the
Version 2 routers and then adds Feature Retirement and security middleware in
`backend/app/application.py:11-25`. Starlette places the last added middleware
outermost, matching the source comment at `backend/app/application.py:21-24`.

The real synchronous request path is:

1. **Body-size, authentication, Origin, and CSRF gate.**
   `V2SecurityMiddleware.dispatch` at
   `backend/app/auth/middleware.py:58-118` checks `Content-Length`, opens the
   request SQLAlchemy session, authenticates the server-side session cookie,
   rejects untrusted Origin or Referer origins, validates the session-bound
   `X-CSRF-Token`, and commits or rolls back the request session after the
   downstream response.
2. **Session lookup and account state.**
   `AuthService.authenticate` at `backend/app/auth/service.py:123-157` hashes
   and looks up the cookie, rejects missing, expired, or revoked sessions,
   loads the user, rejects disabled users, and periodically touches the idle
   expiry. Remember Me uses the absolute expiry behavior defined at
   `backend/app/auth/service.py:84-114` and `143-156`.
3. **Multipart request validation.**
   `POST /api/analyze` is declared at
   `backend/legacy_application.py:2421-2434`. It accepts one uploaded Resume
   or `resume_version_id`, one pasted JD or Job URL, History and RAG flags,
   top-k values, and RAG mode.
4. **Resume and JD source validation.**
   Mutual-exclusion and size/type checks run at
   `backend/legacy_application.py:2441-2493`.
5. **Resume acquisition.**
   Stored versions are owner-scoped by
   `ResumeService.analysis_text` at `backend/app/resumes/service.py:155-177`.
   Uploaded PDF or DOCX files are parsed and bounded at
   `backend/legacy_application.py:2495-2536`.
6. **Job Description acquisition.**
   Pasted text is used directly, or the URL is fetched at
   `backend/legacy_application.py:2538-2568`. The URL fetcher canonicalizes and
   resolves the destination, rejects local/private targets, pins an address,
   uses a 3-second connect and 7-second read timeout, disables HTTP retries,
   bounds redirects and response size, and rejects unsafe media behavior in
   `backend/app/jobs/acquisition.py:76-155`.
7. **Input security.**
   Resume and JD text are sanitized, scanned for prompt injection and
   credential-like content, and may be blocked before model invocation at
   `backend/legacy_application.py:2570-2607`.
8. **Project Knowledge retrieval.**
   RAG is skipped when off. Otherwise the code ensures the configured Project
   Knowledge document is indexed and runs the current search at
   `backend/legacy_application.py:2609-2658`, with the helper at
   `backend/legacy_application.py:1609-1640`. Retrieved evidence is scanned at
   `backend/legacy_application.py:2660-2713`.
9. **Prompt creation.**
   The safe prompt is constructed at
   `backend/legacy_application.py:2715-2734`, using bounded, redacted sections
   from `backend/safe_prompt.py:53-107`.
10. **DeepSeek analysis call.**
    `call_deepseek_raw` is invoked at
    `backend/legacy_application.py:2736-2770`. Its implementation at
    `backend/legacy_application.py:1116-1239` creates a synchronous OpenAI
    client against the DeepSeek base URL with the configured timeout and
    emits safe start/success/failure logs.
11. **Provider-output scan, tolerant parsing, and repair.**
    Provider output is scanned at
    `backend/legacy_application.py:2772-2816`. Local parsing is attempted
    first; one format-only provider repair is allowed by
    `model_response_to_result` at
    `backend/legacy_application.py:1290-1320`, using
    `call_deepseek_repair` at `backend/legacy_application.py:1242-1287`.
12. **Deterministic fallback.**
    Provider exceptions and unusable output are converted to a structured
    local fallback rather than normally becoming an HTTP error, at
    `backend/legacy_application.py:2754-2770` and `2837-2872`. Existing tests
    assert a 200 fallback for timeout and provider 5xx simulations at
    `backend/test_v203_analysis_resilience.py:184-206`.
13. **Evidence reconciliation and final business result.**
    Evidence validation, deterministic scoring, safe claims, and next-action
    selection run at `backend/legacy_application.py:2874-2989`.
14. **Optional History insert.**
    When requested, a History row is inserted at
    `backend/legacy_application.py:2992-3017` through
    `backend/database.py:858-951`.
15. **Finalization and post-insert History update.**
    The response is assembled at
    `backend/legacy_application.py:3025-3066`. Final workflow steps and
    duration are written in a second database operation at
    `backend/legacy_application.py:3068-3074` through
    `backend/database.py:1082-1112`.
16. **Monitoring.**
    Analysis and step observations are built at
    `backend/legacy_application.py:1769-1814` and persisted best effort by
    `backend/monitoring_service.py:236-349`.
17. **Response.**
    The completed dictionary is returned at
    `backend/legacy_application.py:3083`.

### Timeout and retry behavior

- Browser `fetch` has no `AbortController`, deadline, or network retry in
  `frontend/src/api/client.js:22-38`.
- The frontend performs one special retry only after a CSRF-related 403,
  refreshing the session and resending the original request at
  `frontend/src/api/client.js:30-36`.
- The Job URL fetcher has bounded connect/read timeouts and explicitly sets
  `retries=False`.
- The model timeout defaults to 60 seconds and is bounded to 5-300 seconds at
  `backend/config.py:128-130`.
- The pinned dependency is `openai==2.44.0` at
  `backend/requirements.txt:9`. Local signature inspection showed that the
  client default is `max_retries=2`; neither provider client construction at
  `backend/legacy_application.py:1158-1162` nor
  `backend/legacy_application.py:1251-1255` overrides it. Therefore one
  logical primary or repair call can include SDK-level transport retries.
- The synchronous OpenAI client is called directly inside an async route. This
  audit does not propose changing the synchronous API model, but an
  implementation should keep request idempotency independent of connection
  lifetime.

## 6. Current transaction boundaries and partial-state analysis

There is not one transaction covering the Analyze workflow.

1. `V2SecurityMiddleware` creates the request-scoped SQLAlchemy session at
   `backend/app/auth/middleware.py:68-69` and commits responses below 500 or
   rolls back responses at or above 500 at lines `97-101`. This transaction
   covers session touch and the stored Resume lookup, not the compatibility
   History writes.
2. `insert_application_record` opens a separate psycopg compatibility
   connection. Its context manager commits on normal exit at
   `backend/database.py:107-115`, so the History insert is durable before the
   rest of Analyze finalization.
3. `update_application_workflow_steps` opens and commits another connection.
4. `record_analysis_metric` and `record_step_metrics` each open and commit
   separate connections. Best-effort handling prevents their failure from
   failing a successful Analyze response.

Consequences:

- A failure before the History insert leaves no History row, although a
  failed monitoring observation may already be committed.
- A failure after the History insert and before or during the workflow-step
  update can return an error while leaving a durable, incomplete History row.
- A second user retry creates a new workflow ID and can call DeepSeek again
  and insert a second History row.
- Monitoring can contain the aggregate metric without all step metrics if the
  second persistence operation fails.
- No provider partial response is stored before History, but a process loss
  after the external provider accepted the call leaves no durable fact that
  can safely prove whether the call occurred.
- There is no explicit client-disconnect check. Work may continue after a
  disconnect; process cancellation or shutdown can interrupt it. Correctness
  must not depend on the connection remaining open.

## 7. Current duplicate-request risks

There is no idempotency handling on `POST /api/analyze`:

- No `Idempotency-Key` header is read.
- No request fingerprint is computed.
- No unique row or lock represents an in-progress Analyze request.
- History uniqueness is unrelated to Analyze input.
- Each attempt creates a new `workflow_id` at
  `backend/legacy_application.py:2435-2439`.

Repeated requests can independently invoke the primary model call and, when
needed, the one allowed repair call. SDK transport retries may add more
provider HTTP attempts. Repeated requests can independently persist History
rows and return different model or fallback results.

The frontend does prevent two submissions in one mounted component while the
first promise is pending: `loading` and `submittingRef` are checked at
`frontend/src/legacy-workspace.jsx:875-879`, set at lines `913-914`, cleared at
lines `931-933`, and the button is disabled at lines `1017-1019`. The behavior
is tested at `frontend/src/pages/V201Pages.test.jsx:109-136`.

That UI guard does not cover:

| Retry source | Covered now? | Reason |
|---|---|---|
| Second click in the same mounted page | Yes | React state plus `submittingRef` |
| Page refresh or navigation and resubmit | No | Component state and ref are lost |
| Browser or reverse-proxy replay | No | No server key or fingerprint |
| Mobile network retry | No | No server key or fingerprint |
| Concurrent tabs | No | Each tab has independent state |
| Manual retry after ambiguous timeout | No | New request is indistinguishable |
| CSRF refresh retry | Only at UI transport level | The request is resent without an idempotency key; CSRF currently fails before route execution, but no general replay guarantee exists |

## 8. Current request-ID behavior

Request correlation is partially implemented.

- Accepted client syntax is
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` at
  `backend/logging_utils.py:18`.
- A valid `X-Request-ID` is preserved; an absent or invalid value is replaced
  with a UUIDv4 at `backend/logging_utils.py:22-25`.
- `RequestLoggingMiddleware` places the ID in a `ContextVar` and
  `request.state`, returns it in `X-Request-ID`, and emits a structured
  completion log at `backend/logging_utils.py:85-120`.
- `JsonFormatter` automatically adds the ContextVar request ID to application
  logs at `backend/logging_utils.py:28-51`.
- Unit coverage for generation, accepted IDs, replacement, response headers,
  safe fields, and secret exclusion exists at
  `backend/test_logging_utils.py:50-100`.

The limitations are material:

1. `V2SecurityMiddleware` is outermost, while request logging was added
   earlier at `backend/legacy_application.py:335`. Early body-size,
   authentication, Origin, CSRF, admin-role, and database-error responses
   bypass request-ID generation, the header, and completion logging.
2. An isolated middleware-order probe produced a 401 with
   `X-Request-ID: None` and zero completion logs for a protected request.
3. Error response bodies do not contain the request ID.
4. The frontend does not generate an `X-Request-ID` and does not read the
   response header.
5. CORS exposes only `Content-Disposition` at
   `backend/legacy_application.py:325-332`; cross-origin browser code cannot
   read `X-Request-ID`.
6. Request context correlates normal in-process logs, including current
   provider log messages, but the ID is not explicitly persisted with
   provider-call, idempotency, History, or monitoring metadata.
7. A request ID is observational metadata, not unique storage and not an
   authorization or idempotency credential.

## 9. Current error formats

The API currently exposes several shapes:

| Source | Status examples | Current body |
|---|---|---|
| Security middleware | 400, 401, 403, 413, 503 | `{"detail": "..."}` |
| Global HTTP exception handler | Any route status | `{"detail": <string-or-object>}` |
| Global validation handler | 400 | `{"detail": "Invalid request..."}` |
| Global unknown exception handler | 500 | `{"detail": "Unexpected server error..."}` |
| Analyze workflow failure | 400, 422, 502 | `{"detail":{"message":...,"workflow_id":...,"error_code":...,"error_stage":...}}` |
| Analyze security block | 422 or 502 | Nested `detail` plus safe security and workflow metadata |
| Retired feature middleware | 410 | `{"error":{"code":"FEATURE_REMOVED","message":"..."}}` |

The handlers are at `backend/legacy_application.py:338-379`. Analyze-specific
error construction is at `backend/legacy_application.py:1734-1766` and
`1817-1879`.

Frontend parsing is also split:

- `frontend/src/api/client.js:11-20` expects top-level `detail`.
- `frontend/src/api/client.js:30-35` detects CSRF by searching English text in
  `detail`.
- The legacy Analyze helper sets `error.payload = data.detail` at
  `frontend/src/legacy-workspace.jsx:157-165`.
- Analyze maps a small set of provider codes at
  `frontend/src/legacy-workspace.jsx:18-24` and `150-155`.

Provider timeout, provider 5xx, and invalid structured output normally become
a successful deterministic fallback with `analysis_status="fallback"`.
Changing those cases to HTTP errors would be a behavior regression and is not
recommended.

## 10. Proposed request-ID design

### Identifier choice

| Choice | Advantages | Costs or concerns | Decision |
|---|---|---|---|
| UUIDv4 | Already implemented and tested; unpredictable; standard library; 122 random bits | Not time-sortable | **Recommended** |
| UUIDv7 | Time-sortable and useful for database locality | Adds no value for log-only IDs; exposes creation time; current code does not use it |
| ULID | Compact, sortable, readable | New encoding/dependency and time leakage; unnecessary compatibility change |
| Custom opaque ID | Can use a product prefix | Reimplements a solved format and does not improve correlation |

Retain server-generated canonical UUIDv4 strings. Retain valid client IDs for
backward compatibility.

### Contract

- Header: `X-Request-ID`.
- Accepted client length: 1-64 ASCII characters.
- Accepted syntax:
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`.
- Normalization: none. Do not trim, lowercase, or case-fold; invalid input is
  replaced with a new UUIDv4.
- Response: always include `X-Request-ID`, including authentication,
  authorization, validation, CSRF, body-size, and unknown-error responses.
- Error body: always use the current request ID in the proposed Analyze error
  envelope.
- CORS: expose `X-Request-ID` and `Idempotency-Replayed`.
- Collision handling: server-generated collision probability is negligible;
  generate another value only if a local generation test ever detects one.
  Client IDs are not guaranteed unique and duplicate IDs are accepted because
  they are not credentials or storage keys.
- Structured log fields:
  `request_id`, `method`, `route`, `status_code`, `duration_ms`,
  `workflow_id`, `operation`, `idempotency_status`,
  `idempotency_replayed`, `error_code`, and `error_stage`.
- Never log the raw idempotency key, session cookie, CSRF token, Resume/JD
  content, provider body, or private database identifiers.

### Placement

Request-ID creation and completion logging must wrap the security middleware.
The smallest implementation is to make one correlation middleware the
outermost middleware and keep security default-deny inside it. This does not
weaken authentication, Origin, or CSRF checks.

Provider logs emitted in the same request context already inherit the
`ContextVar`. The implementation should also record the request ID on the new
idempotency row and in local provider-call telemetry. It should not send a
user-supplied identifier to DeepSeek unless that provider has a documented,
safe metadata field. No History business column is needed initially: the
idempotency row can reference the History row and retain the original request
ID, forming the audit link without putting log metadata into user content.

No OpenTelemetry collector, Jaeger, service mesh, or distributed tracing
infrastructure is justified in this phase.

## 11. Proposed stable Analyze error schema

Use one envelope for Analyze and its pre-route security errors:

```json
{
  "error": {
    "code": "IDEMPOTENCY_KEY_REUSED",
    "message": "The idempotency key was already used with different input.",
    "request_id": "4b380279-0d90-4a4f-9361-7cc0d96df274",
    "details": {}
  }
}
```

All four fields are mandatory:

- `code`: stable uppercase machine code.
- `message`: safe, bounded English fallback suitable for display.
- `request_id`: current HTTP request correlation ID.
- `details`: always an object; use `{}` when no safe structured detail exists.

Safe details may include field names, bounded validation reasons, workflow ID,
error stage, retryability, and sanitized security findings. They must not
include stack traces, exception text, SQL, filesystem paths, internal IP
addresses, database IDs not already authorized for the user, provider
response bodies, prompts, Resume/JD text, tokens, cookies, CSRF values, or
secrets.

### Focused initial Analyze codes

| Code | Typical status | Meaning |
|---|---:|---|
| `AUTHENTICATION_REQUIRED` | 401 | No valid active server-side session |
| `REQUEST_ORIGIN_NOT_TRUSTED` | 403 | Origin/Referer policy failed |
| `CSRF_VALIDATION_FAILED` | 403 | Session-bound CSRF failed |
| `REQUEST_TOO_LARGE` | 413 | Request exceeds configured body limit |
| `REQUEST_VALIDATION_FAILED` | 400 | Multipart/form validation failed |
| `RESUME_SOURCE_INVALID` | 400 | Resume source combination/type/size invalid |
| `RESUME_NOT_FOUND` | 404 | Owned Resume Version not found |
| `RESUME_PARSING_FAILED` | 400 | Uploaded or stored Resume has no usable text |
| `JOB_SOURCE_INVALID` | 400 | JD source combination invalid |
| `JOB_DESCRIPTION_ACQUISITION_FAILED` | 400 | URL or pasted JD could not be safely acquired |
| `INPUT_SECURITY_BLOCKED` | 422 | Credential-like or unsafe input blocked |
| `PROJECT_KNOWLEDGE_RETRIEVAL_FAILED` | 500 | Current Project Knowledge retrieval failed safely |
| `OUTPUT_SECURITY_BLOCKED` | 502 | Provider output failed the output security gate |
| `ANALYZE_PERSISTENCE_FAILED` | 503 | Required History/idempotency finalization failed |
| `IDEMPOTENCY_KEY_INVALID` | 400 | Header syntax or length invalid |
| `IDEMPOTENCY_KEY_REUSED` | 409 | Same scoped key, different fingerprint |
| `IDEMPOTENCY_REQUEST_IN_PROGRESS` | 409 | Same request is still running |
| `IDEMPOTENCY_KEY_EXPIRED` | 409 | Replay guarantee expired; use a new key |
| `IDEMPOTENCY_OUTCOME_UNKNOWN` | 409 | Provider may have run; automatic replay is unsafe |
| `UNEXPECTED_SERVER_ERROR` | 500 | Unclassified safe internal failure |

Provider timeout or malformed output should continue to return a 200 fallback
when the deterministic fallback succeeds. Only failure to produce any safe
result should use a provider-related terminal error.

### Backward compatibility

Apply the envelope only to `POST /api/analyze` and security responses for that
path in Phase A. Update the current frontend in the same implementation PR to
prefer `error.code`, `error.message`, and `error.details`, while temporarily
accepting legacy `detail` for other endpoints. Preserve existing Analyze HTTP
statuses where practical; the initial change should not globally restore
FastAPI's default 422 behavior. Replace frontend English-text CSRF detection
with the stable code, but keep the legacy text fallback during transition.

Broad conversion of every API endpoint is explicitly deferred.

## 12. Proposed idempotency storage

Use a dedicated PostgreSQL table as the durable source of truth.

### Options evaluated

| Option | Decision |
|---|---|
| Dedicated PostgreSQL table | **Selected.** Durable, transaction-capable, multi-process safe, already an authoritative dependency |
| Redis only | Rejected. Redis is not an acceptable sole durable result ledger and can be evicted or unavailable |
| PostgreSQL plus Redis | Deferred. Redis may later accelerate completed lookups, but PostgreSQL must remain authoritative |
| Reuse History | Rejected. History is optional, is created too late, has no key/fingerprint/state, and cannot represent `save_to_history=false` |
| Reuse monitoring tables | Rejected. They are best effort and split across transactions |
| Reuse Agent Runs | Rejected. New Agent Runs are retired, their asynchronous lifecycle does not match synchronous Analyze, and reusing them would couple a current path to a retired workflow |
| In-process Python lock | Rejected. It fails across processes and restarts |

Idempotency is opt-in by `Idempotency-Key`. Requests without the header retain
current behavior for backward compatibility and are not deduplicated.

## 13. Proposed PostgreSQL data model

Suggested table: `analyze_idempotency_requests`.

| Column | Type | Purpose |
|---|---|---|
| `id` | UUID primary key | Internal row identity |
| `user_id` | UUID, FK `users(id)` `ON DELETE CASCADE` | Ownership boundary |
| `operation` | varchar(64) | Fixed operation, initially `analyze:v1` |
| `idempotency_key_hash` | char(64) | Domain-separated SHA-256; raw key is never stored |
| `request_fingerprint` | char(64) | SHA-256 of canonical effective inputs |
| `fingerprint_version` | smallint | Canonicalization version, initially 1 |
| `status` | varchar(32) with check | `processing`, `completed`, `failed_retryable`, `failed_terminal`, or `indeterminate` |
| `request_id` | varchar(64) | Correlation ID of the winning attempt |
| `response_status` | smallint nullable | Stored terminal HTTP status |
| `response_body` | JSONB nullable | Bounded safe terminal response |
| `history_record_id` | integer nullable FK `application_records(id)` `ON DELETE SET NULL` | Optional History result reference |
| `provider_started_at` | timestamptz nullable | Durable ambiguity boundary |
| `lease_expires_at` | timestamptz nullable | Detect abandoned processing, not automatic provider retry |
| `attempt_count` | smallint | Safe pre-provider claim attempts |
| `safe_error_code` | varchar(80) nullable | Operational classification without private text |
| `created_at` | timestamptz | Creation time |
| `updated_at` | timestamptz | State transition time |
| `expires_at` | timestamptz | Replay retention boundary |
| `completed_at` | timestamptz nullable | Terminal time |

Constraints:

- Unique:
  `(user_id, operation, idempotency_key_hash)`.
- Status check for the five states above.
- Response body and status must both be present for a replayable terminal row.
- Enforce an application limit and a database check of at most 1 MiB of
  serialized response JSON.
- `provider_started_at` must be non-null for `indeterminate`.

The full safe response should be stored. A History reference alone is
insufficient because History is optional and does not contain every response
field required for byte-equivalent business replay. The response is already
bounded by the Analyze output contract and model token limit, but the 1 MiB
ceiling prevents accidental table abuse. Do not store raw Resume bytes,
Resume/JD input text, passwords, session or CSRF tokens, provider secrets, raw
idempotency keys, or prompts.

## 14. Idempotency key policy

- Header: `Idempotency-Key`.
- Length: 16-128 ASCII characters.
- Syntax:
  `^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$`.
- Case-sensitive; no trimming or normalization.
- The frontend should use `crypto.randomUUID()` for a new logical submission.
- Hash:
  `SHA-256("pja:idempotency-key:v1\\0" || UTF8(raw_key))`.
- Never log or return the raw key.
- The key is scoped by authenticated user and operation. It is not a bearer
  secret and cannot authorize a request.

The frontend should keep the key stable for automatic transport retries of the
same submission. A small pending record containing only the random key,
client-side fingerprint hash, and expiry may be kept in `sessionStorage` to
survive an ambiguous same-tab reload; it must not store Resume/JD content or
authentication material. Cross-tab semantic deduplication is not promised in
Phase A. Different keys represent different logical submissions even when
their bodies happen to match.

## 15. Request fingerprint algorithm

Compute the fingerprint after source ownership, parsing/acquisition, RAG
selection, and security validation, but before any primary or repair provider
call. Repeating local parsing, safe URL acquisition, or Project Knowledge
search is acceptable; the critical external provider and History effects are
behind the claim.

Canonical object, version 1:

```json
{
  "operation": "analyze:v1",
  "resume": {
    "source": "stored_version|upload",
    "version_id": "uuid-or-null",
    "effective_text_sha256": "hex",
    "upload_bytes_sha256": "hex-or-null",
    "normalized_filename_sha256": "hex-or-null"
  },
  "job": {
    "source": "text|url",
    "normalized_url_sha256": "hex-or-null",
    "effective_text_sha256": "hex"
  },
  "rag": {
    "mode": "off|project",
    "top_k": 5,
    "evidence": [
      {"document_id": 1, "chunk_id": 7, "content_sha256": "hex"}
    ]
  },
  "save_to_history": true,
  "analysis_behavior_version": "analyze-contract-v1",
  "security_policy_version": "current-version",
  "model": "configured-model-identifier"
}
```

Rules:

1. Apply Unicode NFC to strings.
2. Convert CRLF/CR to LF and trim only leading/trailing outer whitespace;
   preserve internal whitespace because it can affect prompts.
3. Use the already canonicalized safe Job URL. Lowercase scheme and host,
   remove a fragment and default port, and preserve path/query semantics.
4. Include a hash of the acquired JD text so changed URL content is not
   silently replayed under an old key.
5. For a stored Resume include the owner-validated immutable Version UUID and
   effective text hash.
6. For an upload include raw byte hash, effective parsed text hash, and a hash
   of the normalized basename because the filename is persisted to History.
7. Include effective RAG mode and clamped top-k.
8. For Project Knowledge include the ordered selected chunk IDs and hashes,
   not raw chunk content. This captures the evidence that affects the prompt.
9. Include `save_to_history`; a no-save request is not equivalent to a saved
   request.
10. Include a deliberately maintained analysis behavior version covering
    prompt, parser, fallback, scoring, and retrieval contract changes.
11. Serialize UTF-8 JSON with sorted keys, compact separators, explicit
    booleans/nulls, integer top-k, and no NaN/Infinity.
12. Hash:
    `SHA-256("pja:analyze-fingerprint:v1\\0" || canonical_json_bytes)`.

Do not include the authenticated user ID in the hash because it is already in
the uniqueness scope. Do not include timestamp, request ID, session token,
CSRF token, generated workflow ID, generated History ID, or other unstable
values.

A SHA-256 collision is not a practical operating concern. A stored
fingerprint mismatch for the same scoped key is always a 409; never replace
the old row. Increment `fingerprint_version` and the operation/behavior
version when canonicalization changes.

Only hashes and resolved IDs enter the idempotency record, limiting disclosure
if the table is inspected. Hashing does not anonymize low-entropy text, so raw
input hashes should not be exposed through API responses or ordinary logs.

## 16. State machine

```text
                  safe pre-provider retry
     +-----------------------------------------------+
     |                                               |
     v                                               |
 processing -- validation/local failure --> failed_retryable
     |
     | commit provider_started_at
     v
 processing (provider started)
     |                         |
     | safe result/error       | lease expires or process disappears
     v                         v
 completed / failed_terminal  indeterminate
```

State meanings:

- `processing`: one winner owns the logical attempt. A null
  `provider_started_at` means a retry can be proven safe after lease expiry.
- `completed`: terminal safe response is stored, commonly 200.
- `failed_retryable`: failure occurred before the provider boundary; the same
  fingerprint may claim another attempt.
- `failed_terminal`: a safe terminal error is stored and replayed; retrying
  the provider under the same key is not allowed.
- `indeterminate`: the provider may have accepted work, but no durable
  terminal response exists. Return an explicit conflict and require operator
  or user judgment rather than silently duplicating the call.

Permanent input/security errors should be discovered before the idempotency
claim whenever possible. Once provider work begins, mark
`provider_started_at` in its own committed transaction before the external
call.

## 17. Concurrency handling

Use PostgreSQL, not an in-process lock:

1. Attempt `INSERT ... ON CONFLICT DO NOTHING` for the scoped key in a short
   transaction and commit immediately.
2. The inserted row is the winner. Do not hold a row lock or request
   transaction during URL/RAG/provider work.
3. A loser reads the existing row after the unique conflict:
   - Different fingerprint: 409 `IDEMPOTENCY_KEY_REUSED`.
   - Completed or terminal failure: replay stored response.
   - Active lease: 409 `IDEMPOTENCY_REQUEST_IN_PROGRESS`.
   - Expired pre-provider lease: use `SELECT ... FOR UPDATE` or an atomic
     compare-and-swap update to transition to a new `processing` attempt.
   - Expired post-provider lease: transition to `indeterminate`; do not call
     DeepSeek again automatically.
4. Before the primary provider call, commit `provider_started_at` and a fresh
   lease.
5. After a safe result exists, use one final PostgreSQL transaction to insert
   the optional History row, construct its final workflow fields, store the
   idempotency response/status, link the History row, and transition terminal.
   The current History helper must be adapted to accept a caller-owned
   transaction or replaced by a small repository method.
6. Monitoring remains best effort after terminal finalization and must not
   invalidate the replayable response.

Race outcomes:

| Race | Required behavior |
|---|---|
| Same key arrives simultaneously | Unique constraint elects one winner across processes |
| Second arrives while first runs | 409 plus `Retry-After`; no provider or History effect |
| First completes before second reads | Second replays stored response |
| First fails before provider | Atomically allow same-fingerprint safe retry |
| First fails after provider but before History commit | Mark/detect `indeterminate`; no automatic provider retry |
| Client disconnects | Server finalization may continue; database state, not socket state, controls replay |
| Same key, different body | 409 without disclosing the prior body |
| Same textual key, different users | Independent rows; no cross-user read |
| Row expires during retry | Row lock and cleanup locking serialize the decision; return expired conflict |
| Two application processes | PostgreSQL uniqueness and row state are authoritative |

Advisory locks are not needed. A unique constraint, short row locks for state
transitions, and compare-and-swap updates are easier to test and explain.
Default `READ COMMITTED` isolation is sufficient when every transition checks
the locked/current status. No transaction should span a DeepSeek call.

### Exactly-once limitation

PostgreSQL cannot atomically commit with an external model provider. If the
process dies after DeepSeek accepts the request but before PostgreSQL stores
the result, the outcome is unknowable unless the provider itself offers a
durable idempotency contract. `indeterminate` provides at-most-one automatic
provider attempt for a scoped key; it intentionally trades automatic recovery
for protection from an unobserved duplicate. The portfolio case must state
this limitation rather than claim exactly-once execution.

## 18. HTTP status and header semantics

| Condition | Status | Headers | Body behavior |
|---|---:|---|---|
| First successful keyed request | 200 | `X-Request-ID`, `Idempotency-Replayed: false` | Normal Analyze response |
| Completed duplicate, same fingerprint | Stored status, normally 200 | Current `X-Request-ID`, `Idempotency-Replayed: true` | Stored business response |
| Duplicate while processing | 409 | `X-Request-ID`, `Retry-After: 2`, `Idempotency-Replayed: false` | `IDEMPOTENCY_REQUEST_IN_PROGRESS` |
| Same key, different fingerprint | 409 | `X-Request-ID` | `IDEMPOTENCY_KEY_REUSED` |
| Expired stored key | 409 | `X-Request-ID` | `IDEMPOTENCY_KEY_EXPIRED`; client must use a new key |
| Safe retryable pre-provider failure | Underlying eventual status | Standard keyed headers | Atomically reclaim same key |
| Stored terminal failure | Stored failure status | `Idempotency-Replayed: true` | Safe stored error semantics |
| Ambiguous post-provider failure | 409 | `X-Request-ID` | `IDEMPOTENCY_OUTCOME_UNKNOWN` |
| Malformed key | 400 | `X-Request-ID` | `IDEMPOTENCY_KEY_INVALID` |
| No key | Existing synchronous status | `X-Request-ID`; omit `Idempotency-Replayed` | Backward-compatible, not deduplicated |

Use 409 rather than 202 for an in-progress duplicate. The API has no async
status resource, and 202 would imply a job-oriented contract. The existing
Analyze endpoint remains synchronous and is not converted into Dramatiq work.

The response `X-Request-ID` belongs to the current HTTP attempt. The new row
retains the winner's original request ID for operator correlation. A replayed
success body should remain the same business response; it should not embed an
obsolete request ID. Error envelopes generated for the current attempt use
the current request ID.

## 19. Authentication, authorization, Origin, and CSRF interaction

All authentication and request-integrity checks occur before idempotency
lookup or replay:

- A valid idempotency key never bypasses session authentication.
- A replayed POST still requires the current trusted Origin/Referer and valid
  session-bound CSRF token.
- The unique scope and every lookup include the authenticated `user_id`.
- A History reference is returned only through the same owner-scoped result.
- Remember Me changes session lifetime, not idempotency ownership or expiry.
- Logout, session revocation, session expiry, password-driven revocation, or a
  disabled user causes 401 before any completed result can be replayed.
- A user who signs in with a new valid session may replay their own result
  while it is retained because ownership belongs to the user, not the browser
  session.
- An administrator receives no cross-user replay privilege through Analyze;
  the normal authenticated user scope remains in force.
- Two users may use the same textual key without collision or disclosure.

This preserves the controls implemented at
`backend/app/auth/middleware.py:71-96` and account validation at
`backend/app/auth/service.py:123-157`.

## 20. Retention and cleanup

Recommended initial policy:

- Replay retention: 24 hours from claim for completed and terminal-failed
  rows.
- Indeterminate retention: 7 days for diagnosis and to avoid automatic reuse
  during the ambiguity window.
- Maximum stored response: 1 MiB JSON.
- Cleanup batch: at most 500 terminal expired rows per transaction.
- Never delete an active `processing` row solely because its replay expiry
  passed. First resolve its lease state.

No new worker should be created only for cleanup. The repository already has
a bounded maintenance loop at `backend/app/agent_runs/worker.py:103-111`.
Phase A may call a small idempotency cleanup function from that loop if the
worker remains an active operational component, or expose the same bounded
function to the existing host maintenance schedule. Cleanup correctness must
use PostgreSQL row locking/`SKIP LOCKED`, not depend on only one process.

If cleanup is delayed, correctness is unchanged: expired rows return an
expired conflict while present, and storage grows. Once an expired row is
physically removed, the retention guarantee has ended and a reused textual
key can represent a new request. Clients should always generate a new key
after expiry.

Monitor:

- claims, completed replays, in-progress conflicts, fingerprint conflicts,
  safe retries, terminal failures, and indeterminate outcomes;
- provider calls per idempotency claim;
- History inserts per idempotency claim;
- row count and JSONB bytes;
- oldest expired row;
- cleanup rows and duration;
- processing rows with expired leases.

At 1,000 analyses per day and a hypothetical 100 KiB average stored response,
one day of response payload is roughly 100 MiB before PostgreSQL overhead.
Actual usage should be measured; the 1 MiB hard ceiling is a guard, not a
planning average.

## 21. Index strategy

Create only:

1. Unique B-tree
   `(user_id, operation, idempotency_key_hash)` for claim and lookup.
2. Partial B-tree on `expires_at` for terminal cleanup, for example:
   `WHERE status IN ('completed','failed_retryable','failed_terminal','indeterminate')`.

The unique index begins with `user_id`, so a separate foreign-key index on
`user_id` is redundant for this table's expected access path. Do not index
`request_fingerprint`, `request_id`, response status, or JSONB initially.
They are not on the critical lookup path. Add operational indexes only after
measured query evidence.

## 22. Test plan

All model behavior tests must use the Mock provider or injected fakes. The
real DeepSeek API must never be called.

### Request ID

- Generate UUIDv4 when absent.
- Preserve a valid client ID.
- Replace malformed and overlong client IDs.
- Cover early 400/401/403/413/503 security responses.
- Return the header for success, validation, authentication, CSRF, provider,
  persistence, and unknown errors.
- Include the current ID in the stable Analyze error body.
- Include the ID in route, service, provider, and completion logs.
- Expose the header through CORS.
- Prove logs and responses exclude cookies, CSRF, idempotency keys, provider
  secrets, Resume/JD content, and internal exception text.

### Error contract

- Multipart/request validation.
- Missing, malformed, oversized, and unowned Resume sources.
- Missing JD and unsafe Job URL.
- Authentication, disabled user, expired session, Origin, and CSRF.
- Provider timeout and invalid provider output still produce a 200 fallback
  when fallback succeeds.
- Output security rejection.
- Project Knowledge retrieval failure.
- History/idempotency transaction failure.
- Unknown internal exception.
- Frontend maps `error.code` without matching English strings and retains a
  legacy `detail` fallback for other endpoints.
- `details` is always an object and contains only allowlisted fields.

### Idempotency correctness

- First keyed request succeeds.
- Exact completed duplicate returns the same business payload and replay
  header.
- Duplicate invokes primary DeepSeek mock once.
- Duplicate invokes format-repair mock at most once for the winning request.
- Duplicate creates one History row.
- `save_to_history=false` still replays.
- Same key with different Resume, JD, URL content, RAG setting, top-k, or save
  flag returns 409.
- Same key and identical body for two users produces independent results.
- An unowned Resume Version is rejected before idempotency disclosure.
- Request without a key preserves current behavior.
- Malformed key is rejected without provider or History effects.
- Completed response larger than the configured cap fails safely.
- Pre-provider retryable failure can be reclaimed once.
- Terminal failure replays without a provider call.
- Expiry requires a new key.
- Cleanup deletes only terminal expired rows.
- History and idempotency finalization roll back together.
- Monitoring failure does not invalidate a completed replay.

### Concurrency and PostgreSQL integration

- Use PostgreSQL 16 and two independent SQLAlchemy sessions/process-level
  clients.
- Release simultaneous requests with a barrier; assert one provider fake
  call, one History row, one winner, and one in-progress or replay response.
- Verify `INSERT ... ON CONFLICT` winner behavior.
- Verify conflicting fingerprints cannot overwrite the row.
- Verify expired pre-provider lease compare-and-swap.
- Verify expired post-provider lease becomes `indeterminate`.
- Verify cleanup uses bounded locked batches and does not delete active rows.
- Verify migration upgrade from `20260721_05`, clean upgrade, downgrade, and
  data preservation.
- Verify unique and cleanup indexes exist with the intended definitions.

### Frontend

- Generate one UUID key per logical submission.
- Preserve it through the one CSRF refresh retry.
- Do not generate a second key for an in-component duplicate event.
- Map 409 in-progress/reused/expired/unknown codes distinctly.
- Honor `Retry-After` as guidance without automatic provider-triggering loops.
- Display the request ID for support without exposing secrets.
- Clear bounded pending-key state on terminal completion and logout.

Avoid microsecond timing assertions. Test plan shape, state, ownership,
effects, and call counts.

## 23. Expected implementation files

The smallest likely Phase A change set is:

- `backend/logging_utils.py` — outer request correlation behavior and fields.
- `backend/app/application.py` and/or
  `backend/legacy_application.py` — middleware ordering, CORS exposure, Analyze
  integration, and Analyze-specific exception envelope.
- `backend/app/auth/middleware.py` — stable Analyze security errors while
  retaining default-deny behavior.
- `backend/app/db/models.py` — idempotency ORM model.
- `backend/app/analyze/idempotency.py` — new focused claim, fingerprint,
  transition, replay, and cleanup service.
- `backend/database.py` — caller-owned History transaction support or a small
  replacement repository path.
- `backend/alembic/versions/20260724_06_add_analyze_idempotency.py` — one
  migration.
- `backend/test_logging_utils.py` — early-response correlation tests.
- `backend/test_v203_analysis_resilience.py` and a focused new Analyze
  idempotency test module — behavior and failure tests.
- `backend/test_v2_postgres_integration.py` or a dedicated PostgreSQL
  concurrency test — multi-session state and plan assertions.
- `backend/test_v2_database_migration.py` — migration head, upgrade, and
  downgrade coverage.
- `frontend/src/api/client.js` — stable error parsing and retry header
  preservation.
- `frontend/src/legacy-workspace.jsx` — key generation, stable error mapping,
  and support request ID.
- `frontend/src/api/client.test.js`,
  `frontend/src/pages/V201Pages.test.jsx`, and/or a focused Analyze test —
  frontend contract coverage.
- `.env.example` only if retention or lease durations are made configurable.
- API/architecture/project documentation and the implementation Work Report.

Do not modify Docker, Compose, authentication semantics, or deployment
infrastructure for Phase A.

## 24. Migration impact

One Alembic migration is required for the new table, constraints, foreign
keys, and two indexes. It does not rewrite existing History or user rows.
Creating an empty table and its indexes is low lock and storage risk.

Upgrade:

- Create `analyze_idempotency_requests`.
- Add the owner and optional History foreign keys.
- Add the status/response constraints.
- Add the unique lookup and partial expiry indexes.

Downgrade:

- Drop the partial index, unique constraint/index as appropriate, and table.
- Existing History data remains untouched.

The application must be backward compatible when the client sends no key.
Deploy the migration before code that requires the table. No concurrent index
creation is justified for a new empty table.

## 25. Risks

| Risk | Mitigation |
|---|---|
| Claim transaction held through provider call | Use a dedicated short session and commit before external work |
| Crash after provider starts | Durable provider boundary and `indeterminate`; never silently retry |
| History row and replay result diverge | Finalize both in one PostgreSQL transaction |
| Cross-user replay | Include authenticated user in unique scope and every lookup |
| Same key with changed input | Versioned fingerprint and 409 conflict |
| Sensitive response retention | 24-hour TTL, 1 MiB cap, no raw inputs/keys, existing DB access controls |
| Table growth when cleanup stops | Partial expiry index, bounded cleanup, oldest-expired metric |
| Error-contract frontend break | Analyze-only rollout and temporary legacy parser fallback |
| Request ID trusted as security input | Treat as untrusted observational text only |
| Duplicate semantic requests with different keys | Document that idempotency is key-based; keep UI duplicate guard |
| SDK-level provider retries | Measure and explicitly configure future retry policy; do not mislabel transport retries as separate user requests |
| CORS hides support headers | Expose only the two safe correlation headers |
| Reusing retired Agent infrastructure | Use a dedicated current-path table/service |

## 26. Rollback

Application rollback:

1. Stop sending `Idempotency-Key` from the frontend.
2. Restore the previous Analyze route path; requests without keys remain
   compatible throughout.
3. Restore legacy `detail` parsing if necessary.
4. Leave the new table in place during an emergency code rollback because it
   is inert and does not affect existing rows.
5. After confirming no running version depends on it, apply the Alembic
   downgrade to drop only the idempotency table and indexes.

Request-correlation rollback can restore the old middleware order without
changing auth state. The new error envelope should be rolled back together
with its frontend parser.

No History, Resume, user, or Project Knowledge data should be deleted by
rollback.

## 27. Recommended implementation scope

### Phase A: recommended portfolio case

Implement together:

1. Make existing UUIDv4 request correlation cover the full middleware stack.
2. Return and expose `X-Request-ID`.
3. Add the Analyze-only stable error envelope.
4. Add the PostgreSQL idempotency table and one migration.
5. Integrate key validation, versioned fingerprinting, atomic claim, explicit
   state transitions, replay, and bounded retention.
6. Make optional History insert and terminal idempotency finalization one
   transaction.
7. Generate and preserve an idempotency key in the Analyze frontend.
8. Add Mock-provider correctness, PostgreSQL concurrency, migration, security,
   and frontend tests.
9. Add evidence-based API and portfolio documentation.

This is a strong portfolio case because it combines HTTP contract design,
security boundaries, PostgreSQL concurrency, external-side-effect reasoning,
transaction design, frontend retry behavior, and honest failure semantics
without introducing an unnecessary distributed system.

### Phase B: defer

- Broader error-contract adoption across all endpoints.
- Idempotency for other POST routes.
- Redis read acceleration.
- General metrics dashboard changes.
- Distributed tracing.
- Async Analyze jobs.
- Cross-tab semantic submission coordination.

## 28. Rejected alternatives

- **Request ID as idempotency key:** rejected because correlation IDs may be
  duplicated and are not an authorization or uniqueness credential.
- **Redis-only idempotency:** rejected because it is not the durable source of
  truth.
- **Cache only completed results:** rejected because it does not serialize
  concurrent first requests.
- **Hold a row lock through DeepSeek:** rejected because it creates a long
  transaction and pool/lock pressure.
- **PostgreSQL advisory lock:** rejected because a unique row and state
  transitions are sufficient and easier to inspect.
- **In-process mutex:** rejected because multiple app processes and restarts
  bypass it.
- **History as the idempotency ledger:** rejected because save is optional and
  History is created after provider work.
- **Monitoring row as the ledger:** rejected because monitoring is best effort
  and not transactionally authoritative.
- **Agent Run reuse or Dramatiq conversion:** rejected because the workflow is
  retired for creation and Analyze must remain synchronous.
- **Automatic post-provider retry after a crash:** rejected because it can
  duplicate an accepted provider call.
- **Return 202 for in-progress duplicates:** rejected because there is no
  asynchronous status resource.
- **Redesign every API error immediately:** rejected as unnecessary scope and
  compatibility risk.
- **UUIDv7 or ULID migration:** rejected because UUIDv4 already satisfies the
  log-correlation need and is implemented/tested.
- **OpenTelemetry/Jaeger/service mesh:** rejected as disproportionate for this
  phase.
- **Store only a History reference:** rejected because no-save responses must
  replay and History is not a complete response representation.

## 29. Audit validation and safety confirmations

Read-only evidence commands included:

```text
git status --short --branch
git log --oneline --decorate -10
git rev-parse HEAD main origin/main
gh pr view 18 --json ...
gh run view 30075604538 --json ...
backend/.venv/bin/alembic heads
source inspection with rg, sed, and nl
isolated temporary-SQLite middleware-order probe
local inspection of the pinned OpenAI client signature
```

Validation results:

- Main merge commit CI: 10/10 jobs successful.
- Existing request-correlation and Analyze-resilience tests:
  34/34 passed with
  `python -m unittest -v test_logging_utils.py test_v203_analysis_resilience.py`
  against an isolated test database.
- Alembic head inspection: `20260721_05 (head)`.
- Worktree scope review: only this report and the Work Report index changed.
- `git diff --check`: passed.

The temporary middleware probe created its database only under a temporary
directory and removed it on exit. It did not use production configuration or
data.

Confirmed:

- Production was untouched.
- No production database, runtime, deployment host, or Project Knowledge
  source was accessed.
- DeepSeek was not called.
- No real Resume, JD, email, account, session, or Project Knowledge content
  was used.
- Runtime application code was not changed.
- Database models and Alembic migrations were not changed.
- Frontend behavior was not changed.
- Docker, Compose, authentication behavior, production configuration,
  release state, tags, and deployment infrastructure were not changed.
- The only audit-branch changes are documentation.
