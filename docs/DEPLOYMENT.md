# Version 2.0.6 deployment and rollback

Version 2.0.6 promotes the reviewed Provider-deadline and Analyze-resilience
source after the Java-authoritative production rollout reached Phase IVD-B GO.
It keeps Alembic
`20260730_07`, normalization mode `java`, the existing private Java service,
HTTPS, Mihomo, `pja-br0`, routing preference 8999, and the established public
ports and networks.

## Artifacts

Publish Backend and Frontend from the exact release source commit with
`.github/workflows/release-images.yml`. Use only the resulting
`sha-<full-commit>` images and record immutable registry digests plus OCI source,
revision, and Version `2.0.6` labels. Do not rebuild the unchanged Java image and
do not create the release tag before production acceptance.

Record the previous Backend and Frontend digests. Production must use immutable
`@sha256` references and `RELEASE_VERSION=2.0.6`; a mutable tag is never a
deployment input.

## Preflight

Immediately before mutation require:

- public Version exactly `2.0.4` and readiness `ready`;
- Alembic exactly `20260730_07` and mode exactly `java`;
- the recorded Backend and Java digests;
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
Deploy Backend, Worker, and Outbox consistently from the same Python digest,
then deploy Frontend from its reviewed digest. Keep all established production
Compose overrides so Backend remains in `java` mode.

Do not run a migration command or recreate PostgreSQL, Redis, Java, or
Edge/Nginx. Preserve the Java project, digest, key, private network, policy
`jd-normalization-v1`, and dictionary `skills-v1`.

## Acceptance

Require public Version `2.0.6`, readiness `ready`, Alembic `20260730_07`, mode
`java`, and exact reviewed Backend/Worker/Outbox and Frontend digests. Require
healthy application and Java services, restart zero, OOM false, unchanged public
ports/networks, no Java host port, no unexpected Java failure/fallback/config
warning during cutover, and no secret in bounded inspection, logs, or image
metadata. Perform no business request.

Only after this GO, and outside this release-preparation phase, may the
annotated `v2.0.6` tag and GitHub Release be created on the exact release source
commit. Until then production remains Version `2.0.5`.

## Rollback

For an application-image failure, restore the recorded Version 2.0.5 Backend
digest consistently to Backend, Worker, and Outbox and restore the prior
Frontend digest. Keep Alembic `20260730_07`, Java, its key/network, all volumes,
and all data.

For an urgent Java-boundary safety issue, omit the Stage 4 and Stage 3 overrides
while retaining the base/safety/routing/Stage 2 files, verify the render is
`local` with sample rate zero, and recreate only Backend. Do not downgrade the
database or delete Java.
