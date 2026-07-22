# Version 2.0.3 deployment and rollback

Version 2.0.3 is the current production release. This runbook records its
promotion from Version 2.0.2 and remains the rollback reference. The release
changed resilient analysis behavior and Primary Resume upload/selection;
navigation, authentication, retired-feature boundaries, Redis/Worker/Outbox
topology, TLS, Mihomo, `pja-br0`, and policy preference 8999 were unchanged.

## Production artifacts

Use `deploy/production/compose.yaml`. Keep `production.env`, TLS private keys, host Redis configuration, Resume files, and runtime Project Knowledge outside Git. Do not print secrets. Set Backend and Frontend to the released Version 2.0.3 GHCR `@sha256` references and `RELEASE_VERSION=2.0.3`.

Backend 8000, PostgreSQL 5432, and Redis 6379 must remain unpublished. The production PostgreSQL 16 and Redis volumes are retained.

## Pre-deployment gates

Stop before cutover unless all of these pass:

1. The Version 2.0.3 PR is merge-committed; required PR and main checks pass; annotated tag `v2.0.3`, formal Release, and immutable image digests exist.
2. Existing tags/releases, especially `v2.0.2`, are unchanged.
3. PostgreSQL backup, current Compose/configuration, exact Version 2.0.2 image digests, private Resume files, and runtime Project Knowledge are saved with hashes where supported.
4. The new PostgreSQL backup reports matching PostgreSQL 16 server/client tools, a verified manifest and checksum, and Alembic `20260717_04` before migration. Rehearse that exact backup once in an isolated PostgreSQL 16 target.
5. Validate Alembic upgrade to `20260721_05` in an isolated database, including Resume preservation, newest-active backfill, and the one-active-primary constraint.
6. Apply the production migration without dropping Resume data and confirm readiness.
7. Start immutable Version 2.0.3 images as an internal candidate only on `127.0.0.1:18090`.
8. Candidate acceptance covers exact health 2.0.3, readiness, healthy containers, PDF/DOCX/TXT/Markdown upload, latest-upload primary selection, Analyze auto-selection, standard/tolerant/fallback analysis, RAG, History, PostgreSQL, Redis, Worker, Outbox, and stable restart counts. Mock responses may validate tolerant/fallback behavior; no production DeepSeek call is required.

Never bind the candidate publicly, use 8080 before cutover, delete volumes, run `docker compose down -v`/prune, or modify production networking/TLS.

## Cutover

After every gate passes, use the existing safe switch to place immutable Version 2.0.3 images on public 8080. Record the Asia/Shanghai switch timestamp.

After switching, require 100 consecutive `/api/health` responses reporting exactly `2.0.3`. Verify HTTPS and Login; PDF/DOCX/TXT/Markdown upload; Primary Resume selection; Analyze default Resume; complete, normalized, and fallback behavior; RAG and History; healthy PostgreSQL/Redis/Worker/Outbox; stable restart counts; and no public Backend/PostgreSQL/Redis ports. Remove the 18090 candidate only after public acceptance.

## Rollback

On deployment failure, restore the saved Version 2.0.2 immutable image digests and Compose/runtime configuration. Preserve PostgreSQL/Redis volumes, Resume files, backups, and Project Knowledge. The additive `is_primary` column is compatible with the prior application, so ordinary image rollback does not require downgrading or deleting data.

Restore the database only for a separately confirmed data incident and only from the verified PostgreSQL 16 backup. Do not modify any existing tag/Release or shared Git history.
