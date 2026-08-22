# Version 2.2.0 deployment and rollback

Version 2.2.0 promotes the reviewed Applications Improvements from the current
Version 2.1.0 production baseline. It keeps Alembic at `20260820_08`, production
normalization mode `java`, the existing private Java service, HTTPS, Mihomo,
`pja-br0`, routing preference 8999, and the established public ports and
networks. There is no migration in this release.

This runbook distinguishes a user-visible or safety failure from bounded
degraded operation and an observability warning. It does not weaken security,
database consistency, backup/restore, immutable artifact, root-capacity, or
public HTTPS gates.

## Gate implementation map

The effective gate is composed from all of the following sources; changing this
document alone does not change the executable policy.

| Source | Enforcement |
|---|---|
| `ops/release_gate/analyze_gate.py` | Automated five-run Analyze decision: `PASS`, `PASS_WITH_WARNING`, `FAIL`, or `HARD_FAIL` |
| `ops/release_gate/collect_analyze.py` | Automated production-equivalent HTTPS requests, response validation, History/metrics checks, Java fallback/duration correlation, and bounded Edge/Frontend/Backend/Java log capture |
| `ops/release_gate/test_analyze_gate.py` | Automated policy regressions, also run by `.github/workflows/ci.yml` |
| `scripts/assert-release-health.sh`, `scripts/verify-images.sh`, `scripts/test-v201-production-runtime.sh` | Shell-enforced version, image, Compose, topology, and runtime gates |
| `scripts/backup-v2.sh`, `scripts/verify-v2-backup.sh`, `scripts/restore-v2.sh`, `scripts/postgres16-restore-regression.sh` | Shell/Python-enforced backup, validation, and PostgreSQL 16 restore gates |
| `.github/workflows/release-images.yml` | CI-enforced release-source, image publication, OCI metadata, non-root, and immutable-image checks |
| This runbook and the release report | Human-reviewed release identity, change scope, cutover/rollback decision, and retained evidence |

The general Docker smoke remains a deterministic application regression. It
does not replace the mandatory production-equivalent candidate or production
five-run gate because its mock-provider HTTP topology is intentionally simpler.

## Gate classes

### HARD FAIL

Stop before cutover when this happens in preflight or candidate. During
production acceptance, preserve evidence and execute the application-image
rollback immediately.

- any Public HTTPS Analyze empty reply, connection failure, non-2xx response,
  incomplete/corrupt response, or Backend final-status mismatch;
- authentication, authorization, trusted-origin/CSRF, secret, ownership, or
  other security-boundary failure;
- database corruption, data-integrity failure, History/metrics persistence
  failure, or Application Delete affecting the wrong Application, Resume, or
  History record;
- migration failure, unexpected Alembic revision, PostgreSQL unavailability,
  or Redis unavailability;
- backup creation/validation failure, restore-validation failure, or missing
  protected rollback assets;
- image/tag/source/revision/version/digest mismatch or candidate/production
  application artifact mismatch;
- required unhealthy container, unexpected restart, OOM, health/readiness
  failure, or persistent Backend/Edge runtime error; or
- root free capacity below the unchanged 6 GiB gate.

Missing required evidence is a HARD FAIL; it is never interpreted as success.
An Empty reply is never a warning even if the Backend later records HTTP 200.

### Statistical Java degraded gate

Evaluate exactly five consecutive production-equivalent Analyze requests. Each
must use Public HTTPS, a unique `X-Request-ID`, normal authentication, RAG ON,
History ON, metrics ON, Java ON, and PostgreSQL persistence.

- `PASS`: 5/5 complete correct HTTP 2xx responses, Java fallback 0/5, and no
  connection failure.
- `PASS_WITH_WARNING`: 5/5 complete correct HTTP 2xx responses, exactly one
  Java fallback, the fallback result is complete and correct, no two
  consecutive fallbacks, and containers/DB/Edge remain normal.
- `FAIL`: Java fallback is at least 2/5, any two fallbacks are consecutive, the
  fallback output is incorrect/incomplete, or fallback causes request failure.
- `HARD_FAIL`: any Public HTTPS empty reply/non-2xx/incomplete response or any
  hard invariant above fails, regardless of fallback count.

Candidate stops on `FAIL` or `HARD_FAIL`. Production rolls back on either. A
single successful fallback is recorded in the release report and does not by
itself trigger rollback.

### Observability warnings

Record but do not block a release solely for a single Java latency spike that
returns normally, one recovered transient network warning, one recovered
external package/CDN failure before the formal gate succeeds, a known npm
advisory not introduced by this release, or one Java fallback satisfying
`PASS_WITH_WARNING`. Repetition, persistence, an incomplete response, or a
failed formal gate is not a warning.

## Artifacts

Use the existing annotated `v2.2.0` tag and GitHub Release. Never move or
recreate that tag. Do not build, retag, or republish application images. Use
only the existing immutable Backend and Frontend `@sha256` references whose OCI
source revision is the peeled `v2.2.0` commit and whose version is `2.2.0`.

Record the Version 2.1.0 Backend and Frontend digests. Production must use
immutable `@sha256` references and `RELEASE_VERSION=2.2.0`; a mutable tag is
never a deployment input. Backend, Worker, and Outbox must use the same Python
digest. Candidate and production must use identical v2.2.0 application digests.

## Preflight

Immediately before mutation require:

- public Version exactly `2.1.0`, health `ok`, and readiness `ready`;
- Alembic exactly `20260820_08` and normalization mode exactly `java`;
- PostgreSQL 16, Redis, and Java readiness healthy;
- every required production container healthy, restart count zero, OOM false;
- at least 1.5 GiB available RAM and 6 GiB available root disk;
- the recorded Version 2.1.0 Backend/Frontend and unchanged Java digests;
- annotated `v2.2.0`, GitHub Release, immutable image metadata, OCI source,
  revision, version, users, and digests all match the reviewed release;
- Java attached only to the private normalization network with no host port;
- unchanged public Edge port, networks, production containers, Java key,
  Compose file order, and restricted environment files; and
- protected rollback Compose/env assets and reachable rollback images.

Stop with NO-GO before mutation on any mismatch. Do not inspect production user
content, print secrets/environment values, or delete resources to force the
capacity gate.

Run a new PostgreSQL production backup, guarded backup validation, strict
isolated PostgreSQL 16 restore validation, Compose validation, and production
runtime regression. This release has no migration: Alembic must be
`20260820_08` before and after every candidate/cutover operation.

## Candidate

Deploy the exact existing immutable v2.2.0 application images to the established
isolated candidate. Use an isolated PostgreSQL database/volume, Redis, file
storage, test account, sessions, metrics, audit data, and synthetic content.
Keep Java normalization enabled and use the production-equivalent Edge and
Frontend proxy path. Do not disable RAG, History, metrics, authentication,
Java, or PostgreSQL persistence.

First require HTTPS health/readiness, Login, Resume, History, Project Knowledge
and RAG, Applications, Application View, Resume Snapshot, Redis, Worker, Outbox,
Java, container health/restart/OOM, backup/restore, and rollback assets. Verify
Application confirmation/cancel/delete, physical PostgreSQL deletion,
ownership boundaries, preservation of the related Analysis/History and Resume,
and preservation of every unrelated Application. Verify pre-wrapped Resume
snapshots and Applications layout at 375 px, 768 px, and desktop widths.

Then run `ops/release_gate/collect_analyze.py` with the checked-in synthetic
Resume/JD fixtures, a mode-0600 password file for the isolated account, the
candidate public HTTPS URL/CA, exact candidate container names, and a JSON file
that positively records every hard gate. The collector:

- creates and finalizes a production-length synthetic Resume;
- rebuilds and uses Project Knowledge;
- executes exactly five Analyze requests with unique request/idempotency keys;
- verifies complete output, RAG, History, monitoring trace, Backend final HTTP
  status, Java outcome/duration/fallback, Edge/Frontend access observations,
  and all four log scans;
- records curl exit code and raw stderr, HTTP status/bytes, connect,
  start-transfer, and total timing without retaining response bodies; and
- writes content-free JSON evidence plus mode-0600 bounded layer logs.

Only `PASS` or `PASS_WITH_WARNING` permits cutover. Clean all isolated
candidate resources and data through the established scoped cleanup; verify
that candidate rows and volumes do not affect production.

## Cutover

Update only the immutable application image references and release version.
Render the exact established production Compose file order. Do not run a
migration or recreate the database. Recreate Backend, Worker, and Outbox
consistently from the same v2.2.0 Python digest, then Frontend from the reviewed
v2.2.0 digest. Recreate Edge from that same reviewed Frontend digest when the
release Compose declares it, after Frontend is healthy.

Do not recreate PostgreSQL, Redis, or Java. Preserve the Java
project, digest, key, private network, policy `jd-normalization-v1`, dictionary
`skills-v1`, and all established production overrides.

Require public Version `2.2.0`, Alembic `20260820_08`, health/readiness,
containers healthy, restart zero, OOM false, and exact image digests before
starting acceptance.

## Production acceptance

Use a newly created isolated production test account and the same collector,
fixtures, five-run policy, and Public HTTPS path used for candidate. Positively
record all hard gates again. Preserve the unique `X-Request-ID`, timestamps,
HTTP status, response completeness/hash/size, end-to-end duration, Java
duration/outcome/fallback, History and metrics persistence, relevant errors,
and bounded Edge/Frontend/Backend/Java logs for every run.

Use nondecreasing gate offsets such as `0,30,60,120,240` seconds so acceptance
samples the immediate cutover and the following stabilization window rather
than sending all requests back-to-back.

- `PASS` becomes `GO`.
- `PASS_WITH_WARNING` becomes `GO_WITH_WARNING` and must appear in the release
  report with fallback count and warning evidence.
- `FAIL` or `HARD_FAIL` becomes `ROLLBACK`.

Do not roll back solely for one normal recovered Java fallback. Do roll back
for any empty reply, non-2xx, incomplete response, at least 2/5 fallback,
consecutive fallback, data/security failure, unhealthy/restarted/OOM container,
or database/health/readiness hard failure.

## Empty reply evidence

On the first Empty reply, stop further acceptance, retain evidence, and roll
back. Before changing containers, preserve under a restricted directory:

- `X-Request-ID` and UTC request window;
- client exit code/raw stderr, HTTP status/bytes, connect/start-transfer/total
  timing, and local/remote socket addresses;
- Edge emitted access/error stream and connection-close evidence;
- Frontend emitted access/error stream;
- Backend correlated log and final HTTP status, if any; and
- Java correlated log, status, and duration, if any.

During a controlled acceptance window, enable a body-free JSON Nginx access
format at Edge and Frontend that records only method/URI without query string,
request ID, status/upstream status, request/upstream response time, and bytes
sent. Never log request bodies, cookies, authorization/CSRF headers, tokens, or
keys. Require one correlated Edge and Frontend access observation per successful
Analyze. Also preserve a safe Docker inspect snapshot containing container
IDs/start times/images/restart/OOM/health and network IPs. Restore the reviewed
normal logging configuration after GO, or from rollback assets after failure.

## Test-data cleanup

After production acceptance, precisely delete only the isolated account's
Resume, Applications, History, Analyze idempotency, Sessions, analysis metrics,
step metrics, and audit test data using the established user-scoped cleanup.
Verify zero remaining rows for that account and confirm real production row
counts were unaffected. Do not use broad table truncation, volume deletion, or
monitoring-retention cleanup.

## Rollback

For an application-image failure, restore the recorded Version 2.1.0 Backend
digest consistently to Backend, Worker, and Outbox and restore the prior
Frontend digest. Keep Java, its key/network, all volumes, and all data. Keep
schema `20260820_08`; Version 2.2.0 has no migration. Use the verified
pre-release backup only for an explicitly approved data rollback.

For an urgent Java-boundary safety issue, omit the Stage 4 and Stage 3
overrides while retaining the base/safety/routing/Stage 2 files, verify the
render is `local` with sample rate zero, and recreate only Backend. Do not
downgrade the database or delete Java.

## Release report

After GO/GO WITH WARNING, create
`docs/work-reports/2026-08-22-v2.2.0-release-work-report.md`. Record the policy
commit, unchanged v2.2.0 tag/release commit, immutable digests, backup and
restore evidence, rollback assets, candidate and production five-run results,
fallback counts, warnings, Applications smoke, production version, Alembic,
and final container health/restart/OOM state. Commit and push the report on
`main`; do not create v2.2.1.
