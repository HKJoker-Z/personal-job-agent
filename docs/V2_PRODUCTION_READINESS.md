# Version 2.0.2 production readiness

Version 2.0.2 is the production replacement for the released-but-never-deployed Version 2.0.1. It retains the complete 2.0.1 product behavior and adds no schema migration. Promotion is allowed only after PR/main CI, strict PostgreSQL 16 backup/restore, immutable image publication, Project Knowledge replacement/reindex, an isolated `127.0.0.1:18089` candidate, HTTPS/security checks, and Version 2.0.0 rollback verification all pass.

## PostgreSQL backup and restore gate

- Server, `pg_dump`, `pg_restore`, and `psql` majors must all be 16.
- Production PostgreSQL and tool images must be immutable `@sha256` references; `latest`, PostgreSQL 17, or an unqualified client package fails repository/runtime safety.
- The manifest must include server/tool versions and digests, custom archive SHA-256, application/Alembic versions, complete row counts, table aggregates, foreign keys, sequences, indexes, ownership, and overall aggregate checksum, without secrets.
- Restore must start from a verified archive and empty isolated PostgreSQL 16 target on private networks and a new temporary Volume. It uses the same controlled tool digest with `--exit-on-error --single-transaction` and reports success only after exact inventory, file, Project Knowledge, and readiness checks.
- Editing SQL/custom archives, filtering `transaction_timeout`, ignoring restore errors, using a nonempty target, or weakening restore options is prohibited.
- The incompatible 17-client backup remains preserved for diagnostics but cannot be the only rollback backup.

`scripts/postgres16-restore-regression.sh` implements the real CI rehearsal and PostgreSQL 17 negative gates. Its sanitized report is retained as a workflow artifact. Any checksum, restore exit, row-count, aggregate, foreign-key, sequence, index, ownership, Project Knowledge, file, or readiness difference stops the release.

## Application and security gates

Only Edge 8080 is public. Backend 8000, PostgreSQL 5432, and Redis 6379 remain unpublished. Production requires private authenticated Redis, Secure/HttpOnly/SameSite=Lax Sessions, explicit trusted Origins/Hosts, CSRF, authentication fingerprinting, disabled API docs, configured provider cost rates, and `MOCK_PROVIDER_ENABLED=false`. Acceptance never calls real DeepSeek.

Jobs, Rankings, Applications, Approvals, and Tasks remain unavailable in the UI and return HTTP 410 through authenticated API boundaries; their historical tables and rows remain present for compatibility and rollback. Remember Me changes only bounded server-side Session expiry, remembered email persists email only, and application code never persists plaintext passwords or tokens.

## Promotion stop conditions

Stop on any failed PR/main/release workflow; unexpected server/client major or floating image; checksum/manifest/strict Restore/inventory failure; secret exposure; Project Knowledge index or retrieval failure; candidate, HTTPS, Secure Cookie, CSRF, Remember Me, navigation, retired-mutation, readiness, or version failure; inability to restore Version 2.0.0; or any requirement to delete a production Volume or change Mihomo, `pja-br0`, or preference 8999.
