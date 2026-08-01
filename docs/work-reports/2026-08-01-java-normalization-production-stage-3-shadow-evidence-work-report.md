# Java Normalization Production Stage 3 Shadow Evidence Work Report

## 1. Shadow deployment-report PR status

Phase IVC-A deployment-report PR #42,
<https://github.com/HKJoker-Z/personal-job-agent/pull/42>, was already merged
normally as `eb23ab1d6910ce4087ca3badd1badafb2a4eba2e`. It changed only:

- `docs/work-reports/2026-08-01-java-normalization-production-stage-3-shadow-deployment-work-report.md`; and
- `docs/work-reports/README.md`.

All 18 required pull-request check contexts passed; two publication jobs were
intentionally skipped. Local `main` was already at the merge commit and was
fast-forward checked against `origin/main`. Post-merge repository CI run
`30693041781` passed.

The deployment-report PR was not recreated.

## 2. Evidence-review timestamp and timezone

The bounded evidence snapshot ended at 2026-08-01 19:05:41 Asia/Shanghai
(`+08:00`).

## 3. Production version, schema, mode, and sample rate

Readiness and the single permitted Alembic metadata query confirmed:

- public application version: exactly `2.0.4`;
- Backend readiness: `ready`;
- production Alembic: exactly `20260730_07`;
- Backend normalization mode: exactly `shadow`; and
- Shadow sample rate: exactly `1.0`.

Worker and Outbox remain configured for local execution. Java-authoritative
mode was not enabled.

## 4. Bounded observation window

The reviewed window was 2026-08-01 16:55:51 through 19:05:41
Asia/Shanghai (`+08:00`). It begins at the Phase IVC-A final acceptance
snapshot and ends at this evidence snapshot.

Only bounded structured Backend and Java log metadata was aggregated. The
review did not read request bodies, response bodies, user tables, History,
idempotency payloads, Redis values, or user content.

## 5. Analyze, sampling, and Java-call counts

The bounded Backend metadata showed:

- new user-initiated Analyze requests observed: **1**;
- deterministically sampled requests: **1**;
- Java normalize attempts: **1**;
- unique Request IDs among attempts: **1**; and
- duplicate Java attempts for a Request ID: **0**.

The Java service independently recorded one non-health normalize request, one
normalization completion, and one HTTP 200 outcome. There was therefore at
most one Java attempt for the observed request and no automatic retry.

Every eligible request actually observed in the window was sampled at rate
1.0. However, only one new request is evidenced, despite the expected 3-5
user actions, so the required minimum of three confirmed sampled production
requests is not met.

## 6. Java outcomes and fallback

For the one attempt:

| Outcome | Count |
|---|---:|
| Success | 1 |
| Connect timeout | 0 |
| Response timeout | 0 |
| Total timeout | 0 |
| Unavailable | 0 |
| Invalid JSON/schema/hash/size response | 0 |
| Unauthorized/client/server error | 0 |
| Policy mismatch | 0 |
| Dictionary mismatch | 0 |
| Other failure | 0 |

Java success was therefore 1/1 and failure was 0/1 for this very small
sample. The Shadow event's fallback flag was false, so local fallback count
was **0**. This is expected Shadow semantics: local was authoritative from the
start and was not selected as a recovery path.

There was no unsafe response-validation failure and no unexpected fallback
pattern.

## 7. Request ID correlation

The Backend Shadow event and Java normalize HTTP event had one matching
trusted Request ID. Counts were:

- matches: **1**;
- mismatches: **0**;
- Backend attempts lacking a Java correlation event: **0**; and
- Java normalize events lacking a Backend Shadow observation: **0**.

No Request ID value is included in this report.

## 8. Policy and dictionary results

The successful observation reported the expected bounded versions:

- normalization policy: `jd-normalization-v1`; and
- skill dictionary: `skills-v1`.

Policy mismatch count was **0** and dictionary mismatch count was **0**.

## 9. Observation-only second scan

The successful response underwent the Shadow observation-only second scan.
The bounded outcomes were:

- `observation_only`: **1**;
- `not_authoritative`: **0**; and
- bounded security finding count: **0**.

The second scan did not block, sanitize, or alter the authoritative Analyze
path.

## 10. Text-equality and skill-difference evidence

Hash values were computed and discarded by the application and were not
inspected, printed, or stored. Only the allowed equality boolean was observed:

- text equality `true`: **1**;
- text equality `false`: **0**; and
- text equality unavailable: **0**.

Required/preferred/mentioned skill-difference counts are **not available** in
the deployed bounded Shadow event schema. The Backend event contains no skill
IDs or difference-count fields, and Java logs contain no response skill data.
The raw Java response was deliberately not inspected to manufacture this
evidence. This is recorded as an observability limitation, not as a mismatch.

## 11. Completed replay evidence

The bounded window contained one Analyze HTTP completion and its one matching
Shadow observation. Therefore, zero completed Analyze requests without a
Shadow attempt were observable in this window, and the safely observable
completed-replay count is **0**.

Merged behavior returns a completed idempotency replay before normalization.
The passing `test_completed_shadow_replay_does_not_call_java_or_rewrite_history`
regression test confirms that a completed replay makes no additional Java or
provider call and does not rewrite History. No production idempotency payload
or History content was inspected.

## 12. Latency evidence

The Backend's end-to-end Java Shadow duration value was **74.609 ms**. For
`n=1`:

- median: **74.609 ms**;
- nearest-rank p95: **74.609 ms**;
- success count: **1**;
- failure count: **0**;
- fallback count: **0**; and
- Request ID mismatch count: **0**.

The Java service separately reported 49 ms of internal normalization time and
63 ms for its HTTP request event. These are diagnostic metadata only.

With one observation, the median and p95 collapse to the same value. They are
not representative percentile estimates, an SLA, a load test, or evidence of
a performance improvement.

## 13. Health, restart, OOM, and resource snapshot

At the evidence snapshot:

- Backend: healthy, restart count 0, OOM false, 0.17% CPU,
  129.1 MiB / 768 MiB;
- Java: healthy, restart count 0, OOM false, 0.12% CPU,
  215.8 MiB / 384 MiB;
- all nine expected running production containers: healthy;
- aggregate unexpected restart count: 0;
- aggregate OOM count: 0;
- host available RAM: 2.01 GiB;
- available swap: approximately 1.8 GiB;
- root disk available: 7.63 GiB, 80% used; and
- load averages: 0.47, 0.43, and 0.39.

The 1.5 GiB available-RAM and 6 GiB available-root-disk thresholds remained
clear.

The running container set, expected immutable images, and published-port
mapping matched the Phase IVC-A state. Only Edge published the established
host port. Java retained no host-published port and remained attached only to
`pja-java-normalization-internal`; that network still contained exactly
Backend and Java. No unexpected production container, image, port, network,
or topology change was found. The HTTPS Edge health endpoint and internal
Backend readiness were healthy.

## 14. Bounded log health and safety

Within the bounded window:

- Backend error-level log count: **0**;
- Backend warning-level log count: **2**, both confined to the existing
  provider/fallback path rather than Java normalization;
- Java error-level log count: **0**; and
- Java warning-level log count: **0**.

The one Analyze request completed with HTTP 200. Java completed successfully,
so the warning-class provider/fallback events were not caused by Java.

The inspected Shadow event had only the reviewed allowlisted metadata. The
Java normalize HTTP event had only structured timestamp, level, service,
process, message, Request ID, route, status, and duration metadata. Automated
bounded checks found:

- zero forbidden structured keys for Authorization, API key, Cookie, Session,
  Resume, JD text, normalized text, prompt, response body, or content hash;
- zero occurrences of the current private Java key value in Backend logs; and
- zero occurrences of the current private Java key value in Java logs.

No actual key, Authorization value, Cookie, Session, hash, arbitrary exception
string, Java body, or user content was printed or copied into this report.

## 15. Local authority and execution binding

The production Shadow observation recorded `normalization_source=local` and
`fallback=false`. The merged Shadow runtime returns the original local
sanitized text as the effective normalization after the observation, while
the Java result is discarded after bounded comparisons. The execution binding
is then created from that effective local choice before provider start.

Merged source and passing post-merge CI regression tests prove that Shadow:

- leaves the existing Analyze fingerprint inputs unchanged;
- sends only first-scan-approved text to Java;
- runs its second scan for observation only;
- keeps local input authoritative for Project Knowledge RAG, prompt building,
  provider input, deterministic fallback, scoring, History, result, and the
  current execution fingerprint;
- persists `local` as the normalization source when an execution binding is
  stored;
- makes at most one Java call with transport retries disabled; and
- prevents blocked first-scan input from reaching Java.

No production History or idempotency row was inspected to reach these
conclusions.

## 16. Public Analyze failure result

The one observed Analyze request completed with HTTP 200. Java had one success
and zero failures, and Backend recorded no Java normalization error. Therefore:

- user-visible Analyze failures caused by Java: **0**;
- Java-correlated HTTP 5xx outcomes: **0**; and
- Java-caused workflow error codes: **0**.

Merged Shadow failure regression coverage additionally confirms that a Java
timeout or other bounded client failure neither retries nor fails or changes
Analyze.

## 17. Rollback readiness

The installed Stage 2 and Stage 3 override files remain root-owned and
read-only. The previously approved rollback remains immediate: omit only the
Stage 3 Shadow override and recreate only Backend, yielding local mode and
sample rate zero with the same image, networks, and read-only key mount.

Rollback requires no database downgrade, Java restart or removal, History
rewrite, completed-response change, Redis operation, or recreation of another
service. It was not executed because no security, correctness, health,
resource, correlation, fallback, or leakage defect was found.

## 18. Phase IVC-B decision

**CONDITIONAL GO for Phase IVD; do not proceed yet.**

The observed call was successful and met the correlation, policy, dictionary,
response-validation, authority, fallback, public-failure, health, resource,
topology, and log-safety gates. The exact blocker to a full GO is evidence
volume: only **1** new sampled production Shadow request is confirmed, below
the required minimum of **3**.

The additional observability limitation is that deployed safe logs do not
emit required/preferred/mentioned skill-difference counts. No mismatch is
shown, but those counts cannot be reconstructed without inspecting the
prohibited Java response.

Shadow remains enabled at sample rate 1.0. This decision does not authorize or
start Phase IVD and does not enable Java-authoritative mode.

## 19. Exact actions not performed

Confirmed for this task:

- no `/api/analyze` request or other production Analyze/user-workflow traffic
  was generated; only permitted read-only health and metadata checks ran;
- no Resume, raw or sanitized JD, History, prompt, Project Knowledge content,
  provider request/response, public response body, Java request/response body,
  user table, idempotency payload, or Redis value was inspected;
- no DeepSeek or other external LLM was called by this task;
- production configuration was not changed;
- no production service was restarted;
- Java-authoritative mode was not enabled;
- Java remained private and normalization-only;
- no image was built or published;
- no database migration or downgrade ran;
- no tag, GitHub Release, or version bump was created; and
- production remains public version `2.0.4`, not `2.0.5`.

## 20. Next phase boundary

The next named phase is **Phase IVD — enable bounded Java-authoritative
production mode**. It was not started and remains blocked pending a later gate
with at least three confirmed sampled production Shadow requests.
