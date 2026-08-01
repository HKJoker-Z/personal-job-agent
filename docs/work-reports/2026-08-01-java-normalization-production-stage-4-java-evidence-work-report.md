# Java Normalization Production Stage 4 Java Evidence Work Report

## 1. Phase IVD-A report PR status and merge commit

Phase IVD-A deployment-report PR [#46](https://github.com/HKJoker-Z/personal-job-agent/pull/46),
**Docs: Record Java-authoritative production deployment**, was already merged
normally as `d555e07470fdbf7c7085a40498f78b0c489da8b2`.

It changed only:

- `docs/work-reports/2026-08-01-java-normalization-production-stage-4-java-deployment-work-report.md`;
  and
- `docs/work-reports/README.md`.

All 18 required pull-request contexts passed, two publication jobs were
intentionally skipped, and GitHub reported CLEAN and MERGEABLE. Post-merge
main CI run `30700904641` also passed. The PR was not recreated.

## 2. Evidence-review timestamp and timezone

The bounded evidence snapshot ended at 2026-08-01 21:37:36 Asia/Shanghai
(`+08:00`).

## 3. Production version and Alembic

The immediate read-only preflight confirmed:

- application version: exactly `2.0.4`;
- production Alembic: exactly `20260730_07`; and
- public HTTPS `/healthz`: HTTP 200.

No migration or database mutation command ran.

## 4. Mode and immutable image digests

- Backend normalization mode: exactly `java`;
- Backend image:
  `sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`;
  and
- Java image:
  `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`.

Both digests matched Phase IVD-A exactly. No image was pulled, replaced,
built, or published.

## 5. Bounded observation window

The observation window was 2026-08-01 20:50:11 through 21:37:36
Asia/Shanghai (`+08:00`). It begins at the recorded Phase IVD-A Backend-only
cutover and ends at this fixed evidence snapshot.

Only allowlisted structured Backend and Java log metadata, selected runtime
configuration values, health/container/network/resource metadata, and bounded
aggregate execution-ledger/analysis-metric fields were inspected. The ledger
queries selected only counts, statuses, nullness, low-cardinality execution
versions/sources, timestamp ordering, attempt counts, and distinct History
link counts. They did not select Request IDs, user IDs, idempotency keys,
fingerprints, hashes, response bodies, or History content.

## 6. User-initiated Analyze count

The fixed window contained **4** new user-initiated Analyze requests:

- `Received analysis request` events: 4;
- POST `/api/analyze` completion events: 4;
- HTTP 200 completions: 4; and
- unique trusted request correlations: 4.

Each Analyze completion had one matching Java-authoritative execution event
and one newly created execution-ledger row. The review task generated no
Analyze request.

## 7. Java attempt, success, and fallback counts

| Outcome | Count |
|---|---:|
| Backend Java attempts | 4 |
| Java normalize HTTP attempts | 4 |
| Java normalization completions | 4 |
| Java successes | 4 |
| `fallback_local` selections | 0 |
| Java failures | 0 |

Every Backend attempt matched one Java HTTP 200 and one Java normalization-
completion event. Each correlation key occurred exactly once in each event
set, so duplicate attempt count and retry count were both zero.

## 8. Failure-category counts

All bounded Java failure categories were zero:

| Category | Count |
|---|---:|
| Connect/response/total timeout | 0 |
| DNS/connection/unavailable | 0 |
| Authentication/client/server HTTP error | 0 |
| Oversized/malformed JSON/schema/hash response | 0 |
| Request ID invalid/missing/mismatch | 0 |
| Policy mismatch | 0 |
| Dictionary mismatch | 0 |
| Authoritative second-scan error/rejection | 0 |
| Other Java failure | 0 |

No fallback reason required investigation.

## 9. Request ID result

Request ID correlation succeeded **4/4** across:

- Backend Analyze HTTP completion;
- Backend Java-authoritative execution observation;
- Java normalize HTTP completion; and
- Java normalization completion.

Mismatch count was zero. No Request ID value was printed, copied, persisted
by this review, or included in this report.

## 10. Policy and dictionary result

All four successful authoritative observations reported:

- normalization policy `jd-normalization-v1`; and
- skill dictionary `skills-v1`.

Policy mismatch count and dictionary mismatch count were both zero. The four
execution-ledger rows independently contained the same expected versions.

## 11. Authoritative second-scan result

| Authoritative second-scan outcome | Count |
|---|---:|
| Accepted | 4 |
| Rejected | 0 |
| Error/unavailable | 0 |

All four Java results passed the authoritative FastAPI second scan before they
could enter RAG or prompt construction. No Java response body or text was
inspected to reach this result.

## 12. Execution source counts

| Effective source | Structured events | Execution ledger |
|---|---:|---:|
| `java` | 4 | 4 |
| `fallback_local` | 0 | 0 |
| `local` | 0 | 0 |

Every eligible new request therefore used the Java-authoritative execution
contract. Merged runtime source and passing tests establish that the selected
effective Java text is assigned to the single downstream JD before Project
Knowledge RAG, prompt construction, provider input, scoring, derived History,
and final result work. Content fields were not compared or inspected in
production.

## 13. Execution-binding result

Bounded execution-ledger aggregates showed:

- new Analyze ledger rows: 4;
- rows with complete Java execution metadata: 4;
- execution binding present before Provider start: 4/4;
- Provider start present before completion: 4/4;
- completed rows with HTTP 200 response metadata present: 4/4;
- maximum attempt count: 1;
- execution-binding conflicts: 0; and
- failed or indeterminate ledger rows: 0.

The query tested timestamp ordering and body presence only; it did not select
or read the stored response, fingerprint, hash, key, or content.

## 14. Provider and History side-effect counts

Safely observable Provider evidence:

- primary Provider starts: 4;
- requests with exactly one primary Provider start: 4/4;
- duplicate primary Provider starts: 0;
- primary Provider outcomes: 1 accepted success, 1 bounded call failure, and
  2 bounded output rejections; and
- public Analyze completions despite those existing Provider-path outcomes:
  4/4 HTTP 200.

The three non-success Provider outcomes selected the product's existing
deterministic analysis fallback and were not caused by Java normalization.
All four analysis metrics completed as `completed_with_warnings`. This is
expected existing Provider containment, not `fallback_local`, a Java failure,
or an Analyze failure.

Safely observable result and History evidence:

- completed result rows with response metadata present: 4;
- result/error metric rows: 4/0;
- saved-to-History metrics: 4;
- non-null ledger History links: 4;
- distinct ledger History links: 4;
- matching existing History rows: 4;
- distinct metric application links: 4; and
- duplicate History links/writes: 0.

History IDs and History content were not selected or printed. The
idempotency finalizer atomically created one History row and completed one
result per execution binding.

## 15. Replay evidence

Safely observable completed replay count was **0**. Every one of the four
Analyze completions had a Java execution event and a new execution-ledger row,
so no completion returned through the pre-normalization completed-replay
path.

Production replay behavior was therefore not exercised in this window. The
merged and passing regression tests remain the evidence that a matching
completed replay makes no new Java call, Provider call, History write, or
result rewrite.

## 16. Java and Analyze latency

Backend end-to-end Java-authoritative durations were:

`11.094`, `12.363`, `12.484`, and `29.101` ms.

For `n=4`:

- Java median: **12.424 ms**; and
- nearest-rank Java p95: **29.101 ms**.

Existing safe Backend HTTP completion metadata reported end-to-end Analyze
durations of `4216.852`, `7293.992`, `7555.963`, and `7851.635` ms, with a
median of 7424.977 ms and nearest-rank p95 of 7851.635 ms.

Four requests remain a very small sample. These values are bounded rollout
evidence only, not an SLA, load test, capacity result, performance trend, or
claim of improvement. Provider latency dominates the public Analyze values;
no causal performance comparison is made.

## 17. Public Analyze failure count

- public Analyze HTTP 200: 4;
- public Analyze HTTP 5xx: 0;
- Java-correlated workflow error: 0; and
- Java-caused public Analyze failure: 0.

No Java error, internal body, or failure detail reached the public response.

## 18. Backend and Java health, restart, and OOM

At the read-only preflight snapshot:

- Backend: healthy, restart count 0, OOM false, 0.14% CPU,
  126.5 MiB / 768 MiB; and
- Java: healthy, restart count 0, OOM false, 3.78% CPU,
  219.4 MiB / 384 MiB.

All nine expected running containers were healthy with restart count zero and
OOM false. Every untouched container retained its Phase IVD-A ID. Java
retained no host-published port, remained attached only to
`pja-java-normalization-internal`, and that network still contained exactly
Backend and Java. Only Edge retained the established public port.

## 19. Host memory and disk snapshot

At 2026-08-01 21:31:27 Asia/Shanghai (`+08:00`):

- available host RAM: 2.09 GiB; and
- available root disk: 7.62 GiB.

The 1.5 GiB RAM and 6 GiB root-disk floors remained clear. No prune, cleanup,
container removal, or resource workaround was used.

## 20. Bounded safe-log result

Across the fixed window, the bounded scan reviewed:

- Backend log lines: 232, including 228 structured JSON events and four
  classified Uvicorn startup lines;
- Java structured JSON events: 291;
- Backend error-level events: 0;
- Java error-level events: 0;
- Backend warning-level events: 6; and
- Java warning-level events: 0.

The six Backend warnings were the existing Provider containment pairs: one
call failure plus its deterministic-fallback selection, and two output
rejections plus their two deterministic-fallback selections. All four
Analyze requests still completed with HTTP 200, every Java normalization
succeeded, and all four execution/History results finalized.

Automated checks found:

- forbidden structured content/secret keys: 0;
- Authorization/Bearer/API-key markers: 0;
- Cookie/Session markers: 0;
- raw/normalized text, Resume, prompt, or body markers: 0;
- 64-hex secret/hash-shaped values: 0;
- unclassified non-JSON Backend lines: 0; and
- unstructured Java lines: 0.

No log line, Request ID, arbitrary exception string, content value, hash, or
secret was printed or included in the report.

## 21. Rollback readiness

The installed Stage 2, Stage 3, and Stage 4 overrides remain root-owned and
mode `0444`. A fresh in-memory rollback render omitted Stage 4 and Stage 3
while retaining the base/safety/routing files and Stage 2. It resolved to:

- Backend mode `local`;
- Shadow sample rate `0`;
- Worker and Outbox `local`;
- unchanged Backend image;
- unchanged application/data/Java networks; and
- unchanged read-only Java key mount.

Emergency rollback remains Backend-only and requires no image change,
database downgrade, Java removal/restart, key rotation, History rewrite,
idempotency transformation, Redis operation, or other service recreation.
Rollback was not executed because every gate passed.

## 22. Phase IVD-B decision

**GO to final v2.0.5 release preparation.**

Four new Java-authoritative production Analyze requests exceed the minimum of
three. All four used source `java`, passed the authoritative second scan,
bound the expected execution before Provider work, completed with one primary
Provider start and one distinct History result, and returned HTTP 200. There
was zero Java failure, `fallback_local`, retry, Request ID mismatch, policy or
dictionary mismatch, second-scan rejection, binding conflict, duplicate
primary Provider/History side effect, Java-caused public failure, health/
resource defect, or leakage finding. Rollback remains ready.

This decision authorizes only the separately requested final release
preparation. It does not publish, tag, release, migrate, change configuration,
or change version in this task.

## 23. Blockers and limitations

There is no remaining Phase IVD-B blocker.

Documented limitations:

- `n=4` is a small controlled-rollout sample, not reliability or SLA evidence;
- no completed production replay was observed in this window, so replay
  guarantees remain supported by merged source and tests;
- the safe log schema records one primary Provider start but does not emit a
  separate low-cardinality format-repair counter; merged code and tests bound
  repair to at most one when needed; and
- downstream effective-text identity is proven by source ordering, the
  authoritative `java` execution binding, and regression tests rather than by
  inspecting prohibited production text or hashes.

None of these limitations hides a demonstrated security, correctness,
correlation, authority, duplicate-side-effect, health, resource, or rollback
defect.

## 24. Confirmation no traffic was generated by this task

Confirmed. This evidence review invoked no `/api/analyze`, Java normalize,
user workflow, production test user, or other production business request.
Only existing user-initiated events and permitted health/metadata were read.

## 25. Confirmation no user content was inspected

Confirmed. The task did not inspect Resume, raw or sanitized JD, prompt,
Provider body, Java body, public response body, History content, Project
Knowledge content, hashes, user rows, Sessions, Cookies, Authorization,
secrets, idempotency keys, or stored response bodies.

## 26. Confirmation no external LLM was called

Confirmed for this review task. It did not call DeepSeek or another external
LLM/provider. The report only counts safe metadata from Provider attempts
already caused by the user's earlier normal Analyze requests.

## 27. Confirmation no image, migration, version bump, tag, or release occurred

Confirmed:

- no image was built, pulled for replacement, published, or changed;
- no migration was added, edited, run, or downgraded;
- no configuration or service changed or restarted;
- no application version changed;
- no repository tag or GitHub Release was created; and
- production remains `2.0.4`, not `2.0.5`.

## 28. Evidence-report delivery metadata

- Branch: `docs/java-normalization-production-stage-4-java-evidence`
- Evidence-report PR: to be recorded after creation
- Implementation commit: to be recorded after creation
- Required merge method: normal merge commit; no squash, rebase, or admin
  bypass

The evidence PR changes only this Work Report and the Work Report index. It
does not start the release task.
