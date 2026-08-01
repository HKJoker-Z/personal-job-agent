# Java Normalization Production Stage 2 Local Backend Deployment Work Report

## 1. Stage IVA report PR status

Stage IVA report-delivery PR #38,
<https://github.com/HKJoker-Z/personal-job-agent/pull/38>, was already merged
normally as `603ec9cf609cb02a2f9f10dc92aff0ce2cd10ce7` at
2026-08-01 14:09:37 Asia/Shanghai (`+08:00`). It was not recreated.

The starting Phase IVA service remained the separate
`pja-java-normalization` Compose project on
`pja-java-normalization-internal`, using Java image digest
`sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`.

## 2. Preparation PR and merge commit

Phase IVB preparation PR #39,
<https://github.com/HKJoker-Z/personal-job-agent/pull/39>, was merged with a
normal merge commit at `bbd896b52e04a03dbadec7c3cd16c2ae60827d4f`.
The final PR head was clean and mergeable. Its 18 required contexts passed;
the two publish jobs correctly skipped for the pull-request event. Repository
post-merge CI run `30689341780` passed all ten jobs.

No squash, rebase, admin bypass, tag, GitHub Release, production mutation, or
deployment occurred before the preparation PR merged.

## 3. Deployed source commit and Python image digest

- Deployed source: `bbd896b52e04a03dbadec7c3cd16c2ae60827d4f`
- Image: `ghcr.io/hkjoker-z/personal-job-agent-backend@sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`
- Previous production Python digest:
  `sha256:305f1151c572be4745cf909eb7389c7566e6b15c5fe4ec7b7021ef1d069e906d`

Manual publication workflow run `30689575804` targeted `main` only after
verifying that `main` resolved exactly to the preparation merge commit. The
run passed the complete Backend suite, PostgreSQL 16 integration suite, and
local-mode production asset validation before publishing only the Backend
application image. OCI source was
`https://github.com/HKJoker-Z/personal-job-agent`, OCI revision was the exact
deployed source commit, OCI version was `2.0.4`, and image user was
`10001:10001`.

No mutable production tag, Frontend image, Java image, migration-only image,
repository tag, or GitHub Release was produced.

## 4. Deployment timestamp and timezone

- Immediate preflight: 2026-08-01 15:25:44 Asia/Shanghai (`+08:00`)
- Backup manifest: 2026-08-01 15:28:48 Asia/Shanghai (`+08:00`)
- Production migration window began: 2026-08-01 15:39:30 `+08:00`
- Backend cutover completed: 2026-08-01 15:41:25 `+08:00`
- Final bounded Java-log window ended: 2026-08-01 15:47:40 `+08:00`

## 5. Immediate preflight

The approved read-only helper confirmed the required starting boundary:

- Personal Job Agent version `2.0.4`;
- production Alembic `20260724_06`;
- Java healthy, private, restart count zero, OOM-killed false;
- all v2 production containers and the legacy Backend healthy, restart count
  zero, OOM-killed false;
- 3.6 GiB host RAM total and 2.2 GiB available;
- 1.9 GiB swap total, 233 MiB used, and 1.7 GiB available;
- 40 GiB root disk, 8.0 GiB available, 79% used;
- load averages `0.28`, `0.33`, and `0.38`;
- Java at 203.8 MiB / 384 MiB with no limit breach;
- only v2 Edge host-published `0.0.0.0:8080`; and
- no conflicting network, container name, volume, or port state.

The gate exceeded the 1.5 GiB available-RAM and 6 GiB available-root-disk
floors. No Docker cleanup or prune was used. Exact pre-existing container IDs,
images, start times, health, restart/OOM state, networks, and port bindings
were recorded before mutation without printing environment values.

## 6. Backup path policy, size, and checksum

The existing production `backup` profile created exactly one timestamped,
nonempty backup at:

`/var/backups/personal-job-agent-v2/v2-production/v2-20260801-072847-030590ef`

Its four files totaled 481,849 bytes:

- `postgres.dump`: 295,289 bytes;
- `manifest.json`: 153,221 bytes;
- `PROJECT_KNOWLEDGE.md`: 33,284 bytes; and
- `files.tar.gz`: 55 bytes.

The PostgreSQL custom archive SHA-256 was
`78c9db710d7e08cd7951d583af1b15a54e29c84bb86d7e9f261751dd00bc514c`;
the manifest SHA-256 was
`43320187cb6121266749b7a5cf3b85515a2a283dd618da9b361e4d3a125427bb`.
The manifest recorded application `2.0.4`, Alembic `20260724_06`, PostgreSQL
server/client major 16, server 16.9, and immutable PostgreSQL server and
backup-tool digests. The guarded verify command passed.

The first invocation refused before writing a backup because the installed
legacy production Compose did not supply the newer helper's immutable
`POSTGRES_SERVER_IMAGE` evidence field. The retry supplied only the exact
immutable image metadata already verified from the running PostgreSQL and
backup-tool containers. It did not override a compatibility result or weaken
the helper. No duplicate backup was created.

## 7. Isolated restore result

The exact backup restored successfully to unique project
`pja-pg16-restore-1785569590-3128855` and database
`pja_restore_target_test_1785569590_3128855` on PostgreSQL 16.9. The target
used only an internal Docker network, a new temporary volume, no host port,
and empty private file targets. It was not attached to any production network.

The target was proven empty before restore. The guarded restore validated the
backup checksums, PostgreSQL major, target identity, volume/project labels,
archive inventory, and explicit owner/database-name mappings. It then reported
`Restore completed and verified.`

The first restore attempt refused before altering the empty target because the
new image did not match the immutable restore-tool digest recorded by the
backup. Restoration was correctly rerun with that exact recorded tool digest;
the newly reviewed image was then used for the migration rehearsal. This
preserved the strict tool-image gate. After evidence capture, only the unique
temporary container, internal network, volume, restored-file targets, and
synthetic environment were removed. The production backup was preserved.

## 8. Rehearsal migration result

The isolated restored database first reported Alembic `20260724_06`. The new
reviewed Backend image reported exactly one repository head,
`20260730_07`, and applied only:

`20260724_06 -> 20260730_07, add Analyze execution fingerprint binding`

The restored target then reported `20260730_07 (head)`. Metadata-only checks
found all six nullable execution-binding columns and all four generated check
constraints with the reviewed fingerprint-size, source-domain,
nonblank-values, and metadata-consistency definitions. A second
`alembic upgrade head` emitted no upgrade transition and left the target at
`20260730_07`.

No restored application row or user content was queried.

## 9. Production migration result

The reviewed one-shot `migrate` service ran with the immutable new Backend
digest and no dependencies recreated. It reported one repository head and the
single production transition:

`20260724_06 -> 20260730_07, add Analyze execution fingerprint binding`

Metadata-only verification found the six nullable columns and four reviewed
constraints. A second one-shot upgrade was a no-op. No `stamp`, `--fake`,
downgrade, migration edit, or history rewrite was used.

## 10. Alembic before and after

- Before backup and migration: `20260724_06`
- Isolated restored copy before rehearsal: `20260724_06`
- Isolated restored copy after rehearsal: `20260730_07`
- Production after migration and cutover: `20260730_07`
- Repository/runtime head agreement: exactly one head at `20260730_07`

The migration was additive. Legacy execution-binding fields remain nullable.

## 11. Deployed Python services

The established production Compose stack and all six existing safety/cutover
overrides were retained. The reviewed Phase IVB override was installed
root:root mode `0444`; its separate image-reference environment file was
installed root:root mode `0600`.

The safe cutover order recreated only:

1. `personal-job-agent-v2-worker-1`;
2. `personal-job-agent-v2-outbox-dispatcher-1`; and
3. `personal-job-agent-v2-backend-1`.

All three resolved to image ID/digest
`sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`.
The one-shot migrate and backup profile also render to that digest. PostgreSQL,
Redis, Frontend, Edge/Nginx, Java, and the legacy Backend were not recreated.

## 12. Local-mode configuration

Rendered Compose and exact runtime environment-name/value checks confirmed:

`ANALYSIS_JD_NORMALIZATION_MODE=local`

on Backend, Worker, and Outbox. No `shadow` or `java` mode was enabled and the
shadow sample rate remained zero. Source and passing test evidence confirm
that local mode returns before Java normalization and that application startup
does not construct `JavaNormalizationClient` or store one in application
state.

No `/api/analyze` request was invoked to create evidence.

## 13. Java network attachment

FastAPI Backend retained its required
`personal-job-agent-v2_application` and `personal-job-agent-v2_data`
attachments and additionally joined `pja-java-normalization-internal`.

The internal Java network contained exactly:

- `pja-java-normalization-java-normalization-1`; and
- `personal-job-agent-v2-backend-1`.

Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, and the legacy Backend
did not join it. Java remained attached only to this internal network and had
no host-published port.

## 14. Secret handling without values

The existing Java key was preserved at the documented root-controlled path
`/etc/personal-job-agent/java-normalization/api-key`. It remained UID/GID
`10001:10001`, mode `0400`, beneath its root-only parent. Only FastAPI Backend
received a read-only bind at
`/run/pja-secrets/java-normalization-api-key`; `RW=false` was verified.

The key was not rotated, printed, copied into Compose, placed in an environment
value, committed, embedded in the image, or included in this report. Runtime
inspection confirmed no literal `JD_NORMALIZATION_API_KEY` environment value.
The actual value matched neither bounded Python logs nor bounded Java logs.

## 15. Proof that no Java normalization request occurred

The bounded Java log window from 2026-08-01 15:39:30 through 15:47:40
`+08:00` contained 49 JSON log events. Every event was the Java container's
existing Docker readiness probe: route `/actuator/health/**`, status 200.
There were zero normalize routes, normalization events, non-health routes,
database signals, or key-value matches. The bounded window SHA-256 was
`0e0f26e44f39e040e3adf43aada2f245b187226f96acb05ab9f250ee2b4695fd`.

The readiness filter generates a fresh Java-local request ID for each periodic
health probe; these were not propagated FastAPI/Analyze request IDs. No
Backend-provided Java Request ID appeared. Bounded Backend, Worker, and Outbox
logs had zero Java normalize-route/request signal. No production Analyze call
was issued.

## 16. Health, restart, and OOM results

After cutover and again after a bounded stabilization wait:

- Backend: healthy, restart 0, OOM false;
- Worker: healthy, restart 0, OOM false;
- Outbox: healthy, restart 0, OOM false;
- PostgreSQL: healthy, restart 0, OOM false;
- Redis: healthy, restart 0, OOM false;
- Frontend: healthy, restart 0, OOM false;
- Edge/Nginx: healthy, restart 0, OOM false;
- Java: healthy, restart 0, OOM false; and
- legacy Backend: healthy, restart 0, OOM false.

Backend readiness was `ready`; the health payload version was `2.0.4`.
Public `/healthz` returned HTTP 200.

## 17. Production port comparison

Before and after Phase IVB, only v2 Edge published
`0.0.0.0:8080 -> 8080/tcp`. Backend, Worker, Outbox, PostgreSQL, Redis,
Frontend, Java, and the legacy Backend had no host port binding. No Nginx,
firewall, routing, Mihomo, or `pja-br0` change was made.

## 18. Java health and resource result

The Phase IVA Java container retained exact container ID
`4dc71ee56b7f24c4c2d33f4a06e9587b1b9d68043278fa9053ad241d34d5d1dd`
and the unchanged immutable digest
`sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`.
It remained normalization-only, healthy, restart count zero, OOM false, and
private.

The post-cutover point-in-time snapshot was 0.11% CPU, 211.6 MiB / 384 MiB,
and 30 PIDs. Java stayed below its memory ceiling.

## 19. Existing production container comparison

Unchanged containers retained exact preflight IDs, images, and port bindings:

- PostgreSQL ID `2e5a6750ad7c...`, image
  `sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7`;
- Redis ID `76981d04ffa5...`, image
  `sha256:c1e88455c85225310bbea54816e9c3f4b5295815e6dbf80c34d40afc6df28275`;
- Frontend ID `3e7830f76613...` and Edge ID `6140b6bfc86f...`, image
  `sha256:09e80b4d51f1069458fe8c4a55ef3b2796789e1191fd9f8fa43c77288d45ebd9`;
- Java ID `4dc71ee56b7f...`; and
- legacy Backend ID `8739ba4c9e27...`, image
  `sha256:127b7ef1bcdbb317d67cab118774ddad0ba17f943ecdb8f7e425d35e260141a7`.

Only Backend, Worker, and Outbox changed IDs as explicitly planned. Their old
common digest was recorded and their new common digest was verified. No
unchanged container was stopped, restarted, or recreated.

At 2026-08-01 15:42:54 `+08:00`, the host had 2.1 GiB available RAM, 1.8 GiB
available swap, 7.7 GiB available root disk, and load averages `0.32`, `0.54`,
and `0.54`. Backend used 111.4 MiB, Worker 152.7 MiB, Outbox 70.55 MiB,
PostgreSQL 40.97 MiB, and Redis 4.801 MiB in the bounded snapshot. There was no
resource stop condition or obvious degradation.

## 20. Rollback validation

Before cutover, the old Backend container remained healthy with restart zero
and OOM false after production reached the additive `20260730_07` schema.
This directly demonstrated old-image schema compatibility.

A no-change rollback render resolved Backend, Worker, and Outbox to the
recorded previous digest
`sha256:305f1151c572be4745cf909eb7389c7566e6b15c5fe4ec7b7021ef1d069e906d`
with mode still explicitly `local`. The image remains locally available.
Rollback would recreate only those three Python services, would not downgrade
the database, and would leave Java, its private network, and its key
independently available. No History, idempotency, or user-data transformation
is required because the migration is additive and nullable.

Rollback was not executed because the deployment remained healthy.

## 21. Exact production changes

Phase IVB made only these production changes:

- pulled the reviewed immutable Backend image;
- created and retained one timestamped verified PostgreSQL backup;
- installed the reviewed root-owned Phase IVB Compose override;
- installed the root-owned mode `0600` Backend image-reference environment
  file;
- migrated PostgreSQL metadata from `20260724_06` to `20260730_07`;
- recreated Backend, Worker, and Outbox on the reviewed digest with explicit
  local mode; and
- attached only FastAPI Backend to the existing Java private network with the
  existing key mounted read-only.

The temporary isolated restore project and all of its temporary resources were
removed after rehearsal evidence was captured.

## 22. Exact items not changed

Phase IVB did not change the application version, Frontend image or behavior,
Java image/runtime/profile/project, Redis data, PostgreSQL container/image or
volume, Frontend container, Edge/Nginx container/configuration, legacy
Backend, public ports, TLS, firewall, routing, Mihomo, `pja-br0`, Project
Knowledge, user files, Java key value, Java normalization policy/dictionary,
Alembic revision source, Java source, or FastAPI public Analyze contract.

Java remained private. No production database downgrade occurred or is needed.

## 23. Phase IVB GO/NO-GO

**GO to separately reviewed Phase IVC planning.**

Backup, strict verification, isolated restore, rehearsal migration,
idempotent second upgrade, production migration, service cutover, local-mode
configuration, health, topology, no-normalize-request, resource, secret,
schema, port, and rollback gates all passed. No blocking stop condition
remained. This decision does not authorize shadow mode or automatically start
Phase IVC.

## 24. Risks and limitations

Evidence is point-in-time and single-host. No production Analyze request was
made, so this phase deliberately does not provide live Analyze-output or
external-provider evidence. No shadow comparison, Java-authoritative behavior,
load test, long-duration soak, or performance claim is included. The no-Java-
call conclusion is based on explicit local mode, passing lifecycle/runtime
tests, topology, and bounded logs; periodic Java readiness traffic continues
independently and produces Java-local request IDs.

Root disk fell from 8.0 GiB available at preflight to 7.7 GiB after image pull,
backup, and cutover, while remaining above the reviewed 6 GiB stop floor. It
requires continued ordinary monitoring without broad prune. The backup helper
and restore helper both demonstrated strict fail-closed image-metadata gates;
their legacy/new image metadata coordination should remain documented for
future restoration.

## 25. Confirmation production version remained 2.0.4

Confirmed before mutation and after cutover through the status-only readiness
contract. The new image OCI version was also `2.0.4`. No application version
bump occurred.

## 26. Confirmation production schema became 20260730_07

Confirmed from the single `alembic_version` metadata row, repository head,
one-shot migration output, six new nullable columns, four constraints, and the
idempotent second upgrade. Production ended at exactly `20260730_07`.

## 27. Confirmation shadow/java modes were not enabled

Confirmed. Backend, Worker, and Outbox each had exactly one runtime setting
`ANALYSIS_JD_NORMALIZATION_MODE=local`. Neither `shadow` nor `java` mode was
configured or activated.

## 28. Confirmation `/api/analyze` was not invoked

Confirmed. Validation used readiness, health, startup, schema metadata,
topology, configuration, image, resource, and bounded log evidence only. No
production `/api/analyze` request was sent.

## 29. Confirmation no user content was inspected

Confirmed. No Resume, JD, History, email, application row, user row, Redis
value, Project Knowledge content, or other user content was read. Backup and
restore validation used checksums, structural inventory, ownership/schema
metadata, and Alembic metadata only.

## 30. Confirmation no external LLM was called

Confirmed. No DeepSeek or other external LLM endpoint was called. No Analyze
or provider request was made.

## 31. Confirmation no tag or GitHub Release was created

Confirmed. The publication workflow publishes only the immutable Backend
commit-SHA tag and registry digest. No repository tag, mutable production tag,
or GitHub Release was created during Phase IVB.
