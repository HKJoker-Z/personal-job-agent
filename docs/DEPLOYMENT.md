# Version 2.0.2 deployment and rollback

Version 2.0.1 was released but never deployed. Version 2.0.2 contains all of its user features and replaces it as the only Version 2 production upgrade target. Production moves directly from Version 2.0.0 to Version 2.0.2; Version 2.0.1 is neither an intermediate deployment nor a rollback target.

## Production artifacts

Use `deploy/production/compose.yaml` and stage its referenced Nginx, Redis initialization, and PostgreSQL role scripts under the restricted release directory. Keep `production.env`, TLS private keys, and host Redis configuration outside Git. Do not read or print production secrets. Set `BACKEND_IMAGE` and `FRONTEND_IMAGE` to the released Version 2.0.2 GHCR `@sha256` references and set `RELEASE_VERSION=2.0.2`.

The production database stays on the existing PostgreSQL 16.9 digest and retained Volume. The backup service uses the immutable Backend digest as its controlled PostgreSQL 16 tool image. Backend, PostgreSQL, and Redis ports remain unpublished.

## Hard pre-deployment gates

Stop before cutover unless every item passes:

1. The Version 2.0.2 PR is merged with a merge commit, all required PR/main checks pass, the annotated tag and non-prerelease Release exist, and release images have verified immutable digests.
2. The Version 2.0.1 tag, Release, and image digests remain unchanged.
3. A new production backup reports server/`pg_dump`/`pg_restore` major 16, valid manifest/checksum, Alembic `20260717_04`, complete row counts, validated foreign keys, matching sequences/ownership/aggregate checksums, private-file hash, and Project Knowledge hash.
4. That exact new backup restores with `--exit-on-error --single-transaction` into a fresh isolated PostgreSQL 16 Compose project with private network and temporary Volume. No ignored errors are allowed.
5. The prior incompatible backup remains preserved and is marked `RESTORE_INCOMPATIBLE_WITH_POSTGRESQL_16` without modification.
6. Current Version 2.0.0 backend/frontend digests, Compose/runtime configuration, Project Knowledge, new PostgreSQL 16 backup, and exact rollback commands are preserved and verified. Version 1.9 rollback assets remain intact.
7. Runtime Project Knowledge is backed up and hashed, replaced atomically with the reviewed Version 2.0.2 Git baseline, rebuilt through the supported mechanism, and verified by status, PostgreSQL FTS search, and fictional Mock RAG-off/RAG-on reconciliation.
8. The isolated candidate on `127.0.0.1:18089` passes exact 2.0.2 health/readiness, PostgreSQL/Redis/Worker/Outbox, Login/Remember Me/email-only persistence/password non-persistence/Secure Cookie/CSRF/Logout, unified responsive navigation, retired route and mutation 410s, Profile/Resumes/Analyze/History, Mock RAG checks, Backup/Restore, restart persistence, HTTPS, and rollback rehearsal.

Never bind the candidate to `0.0.0.0`, use port 8080 before cutover, call real DeepSeek, delete a PostgreSQL/Redis Volume, run `docker compose down -v` or Docker prune, or modify Mihomo, `pja-br0`, or policy preference 8999.

## Cutover

After every gate passes, use the existing safe switch to move directly from Version 2.0.0 to immutable Version 2.0.2 images on public 8080. Do not deploy Version 2.0.1. Record the switch timestamp and downtime.

After switching, require at least 150 consecutive `/api/health` responses reporting exactly `2.0.2`; any 2.0.1, 2.0.0, 1.9, error, or version instability stops acceptance. Verify HTTPS/certificate and several external network paths, authentication and CSRF, unified navigation, retired mutation boundaries, Project Knowledge retrieval, PostgreSQL, Redis, Worker, Outbox, restart counts, and unchanged host routing. Remove the localhost 18089 candidate only after public acceptance.

## Rollback

On any deployment failure, restore the saved Version 2.0.0 immutable image digests and Compose/runtime configuration. Version 2.0.1 is not a rollback target because it was never deployed and retained the old backup-tool defect. Restore data only for a separately verified data incident and only from the new PostgreSQL 16-compatible backup after its strict rehearsal.

Do not delete or overwrite database/Redis Volumes, tables, backups, Version 2.0.1 artifacts, or Version 1.9 assets. Do not alter Mihomo, `pja-br0`, preference 8999, or shared Git history.
