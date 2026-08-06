# DeepSeek Provider Real Candidate Validation Work Report

Date: 2026-08-06
Repository: HKJoker-Z/personal-job-agent
Candidate decision: CONDITIONAL GO for a controlled rollout candidate; this is not production approval.

## 1. Repository and delivery baseline

Repository: https://github.com/HKJoker-Z/personal-job-agent

PR #51 final head: be7deb6f2db0a2ad7730abe0b92d69cf123800cf
PR #51 merge commit: adba18ce5bb2bec2ee177506ca991b9085a4f1da
Starting main commit for this phase: adba18ce5bb2bec2ee177506ca991b9085a4f1da
Candidate branch: test/deepseek-provider-real-candidate

PR #51 was merged with a normal merge commit. Local main and origin/main
were synchronized at the merge commit before the candidate branch was
created. The candidate PR URL will be recorded after it is opened.

The production baseline remained v2.0.5, Alembic 20260730_07, Java JD
normalization mode java, Java policy jd-normalization-v1, and skill
dictionary skills-v1. The synchronous /api/analyze path was not deployed
or called as a production endpoint.

## 2. Exact scope and exclusions

This phase validated the merged Provider acceptance boundary against the real
DeepSeek API with ten bounded synthetic cases, plus isolated mock and
regression validation for the HTTP, persistence, History, and idempotency
contracts.

The phase excluded production deployment, production Analyze traffic,
production PostgreSQL, production Redis, production Docker networks and
volumes, production Project Knowledge, production Resume/JD/History data,
version bump, tag, Release, image publication, migration changes, and Java
source/configuration changes.

The real candidate runner validates the Provider boundary after synthetic JD
input preparation. Java normalization was not called from the real-provider
runner; the existing Java path was validated separately by its current Maven
and container checks.

## 3. Candidate isolation and secret handling

The real runner was manually opt-in only and required
PJA_REAL_DEEPSEEK_CANDIDATE=1. It used a disposable SQLite database and a
synthetic Project Knowledge path under a temporary directory. The runner did
not connect to the running application containers, their PostgreSQL, Redis,
networks, or volumes. The PostgreSQL integration suite used a separate
disposable PostgreSQL 16 container on a dedicated loopback port and removed it
after the test.

The existing local operator-controlled DeepSeek secret mechanism was used by
the normal development .env loader. The key was checked only for presence,
was never printed, placed in Git, put in a command argument, included in the
report, or written to an artifact. Authorization headers, complete requests,
complete Provider responses, and reasoning_content were not recorded.

The host environment exposed an unsupported SOCKS ALL_PROXY for the pinned
OpenAI/httpx client. The candidate wrapper clears ALL_PROXY only inside the
disposable candidate process; it does not alter production configuration.
With that candidate-only isolation, the real DeepSeek request completed.

## 4. Configuration under test

The current operator-configured model was used without rewriting it:
deepseek-v4-pro. No model migration cohort was mixed into these results.

The exact merged configuration was:

- response mode: json_object;
- thinking: disabled, through extra_body.thinking.type=disabled;
- primary output budget: 1600 tokens;
- length-retry budget: 2400 tokens;
- format-repair budget: 1000 tokens;
- application configuration maximum: 5000 tokens;
- SDK automatic retries: zero;
- one application-level primary retry at most;
- one format-only repair at most;
- absolute maximum Provider calls for a new Analyze execution: three.

The successful real responses confirm that DeepSeek accepted JSON Output with
thinking disabled. The candidate did not enable thinking or expose reasoning
content.

## 5. Retry and repair contract

The merged path permits one retry only for fixed transient categories:
connect timeout, read timeout, HTTP 429, HTTP 5xx, documented resource
exhaustion, empty content, or finish_reason=length. The retry is bounded by
the overall deadline and backoff configuration. Authentication, invalid
configuration, non-retryable 4xx, local deterministic validation failures,
severe output-security findings, and completed idempotency replays are not
retried.

A safe but unparseable response may receive one format-only repair request.
The repair is never sent a severely unsafe primary response. No primary
length retry and multiple repair calls can occur. The real cohort observed a
maximum of two calls; the mock tests exercised the three-call ceiling.

The accepted negative effects remain higher worst-case latency and token cost,
and possible duplicate Provider billing after an ambiguous timeout.

## 6. Synthetic candidate corpus

The corpus contains ten distinct, bounded, synthetic cases. It covers short
and medium Resume/JD sizes, backend/platform/frontend/data/quality technical
roles, support-engineering roles, strong/partial/low matches, required and
preferred skills, work experience, projects, limited Project Knowledge, and
no relevant Project Knowledge. It contains no production identifiers, user
content, secrets, deliberate prompt injection, or illegal content.

Requests were executed sequentially. This was not a load or stress test.

## 7. Real-provider evidence

The final cohort was the ten-case run executed with the final runner revision.
Only the following bounded metadata was retained.

| Observation | Result |
|---|---:|
| Candidate executions | 10 |
| complete | 3 |
| repaired | 0 |
| partial | 4 |
| fallback | 3 |
| Security rejections | 0 |
| Public-contract serialization failures | 0 |
| Primary attempts | 14 |
| Primary retries | 4 |
| Format repairs | 0 |
| Maximum Provider calls observed | 2 |
| Empty-content responses | 0 |
| Length retries | 0 |
| Job Summary present | 10/10 |
| Job Summary explicit-unavailable | 0/10 |
| Match Reasons present | 10/10 |
| Match Reasons explicit-unavailable | 0/10 |

Retry categories were connect_timeout: 4. The three fallback categories
were provider_call_failed: 3; each exhausted the single allowed retry.
Finish-reason observations were stop: 7 and other: 3 for the three failed
Provider attempts. Parse outcomes were canonical: 7 and invalid: 3 (the
invalid observations corresponded to calls that produced no usable Provider
response). No empty or length-truncated response was observed.

Four accepted partial results applied the bounded
evidence_reference_cleanup action. Complete results used no salvage. No
real response required format repair, so the real cohort does not claim repair
success evidence.

## 8. Token and latency observations

Token counts are Provider-returned counts only; no monetary cost was inferred.
Failed calls contribute zero returned token counts.

| Metric | Minimum | Maximum | Total |
|---|---:|---:|---:|
| Input tokens | 0 | 837 | 5,750 |
| Output tokens | 0 | 392 | 2,232 |
| Total tokens | 0 | 1,222 | 7,982 |

Measured Provider-duration median/p95 was 5,710.432 / 8,080.731 ms.
Measured end-to-end candidate median/p95 was 5,733.206 / 8,088.275 ms.
These are bounded candidate observations, not a performance improvement
claim or a production latency guarantee.

## 9. Acceptance correctness

All ten candidate records produced a safe serialized result representation,
including the three deterministic fallbacks. All ten exposed a Job Summary
and Match Reasons representation; none required the unavailable explanation.
The accepted partial results retained Provider-derived analysis and only
applied bounded evidence cleanup. Severe output findings are rejected before
repair by the mocked runner tests and existing Provider acceptance corpus.
No candidate execution exceeded three calls.

The real runner itself exercises the Provider acceptance and final
serialization boundary directly. The HTTP idempotency and History behavior
was validated through the existing isolated mock endpoint tests because a
completed replay must not make a second real Provider call.

## 10. Idempotency, History, and side effects

The focused Analyze idempotency suite passed. Its completed duplicate replay
assertion verifies one Provider invocation for the initial request, zero new
Provider calls for the completed replay, identical replayed response, and one
History row. History-plus-idempotency finalization is asserted as one atomic
completion. Provider-indeterminate and stale-attempt behavior also passed.

The PostgreSQL integration suite passed all 12 tests with zero skips in the
disposable database, including process-safe idempotency claims, execution
binding, rollback, monitoring, and History-related database behavior. No
duplicate Provider or History side effect was observed in the validated
paths.

## 11. Safe observability and log inspection

The runner wrote only bounded metadata: model ID, thinking flag, response
mode, attempt counts, retry categories, finish reason, empty flag, parse
outcome, salvage categories, accepted/rejected field counts, result state,
fallback category, token counts, and durations. No prompt, Resume/JD text,
Project Knowledge text, Provider body, reasoning content, content hash,
request ID, credential, authorization value, or arbitrary exception string
was written.

The in-memory safe-log inspection passed. It checked for reasoning,
authorization, API-key, and Provider-body markers without persisting the log
body.

## 12. Regression validation

The following validations passed:

- mocked real-candidate runner tests: 6/6;
- focused Provider acceptance, candidate, and idempotency tests: 48/48;
- complete Backend unittest discovery: 515 passed, exit 0;
- explicit Backend PostgreSQL integration: 12/12, zero skips;
- Frontend suite: 70 tests across 9 files passed;
- Frontend production build: passed;
- Java ./mvnw -B verify: 46 tests, 0 failures, 0 errors, 0 skips;
- Java normalization-only ephemeral container smoke: passed;
- Java full-profile ephemeral container smoke: passed;
- existing Java candidate Compose configuration validation: passed;
- Backend OpenAPI generation/serialization: OpenAPI 3.1.0, 39 paths, Analyze
  POST and History paths present;
- Python dependency check: no broken requirements;
- Java runtime dependency inspection: no H2 runtime dependency;
- repository tracked-output and credential scan: passed;
- git diff --check: passed.

The unconfigured full Backend discovery reports the PostgreSQL class as
skipped by design; the explicit PostgreSQL run above was performed separately
with opt-in and had zero skips. Java Maven was run through the repository
wrapper because a system mvn binary is not installed.

## 13. Changed files

The candidate branch changes are documentation/test/candidate-harness only:

- backend/candidates/deepseek_provider_real_candidate.py;
- backend/fixtures/deepseek_provider_real_candidate_v1/cases.json;
- backend/test_deepseek_provider_real_candidate.py;
- ops/candidate/deepseek-provider/run-real-candidate.sh;
- docs/work-reports/2026-08-06-deepseek-provider-real-candidate-work-report.md;
- docs/work-reports/README.md.

No production runtime behavior, Java source, Java configuration, Alembic
migration, image publication configuration, or application version was
changed.

## 14. Commits and pull request

Candidate runner commit: 3e0d320 (test: add isolated DeepSeek real-provider
candidate runner).

The documentation/report commit and candidate PR URL will be recorded in the
final update to this report after the documentation/test-only PR is opened.

PR title: Test: Validate DeepSeek acceptance against real provider

## 15. Decision and rollout prerequisites

Decision: CONDITIONAL GO.

The API compatibility and safety portions passed, but this final ten-case
cohort produced 7 accepted results and 3 transient-connect-timeout fallbacks,
where the gate requires at least 8 accepted and no more than 2 fallback. The
result is therefore not a GO and does not authorize production modification.

Exact prerequisites before a controlled production rollout are:

1. Re-run the same ten-case candidate with the same operator-configured model
   and exact budgets after the transient network/provider condition is
   stabilized; achieve at least 8/10 complete, repaired, or partial, with no
   more than 2 fallback.
2. Preserve zero security rejection, public serialization failure, duplicate
   side effect, and call-bound violations.
3. Keep JSON Output, thinking disabled, SDK retries zero, one primary retry,
   one repair, and the three-call ceiling unchanged unless a separately
   approved experiment is run.
4. Prepare a controlled rollout with bounded monitoring for fallback reason,
   connect/read timeout, token, duration, repair, security, and narrative
   availability metadata; do not infer success from this synthetic cohort.
5. Keep a configuration-only rollback ready for the model and bounded token /
   retry settings. Do not change Java normalization, schema, or dictionary.

## 16. Risks, negative effects, and deferred work

The observed connect timeouts show that external network/provider stability
can still dominate fallback behavior even when JSON acceptance succeeds. The
one retry increases worst-case latency and token cost and can result in
duplicate billing after an ambiguous timeout. The ten-case sample is small,
synthetic, sequential, and not a production success-rate estimate. No real
repair or length-retry behavior occurred in the final cohort, so those paths
remain covered by mocks and the isolated acceptance corpus.

Strict Function Calling remains a deferred candidate experiment. Multi-call
response splitting remains deferred because it changes cost, ordering, and
semantic reconciliation. Thinking-enabled real validation was not included
in the disabled-thinking production candidate cohort.

## 17. Required confirmations

- Production was untouched; no production endpoint or production traffic was
  used.
- No production user data was used or inspected.
- Java source and configuration were unchanged.
- No Alembic migration was added or edited.
- No image was published.
- No deployment occurred.
- No tag or Release was created.
- No application version bump occurred; v2.0.6 remains provisional.
- The only external LLM call was the explicitly authorized DeepSeek candidate
  call, using bounded synthetic inputs; no other external LLM was called.
- No Provider response body or reasoning_content was stored in the report,
  repository, or candidate artifact.
