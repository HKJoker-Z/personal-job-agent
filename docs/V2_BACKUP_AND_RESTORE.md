# Version 2 PostgreSQL and Private File Backup

## Backup contents

A completed `v2-*` backup directory contains exactly:

- `postgres.dump`: custom-format PostgreSQL dump without ownership or grants
- `files.tar.gz`: private file-storage contents under relative paths
- `PROJECT_KNOWLEDGE.md`: the writable Project Knowledge file
- `manifest.json`: application version, UTC time, Alembic revision, table row counts, and SHA-256 checksums

Environment files, Cookies, Session/CSRF plaintext, logs, and unrelated runtime paths are excluded. Run the command with an account allowed to read UID 10001 private files and write the restricted backup destination. Do not weaken file modes to make backups work.

```bash
sudo --preserve-env=DATABASE_URL,PYTHON_BIN \
  scripts/backup-v2.sh \
  --backup-dir /restricted/backups \
  --files-root /restricted/runtime/files \
  --project-knowledge /restricted/runtime/project-knowledge/PROJECT_KNOWLEDGE.md
```

The command writes a hidden incomplete directory and atomically renames it only after database dump, file archive, Project Knowledge copy, row-count collection, and manifest checksums succeed.

## Verification

Pass the concrete backup directory, not its parent and not an implicitly selected latest backup:

```bash
sudo env PYTHON_BIN="${PYTHON_BIN:-python3}" \
  scripts/verify-v2-backup.sh \
  --backup /restricted/backups/v2-YYYYMMDD-HHMMSS-xxxxxxxx
```

Verification checks the exact manifest file set, all SHA-256 values, and every tar member before restore. Retention and off-host encrypted copies remain operator responsibilities. Periodically test a restore into an isolated database and empty temporary file tree.

## Guarded restore

Restore only to an empty PostgreSQL database, empty file directory, and nonexistent Project Knowledge target:

```bash
sudo --preserve-env=DATABASE_URL,PYTHON_BIN \
  scripts/restore-v2.sh \
  --backup /restricted/backups/v2-YYYYMMDD-HHMMSS-xxxxxxxx \
  --files-root /restricted/restore/files \
  --project-knowledge /restricted/restore/project-knowledge/PROJECT_KNOWLEDGE.md \
  --confirmation 'RESTORE V2 BACKUP'
```

The tool verifies the backup first, restores PostgreSQL with `--exit-on-error`, safely extracts data-only archive members, restores Project Knowledge, and compares the Alembic revision and required-table row counts with the manifest. The isolated Smoke additionally compares source/restored file checksums. It never overwrites an existing database, nonempty file tree, or Project Knowledge file.

Restoration requires a controlled maintenance window and an independently tested rollback plan. These scripts do not deploy Version 2, change the live Version 1.9 SQLite database, modify `pja-br0`, or alter host routing.
