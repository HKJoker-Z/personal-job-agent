# Java Normalization Production Stage 3 Shadow Deployment Work Report

## 1. Phase IVB report PR status

Phase IVB deployment-report PR #40,
<https://github.com/HKJoker-Z/personal-job-agent/pull/40>, was already merged
normally as `739ad80ba31cc1143768f1f8baba0cb530d5e399`. Its diff contained only the
Phase IVB deployment report and Work Report index. Post-merge repository CI
run `30690813943` passed.

## 2. Preparation PR and merge commit

Phase IVC-A preparation PR #41,
<https://github.com/HKJoker-Z/personal-job-agent/pull/41>, was merged with a
normal merge commit at `b12f207874b94685d53e7def26c76f55c57cd849`.

The final report-only head passed 18 check contexts with zero failures and two
intentional pull-request publication skips. GitHub reported CLEAN and
MERGEABLE. Post-merge repository CI run `30692395665` passed before production
mutation. No squash, rebase, admin bypass, tag, release, image publication, or
deployment occurred before merge.

## 3. Deployment timestamp and timezone

- Immediate production preflight: 2026-08-01 16:49:48 Asia/Shanghai (`+08:00`)
- Backend-only cutover start: 2026-08-01 16:51:43 `+08:00`
- Backend healthy after cutover: 2026-08-01 16:51:51 `+08:00`
- Final bounded acceptance check: 2026-08-01 16:55:51 `+08:00`

## 4. Preflight

The immediate read-only gate confirmed:

- public version exactly `2.0.4`;
- production Alembic exactly `20260730_07`;
- Backend image exactly
  `sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`;
- Java image exactly
  `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`;
- Backend mode `local` and Shadow sample rate `0`;
- Backend, Java, every v2 container, and the legacy Backend healthy with
  restart count zero and OOM-killed false;
- Java attached only to the internal Java network, with no host port;
- FastAPI the only Python service attached to that network;
- only v2 Edge published `0.0.0.0:8080`;
- 3.6 GiB total RAM and 2.1 GiB available;
- 1.9 GiB swap, 122 MiB used and 1.8 GiB available;
- 40 GiB root disk, 7.7 GiB available, 80% used; and
- load averages `0.25`, `0.37`, and `0.43`.

Java used 213.5 MiB / 384 MiB at preflight. A bounded 374-event Java log
window since the Phase IVB acceptance snapshot contained only HTTP 200
`/actuator/health/**` events, zero non-health routes, and no key value. No
cleanup or prune was used to pass the gate.

## 5. Exact configuration change

The reviewed
`compose.java-normalization-stage-3-shadow.override.yaml` was installed at
`/opt/personal-job-agent-v2/compose.java-normalization-stage-3-shadow.override.yaml`
as root:root mode `0444`. Source and installed SHA-256 both were
`403a39fa2a390163947cea08a1049a3fdac6dae921e9e69ed402766317ba2754`.

The exact production Phase IVB and Phase IVC-A renders were compared after
normalizing the reviewed Shadow fields. The remaining Compose documents were
identical. Only FastAPI Backend environment changed:

- mode `local` to `shadow`;
- deterministic sample rate `0` to `1.0`;
- connect timeout explicit at 200 ms;
- response timeout explicit at 600 ms;
- total deadline explicit at 800 ms;
- maximum response explicit at 262144 bytes;
- expected policy explicit at `jd-normalization-v1`; and
- expected dictionary explicit at `skills-v1`.

The private origin, key-file path/mount, networks, image, command, limits,
healthcheck, and public ports remained unchanged. The cutover recreated only
`personal-job-agent-v2-backend-1` with `--no-deps --wait`.

## 6. Backend mode and sample rate

Runtime inspection confirmed exactly:

- `ANALYSIS_JD_NORMALIZATION_MODE=shadow`; and
- `JD_NORMALIZATION_SHADOW_SAMPLE_RATE=1.0`.

Worker and Outbox remained explicitly `local`. The 1.0 setting makes every
later user-initiated, non-replayed Analyze deterministically eligible for one
observation-only Java attempt. It does not make Java authoritative.

## 7. Backend and Java health/restart/OOM

After cutover and after a bounded stabilization interval:

- Backend: healthy, restart count 0, OOM false;
- Java: healthy, restart count 0, OOM false;
- Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, and the legacy
  Backend: healthy, restart count 0, OOM false.

Backend retained the same immutable image digest. Java retained exact
container ID `4dc71ee56b7f24c4c2d33f4a06e9587b1b9d68043278fa9053ad241d34d5d1dd`
and its Phase IVA immutable image.

## 8. Production version and schema

- Public/readiness version after cutover: `2.0.4`
- Backend readiness status: `ready`
- Public `/healthz`: HTTP 200
- Production Alembic after cutover: `20260730_07`
- Repository Alembic head: `20260730_07`

No migration or database command was run in Phase IVC-A.

## 9. Network and port isolation

FastAPI Backend remained attached to
`personal-job-agent-v2_application`, `personal-job-agent-v2_data`, and
`pja-java-normalization-internal`. Java remained attached only to
`pja-java-normalization-internal`. That internal network contained exactly the
Backend and Java containers.

Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, and the legacy Backend
did not join the Java network. Java `HostConfig.PortBindings` remained empty.
Only Edge retained the existing public `0.0.0.0:8080` binding. No port,
network, Nginx, firewall, routing, Mihomo, or `pja-br0` change occurred.

## 10. Secret handling

The existing key stayed at the root-controlled documented host path and was
not rotated or modified. Backend retained one read-only bind at
`/run/pja-secrets/java-normalization-api-key`; runtime inspection reported
`RW=false`. The key remained absent from Compose literals and container
environment values.

The actual value matched neither bounded Backend nor Java logs. No API key,
Authorization value, database credential, complete environment, or secret
content was printed or placed in this report.

## 11. Proof no Analyze was generated by this task

No `/api/analyze` request, production user Session, or production test user was
used. The bounded Backend log window beginning at cutover contained zero
`/api/analyze`, received-analysis, or Shadow-observation signals. The matching
Java window contained only 24 periodic HTTP 200 readiness events and zero
normalize/non-health route.

Consequently no Shadow observation existed at the acceptance snapshot. The
deployment is left running for later user-initiated Analyze requests; this
task did not manufacture production traffic.

## 12. Safe observation design

Merged source plus the passing configuration, client, Shadow integration, and
idempotency test modules verify:

- the local sanitized JD remains authoritative for the execution fingerprint,
  RAG, prompt, History, provider input, result, and public response;
- Shadow failure, timeout, HTTP/authentication error, invalid body, size/hash/
  version mismatch, Request ID mismatch, or second-scan result cannot fail or
  alter Analyze;
- at most one Java attempt is made, with no transport retry, redirect, or
  inherited proxy;
- the trusted FastAPI Request ID is forwarded and the response contract must
  preserve it;
- the only Shadow event fields are bounded mode/source, attempted/sampled,
  stable outcome, duration, equality boolean, bounded finding count, expected
  versions, fallback false, observation-only scan outcome, and Request ID;
- raw or sanitized JD, Resume, prompt, response, History, hash values, API key,
  Authorization, Java body, and arbitrary exception text are not logged; and
- a valid completed idempotency replay bypasses Java and preserves the stored
  response and History.

No production content was required to validate these invariants.

## 13. Rollback render

The rollback render omitted only the final Shadow override and retained every
Phase IVB production file. It resolved to:

- Backend mode `local`;
- Shadow sample rate `0`;
- unchanged Backend image digest;
- Worker and Outbox `local`;
- unchanged Backend application/data/Java networks; and
- unchanged read-only Java key mount.

A Compose `--dry-run` targeted only Backend recreation. Exact Backend ID was
unchanged before/after the dry-run, proving no state mutation. Actual rollback
would require no image change, schema downgrade, Java restart/removal, History
transformation, completed-response rewrite, Redis change, or other service
recreation. Rollback was not executed because Shadow was healthy.

## 14. Exact production changes

Phase IVC-A made only two production changes:

1. installed the reviewed root-owned, read-only Shadow override; and
2. recreated FastAPI Backend on the same immutable image with Shadow mode and
   sample rate 1.0.

The old Backend container ID
`52448af68ebf61d0d6aa95f090a0985ef6293ec65ea7d380ba59d1f62d7c3589`
was replaced by
`0f1446d9b44ac4dd24718cef089eb922de17279adf55a706f2a64cb57c569531`.

## 15. Exact items not changed

Phase IVC-A did not change any image digest, application source, application
version, Alembic source or production schema, PostgreSQL container/data/
volume, Redis container/data, Worker, Outbox, Frontend behavior/image/
container, Edge/Nginx, Java image/runtime/profile/project/policy/dictionary,
Java key, Project Knowledge, user data, public port, TLS, firewall, routing,
Mihomo, `pja-br0`, or legacy Backend.

All eight containers outside FastAPI retained their exact preflight IDs,
images, health, restart/OOM state, and port bindings.

## 16. Current disk and memory evidence

At 2026-08-01 16:54:30 `+08:00`:

- host available RAM: 2.1 GiB;
- swap: 122 MiB used, 1.8 GiB available;
- root disk: 7.7 GiB available, 80% used;
- load averages: `0.39`, `0.42`, and `0.43`;
- Backend: 110.2 MiB / 768 MiB;
- Java: 213.6 MiB / 384 MiB;
- Worker: normally 155.6 MiB / 768 MiB; and
- Outbox: normally 74.15 MiB / 256 MiB.

A point sample caught the unchanged Worker near one configured CPU and Outbox
at 25% CPU. Three bounded follow-ups showed Worker 0.32%, 0.73%, then another
short 99.48% interval, with host load remaining below 0.5 and memory returning
to 155.6 MiB. The cause was not investigated because Worker was unchanged,
the burst stayed within its one-CPU ceiling, and it did not correlate with
Backend or Java pressure. Backend remained 0.13-0.16% CPU and Java 0.10-0.11%
in the follow-ups. No configured limit or host resource stop condition
occurred.

## 17. Stage IVC-A decision

**CONDITIONAL GO pending user-initiated Shadow traffic.**

Deployment, startup, configuration, authority/fallback design, health,
topology, port, secret, resource, no-generated-Analyze, and rollback gates all
passed. GO cannot yet be issued because this task was prohibited from invoking
Analyze and therefore collected no sampled production Shadow observation.

Required user action: run 3-5 normal Analyze requests with non-sensitive test
data, then request Phase IVC-B evidence review.

Shadow remains running. This decision does not authorize Java-authoritative
mode or Phase IVD.

## 18. Confirmation Java-authoritative mode was not enabled

Confirmed. Backend runtime mode is exactly `shadow`; Worker and Outbox remain
`local`. No `java` mode was configured or activated, and local output remains
authoritative.

## 19. Confirmation no user content was inspected

Confirmed. No Resume, JD, History, prompt, response, Project Knowledge
content, user row, application row, Session, email, Redis value, or other user
content was read. Only configuration names/approved values, health, topology,
container metadata, safe resource counters, Alembic metadata, and bounded log
field/route counts were inspected.

## 20. Confirmation no external LLM was called

Confirmed. This task did not invoke `/api/analyze`, DeepSeek, or another
external LLM or provider endpoint.

## 21. Confirmation no tag, release, image publication, or version bump occurred

Confirmed. No Backend, Frontend, or Java image was published. The existing
immutable images remained deployed. No mutable production tag, repository
tag, GitHub Release, or version `2.0.5` bump occurred.
