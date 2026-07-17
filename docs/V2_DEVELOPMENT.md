# Version 2 Development Guide

Version 2.0.3 is developed on `version-2.0.3-matching-application-materials` from the Alpha 2 `main` commit. `v2.0.0-alpha.2` is published; Alpha 3 remains an unmerged development PR and is not deployed.

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
```

PostgreSQL integration requires an explicitly test-named database and both `PJA_RUN_POSTGRES_TESTS=1` and `TEST_DATABASE_URL`. Never point these commands at a live database.

Alembic development:

```bash
cd backend
alembic heads
alembic upgrade head
alembic downgrade 20260713_02
alembic upgrade head
alembic check
```

Use only an isolated development/test URL. Do not edit `20260712_01` or `20260713_02`; Alpha 3 changes belong in `20260713_03` or a later revision.

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

## Alpha 3 PR safety

Before push, compare against `origin/main`, run `git diff --check`, scan tracked/generated paths and secrets, and confirm no runtime files, databases, uploads, generated Materials, backups, logs, `node_modules`, or `frontend/dist` are tracked. Do not force push, merge the Alpha 3 PR, create an Alpha 3 tag/release, publish an Alpha 3 image, or deploy.
