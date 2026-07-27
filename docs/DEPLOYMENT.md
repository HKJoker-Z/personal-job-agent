# Version 2.0.4 deployment and rollback

Version 2.0.4 promotes the already merged portfolio architecture and Backend
reliability work from production Version 2.0.3. It preserves HTTPS, Mihomo,
`pja-br0`, routing preference 8999, and private Backend/PostgreSQL/Redis ports.

## Artifacts and backup

Use `deploy/production/compose.yaml` with immutable Backend and Frontend
`@sha256` references and `RELEASE_VERSION=2.0.4`. Keep `production.env`, TLS
keys, Redis configuration, Resume files, and runtime Project Knowledge outside
Git and out of terminal output.

Before deployment, record the Version 2.0.3 component digests; save its Compose
and runtime configuration; and create a new PostgreSQL 16 backup with a verified
checksum and manifest. Preserve the Version 2.0.3 rollback images and config,
the prior Project Knowledge copy, and existing Version 2.0.2/1.9 assets.

Restore that exact backup once into an empty isolated PostgreSQL 16 target.
Upgrade `20260721_05` to `20260724_06` and verify unchanged existing row counts
and checksums, valid foreign keys and sequences, and an empty
`analyze_idempotency_records` table. Do not downgrade production.

## Candidate and Project Knowledge

Start one internal candidate on `127.0.0.1:18091` using the immutable Version
2.0.4 digests and Mock LLM. Require exact 2.0.4 health/readiness, healthy
containers with zero restarts, authentication/CSRF, Resume/Primary Resume,
normal and fallback Analyze, keyed replay/conflict/concurrency behavior,
History, Architecture, optimized Monitoring, healthy PostgreSQL/Redis/Worker/
Outbox, and private service ports.

Before replacing runtime Project Knowledge, hash the Git baseline and runtime
copy, back up the runtime file, and prove it is a known prior Git version. Use
the authenticated replace/rebuild API, then verify PostgreSQL full-text searches
for the release concepts. Stop if the runtime copy contains unknown edits.

## Cutover

After all gates pass, use the existing safe Compose cutover to move public 8080
from Version 2.0.3 to the validated Version 2.0.4 digests. Preserve the external
application network and all volumes. Require 100 consecutive public HTTPS
health responses reporting exactly `2.0.4`, then repeat the bounded functional,
dependency, restart, and private-port checks with synthetic data and precise
cleanup.

Never run `docker compose down -v`, prune Docker resources, expose the candidate
publicly, or call real DeepSeek during release validation.

## Rollback

On failure, restore the saved Version 2.0.3 images and runtime configuration.
Keep the migrated additive schema unless a diagnosed code incompatibility
requires the documented downgrade after Analyze traffic is stopped. Never
delete the idempotency ledger without a verified backup. Preserve all database
and Redis volumes, private files, backups, and both Project Knowledge copies.
