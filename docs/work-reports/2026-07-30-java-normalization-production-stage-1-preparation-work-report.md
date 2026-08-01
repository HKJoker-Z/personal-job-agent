# Java Normalization Production Stage 1 Preparation Work Report

## 1. Repository

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Stable production version: Personal Job Agent `2.0.4`
- Production Alembic revision: `20260724_06`
- Repository Alembic head: `20260730_07`

## 2. Candidate PR final head

PR #35 ended at `cf903bf6810ad5350cad281e4ea8d3c273a1f938`. Its final head
contained the complete candidate Work Report.

## 3. Candidate PR merge commit

PR #35 was merged with a normal merge commit at
`e476eb2224f23d2a0f11cc7d552d27e0acb715b3`, without squash, rebase, admin
bypass, tag, release, image publication, deployment, or production runtime
change.

## 4. Starting main commit

Phase IVA preparation started from matching local `main` and `origin/main` at
`e476eb2224f23d2a0f11cc7d552d27e0acb715b3`. Post-merge repository CI and the
complete isolated Java candidate both passed. Source head `20260730_07` was
confirmed without applying it to production.

## 5. Implementation branch

`ops/java-normalization-production-stage-1`

## 6. Exact scope

This change adds one Java application image publication/validation workflow,
one separate stateless production Compose project, a stable external private
network contract, bounded deployment/removal helpers, an operations runbook,
an architecture status update, this report, and the Work Report index entry.

## 7. Scope exclusions

It does not modify FastAPI runtime source, Java runtime source, the Java POM,
Flyway, normalization policy/dictionary, React, Alembic, Redis, Worker,
Outbox, Nginx, the current production Compose project, production version,
production database, or `docs/PROJECT_KNOWLEDGE.md`.

## 8. Read-only preflight design

The helper collects bounded time/uptime, memory, disk, Docker status/stats/disk
usage, selected health/restart/OOM/image/port metadata, networks, status-only
version, and only the `alembic_version` metadata row. It enforces seven healthy
v2 containers with zero restarts/OOM, version `2.0.4`, schema `20260724_06`, at
least 1.5 GiB available RAM, and at least 6 GiB available root disk. It never
prints environments or reads application/user tables.

The preparation-time read-only snapshot on 2026-08-01 Asia/Shanghai found 2.5
GiB available RAM, 1.7 GiB available swap, load `0.26/0.33/0.34`, and 8.1 GiB
available root disk at 79% use. All eight existing containers, including the
legacy backend, were healthy with restart count zero and no OOM. Only Edge
published `0.0.0.0:8080`. Production reported `2.0.4` and `20260724_06`. The
lower disk headroom than the July 29 audit is an explicit recheck/stop risk;
no cleanup was performed.

## 9. Java image workflow

`.github/workflows/java-normalization-production.yml` runs Maven `verify`, the
existing normalization-only no-database smoke, Compose/script/static safety
validation, and secret/dependency checks. Manual dispatch after merge publishes
only Dockerfile target `application` to GHCR. It uses minimum job permissions
and immutable third-party action SHAs.

## 10. Image tags and digest policy

The registry is
`ghcr.io/hkjoker-z/personal-job-agent-java-normalization`. Publication uses
only `sha-<full-github-sha>`. OCI source and revision labels identify the exact
reviewed commit. Production must use `IMAGE@sha256:<digest>`; no mutable tag,
repository tag, GitHub Release, migration image, backend image, or frontend
image is produced.

## 11. Compose project

`compose.java-normalization.yaml` fixes project `pja-java-normalization` and
contains exactly one service, `java-normalization`. It includes no database,
migration, Redis, Worker, frontend, backend, Nginx, fault stub, or mock.

## 12. Private network

The helper safely creates or validates the explicitly named internal bridge
`pja-java-normalization-internal` with repository, purpose, and owner labels.
It is external to Compose and unrelated to `pja-br0`. Phase IVA permits only
Java and ephemeral validation probes; FastAPI is not attached.

## 13. Secret handling

The default root-controlled directory is
`/etc/personal-job-agent/java-normalization` at root:root mode `0700`. The
helper generates 32 random bytes without printing them and atomically installs
the file for container UID/GID `10001` at mode `0400`. Spring reads it from a
config-tree secret mount. It is not a Compose literal, image value, container
configuration environment value, report value, or health value. Rollback
retains it; rotation and later revocation are documented.

## 14. Runtime profile

`SPRING_PROFILES_ACTIVE=normalization-only`; there is no JDBC, database,
Flyway, Redis, or external proxy configuration. JVM sizing is
`-Xms64m -Xmx256m`.

## 15. Container security

The service is UID/GID `10001`, read-only, non-privileged, drops all
capabilities, enables no-new-privileges, uses a bounded noexec/nosuid/nodev
`/tmp`, has no host network, Docker socket, public port, or ordinary host
mount, and joins only the dedicated private network.

## 16. Resource ceilings

The exact ceilings are 0.50 CPU, 384 MiB memory and memory+swap, and 128 PIDs.

## 17. Health

The health check requests only `/actuator/health/readiness`, requires a
status-only response, and uses 10-second interval, 3-second timeout, 5 retries,
and 45-second start period. Restart is bounded to `on-failure:3`; validation
requires zero restart and no OOM.

## 18. Deployment script

`scripts/deploy-java-normalization.sh` provides separated `preflight`,
`ensure-network`, `create-secret`, `pull-image`, `deploy`, `validate`,
`synthetic`, `status`, `rollback-check`, `rollback`, and `stop` operations. It
uses exact project/network/image validation, bounded waits, traps, safe
quoting, sanitized outputs, synthetic-only probes, and no broad Docker action.

## 19. Rollback script

`scripts/remove-java-normalization.sh` requires the exact
`--confirm-java-only` token and delegates to the bounded rollback. Rollback
stops/removes only the Java service, preserves the key, removes the network
only at zero attachments, and never touches an existing production container,
volume, database, Redis, Nginx, routing, or firewall.

## 20. Operations runbook

`docs/operations/JAVA_NORMALIZATION_PRODUCTION_ROLLOUT.md` documents Phase IVA
topology, digest handling, secret lifecycle, commands, health/private probes,
resources, logs, rollback, stop gates, the production version/schema boundary,
and separately gated Phase IVB/shadow/Java stages.

## 21. Validation performed before merge

Local validation included `bash -n`, ShellCheck, Compose rendering with a
synthetic immutable digest and placeholder file, Git whitespace checks,
workflow/static secret review, and scope review. GitHub validation results are
recorded in final delivery metadata before merge.

## 22. Changed files

- `.github/workflows/java-normalization-production.yml`
- `compose.java-normalization.yaml`
- `scripts/deploy-java-normalization.sh`
- `scripts/remove-java-normalization.sh`
- `docs/operations/JAVA_NORMALIZATION_PRODUCTION_ROLLOUT.md`
- `docs/architecture/JAVA_PRODUCTION_NORMALIZATION_INTEGRATION.md`
- `docs/work-reports/README.md`
- this Work Report

## 23. Commit SHAs

Implementation and final report-only delivery metadata commits will be
recorded after the commits exist and before merge.

## 24. Implementation PR URL

The pull request URL will be recorded after creation and before merge.

## 25. Risks and limitations

The service remains single-host and is not high availability. Resource
snapshots are point-in-time, not a load test. The host has less free disk than
the reviewed July 29 audit and must pass the immediate predeployment gate.
Config-tree secret readability relies on the reviewed UID/GID and root-owned
directory arrangement. Phase IVA proves private infrastructure only, not
FastAPI connectivity, shadow correctness, Java-authoritative behavior,
external provider behavior, or a performance improvement.

## 26. Confirmation that production was not modified during PR preparation

Confirmed. Preparation used bounded read-only production inspection only. No
container, network, image, secret, route, firewall, database, or configuration
was created, changed, restarted, or removed.

## 27. Confirmation that FastAPI runtime was untouched

Confirmed. No FastAPI runtime source or deployed FastAPI container/configuration
was changed.

## 28. Confirmation that no migration was added or edited

Confirmed. No Alembic or Flyway migration was added, edited, or run.

## 29. Confirmation that no release or deployment occurred during PR preparation

Confirmed. No tag, GitHub Release, image publication, production deployment,
or application restart occurred during PR preparation.

## 30. Confirmation that no external LLM was called

Confirmed. No DeepSeek or other external LLM was called.
