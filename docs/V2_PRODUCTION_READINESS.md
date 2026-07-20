# Version 2.0.1 production readiness

Production promotion is allowed only after PR checks, main CI, immutable image publication, verified backups, an isolated candidate on `127.0.0.1:18089`, and exact health-version assertions all pass.

## Required security configuration

Production must use PostgreSQL, a private authenticated Redis service, Secure/HttpOnly/SameSite=Lax Session cookies, explicit trusted Origins/Hosts, an authentication fingerprint key, provider cost rates, disabled API docs, and `MOCK_PROVIDER_ENABLED=false`. Normal Session defaults are 30 idle minutes and 24 absolute hours. `REMEMBER_ME_SESSION_TTL_DAYS` is bounded to 1–30 and defaults to 30.

Only Edge 8080 is public. Backend 8000, PostgreSQL 5432, and Redis 6379 remain un-published. Production images are supplied as full GHCR `@sha256` references.

## Retired features and data

Jobs, Rankings, Applications, Approvals, and Tasks return 410 through the full authenticated app and cannot mutate. No Version 2.0.1 migration drops their tables. Backup and restore must still include all historical rows. Waiting Approval Agent Runs are read-only/cancellable.

## Runtime regression gates

`scripts/test-v201-production-runtime.sh` verifies:

- Redis initialization succeeds three consecutive times without unconditional recursive ownership changes
- Edge is read-only, UID/GID 101, writable tmpfs, `no-new-privileges`, and `cap_drop: ALL`
- Backend and Frontend use unique `backend-v2` and `frontend-v2` aliases
- Nginx contains no ambiguous `backend` or `frontend` upstream
- Edge joins only the application network
- an Edge-side network probe resolves the v2 alias but cannot resolve an isolated v1 service or its legacy alias
- all application images are immutable digest references
- health assertions reject a mismatched release version

At cutover, the retained Version 1.9 container must be detached from the shared `job-agent_application` network so the Version 2 Edge cannot resolve it. Preserve the exact reconnect command for rollback. Do not alter `pja-br0`, policy rule preference 8999, the routing service, or Mihomo.

## Backup and migration gate

Before deployment, create and verify a PostgreSQL/private-files/Project-Knowledge backup, save current Compose/runtime overrides and Version 2.0.0 image digests, check disk and certificate renewal state, and rehearse restore into an isolated database. Alembic must report current=head=`20260717_04` and `alembic check` clean. There is no new Version 2.0.1 revision.

Stop the release on any failed test, backup, restore, candidate, HTTPS, Secure Cookie, CSRF, RAG evidence, unsupported-claim, or version assertion.
