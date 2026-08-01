# Java Normalization Production Stage 2 Preparation Work Report

## 1. Repository and starting point

- Repository: `https://github.com/HKJoker-Z/personal-job-agent`
- Starting `main`: `603ec9cf609cb02a2f9f10dc92aff0ce2cd10ce7`
- Branch: `ops/java-normalization-production-stage-2-local`
- Production phase: IVB, integrated Backend deployment with normalization mode
  remaining `local`
- Starting production version: `2.0.4`
- Starting production Alembic revision: `20260724_06`
- Repository Alembic head: `20260730_07`

Stage IVA report PR #38 was already merged normally as
`603ec9cf609cb02a2f9f10dc92aff0ce2cd10ce7`. The private
`pja-java-normalization` service was healthy on
`pja-java-normalization-internal`, with no host port, restart count zero, and
OOM-killed false when Phase IVB preparation began.

## 2. Exact scope

This branch prepares only the operational bridge needed to deploy the already
merged Python Java-client and execution-fingerprint code while keeping Java
behavior inactive:

- one production Compose override for the integrated Backend image, explicit
  local mode, Backend-only Java network attachment, and read-only existing key
  mount;
- one manual immutable Backend-only publication workflow;
- placeholder-only production configuration names;
- focused production topology regression assertions;
- the Phase IVB operations extension; and
- this Work Report and the Work Report index.

No FastAPI, Java, Frontend, migration, normalization policy/dictionary, Redis,
Worker, Outbox, Nginx, or database runtime source is changed.

## 3. Exact changed files

- `.env.production.example`
- `.github/workflows/backend-production.yml`
- `deploy/production/compose.java-normalization-stage-2.override.yaml`
- `docs/operations/JAVA_NORMALIZATION_PRODUCTION_ROLLOUT.md`
- `scripts/test-v201-production-runtime.sh`
- `docs/work-reports/2026-08-01-java-normalization-production-stage-2-preparation-work-report.md`
- `docs/work-reports/README.md`

## 4. Production Compose and network changes

The new override is additive to the established production base and its
existing host-specific safety/cutover overrides. It does not replace or
redesign the production Compose system.

It declares the already operator-owned external network
`pja-java-normalization-internal` and attaches only `backend`. PostgreSQL,
Redis, Worker, Outbox, Frontend, Edge/Nginx, and the one-shot migration and
backup tools are not attached. Java remains in its separate
`pja-java-normalization` project and retains its Phase IVA topology.

The override uses one required immutable `BACKEND_IMAGE` reference for
`migrate`, `worker`, `outbox-dispatcher`, `backend`, and the backup profile.
This prevents long-running Python consumers and later one-shot tools from
silently resolving different application code.

## 5. Local-mode configuration

`ANALYSIS_JD_NORMALIZATION_MODE=local` is explicit on Backend, Worker, and
Outbox. Backend also receives:

- private origin `http://java-normalization:8080`;
- key-file path `/run/pja-secrets/java-normalization-api-key`; and
- shadow sample rate `0`.

Merged source loads the Java base URL and key and constructs the application-
scoped HTTP client only in `shadow` or `java`. In `local`, it creates no Java
client, does not read the key, performs no Java DNS lookup/request, and keeps
the existing FastAPI local preprocessing authoritative.

No configuration permits `shadow` or `java` in this phase.

## 6. Secret mount and handling

The existing Phase IVA key remains at the root-controlled host path
`/etc/personal-job-agent/java-normalization/api-key`. Phase IVB does not rotate,
replace, copy, or print it. Backend mounts that exact file read-only at
`/run/pja-secrets/java-normalization-api-key`; no other Python service mounts
it. The key is not a Compose literal, environment value, image layer, report
value, or health response.

The source remains protected by the reviewed Phase IVA directory/file
ownership and modes. The matching UID/GID `10001:10001` permits only the
non-root Backend process to read the mounted file after a future separately
reviewed mode change.

## 7. Python image publication plan

`.github/workflows/backend-production.yml` is manual for publication and
pull-request-triggered for validation. It uses minimum default permissions and
immutable third-party action SHAs. Before publication it runs:

- the complete Backend unit/regression suite;
- the opt-in PostgreSQL 16 integration suite, including the execution-binding
  migration and constraints; and
- production Compose, topology, local-mode, script, and secret safety checks.

Only `ghcr.io/hkjoker-z/personal-job-agent-backend` is published, tagged
`sha-<full-commit>`. Production deploys the registry digest, not that tag. OCI
source, revision, application version `2.0.4`, non-root user, image metadata,
history, and secret absence are verified. The workflow publishes no Frontend
or Java image, mutable production tag, migration-only image, repository tag,
or GitHub Release.

## 8. Backup and migration plan

Immediately before the first production mutation, the approved read-only
preflight must reconfirm Version `2.0.4`, Alembic `20260724_06`, Java health and
isolation, all existing production health/restart/OOM state, at least 1.5 GiB
available RAM, at least 6 GiB available root disk, and non-conflicting
topology.

The current production Compose `backup` profile will create exactly one new
timestamped PostgreSQL 16/private-file backup using the existing immutable
Backend tool image and restricted production environment. The exact backup
will be verified for file set, nonempty archive, manifest, checksum, server and
client major 16, application version, Alembic `20260724_06`, and safe inventory
aggregates.

That exact backup will be restored once into a uniquely named PostgreSQL 16
container and volume on an internal-only disposable network with no host port.
Only schema and inventory metadata will be inspected. On the same restored
copy, the reviewed integrated Backend will upgrade
`20260724_06 -> 20260730_07`, validate the six nullable execution-binding
columns and four named constraints, and prove a second upgrade is a no-op.
Only that isolated environment will then be removed.

Production uses the same reviewed one-shot Alembic command, without `stamp`,
`--fake`, revision edits, or a downgrade. It verifies one head before/after,
metadata-only columns/constraints, and a second no-op upgrade. The revision is
additive and leaves legacy rows nullable.

## 9. Service cutover order

After migration verification:

1. verify the still-running previous Backend remains healthy against the
   additive `20260730_07` schema;
2. install the reviewed override and a separate root-controlled environment
   file containing only the immutable Backend reference;
3. pull the immutable digest;
4. recreate only Worker and Outbox and wait for health; and
5. recreate only Backend and wait for readiness.

PostgreSQL, Redis, Frontend, Edge/Nginx, Java, and their volumes/networks are
not recreated. No `/api/analyze` request is used for validation.

## 10. Rollback plan

The previous production Backend digest and exact production configuration are
recorded before cutover. If the new Python deployment fails, the override's
immutable Backend reference is changed back and only Backend, Worker, and
Outbox are recreated, still with mode `local`.

Production remains at additive Alembic `20260730_07`; no schema downgrade is
required. Compatibility is demonstrated before cutover by the previous
Backend remaining healthy after migration. Java remains independently healthy
and private, and its key/network can remain for later Phase IVC review. No
History, idempotency, Redis, or user-data transformation is part of rollback.

## 11. Validation before merge

The authoritative final validation record will be added to this report at the
final pull-request head. Required gates include:

- Bash syntax and ShellCheck through repository CI;
- production Compose rendering and topology assertions;
- complete Backend tests;
- PostgreSQL 16 integration tests;
- migration and backup/restore regressions;
- Backend/Frontend image and v2 Mock smoke regressions;
- repository safety and secret scans;
- Java verify, normalization-only smoke, and isolated candidate regression
  required by repository branch protection; and
- CLEAN/MERGEABLE GitHub state with all required contexts passing.

## 12. Delivery metadata

- Preparation PR: pending creation
- Preparation commits: pending final metadata commit
- Merge method: normal merge commit required
- Merge commit: pending merge

## 13. Risks and limitations

- Production uses an established host-specific base Compose and several
  historical safety/cutover overrides. The new file must remain the final
  additive override; it must not replace those files.
- The host has finite disk and memory. Image/backup creation proceeds only
  above the reviewed floors and no Docker prune is authorized.
- A point-in-time healthy local-mode deployment does not validate Java calls,
  shadow equality, provider behavior, or performance.
- Mounting the key and network in local mode prepares topology only; it does
  not prove future shadow behavior.
- Migration rollback is application-image rollback against an additive schema,
  not a schema downgrade.

## 14. Preparation boundary confirmations

- Production was not modified during preparation of this PR.
- Production remained Personal Job Agent `2.0.4` at Alembic `20260724_06`.
- No version was bumped.
- No image was published or deployed.
- No migration was run or edited.
- No Java runtime code or image was changed.
- No FastAPI runtime source was changed.
- No Java request or `/api/analyze` request was made.
- Shadow and Java-authoritative modes were not enabled.
- No user data was inspected.
- No DeepSeek or other external LLM was called.
- No repository tag or GitHub Release was created.
