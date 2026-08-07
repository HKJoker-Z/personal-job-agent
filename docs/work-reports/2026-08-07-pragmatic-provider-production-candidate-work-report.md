# Pragmatic Provider Production Candidate Work Report

Date: 2026-08-07

Repository: `HKJoker-Z/personal-job-agent`

Remote: https://github.com/HKJoker-Z/personal-job-agent

Decision: **NO-GO for Version 2.0.6 release preparation**. The deployed
candidate completed exactly ten authorized synthetic production Analyze
executions and met the revised Provider quality observation of 7/10 accepted
results. Runtime hard-failure signals were not observed. The release gate is
nevertheless not complete because the bounded collector failed after the ten
executions while reading its temporary idempotency metadata. Consequently the
completed-replay proof and several aggregate fields were not retained. No
additional Analyze cohort was run.

Provider quality: **DEGRADED** (`7/10`, 70%). This is a quality observation,
not the reason for the NO-GO.

Evidence in this report is bounded operational metadata. No Provider body,
reasoning content, prompt, Resume, Job Description, Project Knowledge body,
user identifier, API key, Authorization value, Cookie, Session token, raw
exception text, or complete environment file was inspected or retained.

## 1. PR #58 and source disposition

PR #58:
https://github.com/HKJoker-Z/personal-job-agent/pull/58

- Final PR head: `da1ab24beb36fd20b67aba77f2c0c14f277aa2c7`
- Final head status before merge: CLEAN and MERGEABLE
- Required PR checks: passed; publication jobs were skipped by policy
- Merge method: normal merge commit
- Squash: not used
- Rebase: not used
- Admin bypass: not used
- Merge commit: `7b834dd469892d2798661dca14f2f906e7b339cf`
- Post-merge main CI: passed on the merge commit
- Post-merge Java Normalization Candidate: passed on the merge commit

PR #57 was not merged and was not cherry-picked. It remains an optional future
Provider networking experiment only. The candidate retained the current main
environment-proxy networking behavior.

## 2. Production baseline

| Property | Baseline |
|---|---|
| Stable public version | `2.0.5` |
| Production candidate source | `7b834dd469892d2798661dca14f2f906e7b339cf` |
| Alembic current/head | `20260730_07` |
| JD normalization mode | `java` |
| Java policy | `jd-normalization-v1` |
| Skill dictionary | `skills-v1` |
| Analyze route | synchronous `POST /api/analyze` |
| Provider networking | unchanged current production environment-proxy path |

Previous immutable application images:

| Component | Previous digest |
|---|---|
| Backend, Worker, Outbox | `sha256:79fac56ae0884cc5362356c2d3d3f981e681286e9214faea4b4a4c1d03255b57` |
| Frontend, Edge | `sha256:325bae0c95b8f571e6d1a5a64dff4ae3012ff71c929c15e7c47aebe4652c0996` |
| Java normalization | `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f` |

The previous application images were preserved locally under the existing
`pja-rollback/v2.0.5-*` references. A new protected rollback snapshot was
created at:

`/var/backups/personal-job-agent-v2/pragmatic-provider-candidate-20260807T131529Z`

It contains the previous production Compose files, production environment
file, and Java stage configuration with restricted permissions. Secret values
were not printed or copied into this report.

## 3. Candidate image build and publication

The reviewed manual `Release Container Images` workflow was dispatched after
verifying that `origin/main` pointed exactly to the merge commit. Workflow:

https://github.com/HKJoker-Z/personal-job-agent/actions/runs/31181100116

The workflow built only Backend and Frontend from the exact merge SHA. It did
not rebuild Java, create a Version 2.0.6 tag, or create a GitHub Release.

| Component | Candidate source-SHA tag | Candidate digest |
|---|---|---|
| Backend | `sha-7b834dd469892d2798661dca14f2f906e7b339cf` | `sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa` |
| Frontend, Edge | `sha-7b834dd469892d2798661dca14f2f906e7b339cf` | `sha256:70df317280ad5acd5e2916a0de65844b1add1bb54636cdeec1f793c8c93b174b` |

Both candidate images have OCI revision `7b834dd469892d2798661dca14f2f906e7b339cf`
and application version `2.0.5`. Backend runs as `10001:10001`; Frontend runs
as `101:101`.

Candidate validation passed:

- repository workflow validation and image publication checks;
- non-root and sensitive-path image checks;
- Backend import smoke;
- Nginx configuration smoke;
- image history secret scan;
- no configured DeepSeek, Java, PostgreSQL, or migration credential marker in
  image history or image metadata.

No local vulnerability scanner was available on the host. The bounded image
safety checks above and the repository CI/release workflow secret checks were
used; a vulnerability database scan was not claimed.

## 4. Deployment sequence

The candidate was deployed while keeping `APP_VERSION=2.0.5`. The active
production Compose anchors were changed only from the previous immutable
Backend and Frontend digests to the two candidate digests. The prior Compose
file was copied to the protected rollback snapshot first.

The sequence used `docker compose up -d --no-build --pull never --no-deps`:

1. Worker and Outbox from the candidate Backend digest;
2. Backend from the same candidate Backend digest;
3. Frontend and Edge from the candidate Frontend digest.

The deployment did not run `migrate`, `alembic`, `redis-init`, or any upgrade
or downgrade command. PostgreSQL, Redis, Java, their volumes, the private Java
network, and the existing Provider network behavior were not recreated or
modified.

The active production Compose file is outside the Git worktree at
`/opt/personal-job-agent-v2/compose.yaml`; the Git implementation/report PR
contains documentation only for this operational phase.

## 5. Production health after deployment

Bounded health verification passed:

- public health: HTTP 200, status `ok`, Version `2.0.5`;
- public readiness: ready, database ready, database schema ready, Redis ready,
  Worker ready, Project Knowledge search ready;
- Frontend/Edge HTTPS root: HTTP 200;
- Backend, Worker, Outbox, Frontend, Edge, Java, PostgreSQL, and Redis:
  healthy;
- all inspected service restart counts: zero;
- all inspected service OOM flags: false;
- public ports and Edge binding: unchanged;
- Java host port exposure: none;
- root disk after image pull/deployment: 10,480,084 KiB available;
- no migration service was recreated; the pre-existing completed migration
  container remained exited successfully.

Deployed runtime image summary:

| Service | Digest | Health | Restart | OOM |
|---|---|---|---:|---|
| Backend | `sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa` | healthy | 0 | false |
| Worker | `sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa` | healthy | 0 | false |
| Outbox | `sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa` | healthy | 0 | false |
| Frontend | `sha256:70df317280ad5acd5e2916a0de65844b1add1bb54636cdeec1f793c8c93b174b` | healthy | 0 | false |
| Edge | `sha256:70df317280ad5acd5e2916a0de65844b1add1bb54636cdeec1f793c8c93b174b` | healthy | 0 | false |
| Java | `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f` | healthy | 0 | false |
| PostgreSQL | `sha256:7c688148e5e1560d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7` | healthy | 0 | false |
| Redis | `sha256:c1e88455c85225310bbea54816e9c3f4b5295815e6dbf80c34d40afc6df28275` | healthy | 0 | false |

## 6. Controlled production cohort

Exactly ten sequential authorized Analyze executions were sent through the
deployed candidate. Inputs came only from the repository’s ten approved
synthetic fixtures. A temporary synthetic operator account was created for the
cohort and removed afterward. History saving was enabled so finalization and
cleanup could be checked without involving any existing user account.

The collector completed all ten requests and classified their public state in
memory before failing during bounded idempotency-ledger metadata collection.
No further Analyze request was started.

| State | Count |
|---|---:|
| complete | 6 |
| repaired | 0 |
| partial | 1 |
| fallback | 3 |
| Provider accepted | 7/10 (70%) |

Provider quality classification: **DEGRADED** under the approved scale.

Recovered bounded runtime observations:

- Analyze timing log rows: 10;
- retry started: 8;
- repair started: 0;
- maximum Provider calls: 2 (eight executions retried once; no repair call);
- deadline exhausted: 0;
- client disconnected: 0;
- fallback category: `provider_call_failed`, 3 observations;
- bounded log timeout marker: `connect_timeout` only; 19 bounded log-line
  references were observed across the retry/failure metadata;
- read, write, pool, remote-protocol, transport-other, and Provider-phase
  deadline categories: 0 bounded log observations;
- Provider duration median/p95/max: 7,155.324 / 8,234.822 / 8,234.822 ms;
- Analyze duration median/p95/max: 7,277.768 / 8,275.916 / 8,275.916 ms;
- all ten Analyze timing rows remained far inside the 175-second Analyze
  safety deadline.

The exact per-execution timeout-category vector was not retained because the
collector failed before emitting its final aggregate. The report therefore
does not convert the 19 log references into a false per-execution count.

Token aggregates were not retained. No Provider body or usage object was
written to disk, and the collector failed before printing the in-memory usage
aggregate. No token estimate is claimed here.

## 7. Public result and safety observations

All ten Analyze HTTP responses were HTTP 200 JSON objects with a recognized
state (`complete`, `partial`, or `fallback`). The collector reached ten
completed records without a public serialization exception or Provider-call
limit exception.

The deterministic completion path in the merged implementation supplies a
stable Job Summary and Match Reasons representation for accepted and fallback
results. The collector did not emit the final per-field boolean aggregate
before its metadata failure, so the production candidate gate records Job
Summary and Match Reasons as **not independently captured**, rather than
claiming a stronger 10/10 measurement from discarded response bodies.

Other bounded safety observations:

- hard security response: 0 observed;
- public serialization response: 0 observed;
- secret/body/reasoning marker hits in bounded Backend logs: 0;
- `history_finalized=True`: 10;
- `history_finalized=False`: 0;
- `idempotency_finalized=True`: 10;
- `idempotency_finalized=False`: 0;
- temporary synthetic-owned rows before cleanup: 23 bounded rows;
- temporary synthetic-owned rows after cleanup: 0;
- temporary synthetic user remaining: 0;
- duplicate History: none observed in bounded cleanup/finalization evidence.

The completed-replay check itself was not run. The collector failed while
looking up the first idempotency record before it could reuse the key. The
existing merged Backend idempotency regression suite and the 10/10
`idempotency_finalized` runtime observations remain green, but they do not
replace the requested production completed-replay observation.

## 8. Hard-gate evaluation

| Gate | Result |
|---|---|
| Ten Analyze executions completed | Pass |
| All ten returned bounded public JSON/state | Pass |
| All executions inside Analyze deadline | Pass |
| Provider calls never exceeded three | Pass; maximum observed 2 |
| Job Summary boolean 10/10 | Unverified; collector did not retain aggregate |
| Match Reasons boolean 10/10 | Unverified; collector did not retain aggregate |
| Severe security defect | Pass; 0 observed |
| Secret/prompt/system leakage | Pass; 0 bounded marker hits |
| Public serialization failure | Pass; 0 observed |
| Duplicate History | Pass in bounded finalization/cleanup evidence |
| Completed replay makes zero Provider calls | Unverified; replay was not run |
| Java behavior | Pass; unchanged image, mode, policy, and dictionary |
| PostgreSQL schema | Pass; `20260730_07`, no migration |
| Authentication/CSRF/Origin | Pass in synthetic setup smoke |
| Resume and History routes | Pass in synthetic candidate smoke |
| Services healthy | Pass |

The NO-GO is caused by incomplete hard-gate evidence, specifically the missing
completed replay and missing bounded aggregate output. It is not caused solely
by the three supported deterministic fallbacks or by the 70% Provider quality
observation.

## 9. Rollback status and readiness

No automatic rollback was triggered. There was no observed security,
serialization, deadline, call-limit, persistence, authentication, Java,
PostgreSQL, restart-loop, or resource hard failure. This follows the approved
policy that a bounded Provider failure with safe deterministic fallback is not
by itself a rollback condition.

The pragmatic candidate remains deployed with public Version `2.0.5`; no
Version 2.0.6 release preparation or tag was authorized. Rollback is ready
using the protected Compose snapshot and the previous immutable Backend and
Frontend digests. Rollback would recreate only Backend, Worker, Outbox,
Frontend, and Edge with the previous application images, without touching
Java, PostgreSQL, Redis, volumes, or Alembic.

## 10. Java and PostgreSQL validation

Java was not rebuilt or changed. The production Java image remains
`sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`.
Backend runtime configuration remained:

- mode `java`;
- policy `jd-normalization-v1`;
- dictionary `skills-v1`;
- Java private network unchanged;
- Java API-key mount unchanged and not inspected.

Java health remained passing. PostgreSQL remained on its pinned PostgreSQL
16.9 image, healthy, with readiness and schema readiness passing. No Alembic
revision was added, removed, upgraded, downgraded, or stamped.

## 11. Validation before and after deployment

Passed before deployment:

- PR #58 required checks;
- post-merge main CI;
- post-merge Java normalization candidate;
- reviewed candidate image validation/publication;
- image user, sensitive-path, import, Nginx, and history secret checks.

Passed after deployment:

- Backend health/readiness;
- Frontend/HTTPS availability;
- authentication login and logout path for the temporary synthetic account;
- CSRF rejection and untrusted-Origin rejection;
- Resume and History route smoke;
- Java health and Java-authoritative mode checks;
- Worker and Outbox health;
- PostgreSQL and Redis health;
- image digest and OCI revision checks;
- bounded log secret/body marker review;
- restart/OOM review;
- disk/resource review.

No destructive production test, load test, stress test, migration, or
Project-Knowledge rebuild was performed.

## 12. React Router advisory

The locked frontend state remains React `19.2.7`, React DOM `19.2.7`, and
React Router DOM `7.18.1`. The prior production audit still reports two high
React Router advisory findings (`GHSA-qwww-vcr4-c8h2`) in the locked range.
No unrelated downgrade or frontend dependency migration was mixed into this
Provider candidate. The advisory remains a separate deferred security task
to address before or immediately after Version 2.0.6 according to its actual
impact on this Vite client.

## 13. Changed files and commits

Documentation-only report PR files:

- `docs/work-reports/2026-08-07-pragmatic-provider-production-candidate-work-report.md`
- `docs/work-reports/README.md`

Operational file changed outside the repository for the candidate cutover:

- `/opt/personal-job-agent-v2/compose.yaml` — only the Backend and Frontend
  immutable image anchors changed; the previous file is in the protected
  rollback snapshot.

Source and delivery commits:

- PR #58 implementation head: `da1ab24beb36fd20b67aba77f2c0c14f277aa2c7`;
- PR #58 normal merge: `7b834dd469892d2798661dca14f2f906e7b339cf`;
- report branch: `ops/pragmatic-provider-production-candidate`;
- initial report commit: `ab213edec1db24c3253a3eb70e9d7147cf6db3b7`;
- report PR: https://github.com/HKJoker-Z/personal-job-agent/pull/59;
- report metadata commit: `88722ec00cf92979669537cb0e745891319e2bcb`;
- this finalization commit is documentation-only and is the report-branch
  follow-up to that metadata commit.

## 14. Next prerequisite and risks

Exact next prerequisite:

1. repair the bounded production candidate collector so it can emit the
   per-execution safe metadata and complete-replay result without retaining
   keys, bodies, prompts, or content; and
2. obtain explicit authorization for a fresh ten-execution candidate cohort.

The current ten-execution cohort must not be rerun or selectively repeated.
Version 2.0.6 preparation must remain blocked until the fresh authorized
cohort proves every hard gate, including completed replay with zero Provider
calls.

Accepted negative effects and risks:

- Provider quality is DEGRADED at 7/10, with three safe deterministic
  fallbacks;
- exact timeout-category and token aggregates were lost by the bounded
  collector failure;
- the candidate remains on public Version 2.0.5 but is not authorized for a
  Version 2.0.6 release;
- the React Router advisory remains deferred as a separate task;
- no automatic rollback is justified by the observed Provider fallback alone.

## 15. Scope confirmations

- Production was touched only for the explicitly authorized candidate image
  deployment and ten synthetic Analyze executions.
- No production user content was inspected.
- Only repository synthetic fixtures were used.
- No Provider response body, reasoning, prompt, Resume, Job Description,
  Project Knowledge content, token object, secret, or arbitrary exception text
  was retained or printed.
- No Alembic migration occurred; current/head remains `20260730_07`.
- Java source, image, policy, dictionary, private network, and key mount were
  unchanged.
- Provider networking, Mihomo, HTTP proxy variables, Java networking, and Job
  URL networking were unchanged.
- Version 2.0.6 was not bumped, tagged, published, or released.
- No release image, Version 2.0.6 GitHub Release, or annotated Version 2.0.6
  tag was created.

## 16. Final decision

**NO-GO — hard-gate evidence incomplete; Provider quality DEGRADED.**

The candidate is operationally healthy and the revised 7/10 quality target
was met. Release preparation remains blocked only until the collector is
repaired and a newly authorized ten-execution cohort provides the missing
completed-replay and bounded aggregate evidence.
