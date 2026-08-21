# Version 2.1.0 deployment and rollback

Version 2.1.0 promotes the reviewed Applications workflow while preserving the
Java-authoritative production rollout and bounded Analyze behavior. It upgrades
Alembic from `20260730_07` to `20260820_08` and keeps normalization mode `java`,
the existing private Java service, HTTPS, Mihomo, `pja-br0`, routing preference
8999, and the established public ports and networks.

## Artifacts

Publish Backend and Frontend from the exact release source commit with
`.github/workflows/release-images.yml`. Use only the resulting
`sha-<full-commit>` images and record immutable registry digests plus OCI source,
revision, and Version `2.1.0` labels. Do not rebuild the unchanged Java image and
do not create the release tag before the exact images pass publication checks.

Record the previous Backend and Frontend digests. Production must use immutable
`@sha256` references and `RELEASE_VERSION=2.1.0`; a mutable tag is never a
deployment input.

## Preflight

Immediately before mutation require:

- public Version exactly `2.0.7` and readiness `ready`;
- Alembic exactly `20260730_07` and mode exactly `java`;
- the recorded Backend and Java digests;
- a completed, verified PostgreSQL 16 production backup at revision
  `20260730_07`, with protected restore assets;
- the annotated `v2.1.0` tag and GitHub Release resolve to the exact reviewed
  source, with successful tag/image verification;
- healthy Backend and Java, restart count zero, and OOM false;
- at least 1.5 GiB available RAM and 6 GiB available root disk;
- Java attached only to the private normalization network with no host port;
- unchanged public Edge port, networks, production containers, and Java key;
  and
- the exact existing Compose file order and restricted environment files.

Stop with NO-GO before mutation on any mismatch. Do not inspect user content,
invoke `/api/analyze`, print secrets/environment values, call an external LLM,
or clean resources to force a capacity gate.

## Cutover

Update only the immutable application image references and release version.
Render the exact established production Compose file order, run its one-shot
`migrate` service, and require Alembic `20260820_08`. Deploy Backend, Worker,
and Outbox consistently from the same Python digest, then deploy Frontend from
its reviewed digest. Keep all established production Compose overrides so
Backend remains in `java` mode.

Do not recreate PostgreSQL, Redis, Java, or Edge/Nginx. Preserve the Java
project, digest, key, private network, policy
`jd-normalization-v1`, and dictionary `skills-v1`.

## Acceptance

Require public Version `2.1.0`, readiness `ready`, Alembic `20260820_08`, mode
`java`, and exact reviewed Backend/Worker/Outbox and Frontend digests. Require
healthy application and Java services, restart zero, OOM false, unchanged public
ports/networks, no Java host port, no unexpected Java failure/fallback/config
warning during cutover, and no secret in bounded inspection, logs, or image
metadata. Perform no business request.

After this GO, retain the exact `v2.1.0` source, Release, image digests, previous
Version 2.0.7 digests, production configuration, database backup, and validation results in the
release report.

## Rollback

For an application-image failure, restore the recorded Version 2.0.7 Backend
digest consistently to Backend, Worker, and Outbox and restore the prior
Frontend digest. Keep Java, its key/network, all volumes, and all data. Because
Version 2.1.0 can write new Application records, do not automatically downgrade
the database. Use the verified pre-release backup only for an explicitly
approved data rollback, or keep schema `20260820_08` for an image rollback.

For an urgent Java-boundary safety issue, omit the Stage 4 and Stage 3 overrides
while retaining the base/safety/routing/Stage 2 files, verify the render is
`local` with sample rate zero, and recreate only Backend. Do not downgrade the
database or delete Java.
