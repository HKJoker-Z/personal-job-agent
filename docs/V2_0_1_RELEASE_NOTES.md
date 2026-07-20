# Version 2.0.1 — Simplified Workspace and Project Knowledge RAG

## Highlights

- Secure Remember Me with bounded server-side Sessions and browser-session behavior when off
- optional normalized email-only LocalStorage persistence; plaintext passwords are never stored
- one responsive, accessible authenticated navigation
- retirement of Jobs, Job Rankings, Applications, Approvals, and Tasks
- direct Resume Version/upload plus pasted JD/safe URL Analyze flow
- actual Project Knowledge PostgreSQL FTS retrieval, trusted prompt evidence, skill reconciliation, safe sources, and evidence mapping
- Project Knowledge rewritten for the PostgreSQL 16, Redis 7, Dramatiq, Outbox, HTTPS production stack
- idempotent Redis init, correct Nginx tmpfs ownership, unique Docker aliases, exact health version checks, and rollback-safe production configuration

## Data and database impact

There is no new Alembic revision. Current head remains `20260717_04`. Retired feature tables and every historical row remain present. Authenticated retired endpoints return 410 and cannot create, update, or delete those resources.

## Security

Session cookies remain Secure/HttpOnly/SameSite=Lax. Login rotates Sessions; logout and password change revoke Sessions. Remember Me has an absolute maximum of 30 days. RAG evidence is scanned and data-only. Unsupported skills are removed and unsupported generated claims block the generated letter.

## Upgrade and rollback

Deploy only immutable GHCR digests after a verified PostgreSQL/Files/Project-Knowledge backup and isolated candidate. Runtime Project Knowledge is never overwritten without hash, backup, comparison, replace, rebuild, and search/Analyze verification. Roll back to saved Version 2.0.0 digests/config without deleting volumes or historical tables.

## Limitations

AI output requires human review. The service does not automatically submit applications. PostgreSQL retrieval is lexical, the architecture is single-host Compose, and historical Approval-based Agent Runs cannot be resumed in this release.
