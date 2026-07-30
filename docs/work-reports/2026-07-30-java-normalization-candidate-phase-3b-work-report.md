# Java Normalization Candidate Phase IIIB Work Report

## 1. Repository

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Stable production version: Personal Job Agent `2.0.4`
- Candidate date: 2026-07-30
- This report covers isolated synthetic candidate validation only.

## 2. Phase IIIA PR final head

Phase IIIA PR
[#34](https://github.com/HKJoker-Z/personal-job-agent/pull/34) ended at
`b9a30f57ccc43a1c828b4f0c5d3c5c9d209021e2`. Its final head contained the
complete Phase IIIA Work Report and passed all 13 repository/Java check
contexts.

## 3. Phase IIIA merge commit

PR #34 was merged with a normal merge commit, without squash, rebase, admin
bypass, tag, release, image publication, deployment, or production access:

`29c1881a924e909f13a19cb00ce25f0f7a2a4b85`

## 4. Starting main commit

Phase IIIB started from matching local `main` and `origin/main` at
`29c1881a924e909f13a19cb00ce25f0f7a2a4b85`. Post-merge CI run
`30521552744` passed all ten jobs. The repository Alembic head was confirmed as
`20260730_07`; this source check did not imply or perform a production database
migration.

## 5. Candidate branch

`test/java-normalization-candidate-environment`

## 6. Exact scope

Phase IIIB adds an isolated Compose candidate, generated candidate-only
secrets, a candidate FastAPI evidence adapter, a minimal deterministic Java
fault stub, a bounded end-to-end runner, focused assertions, path-scoped CI,
candidate documentation, architecture status, and this Work Report.

The candidate validates the merged Phase IIIA implementation. It does not
change FastAPI or Java production runtime semantics.

## 7. Scope exclusions

The work does not modify FastAPI runtime source, Java source/POM/Dockerfile/
Compose/Flyway/policy/dictionary, React, production Compose, Nginx, release or
deployment workflows, production configuration/version metadata, or
`docs/PROJECT_KNOWLEDGE.md`. It adds no Redis, Worker, frontend, production
network, production volume, registry publication, tag, release, or deployment.

## 8. Candidate directory

The complete candidate is under:

`ops/candidate/java-normalization/`

Generated `.env.candidate`, `.candidate-secrets/`, `.candidate-results/`, and
Python cache output are ignored. The committed `.env.compose.example` contains
placeholders only.

## 9. Candidate architecture

The candidate contains one PostgreSQL 16 database, one-shot Personal Job Agent
Alembic migration, FastAPI from merged source, the real Java application in
`normalization-only`, the repository's test-only in-process mock provider, and
a candidate-only fault stub. The normal synchronous `/api/analyze` route is
used; no queue is introduced.

## 10. Compose services

The exact Compose service set is:

- `postgres`
- `migrate`
- `backend`
- `java-normalization`
- `fault-stub`

The mock provider remains the existing FastAPI test-only implementation and is
therefore not a separate container. Redis and Worker were unnecessary for this
synchronous candidate.

## 11. Network isolation

Every run uses a random project name matching
`pja-java-candidate-*`. The `data` network is internal and contains FastAPI,
Java, PostgreSQL, migration, and the fault stub as required. The separate edge
network exists only for FastAPI's loopback mapping. The candidate never joins
`pja-br0`, a production network, or an unrelated network. Java proxy variables
are empty and `NO_PROXY=*`; no Docker socket or arbitrary host directory is
mounted.

## 12. Port exposure

Only FastAPI publishes a host port, selected dynamically and bound to
`127.0.0.1`. Docker port inspection proved that Java, PostgreSQL, migration,
and the fault stub had no host-published port. FastAPI reached Java by the
private service name on the internal network.

## 13. Secret handling

`generate-secrets.sh` uses OpenSSL randomness under a mode-0700 candidate
secret directory. It creates candidate-only PostgreSQL, admin, fingerprint,
Java API-key, mock-provider, and monitoring credentials without printing
values. The backend reads its Java key from a read-only local Compose secret;
the generated environment file remains mode 0600. Values do not appear in
Compose literals, images, logs, CI artifacts, documentation, or command
summaries.

Cleanup validates exact candidate paths and never removes an unrelated
environment file.

## 14. Synthetic fixtures

The runner creates only a synthetic admin, Session, Resume, Project Knowledge
index, JD, request IDs, and Idempotency-Keys. The bounded JD representation is
a platform-engineering role with FastAPI, PostgreSQL, and Java tokens. Its role
heading contains a decomposed accent: the existing local path preserves that
representation while the Java policy deterministically applies NFC. This
produces different local and Java effective-text identities without a
first-scan finding. Raw text is never retained in evidence.

## 15. Alembic migration to 20260730_07

The one-shot migration service upgraded a fresh candidate PostgreSQL 16
database through the single repository head `20260730_07`. It verified the
execution-fingerprint column and existing ledger check constraints. No
production database endpoint was configured or contacted.

## 16. Migration no-op rerun

A second `alembic upgrade head` completed without a new operation. `alembic
heads` and `alembic current` both reported only `20260730_07`. The same no-op
upgrade also passed after the candidate PostgreSQL restart.

## 17. Java normalization-only runtime

The successful authoritative path used the real merged Java application image
with `SPRING_PROFILES_ACTIVE=normalization-only`. It started without
PostgreSQL, required the internal API key, exposed no persistence route or host
port, propagated the trusted Request ID, and returned
`jd-normalization-v1`/`skills-v1`.

It ran as UID/GID `10001`, with a read-only root, dropped capabilities,
no-new-privileges, bounded 64 MiB `/tmp`, 0.50 CPU, 384 MiB, 128 PIDs, and
`-Xms64m -Xmx256m`.

## 18. Mock provider

FastAPI ran with `APP_ENV=test` and `MOCK_PROVIDER_ENABLED=true`. A
candidate-only image adapter wrapped the existing deterministic mock boundary
to record bounded call counts and effective-input/prompt identities, and to
provide a one-shot barrier. The adapter refuses to run if the test-only mock is
disabled. No network LLM endpoint was added and no request body was stored in
candidate results.

## 19. Local-mode result

With mode `local`, FastAPI started while Java was stopped. Analyze succeeded
without a Java connection. The ledger stored source `local`, contract
`analyze-execution-v1`, policy `fastapi-local-jd-v1`, null dictionary, a
32-byte execution fingerprint, and a bound timestamp. One History row was
created. Completed replay returned the exact response and added no provider or
History side effect.

## 20. Shadow-mode result

With mode `shadow` and candidate sample rate `1`, one eligible request made
exactly one real Java call with matching Request ID. Source stayed `local`;
bounded evidence proved RAG, prompt, mock provider, result, and History remained
locally authoritative. Completed replay made no Java/provider call. Stopping
Java made the shadow observation fail safely while Analyze still succeeded.

## 21. Java-authoritative result

With mode `java`, exactly one real Java request succeeded. The ledger stored
source `java`, contract `analyze-execution-v1`, policy
`jd-normalization-v1`, dictionary `skills-v1`, and a 32-byte fingerprint.
The authoritative second scan accepted the normalized text. Analyze retained
its public request/response schema and produced one History row.

## 22. Effective-input proof

Candidate-only bounded SHA-256 identities proved that the Java effective text
differed from the local identity and that the same Java identity reached
Project Knowledge retrieval, safe-prompt construction, the mock-provider
request, and the derived stored result. Evidence includes hashes of known
synthetic values only; it records no raw JD, Resume, or execution fingerprint.

## 23. Binding-before-provider proof

The mock-provider barrier paused the request after provider entry but before
completion. While paused, the runner queried only the isolated synthetic
ledger and proved state `processing`, source `java`, contract/policy/dictionary
present, a 32-byte fingerprint, `execution_bound_at <= provider_started_at`,
and no History row. Releasing the barrier then completed Analyze and History.
This proof does not rely solely on logs.

## 24. Request ID propagation

The synthetic trusted Request ID was present in FastAPI bounded evidence and
the real Java `jd_normalization_completed` event. The Java response header
matched the request and one Java normalization completion was counted.

## 25. Java unavailable fallback

An unresolvable candidate-only Java service origin caused exactly one attempt.
Analyze remained available with `fallback_local`,
`fastapi-local-jd-v1`, null dictionary, binding before provider work, and the
local effective identity. The public response exposed no Java detail.

## 26. Java timeout fallback

The private fault stub held the response beyond the bounded client timeout.
There was no retry. Analyze completed through `fallback_local`, and downstream
identity/call-count evidence remained local and bounded.

## 27. Invalid-response/version fallback

Separate malformed-JSON and unsupported-policy cases each selected
`fallback_local` before binding. A Request-ID mismatch case did the same.
All produced available public Analyze responses and one mock-provider call,
without exposing Java bodies or arbitrary errors.

## 28. Authoritative second-scan fallback

The fault stub returned a validly hashed/versioned response containing a
synthetic credential marker. The authoritative second scan rejected it;
FastAPI selected and bound `fallback_local` before RAG/provider work. The
rejected Java text did not enter downstream evidence or the public response.

## 29. Security validation

The first scan blocked a synthetic key marker with the unchanged
`INPUT_SECURITY_BLOCKED` response before Java or provider work. Java received
only the bounded first-scan text and never received Session, Cookie, CSRF,
Origin, Resume, or browser state. Host inspection proved Java/PostgreSQL were
not public. Bounded log scanning found no synthetic JD marker or generated
secret, and public failures contained no Java body.

## 30. Java-completed replay in local mode

After completing a keyed Java-authoritative request, FastAPI was recreated in
`local`. The same stable input/key returned the exact stored response with the
replay header. Java count, provider count, History count, and historical
execution metadata did not change.

## 31. Local-completed replay in Java mode

After completing a keyed local request, FastAPI was recreated in `java`. The
same stable input/key returned the exact local stored response without a Java
call, provider call, or History rewrite.

## 32. Execution-conflict evidence

A candidate-only SQL fixture converted one isolated completed local claim into
an expired processing claim while retaining its local execution binding.
Continuation under Java returned HTTP 409 with
`IDEMPOTENCY_EXECUTION_CONFLICT`. No provider observation or duplicate History
was created. No debug endpoint or production hook was added.

## 33. Rollback to local

The primary rollback was configuration-only:

`ANALYSIS_JD_NORMALIZATION_MODE=local`

Recreating FastAPI was sufficient; no image rebuild or schema downgrade
occurred. A new request completed locally, an existing Java-completed response
remained replayable, the database stayed at `20260730_07`, and Java was stopped
independently after proof.

## 34. Restart behavior

An intentional Java restart retained health and subsequent Java-authoritative
Analyze success. Java unavailability selected fallback instead of failing
Analyze. FastAPI recreations preserved completed responses, and the final
inspection showed zero unexpected Docker restart counts.

## 35. Persistence behavior

PostgreSQL survived an ordinary candidate restart. A previously completed Java
response replayed after FastAPI switched to local, History remained unchanged,
and the Alembic rerun was a no-op. The volume was preserved until all replay,
restart, and rollback cases completed.

## 36. Health and restart counts

FastAPI readiness, Java health/readiness, PostgreSQL health, and fault-stub
health passed bounded waits. At the resource snapshot all four running
containers reported status `running`, restart count `0`, and
`oom_killed=false`. Intentional stop/start operations were limited to candidate
containers.

## 37. Resource observations

One point-in-time snapshot after 20 sequential Java-mode requests observed:

| Service | Memory | CPU | PIDs |
|---|---:|---:|---:|
| FastAPI | 112.6 MiB / 640 MiB | 0.15% | 3 |
| Java | 174.9 MiB / 384 MiB | 0.19% | 30 |
| PostgreSQL | 28.36 MiB / 384 MiB | 6.55% | 9 |
| Fault stub | 23.05 MiB / 96 MiB | 10.15% | 2 |

Total observed memory was approximately 338.91 MiB. Candidate database size
was 12,205,079 bytes (11.64 MiB). Locally built backend and Java candidate
images were 106,908,637 and 155,587,899 bytes. Java remained below its 0.50
CPU/384 MiB/128 PID ceiling; no obvious limit violation was observed.

This is a bounded synthetic snapshot, not production sizing or a load test.

## 38. Java duration median/p95

For 20 sequential successful synthetic Java-mode calls:

- median: `9.383 ms`
- p95: `20.457 ms`

These are FastAPI's candidate Java-normalization duration observations, not
production latency or an SLA.

## 39. Candidate Analyze duration median/p95

For the same 20 sequential synthetic requests:

- median: `208.188 ms`
- p95: `322.831 ms`

The sample had zero fallback and zero failure. It was deliberately sequential
and is not a stress, concurrency, capacity, or performance-improvement claim.

## 40. Test counts and skipped-test status

- Candidate runner: 14 required validation gates passed; six Java failure
  categories covered; 20/20 sequential samples completed; zero required case
  skipped.
- Backend full discovery: 495 passed; the 12 explicitly opt-in PostgreSQL tests
  were skipped only in this general discovery.
- Separate PostgreSQL 16 suite: 12 passed, zero skipped.
- Frontend: 9 files and 64 tests passed; build passed.
- Java Surefire: 67 passed, zero failed/errored/skipped.
- Java Failsafe: 46 passed, zero failed/errored/skipped.

## 41. CI result

The PR's final authoritative GitHub check rollup is recorded by the final
report-metadata commit. It includes repository CI, Java verify/full-profile/
normalization-only jobs, and the path-scoped `Java Normalization Candidate`
job. The candidate job builds locally, runs the complete synthetic matrix,
requires cleanup, uses minimum permissions and immutable checkout pinning, and
does not publish, release, or deploy.

## 42. Changed files

Candidate and CI:

- `.gitignore`
- `.github/workflows/java-normalization-candidate.yml`
- `ops/candidate/java-normalization/.env.compose.example`
- `ops/candidate/java-normalization/README.md`
- `ops/candidate/java-normalization/assertions.py`
- `ops/candidate/java-normalization/backend-candidate.Dockerfile`
- `ops/candidate/java-normalization/candidate_runtime.py`
- `ops/candidate/java-normalization/compose.yaml`
- `ops/candidate/java-normalization/fault_stub.py`
- `ops/candidate/java-normalization/generate-secrets.sh`
- `ops/candidate/java-normalization/run-candidate.sh`

Documentation:

- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/README.md`
- this Work Report

No FastAPI or Java runtime source file changed.

## 43. Commit SHAs

- `a70cd454690b286f52751d26bd8894ec9973f458` — isolated topology and
  candidate helpers.
- `a7379d8129d8347a8559d7c02fc6fdcaf3f0f2d5` — mode, fallback, replay,
  rollback, resource, and safety assertions.
- `c7d07d6eb940746cbf8edd024d6a6ed5ef7200f2` — path-scoped candidate CI.
- Documentation/report and final delivery-metadata commit SHAs are recorded in
  the final report update on this same branch.

## 44. PR URL

The candidate pull request URL is recorded in the final delivery-metadata
update on this same branch.

## 45. Go/no-go recommendation

**GO to controlled production rollout design.**

Local, shadow, and Java modes passed in the isolated candidate. Java changed
only the effective JD path; fallback preserved Analyze availability; Request
ID propagation and binding before provider were proven; replay introduced no
Java/provider/History side effect; local rollback needed no schema downgrade;
Java/PostgreSQL had no public port; no secret/JD marker leaked; no required
case was skipped; and no unexpected restart, OOM, or obvious candidate-limit
violation occurred.

This GO authorizes design of a controlled production rollout phase only. It is
not a production deployment authorization or production reliability claim.

## 46. Risks and limitations

The evidence is single-host, synthetic, sequential, and uses a deterministic
mock provider. It does not prove production latency, capacity, high
availability, exactly-once external provider execution, external provider
behavior, or long-duration stability. Java and local policy differences remain
contract-versioned behavior. Docker structured evidence is not a durable
metrics warehouse. Phase IV must retain rollback gates and production-safe
observability.

## 47. Cleanup

The runner uses `set -euo pipefail`, bounded waits, safe quoting, and an
EXIT/INT/TERM trap. It sanitizes bounded failure output and removes only the
validated unique `pja-java-candidate-*` project with its candidate network and,
because the exact `--ephemeral` flag is mandatory, its candidate volume. It
removes only its exact generated environment/key paths. It never invokes
Docker prune or an unqualified Compose teardown.

## 48. Confirmation that production was not accessed

Confirmed. Production hosts, containers, networks, databases, Redis, Nginx,
volumes, secrets, user data, and metrics were not accessed or inspected.

## 49. Confirmation that production was not migrated

Confirmed. Alembic ran only against the unique synthetic candidate PostgreSQL
database and a separately named temporary backend-test database. The
production schema remains reported as `20260724_06`; source head
`20260730_07` was not applied to production.

## 50. Confirmation that production configuration was unchanged

Confirmed. Production Compose, environment, Nginx, deployment scripts, version
metadata, and `docs/PROJECT_KNOWLEDGE.md` were unchanged.

## 51. Confirmation that no image was published

Confirmed. Validation built local disposable images only. There was no registry
login, push, or image publication.

## 52. Confirmation that no release or deployment occurred

Confirmed. No tag, GitHub release, deployment, production restart, production
migration, or production Project Knowledge synchronization occurred. The
candidate PR is not to be merged as part of this phase.

## 53. Confirmation that no real DeepSeek or external LLM was called

Confirmed. All Analyze calls used the repository's deterministic test-only
mock provider. No real DeepSeek or other external LLM endpoint or credential
was configured or called.
