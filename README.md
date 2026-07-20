# Personal Job Agent

Personal Job Agent 2.0.2 is a private resume-to-job analysis workspace. It contains the complete Version 2.0.1 product surface and adds a production-safety fix for PostgreSQL 16 backup and restore.

## Version 2.0.2 scope

The authenticated application provides Dashboard, Analyze, Profile, Resume Versions, History, Project Knowledge, historical Agent Runs, Monitoring/Evaluation for administrators, and Account controls. Analyze accepts one stored/uploaded Resume and one pasted job description or safely fetched job URL. It does not require a Job or Application database entity.

Jobs, Job Rankings, Applications, Approvals, and Tasks are retired. Their old web routes show Feature Removed, and authenticated retired API calls return HTTP 410. Existing production tables and records are retained for rollback, backup, and recovery; Version 2.0.2 has no schema migration or product change beyond Version 2.0.1.

Version 2.0.1 was formally released but was never deployed to production. Its deployment was stopped when a PostgreSQL 17.10 `pg_dump` archive emitted `transaction_timeout`, which PostgreSQL 16 cannot restore. Version 2.0.2 replaces it as the production upgrade target. Backup and restore now require `server major = pg_dump major = pg_restore major = 16`, immutable image provenance, a verified manifest, and a strict isolated restore rehearsal. Dump or archive content must never be edited to bypass compatibility.

## Technology

- React 19, React Router, Vite 8, project CSS tokens
- FastAPI, Python 3.12, SQLAlchemy 2, Alembic, psycopg 3
- PostgreSQL 16
- Redis 7, Dramatiq, Transactional Outbox, SSE
- Docker Compose, Nginx, HTTPS
- Argon2, server-side Sessions, CSRF, ownership/IDOR controls
- SSRF guards, prompt-injection/secret scans, PII minimization, output scanning, fact grounding
- PostgreSQL full-text Project Knowledge RAG
- GitHub Actions and immutable GHCR release images

## Remember Me

Remember Me selects a bounded long-lived server-side Session, with a production maximum of 30 days. The cookie remains random, opaque, `Secure`, `HttpOnly`, and `SameSite=Lax`; only a token hash is stored in PostgreSQL. Normal Sessions default to a 30-minute idle and 24-hour absolute lifetime.

“Remember email” is independent and stores only a normalized email at `pja.v2.login.rememberedEmail` in LocalStorage. The application never stores a plaintext password, Session token, or CSRF token in browser storage. Browser password saving is delegated to the browser/iOS password manager through standard autocomplete fields.

## Project Knowledge RAG

`docs/PROJECT_KNOWLEDGE.md` is the Git baseline and the only supported RAG corpus. Production has a separate runtime copy. With RAG off, Project Knowledge retrieval and prompt injection are skipped. With RAG on, the backend retrieves 1–10 relevant PostgreSQL FTS chunks (default 5), scans them, supplies them under `TRUSTED_PROJECT_EVIDENCE`, and returns only safe source metadata and skill evidence links.

AI-generated content still requires human review. The application does not automatically submit applications or guarantee outcomes.

## Development

Create an ignored environment file from `.env.example`, then:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm ci
```

Run backend tests from the repository root:

```bash
APP_ENV=test .venv/bin/python -m unittest discover -s backend -p 'test_*.py'
```

Run frontend tests and build:

```bash
cd frontend
npm test
npm run build
```

Run the Version 2.0.2 application over the retained Version 2.0.1 product-regression scope using only the Mock LLM:

```bash
PJA_SMOKE_MILESTONE=2.0.1 PJA_APP_VERSION=2.0.2 scripts/docker-smoke-v2.sh
```

Run the strict PostgreSQL 16 backup/restore regression after building the controlled Backend tool images:

```bash
docker build -f backend/Dockerfile -t personal-job-agent-backend:pg16-test .
docker build -f backend/Dockerfile --build-arg POSTGRES_CLIENT_MAJOR=17 -t personal-job-agent-backend:pg17-negative .
scripts/postgres16-restore-regression.sh personal-job-agent-backend:pg16-test personal-job-agent-backend:pg17-negative
```

Production deployment requires immutable `@sha256` image references, verified backups, an isolated candidate, exact `/api/health` version matching, and the runbook in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

- [Project Knowledge](docs/PROJECT_KNOWLEDGE.md)
- [Authentication](docs/V2_AUTHENTICATION.md)
- [RAG](docs/V2_RAG.md)
- [Development](docs/V2_DEVELOPMENT.md)
- [Production readiness](docs/V2_PRODUCTION_READINESS.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Version 2.0.2 release notes](docs/V2_0_2_RELEASE_NOTES.md)
- [Version 2.0.1 release notes](docs/V2_0_1_RELEASE_NOTES.md)

Documents for Jobs, Applications, Tasks, Rankings, Materials, and Approvals describe historical Version 2.0.0 implementation only and are not current product instructions.
