# Version 2.2.0 deployment and rollback

Version 2.2.0 promotes the reviewed Applications Improvements from the current
Version 2.1.0 production baseline. It keeps Alembic at `20260820_08`, production
normalization mode `java`, the existing private Java service, HTTPS, Mihomo,
`pja-br0`, routing preference 8999, and the established public ports and
networks. There is no migration in this release.

## Artifacts

Publish Backend and Frontend from the exact release source commit with
`.github/workflows/release-images.yml`. Use only the resulting
`sha-<full-commit>` images and record immutable registry digests plus OCI source,
revision, and Version `2.2.0` labels. Do not rebuild the unchanged Java image and
do not create the release tag before the exact images pass publication checks.

Record the Version 2.1.0 Backend and Frontend digests. Production must use
immutable `@sha256` references and `RELEASE_VERSION=2.2.0`; a mutable tag is
never a deployment input.

## Preflight

Immediately before mutation require:

- public Version exactly `2.1.0` and readiness `ready`;
- Alembic exactly `20260820_08` and mode exactly `java`;
- the recorded Version 2.1.0 Backend/Frontend and unchanged Java digests;
- a completed, verified PostgreSQL 16 production backup at revision
  `20260820_08`, with protected restore assets;
- the annotated `v2.2.0` tag and GitHub Release resolve to the exact reviewed
  source, with successful tag/image verification;
- healthy Backend and Java, restart count zero, and OOM false;
- at least 1.5 GiB available RAM and 6 GiB available root disk;
- Java attached only to the private normalization network with no host port;
- unchanged public Edge port, networks, production containers, and Java key;
  and
- the exact existing Compose file order and restricted environment files.

Stop with NO-GO before mutation on any mismatch. Do not inspect production user
content, invoke `/api/analyze` with production data, print secrets/environment
values, call an external LLM, or clean resources to force a capacity gate.

## Candidate

Deploy the exact reviewed immutable application images first to the established
isolated candidate. Require HTTPS, health/readiness, login, Resume, Analyze,
History, Applications, Project Knowledge, PostgreSQL, Redis, Worker, Outbox,
Java normalization, healthy containers, stable restarts, and rollback assets.
Use only isolated synthetic data. Verify Application confirmation/cancel/delete,
physical PostgreSQL deletion, ownership boundaries, preservation of the source
Analysis/History and Resume, unaffected other Applications, and readable
pre-wrapped Resume snapshots without changing stored text. Verify Applications
layout at 375 px, 768 px, and desktop widths.

## Cutover

Update only the immutable application image references and release version.
Render the exact established production Compose file order. Because the schema
does not change, require Alembic `20260820_08` before and after deployment; do
not run a migration or recreate the database. Deploy Backend, Worker, and Outbox
consistently from the same Python digest, then deploy Frontend from its reviewed
digest. Keep all established production Compose overrides so Backend remains in
`java` mode.

Do not recreate PostgreSQL, Redis, Java, or Edge/Nginx. Preserve the Java
project, digest, key, private network, policy `jd-normalization-v1`, and
dictionary `skills-v1`.

## Acceptance

Require public Version `2.2.0`, readiness `ready`, Alembic `20260820_08`, mode
`java`, and exact reviewed Backend/Worker/Outbox and Frontend digests. Require
healthy application and Java services, restart zero, OOM false, unchanged public
ports/networks, no Java host port, no unexpected Java failure/fallback/config
warning during cutover, and no secret in bounded inspection, logs, or image
metadata. Perform Application DELETE smoke only with isolated synthetic data,
never with a production user's Application.

After this GO, retain the exact `v2.2.0` source, Release, image digests, Version
2.1.0 rollback digests, production configuration, database backup, and
validation results in the release report.

## Rollback

For an application-image failure, restore the recorded Version 2.1.0 Backend
digest consistently to Backend, Worker, and Outbox and restore the prior
Frontend digest. Keep Java, its key/network, all volumes, and all data. Keep
schema `20260820_08`; Version 2.2.0 has no migration. Use the verified
pre-release backup only for an explicitly approved data rollback.

For an urgent Java-boundary safety issue, omit the Stage 4 and Stage 3 overrides
while retaining the base/safety/routing/Stage 2 files, verify the render is
`local` with sample rate zero, and recreate only Backend. Do not downgrade the
database or delete Java.
