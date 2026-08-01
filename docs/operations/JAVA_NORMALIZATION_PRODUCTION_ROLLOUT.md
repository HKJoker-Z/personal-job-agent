# Java normalization production rollout

## Phase IVA purpose and boundary

Phase IVA predeploys one private, stateless Java normalization-only service on
the existing production host. It does not make Java part of Analyze. FastAPI
is not attached to the Java network, makes no Java request, and remains on the
unchanged Personal Job Agent `2.0.4` images and configuration. Production
Alembic remains `20260724_06`; no migration command is permitted in this
runbook.

The separate Compose project is `pja-java-normalization`. It owns only the
`java-normalization` service. The operator-created internal bridge
`pja-java-normalization-internal` is external to Compose so a project teardown
cannot delete a network later shared with FastAPI. During Phase IVA, only Java
and a short-lived validation probe may join it. It is unrelated to `pja-br0`,
the application/data networks, PostgreSQL, Redis, Nginx, and host routing.

## Reviewed artifacts

- Compose: `compose.java-normalization.yaml`
- Deployment helper: `scripts/deploy-java-normalization.sh`
- Java-only removal wrapper: `scripts/remove-java-normalization.sh`
- Publication workflow: `.github/workflows/java-normalization-production.yml`
- Image: `ghcr.io/hkjoker-z/personal-job-agent-java-normalization`

The publication workflow runs Maven `verify` and the existing
normalization-only no-database container smoke before publishing only the
Dockerfile `application` target. It tags `sha-<full-commit>` and records OCI
source/revision labels. Production always uses the resulting
`IMAGE@sha256:<digest>` reference, never the tag. It creates no Git tag,
GitHub Release, migration image, FastAPI image, or full-profile database stack.

## Secret storage and lifecycle

The default secret path is:

`/etc/personal-job-agent/java-normalization/api-key`

The helper creates at least 32 cryptographically random bytes as 64 lowercase
hex characters without printing them. The parent is root-owned mode `0700`.
The file is UID/GID `10001`, mode `0400`, so Compose can bind it directly to
the same non-root UID while only root can traverse or change its host path.
Spring imports it through a config-tree mount named
`jd-normalization.security.api-key`; the value is not a Compose literal,
container configuration environment value, image layer, or health response.

The key is intentionally retained by rollback for Phase IVB review. To rotate,
first keep Analyze in `local`, generate a replacement in the same root-owned
directory, atomically install it with the same ownership/mode, recreate only
Java, validate privately, later configure FastAPI with the matching key in a
separately reviewed Phase IVB, and revoke the old key only after rollback
validation. A suspected compromise requires Java removal or local mode,
rotation, and bounded log review; never print either key.

## Read-only preflight

From the reviewed repository commit on the production host, set the immutable
reference and run the read-only gate:

```bash
export JAVA_NORMALIZATION_IMAGE='ghcr.io/hkjoker-z/personal-job-agent-java-normalization@sha256:<digest>'
scripts/deploy-java-normalization.sh preflight --image "${JAVA_NORMALIZATION_IMAGE}"
```

The helper reports time/uptime, memory, root disk, running container status and
ports, bounded point-in-time stats, Docker disk accounting, exact existing
health/restart/OOM/image/port metadata, Docker networks, version, and the
single Alembic metadata revision. It reads no application table or user data
and prints no container environment values.

Stop before any mutation if version is not `2.0.4`, schema is not
`20260724_06`, an existing v2 container is missing/unhealthy/restarted/OOM
killed, available RAM is below 1.5 GiB, root disk is below 6 GiB available, or
the proposed network conflicts with Docker state. Also stop for unexplained
host load/swap growth or materially worse capacity than the reviewed audit.
Do not prune Docker to force the gate.

## Deployment

Run each mutation as root so network and secret ownership remain explicit:

```bash
sudo scripts/deploy-java-normalization.sh ensure-network --image "${JAVA_NORMALIZATION_IMAGE}"
sudo scripts/deploy-java-normalization.sh create-secret --image "${JAVA_NORMALIZATION_IMAGE}"
sudo scripts/deploy-java-normalization.sh pull-image --image "${JAVA_NORMALIZATION_IMAGE}"
sudo scripts/deploy-java-normalization.sh deploy --image "${JAVA_NORMALIZATION_IMAGE}"
sudo scripts/deploy-java-normalization.sh validate --image "${JAVA_NORMALIZATION_IMAGE}"
sudo scripts/deploy-java-normalization.sh synthetic --image "${JAVA_NORMALIZATION_IMAGE}"
scripts/deploy-java-normalization.sh status --image "${JAVA_NORMALIZATION_IMAGE}"
scripts/deploy-java-normalization.sh rollback-check --image "${JAVA_NORMALIZATION_IMAGE}"
```

`validate` uses the Java image itself as an ephemeral private-network curl
probe. It validates status-only readiness, stable unauthenticated `401`,
authenticated normalization, Request ID preservation,
`jd-normalization-v1`/`skills-v1`, security metadata, exact resource ceilings,
single-network attachment, absence of database/Flyway configuration or log
signals, and absence of the key or synthetic marker in logs. `synthetic` makes
20 sequential private calls with synthetic text only and verifies health,
restart count, and OOM state afterward. Each probe uses `--rm`; confirm no
probe remains attached.

## Runtime and security inspection

The Compose service fixes:

- profile `normalization-only`, with no JDBC/Flyway/database/Redis values;
- UID/GID `10001:10001`, read-only root, 64 MiB bounded `/tmp` tmpfs;
- all capabilities dropped, no-new-privileges, no privileged/host network,
  Docker socket, host port, or ordinary host mount;
- only the reviewed read-only config-tree secret mount;
- 0.50 CPU, 384 MiB memory and memory+swap, 128 PIDs;
- JVM `-Xms64m -Xmx256m`;
- bounded status-only readiness and `on-failure:3`; and
- bounded json-file logs.

No inherited HTTP/HTTPS/ALL proxy is available. `NO_PROXY` contains only the
service-local names. The internal Docker network prevents ordinary external
routing.

Use `status` for the sanitized container snapshot. For bounded additional
inspection, use selected `docker inspect` formats and `docker stats
--no-stream`; never print the container environment or secret mount contents.
Java logs may be read only in bounded tails because Phase IVA generates
synthetic requests only:

```bash
docker logs --since 15m --tail 400 pja-java-normalization-java-normalization-1
```

Stop and remove Java for any public port, extra network, database attempt,
root user, writable root, unexpected capability/security option, missing
limit, unhealthy state, restart, OOM, secret/marker leak, excessive Java
memory, host degradation, or change to an existing production container.

## Rollback

Validate targeting without stopping the successful deployment:

```bash
scripts/deploy-java-normalization.sh rollback-check --image "${JAVA_NORMALIZATION_IMAGE}"
```

If rollback is required, the explicit confirmation wrapper stops/removes only
the Java Compose service and removes the private network only after it has zero
attachments:

```bash
sudo scripts/remove-java-normalization.sh --confirm-java-only \
  --image "${JAVA_NORMALIZATION_IMAGE}"
```

Rollback preserves the API key, all existing Personal Job Agent containers,
images, networks, volumes, PostgreSQL, Redis, routing, and Nginx. It never uses
`docker compose down`, `down -v`, prune, a database command, a FastAPI restart,
or a firewall/routing change.

## Later phases are separate

Phase IVB may attach FastAPI to the external private network and configure its
matching secret while keeping mode `local`, but only through a separate
reviewed task. Shadow observation and Java-authoritative Analyze are later
gated stages. Do not attach the current FastAPI container manually and do not
call `/api/analyze`, DeepSeek, or any external LLM during Phase IVA.
