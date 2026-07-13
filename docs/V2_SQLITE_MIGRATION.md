# Version 1.9 SQLite to Version 2 PostgreSQL Migration

## Safety model

The migration CLI opens the source SQLite database in read-only/query-only mode, runs `integrity_check`, accepts only the reviewed Version 1.9 table set, fingerprints the file, and confirms its size, mtime, and SHA-256 did not change. Unknown business tables cause a refusal. The PostgreSQL target must already be at Alembic head and the owner account must already exist.

Migration is transactional. Existing conflicting primary keys cause a refusal. Each known table records source/target row counts and a content-free aggregate checksum based on stable IDs, run/workflow IDs, and timestamps. Malformed legacy JSON is normalized to a safe field-specific empty value and counted in the report. Successful migrations record the source fingerprint so reruns are idempotent. PostgreSQL sequences are synchronized after explicit legacy IDs are inserted.

## Dry run

Always stop writes to the Version 1.9 source and create a verified Version 1.9 backup first. Then run a dry inspection:

```bash
cd backend
APP_ENV=production DATABASE_URL='postgresql+psycopg://...' \
  python -m app.cli migrate-v1 \
  --source-sqlite /absolute/read-only/path/app.db \
  --owner-email owner@example.com \
  --dry-run \
  --report /restricted/path/migration-dry-run.json
```

The report contains fingerprints, counts, and checksums, not source Resume or job-description text. Protect it anyway because operational metadata may still be sensitive.

## Execute and verify

For a deliberately test-named target database:

```bash
cd backend
APP_ENV=test \
TEST_DATABASE_URL='postgresql+psycopg://.../personal_job_agent_migration_test' \
MIGRATION_DATABASE_URL='postgresql+psycopg://.../personal_job_agent_migration_test' \
  python -m app.cli migrate-v1 \
  --source-sqlite /absolute/read-only/path/app.db \
  --target-database-url-env MIGRATION_DATABASE_URL \
  --owner-email owner@example.com \
  --execute \
  --report /restricted/path/migration.json
```

Repeat with `--verify-only` to validate the recorded fingerprint and table summaries. Production execution is intentionally not a casual default; it must be performed in a separately approved deployment/migration window with backups, stopped writes, least-privilege credentials, and rollback instructions. Phase 1 development must never run this against the live Version 1.9 database.
