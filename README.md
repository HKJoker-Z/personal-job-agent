# Personal Job Application Agent

Current version: v1.6

Personal Job Application Agent is a local-first, full-stack AI job application assistant. It parses a PDF or DOCX resume, accepts pasted job description text or one user-provided job URL, uses the DeepSeek API to generate explainable Resume-JD matching results, retrieves evidence from a curated Project Knowledge RAG source, creates an English cover letter, recommends the next application action, tracks saved applications in SQLite, and exports application materials as DOCX/PDF files.

Version 1.6 adds a custom lightweight agent workflow orchestration layer. The synchronous Analyze API now executes explicit backend workflow steps, returns a real execution audit trail, generates a deterministic next-action recommendation, and lets the user record a human-in-the-loop decision. The project still uses Project Knowledge RAG only; it does not use LangGraph, CrewAI, AutoGen, MCP, or fake real-time streaming.

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

Version 1.5.2 removed the generic knowledge base upload UI and disabled generic `/api/knowledge/*` endpoints with HTTP `410 Gone`. Version 1.6 keeps that Project Knowledge-only RAG design.

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
- Version control: Git/GitHub

No external vector database is used in v1.6.

## Project Structure

```text
.
├── backend/
│   ├── data/
│   │   └── app.db            # generated locally, not committed
│   ├── database.py
│   ├── export_utils.py
│   ├── agent_workflow.py
│   ├── recommendation_engine.py
│   ├── knowledge_utils.py
│   ├── main.py
│   ├── test_agent_workflow.py
│   ├── test_recommendation_engine.py
│   └── requirements.txt
├── docs/
│   └── PROJECT_KNOWLEDGE.md  # curated Project Knowledge RAG source
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       └── styles.css
├── .gitignore
└── README.md
```

## Environment Variables

Create a `.env` file in the project root:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

Optional frontend API base URL:

```bash
cd frontend
printf 'VITE_API_BASE_URL=http://127.0.0.1:8000\n' > .env.local
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
npm run dev -- --host 0.0.0.0 --port 5173
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
  "version": "1.6"
}
```

## Public Development Access

The backend CORS allowlist includes:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://101.34.61.52:5173`

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Public development URLs:

```text
Frontend: http://101.34.61.52:5173
Backend:  http://101.34.61.52:8000
Health:   http://101.34.61.52:8000/api/health
Docs:     http://101.34.61.52:8000/docs
```

If another device cannot connect, check that the cloud security group or firewall allows TCP ports `5173` and `8000`.

## Database

SQLite database file:

```text
backend/data/app.db
```

The backend creates `backend/data/` and `app.db` automatically. Database files are ignored by Git.

Application history stores normalized AI analysis results, scoring breakdowns, ATS analysis, upgraded resume bullets, RAG mode, RAG source metadata, workflow IDs, workflow step audit trails, next-action recommendations, human decisions, status, and notes. It does not store uploaded resume files or complete `resume_text`.

Project Knowledge RAG uses the existing v1.5 tables:

- `knowledge_documents` stores Project Knowledge metadata and content previews.
- `knowledge_chunks` stores parsed Project Knowledge chunks.
- `knowledge_chunks_fts` is created with SQLite FTS5 when available.

The tables remain in place to avoid breaking existing local databases, but the product UI no longer supports arbitrary knowledge document uploads.

## RAG Retrieval

Version 1.6 uses Project Knowledge RAG only:

- The only recommended RAG source is `docs/PROJECT_KNOWLEDGE.md`.
- The backend chunks the file and indexes it in SQLite.
- SQLite FTS5 is used when available.
- If FTS5 is unavailable, the backend falls back to lightweight keyword scoring over chunk content, title, and category.
- Only top-k relevant chunks are sent to DeepSeek during analysis.
- The entire Project Knowledge file is never sent to the LLM.
- Generic `/api/knowledge/*` endpoints are disabled in v1.6 and return `410 Gone`.

## Agent Workflow Orchestration

Version 1.6 decomposes `POST /api/analyze` into real backend workflow steps:

1. Validate Input
2. Parse Resume
3. Acquire Job Description
4. Retrieve Project Knowledge
5. Run LLM Analysis
6. Validate Structured Output
7. Reconcile Evidence
8. Recommend Next Action
9. Save Application
10. Finalize Result

Each step records a stable key, display name, status, safe message, start time, completion time, and measured `duration_ms`. Steps can be `pending`, `running`, `completed`, `skipped`, or `failed`.

The current workflow is synchronous. Version 1.6 returns an execution audit trail after the synchronous workflow completes. The UI may show a loading message while the request is running, but it does not simulate fake step progress with timers and it does not provide real-time streaming.

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

The following generic knowledge endpoints are disabled in v1.6 and return `410 Gone`:

- `GET /api/knowledge/documents`
- `POST /api/knowledge/documents`
- `GET /api/knowledge/documents/{id}`
- `DELETE /api/knowledge/documents/{id}`
- `GET /api/knowledge/search`

Response:

```json
{
  "detail": "Generic knowledge base upload is disabled in v1.6. Use Project Knowledge RAG instead."
}
```

### Application History and Export APIs

- `GET /api/applications`: returns historical application records without heavy detail fields, plus lightweight next-action label and decision data.
- `GET /api/applications/{id}`: returns one full application record, including RAG mode, RAG sources, workflow steps, next action, and human decision data.
- `PATCH /api/applications/{id}`: updates application status and optional notes.
- `PATCH /api/applications/{id}/next-action`: records the user's decision for the Agent recommendation.
- `DELETE /api/applications/{id}`: deletes one historical application record.
- `GET /api/applications/{id}/cover-letter.docx`: exports the saved cover letter as DOCX.
- `GET /api/applications/{id}/report.pdf`: exports a full PDF report, including RAG Mode, RAG Sources, Agent Workflow, Recommended Next Action, and Human Decision.

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
- The system instructs the LLM not to fabricate user experience.
- Cover letters must be grounded in the resume and retrieved Project Knowledge evidence.

## Version 1.6 Core Changes

- Added custom Agent Workflow Orchestration for `POST /api/analyze`.
- Added workflow IDs and backend execution audit trails.
- Broke analysis into explicit steps for validation, resume parsing, JD acquisition, Project Knowledge retrieval, LLM analysis, structured output validation, evidence reconciliation, recommendation, saving, and finalization.
- Added deterministic next-action recommendation without an extra LLM call.
- Added human-in-the-loop recommendation decisions.
- Persisted workflow, recommendation, and decision data in SQLite.
- Displayed workflow and recommendations in Analyze, History Detail, and PDF reports.
- Kept Version 1.5.2 Project Knowledge RAG only behavior.

## Version History

- v1.1: Stability improvements
- v1.2: SQLite application tracking
- v1.3: Explainable scoring and ATS analysis
- v1.4: DOCX/PDF export and product polish
- v1.5: RAG Knowledge Base
- v1.5.2: Project Knowledge RAG Only
- v1.6: Agent workflow orchestration and next-action recommendation

## Roadmap

- v1.7: AI security and prompt injection mitigation
- v1.8: Monitoring and evaluation
- v1.9: Docker and cloud deployment
- v2.0: MCP server integration
