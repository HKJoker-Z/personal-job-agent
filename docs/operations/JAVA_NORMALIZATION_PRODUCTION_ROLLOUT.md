# Java normalization production rollout

## Version 2.0.5 final release status

Phases IVA through IVD-B are complete. The accepted production baseline before
the Version 2.0.5 image cutover is application `2.0.4`, Alembic `20260730_07`,
mode `java`, Backend digest
`sha256:eb58b008cb368547a9e16b987a21da6185ec280e0cf64552a90ebebfcf7a9488`,
and unchanged Java digest
`sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f`.
The IVD-B evidence decision is GO.

The final release changes only application version-bearing Backend/Worker/
Outbox and Frontend images, all promoted by immutable digest from the reviewed
release source commit. It keeps mode `java`, Alembic `20260730_07`, the Java
image/project/key/private network, public ports, and database topology. No
migration command is required. Emergency mode rollback omits the Stage 4 and
Stage 3 overrides and recreates only Backend in `local`; image rollback uses
the recorded previous application digests without a schema downgrade.

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

## Phase IVB: integrated Backend in local mode

Phase IVB deploys the merged Python execution-fingerprint and Java-client code
without activating Java behavior. The production override is
`deploy/production/compose.java-normalization-stage-2.override.yaml`. It pins
the migration, Backend, Worker, Outbox, and backup services to one immutable
Backend image; sets `ANALYSIS_JD_NORMALIZATION_MODE=local` explicitly for the
long-running Python services; and attaches only the FastAPI Backend to
`pja-java-normalization-internal`.

The Backend receives the private origin and the existing key as a read-only
file, but local configuration intentionally does not read the key, resolve the
Java service, create an HTTP client, or make a Java request. Worker, Outbox,
PostgreSQL, Redis, Frontend, and Edge do not join the Java network. Java keeps
its Phase IVA image, profile, security controls, limits, project, and lack of a
host-published port.

Publish the Backend only through `.github/workflows/backend-production.yml`
at the exact reviewed preparation merge commit. Its manual run repeats the
complete Backend and PostgreSQL 16 integration suites before publishing only:

`ghcr.io/hkjoker-z/personal-job-agent-backend:sha-<full-commit>`

Production uses the resulting `IMAGE@sha256:<digest>`. The workflow creates no
mutable production tag, Frontend/Java image, repository tag, or GitHub
Release.

### Phase IVB preflight and backup

Before the first host mutation, run the Phase IVA helper's read-only preflight
with the deployed Java digest. Require production `2.0.4`, Alembic
`20260724_06`, at least 1.5 GiB available RAM, at least 6 GiB available root
disk, healthy existing containers, zero unexpected restart/OOM state, and the
unchanged private Java topology. Record exact existing container IDs, image
references, start times, health, restart/OOM state, networks, and published
ports without printing environment values.

Use the current production Compose file list recorded on the running Backend;
do not omit established safety/cutover overrides. Before adding the Phase IVB
override, use that exact current stack and restricted production environment
file to run the existing `backup` profile once. Verify the resulting exact
backup with `scripts/v2_backup_restore.py verify`, and record only its safe
path, sizes, SHA-256 values, PostgreSQL major, application version, Alembic
revision, and inventory aggregates.

Restore that exact backup once to a uniquely named PostgreSQL 16 project with
an internal-only network, a new temporary volume, no host port, and empty
private-file targets. Use the existing guarded restore command with explicit
disposable-target identity and only the exact owner/database-name mappings
reported by the verified manifest. Inspect no restored user row or content.
On the same restored target:

1. confirm Alembic `20260724_06`;
2. run the reviewed Backend image's `alembic upgrade head`;
3. confirm exactly one head at `20260730_07`;
4. inspect only schema metadata for the six execution-binding columns and the
   four named constraints;
5. run `alembic upgrade head` again and prove it is a no-op; and
6. remove only the uniquely named rehearsal containers, network, volume, and
   empty restored file targets after evidence is captured.

Stop with NO-GO before production migration for any backup, verification,
restore, inventory, migration, constraint, or cleanup-target identity failure.

### Phase IVB migration and cutover

Run the existing one-shot `migrate` service with the immutable reviewed
Backend image and the Phase IVB override. Do not use `stamp`, `--fake`, edit a
revision, or downgrade. Confirm the only transition is:

`20260724_06 -> 20260730_07`

Inspect only `alembic_version`, `information_schema.columns`, and
`pg_constraint` metadata. Run the same one-shot migration a second time and
confirm the revision remains unchanged. Before replacing the Backend, verify
the previous Backend remains healthy against the additive schema; this is the
rollback-compatibility proof and avoids a schema downgrade.

Keep the established production base Compose and all existing override files.
Install the reviewed Phase IVB override as a root-owned read-only file under
the existing `/opt/personal-job-agent-v2` deployment directory. Store only the
new immutable `BACKEND_IMAGE` reference in a separate root-owned mode `0600`
Stage IVB environment file; continue supplying the existing restricted
production environment file first. Never copy or print its secret values.

Pull the reviewed image, then recreate only Worker and Outbox, wait for their
health, and recreate only Backend. Do not recreate PostgreSQL, Redis, Frontend,
Edge/Nginx, or Java. The successful steady state has the same immutable image
digest on Backend, Worker, and Outbox, while the one-shot migrate service and
backup profile resolve to that digest for later use.

### Phase IVB validation and rollback

Validate from status, startup, schema, topology, configuration-name, and
bounded log evidence only. Do not invoke `/api/analyze`. Require:

- public readiness `ready`, version `2.0.4`, and Alembic `20260730_07`;
- exact runtime mode `local` without printing the rest of the environment;
- Backend on its existing application/data networks plus only the Java
  network, and no other Personal Job Agent service newly attached;
- Java healthy/private with restart zero and OOM false;
- no new Java normalize request, Request ID, or request-log event across the
  deployment validation window;
- healthy Backend, Worker, Outbox, PostgreSQL, Redis, Frontend, and Edge;
- unchanged public port bindings and unchanged IDs for services not recreated;
- expected immutable Python digest on Backend, Worker, and Outbox; and
- no key, environment secret, synthetic marker, database content, or user
  content in bounded logs, image history, terminal output, or the report.

Record the previous Python digest and configuration before cutover. Rollback
recreates only Backend, Worker, and Outbox with that previous digest and
explicit local mode. Keep Alembic `20260730_07`; the migration is additive and
the previous Backend compatibility check proves no downgrade is required.
Java, its network, and its key may remain independently for later review.

Shadow observation and Java-authoritative Analyze remain separately gated.
Phase IVB does not authorize Phase IVC, `/api/analyze`, DeepSeek, another
external LLM, a version bump, tag, or GitHub Release.

## Phase IVC-A: bounded production Shadow configuration

Phase IVC-A adds
`deploy/production/compose.java-normalization-stage-3-shadow.override.yaml`
after the established Phase IVB override. It changes only the FastAPI Backend
environment: normalization mode becomes `shadow`, deterministic sampling is
`1.0`, and the reviewed 200/600/800 ms connect/response/total deadlines,
262144-byte response ceiling, `jd-normalization-v1` policy, and `skills-v1`
dictionary are explicit. The private origin, key-file mount, immutable image,
and Backend-only Java network attachment remain inherited from Phase IVB.
Worker and Outbox remain explicitly `local`.

The 1.0 rate is bounded rollout configuration, not a Java-authoritative
decision. Every later user-initiated, non-replayed Analyze is deterministically
eligible for one observation-only Java attempt. Local sanitized JD remains
authoritative for the execution fingerprint, RAG, prompt, History, provider
input, and response. Java failure is contained as a safe observation and never
fails Analyze. The client has one attempt, no retry, no redirect, no inherited
proxy, and the reviewed total deadline.

### Preflight and deployment

Immediately before mutation, verify production `2.0.4`, Alembic
`20260730_07`, exact current Backend/Java digests, runtime mode `local`, all
existing health/restart/OOM state, Java-private topology and health-only logs,
at least 1.5 GiB available RAM, and at least 6 GiB available root disk. Record
container IDs, networks, and published ports without printing environment or
secret values. Do not prune to pass the gate.

Install the reviewed Shadow override root:root mode `0444` under
`/opt/personal-job-agent-v2`. Keep the exact existing production environment
files and Compose file sequence, append the Shadow override last, render the
configuration, and prove its only semantic difference from the Phase IVB
render is the bounded Backend environment listed above. Then recreate only:

```bash
docker compose <existing production files and environment files> \
  -f /opt/personal-job-agent-v2/compose.java-normalization-stage-2.override.yaml \
  -f /opt/personal-job-agent-v2/compose.java-normalization-stage-3-shadow.override.yaml \
  up -d --no-deps --wait backend
```

Do not recreate Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, Java,
or the legacy Backend. Do not invoke `/api/analyze`; Shadow evidence must come
only from later user-initiated requests.

### Validation and safe evidence

Require Backend `shadow` and sample rate `1.0`, healthy/restart zero/OOM false,
Java healthy/private/restart zero/OOM false, public health 200, application
`2.0.4`, Alembic `20260730_07`, unchanged images/IDs/ports for every untouched
container, and no secret value in inspection or bounded logs.

Before user traffic, Java logs should contain only periodic
`/actuator/health/**` readiness events. After user-initiated test traffic, a
separately requested Phase IVC-B review may inspect only bounded structured
observation fields: mode/source, sampled/attempted booleans, stable outcome,
bounded duration, equality boolean, bounded finding count, expected versions,
and trusted Request ID outcome. Never inspect or record JD, Resume, prompt,
response, History, hashes, key/Authorization, Java bodies, or arbitrary
exceptions.

### Rollback to local

Render rollback by omitting the Stage 3 Shadow override while retaining every
prior production file and the Phase IVB override. Confirm the result is
Backend `local`, sample rate `0`, the same immutable image, the same networks
and read-only key mount, and Worker/Outbox `local`. If rollback is needed,
recreate only Backend with that exact Phase IVB render. No image change,
database downgrade, Java restart, History transformation, completed-response
change, or other service recreation is required. A healthy Shadow deployment
is not rolled back merely to demonstrate the command.

Stop for any health, restart, OOM, secret, topology, port, resource, version,
schema, configuration, unauthorized/version-mismatch observation, or
Java-correlated Analyze failure. Phase IVC-A may return only conditional GO
until later user-initiated traffic supplies safe Shadow observations. It does
not authorize Java-authoritative mode, production test users, generated
Analyze traffic, an external LLM call, image publication, a version bump, tag,
or GitHub Release.

## Phase IVD-A: bounded Java-authoritative configuration

Phase IVD-A appends
`deploy/production/compose.java-normalization-stage-4-java.override.yaml`
after the established Phase IVB and Phase IVC-A overrides. Its only setting is
`ANALYSIS_JD_NORMALIZATION_MODE=java` for `backend`. The preceding overrides
continue to provide the immutable Backend image, private Java origin,
read-only key file, Backend-only Java network, 200/600/800 ms deadlines,
262144-byte response ceiling, and expected `jd-normalization-v1` and
`skills-v1` versions. Worker and Outbox remain explicitly `local`.

In Java mode, a valid successful Java result passes the authoritative second
security scan and becomes the effective JD with execution source `java`. Any
bounded Java failure or rejected second scan selects the existing local
candidate with source `fallback_local`. Selection and the
`analyze-execution-v1` binding complete before Project Knowledge retrieval,
prompt construction, provider work, scoring, History derivation, or result
finalization. The client retains one attempt, no retry, no redirect, bounded
timeouts and response size, and `trust_env=False`. Completed response replay
returns before Java, provider, or History side effects.

### Preflight and deployment

Immediately before mutation, require production `2.0.4`, Alembic
`20260730_07`, exact approved Backend and Java digests, runtime mode `shadow`,
healthy Backend and Java with restart zero and OOM false, unchanged
private-network membership and public ports, at least 1.5 GiB available RAM,
at least 6 GiB available root disk, and no bounded log security or secret
issue. Record only allowlisted structured metadata; never print environment,
secret, request, user-content, or Java-body values. Do not prune resources to
pass a gate.

Install the Stage 4 override root:root mode `0444` under
`/opt/personal-job-agent-v2`. Retain the exact existing production environment
files and Compose sequence, append Stage 4 last, render it, and prove the only
semantic difference from the running Shadow render is Backend mode `java`.
Then recreate only:

```bash
docker compose <existing production files and environment files> \
  -f /opt/personal-job-agent-v2/compose.java-normalization-stage-2.override.yaml \
  -f /opt/personal-job-agent-v2/compose.java-normalization-stage-3-shadow.override.yaml \
  -f /opt/personal-job-agent-v2/compose.java-normalization-stage-4-java.override.yaml \
  up -d --no-deps --wait backend
```

Do not recreate Worker, Outbox, PostgreSQL, Redis, Frontend, Edge/Nginx, Java,
or the legacy Backend. Do not invoke `/api/analyze`; Java-authoritative
evidence must come only from later normal user-initiated requests.

### Validation and emergency rollback

Require Backend mode `java`, healthy/restart zero/OOM false Backend and Java,
public health `200`, application `2.0.4`, Alembic `20260730_07`, identical image
digests, unchanged IDs for untouched services, unchanged ports and private
network membership, sufficient host resources, and no secret or unsafe value
in bounded logs. Verify the authoritative/fallback, second-scan, execution-
binding, one-attempt/no-retry, hidden-Java-failure, and completed-replay
contracts from merged source and tests without generating Analyze traffic.

Render emergency rollback by omitting both Stage 4 and Stage 3 while retaining
the base stack and Phase IVB override. Confirm Backend mode `local`, sample
rate `0`, and the same image, networks, and read-only key mount. If any gate
fails, recreate only Backend from that local render. No image change, database
downgrade, Java restart/removal, History or idempotency transformation, Redis
operation, or other service recreation is required. Do not execute rollback
when all gates pass.

A successful Phase IVD-A is only **CONDITIONAL GO** pending a separately
requested Phase IVD-B review of 3-5 later user-initiated non-sensitive Analyze
requests. Phase IVD-A does not authorize generated Analyze traffic, external
LLM calls by the operator, image publication, migration, release, version
bump, tag, or automatic progression into Phase IVD-B.
