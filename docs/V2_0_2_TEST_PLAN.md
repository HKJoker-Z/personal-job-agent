# Version 2.0.2 Test Plan

All tests use synthetic data. No real Job Description, Resume, Job URL, DeepSeek request, production database, or live recruitment site is used.

## Automated matrix

- Backend SQLite regression: all Version 1.9/2.0.1 tests plus Job CRUD, import, deterministic/Mock LLM extraction, evidence, dedup/merge, Pipeline, Notes, Tasks, Dashboard, CSRF, IDOR, SQL/sort/CSV/HTML injection, storage, migration, readiness, backup, and compatibility tests
- PostgreSQL: fresh Alembic upgrade, Version 1 migration, ownership/constraints, partial uniqueness, Stage History, downgrade to `20260712_01`, and re-upgrade
- Frontend: Dashboard load/empty/error, Job list/search/pagination/import/detail/edit/requirements/duplicates, Application Board transitions/rollback/409/confirmation, detail/history/Resume link/Notes/Tasks, Task grouping/edit/complete/reopen, 401 and safe IDOR handling
- Build/static: Python compile, shell syntax, frontend production build, Compose config, Backend/Frontend Docker builds, image verification, and repository safety scans

## SSRF and untrusted input

Tests cover loopback, localhost, IPv6 loopback, private ranges, link-local/cloud metadata, multicast, IPv4-mapped IPv6, decimal/hex/octal IPs, URL credentials, non-HTTP schemes, private redirect, redirect loop, gzip expansion, response limits, and pinned DNS behavior. The successful URL test uses only a local Mock HTTP server with a test-only allowlist.

Prompt-injection fixtures request system prompts, other-user Resumes, secrets, external tools, database changes, CSRF disablement, and environment variables. Assertions verify data wrapping, sanitization, no tools/network, strict schema, safe metadata, exact evidence, and `needs_review`.

## Isolated Smoke

Run:

```bash
PJA_SMOKE_MILESTONE=2.0.2 \
PYTHON_BIN="$(command -v python)" \
scripts/docker-smoke-v2.sh
```

The project name is `pja-v2-0-2-*`, HTTP binds only `127.0.0.1:18082`, PostgreSQL uses a loopback-only test port, and the network, volume, files, credentials, and Mock HTTP service are unique to the run. The script verifies auth/CSRF, Profile/Resume compatibility, all four Job import paths, duplicate detection, Requirements, Pipeline/history/Resume link/Note, Task completion, Dashboard, restart persistence, backup/verify/restore row counts and file checksums, 401/403 negatives, and prefix-guarded cleanup.

After Smoke, confirm no prefixed container/network/volume or listening test port remains and production container IDs/restart counts, port 8080 health, `pja-br0`, and pref 8999 are unchanged.
