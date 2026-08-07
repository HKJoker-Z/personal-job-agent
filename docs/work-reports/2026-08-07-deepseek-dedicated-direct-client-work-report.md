# DeepSeek Dedicated Direct Client Work Report

Date: 2026-08-07

Decision: **NO-GO** for a later production candidate from this evidence. The
client-scoped direct architecture, deadline preservation, security controls,
and exact exception classification passed offline validation and direct
transport preflight. The single authorized authenticated ten-case cohort did
not satisfy the acceptance gate: it produced five fallback results and only
five complete/repaired/partial results. Production was not deployed or
changed.

## 1. Repository

Repository: https://github.com/HKJoker-Z/personal-job-agent

Implementation branch: `fix/deepseek-dedicated-direct-client`

This phase was based on the reviewed deadline-enforcement implementation in
PR #56. No production deployment, release, tag, or Version 2.0.6 action was
performed.

## 2. PR #56 final disposition

PR #56, `Fix: Enforce bounded Analyze provider deadlines`, was inspected before
this phase. Its final head was
`966026847eb18c95a7ffe319f9fc0bf09ad1ad3d`. The direct-connectivity candidate
report was present, all required checks passed, and the PR was CLEAN and
MERGEABLE with no deployment evidence.

It was merged before this implementation phase using a normal merge commit:

- merge commit: `2e154b689de8deacbadb759a151dc027df8b4efe`;
- no squash;
- no rebase;
- no admin bypass;
- main was checked out and synchronized with `pull --ff-only`;
- post-merge main CI run `31153657873` passed;
- post-merge Java candidate run `31153657871` passed.

The new branch was created from that merge commit.

## 3. Starting main commit

Starting main commit:
`2e154b689de8deacbadb759a151dc027df8b4efe`.

## 4. Production baseline

The production baseline remained:

| Item | Baseline |
|---|---|
| stable production version | `v2.0.5` |
| Alembic current/head | `20260730_07` / `20260730_07` |
| JD normalization mode | Java-authoritative `java` |
| Java policy | `jd-normalization-v1` |
| skill dictionary | `skills-v1` |
| Version 2.0.6 | unreleased |
| Provider-phase deadline | 130 seconds |
| Analyze safety deadline | 175 seconds |
| external client safety assumption | 180 seconds |
| fallback/finalization reserve | 30 seconds |

## 5. Selected architecture

The selected architecture is a DeepSeek-only, client-scoped HTTPX transport:

```text
DEEPSEEK_NETWORK_MODE
        |
        +--> direct            -> DeadlineHttpxClient(trust_env=False)
        |
        +--> environment_proxy -> DeadlineHttpxClient(trust_env=True)
```

The Provider adapter now delegates construction to
`backend/deepseek_client.py`. The client retains the current DeepSeek base URL,
API-key wiring, OpenAI-compatible SDK, `max_retries=0`, `DeadlineHttpxClient`,
per-attempt timeout derivation, and complete response-body deadline
enforcement. No process-global environment mutation is used.

## 6. Network-mode configuration

The validated setting is `DEEPSEEK_NETWORK_MODE` with only these values:

- `direct`: the dedicated production-candidate mode;
- `environment_proxy`: the configuration-only rollback and compatibility mode.

`.env.example` explicitly documents `DEEPSEEK_NETWORK_MODE=direct`. The
application parser deliberately retains `environment_proxy` as the implicit
unset-variable default so an existing deployment does not silently change
network policy. The candidate runner explicitly sets `direct`, and a later
production candidate must explicitly set `direct` in its owned environment.
Unknown values are rejected during application configuration validation. No
proxy URL or new secret was added.

## 7. Direct-client implementation

In `direct` mode the DeepSeek builder constructs the installed HTTPX client
with `trust_env=False` and explicit normal TLS certificate verification. This
ignores uppercase and lowercase `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and
`NO_PROXY` variables for this DeepSeek client only. System DNS and the current
`https://api.deepseek.com` origin remain in use.

The OpenAI-compatible SDK is configured with the installed versions:

- `openai==2.44.0`;
- `httpx==0.28.1`.

SDK automatic retries remain zero. The HTTP client is closed on construction
failure and after each Provider attempt as before.

## 8. Environment-proxy rollback implementation

In `environment_proxy` mode the same deadline-aware HTTPX client is built with
`trust_env=True`. This preserves approved HTTPX environment-proxy behavior,
including the repository's existing handling of unsupported SOCKS
`ALL_PROXY` values. Proxy types are not converted and proxy values are never
printed or persisted.

Rollback is configuration-only:

```text
DEEPSEEK_NETWORK_MODE=environment_proxy
```

No database downgrade or process-wide proxy edit is required.

## 9. Proof of client-level scope

The production Provider construction contains no `os.environ.pop`, proxy
variable rewrite, or process-global proxy clearing. Direct mode passes the
transport setting directly to the DeepSeek-specific `DeadlineHttpxClient`.

The candidate harness may still modify its own disposable process environment
for Path A and Path B comparison tests. Path C leaves the proxy variables
present and exercises the production DeepSeek builder, so that comparison
proves client-level bypass rather than environment cleanup.

## 10. Proof other Backend HTTP clients are unaffected

The direct-client unit tests construct DeepSeek with all eight upper/lowercase
proxy variables present and verify that the process environment is byte-for-
byte unchanged. In the same controlled environment, an unrelated
`httpx.Client(trust_env=True)` still selects the environment proxy transport.

The Job URL acquisition, SSRF-safe fetch, Java normalization, Project
Knowledge, Frontend, Worker/Outbox, and other Backend HTTP clients were not
changed. The existing Java normalization client continues to use its own
transport policy.

## 11. Previous `connect_timeout` discrepancy

The previous authenticated direct candidate recorded 19 Provider attempts and
9 `connect_timeout` categories, while the unauthenticated direct preflight
showed approximately 1–2 ms TCP establishment, 170–500 ms TLS, and 0.6–1.1 s
HTTP response timing. That discrepancy was not safe evidence that nine TCP/TLS
connect operations exceeded their connect bound.

## 12. Confirmed timeout-classification root cause

The installed OpenAI SDK boundary was traced with deterministic HTTPX
`MockTransport` tests. `APITimeoutError` can wrap an HTTPX timeout, while the
SDK's broad `APIConnectionError` does not itself identify whether the failure
occurred during connection, TLS, response reading, or another transport
operation.

The old Provider adapter treated every `APIConnectionError` as
`connect_timeout`. It also converted broad generic timeout/connection cases
into component categories. Therefore the old nine `connect_timeout` records
were an over-broad adapter normalization, not proof of nine failed TCP
establishments.

The new classifier walks only a bounded exception cause/context chain and
checks concrete HTTPX exception types, explicit status codes, and the custom
absolute-deadline exception types. A broad SDK wrapper without a concrete
cause is `unknown_bounded_provider_error`; a concrete non-timeout network
cause is `transport_error`. Raw exception text is not read or logged.

## 13. Old and new timeout categories

Old behavior:

- `connect_timeout`: 9 in the previous 19-attempt authenticated candidate;
- the category included broad `APIConnectionError` cases and was therefore
  ambiguous;
- HTTP status categories were named `http_429` and `http_5xx`.

New bounded categories:

- `connect_timeout`;
- `read_timeout`;
- `write_timeout`;
- `pool_timeout`;
- `provider_attempt_deadline_exhausted`;
- `provider_phase_deadline_exhausted`;
- `transient_http_429`;
- `transient_http_5xx`;
- `transport_error`;
- `unknown_bounded_provider_error`.

The deterministic tests cover every category boundary, OpenAI wrapping,
generic wrappers, arbitrary exception text exclusion, status mapping, and
the distinction between attempt and phase deadline exhaustion.

## 14. Actual connect-timeout configuration

The configured Provider connect timeout is unchanged at **5.0 seconds**. It
is derived as:

```text
effective_connect_timeout = min(5.0, effective_attempt_budget)
```

The fresh direct cohort used `REQUEST_TIMEOUT_SECONDS=60`; the effective
connect timeout was 5.0 seconds for the observed attempts, with effective
minimum/maximum 5.0/5.0 seconds. A deterministic short-budget test verifies
that the value is capped by the same absolute-deadline budget.

In installed HTTPX 0.28.1/httpcore behavior, the connect timeout is passed to
`socket.create_connection`, which includes the resolver/socket-connect call,
and to TLS `start_tls`/`ssl_context.wrap_socket`; TLS failures are therefore
observable as connect-bound failures. Connection-pool wait has its own
separate 5.0-second pool timeout. No connect-timeout increase was made.

The fresh direct preflight did not provide evidence requiring a larger bound,
and no value above 10 seconds was considered.

## 15. Authoritative deadline preservation

The implementation preserves:

- 130-second Provider phase deadline;
- 175-second Analyze safety deadline;
- 180-second external client safety assumption;
- 30-second fallback/finalization reserve;
- one shared monotonic absolute deadline for primary, retry, and repair work;
- response-body enforcement through the same deadline-aware stream;
- no independent unbounded direct-client timer.

The attempt deadline is derived from the same remaining bounded budget and is
classified separately from the shared Provider phase deadline. No active
Provider operation survived its own bounded deadline in the cohort.

## 16. Retry, repair, and call-limit preservation

The existing contract remains:

- OpenAI SDK retries: zero;
- maximum application-level retry: one;
- maximum format-only repair call: one;
- maximum Provider calls: three total;
- primary output tokens: 1600;
- length-retry tokens: 2400;
- repair tokens: 1000;
- configured token maximum: 5000.

No Schema tolerance, acceptance behavior, evidence reconciliation, scoring,
deterministic fallback, Job Summary, or Match Reasons behavior was relaxed.

## 17. Fresh direct connectivity preflight

Exactly 20 sequential unauthenticated checks were run from the disposable
Backend candidate image with `DEEPSEEK_NETWORK_MODE=direct`. No API key was
provided. Uppercase and lowercase proxy variables were passed to the
container to test the client-level bypass.

| Measure | Result |
|---|---:|
| attempts | 20 |
| transport success | 20/20 |
| connect timeout | 0/20 |
| read timeout | 0/20 |
| TLS failures | 0/20 |
| DNS failures | 0/20 |
| bounded preflight timeout | 8 seconds |
| direct bypass proven | true |
| proxy transport selected | false |
| proxy connection observed | false |
| HTTPX trust_env | false |

Bounded timing aggregates were:

| Phase | Minimum | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| TCP | 0.659 ms | 0.750 ms | 0.947 ms | 1.006 ms |
| TLS | 171.358 ms | 173.973 ms | 179.944 ms | 182.780 ms |
| total | 607.395 ms | 638.228 ms | 664.245 ms | 670.819 ms |

The disposable container could not inspect the host Mihomo process because it
was in a separate network namespace. Bypass was proven by the selected
transport and absence of proxy connection observation while the proxy
variables remained present.

## 18. Fresh authenticated cohort

Exactly one new sequential ten-case synthetic cohort was run after the direct
preflight passed. It used the same ten synthetic fixtures, model, JSON output,
thinking-disabled setting, token budgets, Provider deadline, retry limit,
repair limit, and call maximum. Only bounded metadata was retained; prompts,
responses, reasoning, and content were not stored.

Execution count: **10**.

Result states:

| Result state | Count |
|---|---:|
| complete | 3 |
| repaired | 0 |
| partial | 2 |
| fallback | 5 |
| accepted complete + repaired + partial | 5 |

## 19. Cohort retry, repair, timeout, and fallback categories

| Observation | Result |
|---|---:|
| application retries | 8 |
| format repairs | 0 |
| component timeout categories | none (`{}`) |
| `transport_error` observations | 8 |
| `provider_attempt_deadline_exhausted` observations | 1 |
| `provider_phase_deadline_exhausted` observations | 0 |
| `connect_timeout` observations | 0 |
| `read_timeout` observations | 0 |
| `write_timeout` observations | 0 |
| `pool_timeout` observations | 0 |
| fallback category | `provider_call_failed=5` |
| deadline-exhausted execution count | 0 |

The `provider_attempt_deadline_exhausted` observation is distinct from
Provider-phase exhaustion: the bounded attempt operation stopped at its own
derived attempt deadline while the shared 130-second phase still had budget.
No operation was allowed to remain active beyond that bound.

## 20. Provider and Analyze duration

The isolated runner's Provider duration and end-to-end Analyze duration
aggregates were:

| Observation | Median | p95 | Maximum |
|---|---:|---:|---:|
| Provider duration | 6,280.915 ms | 63,464.341 ms | 63,464.341 ms |
| Analyze/end-to-end duration | 6,282.320 ms | 63,470.187 ms | 63,470.187 ms |

Maximum Provider calls per execution: **2**. The 63-second observations
remained within the 130-second Provider phase and the 175-second Analyze
safety contract, but the five fallback results still fail the acceptance gate.

## 21. Token aggregates

Only bounded aggregate usage was retained:

| Token type | Minimum | Maximum | Total |
|---|---:|---:|---:|
| input | 0 | 832 | 4,061 |
| output | 0 | 445 | 1,622 |
| total | 0 | 1,275 | 5,683 |

## 22. Job Summary and Match Reasons

- Job Summary: present in 10/10 records;
- Match Reasons: present in 10/10 records.

## 23. Security, serialization, idempotency, and History

- security rejection: 0;
- public serialization/contract failure: 0;
- safe-log inspection: passed;
- secret, proxy, request-body, response-body, and reasoning leakage: 0;
- deterministic fallback remained valid;
- completed idempotency replay regression: zero Provider calls;
- History/idempotency regression tests: passed in the complete Backend suite;
- the isolated candidate runner reports History/idempotency as not applicable
  because it intentionally uses a disposable isolated runner database.

## 24. Backend validation

Final clean-environment Backend unittest discovery passed:

- 563 tests passed;
- 0 failures;
- 0 errors;
- 12 explicit PostgreSQL tests skipped in this non-PostgreSQL invocation.

Focused direct-client, configuration, candidate, acceptance, deadline, and
exception-classification suites passed. The final direct/error/deadline
rerun was 37/37.

The Backend image was rebuilt with the new client modules. A no-network
candidate-image smoke imported the production builder, verified direct
`trust_env=False`, and verified exact transport classification.

Compose configuration validation passed for both the repository compose file
and the production compose file. The full local Compose smoke reached the
frontend image build but could not complete because the isolated Docker build
could not fetch npm packages and returned `ECONNRESET`; no application
assertion failed and the smoke cleanup removed its isolated resources. The
already-run frontend tests/build and the PR's required container checks remain
the authoritative follow-up checks.

## 25. PostgreSQL validation

The opt-in PostgreSQL integration suite ran against a disposable PostgreSQL
16.9 container with explicit test-only credentials and database URLs:

- 12 tests passed;
- 0 failures;
- 0 errors;
- 0 skips.

Only the exact disposable container was removed after validation. Production
PostgreSQL, Redis, volumes, backups, and Project Knowledge were not used.

## 26. Frontend validation

- Vitest: 9 files and 70 tests passed;
- Vite production build: passed.

No frontend source or dependency change was made.

## 27. Java regression validation

Java source, policy, dictionary, and image references were unchanged.

- Maven verify: 67 unit tests plus 46 Failsafe/integration tests passed with
  zero failures, errors, and skips;
- normalization-only container smoke: healthy, zero restarts, no database
  container;
- Java-authoritative JD behavior remained unchanged in Backend tests;
- Alembic remained at `20260730_07`.

## 28. Repository safety and dependency validation

- pinned dependency inspection: `pip check` passed with no broken
  requirements;
- secret/safety scan: passed without exposing configured secret or proxy
  values;
- tracked-output check: passed;
- `git diff --check`: passed;
- no CI job was configured or used to call DeepSeek; the authenticated cohort
  was a single manual disposable validation run.

## 29. Changed files

Implementation commit files:

- `.env.example`;
- `backend/Dockerfile`;
- `backend/analysis_contract.py`;
- `backend/candidates/deepseek_direct_connectivity_candidate.py`;
- `backend/candidates/deepseek_provider_real_candidate.py`;
- `backend/config.py`;
- `backend/deepseek_client.py`;
- `backend/legacy_application.py`;
- `backend/monitoring_service.py`;
- `backend/provider_deadline.py`;
- `backend/provider_errors.py`;
- `backend/test_config.py`;
- `backend/test_deepseek_client.py`;
- `backend/test_deepseek_direct_connectivity_candidate.py`;
- `backend/test_deepseek_provider_real_candidate.py`;
- `backend/test_provider_error_classification.py`;
- `compose.yaml`;
- `deploy/production/compose.yaml`;
- `docs/DEEPSEEK_PROVIDER_ACCEPTANCE.md`;
- `ops/candidate/deepseek-provider/run-real-candidate.sh`.

The evidence commit adds this report and updates
`docs/work-reports/README.md`.

## 30. Commits

Implementation commit:

- `e1ceec3` — `feat: isolate DeepSeek provider networking`.

The report/index documentation commit and final PR head will be recorded
after the report is committed and the PR is created.

## 31. Pull request

PR title: `Fix: Isolate DeepSeek from environment proxies`

PR URL: to be recorded after PR creation in the final report update.

The PR will remain open. It must not be merged automatically, deployed,
tagged, or released.

## 32. Candidate decision

Decision: **NO-GO**.

The direct transport gate passed: 20/20 success, zero connect timeouts, and
client-level Mihomo bypass proof. The implementation and classification gates
also passed. The authenticated acceptance gate failed:

- accepted complete/repaired/partial: 5, required at least 8;
- fallback: 5, allowed at most 2;
- maximum Provider calls: 2, within the limit;
- Job Summary: 10/10;
- Match Reasons: 10/10;
- security and serialization defects: 0;
- deadline-exhausted executions: 0.

The exact `transport_error` observations are no longer misreported as
`connect_timeout`, but the resulting Provider availability evidence does not
authorize a production candidate.

## 33. Exact next prerequisite

Do not deploy this branch. First investigate and stabilize the external
DeepSeek direct Provider availability represented by the bounded
`transport_error` results and the one attempt-deadline result. After that
external state changes, a separately authorized phase may run one fresh
ten-case cohort using the final branch and the same gate. Do not rerun
individual failures or manufacture a passing cohort.

## 34. Rollback plan

If this change is later authorized for deployment and a stop condition occurs:

1. stop candidate Analyze traffic;
2. set `DEEPSEEK_NETWORK_MODE=environment_proxy` for the DeepSeek client, or
   restore the previous Version 2.0.5 Backend configuration/images if broader
   rollback is required;
3. preserve Java, Alembic, PostgreSQL/Redis volumes, backups, and Project
   Knowledge;
4. verify Backend, Frontend/Edge, Java, PostgreSQL, Redis, Worker, Outbox,
   version, Alembic head, restart counts, login, Analyze, History, and
   idempotency without inspecting user content.

No rollback was required because production was not touched.

## 35. Risks and negative effects

- Direct mode intentionally bypasses an operator or corporate proxy for
  DeepSeek only; a network policy that requires that proxy may fail until the
  configuration rollback is selected.
- Direct DNS/TLS/provider availability is now exposed directly to the
  Provider acceptance gate; the fresh cohort showed bounded transport
  failures.
- Exact classification may reduce retries for ambiguous SDK errors by
  refusing to invent a component category; only concrete bounded categories
  receive the one application retry.
- The deadline-aware transport uses a small daemon worker boundary and closes
  the active HTTPX client when a hard deadline expires.
- No Schema relaxation, retry increase, deadline increase, or fallback
  weakening was made.

## 36. Confirmation production was untouched

Confirmed: production was not deployed, restarted, reconfigured, migrated,
queried through `/api/analyze`, or used for candidate traffic. Existing
production processes/containers were not modified.

## 37. Confirmation Java and Alembic were unchanged

Confirmed: Java source, Java policy `jd-normalization-v1`, skill dictionary
`skills-v1`, Java image references, and Alembic revision files were unchanged.
No Alembic migration was created or run against production. The baseline head
remains `20260730_07`.

## 38. Confirmation no production/user content was inspected

Confirmed: no production/user application content—resumes, job descriptions,
Project Knowledge, History records, database records, Provider bodies, or
reasoning—was inspected. The authenticated cohort used only synthetic
fixtures and retained bounded metadata aggregates. Repository configuration
files were used only for implementation and validation.

## 39. Confirmation no release activity occurred

Confirmed:

- no version bump;
- no deployment;
- no release image publication;
- no image release tag;
- no Git tag;
- no GitHub Release;
- no Version 2.0.6 release;
- no production environment change.

Version 2.0.5 remains the stable production version. This phase produced an
open implementation PR and a NO-GO evidence record only.
