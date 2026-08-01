# Java Normalization Production Stage 1 Deployment Work Report

## 1. Repository

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Phase: Production Phase IVA, infrastructure-only predeployment
- Stable production version: Personal Job Agent `2.0.4`

## 2. Implementation PR merge commit

Implementation PR #36 was merged with a normal merge commit at
`35352b2cbef4f2f111c5f0bc5f60732eed7a8b33`. No squash, rebase, admin
bypass, tag, or GitHub Release was used.

## 3. Deployed source commit

The deployed Java image was built from exact merged commit
`35352b2cbef4f2f111c5f0bc5f60732eed7a8b33`. Matching local `main`,
`origin/main`, workflow `headSha`, and OCI revision label were verified.

## 4. Production deployment timestamp and timezone

- Container deployment/start: 2026-08-01 13:04:42 Asia/Shanghai (`+08:00`)
- Final acceptance snapshot: 2026-08-01 13:06:48 Asia/Shanghai (`+08:00`)

## 5. Production host preflight

The immediate read-only preflight at 2026-08-01 13:03:30 `+08:00` found:

- uptime: 4 days, 20 hours, 7 minutes;
- load: `0.57`, `0.43`, `0.40`;
- RAM: 3.6 GiB total, 2.5 GiB available;
- swap: 1.9 GiB total, 233 MiB used, 1.7 GiB available;
- root disk: 40 GiB total, 8.1 GiB available, 79% used;
- eight existing containers healthy, restart count zero, no OOM;
- only v2 Edge published a host port (`0.0.0.0:8080`);
- Docker images: 9.699 GB, 5.245 GB reported reclaimable;
- Docker build cache: 6.948 GB, 2.37 GB reported reclaimable; and
- no existing `pja-java-normalization-internal` network conflict.

This was above the reviewed 1.5 GiB RAM and 6 GiB disk stop floors. Disk was
lower than the July 29 audit, but still had over 50 times the 155.6 MB Java
image size and remained stable at 8.0 GiB after deployment. No cleanup or
prune was performed.

## 6. Production version before and after

- Before: `2.0.4`, readiness status `ready`
- After: `2.0.4`, readiness status `ready`

Database, Redis, and Worker readiness remained `ready`.

## 7. Production schema before and after

- Before: Alembic `20260724_06`
- After: Alembic `20260724_06`

Only the single `alembic_version` metadata row was read. No migration command
was run.

## 8. Java image reference

`ghcr.io/hkjoker-z/personal-job-agent-java-normalization@sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`

The local image was 155,587,520 bytes and declared UID/GID `10001:10001`.
OCI source was `https://github.com/HKJoker-Z/personal-job-agent`; OCI revision
was the deployed source commit.

## 9. Java immutable registry digest

`sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`

Workflow dispatch run `30684925264` reran Maven verify, the
normalization-only no-database smoke, and the private production Compose
config-tree probe before publishing only the application target. Publication
and immutable metadata verification passed. No migration, backend, or frontend
image was published.

## 10. Compose project

The separate stable Compose project is `pja-java-normalization`. It contains
exactly one service, `java-normalization`, and no database, migration, Redis,
Worker, frontend, backend, Nginx, fault stub, or mock provider.

## 11. Private network

`pja-java-normalization-internal` is an explicitly named internal Docker
bridge labeled:

- repository: `HKJoker-Z/personal-job-agent`;
- purpose: `private-java-normalization`; and
- owner: `pja-java-normalization`.

After all probes exited, its only attachment was the Java container. It is not
`pja-br0`, is external to Compose, and has no PostgreSQL, Redis, FastAPI,
Nginx, or other production attachment.

## 12. Port inspection

Java had `HostConfig.PortBindings={}` and `docker port` returned no mapping.
The image/container-internal port 8080 was not host-published. The existing v2
Edge remained the only host-published production port at `0.0.0.0:8080`.

## 13. Secret storage approach

The helper generated 32 cryptographically random bytes without printing the
value. The key is stored at the documented root-controlled path
`/etc/personal-job-agent/java-normalization/api-key`. Its parent is root:root
mode `0700`; the key file is UID/GID `10001` mode `0400` for the matching
non-root container UID. It is mounted read-only as the Spring config-tree
property `jd-normalization.security.api-key`.

Local Compose reported that secret long-syntax UID/GID/mode fields are ignored;
the reviewed host ownership/mode therefore supplies the actual enforcement.
The value was not printed, committed, placed in Compose, embedded in the image,
configured as a Docker environment value, exposed through health, or included
in this report. It is retained for Phase IVB review and documented rotation,
rollback retention, and later revocation.

## 14. Java profile

`SPRING_PROFILES_ACTIVE=normalization-only` was present. JVM sizing was
`-Xms64m -Xmx256m`. HTTP/HTTPS/ALL proxy variables were explicitly empty and
NO_PROXY was service-local.

## 15. Database-dependency absence

The container environment-name inspection found no JDBC URL, database user or
password, Flyway user/password, `DATABASE_URL`, Spring datasource, or Spring
Flyway configuration. It was attached to neither production data network nor
PostgreSQL. A bounded 69-line Java log scan found no JDBC, Hikari, Flyway,
PostgreSQL, or database-connection signal. Readiness did not depend on a
database.

## 16. Container user

Docker image and running-container inspection both reported
`10001:10001`. The container was non-privileged.

## 17. Read-only filesystem

`ReadonlyRootfs=true`. The only writable path was a 64 MiB
noexec/nosuid/nodev `/tmp` tmpfs. The only host file mount was the reviewed
read-only key mount.

## 18. Capabilities and no-new-privileges

`CapDrop=[ALL]`, `SecurityOpt=[no-new-privileges:true]`, and
`Privileged=false`. There was no host network or Docker socket.

## 19. CPU/memory/PID limits

- CPU: 500,000,000 NanoCPUs (0.50 CPU)
- Memory: 402,653,184 bytes (384 MiB)
- Memory+swap: 402,653,184 bytes
- PIDs: 128
- Restart: `on-failure`, maximum 3 attempts

## 20. Health and readiness

Java reached Docker health `healthy` within the bounded wait. Readiness
returned HTTP 200 with exactly the status-only `{"status":"UP"}` contract.
After all validation, health remained `healthy`, restart count was zero, and
OOM-killed was false.

## 21. Private authentication test

One ephemeral probe using only the internal network proved:

- unauthenticated normalize: HTTP 401 with stable `UNAUTHORIZED` envelope;
- authenticated normalize: HTTP 200; and
- the API key was read inside the probe from the same read-only secret path,
  not placed in a Docker command or environment value.

The ephemeral probe was removed automatically.

## 22. Request ID test

The authenticated synthetic probe supplied
`stage-iva-private-probe:0000000000000001`. The response preserved the exact
`X-Request-ID` value.

## 23. Policy/dictionary versions

- Normalization policy: `jd-normalization-v1`
- Skill dictionary: `skills-v1`

Both matched the approved candidate and FastAPI client contract.

## 24. Bounded synthetic normalize result

Twenty sequential private normalization requests completed successfully:
`20/20`. Inputs were synthetic and carried no user content. Java remained
healthy with zero restarts and no OOM afterward. No `/api/analyze` request was
made.

## 25. Java resource snapshot

After the synthetic sequence:

- memory: 185.5 MiB / 384 MiB;
- CPU: 0.17%; and
- PIDs: 30 / 128.

Java stayed below the candidate observation and all configured ceilings.

## 26. Host resource snapshot

At final acceptance:

- uptime: 4 days, 20 hours, 11 minutes;
- load: `0.47`, `0.51`, `0.45`;
- RAM: 2.3 GiB available;
- swap: unchanged at 233 MiB used, 1.7 GiB available; and
- root disk: 8.0 GiB available, 79% used.

No obvious host degradation or Java-induced swap/disk pressure was observed.

## 27. Existing production container health/restart comparison

All eight pre-existing containers retained the exact same container ID and
start timestamp across deployment:

- v2 Edge;
- v2 frontend;
- v2 backend;
- v2 outbox dispatcher;
- v2 worker;
- v2 Redis;
- v2 PostgreSQL; and
- legacy backend.

Each remained running/healthy with restart count zero and OOM-killed false.
No existing container was stopped, restarted, recreated, or network-attached.

## 28. Log and secret scan

The published image inspection/history contained no Java API key or database
secret assignment. The bounded Java runtime log scan found neither the actual
key nor the synthetic JD marker and found no database-connection signal. Logs
contained 69 bounded lines at inspection. No complete environment or secret
value was printed.

## 29. Rollback-helper validation

`rollback-check` validated the exact
`pja-java-normalization/java-normalization` target and required network removal
only after zero attachments. It made no state change and did not stop the
successful deployment. The destructive wrapper still requires the explicit
`--confirm-java-only` token. Rollback preserves the key and every existing
production item.

## 30. Stage IVA GO/NO-GO decision

**GO to separately reviewed Phase IVB planning.**

This GO means only that the Phase IVA private infrastructure acceptance gate
passed. It does not authorize automatic Phase IVB execution, FastAPI network
attachment, shadow mode, Java-authoritative mode, or a production Analyze
change.

## 31. Stop conditions encountered

None. The lower disk headroom noted during preparation remained above the
reviewed floor and showed only the expected approximately 0.1 GiB displayed
change after pulling the 155.6 MB image. No health, isolation, security,
resource, secret, version, schema, restart, OOM, or topology stop condition
occurred.

## 32. Risks and limitations

Evidence is single-host, point-in-time, synthetic, and sequential. It does not
prove high availability, long-duration stability, load capacity, FastAPI-to-
Java behavior, shadow correctness, Java-authoritative correctness, external
provider behavior, or a performance improvement. Host disk is finite and must
remain monitored without broad prune. Java retains persistence libraries in
the image even though the normalization-only profile excluded configuration,
auto-configuration, routes, connections, and health dependencies.

## 33. Exact production changes

Phase IVA created only:

- the local Java application image by the immutable registry digest;
- the labeled internal network `pja-java-normalization-internal`;
- the retained internal key at its documented root-controlled path; and
- the one-container Compose project `pja-java-normalization`.

The GHCR Java application image was published from the implementation merge
commit. No other image was published or deployed.

## 34. Exact production items not changed

FastAPI/backend, frontend, Worker, Outbox, PostgreSQL, Redis, Nginx/Edge,
legacy backend, their images/configuration/networks/volumes, `pja-br0`, Mihomo,
routing, firewall, public ports, Project Knowledge, user files, version
metadata, and database schema/data were not changed.

## 35. Rollback state

The successful Java deployment remains running and healthy. The key is
retained. Rollback was not executed because the gate passed; its exact target
and safety preconditions were validated without stopping Java.

## 36. Confirmation that FastAPI was not attached to Java

Confirmed. FastAPI remained attached only to
`personal-job-agent-v2_application` and `personal-job-agent-v2_data`. It was
not attached to `pja-java-normalization-internal` manually or through Compose.

## 37. Confirmation that Analyze did not use Java

Confirmed. FastAPI could not reach the Java-only internal network, made no Java
request, and no `/api/analyze` request was invoked during Phase IVA. User-
visible Analyze behavior remained unchanged.

## 38. Confirmation that the production database was not migrated

Confirmed. No Alembic, Flyway, schema, PostgreSQL mutation, or application
table command was run. Java had no database configuration or attachment.

## 39. Confirmation that production remained version 2.0.4

Confirmed before and after through status-only readiness: Personal Job Agent
remained `2.0.4`.

## 40. Confirmation that production schema remained 20260724_06

Confirmed before and after from only `alembic_version`: production remained
`20260724_06`. Repository source head `20260730_07` was not applied.

## 41. Confirmation that no real DeepSeek or external LLM was called

Confirmed. Validation used deterministic Java normalization only. No DeepSeek
or other external LLM endpoint was called.

## 42. Confirmation that no user data was inspected

Confirmed. No Resume, JD, History, email, user record, application table, or
user content was read. Every normalize input was synthetic.

## 43. Confirmation that no unrelated production container was restarted

Confirmed by exact container-ID/start-time comparison and zero restart counts
for all eight pre-existing containers.

## 44. Deployment report delivery

The documentation-only pull request URL, report commit, final checks, and merge
commit are recorded in final delivery metadata before merge.
