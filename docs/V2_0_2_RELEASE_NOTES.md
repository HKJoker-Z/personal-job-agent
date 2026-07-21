# Version 2.0.2 — PostgreSQL 16 Backup and Restore Compatibility

## Status

Version 2.0.1 was formally released but never deployed to production. Its production promotion was safely stopped when the mandatory Restore rehearsal failed. Version 2.0.2 supersedes it as the production target; production upgrades directly from Version 2.0.0.

## Included product behavior

Version 2.0.2 contains every Version 2.0.1 user feature: Remember Me with bounded server-side Sessions, email-only browser persistence, unified responsive navigation, simplified Resume-to-JD Analyze, Project Knowledge PostgreSQL FTS RAG with evidence reconciliation, History, Profile/Resumes, monitoring, and retained Worker/Outbox infrastructure. Jobs, Rankings, Applications, Approvals, and Tasks remain retired. There are no database schema changes and no product changes beyond Version 2.0.1.

## Root cause and fix

The blocked backup was created and restored with PostgreSQL client 17.10 against PostgreSQL 16. The archive emitted `SET transaction_timeout = 0`, which PostgreSQL 16 does not recognize; strict `--exit-on-error` correctly rejected the incomplete restore.

Version 2.0.2:

- pins the Backend backup/restore package to `postgresql-client-16`
- retains the production PostgreSQL 16.9 server image at its existing immutable digest
- uses the same immutable Backend digest for backup and restore tools
- refuses dump before output unless server, `pg_dump`, `pg_restore`, and `psql` majors all equal 16
- refuses restore before writes unless manifest dump major, restore major, and target major all equal 16 and the tool digest matches
- records safe server/client versions, server/tool digests, archive SHA-256, Alembic/application versions, row counts, table aggregates, foreign keys, sequences, indexes, ownership, files, and Project Knowledge checksums
- uses a custom archive, no owner/ACL, one exported snapshot for dump and inventory, atomic completion, `--exit-on-error`, and `--single-transaction`
- adds a real isolated PostgreSQL 16 Backup/Restore CI rehearsal and PostgreSQL 17 pre-write negative tests
- rejects floating tool images and keeps logs free of database URLs, passwords, and provider keys

No dump SQL or custom archive is edited. No error is ignored. The failed prior backup is retained for diagnostics and marked incompatible with the approved PostgreSQL 16 restore path; a new PostgreSQL 16 backup and successful strict rehearsal are mandatory before deployment.

## Deployment and rollback

Deploy only Version 2.0.2 Backend/Frontend immutable digests after every release, backup, Restore, Project Knowledge, candidate, HTTPS, security, and Version 2.0.0 rollback gate passes. Version 2.0.1 artifacts remain immutable and are not deployed or used for rollback. PostgreSQL/Redis Volumes and Version 1.9 rollback assets remain untouched.
