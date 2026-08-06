# DeepSeek Provider Real Candidate Rerun Work Report

Date: 2026-08-06
Repository: HKJoker-Z/personal-job-agent
Decision: GO for the separately authorized production-candidate phase. No
production deployment occurred in this phase.

## 1. Delivery baseline

PR #52 was requested at head
254370ae9675afd2f9f92e0ee536bcadcc143922. A later documentation-only report
finalization commit, ce79a881903ca281617ec7609e469b5eea9950e4, was present on
the clean, mergeable PR head and was included in the normal merge.

PR #52 merge commit:
47aa34434c10bc9ffd62aa9233fda6ee01bba82a.

Starting main commit for this rerun:
47aa34434c10bc9ffd62aa9233fda6ee01bba82a.

Rerun branch: test/deepseek-provider-real-candidate-rerun.

The production baseline remains v2.0.5, Alembic 20260730_07, Java JD
normalization mode java, Java policy jd-normalization-v1, and skill dictionary
skills-v1. PR #52 contained only the candidate runner, synthetic fixtures,
mock tests, and documentation. No acceptance behavior was changed for this
rerun.

## 2. Scope and isolation

One sequential ten-case cohort was run with the existing merged runner and
the unchanged synthetic fixture file. The cases cover the same bounded
technical and support-engineering roles, short and medium inputs, strong,
partial, and low matches, required and preferred skills, project/work
evidence, limited Project Knowledge, and no relevant Project Knowledge.

The runner used APP_ENV=development only so the existing operator secret
loading mechanism could be exercised. It used a disposable SQLite database,
a disposable synthetic Project Knowledge path, synthetic Request IDs and
idempotency values, and no production networks, volumes, PostgreSQL, Redis,
Session, Project Knowledge, Resume, JD, History, or /api/analyze endpoint.

## 3. Network-path preflight

The Provider base URL is the repository’s configured constant
https://api.deepseek.com. No API key was sent during preflight.

Safe preflight results:

- system clock was valid; the observed UTC clock was 2026-08-06T08:55:37Z;
- the system CA bundle was available at the standard system path;
- DNS resolution succeeded with one resolved address;
- direct TCP/TLS succeeded with TLS 1.3;
- direct unauthenticated HTTPS reached the origin and returned HTTP 401;
- the existing HTTP(S) proxy path also reached the origin and returned HTTP
  401;
- HTTP_PROXY and HTTPS_PROXY were present as the existing HTTP path;
- the inherited ALL_PROXY was an unsupported SOCKS path and was explicitly
  cleared only inside the disposable candidate process;
- NO_PROXY was present and its behavior was left unchanged;
- no proxy credential, API key, Authorization header, request body, or
  response body was printed.

The proxy decision was therefore to preserve the existing operator HTTP(S)
proxy behavior while clearing only the incompatible SOCKS ALL_PROXY in the
candidate wrapper. No production environment was changed.

## 4. Exact configuration under test

The rerun used the exact merged configuration:

- model: deepseek-v4-pro;
- response mode: json_object;
- thinking: disabled;
- primary output budget: 1600 tokens;
- length-retry budget: 2400 tokens;
- format-repair budget: 1000 tokens;
- application token maximum: 5000 tokens;
- SDK automatic retries: zero;
- at most one application-level primary retry;
- at most one format-only repair;
- absolute maximum Provider calls: three.

No model, timeout, retry count, retry backoff, token budget, thinking setting,
fixture, or acceptance rule was changed between cohorts.

## 5. Rerun results

Execution count: 10.

| Result state | Count |
|---|---:|
| complete | 4 |
| repaired | 0 |
| partial | 5 |
| fallback | 1 |
| accepted (complete + repaired + partial) | 9 |

Security rejection count: 0.

Public serialization failure count: 0.

Primary attempts: 14. Application retries: 4. Format repairs: 0. Maximum
Provider calls observed: 2.

Failure and parsing categories:

- transient retries: connect_timeout=4;
- fallback reason: provider_call_failed=1;
- HTTP 429: 0;
- HTTP 5xx: 0;
- read timeout: 0;
- empty content: 0;
- finish_reason=length: 0;
- finish_reason=stop: 9; other: 1;
- parse outcomes: canonical=9; invalid=1;
- salvage: evidence_reference_cleanup=5.

The single fallback followed two bounded Provider attempts and was caused by
the same transient connect-timeout category. It was not caused by JSON Output
incompatibility, security rejection, public serialization, or an exceeded
call bound.

## 6. Tokens and latency

Token observations are aggregate metadata only; no content was retained.

| Metric | Minimum | Maximum | Total |
|---|---:|---:|---:|
| input tokens | 0 | 837 | 7,327 |
| output tokens | 0 | 382 | 2,649 |
| total tokens | 0 | 1,205 | 9,976 |

Provider duration median/p95: 6,179.883 ms / 9,683.196 ms.

End-to-end candidate duration median/p95: 6,186.418 ms / 9,706.978 ms.

No monetary cost was calculated because the Provider response did not supply
an authoritative cost field. The one allowed retry remains a possible source
of increased latency, token use, and duplicate billing after an ambiguous
timeout.

## 7. Public result narratives and correctness

Job Summary was present in 10/10 results; explicit unavailable count was 0.
Match Reasons was present in 10/10 results; explicit unavailable count was 0.

All ten records passed the public Analyze serialization check. Accepted
partial records retained Provider-derived analysis and used only bounded
local evidence cleanup or deterministic completion. The single fallback used
the existing deterministic fallback path. No severe output-security finding
was converted into partial.

The mock candidate, Provider, and idempotency/History tests passed. The
idempotency tests confirmed completed replay performs no new Provider or
History side effect, and History finalization remains at most once.

## 8. Security and log safety

The runner’s safe-log inspection passed. Logs contained only bounded model,
attempt, category, token, response-length, and duration metadata. No Resume,
JD, Project Knowledge, prompt, Provider response, reasoning_content, API key,
Authorization header, arbitrary exception string, or actual content hash was
stored or reported.

The real runner screened Provider output before any repair decision and kept
the existing severe-security rejection boundary. No security rejection or
secret/body leakage occurred.

## 9. Regression validation

Local validation on the rerun branch:

- focused candidate, Provider, and idempotency/History tests: 48 passed;
- full Backend suite: 515 passed, with 12 PostgreSQL tests skipped because
  the suite is opt-in without PostgreSQL;
- PostgreSQL integration: 12 passed, 0 skipped, in a disposable PostgreSQL
  16.9 container;
- Frontend suite: 9 files and 70 tests passed;
- Frontend production build: passed;
- Java Maven verify: 46 tests passed, 0 failures, 0 errors, 0 skipped;
- Java normalization-only container smoke: passed;
- Java full-profile container smoke: passed;
- git diff --check: passed;
- tracked-output check: passed;
- repository secret scan: passed;
- disposable PostgreSQL and candidate-container cleanup: passed.

The first disposable PostgreSQL command used a temporary database name that
did not contain the repository-required word test and was rejected before
schema setup. That container was removed; the corrected final run passed all
12 tests with zero skips. No application code or migration was touched.

## 10. Commits and pull request

PR #52 merge commit:
47aa34434c10bc9ffd62aa9233fda6ee01bba82a.

Rerun documentation commit and candidate PR URL will be finalized in this
report before the rerun PR is merged. The rerun PR title is:
Test: Revalidate DeepSeek provider acceptance.

## 11. Decision and exact next prerequisite

Decision: GO.

The ten valid executions produced 9 accepted results and 1 bounded transient
fallback, meeting the gate of at least 8 accepted results and no more than 2
fallbacks. Security rejection, public serialization failure, body/secret
leakage, duplicate side effect, and call-bound violations were all zero.

This GO authorizes only the next separately controlled production-candidate
phase. It does not deploy production in this task. The exact prerequisite is
to keep v2.0.5 and the current Java, migration, model, token, thinking, retry,
and acceptance configuration unchanged while performing a bounded staged
production-candidate deployment with monitoring for state, fallback reason,
timeouts, tokens, latency, security, narrative availability, idempotency, and
History. Maintain configuration-only rollback and stop on any safety or
correctness regression.

## 12. Required confirmations

- Production was untouched; production /api/analyze was not called.
- No production user data was used or inspected.
- Java source and configuration were unchanged.
- No Alembic migration was added or edited.
- No image was published.
- No deployment occurred.
- No tag or Release was created.
- No application version bump occurred; production remains v2.0.5.
- No external LLM other than the explicitly authorized DeepSeek candidate was
  called, and all inputs were synthetic.
