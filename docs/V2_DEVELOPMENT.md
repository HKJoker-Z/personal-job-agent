# Version 2.0.3 development

Use Python 3.12 and Node 22. Tests must use temporary SQLite or a database whose name contains `test`; never point test configuration at production data. CI and normal local smoke use Mock LLM and must not call DeepSeek.

## Setup and checks

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci && cd ..

APP_ENV=test .venv/bin/python -m unittest discover -s backend -p 'test_*.py'
cd frontend && npm test && npm run build && cd ..
scripts/test-v201-production-runtime.sh
PJA_SMOKE_MILESTONE=2.0.1 PJA_APP_VERSION=2.0.3 scripts/docker-smoke-v2.sh
docker build -f backend/Dockerfile -t personal-job-agent-backend:pg16-test .
docker build -f backend/Dockerfile --build-arg POSTGRES_CLIENT_MAJOR=17 -t personal-job-agent-backend:pg17-negative .
scripts/postgres16-restore-regression.sh personal-job-agent-backend:pg16-test personal-job-agent-backend:pg17-negative
```

Run PostgreSQL integration with a dedicated test database and `PJA_RUN_POSTGRES_TESTS=1`. The strict Restore report must prove client/server major 16, an empty target, zero `pg_restore` exit, exact rows/checksums/foreign keys/sequences/indexes/ownership, matching files/Project Knowledge, and readiness. The test-only client 17 must be rejected before dump and restore writes. Run Docker/Compose, ShellCheck, secret/path safety, Alembic fresh-upgrade/current/heads/check, backup/restore, and isolated smoke before opening or merging a release PR.

## Product boundaries

Do not add Version 2.1 features. Do not restore public Jobs, Job Rankings, Applications, Approvals, or Tasks. Their models and migrations remain for compatibility, but the full application must return 410 for old APIs. Analyze must remain independent of retired entities.

Do not persist passwords or tokens in frontend storage. Do not add arbitrary user-upload RAG. Do not bypass prompt injection, secret/PII scans, output scanning, evidence reconciliation, or claim validation. Mock provider mode must fail closed in production.

## Project Knowledge workflow

Update `docs/PROJECT_KNOWLEDGE.md` only with facts verified in code, tests, CI, or production configuration. Test chunk rebuild and PostgreSQL search for the changed technologies. Production runtime replacement is a deployment action with hash, backup, comparison, explicit replace, rebuild, and Analyze verification.

## Git and releases

Use a feature branch, normal commits, a PR, required checks, and a merge commit. Do not force-push or rebase shared history. Version 2.0.1 artifacts are immutable. Annotated release tags trigger GHCR publication. Production selects immutable component digests, never mutable tags.
