# Version 2 PostgreSQL 16 and Private File Backup

## Compatibility policy

Production PostgreSQL 16 backups and restores use PostgreSQL 16 client tools from the same controlled Backend image. The Backend image installs the explicitly major-pinned `postgresql-client-16` package; production supplies the Backend as a full immutable GHCR `@sha256` reference. The PostgreSQL server remains pinned to `postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7`.

Before a dump, the tool reads `SHOW server_version` and `SHOW server_version_num`, executes `pg_dump --version`, `pg_restore --version`, and `psql --version`, and parses their numeric majors. It refuses the operation before creating a dump unless every major is 16. `POSTGRES_SERVER_IMAGE` and `POSTGRES_TOOL_IMAGE` must be immutable `name@sha256` references; floating `latest`, `postgres:17`, and unqualified tool images are rejected.

Restore repeats the preflight and additionally requires:

- archive `pg_dump` major = current `pg_restore` major = target server major = 16
- the same controlled tool-image digest used for backup and restore
- a valid Version 2 manifest and exact archive checksum
- a completely empty target database, empty file directory, and nonexistent Project Knowledge target

Do not edit SQL, filter `transaction_timeout`, modify a custom archive, remove `--exit-on-error`, or permit ignored errors. A dump created by a newer major client is not an approved production restore path to an older server.

## Backup contents

A completed `v2-*` directory contains exactly:

- `postgres.dump`: PostgreSQL custom archive, public schema, no owner, no ACL
- `files.tar.gz`: private file-storage contents under safe relative paths
- `PROJECT_KNOWLEDGE.md`: runtime Project Knowledge
- `manifest.json`: manifest version, application version, creation time, Alembic revision, server version/major/image digest, `pg_dump`/`pg_restore`/`psql` versions and majors, tool-image digest, expected restore major, archive format/SHA-256, all public table row counts and safe per-table checksums, foreign-key/index/sequence/ownership checksums, and aggregate checksum

The manifest contains no database URL, password, API key, Session/CSRF plaintext, Resume/JD content, prompt, or provider response. Database statistics and `pg_dump` share one exported repeatable-read snapshot, so the archive, row counts, and aggregate checksums describe the same database state. A hidden incomplete directory is atomically renamed only after the dump, `pg_restore --list`, file archive, knowledge copy, and manifest creation all succeed.

## Production backup

Use the production Compose `backup` profile. It obtains PostgreSQL clients and `POSTGRES_TOOL_IMAGE` provenance from the same immutable Backend image selected by `BACKEND_IMAGE`; it does not rely on host-installed clients.

```bash
docker compose --env-file /restricted/path/production.env \
  -f /restricted/release/compose.yaml --profile tools run --rm backup
```

Do not print or inspect `production.env`. Pass secrets only through the existing restricted environment file. The direct `scripts/backup-v2.sh` wrapper is suitable only when the operator has independently established PostgreSQL 16 clients and supplies accurate immutable `POSTGRES_SERVER_IMAGE` and `POSTGRES_TOOL_IMAGE` metadata.

## Verification and guarded restore

Verification takes one explicit backup directory and checks the exact file set, manifest schema, all SHA-256 values, and every tar member. Restore uses:

```text
pg_restore --no-owner --no-privileges --exit-on-error --single-transaction
```

After PostgreSQL returns zero, the tool recomputes and compares the complete database inventory: Alembic revision, every public table and row count, safe table aggregate checksums, validated foreign keys, sequence values/state, indexes including Project Knowledge FTS, and ownership mapping. Because the controlled archive uses `--no-owner`, any expected source-role to restore-role change must be declared explicitly with a narrow `--allowed-owner-mapping SOURCE_ROLE=TARGET_ROLE`; every undeclared ownership change remains a hard failure. A different isolated target database name likewise requires the explicit `--allow-isolated-database-name-difference` policy after target identity has already been proven. PostgreSQL physical OIDs and ACLs intentionally omitted by the no-privileges policy are reported as normalized environment metadata rather than data mismatches. It then restores private files and Project Knowledge. Any nonzero restore, missing object, count/checksum difference, invalid foreign key, sequence/index/ownership difference, or file error prevents success from being reported.

## Strict rehearsal

`scripts/postgres16-restore-regression.sh` creates a uniquely named Compose project with separate source and restore internal networks, separate temporary PostgreSQL 16 volumes, no published database port, an empty target database, and controlled tool containers. It proves PostgreSQL 17 clients are rejected before dump and restore writes, completes a PostgreSQL 16 custom dump and strict restore, validates data/inventory/files/Project Knowledge/application readiness, writes a sanitized JSON report, and removes only the explicitly named temporary containers, networks, and volumes.

Production deployment remains blocked until an equivalent rehearsal of the new production backup passes. The incompatible Version 2.0.1-era backup must be retained and marked `RESTORE_INCOMPATIBLE_WITH_POSTGRESQL_16`; it must not be the sole rollback backup.
