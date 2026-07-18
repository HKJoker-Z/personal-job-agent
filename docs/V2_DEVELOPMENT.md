# Version 2 Development Guide

Version 2.0.4 is developed on `version-2.0.4-final-release` from the Version 2.0.3 `main` commit `031dfa9`. `v2.0.0-alpha.3` is published. The runtime marker is `2.0.0-alpha.4-dev+031dfa9`; this milestone remains a development PR and is not deployed.

## Local checks

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt

cd backend
APP_ENV=test python -m unittest discover -v
python -m compileall -q . ../scripts
cd ../frontend
npm ci
npm run test
npm run build
cd ..
find scripts -maxdepth 1 -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
shellcheck scripts/*.sh deploy/postgres/*.sh
```

PostgreSQL integration requires an explicitly test-named database and both `PJA_RUN_POSTGRES_TESTS=1` and `TEST_DATABASE_URL`. Never point these commands at a live database.

Alembic development:

```bash
cd backend
alembic heads
alembic upgrade head
alembic downgrade 20260713_03
alembic upgrade head
alembic check
```

Use only an isolated development/test URL. Do not edit `20260712_01`, `20260713_02`, or `20260713_03`; final workflow changes belong in `20260717_04` or a later revision.

## Domain rules

- Routers validate and translate errors; repositories query; services own business transactions.
- Every business query must be ownership-scoped.
- Stage changes must use the transition service and append history.
- Job merge must preserve all relations and stop on two active Applications.
- Job Description, Notes, CSV, Resume, and files never enter ordinary logs.
- URL import must retain pinned-address SSRF checks; tests use only the explicit test override.
- LLM tests must inject a Mock invoker. Never put a real API key in tests.
- `reminder_at` does not authorize scheduling or notifications.
- Matching uses confirmed Profile facts and confirmed Job Requirements; unknown is never silently converted to unmet.
- LLM output cannot set scores. It may rewrite a grounded local Draft only and must pass strict schema, output scan, and independent claim validation.
- Material edits create a new immutable Version. Unsupported claims block approval/finalization unless edited or explicitly user-confirmed for that Version.
- PostgreSQL is the system of record. Redis carries only allow-listed IDs and short-lived coordination state; queue messages are JSON and never contain Resume/JD/Material text, PII, Sessions, Cookies, CSRF values, API keys, or database URLs.
- Every Run/Step transition is transactional, row-locked, revisioned, and accompanied by an append-only Agent Event and Audit Event. Usage keys make accounting exactly-once under duplicate delivery.
- Approval waits do not occupy a Worker. Completed steps and generated Materials are reused during retry and crash recovery.

## Final Version 2 PR safety

Before push, compare against `origin/main`, run `git diff --check`, scan tracked/generated paths and secrets, and confirm no runtime files, databases, uploads, generated Materials, backups, logs, `node_modules`, or `frontend/dist` are tracked. Use only the isolated `pja-v2-final-*` Smoke project on `127.0.0.1:18088`. Do not force push, merge the PR, create a `v2.0.0` tag/Release, publish final images, deploy, or change the existing 8080 service.
