# Personal Job Application Agent

Latest stable release: v1.9.0

Latest prerelease: v2.0.0-alpha.2

Development runtime version: 2.0.0-alpha.3

Personal Job Application Agent is a local-first, full-stack AI job application assistant. It parses a PDF or DOCX resume, accepts pasted job description text or one user-provided job URL, applies deterministic AI security checks, uses the DeepSeek API to generate explainable Resume-JD matching results, retrieves evidence from a curated Project Knowledge RAG source, creates an English cover letter, recommends the next application action, tracks saved applications in SQLite, records local AI monitoring metadata, runs offline behavioral evaluations, and exports application materials as DOCX/PDF files.

Version 1.9 adds containerized deployment, persistent runtime storage, production configuration validation, health/readiness checks, privacy-aware request logging, SQLite-safe backup/restore tooling, GitHub Actions CI, and versioned GHCR publishing configuration. It remains a single-instance SQLite deployment model and does not claim Kubernetes, high availability, zero downtime, distributed tracing, or automatic cloud deployment.

## Version 2 development milestones

Version 2.0.1 and Version 2.0.2 are included in the published `v2.0.0-alpha.2` prerelease. Version 2.0.3 is the current development milestone for deterministic explainable matching, reproducible Job ranking, and evidence-grounded Application Materials. The final formal release remains planned as `v2.0.0`.

Version 2.0.2 adds:

- An ownership-scoped Job Library with search, filtering, stable pagination, optimistic revisions, archive/restore, source provenance, structured requirements, and explicit duplicate resolution
- Manual, SSRF-guarded URL, private PDF/DOCX, and bounded CSV imports with deterministic normalization and per-row validation
- Deterministic duplicate candidates and user-confirmed transactional Job merge without physical deletion
- Explicit, Mock-tested requirement extraction where Job Descriptions are untrusted data and LLM evidence must exactly match the current description
- An Application Pipeline with a validated stage-transition matrix, append-only Stage History, private Notes, and owned Resume Version links
- User-confirmed Tasks with priority, due/reminder timestamps, completion/reopen, filters, and deterministic suggestions; `reminder_at` is stored only and sends no notification
- A database-backed Dashboard and authenticated React pages for Jobs, imports, Applications, Tasks, and summary statistics
- Alembic revision `20260713_02`, PostgreSQL integration coverage, and an isolated `pja-v2-0-2-*` Docker Smoke mode on `127.0.0.1:18082`

The foundation from Version 2.0.1 remains intact:

- SQLAlchemy 2.x models, psycopg 3, PostgreSQL 16, and Alembic migrations
- Explicit administrator initialization with no default account or public registration
- Argon2 password hashing, opaque server-side Sessions, HttpOnly Cookies, Origin-bound CSRF, database-backed login throttling, and ownership-scoped queries
- Career Profile CRUD, optimistic revision checks, immutable snapshots, restore, verification states, and deterministic completeness
- Resume Library, immutable Resume Versions, PDF/DOCX import, human review gates, private file storage, and IDOR protection
- Read-only Version 1.9 SQLite inspection and transactional PostgreSQL migration with row-count/checksum verification
- PostgreSQL/private-file backup, manifest verification, guarded empty-target restore, and isolated Docker Smoke coverage
- Authenticated React routes, in-memory CSRF handling, Profile, Resume, Import, and Account pages around the preserved workspace

Version 2.0.3 adds deterministic 0–100 dimension scoring, separately reported hard filters, immutable Match snapshots, reproducible ranking, Application Packages, Tailored Resume/Cover Letter/Application Answer Drafts, immutable Material Versions, evidence links, independent fact validation, and explicit review/finalization gates. An LLM may only rewrite the local grounded Draft; it never decides numeric scores, and all tests use a deterministic or Mock provider. Unknown evidence is distinct from confirmed missing evidence, and the score is not an Offer probability.

No Version 2 build is deployed to the live Version 1.9 runtime. Alpha 3 does not implement Workers, queues, schedulers, automatic applications, email sending, interview tools, or production migration. Generated Materials remain Drafts until explicit user review; Tailored Resume generation never changes the source Resume.

Start with [Version 2 roadmap](docs/V2_ROADMAP.md), [Version 2.0.3 architecture](docs/V2_0_3_ARCHITECTURE.md), [matching engine](docs/V2_MATCHING_ENGINE.md), [fact grounding](docs/V2_FACT_GROUNDING.md), [Application Packages](docs/V2_APPLICATION_PACKAGES.md), and [development guide](docs/V2_DEVELOPMENT.md).

Useful development checks:

```bash
cd backend
python -m unittest discover -v
cd ../frontend
npm ci
npm run test
npm run build
cd ..
PJA_SMOKE_MILESTONE=2.0.3 PYTHON_BIN="$(command -v python)" scripts/docker-smoke-v2.sh
```

## Core Features

- Resume parsing from PDF and DOCX
- Job description analysis from pasted text or one user-provided job URL
- DeepSeek-powered resume and job matching analysis
- Project Knowledge RAG using `docs/PROJECT_KNOWLEDGE.md`
- Dedicated Project Knowledge upload/replace workflow for `.md` and `.txt` files
- Project Knowledge status, rebuild, and search APIs
- SQLite-backed local RAG indexing
- SQLite FTS5 retrieval when available
- Lightweight keyword retrieval fallback when FTS5 is unavailable
- RAG-enhanced analysis with top-k Project Knowledge evidence injection
- RAG Mode and RAG Sources in Analyze results and History Detail
- RAG Mode and RAG Sources in PDF analysis reports
- Custom Agent Workflow Orchestration for the Analyze pipeline
- AI Security Layer for prompt injection mitigation and data leakage prevention
- Secret and credential-like content detection before LLM calls
- Best-effort PII minimization for resume data sent to DeepSeek
- Safe prompt construction with isolated untrusted sections
- LLM output leakage scanning
- Security audit trail in Analyze, History Detail, and PDF reports
- Security policy endpoint
- Local SQLite AI monitoring
- Workflow latency metrics
- LLM latency monitoring
- RAG effectiveness metrics
- Security monitoring
- Recommendation outcome monitoring
- Sanitized workflow trace explorer
- Offline behavioral evaluation suite
- Evaluation history
- Monitoring dashboard
- Clear-all and filtered monitoring cleanup
- Workflow-specific monitoring trace deletion
- Evaluation-history cleanup
- Admin-token-protected destructive APIs with local-only default
- Temporary SQLite databases and fail-fast test/real-data isolation
- Workflow IDs and real execution audit trails
- Deterministic next-action recommendation
- Human-in-the-loop decision recording for recommendations
- Workflow and recommendation display in Analyze, History, and PDF reports
- Explainable scoring breakdown across skills, projects, education, work experience, and keyword match
- Backend-controlled weighted match score calculation
- ATS keyword analysis
- Resume bullet optimization suggestions based only on existing resume or retrieved evidence
- English cover letter generation
- SQLite application history tracking
- DOCX cover letter export
- PDF analysis report export
- Dockerized non-root FastAPI backend
- Multi-stage React/Nginx frontend with same-origin `/api` proxying
- Docker Compose production topology with persistent SQLite and Project Knowledge storage
- Production Trusted Hosts, strict CORS, and API docs disabled by default
- Lightweight health and detailed readiness endpoints
- Request IDs and privacy-aware structured JSON logging
- SQLite-safe backup, verified restore, and existing-data migration workflows
- GitHub Actions CI and semantic-tag GHCR image publishing configuration
- Ubuntu deployment and production security documentation

Version 1.5.2 removed the generic knowledge base upload UI and disabled generic `/api/knowledge/*` endpoints with HTTP `410 Gone`. Version 1.8 keeps that Project Knowledge-only RAG design.

## Why Project Knowledge RAG Only

The project is an AI job application assistant, not a general document storage or knowledge management product.

Project Knowledge RAG keeps retrieval focused on a single curated evidence file:

- `docs/PROJECT_KNOWLEDGE.md` is easy to review and maintain through Git/Codex.
- Retrieval is focused on real project evidence instead of arbitrary documents.
- The RAG source is auditable before it influences cover letters, scoring, or resume bullets.
- Fewer arbitrary uploads reduce retrieval noise and data leakage risk.
- The design better demonstrates RAG, LLM applications, workflow automation, API development, system integration, and responsible AI.

## Project Knowledge Workflow

1. Edit `docs/PROJECT_KNOWLEDGE.md` directly through Git/Codex.
2. Or upload a `.md` or `.txt` file from the Project Knowledge page to replace `docs/PROJECT_KNOWLEDGE.md`.
3. Rebuild the Project Knowledge index.
4. Analyze a job with Project Knowledge RAG enabled.
5. Review RAG Sources in Analyze, History Detail, and PDF reports.

## Tech Stack

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Storage: SQLite through Python `sqlite3`
- Local retrieval: SQLite FTS5 if available, with lightweight keyword fallback
- Resume parsing: `pypdf`, `python-docx`
- Project Knowledge parsing: UTF-8 Markdown or text
- DOCX export: `python-docx`
- PDF export: `reportlab`
- URL extraction: `requests`, `beautifulsoup4`
- Local monitoring and evaluation: SQLite, FastAPI, React, Python standard library
- Version control: Git/GitHub
- Containers: Docker, Docker Compose, non-root Nginx
- CI/CD: GitHub Actions and GitHub Container Registry

No external vector database or external observability vendor is used in v1.8.

## Project Structure

```text
.
├── backend/
│   ├── data/
│   │   └── app.db            # generated locally, not committed
│   ├── database.py
│   ├── config.py
│   ├── readiness.py
│   ├── logging_utils.py
│   ├── project_knowledge_runtime.py
│   ├── Dockerfile
│   ├── export_utils.py
│   ├── agent_workflow.py
│   ├── recommendation_engine.py
│   ├── security_utils.py
│   ├── safe_prompt.py
│   ├── monitoring_service.py
│   ├── evaluation_service.py
│   ├── data_management_service.py
│   ├── test_support.py
│   ├── knowledge_utils.py
│   ├── evals/
│   │   ├── cases.json
│   │   └── README.md
│   ├── main.py
│   ├── test_agent_workflow.py
│   ├── test_recommendation_engine.py
│   ├── test_security_utils.py
│   ├── test_safe_prompt.py
│   ├── test_monitoring_service.py
│   ├── test_evaluation_service.py
│   ├── test_data_management_service.py
│   ├── test_database_isolation.py
│   └── requirements.txt
├── docs/
│   ├── PROJECT_KNOWLEDGE.md  # curated Project Knowledge RAG source
│   ├── MONITORING_AND_EVALUATION.md
│   ├── MONITORING_DATA_MANAGEMENT.md
│   ├── DEPLOYMENT.md
│   ├── BACKUP_AND_RESTORE.md
│   ├── PRODUCTION_SECURITY.md
│   └── CI_CD.md
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       └── styles.css
├── scripts/
├── compose.yaml
├── compose.prod.yaml
├── .dockerignore
├── .gitignore
└── README.md
```

## Environment Variables

Create a `.env` file in the project root:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
APP_ENV=development
APP_DATABASE_PATH=
PROJECT_KNOWLEDGE_PATH=
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
TRUSTED_HOSTS=localhost,127.0.0.1
MAX_UPLOAD_SIZE_MB=8
REQUEST_TIMEOUT_SECONDS=60
ENABLE_API_DOCS=true
LOG_LEVEL=INFO
MONITORING_ADMIN_TOKEN=
MONITORING_ALLOW_REMOTE_ADMIN=false
```

`APP_DATABASE_PATH` and `PROJECT_KNOWLEDGE_PATH` are optional in development. `APP_ENV=test` refuses the default application database. Production requires a configured DeepSeek key and explicit trusted hosts, rejects wildcard hosts/origins, disables API docs by default, and keeps remote destructive administration disabled by default.

Optional frontend API base URL:

```bash
cd frontend
printf 'VITE_BACKEND_PROXY_TARGET=http://127.0.0.1:8000\n' > .env.local
```

Do not commit `.env`, `.env.local`, or any `*.env` file.

## Local Run

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Local URLs:

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
Docs:     http://localhost:8000/docs
Health:   http://localhost:8000/api/health
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "personal-job-agent",
  "version": "1.9"
}
```

`GET /api/health` is process liveness only. `GET /api/ready` checks SQLite connectivity and schema, data-directory writeability, Project Knowledge initialization/index state, and production LLM configuration without calling DeepSeek.

## Docker Compose Production-Style Quick Start

The Version 1.9 production URL is `http://SERVER_IP:8080`; its health endpoint is `http://SERVER_IP:8080/api/health`. Port 8080 is the React/Nginx entry point. Backend port 8000 stays inside the Compose network, while Vite port 5173 is development-only. Install and start Docker Engine plus Docker Compose before continuing, and allow inbound TCP 8080 in the cloud security group when deploying to a public server. Do not expose ports 8000 or 5173.

Bootstrap persistent host directories and create an ignored production configuration:

```bash
sudo scripts/bootstrap-runtime.sh
cp .env.production.example .env.production
```

Set the required production values, then validate and build:

```bash
APP_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml config --quiet
APP_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml build
```

Start only when the container topology is intentionally being deployed:

```bash
APP_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml up -d
scripts/health-check.sh http://127.0.0.1:8080
```

The backend has no host port. Nginx is the only published service and forwards same-origin `/api` requests internally. After changing `.env.production`, recreate the containers. Troubleshoot with `docker compose ps`, `docker compose logs --tail=200 backend frontend`, and `curl http://127.0.0.1:8080/api/health`. Read `docs/DEPLOYMENT.md` before Ubuntu deployment. Version 1.9 does not automatically configure cloud firewalls, DNS, HTTPS, or system services.

On Linux hosts using Mihomo TUN, policy routing can capture Docker published-port return traffic even though port 8080 is listening correctly. The production Compose network uses the stable Linux bridge name `pja-br0`, and the optional systemd routing service bypasses TUN only for packets entering from `pja-br0` with TCP source port 8080. Backend port 8000 remains private, and other Backend HTTPS traffic keeps its existing routing policy. See [Client Proxy Troubleshooting](docs/CLIENT_PROXY_TROUBLESHOOTING.md) and [Deployment](docs/DEPLOYMENT.md). Never flush iptables or nftables as a workaround.

## Database

SQLite database file:

```text
backend/data/app.db
```

The backend creates `backend/data/` and `app.db` automatically. Database files are ignored by Git.

Application history stores normalized AI analysis results, scoring breakdowns, ATS analysis, upgraded resume bullets, RAG mode, RAG source metadata, workflow IDs, workflow step audit trails, security audit metadata, next-action recommendations, human decisions, status, and notes. It does not store uploaded resume files or complete `resume_text`.

Version 1.8 monitoring tables store local metadata only:

- `analysis_metrics`: one metadata row per Analyze workflow ID.
- `analysis_step_metrics`: step status and duration without step messages.
- `evaluation_runs`: offline Behavioral Evaluation Suite run summaries.
- `evaluation_results`: safe case check summaries.

Monitoring tables do not store raw resumes, raw job descriptions, full prompts, full model outputs, RAG chunk content, detected secret values, or prompt injection attack text. Monitoring persistence is best effort and does not fail the primary Analyze request.

Version 1.8.1 cleanup can permanently delete `analysis_metrics`, `analysis_step_metrics`, `evaluation_runs`, and `evaluation_results`. It does not delete `application_records`, application workflow history, Project Knowledge, `knowledge_documents`, `knowledge_chunks`, `knowledge_chunks_fts`, or `backend/evals/cases.json`. See [Monitoring Data Management](docs/MONITORING_DATA_MANAGEMENT.md) for lifecycle, authorization, and isolation details.

Project Knowledge RAG uses the existing v1.5 tables:

- `knowledge_documents` stores Project Knowledge metadata and content previews.
- `knowledge_chunks` stores parsed Project Knowledge chunks.
- `knowledge_chunks_fts` is created with SQLite FTS5 when available.

The tables remain in place to avoid breaking existing local databases, but the product UI no longer supports arbitrary knowledge document uploads.

## RAG Retrieval

Version 1.8 uses Project Knowledge RAG only:

- The only recommended RAG source is `docs/PROJECT_KNOWLEDGE.md`.
- The backend chunks the file and indexes it in SQLite.
- SQLite FTS5 is used when available.
- If FTS5 is unavailable, the backend falls back to lightweight keyword scoring over chunk content, title, and category.
- Only top-k relevant chunks are sent to DeepSeek during analysis.
- The entire Project Knowledge file is never sent to the LLM.
- Generic `/api/knowledge/*` endpoints are disabled in v1.8 and return `410 Gone`.

## AI Security Layer

Version 1.8 includes deterministic security controls around the RAG-powered analysis workflow:

- Prompt injection mitigation scans untrusted resume, JD, job URL content, and Project Knowledge chunks for instruction override, system prompt extraction, data exfiltration, role manipulation, tool or command manipulation, and indirect instruction priority patterns.
- Prompt injection findings do not automatically block ordinary analysis. Suspicious instruction segments are replaced with `[REMOVED_SUSPICIOUS_INSTRUCTION]`, the workflow continues, and the result is marked `passed_with_warnings`.
- Secret detection scans for credential-like API keys, GitHub tokens, bearer tokens, AWS access keys, AWS secret assignments, private key headers, password assignments, database URLs with embedded credentials, and generic secret environment variable assignments.
- Critical credential-like content is blocked before DeepSeek invocation with a 4xx response. The response does not echo the detected secret, and blocked requests are not saved to application history.
- PII minimization redacts email addresses, phone numbers, stable street address patterns, and token-like URL query parameters from the copy of resume text sent to DeepSeek.
- Safe prompt construction isolates untrusted resume, JD, and Project Knowledge evidence in explicit XML-style sections and states that untrusted content is data only.
- LLM output scanning redacts credential-like content before returning output. If an internal security marker appears in model output, the response is blocked as internal instruction leakage.
- Security findings use stable codes, categories, severity, source, and safe messages. Full malicious text, secrets, full resumes, full JDs, and full Project Knowledge chunks are not stored in findings.

These controls are heuristic and pattern-based. They reduce risk but cannot guarantee complete protection against every prompt injection attack, and they may produce false positives or false negatives. PII redaction is best-effort. Version 1.8 does not claim formal security certification, penetration testing coverage, SOC 2, ISO 27001, or a third-party AI firewall.

## Agent Workflow Orchestration

Version 1.8 decomposes `POST /api/analyze` into real backend workflow steps:

1. Validate Input
2. Parse Resume
3. Acquire Job Description
4. Scan Untrusted Input
5. Retrieve Project Knowledge
6. Scan Project Evidence
7. Build Safe Prompt
8. Run LLM Analysis
9. Scan LLM Output
10. Validate Structured Output
11. Reconcile Evidence
12. Recommend Next Action
13. Save Application
14. Finalize Result

Each step records a stable key, display name, status, safe message, start time, completion time, and measured `duration_ms`. Steps can be `pending`, `running`, `completed`, `skipped`, or `failed`.

The current workflow is synchronous. Version 1.8 returns an execution audit trail after the synchronous workflow completes. The UI may show a loading message while the request is running, but it does not simulate fake step progress with timers and it does not provide real-time streaming.

This is a custom lightweight orchestration layer, not LangGraph, CrewAI, AutoGen, MCP, or an asynchronous distributed task queue.

Workflow timing uses Python `time.perf_counter_ns()` for high-resolution monotonic backend timing. Each step returns `duration_ms` with sub-millisecond precision and `duration_us` for microsecond-level display. Fast operations below one millisecond are displayed as `<1 ms`; no artificial delays or fake minimum durations are added. The timing values represent measured backend workflow execution time, not frontend network round-trip time.

## Next-Action Recommendation

The backend generates a deterministic recommendation without making an additional DeepSeek call:

- `apply_now`: high match score and no critical missing requirements.
- `improve_resume_first`: strong or moderate match where resume wording or limited gaps should be addressed first.
- `upskill_first`: meaningful technical gaps remain before applying.
- `save_for_later`: weak but not irrelevant fit.
- `skip`: very low fit or major core requirement gaps.

The recommendation includes an action, label, priority, rule-based confidence indicator, reason, recommended tasks, and evidence. The confidence value is an explainable rule indicator from `0.0` to `1.0`; it is not a trained model probability and does not predict hiring outcome.

Critical missing skills are identified from missing skills, ATS missing keywords, important JD keywords, scoring, and retrieved Project Knowledge evidence. If a skill is supported by the resume or Project Knowledge evidence, it should not be treated as critical missing.

## Human-in-the-Loop Decision

The Agent recommends the next action, but the user decides. Saved records can store one of these decision states:

- `pending`
- `accepted`
- `dismissed`
- `completed`

The Agent does not automatically submit job applications, change the user's resume, or modify application status based on the recommendation.

## Troubleshooting / Validation

### How to verify Project Knowledge RAG affects matching

Project Knowledge evidence is treated as user project experience for matching, but not as system instructions. If a JD requires RAG and `docs/PROJECT_KNOWLEDGE.md` contains RAG evidence, the system should treat RAG as a matched skill instead of a missing skill.

Use these checks:

```bash
curl http://127.0.0.1:8000/api/project-knowledge/status
curl -X POST http://127.0.0.1:8000/api/project-knowledge/rebuild
curl "http://127.0.0.1:8000/api/project-knowledge/search?query=RAG%20Retrieval-Augmented%20Generation%20LLM%20applications%20FastAPI%20workflow%20automation&top_k=5"
```

The search response should include Project Knowledge chunks containing terms such as:

- RAG
- Retrieval-Augmented Generation
- Project Knowledge RAG
- SQLite FTS5 retrieval
- document chunking
- top-k evidence injection
- evidence-based generation
- LLM applications
- FastAPI API development
- workflow automation

When calling `POST /api/analyze` with a JD that requires RAG, LLM applications, FastAPI, and workflow automation, verify:

- `rag_mode` is `project`.
- `used_knowledge_base` is `true`.
- `rag_sources` is not empty.
- `missing_skills` does not include RAG when retrieved Project Knowledge evidence supports it.
- `matched_skills` or `ats_analysis.matched_keywords` includes RAG or Retrieval-Augmented Generation.

## API

API documentation:

```text
http://localhost:8000/docs
```

### `GET /api/health`

Returns service health and current version.

### `POST /api/analyze`

Request type: `multipart/form-data`

- `resume`: required, PDF or DOCX
- `job_text`: optional job description text
- `job_url`: optional single job posting URL
- `save_to_history`: optional boolean, defaults to `true`
- `use_knowledge_base`: optional boolean, defaults to `true`
- `rag_mode`: optional string, `project` or `off`, defaults to `project`
- `rag_top_k`: optional integer, defaults to `5`, allowed range `1-10`

Compatibility behavior:

- `use_knowledge_base=false` is treated as `rag_mode=off`.
- `use_knowledge_base=true` without `rag_mode` defaults to `rag_mode=project`.
- Legacy `rag_mode=all` is downgraded to `rag_mode=project`.
- All-knowledge retrieval is no longer executed.

Response includes all analysis fields plus:

- `rag_mode`
- `used_knowledge_base`
- `rag_sources`
- `workflow_id`
- `workflow_status`
- `workflow_steps`
- `next_action`
- `next_action_decision`
- `security_scan`
- `security_status`
- `security_policy_version`

`security_status` is one of `passed`, `passed_with_warnings`, or `blocked`. If critical credential-like content is detected before DeepSeek invocation, the API returns a 4xx security error and does not save an application record.

### `GET /api/security/policy`

Returns the public security policy capabilities and limitations without exposing internal regex rules, system prompts, or internal markers.

Example response:

```json
{
  "version": "1.7",
  "prompt_injection_detection": true,
  "secret_detection": true,
  "pii_redaction": true,
  "output_leakage_scan": true,
  "limitations": [
    "Pattern-based detection may produce false positives or false negatives.",
    "The system cannot guarantee complete prompt injection prevention."
  ]
}
```

### Monitoring APIs

Version 1.8 adds metadata-only monitoring endpoints:

- `GET /api/monitoring/status`
- `GET /api/monitoring/overview?days=30`
- `GET /api/monitoring/workflow-steps?days=30`
- `GET /api/monitoring/rag?days=30`
- `GET /api/monitoring/security?days=30`
- `GET /api/monitoring/recommendations?days=30`
- `GET /api/monitoring/traces?days=30&limit=50&offset=0`
- `GET /api/monitoring/traces/{workflow_id}`
- `GET /api/monitoring/data-management/status`
- `POST /api/monitoring/data/preview`
- `DELETE /api/monitoring/data`
- `DELETE /api/monitoring/traces/{workflow_id}`

Monitoring APIs return workflow metrics, latency summaries, RAG hit metrics, security finding code distributions, recommendation outcomes, and sanitized trace metadata. They do not return resumes, job descriptions, prompts, model responses, RAG chunk content, detected secret values, or original attack text.

Workflow P50 and P95 use nearest-rank percentile over non-skipped, non-null durations. If a denominator is zero, rate fields return `0`.

Data-management preview and deletion APIs require `X-Monitoring-Admin-Token`; deletion is disabled unless `MONITORING_ADMIN_TOKEN` is configured. All cleanup is permanent. Application history and Project Knowledge are preserved. Remote destructive APIs should only be enabled behind HTTPS or a protected reverse proxy.

### Evaluation APIs

Version 1.8 adds offline Behavioral Evaluation APIs:

- `GET /api/evaluations/status`
- `POST /api/evaluations/run`
- `GET /api/evaluations/runs?limit=20&offset=0`
- `GET /api/evaluations/runs/{run_id}`
- `POST /api/evaluations/data/preview`
- `DELETE /api/evaluations/data`

Request:

```json
{
  "suite_name": "default",
  "mode": "offline"
}
```

Only `offline` mode is supported. Live LLM evaluation is not supported in Version 1.8 and does not call DeepSeek. Evaluation pass rate measures deterministic behavioral and rule compliance checks. It is not model accuracy, hiring success probability, or real-world accuracy.

### `GET /api/project-knowledge/status`

Returns whether `docs/PROJECT_KNOWLEDGE.md` exists and whether it is indexed.

Example:

```json
{
  "exists": true,
  "path": "docs/PROJECT_KNOWLEDGE.md",
  "indexed": true,
  "document_id": 1,
  "chunk_count": 12,
  "updated_at": "2026-07-10T00:00:00+00:00"
}
```

### `POST /api/project-knowledge/rebuild`

Rebuilds the Project Knowledge RAG index from `docs/PROJECT_KNOWLEDGE.md`.

Example response:

```json
{
  "rebuilt": true,
  "document_id": 1,
  "chunk_count": 12,
  "source_path": "docs/PROJECT_KNOWLEDGE.md"
}
```

### `POST /api/project-knowledge/upload`

Uploads and replaces `docs/PROJECT_KNOWLEDGE.md`, then automatically rebuilds the Project Knowledge index.

Request type: `multipart/form-data`

- `file`: required, `.md` or `.txt`
- Maximum size: 2 MB
- File must be UTF-8 encoded

Example response:

```json
{
  "uploaded": true,
  "source_path": "docs/PROJECT_KNOWLEDGE.md",
  "document_id": 1,
  "chunk_count": 12,
  "message": "Project knowledge file uploaded and indexed successfully."
}
```

### `GET /api/project-knowledge/search`

Searches only the indexed chunks that belong to `docs/PROJECT_KNOWLEDGE.md`.

Query parameters:

- `query`: required
- `top_k`: optional integer, defaults to `5`, allowed range `1-10`

Example:

```bash
curl "http://localhost:8000/api/project-knowledge/search?query=RAG%20FastAPI%20DeepSeek&top_k=5"
```

### Generic Knowledge Endpoints

The following generic knowledge endpoints are disabled in v1.8 and return `410 Gone`:

- `GET /api/knowledge/documents`
- `POST /api/knowledge/documents`
- `GET /api/knowledge/documents/{id}`
- `DELETE /api/knowledge/documents/{id}`
- `GET /api/knowledge/search`

Response:

```json
{
  "detail": "Generic knowledge base upload is disabled in v1.8. Use Project Knowledge RAG instead."
}
```

### Application History and Export APIs

- `GET /api/applications`: returns historical application records without heavy detail fields, plus lightweight next-action label, decision data, security status, and security risk level.
- `GET /api/applications/{id}`: returns one full application record, including RAG mode, RAG sources, workflow steps, security audit data, next action, and human decision data.
- `PATCH /api/applications/{id}`: updates application status and optional notes.
- `PATCH /api/applications/{id}/next-action`: records the user's decision for the Agent recommendation.
- `DELETE /api/applications/{id}`: deletes one historical application record.
- `GET /api/applications/{id}/cover-letter.docx`: exports the saved cover letter as DOCX.
- `GET /api/applications/{id}/report.pdf`: exports a full PDF report, including RAG Mode, RAG Sources, AI Security Audit, Agent Workflow, Recommended Next Action, and Human Decision.

### `PATCH /api/applications/{id}/next-action`

Records a human-in-the-loop decision for the recommendation.

Request:

```json
{
  "decision": "accepted",
  "notes": "I will tailor the resume before applying."
}
```

Allowed decisions:

- `pending`
- `accepted`
- `dismissed`
- `completed`

Response:

```json
{
  "application_id": 6,
  "next_action": {},
  "decision": "accepted",
  "notes": "I will tailor the resume before applying.",
  "decided_at": "2026-07-10T00:00:00+00:00"
}
```

## Security and Responsible AI

- RAG only sends top-k chunks from `docs/PROJECT_KNOWLEDGE.md`.
- Project Knowledge is curated and auditable.
- No arbitrary knowledge uploads are needed in the product workflow.
- `.env` is ignored.
- SQLite database files are ignored.
- Original resume files are not stored.
- Full `resume_text` is not stored in `application_records`.
- The DeepSeek API key is never printed.
- Backend logs record steps and counts, not full resume content, full JD content, knowledge chunk content, cover letter content, or report content.
- Workflow step messages are short, safe status messages and do not contain full resumes, full JDs, full Project Knowledge chunks, or API keys.
- Job descriptions and Project Knowledge content are treated as untrusted data in the prompt.
- Uploaded resumes, pasted JDs, fetched job URL content, Project Knowledge chunks, and DeepSeek output are treated as untrusted data.
- Untrusted JD and RAG content are isolated as data in safe prompt sections.
- Deterministic prompt injection detection filters suspicious instruction text before LLM invocation.
- Critical credential-like content is blocked before LLM invocation.
- PII redaction is best-effort and is applied to the LLM-bound copy of resume text.
- LLM output is scanned for credential-like content and internal marker leakage before returning.
- Security findings do not store full malicious content, full resume text, full JD text, full Project Knowledge chunks, or detected secret values.
- Monitoring stores sanitized metadata and counts only.
- Monitoring does not store raw prompts or private inputs.
- No additional DeepSeek calls are used for monitoring.
- Offline evaluation does not call external LLMs.
- Evaluation measures deterministic behavior and rule compliance, not model accuracy or hiring success probability.
- Detection uses deterministic heuristic rules. It reduces risk but cannot guarantee complete protection against every prompt injection attack.
- Version 1.8 does not claim formal security certification, distributed tracing, production APM, OpenTelemetry, Langfuse, Prometheus, or Grafana integration.
- The system instructs the LLM not to fabricate user experience.
- Cover letters must be grounded in the resume and retrieved Project Knowledge evidence.

## Version 1.9 Core Changes

- Containerized the FastAPI backend as a non-root image.
- Added a multi-stage React/Nginx frontend image with same-origin `/api` proxying.
- Added a hardened Docker Compose topology with persistent SQLite and Project Knowledge bind mounts.
- Added strict production configuration, Trusted Hosts, CORS, and API documentation controls.
- Added liveness/readiness checks, request IDs, and privacy-aware structured logging.
- Added SQLite-safe backup, verified restore, and explicit existing-data migration tooling.
- Added GitHub Actions CI and semantic-tag GHCR image publishing configuration.
- Added Ubuntu deployment, backup/restore, CI/CD, and production security documentation.
- Added stable Docker bridge naming and an exact, restart-safe policy-routing service for Mihomo TUN compatibility without bypassing Backend HTTPS traffic.

## Version 1.8.1 Core Changes

- Added monitoring data lifecycle management with clear-all and filtered cleanup.
- Added workflow-specific trace deletion and evaluation-history cleanup.
- Added transaction-safe child-before-parent deletion.
- Added admin-token protection and local-only destructive operations by default.
- Added configurable database paths and temporary SQLite databases for automated tests.
- Added fail-fast safeguards preventing `APP_ENV=test` from writing to `app.db`.
- Added Data Management controls to the React Monitoring dashboard.

## Version 1.8 Core Changes

- Added local SQLite monitoring for Analyze workflows.
- Added step-level workflow latency metrics.
- Added LLM, RAG, security, and recommendation monitoring.
- Added privacy-aware metadata-only traces.
- Added trace lookup by workflow ID.
- Added an offline deterministic Behavioral Evaluation Suite.
- Added evaluation run and result history.
- Added a React Monitoring dashboard.
- Added monitoring and evaluation unit tests.
- Kept Version 1.7 AI security, Project Knowledge RAG, History, Export, and next-action recommendation behavior.

## Version History

- v1.1: Stability improvements
- v1.2: SQLite application tracking
- v1.3: Explainable scoring and ATS analysis
- v1.4: DOCX/PDF export and product polish
- v1.5: RAG Knowledge Base
- v1.5.2: Project Knowledge RAG Only
- v1.6: Agent workflow orchestration and next-action recommendation
- v1.7: AI Security and Prompt Injection Mitigation
- v1.8: AI Monitoring and Behavioral Evaluation
- v1.8.1: Monitoring Data Management and Test Isolation
- v1.9: Containerized Deployment, CI/CD, and Production Hardening

## Roadmap

- v2.0: MCP Server Integration
