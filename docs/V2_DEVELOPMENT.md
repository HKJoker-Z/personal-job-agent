# Version 2 Development Guide

Version 2.0.2 is developed on `version-2.0.2-job-library-pipeline`, stacked on `version-2.0-phase-1-foundation` (PR #6). Do not retarget it to `main` until PR #6 is merged and the stacked diff is revalidated.

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
alembic downgrade 20260712_01
alembic upgrade head
alembic check
```

Use only an isolated development/test URL. Do not edit `20260712_01`; Version 2.0.2 changes belong in `20260713_02` or a later revision.

## Domain rules

- Routers validate and translate errors; repositories query; services own business transactions.
- Every business query must be ownership-scoped.
- Stage changes must use the transition service and append history.
- Job merge must preserve all relations and stop on two active Applications.
- Job Description, Notes, CSV, Resume, and files never enter ordinary logs.
- URL import must retain pinned-address SSRF checks; tests use only the explicit test override.
- LLM tests must inject a Mock invoker. Never put a real API key in tests.
- `reminder_at` does not authorize scheduling or notifications.

## Stacked PR safety

Before push, compare only against `origin/version-2.0-phase-1-foundation`, run `git diff --check`, scan tracked/generated paths and secrets, and confirm no runtime files, databases, uploads, backups, logs, `node_modules`, or `frontend/dist` are tracked. Do not rebase a published shared branch, force push, merge either PR, create a tag/release, publish a Version 2 image, or deploy.
