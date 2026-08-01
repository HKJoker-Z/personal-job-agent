# Java Normalization Production Stage 4 Java Deployment Work Report

## 1. Preparation PR and merge commit

Phase IVD-A preparation PR [#45](https://github.com/HKJoker-Z/personal-job-agent/pull/45),
**Ops: Prepare Java-authoritative production stage**, was merged with a normal
merge commit at `47e5075965dd4fcfb60520d9ee41981ca40fc41b`.

Its final pull-request head passed 18 required check contexts with zero
failures and two intentional publication skips. GitHub reported CLEAN and
MERGEABLE. There was no squash, rebase, admin bypass, image publication, tag,
release, or production mutation before merge. Post-merge main CI run
`30700249912` passed before the production preflight.

The production source checkout was fast-forwarded to the reviewed merge
commit. The merged change consists only of the Stage 4 Compose override,
production-render regression coverage, rollout documentation, preparation
Work Report, and Work Report index.

## 2. Deployment timestamp and timezone

- Immediate production preflight: 2026-08-01 20:48:38 Asia/Shanghai (`+08:00`)
- Backend-only cutover start: 2026-08-01 20:50:11 `+08:00`
- Backend healthy after cutover: 2026-08-01 20:50:18 `+08:00`
- Initial post-cutover snapshot: 2026-08-01 20:51:14 `+08:00`
- Stabilized acceptance and rollback dry-run: 2026-08-01 20:52:26 `+08:00`

## 3. Immediate production preflight

The bounded read-only gate passed before service mutation:

- public application version: exactly `2.0.4`;
- production Alembic: exactly `20260730_07`;
- Backend runtime mode: exactly `shadow`;
- Shadow sample rate: exactly `1.0`;
- Backend image: exact approved digest;
- Java image: exact approved digest;
- all nine expected running containers: healthy, restart count zero, OOM
  false;
- Java: no host-published port and only the private Java network;
- private network membership: exactly FastAPI Backend and Java;
- Backend: exactly the application, data, and Java networks;
- only Edge: existing `0.0.0.0:8080` host binding;
- public HTTPS `/healthz`: HTTP 200;
- host available RAM: 2.14 GiB;
- available root disk: 7.62 GiB; and
- no unexpected container, image, port, or network state.

The RAM and disk gates remained above 1.5 GiB and 6 GiB. No prune, cleanup,
container removal, image deletion, service restart, or configuration change
was used to pass preflight.

An automated bounded scan examined 149 recent Backend and Java log lines for
forbidden Authorization/Bearer, Cookie, Session, API-key, raw/normalized text,
Resume, prompt, request/response body, and content-hash labels. It found zero
leakage markers and printed no log line, Request ID, environment, secret, or
content value.

## 4. Exact mode change

The merged asset
`compose.java-normalization-stage-4-java.override.yaml` was installed at:

`/opt/personal-job-agent-v2/compose.java-normalization-stage-4-java.override.yaml`

Installed metadata and integrity:

- owner/group: `root:root`;
- mode: `0444`; and
- source/installed SHA-256:
  `9aa960d1c5487ab17c1feed914881c27311036eedfa14c3985b7ffee8b4b3343`.

The exact existing production base, safety, routing, Stage 2, and Stage 3
files were retained, and Stage 4 was appended last. In-memory Compose render
comparison proved the entire Java document equals the running Shadow
document after removing one field. The only semantic change is FastAPI
Backend:

`ANALYSIS_JD_NORMALIZATION_MODE=shadow -> java`

Stage 3 continues to provide sample rate 1.0, reviewed deadlines, response
ceiling, policy, and dictionary values. Stage 2 continues to provide the
private origin, read-only key file, immutable image, Backend-only private
network, and explicit Worker/Outbox local modes.

Only `personal-job-agent-v2-backend-1` was recreated with `--no-deps --wait`.
It became healthy in approximately seven seconds. Worker and Outbox remained
running in `local` mode.

## 5. Unchanged image digests

- Backend before and after:
  `sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`
- Java before and after:
  `sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`

No Backend, Frontend, Edge, Java, Worker, Outbox, PostgreSQL, Redis, or legacy
Backend image was pulled, built, published, retagged, or changed.

## 6. Production version and Alembic

After cutover:

- application version: exactly `2.0.4`;
- production Alembic: exactly `20260730_07`;
- public HTTPS health: HTTP 200; and
- Backend mode: exactly `java`.

No migration command, schema change, database downgrade, or version bump ran.

## 7. Backend and Java health, restart, and OOM

The initial and stabilized acceptance snapshots both confirmed:

- Backend: healthy, restart count 0, OOM false;
- Java: healthy, restart count 0, OOM false; and
- Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, and the legacy
  Backend: healthy, restart count 0, OOM false.

Backend point-in-time usage was 0.14% CPU and 109.6 MiB / 768 MiB. Java was
3.83% CPU and 219.1 MiB / 384 MiB immediately after Backend startup. These are
short diagnostic samples, not capacity, latency, or SLA evidence.

## 8. Private network and port isolation

After cutover:

- Backend networks remained `personal-job-agent-v2_application`,
  `personal-job-agent-v2_data`, and
  `pja-java-normalization-internal`;
- Java remained attached only to `pja-java-normalization-internal`;
- that private network contained exactly Backend and Java;
- Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, and the legacy
  Backend did not join it;
- Java retained zero host-published ports; and
- only Edge retained `0.0.0.0:8080`.

No Nginx, TLS, firewall, routing, Mihomo, `pja-br0`, DNS, host-port, or Docker
network change occurred.

## 9. Secret handling and safe logs

The existing root-controlled Java key was neither read nor modified. Backend
retained exactly one read-only mount at
`/run/pja-secrets/java-normalization-api-key`; runtime inspection confirmed
the documented host source and `RW=false`. Backend had the key-file path and
no literal `JD_NORMALIZATION_API_KEY` environment variable. The Stage 4 file
contains no key, Authorization value, secret mount, URL, or credential.

The post-cutover bounded window contained 28 Backend/Java log lines. The same
automated forbidden-marker scan returned zero findings. No actual API key,
Authorization, Cookie, Session, environment, Request ID, exception body,
request body, response body, hash, or user content was printed, copied, or
placed in this report.

## 10. Java-authoritative success and fallback contract

Merged source and passing tests confirm:

- a valid Java result becomes the selected effective JD with source `java`;
- the first local preprocessing and security scan always run before Java;
- DNS, connection, timeout, HTTP/authentication, oversize, JSON/schema/hash,
  Request ID, policy, dictionary, and bounded client failures select the
  existing local candidate with source `fallback_local`;
- a fallback is selected before binding and never overwrites a different
  already-bound Java execution;
- Java messages and bodies remain hidden from the public response;
- a Java boundary failure does not itself fail public Analyze; and
- the client makes exactly one Java attempt with transport retries zero, no
  application retry, no redirect, no inherited proxy, and bounded total time.

Phase IVD-A did not invoke Analyze to manufacture success or fallback
evidence. Those production outcomes remain for Phase IVD-B.

## 11. Authoritative second-scan contract

In Java mode, a successful normalized result passes the second FastAPI
security scan before it can enter RAG or prompt construction. Accepted text
becomes authoritative and its safe findings merge conservatively with the
first scan. A blocked, blank, errored, or otherwise unusable second-scan result
cannot become effective; FastAPI selects `fallback_local` instead.

This differs intentionally from Shadow, where the second scan was
observation-only. The authoritative behavior is verified by
`test_java_authoritative_normalization.py` and the complete required CI suite;
no production Java body or user content was inspected.

## 12. Execution-binding and replay contract

Merged runtime order selects one effective normalization and computes its
domain-separated `analyze-execution-v1` fingerprint, then atomically binds
source `java` or `fallback_local` to the current attempt token before Project
Knowledge retrieval, prompt construction, provider work, scoring, derived
History, or finalization.

Provider start and finalization require that exact binding. An unfinished
same-key source/content/version conflict is rejected rather than silently
switching authority. Matching completed idempotency rows replay their stored
result before Java/provider work and do not rewrite History.

The targeted local tests and required GitHub checks passed coverage for Java
success, Java failure bound as `fallback_local`, second-scan rejection,
binding before provider work, immutable execution choice, completed local
replay in Java mode, completed Java replay in local mode, and completed Shadow
replay without another Java/provider/History side effect.

## 13. Proof this task generated no Analyze traffic

This task made only bounded local/public health checks and read-only metadata
queries. It did not call `/api/analyze`, create a production test user, use a
production Session, or invoke a user workflow.

The bounded deployment window from 20:50:11 through 20:52:26 contained:

- `/api/analyze` log signals: 0; and
- Java normalize-route signals: 0.

The task therefore created no Analyze or Java-normalize traffic. Java mode is
left running so later normal user-initiated requests can provide evidence.

## 14. Emergency rollback render

The emergency rollback render omitted both Stage 4 and Stage 3 while retaining
the exact base/safety/routing files and Stage 2. It resolved to:

- Backend mode `local`;
- Shadow sample rate `0`;
- Worker and Outbox `local`;
- unchanged Backend image digest;
- unchanged application/data/Java networks; and
- unchanged read-only key mount.

A Compose `--dry-run up -d --no-deps backend` targeted only Backend under that
local render. Backend and Java IDs were unchanged before and after the dry-run,
confirming no actual rollback or service mutation occurred.

If a stop condition appears, emergency rollback recreates only Backend in
local mode. It requires no image change, database downgrade, Java removal or
restart, key rotation, History rewrite, completed-response change,
idempotency transformation, Redis operation, or other service recreation.

Rollback was not executed because every deployment gate passed.

## 15. Exact production changes

Phase IVD-A made exactly two production changes:

1. installed the reviewed root-owned, read-only Stage 4 override; and
2. recreated only FastAPI Backend on the same immutable image in mode `java`.

Backend container ID changed from
`0f1446d9b44ac4dd24718cef089eb922de17279adf55a706f2a64cb57c569531`
to
`5a9159f894d9497a9b35e25175fa16870ad9cbc5645234cc1ae4bb0589873870`.

## 16. Exact items not changed

The following container IDs remained exactly unchanged:

- Java:
  `4dc71ee56b7f24c4c2d33f4a06e9587b1b9d68043278fa9053ad241d34d5d1dd`;
- Worker:
  `a6d2f4c9859b560af7ad9dab0d312185584d0a043ffcdd3957be11a0968e6fcd`;
- Outbox:
  `b506660652caf0abda80015f11c9656cc9af1619b51117df882d39ec24c83243`;
- PostgreSQL:
  `2e5a6750ad7ccdd22c5c15fc81769606ed71e3cff2751cd5a617f61a2b206fbc`;
- Redis:
  `76981d04ffa5ad854e41a1ce543ef868ff43f6a879e3c4a75af8e7ab8f6ea68b`;
- Frontend:
  `3e7830f76613a72e64d92ea522a8fa80951bcea15726036b3bb590d7b9948b05`;
- Edge/Nginx:
  `6140b6bfc86f0b43aedc6181f226d8797ebe3f7018f7505bd86f2280e1fddb17`;
  and
- legacy Backend:
  `8739ba4c9e27a51b2f2387262ac74aa614cbb1aa11dd91a8c8cf461eddc37da1`.

No application or Java source, migration, schema, data, volume, image,
service command, resource limit, timeout, expected version, Java policy or
dictionary, key, Project Knowledge, Nginx, public port, TLS, firewall,
routing, Worker/Outbox behavior, Frontend, PostgreSQL, Redis, user data, or
release metadata changed.

## 17. Disk and memory snapshot

At preflight and initial acceptance:

- available RAM: 2.14-2.15 GiB;
- available root disk: 7.62 GiB;
- Backend memory: 109.6 MiB / 768 MiB; and
- Java memory: 219.1 MiB / 384 MiB.

The required resource floors remained clear. There was no OOM, restart,
container cleanup, image prune, or resource workaround.

## 18. Phase IVD-A decision

**CONDITIONAL GO pending user-initiated Java-authoritative evidence.**

Java mode is deployed and the configuration, version, schema, image, health,
restart/OOM, resource, public-health, security, secret, topology, isolation,
authoritative/fallback, second-scan, execution-binding, replay, one-attempt/no-
retry, no-generated-traffic, and rollback gates all passed.

No Java-authoritative Analyze occurred during the deployment window because
this task was prohibited from generating traffic. Phase IVD-B is not started.
The required next action is for the user to run 3-5 normal Analyze requests
with non-sensitive test data and then request the separate evidence review.

## 19. Confirmation no user content was inspected

Confirmed. No Resume, raw or sanitized JD, prompt, History, Project Knowledge
content, provider request/response, Java request/response body, public Analyze
body, hash, Session, Cookie, Authorization, secret value, user row,
idempotency payload, or Redis value was inspected.

Only approved configuration names/values, immutable digests, health/status,
container IDs, networks, ports, mount metadata, resource counters, Alembic
metadata, and aggregate bounded log-safety counts were reviewed.

## 20. Confirmation no external LLM was called

Confirmed. This task did not call DeepSeek or another external LLM/provider.
No `/api/analyze` request was invoked by the task.

## 21. Confirmation no image, migration, tag, release, or version bump occurred

Confirmed:

- no image was built, published, pulled for replacement, or changed;
- no migration was added, edited, run, or downgraded;
- no database schema or data transformation occurred;
- no repository tag or GitHub Release was created; and
- production remains version `2.0.4`; no `2.0.5` bump occurred.

## 22. Delivery metadata

- Branch: `docs/java-normalization-production-stage-4-java-report`
- Deployment-report PR: to be recorded after creation
- Report implementation commit: to be recorded after creation
- Required merge method: normal merge commit; no squash, rebase, or admin
  bypass

The documentation PR changes only this deployment report and the Work Report
index. Java mode remains running while checks and normal merge complete.
