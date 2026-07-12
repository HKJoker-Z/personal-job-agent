# Backup and Restore

## Backup Scope

Backups contain the runtime SQLite `app.db`, the writable `PROJECT_KNOWLEDGE.md`, and `manifest.json`. The manifest records application version, UTC creation time, logical filenames, and SHA-256 checksums.

Backups exclude `.env`, API keys, Monitoring admin tokens, logs, temporary uploads, generated exports, and other host files. Never commit `runtime/backups`.

## SQLite Online Backup

Run `scripts/backup.sh`. The implementation uses `sqlite3.Connection.backup`, writes into an incomplete temporary directory, verifies the output, and atomically renames the completed timestamp directory. It does not copy an actively written SQLite file with a plain filesystem copy.

Custom paths are supported:

```bash
scripts/backup.sh \
  --database-path /path/to/app.db \
  --project-knowledge-path /path/to/PROJECT_KNOWLEDGE.md \
  --backup-dir /path/to/backups
```

For scheduled backups, invoke the same script from a host scheduler and restrict permissions. Example daily cron entry (adjust the checkout path):

```cron
15 2 * * * cd /opt/personal-job-agent && ./scripts/backup.sh >> /var/log/pja-backup-status.log 2>&1
```

Define retention appropriate to available disk space, keep multiple generations, protect the status log, and periodically test restore against a temporary runtime. No automatic cloud backup is included.

## Restore Verification and Protection

Stop backend writes before restoring. Select one explicit backup directory; the restore tool never silently chooses the latest backup:

```bash
scripts/restore.sh \
  --backup runtime/backups/YYYYMMDD-HHMMSS \
  --confirmation "RESTORE BACKUP"
```

The wrapper stops the Compose backend to prevent writes, then restore verifies the manifest, allowed logical filenames, checksums, SQLite integrity, and required tables. It rejects absolute paths and traversal entries. If current database and knowledge files exist, a pre-restore backup is created first. Replacement files are staged and atomically renamed; `.env` and secrets are never restored. The wrapper restarts the backend and checks `/api/ready`.

Restart the backend after restore and run `/api/ready`. Restoration requires an intentional write-stop window and does not provide a complete automatic rollback system. Test disaster-recovery procedures with temporary data before relying on them operationally.
