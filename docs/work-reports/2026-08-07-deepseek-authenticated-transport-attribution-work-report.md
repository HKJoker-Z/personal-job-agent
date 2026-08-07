# DeepSeek Authenticated Transport Failure Attribution

Date: 2026-08-07

Decision: **NO-GO**

This report records diagnosis-first work on PR #57. It does not authorize a
merge, deployment, version release, image publication, or production change.

## 1. Repository

Repository: https://github.com/HKJoker-Z/personal-job-agent

Implementation branch: `fix/deepseek-dedicated-direct-client`

Pull request: https://github.com/HKJoker-Z/personal-job-agent/pull/57

PR #57 starting head: `615cd71bc1eb2b36204ff5fd30926db608478f15`.

## 2. Starting repository and production state

PR #56 was merged before this phase with a normal merge commit:
`2e154b689de8deacbadb759a151dc027df8b4efe`. Main was checked out and pulled
fast-forward-only at that commit before the PR #57 branch was used.

The production baseline remained:

- stable version: `v2.0.5`;
- Alembic current/head: `20260730_07`;
- JD normalization mode: `java`;
- Java policy: `jd-normalization-v1`;
- skill dictionary: `skills-v1`;
- Version 2.0.6: unreleased.

Production does not contain the dedicated direct-client implementation.

## 3. Previous NO-GO result

The preceding authenticated direct cohort contained exactly ten synthetic
executions: complete 3, repaired 0, partial 2, fallback 5. It accepted 5/10,
recorded 8 `transport_error` observations and one
`provider_attempt_deadline_exhausted` observation, used at most two Provider
calls per execution, and had no security or serialization defect. Its decision
was NO-GO.

The prior unauthenticated direct preflight was 20/20 with zero connect or read
timeouts. The apparent connect-timeout discrepancy therefore required tracing
the actual SDK/HTTPX cause chain.

## 4. Exact transport stack

The production call sequence is:

```text
legacy_application.call_deepseek_raw
  -> _build_provider_client
  -> build_deepseek_client
  -> OpenAI SyncAPIClient / chat.completions.create
  -> DeadlineHttpxClient.send
  -> httpx.Client / HTTPTransport
  -> httpcore connection, DNS/socket connect, TLS, HTTP protocol
  -> DeepSeek response headers and body stream
  -> DeadlineSyncByteStream bounded reads
  -> OpenAI response decoding and typed completion
  -> Provider adapter and acceptance/fallback pipeline
```

The application creates a new DeepSeek SDK/client pair for each Provider
attempt. The SDK has `max_retries=0`. The application closes the SDK client in
`finally`, then closes the associated `DeadlineHttpxClient`; both close paths
are idempotent. The SDK uses the non-streaming call path, while
`DeadlineHttpxClient` obtains the response with streaming enabled internally,
wraps the body stream, and fully reads it before returning the response to the
SDK.

`DeadlineHttpxClient` uses a bounded worker for header acquisition and a
bounded worker per response-body chunk. A timeout closes the response/client
transport and raises the custom attempt or phase deadline exception. Normal
completion consumes and closes the response stream before Provider cleanup.

## 5. Installed runtime versions

The installed versions, not assumptions from a candidate source file, were:

| Component | Version |
|---|---|
| Python | 3.12.3 |
| OpenAI-compatible SDK | `openai==2.44.0` |
| HTTPX | `httpx==0.28.1` |
| HTTPcore | `httpcore==1.0.9` |
| OpenSSL | 3.0.13, 30 Jan 2024 |

OpenAI 2.44.0 catches an HTTPX timeout and raises `APITimeoutError` from the
HTTPX cause. Other exceptions are wrapped as `APIConnectionError` from the
original cause. The wrapper alone does not identify a connection, TLS, write,
read, pool, or protocol phase.

HTTPcore 1.0.9 passes the connect timeout to socket connection setup and TLS
`wrap_socket`/`start_tls`; pool acquisition uses the separate pool timeout.

## 6. Expanded bounded exception categories

The bounded classifier now distinguishes, when the installed libraries expose
the phase:

- `connect_error`, `connect_timeout`;
- `read_error`, `read_timeout`;
- `write_error`, `write_timeout`;
- `pool_timeout`;
- `remote_protocol_error`, `local_protocol_error`;
- `proxy_error`;
- `tls_or_connect_error` when an `ssl.SSLError` remains observable;
- `provider_attempt_deadline_exhausted`;
- `provider_phase_deadline_exhausted`;
- `transient_http_429`, `transient_http_5xx`;
- compatibility `transport_error` for old stored observations;
- `transport_error_other` for bounded generic network/protocol failures;
- `unknown_bounded_provider_error` when no concrete boundary is observable.

Classification walks only a bounded cause/context chain and explicit status
fields. It never reads raw exception text. Allowlisted exception class names
may be retained in the manual attribution artifact; arbitrary classes map to
stable categories and raw values are discarded. No body, prompt, Resume, JD,
reasoning, URL credential, header, API key, proxy value, or response content is
persisted.

The retry policy remains bounded. The new concrete transport categories retain
the existing one application-level retry eligibility; phase exhaustion remains
non-retryable when the shared phase has no safe budget.

## 7. Deterministic classification tests

`backend/test_provider_error_classification.py` and
`backend/test_deepseek_transport_attribution.py` cover:

- HTTPX and HTTPcore connect/read/write errors and component timeouts;
- remote and local protocol errors;
- proxy errors and generic bounded transport errors;
- OpenAI `APITimeoutError` and `APIConnectionError` cause preservation;
- 429/5xx status mapping;
- TLS cause mapping and the installed plaintext-peer TLS behavior;
- remote close before headers, incomplete headers, truncated body, malformed
  HTTP, and response-read closure using a local socket server;
- MockTransport request-write/read/reset equivalents;
- pool exhaustion and generic DNS/connect boundaries;
- read/write stall categories through deterministic exception seams;
- attempt versus phase deadline exceptions;
- response close during an active read;
- normal response consumption before client cleanup;
- arbitrary exception text exclusion.

The latest focused attribution/deadline/client/acceptance run passed 60 tests.
No test calls DeepSeek unless a manual candidate opt-in is explicitly set.

## 8. DeadlineHttpxClient lifecycle and race findings

The normal-success race test proves that the underlying response body is
consumed before the client cleanup path. The active-response test closes the
response from another thread using event synchronization and completes without
an injected sleep race. The attempt-deadline test proves that a blocked stream
is closed and classified as `provider_attempt_deadline_exhausted`.

Retry construction creates a fresh client pair; it does not reuse a closed
transport. Normal SDK and HTTPX close calls are idempotent. No deterministic
test reproduced a successful remote response being converted into a transport
error by cleanup, and no DeadlineHttpxClient correction was justified by the
authenticated matrix.

Daemon workers remain part of the hard-deadline design. They are bounded by
event waits and transport/stream closure; a late worker cannot change the
returned result because the main operation raises the bounded deadline
exception after cancellation.

## 9. Actual timeout configuration

The configured request timeout was `REQUEST_TIMEOUT_SECONDS=60`. The
authoritative Provider phase deadline remained 130 seconds. With the existing
30-second fallback/finalization reserve, the initial effective attempt budget
was 60 seconds and the effective connect timeout was:

```text
min(5.0 seconds, remaining effective attempt budget)
```

The effective connect timeout minimum and maximum in the direct attribution
matrix were both **5.0 seconds**. DNS/socket connection setup and TLS
handshake are within HTTPcore's connect-bound operation. Pool wait is separate
and remained 5.0 seconds. The five-second connect timeout was not increased.

## 10. Preserved deadlines and call limits

The implementation and tests preserve:

- Provider-phase deadline: 130 seconds;
- Analyze safety deadline: 175 seconds;
- external client safety assumption: 180 seconds;
- fallback/finalization reserve: 30 seconds;
- SDK automatic retries: zero;
- application retries: at most one;
- format-only repair: at most one;
- maximum Provider calls: three;
- primary output tokens: 1600;
- length retry tokens: 2400;
- repair tokens: 1000;
- configured maximum: 5000.

No schema tolerance, acceptance behavior, evidence reconciliation, scoring,
security scanning, deterministic fallback, Job Summary, Match Reasons,
idempotency, or History behavior was relaxed.

## 11. Four-level authenticated attribution matrix

The request was a tiny synthetic JSON request using the configured model,
`response_format=json_object`, thinking disabled, a 32-token bound, and a
minimal prompt. Each level ran exactly ten sequential requests. Each request
created and closed its level-appropriate client boundary. Proxy bypass was
explicit for Level A and `trust_env=False` for Levels B-D.

Two preliminary harness validations were discarded before attribution: the
first sent the SDK `extra_body` keyword literally at raw/HTTPX levels; the
second omitted the Authorization header at Level B. Neither was used as
evidence, and no individual failed request was rerun. The following is the
replacement matrix with identical wire semantics and the required ten
requests per level.

| Level | Boundary | HTTP success | expected JSON completion | failures | failure categories | median / p95 / max ms |
|---|---|---:|---:|---:|---|---:|
| A | raw authenticated HTTPS/curl, direct | 9/10 | 9/10 | 1 | `bounded_curl_timeout: 1` | 1534.187 / 5009.811 / 5009.811 |
| B | plain `httpx.Client(trust_env=False)` | 10/10 | 10/10 | 0 | none | 1593.376 / 1690.740 / 1690.740 |
| C | OpenAI SDK + plain HTTPX | 10/10 | 10/10 | 0 | none | 1571.642 / 1977.750 / 1977.750 |
| D | OpenAI SDK + production `DeadlineHttpxClient` | 9/10 | 9/10 | 1 | `connect_timeout: 1` | 1651.677 / 5033.034 / 5033.034 |

All four levels used direct transport. Level A had 9 two-hundred-class
responses and one bounded curl timeout. Level D's one failure had the safe
allowlisted chain `APITimeoutError -> ConnectTimeout`; it was a genuine
five-second connect boundary, not an attempt or phase deadline.

Level B and Level C were materially stable. The one raw HTTPS timeout and the
one Level D connect timeout show intermittent upstream/direct availability,
but the C-to-D comparison did not show a systematic DeadlineHttpxClient
reliability drop.

## 12. Realistic-payload control

The matrix showed a stable tiny C boundary and a remaining C-to-D question, so
the permitted control was run exactly five times at C and exactly five times
at D. It used the first existing synthetic Resume/JD fixture, the current
safe production prompt builder, the configured model, thinking disabled, JSON
output, and 1600 primary output tokens. No request or response content was
stored.

| Level | HTTP success | expected JSON completion | failures | exact bounded categories | median / p95 / max ms |
|---|---:|---:|---:|---|---:|
| C SDK + plain HTTPX | 2/5 | 0/5 | 5 | `remote_protocol_error: 3`; successful HTTP responses with `completion_shape_invalid: 2` | 3374.554 / 5108.042 / 5108.042 |
| D SDK + DeadlineHttpxClient | 1/5 | 0/5 | 5 | `remote_protocol_error: 4`; successful HTTP response with `completion_shape_invalid: 1` | 3030.612 / 4812.428 / 4812.428 |

The successful HTTP responses in this control were not counted as valid
completions because their model content was not the expected tiny `{"ok":true}`
shape. The transport failures were `RemoteProtocolError` wrapped by the SDK
as `APIConnectionError`. C and D showed the same failure boundary; D was not
materially worse. Tiny requests were reliable while the realistic response
was repeatedly interrupted or unusable after larger prompt/response work.

## 13. Confirmed root cause

Root cause classification: **E — payload/duration-dependent upstream failure**.

The narrowest reliable boundary is not the DeadlineHttpxClient. Raw HTTPS,
plain HTTPX, and SDK+plain HTTPX all established successful tiny-request
behavior, while the realistic synthetic payload failed at both C and D with
`remote_protocol_error` or unusable successful content. The remote peer/HTTP
response behavior becomes unreliable for the larger generation. The raw
one-request timeout is a contributing direct/upstream availability signal,
but the decisive differentiator is the realistic payload control.

This is not labeled generic “DeepSeek instability” without evidence: Level A
did reproduce one raw authenticated timeout, and Levels C/D independently
exposed the concrete remote protocol boundary for realistic work.

## 14. Correction performed

The production correction was limited to bounded observability:

- concrete HTTPX/HTTPcore/TLS category mapping was added;
- compatibility `transport_error` remains accepted for old observations;
- new categories are safely admitted to internal Provider metadata and retry
  reason filtering;
- deterministic tests and a manual-only metadata attribution runner were
  added.

No DeadlineHttpxClient, HTTPX timeout, OpenAI request semantic, retry count,
call maximum, or application acceptance correction was made. A speculative
transport change would not address a failure reproduced at the SDK+plain HTTPX
boundary.

Because no application transport fix was performed, a post-fix four-level
matrix was not applicable. The replacement matrix above is the final matrix
after the bounded classifier correction and harness validation.

## 15. Fresh full candidate

The matrix identified root cause E, Level D tiny success was 9/10, and no
deadline/security regression was present, so exactly one fresh ten-case
synthetic candidate was run using the existing candidate runner. No failures
were individually rerun.

| Result | Count |
|---|---:|
| complete | 2 |
| repaired | 0 |
| partial | 5 |
| fallback | 3 |
| accepted complete + repaired + partial | 7/10 |

Provider attempts used 7 application retries and 0 format repairs. The exact
Provider failure category was `remote_protocol_error: 7`; the exact fallback
category was `provider_call_failed: 3`. Component timeout categories were
empty. Maximum Provider calls were 2, below the limit of 3.

Provider latency was median **6318.020 ms**, p95 **8854.542 ms**, maximum
**8854.542 ms**. End-to-end Analyze latency was median **6322.768 ms**, p95
**8878.252 ms**, maximum **8878.252 ms**. Maximum active Provider operation
lifetime was **5573.022 ms**. No operation survived its deadline.

Token aggregates were input total **5723** (maximum 832), output total
**2352** (maximum 392), and total **8075** (maximum 1222). The runner used
1600 primary, 2400 length-retry, 1000 repair, and 5000 configured bounds.

Job Summary was present and valid in **10/10**. Match Reasons was present and
valid in **10/10**. Security rejection was **0**; public-contract/
serialization failure was **0**; safe-log inspection passed. The isolated
runner marks History and idempotency as not applicable; repository regression
tests below cover those contracts.

## 16. Acceptance decision

Decision: **NO-GO**.

The implementation and attribution gates passed, but the full candidate gate
did not:

- accepted results: 7/10, required at least 8;
- fallback: 3/10, allowed at most 2.

The branch must remain open and must not be merged automatically.

## 17. Backend validation

- focused attribution, Provider error, client, deadline, acceptance tests:
  60 passed;
- complete Backend discovery in a sanitized test process: **580 tests passed,
  12 repository-declared skips**;
- the first unsanitized discovery was not authoritative because the ambient
  shell SOCKS `ALL_PROXY` caused five environment-proxy construction errors and
  one dependent call-cap failure before mocks. The sanitized rerun passed;
- idempotency, History, completed replay, zero-Provider-call replay,
  deterministic fallback, and Java-authoritative path regressions remained
  green within the complete suite.

## 18. PostgreSQL validation

An isolated PostgreSQL 16.9 container was used; existing application
containers were not used as a test database. The PostgreSQL integration suite
ran **12 tests, 0 failures, 0 errors, 0 skips**. It migrated to and validated
Alembic head `20260730_07`.

## 19. Frontend validation

- Vitest: 9 files, 70 tests passed;
- production build: passed with Vite 8.1.3.

## 20. Java regression validation

Java source and policy were not changed. Maven `verify` passed with 46 tests,
0 failures, 0 errors, and 0 skips, including the 9-test normalization-only
profile integration run. The normalization-only container smoke and the full
isolated Java container smoke both passed.

## 21. Compose, image, safety, and dependency validation

- Java and Backend Compose configuration validation: passed;
- Python `pip check`: no broken requirements;
- repository safety and secret scan with repository test-fixture exclusions:
  passed;
- shell syntax and available ShellCheck validation: passed;
- tracked-output check: no disallowed tracked output;
- `git diff --check`: passed.

The isolated Version 2.0.5 mock candidate-image smoke reached the Backend image
build but failed twice at the frontend Docker `npm ci` step with external
registry/proxy `ECONNRESET`. It did not call DeepSeek, did not touch production,
and left no smoke containers running. Host frontend tests/build passed. This
external image-build prerequisite remains a validation risk for final GitHub
checks.

## 22. Changed files

- `backend/analysis_contract.py` — bounded category/retry metadata allowlist;
- `backend/provider_errors.py` — exact cause-chain classification;
- `backend/test_provider_error_classification.py` — SDK/HTTPX/TLS category
  tests;
- `backend/candidates/deepseek_transport_attribution.py` — manual-only,
  metadata-only four-level runner and realistic control;
- `backend/test_deepseek_transport_attribution.py` — local transport and
  lifecycle tests;
- `ops/candidate/deepseek-provider/run-transport-attribution.sh` — explicit
  manual opt-in wrapper;
- this report and `docs/work-reports/README.md`.

`.env.example`, the DeepSeek network-mode configuration, and the production
Compose ownership were already updated by PR #57 and were not changed by this
diagnostic phase. No arbitrary proxy URL or secret was added.

## 23. Commits and PR

PR #56 merge commit: `2e154b689de8deacbadb759a151dc027df8b4efe`.

PR #57 starting head: `615cd71bc1eb2b36204ff5fd30926db608478f15`.

Diagnostic implementation commit: `a4b8d65` (`test: attribute DeepSeek
authenticated transport failures`). The report/index commit and final PR head
are recorded in the final PR metadata after this report is committed.

PR URL: https://github.com/HKJoker-Z/personal-job-agent/pull/57

## 24. Exact next prerequisite

Do not merge PR #57. The next prerequisite is an externally authorized
DeepSeek payload/duration response-stability investigation, followed by a
fresh bounded candidate only after realistic synthetic requests remain stable
at the SDK+plain HTTPX boundary. If that provider condition cannot be made
stable, keep `environment_proxy` as the configuration rollback/compatibility
path and do not promote direct mode.

## 25. Rollback plan

Set `DEEPSEEK_NETWORK_MODE=environment_proxy` in the later candidate or
deployment configuration. That mode preserves approved HTTPX environment
proxy behavior, including the repository’s existing handling of unsupported
SOCKS `ALL_PROXY`. Direct mode remains client-scoped and does not mutate the
Backend process environment.

## 26. Risks and negative effects

- realistic payloads can still encounter upstream remote protocol closure;
- the new bounded categories change internal observability from a broad bucket
  to more accurate categories, while preserving public response compatibility;
- a concrete protocol failure remains retryable once, but retries were not
  increased to hide the failure;
- direct mode still needs a successful accepted full candidate before merge;
- Docker image smoke evidence is sensitive to external npm registry/proxy
  availability.

## 27. Scope and release confirmations

- production was untouched; no production Compose project was deployed or
  restarted;
- Java source, Java policy, and Alembic migrations were unchanged;
- no production or user content was inspected; all authenticated requests
  used the approved secret mechanism and synthetic fixtures only;
- no version bump occurred;
- no deployment occurred;
- no release image was published;
- no Git tag was created;
- no GitHub Release was created;
- no CI job calls DeepSeek; real calls exist only behind explicit manual
  candidate/attribution opt-ins;
- PR #57 remains open and must not be merged automatically.
