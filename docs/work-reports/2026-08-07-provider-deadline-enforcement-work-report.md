# Provider Deadline Enforcement Work Report

Date: 2026-08-07

Decision: NO-GO for a future production-candidate attempt. The bounded
deadline correction is implemented and validated, but the final isolated
real-provider cohort exceeded the acceptance fallback limit because of
Provider connection failures. Production was not deployed or changed.

## 1. Repository

Repository: https://github.com/HKJoker-Z/personal-job-agent

Implementation branch: `fix/provider-deadline-enforcement`

Implementation PR: https://github.com/HKJoker-Z/personal-job-agent/pull/56

## 2. Starting commit

The phase started from main commit
`2b7d12a3b19a7125c94773126044c274ff745f4f`.

## 3. Finalized NO-GO report PR

The preceding Version 2.0.6 NO-GO report was finalized before implementation:

- report PR: https://github.com/HKJoker-Z/personal-job-agent/pull/55;
- final report-PR head: `289e4c862918be552e392983f18b05eadcb8d1e2`;
- normal merge commit: `2b7d12a3b19a7125c94773126044c274ff745f4f`;
- required checks: passed;
- contents: documentation-only release evidence and index update.

The report PR was merged with a normal merge commit. Main was checked out and
fast-forward synchronized before this branch was created. No admin bypass,
squash, rebase, deployment, or release action was used.

## 4. Production baseline

The stable production baseline remained:

| Item | Observed baseline |
|---|---|
| application version | `v2.0.5` |
| Alembic current/head | `20260730_07` / `20260730_07 (head)` |
| Analyze API | synchronous `/api/analyze` |
| JD normalization | Java-authoritative `java` mode |
| Java policy | `jd-normalization-v1` |
| skill dictionary | `skills-v1` |
| external Analyze bound | 180 seconds |
| configured Provider deadline | 130 seconds |
| final root capacity from release rollback report | 12,870,742,016 bytes, approximately 11.98 GiB |

The read-only production baseline showed HTTP 200 readiness, Java readiness,
healthy PostgreSQL and Redis, healthy Backend/Frontend/Edge/Worker/Outbox,
zero observed restart counts, and no OOMKilled state. No user Resume, JD,
Project Knowledge, History, Provider body, or production Analyze request was
inspected in this phase.

## 5. Observed 180-second incident

The preceding candidate deployment reached a healthy state while retaining
application Version 2.0.5. Execution 1 completed as a bounded fallback.
Execution 2 produced no response before the external client’s 180-second
bound, although the configured Provider deadline was 130 seconds. Automatic
rollback restored the previous images and compose/configuration revision.
No execution after the stop condition was started, so the required ten-case
production cohort was incomplete and the decision was NO-GO.

The incident does not prove that DeepSeek itself ran for 180 seconds. The
application used a blocking synchronous SDK call, and the previous transport
configuration did not provide a hard total response-body cancellation
boundary.

## 6. Complete synchronous Analyze timing trace

The request path was traced from the public route through final serialization:

1. FastAPI parses the public multipart/form request. Authentication, active
   account, Origin, CSRF, trusted-host, and request-correlation middleware run
   before the Analyze handler.
2. The handler validates the exact resume source, job source, RAG mode/top-k,
   and idempotency key. At handler entry it now starts the monotonic total
   safety clock.
3. Resume resolution either reads the owned stored Resume Version or extracts
   the uploaded PDF/DOCX text, then truncates it to the configured bound.
4. Job acquisition either accepts bounded pasted text or performs the existing
   bounded URL acquisition and truncation.
5. When an idempotency key is present, the request fingerprint is computed and
   the claim is made. A completed claim returns its stored response before any
   Provider call. A processing claim remains protected by the existing lease
   and attempt token.
6. Resume and JD content are sanitized and security-scanned. The effective
   Java normalization path then acquires/validates normalized JD output and
   performs the authoritative second security scan. The execution binding is
   stored for the idempotency claim.
7. Project Knowledge retrieval runs when enabled, followed by Project
   Knowledge security scanning and filtering. The safe prompt is constructed
   only after these boundaries.
8. The Provider phase starts immediately before `provider_started` and the
   initial Provider request. The route creates one `ProviderDeadline` from an
   absolute monotonic deadline and passes that same absolute value to both
   primary and repair functions.
9. The initial primary call receives a derived HTTPX timeout. Response headers
   and the complete non-streaming response body are read through the
   deadline-aware transport.
10. A bounded application retry may follow a safe timeout/5xx/429/resource/
    empty/length category. Backoff consumes the same absolute budget.
11. Output security scanning runs before acceptance. Local JSON parsing and
    field salvage happen next. If needed, exactly one format-only repair call
    receives the same absolute deadline and a derived repair timeout.
12. Acceptance, repaired/partial classification, evidence-reference cleanup,
    evidence reconciliation, deterministic scoring, Job Summary, Match
    Reasons, and deterministic fallback selection complete the Provider-phase
    transition.
13. The final serialized result is security-scanned. Backend-owned scoring and
    narratives are applied; no Provider reasoning or raw body is returned.
14. History is inserted or the atomic idempotency finalization stores the
    response. Attempt-token protection prevents a stale takeover from writing
    a second terminal result.
15. The response is serialized and returned. Completed idempotency replay
    returns the stored body and makes zero Provider calls.

The authoritative Provider deadline begins at the `run_llm_analysis` boundary,
after prompt construction and before the Provider state transition. The
request-level safety clock starts at handler entry. The Provider deadline is
capped so that the request retains the finalization reserve and the unchanged
180-second external bound retains a delivery margin.

## 7. Confirmed root cause

The root cause was a missing hard total deadline at the synchronous transport
boundary, combined with a blocking synchronous OpenAI-compatible SDK call in
an async FastAPI handler. The previous code passed a shrinking numeric timeout
to the SDK, but HTTPX applies read timeouts per read operation. A response that
stalls before headers, stalls between body chunks, or repeatedly emits chunks
can therefore remain active beyond the application’s intended clock. The
async handler cannot observe a client disconnect while it is blocked inside
that synchronous call.

The previous code did bound retry decisions against its monotonic Provider
deadline and passed the route deadline into the repair call, but it did not
bound the complete body stream, did not reserve fallback/finalization time,
and did not enforce the request-level safety contract through finalization.
The failure was not attributed to DeepSeek without transport evidence.

## 8. SDK and HTTP transport behavior

The installed versions inspected in the isolated environment were:

- OpenAI-compatible SDK: `openai 2.44.0`;
- HTTP transport: `httpx 0.28.1`;
- SDK default timeout: connect 5 seconds, read 600 seconds, write 600
  seconds, pool 600 seconds;
- SDK automatic retries: explicitly `0` before and after this change.

The previous application passed a float of up to the configured 60-second
request timeout to `OpenAI`. HTTPX converts a float timeout into a uniform
per-operation timeout; it is not a total request/body deadline. The previous
application used a synchronous client directly inside the async route. It did
not use an async SDK, thread offload, `asyncio.wait_for`, or an AnyIO timeout
around the actual network operation.

The new per-call `DeadlineHttpxClient` retains normal HTTPX environment proxy
behavior, supplies explicit component timeouts, wraps the non-streaming body,
and closes the dedicated per-call client if header acquisition or a body read
reaches the absolute deadline. Blocking transport work is isolated inside the
dedicated transport boundary; closing that client interrupts the active
network operation rather than merely cancelling an outer coroutine.

## 9. Proxy behavior

The operator shell had HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, and NO_PROXY
variables present; no values or credentials were printed. The approved
HTTP(S) proxy path and NO_PROXY behavior were preserved. The inherited
ALL_PROXY value was an incompatible SOCKS path for the installed HTTPX
environment, so only `ALL_PROXY`/`all_proxy` were removed inside the
disposable candidate process. Production’s running Backend proxy state was
not changed.

The isolated candidate used the existing development/operator secret-loading
mechanism only to obtain the approved Provider secret; the value was never
printed, persisted in candidate evidence, or included in logs.

## 10. Previous deadline implementation

Before this phase:

- the route clock began at `run_llm_analysis`;
- primary calls used `min(REQUEST_TIMEOUT_SECONDS, remaining)`;
- the application retry and retry backoff checked the same route absolute
  deadline;
- the route passed that absolute deadline to format repair;
- SDK automatic retries were zero;
- there was no hard total body-stream deadline;
- local parsing, salvage, evidence reconciliation, deterministic fallback,
  final security scanning, History, idempotency finalization, and response
  serialization were outside the Provider deadline contract;
- no client-disconnect check ran before or after Provider work;
- a blocking SDK operation could continue after the external client stopped
  waiting.

Thus the old clock was useful for deciding whether to start another call, but
it did not guarantee that the actual synchronous network operation and the
complete Analyze response path would finish before the client bound.

## 11. New authoritative deadline contract

The new contract uses one absolute `time.monotonic()` deadline per Analyze
Provider phase. No wall-clock arithmetic is used.

| Contract item | Value/behavior |
|---|---|
| external client contract | unchanged 180 seconds |
| total Analyze safety deadline | 175 seconds from handler entry |
| client delivery margin | 5 seconds |
| configured Provider deadline | unchanged default 130 seconds |
| fallback/finalization reserve | 30 seconds |
| retry reserve | configured 0.25-second backoff reserve |
| repair reserve | 5 seconds in addition to finalization reserve |
| minimum new call budget | 1 second |
| maximum primary calls | 2 |
| maximum format repairs | 1 |
| maximum Provider calls | 3 |

The Provider absolute deadline is the minimum of the phase-start plus the
configured 130 seconds and the request safety deadline less the 30-second
finalization reserve. Every call computes `absolute_deadline -
time.monotonic()` immediately before construction and again before retry or
repair. If the remaining budget cannot support a bounded call and the reserve,
no new Provider call starts; the existing deterministic fallback is selected
with `fallback_reason=provider_deadline_exhausted`.

## 12. Per-attempt timeout configuration

Each attempt receives a fresh timeout object derived from the same absolute
deadline. The configured request ceiling remains 60 seconds.

| Component | Contract |
|---|---|
| connect | maximum 5 seconds, capped by remaining attempt budget |
| read | remaining attempt budget, also enforced as an absolute total body bound |
| write | maximum 10 seconds, capped by remaining attempt budget |
| connection pool | maximum 5 seconds, capped by remaining attempt budget |
| SDK retries | 0 |

The transport updates request timeout extensions at send time and actively
closes the dedicated client when a header or body operation reaches the
absolute boundary. Per-read HTTPX behavior cannot extend the total Provider
phase.

## 13. Retry and repair remaining-budget behavior

The first primary call uses the remaining deadline minus the finalization
reserve, capped by `REQUEST_TIMEOUT_SECONDS`. A safe retry can start only when
its derived budget still leaves the finalization reserve and the configured
retry-backoff reserve. The backoff itself is taken from the same absolute
deadline; it never creates a new full timeout.

The one repair call can start only when its derived budget leaves both the
30-second finalization reserve and the 5-second repair reserve. Repair is
format-only and uses the existing 1000-token budget. Length retry remains the
only primary retry that increases the primary output budget to 2400 tokens.
No retry or repair starts after the authoritative deadline is exhausted or
when its remaining budget is unsafe.

## 14. Fallback and finalization reserve

Deadline exhaustion is converted to a classified `MODEL_PROVIDER_ERROR` with
safe metadata and the stable public fallback state. The route constructs the
existing deterministic fallback, completes final security processing, performs
History/idempotency finalization at most once, and serializes the response.
Internal SDK, proxy, timeout, request, and exception details are not exposed.
Fallback state is never converted into an unhandled HTTP 500 solely because
the Provider deadline was reached.

The 30-second reserve is the explicit safety budget for local fallback
construction, final output security, History/idempotency transaction work, and
JSON response serialization. The route’s final timing observation is emitted
after finalization, while timing fields remain internal so stored and replayed
public bodies remain stable.

## 15. Client-disconnect behavior

The request remains synchronous, so a disconnect cannot be polled from another
event loop while the blocking SDK call is executing. The implemented policy is:

- check disconnect status before Provider work;
- if already disconnected, do not start a Provider call, select fallback, and
  finalize the current idempotency claim once;
- if disconnect is observed after Provider work, do not start another retry or
  Provider call; allow one bounded finalization so the ledger does not remain
  stale;
- let the transport deadline close a network operation that is active while
  the caller has stopped waiting;
- retain the existing attempt-token protection and indeterminate-persistence
  contract.

Tests cover a detected pre-Provider disconnect, a disconnect observed after a
Provider result, and active transport close during a stalled body operation.

## 16. Idempotency and History behavior

Completed idempotency replay remains before Provider invocation and makes zero
Provider calls. A stale in-progress claim can still be taken over only under
the existing lease/attempt-token rules. A deadline fallback is finalized with
the same atomic History/idempotency path as other valid Analyze results.

The endpoint regression tests confirmed one terminal idempotency record,
byte-for-byte replay, no duplicate successful result, and no duplicate History
row. The isolated direct candidate runner deliberately does not connect to
PostgreSQL, Redis, History, or the public Analyze endpoint; its candidate
report marks those two fields explicitly not applicable, while endpoint and
PostgreSQL tests cover the applicable behavior.

## 17. Observability changes

The existing bounded model metadata and monitoring observation allow only
stable categories and bounded values:

- Analyze/provider stage duration and total Analyze duration;
- Provider attempt number and bounded attempt durations;
- connect/read/write/pool timeout categories;
- deadline-exhausted boolean and remaining-deadline bucket;
- retry-started, repair-started, fallback-selected;
- History-finalized, idempotency-finalized, client-disconnected;
- final result state.

No prompt, Resume/JD text, Project Knowledge, Provider response,
`reasoning_content`, credentials, Authorization/Session/Cookie, actual hash,
request ID label, arbitrary exception text, or proxy value is added by this
change. No Alembic migration or monitoring-table schema change was made.
Timing fields are kept in internal monitoring/logging observations rather than
the public Analyze body.

## 18. Deterministic reproduction

The offline transport suite uses a local synthetic HTTP server and mocks only;
it never calls DeepSeek. It reproduces:

1. refused/expired connection budget;
2. connection attempt that does not produce a response;
3. connect/TLS timeout classification;
4. connection timeout;
5. headers followed by a stalled body;
6. slow streaming response;
7. a single body read that begins before and crosses the absolute deadline;
8. empty Provider content;
9. initial timeout followed by successful retry;
10. initial timeout followed by retry timeout;
11. insufficient remaining time for retry;
12. insufficient remaining time for repair;
13. fallback/finalization reserve near the deadline;
14. active transport close while a Provider operation is in progress;
15. async disconnect-boundary detection;
16. completed idempotency replay;
17. stale in-progress takeover;
18. maximum primary-call enforcement.

All timeout tests use sub-second scaled deadlines and complete without external
network access.

## 19. Tests added

Added `backend/test_provider_deadline_enforcement.py` with 22 focused tests.
Extended `backend/test_analyze_idempotency.py` with disconnect-after-provider
and deadline-exhaustion endpoint coverage. Candidate runner unit coverage was
retained and updated for one shared absolute deadline and explicit
History/idempotency applicability metadata.

## 20. Complete Backend validation

Final Backend unittest discovery passed:

- 541 tests passed;
- 0 failures and 0 errors;
- 12 PostgreSQL tests were skipped in the non-PostgreSQL discovery invocation
  because that suite is explicitly opt-in.

The focused deadline and Analyze/idempotency suites passed 56/56 after the
final transport and observability changes.

GitHub PR #56 CI completed with all required validation jobs passing,
including Backend, PostgreSQL, Docker/Compose, frontend, Java/assets,
container smoke, repository safety, script validation, and the isolated
candidate workflow. Image-publication jobs were skipped by the explicit
no-release policy.

## 21. PostgreSQL validation

The opt-in PostgreSQL integration suite ran against a disposable, explicitly
test-named PostgreSQL 16.9 container with both the application and test
database URLs pointed at that container:

- 12 tests passed;
- 0 failures;
- 0 errors;
- 0 skips.

The disposable container and its data were removed after the test. Production
PostgreSQL, Redis, volumes, backups, and Project Knowledge were not used.

## 22. Frontend validation

Frontend validation passed:

- Vitest: 9 files and 70 tests passed;
- Vite production build: passed.

The dependency inspection also reported an existing high React Router advisory
for the locked `react-router-dom 7.18.1` dependency. This phase did not change
frontend dependencies; the advisory is recorded as a release risk and was not
introduced by the deadline correction.

## 23. Java regression validation

Java source, policy, dictionary, and image references were unchanged.

- Maven verify: 67 unit tests plus 46 Failsafe/integration tests passed;
  zero failures, errors, and skips;
- normalization-only container smoke: passed with healthy service, zero
  restarts, and no database container;
- full-profile Java container smoke: passed with healthy application and
  PostgreSQL, replay/update/history/persistence checks passing.

## 24. Isolated real-provider execution count

One final ten-case sequential isolated cohort was run after the final candidate
runner changes. It used synthetic Resume, JD, and Project Knowledge fixtures,
the approved model and token contract, the existing operator HTTP(S) proxy
path, unchanged NO_PROXY behavior, and no production database, Redis, volume,
public endpoint, or user data.

Execution count: 10.

## 25. Isolated complete/repaired/partial/fallback counts

| Result state | Count |
|---|---:|
| complete | 3 |
| repaired | 0 |
| partial | 3 |
| fallback | 4 |
| accepted complete + repaired + partial | 6 |

## 26. Isolated timeout categories

The bounded timeout category count was:

- `connect_timeout`: 6;
- `read_timeout`: 0;
- `write_timeout`: 0;
- `pool_timeout`: 0.

Fallback reason category: `provider_call_failed=4`. No deadline was reached
inside the ten synthetic executions; the provider deadline-exhausted count was
0. All four fallback cases were bounded connection failures and returned the
existing deterministic fallback.

## 27. Deadline-exhausted count

Isolated cohort `deadline_exhausted_count`: 0.

The offline deterministic deadline tests separately confirmed that an
exhausted or unsafe remaining budget prevents a new attempt and returns the
stable `provider_deadline_exhausted` fallback classification.

## 28. Maximum Provider calls

Maximum Provider calls observed in the isolated cohort: 2.

The implementation preserves the absolute maximum of 3 calls: two primary
attempts plus one format-only repair. No candidate case exceeded that bound.

## 29. Maximum duration observations

| Observation | Median | p95 / maximum |
|---|---:|---:|
| Provider phase | 6,415.967 ms | p95/max 9,367.956 ms |
| end-to-end | 6,417.421 ms | p95/max 9,375.959 ms |

All ten executions completed well below the 180-second external bound and the
new 175-second total safety contract. The cohort nevertheless failed the
acceptance-state gate because four cases fell back.

## 30. Token and latency observations

The isolated runner recorded only bounded aggregate usage:

| Token type | Minimum | Maximum | Total |
|---|---:|---:|---:|
| input | 0 | 830 | 4,866 |
| output | 0 | 453 | 1,680 |
| total | 0 | 1,283 | 6,546 |

Provider latency median/p95 was 6,415.967/9,367.956 ms. End-to-end latency
median/p95 was 6,417.421/9,375.959 ms. No prompt, response body, or reasoning
content was stored.

## 31. Job Summary result

Job Summary was present in 10/10 isolated public-contract records. No case
required an unavailable-summary marker.

## 32. Match Reasons result

Match Reasons was present in 10/10 isolated public-contract records. No case
required an unavailable-reasons marker.

## 33. Security and serialization result

- security rejection count: 0;
- public serialization/contract failure count: 0;
- safe-log inspection: passed;
- body, prompt, secret, Authorization, proxy, and reasoning leakage: 0;
- severe security output was never converted into a partial result.

## 34. Changed files

Implementation changes are limited to:

- `backend/provider_deadline.py`;
- `backend/legacy_application.py`;
- `backend/Dockerfile`;
- `backend/analysis_contract.py`;
- `backend/monitoring_service.py`;
- `backend/candidates/deepseek_provider_real_candidate.py`;
- `backend/test_provider_deadline_enforcement.py`;
- `backend/test_analyze_idempotency.py`;
- `docs/ANALYZE_IDEMPOTENCY.md`;
- `docs/DEEPSEEK_PROVIDER_ACCEPTANCE.md`;
- `docs/V2_PRODUCTION_READINESS.md`;
- `docs/work-reports/README.md`;
- this Work Report.

`docs/PROJECT_KNOWLEDGE.md`, Java source/configuration, Alembic revisions,
README stable-version references, image release tags, and production files
were not changed.

## 35. Commits

Logical implementation commits pushed to the PR branch:

1. `d3e01be` — `fix: enforce authoritative provider deadline`;
2. `6cef40d` — `test: cover provider deadline and disconnect regressions`;
3. `7f2c802` — `feat: add bounded provider deadline telemetry`;
4. final PR-head documentation commit — `docs: record provider deadline
   candidate evidence` (candidate evidence, operations docs, Work Report, and
   Work Report index update).

The final documentation commit is the PR head containing this report and is
visible in PR #56. No release commit was created.

## 36. Pull request

PR title: `Fix: Enforce bounded Analyze provider deadlines`

PR URL: https://github.com/HKJoker-Z/personal-job-agent/pull/56

The PR description includes the production NO-GO incident, root cause,
previous/new contract, timeout budgets, fallback/disconnect behavior,
security/idempotency preservation, isolated candidate result, risks, rollback,
and this Work Report link. The PR is intentionally open and must not be merged
automatically.

## 37. Candidate decision

Decision: NO-GO.

The deadline enforcement itself passed the boundedness tests and the final
isolated cohort completed all ten executions. The acceptance gate still
requires at least 8 accepted states and no more than 2 fallbacks; this cohort
had 6 accepted and 4 fallback. The connection failures were bounded and
classified, but that does not authorize a GO under the stated gate.

## 38. Exact production-candidate prerequisite

Do not deploy this branch from the current result. First stabilize or verify
the approved HTTP(S) Provider path, then run a fresh isolated ten-case cohort
using the final branch and the exact approved proxy/secret mechanism. That
cohort must record at least 8 complete/repaired/partial results, no more than
2 fallbacks, zero security/serialization failures, no active Provider call
past its absolute deadline, maximum three calls, complete narratives or
explicit unavailable markers, and successful idempotency/History regression
evidence. Only after that gate returns GO may a separately authorized
production-candidate deployment be considered, while retaining Version 2.0.5.

## 39. Risks and negative effects

- The synchronous Analyze architecture still cannot observe a disconnect from
  another event loop while arbitrary local CPU or database code is executing;
  the Provider transport and reserve bound the network phase, and boundary
  checks/finalization protect the ledger.
- A Provider timeout can increase fallback rate and reduce AI-derived detail;
  this is intentional and safer than an unbounded request.
- The dedicated per-call transport thread adds small overhead and closes the
  active call client on deadline; no Provider SDK retry is added.
- The isolated real-provider path showed intermittent/bounded connection
  failures, so Provider availability remains a release-gate risk.
- The existing high React Router dependency advisory remains unresolved and
  outside this deadline-only change.

## 40. Rollback plan

If the change is later deployed and any stop condition occurs:

1. stop the candidate Analyze traffic and do not start another cohort case;
2. restore the previous Version 2.0.5 Backend/Worker/Outbox/Frontend/Edge
   images;
3. restore the previous compose revision and configuration;
4. preserve Java, Alembic, PostgreSQL/Redis volumes, backups, and Project
   Knowledge;
5. verify Backend, Frontend/Edge HTTPS, Java, PostgreSQL, Redis, Worker,
   Outbox, restart counts, version, and Alembic current/head;
6. verify login, Analyze gate, History gate, Java readiness, and idempotency
   replay without inspecting user content.

No rollback was required in this implementation phase because no production
deployment occurred.

## 41. Confirmation production was untouched

Confirmed: production was not deployed, restarted, reconfigured, migrated,
queried through `/api/analyze`, or used for candidate traffic. Only read-only
baseline checks were performed.

## 42. Confirmation Java and Alembic were unchanged

Confirmed: Java source, Java policy `jd-normalization-v1`, skill dictionary
`skills-v1`, Java image, and Alembic revision files were unchanged. No Alembic
migration was created or run against production.

## 43. Confirmation no user data was used

Confirmed: the isolated real-provider cohort used only synthetic Resume, JD,
and Project Knowledge fixtures. No production user content, production
database, Redis, volume, backup, or public Analyze endpoint was used.

## 44. Confirmation no release activity occurred

Confirmed:

- no application version bump;
- no README stable-version bump;
- no `docs/PROJECT_KNOWLEDGE.md` update;
- no image release tag or immutable release image publication;
- no production deployment;
- no Git tag;
- no GitHub Release;
- no Version 2.0.6 release notes or release commit.

Version 2.0.5 remains the stable production release. This phase completed
Provider Deadline Enforcement implementation, validation, documentation, and
an open PR only.
