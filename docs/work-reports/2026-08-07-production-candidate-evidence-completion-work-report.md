# Production Candidate Evidence Completion Work Report

Date: 2026-08-08

Repository: `HKJoker-Z/personal-job-agent`

Remote: https://github.com/HKJoker-Z/personal-job-agent

Decision: **GO for Version 2.0.6 Release Preparation**.

This report completes the three deterministic hard gates that were not
retained by the previous bounded collector.  It carries forward the valid
ten-execution Provider evidence; it does not create a new Provider-quality
cohort.  The one supplemental execution used a supported deterministic
fallback.  That result state is permitted by the gate and does not change the
carried-forward Provider quality classification.

## 1. Previous production-candidate report

Previous report:
`docs/work-reports/2026-08-07-pragmatic-provider-production-candidate-work-report.md`

The previous report recorded a NO-GO only because the collector failed after
all ten Analyze requests had completed.  The application and Provider quality
were not the cause of that NO-GO.

## 2. Evidence carried forward

The following evidence remains valid and was not discarded or rerun:

| Observation | Carried-forward result |
|---|---:|
| Authorized synthetic Analyze executions | 10/10 |
| HTTP 200 public JSON | 10/10 |
| Complete / repaired / partial / fallback | 6 / 0 / 1 / 3 |
| Provider accepted | 7/10 |
| Provider quality | **DEGRADED** |
| Maximum Provider calls | 2 |
| Deadline exhausted | 0 |
| Maximum Analyze duration | approximately 8.276 seconds |
| Severe security defect | 0 |
| Serialization failure | 0 |
| `history_finalized=True` | 10/10 |
| `idempotency_finalized=True` | 10/10 |
| Duplicate History | none observed |

Java, PostgreSQL schema, and all application services were healthy and
unchanged in that cohort.  Provider acceptance and fallback percentage were
not reevaluated in this phase.

## 3. Previous collector failure root cause

The failing operation was the bounded post-execution lookup of temporary
Analyze idempotency metadata before attempting a replay.  The collector
expected one user-scoped `analyze_idempotency_records` row for operation
`analyze:v1`, with a completed status and its bounded History linkage.  It had
not retained the caller-owned idempotency key and instead attempted to
rediscover or reconstruct the temporary key/record from PostgreSQL metadata.
That lookup did not produce usable metadata and the collector treated the
optional observation failure as terminal.

The failure happened only after all ten Analyze requests had returned because
the collector kept the request observations in memory and deferred the
idempotency lookup and final aggregate write until the end of the cohort.  The
ten `/api/analyze` executions, public responses, finalization, and cleanup had
already completed; the observation harness failed while reading its temporary
metadata.  No `/api/analyze` defect is inferred.  The previous run did not
retain arbitrary exception text, so this report does not invent a more
specific database exception than the documented lookup failure class.

## 4. Collector correction

The operations-only collector is now at:
`ops/candidate/pragmatic_provider/collector.py`.

The corrected flow is:

1. Generate a safe caller-owned key before the first request.
2. Send the synthetic fixture with that key.
3. Immediately capture only bounded response, timing, Provider-call, and
   finalization fields in an in-memory record.
4. Verify PostgreSQL only through status, finalization, and bounded History
   counts using the hash of the already-owned key.  The key is never
   rediscovered from PostgreSQL.
5. Send the identical fixture with the exact same key.
6. Prove replay recognition and Provider-call delta using the replay header and
   request-correlated safe log metadata.
7. Write the bounded result even when a later optional metadata lookup fails.

The collector does not retain Resume, Job Description, Prompt, Provider body,
reasoning, API key, Authorization, Cookie, Session, Project Knowledge content,
or raw exception strings.  Each execution record contains only the bounded
fields required by the gate, plus a bounded failure category.

During the supplemental run, Docker exposed the relevant container log stream
on the stream descriptor the first observer version did not read.  That caused
one false first-request log cross-check category (`provider_call_observation_mismatch`)
without changing the request, database, or public evidence.  The observer was
corrected to stream and filter only request-correlated safe log metadata.  A
post-run bounded correlation of the already-existing request IDs confirmed
two first-request Provider-start events and zero replay Provider-start events.
No additional Analyze request was made for that correction.

## 5. Why a full ten-case rerun was not required

The previous ten executions already proved the Provider cohort, runtime
deadline, call ceiling, public serialization, security, Java, PostgreSQL, and
service-health gates.  The missing items were deterministic properties of one
completed idempotent request: two stable public narrative-field booleans and
one completed replay with no new Provider call or persistence side effect.
One approved synthetic fixture is sufficient to complete those properties.
Repeating the ten cases would have reevaluated Provider quality and violated
the bounded evidence-completion scope.

## 6. Current production candidate state

The candidate was checked immediately before the supplemental request and
again after cleanup.  It was unchanged.

| Property | Verified value |
|---|---|
| Source revision | `7b834dd469892d2798661dca14f2f906e7b339cf` |
| Backend / Worker / Outbox digest | `sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa` |
| Frontend / Edge digest | `sha256:70df317280ad5acd5e2916a0de65844b1add1bb54636cdeec1f793c8c93b174b` |
| Java digest | `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f` |
| Public Version | `2.0.5` |
| Alembic current/head | `20260730_07` |
| JD normalization mode | `java` |
| Java policy | `jd-normalization-v1` |
| Skill dictionary | `skills-v1` |

Backend, Worker, Outbox, Frontend, Edge, Java, PostgreSQL, and Redis were
healthy.  The checked application services had zero restart counts and false
OOM flags.  Public health and readiness were HTTP 200/ready with Version
`2.0.5`.

## 7. Offline collector tests

`ops/candidate/pragmatic_provider/test_collector.py` contains 12 deterministic
tests.  They passed with:

```text
python3 -m unittest -v ops.candidate.pragmatic_provider.test_collector
Ran 12 tests ... OK
```

Coverage includes:

- successful Analyze followed by completed replay;
- exact reuse of the caller-owned key and identical fixture;
- zero mocked Provider calls added by replay;
- no duplicate History and the same History record;
- Job Summary and Match Reasons present-or-explicit-unavailable booleans;
- missing optional metadata, token metadata, and timeout aggregate;
- partial aggregate failure without erasing hard-gate fields;
- safe bounded evidence writing after optional failure;
- no secret, request content, or Provider content in logs.

No automated test made a real HTTP or DeepSeek call.

## 8. Supplemental production execution

Exactly one new approved synthetic fixture and one temporary synthetic
operator were used.  History saving was enabled and Project Knowledge was
disabled for this isolated request.  The collector sent one first Analyze
request and one immediately completed replay with the exact same caller-owned
key.

| Gate field | Result |
|---|---|
| Supplemental execution count | 1 first request + 1 replay |
| First result state | `fallback` |
| First HTTP/public result | HTTP 200, bounded JSON, recognized state |
| Inside authoritative deadline | `true` |
| Job Summary present-or-explicit-unavailable | `true` |
| Match Reasons present-or-explicit-unavailable | `true` |
| First-request Provider calls | 2 |
| First History finalized exactly once | `true` |
| First idempotency finalized | `true` |
| Security defect | `false` |
| Serialization defect | `false` |
| First Analyze duration | 6322.5 ms authoritative timing; 6385.297 ms client elapsed |
| Replay recognized | `true`; `Idempotency-Replayed: true` |
| Replay result | completed; same bounded public semantics |
| Replay Provider call delta | 0 |
| Duplicate History | `false` |
| Same History record | `true` |
| Replay duration | 17.876 ms request-correlated HTTP timing |

The fallback result was not used to reevaluate Provider quality and was not a
NO-GO condition.  The first Provider count came from the bounded public
completion metadata and matched the repaired request-correlated log count of
2.  The replay request had no Provider-start log event.

## 9. Cleanup

The temporary synthetic operator was logged out and removed through the
collector's exact-user scoped cleanup.  The cleanup verified zero remaining
rows for:

- `users`;
- `application_records`;
- `analysis_metrics`;
- `analysis_step_metrics`;
- `analyze_idempotency_records`.

No existing user row or user-owned content was inspected or modified.

## 10. Production health and hard-gate decision

The previous Provider quality classification is carried forward as
**DEGRADED (7/10 accepted)**.  Provider success/fallback percentage was not
reevaluated and is not a hard gate in this phase.

No new deadline violation, Provider call-bound violation, security leakage,
serialization failure, broken completed replay, duplicate persistence,
authentication regression, Java regression, PostgreSQL/schema regression, or
unhealthy application state was observed.

**GO — Version 2.0.6 Release Preparation.**

Exact next prerequisite: begin the separately scoped `v2.0.6 Release
Preparation` phase using this carried-forward candidate evidence and the
completed deterministic hard-gate evidence.  This phase did not bump the
version, tag, publish, or release Version 2.0.6.

## 11. Delivery and scope confirmations

- Branch: `fix/production-candidate-collector`.
- Collector and tests are operations-only; no runtime Provider behavior was
  changed.
- No Provider networking, Mihomo, timeout, retry, fallback, prompt, or
  Provider-acceptance code was changed.
- Java source, image, mode, policy, and dictionary were unchanged.
- No Alembic migration was added or run; current/head remained
  `20260730_07`.
- No production user content was inspected.
- No Provider response body, reasoning content, Prompt, Resume, Job
  Description, Project Knowledge content, API key, Authorization, Cookie,
  Session, or raw exception string was retained in evidence.
- Version 2.0.6 was not tagged, published, or released.
- The production candidate was not redeployed for collector validation.
- PR: pending final push and check completion.

## 12. Risks

- Provider quality remains **DEGRADED** at the carried-forward 7/10
  observation and should be considered in the next release-preparation review.
- The supplemental fixture itself used deterministic fallback, although all
  hard correctness and safety gates passed.
- The React Router advisory recorded by the previous report remains a separate
  deferred security task.
- This evidence proves the requested bounded hard gates; it is not a load,
  stress, concurrency, or external exactly-once claim.
