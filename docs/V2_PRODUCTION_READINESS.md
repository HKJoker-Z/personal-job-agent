# Version 2 Production Readiness

Version 2.0.4 provides deployable configuration and validation, but this development task does not deploy production.

## Required configuration

Production startup rejects SQLite, absent or public/non-private Redis targets, insecure Session Cookies, missing trusted Origins or fingerprint key, missing model cost rates, invalid database/Worker limits, and enabled API docs. Secrets belong only in the untracked production environment file. Run `docker compose --env-file .env.production config --quiet` before change control.

## Network and container boundary

Only the frontend port is published. Backend 8000, PostgreSQL 5432, and Redis 6379 use Compose `expose` on private networks and must not be host-published. PostgreSQL and Redis live on an internal data network. Application containers use a non-root UID where practical, read-only roots, bounded tmpfs, `no-new-privileges`, dropped capabilities, CPU/memory limits, stop grace periods, and rotated JSON logs.

## Security controls

Use Secure/HttpOnly/SameSite Cookies, Session-bound CSRF, trusted Origin/Host/CORS lists, CSP and security headers, bounded request/upload bodies, login throttling/lockout, privacy-aware logs, and the existing admin Session revoke CLI. Queue data is JSON and safe-ID only. PostgreSQL remains authoritative. Never place credentials or business text in Redis, Events, Outbox safe payloads, logs, or URLs.

## Migration and backup runbook

1. Check free disk space and database connectivity.
2. Create and verify a PostgreSQL/private-files/Project-Knowledge backup before migration.
3. Allow the Compose pre-migration backup job to complete.
4. Run Alembic under the PostgreSQL advisory migration lock.
5. Confirm `alembic current` equals the single head `20260717_04` and run `alembic check`.
6. Confirm PostgreSQL, Redis, Worker heartbeat, backend, and frontend readiness.
7. Retain the verified backup according to the operator retention policy.

Restore requires the exact confirmation phrase and an empty target database/files directory. Verification compares the Alembic revision, table row counts, manifest hashes, and restored private-file checksums. Practice restore in an isolated environment before any production change.

## Operational checks

- Alert when no ready/busy Worker heartbeat is current, Outbox failed/pending age grows, a Dead Letter is created, Redis readiness fails, disk crosses the configured minimum, or database connections approach the configured pool limit.
- Restarting Redis or a Worker must not change PostgreSQL Run state. The dispatcher recovers orphaned deliveries, and Worker leases recover interrupted Steps.
- Cancellation is cooperative at Step boundaries; a provider request already in flight may finish and its usage must still be recorded.
- Do not bypass Approval, evidence validation, budget checks, or retry acknowledgment during incidents.

## Release boundary

Opening the Version 2.0.4 PR does not authorize Merge, a `v2.0.0` Tag/Release, GHCR publication, production deployment, or any change to the current 8080 service. Those require a separate reviewed release procedure after all PR checks succeed.
