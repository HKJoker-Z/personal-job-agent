# Analyze Request Correlation and Error Contract Work Report

Date: 2026-07-24

Repository: `https://github.com/HKJoker-Z/personal-job-agent`

Application version: `2.0.3`

Schema head: `20260721_05`

## Executive result

Phase A1 gives every HTTP outcome one correlation ID across request state,
the request `ContextVar`, structured logs, and `X-Request-ID`, including
responses produced before authentication or route execution. It also gives
`POST /api/analyze` a focused four-field error contract and updates the
frontend to map stable codes, preserve the one-time CSRF refresh retry, show a
safe support reference, and retain legacy `detail` parsing for endpoints that
have not migrated.

The implementation does not add Analyze idempotency, an `Idempotency-Key`,
request fingerprinting, a database model, an Alembic migration, Redis
behavior, distributed tracing, or asynchronous Analyze execution. Existing
successful and deterministic fallback behavior remains unchanged.

## 1. Repository and starting commit

- Repository: `HKJoker-Z/personal-job-agent`
- Starting `main` commit:
  `364d579ef4d0e60507efe332cd36efabeb4c19ee`
- Application version: `2.0.3`
- Alembic head: `20260721_05`
- Starting state: clean local `main`, equal to `origin/main`

## 2. PR #19 merge commit

The documentation-only audit PR was verified before merge:

- PR: `https://github.com/HKJoker-Z/personal-job-agent/pull/19`
- Verified head:
  `8d9b8840108a0be0d1a01cd659fdcdf7b4ef316a`
- Merge state: `CLEAN` and `MERGEABLE`
- Required checks: all ten successful
- Runtime application files changed by PR #19: none
- Merge method: merge commit, without squash, rebase, or admin bypass
- Merge commit:
  `364d579ef4d0e60507efe332cd36efabeb4c19ee`
- Merge parents:
  `8d1cb3a837ba4242a8ed0f82d5ab2113a47d2466` and
  `8d9b8840108a0be0d1a01cd659fdcdf7b4ef316a`

After the merge, local `main` was updated with `git pull --ff-only origin
main`. Local `main`, `origin/main`, and `HEAD` matched. Main CI run
`30079490009` completed all ten jobs successfully.

## 3. Implementation branch

- Branch: `feat/analyze-request-correlation-error-contract`
- Branch point:
  `364d579ef4d0e60507efe332cd36efabeb4c19ee`
- Scope: Phase A1 request correlation, focused Analyze error contract,
  frontend error handling, tests, and documentation

## 4. Previous middleware order

Starlette wraps middleware in reverse addition order. Before Phase A1, the
effective relevant order was:

```text
V2SecurityMiddleware
  -> FeatureRetirementMiddleware
    -> RequestLoggingMiddleware
      -> TrustedHostMiddleware (production)
        -> CORSMiddleware
          -> route/exception handlers
```

Because `V2SecurityMiddleware` was outside request logging, its body-size,
authentication, Origin, CSRF, administrator-role, and SQLAlchemy error
responses could bypass request-ID creation, `X-Request-ID`, and the structured
completion log.

## 5. New middleware order

Application composition removes the legacy inner request-logging middleware
registration and adds one request logger last:

```text
RequestLoggingMiddleware
  -> V2SecurityMiddleware
    -> FeatureRetirementMiddleware
      -> TrustedHostMiddleware (production)
        -> CORSMiddleware
          -> route/exception handlers
```

An automated composition test verifies the first three classes in this order
and verifies exactly one `RequestLoggingMiddleware` registration.

## 6. Security behavior verification

The middleware-order change does not alter the default-deny gates:

- the same server-side Session authentication runs;
- missing, expired, revoked, and disabled-user sessions still return `401`;
- unsafe methods still require a trusted Origin or Referer origin;
- the Session-bound CSRF token is still mandatory;
- request body-size enforcement remains before authentication;
- administrator-only destructive operations still enforce the role;
- request-scoped SQLAlchemy commit/rollback behavior remains in the security
  middleware;
- request IDs remain observational and cannot satisfy any security check.

Focused tests cover missing authentication, disabled users, expired Sessions,
revoked Sessions, untrusted Origin, CSRF failure, body-size rejection,
administrator-role rejection, database failure, and unknown exceptions.

## 7. Request ID syntax and generation

The existing contract is preserved exactly:

```text
^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$
```

- A valid client value is preserved byte-for-byte.
- Values are not trimmed, lowercased, or otherwise normalized.
- Missing, malformed, or overlong values are replaced with a UUIDv4.
- The identifier is not used for authentication, authorization, ownership,
  uniqueness, or idempotency.

## 8. Response-header coverage

`X-Request-ID` is returned on:

- Analyze success;
- deterministic fallback success;
- request validation and Resume/JD source errors;
- `401` authentication failures;
- `403` Origin and CSRF failures;
- `413` body-size failures;
- `503` database/persistence failures;
- unknown `500` failures;
- unchanged legacy errors on endpoints outside Analyze.

The value in an Analyze error body is tested to equal the response header.

## 9. Structured-log coverage

The same request ID is available through:

- `request.state.request_id`;
- `request_id_context`, a `ContextVar`;
- structured application logs produced inside the request;
- the final `http_request_completed` event;
- the response header;
- the Analyze error envelope.

Completion logs retain method, route, status, duration, safe workflow ID,
error code, and error stage. The unknown-exception path logs the exception
type, not its text. Tests verify that request bodies, query tokens, custom
private headers, cookies, CSRF values, database exception text, Resume/JD
content, and provider fragments are absent from logs and error bodies.

## 10. CORS exposure

The existing CORS configuration now exposes only:

```text
Content-Disposition, X-Request-ID
```

`Idempotency-Replayed` and arbitrary additional response headers are not
exposed. A focused test verifies the actual Analyze response header.

## 11. Previous Analyze error formats

Before Phase A1, callers had to interpret multiple forms:

- security middleware: `{"detail": "..."}`;
- validation: `{"detail": "Invalid request..."}`;
- HTTP exceptions: string or object-valued `detail`;
- Analyze workflow errors: nested `detail.message`, `detail.error_code`,
  workflow, and security metadata;
- unknown exceptions: generic string `detail`.

The frontend detected CSRF failure by searching English text and Analyze used a
separate legacy `detail` parser.

## 12. New Analyze error envelope

Only `POST /api/analyze` and security or validation responses for that route
use:

```json
{
  "error": {
    "code": "REQUEST_VALIDATION_FAILED",
    "message": "The request could not be processed.",
    "request_id": "uuid-or-valid-client-id",
    "details": {}
  }
}
```

`code`, `message`, `request_id`, and `details` are mandatory. `details` is
always an object. Unknown or non-public internal codes are converted to
`UNEXPECTED_SERVER_ERROR` with a generic message. Other endpoints retain
their previous response shape.

## 13. Implemented error codes

The public Analyze allowlist is:

1. `AUTHENTICATION_REQUIRED`
2. `REQUEST_ORIGIN_NOT_TRUSTED`
3. `CSRF_VALIDATION_FAILED`
4. `REQUEST_TOO_LARGE`
5. `REQUEST_VALIDATION_FAILED`
6. `RESUME_SOURCE_INVALID`
7. `RESUME_NOT_FOUND`
8. `RESUME_PARSING_FAILED`
9. `JOB_SOURCE_INVALID`
10. `JOB_DESCRIPTION_ACQUISITION_FAILED`
11. `INPUT_SECURITY_BLOCKED`
12. `PROJECT_KNOWLEDGE_RETRIEVAL_FAILED`
13. `OUTPUT_SECURITY_BLOCKED`
14. `ANALYZE_PERSISTENCE_FAILED`
15. `UNEXPECTED_SERVER_ERROR`

No `IDEMPOTENCY_*` code is implemented.

## 14. Safe details policy

The backend copies only bounded, explicitly allowlisted values. Supported
categories include a validated field name, bounded reason, already-authorized
workflow ID, safe error stage, retryability, normalized security status and
findings, bounded workflow step summaries, safe completion metadata, and RAG
counts.

The contract excludes stack traces, Python exception text, SQL, filesystem
paths, production paths, internal IP addresses, unauthorized raw database
identifiers, Resume/JD text, prompts, provider bodies, cookies, CSRF values,
tokens, and secrets.

The frontend applies another display boundary to blocked-security metadata:
labels must match a small safe character set, counts are bounded, raw finding
messages are replaced with a fixed message, and error workflow messages are
not rendered.

## 15. Frontend error mapping

The shared API client now prefers `error.code`, `error.message`,
`error.request_id`, and object-valued `error.details`. Analyze maps the stable
codes to fixed user-facing messages and shows the request ID only as a support
reference for a terminal error.

The Analyze submit guard and `finally` cleanup remain, so the button recovers
after failures. No new authentication or security value is stored in browser
storage.

## 16. Legacy compatibility

- The shared client still parses string and object-valued `detail`.
- Endpoints outside Analyze retain their prior response shapes.
- The one-time Session refresh and CSRF resend remains.
- CSRF recognition now prefers `CSRF_VALIDATION_FAILED`, with the old English
  `detail` check temporarily retained for unmigrated endpoints.
- Successful Analyze response fields and status codes are unchanged.

## 17. Fallback behavior verification

Phase A1 does not turn recoverable provider behavior into HTTP failures.
Mock-based tests verify that:

- a provider timeout returns HTTP `200`;
- a simulated provider 5xx returns HTTP `200`;
- malformed provider JSON plus failed repair returns HTTP `200`;
- each successful recovery has `analysis_status="fallback"`;
- fallback results remain renderable in the frontend.

Scoring, RAG, parsing, repair, deterministic fallback, History business
behavior, provider prompts, and provider SDK construction were not changed.

## 18. Targeted tests

Backend targeted command:

```bash
APP_ENV=test APP_DATABASE_PATH=/dev/shm/pja-phase-a1-targeted.db \
  .venv/bin/python -m unittest -v \
  test_logging_utils.py \
  test_analyze_request_correlation.py \
  test_v203_analysis_resilience.py
```

Result: all focused request-correlation and Analyze-resilience tests passed.
The final combined run passed 54 of 54 tests. An additional focused
CORS/composition run passed 11 of 11 tests while the CORS assertion was being
isolated.

Frontend targeted command:

```bash
npm test -- --run src/api/client.test.js src/pages/V201Pages.test.jsx
```

Result: 2 files and 22 tests passed.

## 19. Full backend tests

Command:

```bash
APP_ENV=test APP_DATABASE_PATH=/dev/shm/pja-phase-a1-full-final.db \
  .venv/bin/python -m unittest discover -v
```

Result: 413 tests passed in 179.523 seconds; the 9 opt-in PostgreSQL tests were
skipped here and then run separately against PostgreSQL 16.

## 20. PostgreSQL integration tests

An isolated PostgreSQL 16 container and a database whose name contains `test`
are used. No running project or production PostgreSQL service is addressed.

Command:

```bash
APP_ENV=test PJA_RUN_POSTGRES_TESTS=1 \
TEST_DATABASE_URL=postgresql+psycopg://<test-only-user>@127.0.0.1:55433/pja_phase_a1_test \
DATABASE_URL=postgresql+psycopg://<test-only-user>@127.0.0.1:55433/pja_phase_a1_test \
  .venv/bin/python -m unittest -v test_v2_postgres_integration.py
```

Result: 9 tests passed in 23.447 seconds. The suite covered clean Alembic
upgrades, upgrade/downgrade paths, schema constraints, PostgreSQL compatibility
paths, the primary-Resume migration, and the monitoring aggregate plan. The
container used the CI-pinned PostgreSQL 16.9 image digest, bound only to
`127.0.0.1:55433`, and was removed after the run.

No schema or migration change is part of this task.

## 21. Frontend tests and build

Commands:

```bash
npm test -- --run
npm run build
```

Results:

- 9 test files passed;
- 62 frontend tests passed;
- Vite production build passed;
- 38 modules transformed;
- output bundle generation completed successfully.

## 22. Docker/Compose checks

Local results:

- backend image build passed after one transient registry metadata timeout was
  retried;
- frontend image build passed;
- `scripts/verify-images.sh` passed user and sensitive-path checks;
- root Compose configuration validation passed with a test-only environment
  and `/dev/null` as the service env file;
- `scripts/test-v201-production-runtime.sh` passed;
- the Version 2.0.3 isolated Mock LLM Docker smoke passed, including fresh
  Alembic upgrade, health, Session/CSRF, Resume, Analyze, RAG, History,
  persistence restart, backup, and restore checks;
- Bash syntax and ShellCheck passed for repository deployment scripts.

All local Docker work is isolated and does not operate on the running
production-like project stack.

## 23. Changed files

Runtime and contract:

- `backend/app/api/errors.py`
- `backend/app/application.py`
- `backend/app/auth/middleware.py`
- `backend/legacy_application.py`
- `backend/logging_utils.py`
- `frontend/src/api/client.js`
- `frontend/src/legacy-workspace.jsx`

Tests:

- `backend/test_analyze_request_correlation.py`
- `backend/test_v203_analysis_resilience.py`
- `frontend/src/api/client.test.js`
- `frontend/src/pages/V201Pages.test.jsx`

Documentation:

- `docs/V2_0_3_API.md`
- `docs/PROJECT_KNOWLEDGE.md`
- `docs/work-reports/README.md`
- this Work Report

No SQLAlchemy model, Alembic migration, Docker/Compose, production
configuration, Worker, Outbox, Redis, Resume storage, or History schema file
was changed.

## 24. Commit SHAs

- Runtime, tests, and verified documentation:
  `948e25dc44d9992d1820a331f59aaca1a4801dd0`
- Work Report and delivery metadata: the commit containing this report

The implementation and report are separate logical commits on the same pull
request branch.

## 25. PR number and URL

- PR: `#20`
- URL:
  `https://github.com/HKJoker-Z/personal-job-agent/pull/20`
- Title:
  `HTTP: Add full Analyze request correlation and stable error contracts`
- State at report preparation: open and not merged

## 26. CI results

The merged audit commit passed all ten main CI jobs before the implementation
branch was created.

Implementation PR run:
`https://github.com/HKJoker-Z/personal-job-agent/actions/runs/30090170209`

The run on implementation commit
`948e25dc44d9992d1820a331f59aaca1a4801dd0` passed all ten jobs:

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

The subsequent Work Report commit is documentation-only and is also required
to pass the pull-request checks before handoff.

## 27. Risks

1. Middleware ordering is security-sensitive. Composition and early-response
   integration tests reduce the risk of losing default-deny behavior.
2. The stable envelope is deliberately narrow. A caller must still support
   legacy `detail` outside Analyze until later migrations are approved.
3. Request IDs supplied by clients are not globally unique. They are
   observational only and cannot support correctness guarantees.
4. Safe details can become an accidental disclosure boundary if future code
   bypasses the helper. The public code allowlist and detail sanitization
   should remain centralized.
5. The synchronous provider client can perform SDK transport retries. Phase A1
   does not make at-most-one provider-attempt claims.

## 28. Rollback

Rollback requires reverting the Phase A1 commits. There is no migration,
database data transformation, cache invalidation, or infrastructure rollback.
The previous middleware order, legacy Analyze errors, and frontend parser
would be restored together.

## 29. Phase A2 deferred work

Phase A2 must separately define and implement:

- authenticated-user-scoped PostgreSQL idempotency;
- an `Idempotency-Key` contract;
- canonical Analyze request fingerprinting;
- concurrency and replay state transitions;
- atomic History/result handling;
- retention and cleanup;
- multi-process concurrency tests;
- the provider SDK retry policy.

The current OpenAI-compatible provider client leaves `max_retries=2`
unchanged. Phase A2 must decide whether and how to change that setting before
claiming at-most-one automatic provider attempt.

## 30. Idempotency is not implemented

This change does not read or emit `Idempotency-Key`, store an idempotency row,
compute a request fingerprint, cache a response, prevent duplicate Analyze
requests across tabs/processes, or return `Idempotency-Replayed`.

## 31. Provider SDK retries remain unchanged

The provider SDK configuration still uses its existing `max_retries=2`
behavior. No provider retry, timeout, prompt, scoring, parsing, repair, RAG, or
fallback configuration was modified.

## 32. Production confirmation

Production was not accessed, benchmarked, modified, released, tagged, or
deployed. Production data, configuration, and infrastructure were untouched.
Production Project Knowledge was not synchronized.

## 33. DeepSeek confirmation

DeepSeek was not called. Provider tests used mocks or deterministic local
fallback paths only.
