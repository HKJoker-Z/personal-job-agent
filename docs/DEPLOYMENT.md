# Version 2.0.1 deployment and rollback

This runbook promotes immutable Version 2.0.1 images without deleting production data or changing the host routing/Mihomo design.

## Production artifacts

The reviewed production definition is `deploy/production/compose.yaml`. Stage these repository files under the restricted release directory:

- `deploy/postgres/init-roles.sh` as `init-roles.sh`
- `deploy/production/redis-init-idempotent.sh`
- `deploy/production/frontend-nginx.conf`
- `deploy/production/edge-nginx.conf`

Keep `production.env`, TLS private keys, and the host Redis configuration outside Git. Set `BACKEND_IMAGE` and `FRONTEND_IMAGE` to full GHCR `@sha256` references. `RELEASE_VERSION` must be `2.0.1`.

## Pre-deployment audit

1. Record `docker compose ps`, health, restart counts, Alembic current/heads/check, public HTTPS, certificate expiry, disk space, networks, routes, and volumes.
2. Save the Version 2.0.0 backend/frontend digests, Compose file, overrides, and exact rollback commands.
3. Verify Version 1.9 rollback assets remain present.
4. Create and verify PostgreSQL, Files, and runtime Project Knowledge backups. Record the Git and runtime Project Knowledge hashes separately.
5. Rehearse restore into an isolated empty database and directories.
6. Run all tests, Docker builds, Compose validation, ShellCheck, repository safety, and `scripts/test-v201-production-runtime.sh`.
7. If a credential appeared in an operator transcript, rotate it before candidate startup and update only host-managed secret configuration.

## Project Knowledge update

Never overwrite the runtime Project Knowledge blindly. Hash and back it up first, compare it with the Git baseline, and record whether it contains operator changes. Only after review, install the approved baseline atomically, call the authenticated rebuild endpoint, check status and PostgreSQL FTS search, and run RAG-off/RAG-on fictional analysis comparisons.

## Isolated candidate

Start an independent Compose project bound only to `127.0.0.1:18089`. Do not use 8080, 18088, 8000, 5173, 5432, or 6379. Use Mock LLM for normal smoke. Validate PostgreSQL, Redis, Alembic, admin login, Remember Me cookie policy, CSRF, navigation build/tests, removed route 410s, Profile, Resume, Analyze off/on, evidence mapping, History, Worker/Outbox, SSE where retained, restart persistence, backup, and restore.

Run `scripts/assert-release-health.sh` against the candidate; a response other than exactly `2.0.1` fails promotion.

## Optional controlled real-provider check

After all deterministic gates pass, use one completely fictional Resume/JD pair for one RAG-off and one RAG-on request with low output-token limits. Confirm Project Knowledge changes evidence-backed matching and sources without unsupported claims. Never use production personal data and never generate or send an application.

## Cutover

1. Confirm the backup and rollback digest/config again.
2. Disconnect the stopped/retained Version 1.9 application container from `job-agent_application`, recording the exact `docker network connect --alias ...` rollback command. Do not delete the container or assets.
3. Start the Version 2.0.1 production services from immutable digests, with Edge connected only to `job-agent_application` and unique aliases.
4. Switch Edge publication from candidate `127.0.0.1:18089` to `0.0.0.0:8080` using the existing safe Compose switch.
5. Verify exact health version, readiness, trusted HTTPS, Login/Remember Me/Logout, Secure Cookie, CSRF, 401/403, navigation, removed routes, Analyze off/on, source metadata, History, PostgreSQL, Redis, Worker, Outbox, restart counts, and backup.
6. Verify `pja-br0`, policy rule preference 8999, routing service, and Mihomo are unchanged.

## Rollback

On any failure, restore the saved Version 2.0.0 immutable image digests and Compose/runtime configuration. If required, detach the Version 2 Edge, reconnect the retained Version 1.9 container with its saved alias, and restore public 8080. Do not run `down -v`, remove PostgreSQL/Redis volumes, delete old images, drop tables, remove backups, or edit Mihomo/routing policy.

If Version 2.0.1 made no schema change, image/config rollback is sufficient. Restore data only when a separately verified data incident requires it.
