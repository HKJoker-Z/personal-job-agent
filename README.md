# Personal Job Application Agent

Current version: v1.5.2

Personal Job Application Agent is a local-first, full-stack AI job application assistant. It parses a PDF or DOCX resume, accepts pasted job description text or one user-provided job URL, uses the DeepSeek API to generate explainable Resume-JD matching results, retrieves evidence from a curated Project Knowledge RAG source, creates an English cover letter, tracks saved applications in SQLite, and exports application materials as DOCX/PDF files.

Version 1.5.2 intentionally simplifies RAG to Project Knowledge only. The goal is not to build a general-purpose document knowledge base. The goal is to use a curated, auditable project evidence file to support AI job applications for AI, GenAI, LLM application, RAG, and agentic AI related roles.

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
- Explainable scoring breakdown across skills, projects, education, work experience, and keyword match
- Backend-controlled weighted match score calculation
- ATS keyword analysis
- Resume bullet optimization suggestions based only on existing resume or retrieved evidence
- English cover letter generation
- SQLite application history tracking
- DOCX cover letter export
- PDF analysis report export

Version 1.5.2 removes the generic knowledge base upload UI and disables generic `/api/knowledge/*` endpoints with HTTP `410 Gone`.

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

No external vector database is used in v1.5.2.

## Project Structure

```text
.
├── backend/
│   ├── data/
│   │   └── app.db            # generated locally, not committed
│   ├── database.py
│   ├── export_utils.py
│   ├── knowledge_utils.py
│   ├── main.py
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
  "version": "1.5.2"
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

Application history stores normalized AI analysis results, scoring breakdowns, ATS analysis, upgraded resume bullets, RAG mode, RAG source metadata, status, and notes. It does not store uploaded resume files or complete `resume_text`.

Project Knowledge RAG uses the existing v1.5 tables:

- `knowledge_documents` stores Project Knowledge metadata and content previews.
- `knowledge_chunks` stores parsed Project Knowledge chunks.
- `knowledge_chunks_fts` is created with SQLite FTS5 when available.

The tables remain in place to avoid breaking existing local databases, but the product UI no longer supports arbitrary knowledge document uploads.

## RAG Retrieval

Version 1.5.2 uses Project Knowledge RAG only:

- The only recommended RAG source is `docs/PROJECT_KNOWLEDGE.md`.
- The backend chunks the file and indexes it in SQLite.
- SQLite FTS5 is used when available.
- If FTS5 is unavailable, the backend falls back to lightweight keyword scoring over chunk content, title, and category.
- Only top-k relevant chunks are sent to DeepSeek during analysis.
- The entire Project Knowledge file is never sent to the LLM.
- Generic `/api/knowledge/*` endpoints are disabled in v1.5.2 and return `410 Gone`.

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

The following generic knowledge endpoints are disabled in v1.5.2 and return `410 Gone`:

- `GET /api/knowledge/documents`
- `POST /api/knowledge/documents`
- `GET /api/knowledge/documents/{id}`
- `DELETE /api/knowledge/documents/{id}`
- `GET /api/knowledge/search`

Response:

```json
{
  "detail": "Generic knowledge base upload is disabled in v1.5.2. Use Project Knowledge RAG instead."
}
```

### Application History and Export APIs

- `GET /api/applications`: returns historical application records without heavy detail fields.
- `GET /api/applications/{id}`: returns one full application record, including RAG mode and RAG sources.
- `PATCH /api/applications/{id}`: updates application status and optional notes.
- `DELETE /api/applications/{id}`: deletes one historical application record.
- `GET /api/applications/{id}/cover-letter.docx`: exports the saved cover letter as DOCX.
- `GET /api/applications/{id}/report.pdf`: exports a full PDF report, including RAG Mode and RAG Sources.

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
- Job descriptions and Project Knowledge content are treated as untrusted data in the prompt.
- The system instructs the LLM not to fabricate user experience.
- Cover letters must be grounded in the resume and retrieved Project Knowledge evidence.

## Version 1.5.2 Core Changes

- Simplified RAG to Project Knowledge only.
- Removed generic knowledge base upload UI.
- Disabled generic `/api/knowledge/*` endpoints.
- Added `docs/PROJECT_KNOWLEDGE.md` as the curated skill evidence base.
- Added a dedicated Project Knowledge upload/replace endpoint.
- Analyze supports `project` and `off` RAG modes.
- Project Knowledge rebuild/search/status APIs remain available.

## Version History

- v1.1: Stability improvements
- v1.2: SQLite application tracking
- v1.3: Explainable scoring and ATS analysis
- v1.4: DOCX/PDF export and product polish
- v1.5: RAG Knowledge Base
- v1.5.2: Project Knowledge RAG Only

## Roadmap

- v1.6: Agent workflow and orchestration
- v1.7: AI security and prompt injection mitigation
- v1.8: Monitoring and evaluation
- v1.9: Docker and cloud deployment
- v2.0: MCP server integration
