# Version 2.0 Phase 1 Foundation

## Status and scope

Version 2.0 Phase 1 is `2.0.0-alpha.1`. It establishes identity, PostgreSQL, Career Profiles, Resume storage, migration, and recovery primitives. The live Version 1.9 runtime remains the production service until a separately reviewed deployment phase. Phase 1 does not include a production rollout, tag, release, MCP integration, or a replacement AI pipeline.

The transitional application composes the existing Version 1.9 FastAPI routes first and then adds Version 2 routers and default-deny API security middleware. Existing Analyze, History, Project Knowledge, Monitoring, Evaluation, and export code remains available behind authentication. The frontend keeps the existing workspace and adds Login, protected routing, Career Profile, Resume Library, Resume Import, and Account pages.

## Architecture

```text
Browser
  -> Nginx :8080 (only published application port)
    -> FastAPI :8000 (private Compose network)
      -> PostgreSQL :5432 (private; test override binds loopback only)
      -> private file root (host bind, UID 10001, stored names are opaque)
      -> writable Project Knowledge file (host bind)
```

`compose.yaml` defines separate `database`, one-shot `migrate`, `backend`, and `frontend` services. PostgreSQL owns a named volume. Backend 8000 and PostgreSQL 5432 are not published in the production topology. The test override publishes PostgreSQL only on `127.0.0.1` so host-side backup/restore integration can target the isolated test database.

## Data foundation

- SQLAlchemy 2 declarative models use deterministic constraint names.
- Alembic revision `20260712_01` creates Version 1.9-compatible tables and new identity, Profile, Resume, file, audit, and migration tables.
- PostgreSQL Project Knowledge retrieval uses a GIN expression index over `to_tsvector('simple', content)` and `plainto_tsquery` ranking.
- SQLite remains supported for isolated unit tests and development compatibility; Version 2 production configuration requires PostgreSQL.
- The compatibility adapter covers reviewed Version 1.9 SQL so existing product workflows can operate during the transition.

## Identity bootstrap

There is no default administrator and no public registration endpoint. After Alembic reaches head, initialize an administrator from a trusted shell. The password is read without echo and is never accepted as a command-line argument:

```bash
cd backend
APP_ENV=production DATABASE_URL='postgresql+psycopg://...' \
  python -m app.cli users create-admin \
  --email admin@example.com \
  --display-name Administrator
```

Other administrative commands change a password, deactivate a user, or revoke all Sessions. Execute them with the same restricted environment and database role used for the intentional operation.

## Career Profile and Resume rules

Career Profile writes require the current revision. Collection writes use `If-Match`; a stale revision returns `409`. Every accepted mutation produces a new immutable Profile snapshot. Restore creates another revision rather than rewriting history. Imported facts default to `needs_review`; only human-confirmed facts are eligible for copying into Profile.

Resume Versions are append-only drafts. Finalizing a Version makes its content immutable and updates the Resume active Version. Cross-user Resume and file lookups return `404`. Uploaded files are signature checked, archive-bomb constrained, stored under opaque names with mode `0600`, and served only after an ownership check with `nosniff` and `no-store` headers.

## Readiness

`GET /api/health` remains lightweight. `GET /api/ready` checks database connectivity, Alembic revision, required tables, writable private storage, Project Knowledge availability, and knowledge-search readiness without calling DeepSeek. Authenticated administrators can use `GET /api/admin/readiness` for a safe configuration summary; database passwords and filesystem paths are not returned.

## Verification

The local matrix includes all Python unit/regression tests, opt-in PostgreSQL integration tests, frontend Vitest/build, Alembic checks, both Version 1.9 compatibility and Version 2 isolated Docker Smoke tests, image builds, Compose validation, and repository safety scans. `scripts/docker-smoke-v2.sh` creates a random `pja-v2-phase1-*` project, isolated PostgreSQL volume/network/files, loopback ports 18080 and 15432, and removes only its own resources.

See the CI workflow for exact commands. Never point `TEST_DATABASE_URL` at a production-like database; its database name must contain `test`.
