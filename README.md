# Personal Job Application Agent

Current version: v1.5

Personal Job Application Agent is a local-first Job Application Assistant. It parses a PDF or DOCX resume, accepts pasted job description text or one job URL, uses the DeepSeek API to generate explainable Resume-JD matching results, retrieves relevant evidence from a local RAG knowledge base, creates an English cover letter, tracks saved applications in SQLite, and exports application materials as DOCX/PDF files.

Version 1.5 does not include interview answer materials, Interview Q&A, or interview answer generation.

## Core Features

- Resume parsing from PDF and DOCX
- Job description analysis from pasted text or one user-provided job URL
- DeepSeek-powered resume and job matching analysis
- RAG Knowledge Base
- Knowledge document upload from PDF, DOCX, TXT, and Markdown
- Document chunking for local retrieval
- SQLite-backed local retrieval
- SQLite FTS5 retrieval when available
- Lightweight keyword retrieval fallback when FTS5 is unavailable
- RAG-enhanced analysis with top-k evidence injection
- RAG Sources in Analyze results and History Detail
- RAG Sources in PDF analysis reports
- Explainable scoring breakdown across skills, projects, education, work experience, and keyword match
- Backend-controlled weighted match score calculation
- ATS keyword analysis
- Resume bullet optimization suggestions based only on existing resume or knowledge evidence
- English cover letter generation
- SQLite application history tracking
- DOCX cover letter export
- PDF analysis report export

## Supported Knowledge Types

- Resume
- Project Experience
- Skill Profile
- Past Cover Letter
- Company Research
- Other

This version does not include interview answer materials.

## Demo / Screenshots

Screenshots can be added here after running the app.

## Tech Stack

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Storage: SQLite through Python `sqlite3`
- Local retrieval: SQLite FTS5 if available, with lightweight keyword fallback
- Resume parsing: `pypdf`, `python-docx`
- Knowledge parsing: `pypdf`, `python-docx`, TXT, Markdown
- DOCX export: `python-docx`
- PDF export: `reportlab`
- URL extraction: `requests`, `beautifulsoup4`

No external vector database is used in v1.5.

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
  "version": "1.5"
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

Application history stores normalized AI analysis results, scoring breakdowns, ATS analysis, upgraded resume bullets, RAG source metadata, status, and notes. It does not store uploaded resume files or complete `resume_text`.

Knowledge Base stores document metadata and parsed text chunks. It does not store the uploaded original knowledge files.

## RAG Retrieval

Version 1.5 uses local SQLite retrieval:

- `knowledge_documents` stores metadata and content previews.
- `knowledge_chunks` stores parsed text chunks.
- `knowledge_chunks_fts` is created with SQLite FTS5 when available.
- If FTS5 is unavailable, the backend falls back to lightweight keyword scoring over chunk content, title, and category.

Only top-k relevant chunks are sent to DeepSeek during analysis. The full knowledge base is never sent to the LLM.

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
- `rag_top_k`: optional integer, defaults to `5`, allowed range `1-10`

If both `job_text` and `job_url` are provided, `job_text` is used first.

Response includes all v1.4 analysis fields plus:

- `used_knowledge_base`
- `rag_sources`

### `GET /api/applications`

Returns historical application records without heavy detail fields.

### `GET /api/applications/{id}`

Returns one full application record, including RAG sources.

### `PATCH /api/applications/{id}`

Updates application status and optional notes.

### `DELETE /api/applications/{id}`

Deletes one historical application record.

### `GET /api/applications/{id}/cover-letter.docx`

Exports the saved cover letter for one application record as a DOCX file.

### `GET /api/applications/{id}/report.pdf`

Exports a full application analysis report as a PDF file, including RAG Sources.

### `GET /api/knowledge/documents`

Returns Knowledge Base document metadata.

Query parameters:

- `category`: optional
- `search`: optional
- `limit`: optional, default `50`
- `offset`: optional, default `0`

### `POST /api/knowledge/documents`

Creates a Knowledge Base document.

Request type: `multipart/form-data`

- `title`: required
- `category`: required, one of the supported knowledge types
- `content_text`: optional
- `file`: optional PDF, DOCX, TXT, MD, or Markdown file

At least one of `content_text` or `file` is required. If both are provided, the backend combines the pasted text with the parsed file text.

### `GET /api/knowledge/documents/{id}`

Returns one Knowledge Base document with its parsed chunks.

### `DELETE /api/knowledge/documents/{id}`

Deletes one Knowledge Base document and its chunks.

### `GET /api/knowledge/search`

Tests local retrieval.

Query parameters:

- `query`: required
- `top_k`: optional, default `5`

## Export Behavior

- Cover Letter DOCX files are generated in memory with `python-docx`.
- Analysis Report PDF files are generated in memory with `reportlab`.
- Exported files are returned directly to the browser.
- Exported files are not stored long-term on the server.
- PDF reports include RAG Sources when available.

## Safety Notes

- Do not commit `.env`, `.env.local`, or `*.env` files.
- Do not commit SQLite database files such as `backend/data/app.db`.
- Do not commit uploaded knowledge files.
- Do not commit generated DOCX/PDF export files.
- Do not put real API keys in source code, README examples, screenshots, logs, or frontend output.
- Uploaded resumes are processed in memory and are not saved to disk.
- Uploaded knowledge files are processed in memory and are not saved to disk.
- Knowledge Base stores parsed text chunks, not original files.
- Application history does not store complete `resume_text`.
- Backend logs record steps and counts, not full resume content, full JD content, knowledge chunk content, cover letter content, or report content.
- The backend does not send the whole knowledge base to the LLM.
- The backend sends only top-k relevant chunks to the LLM.
- JD and Knowledge Base content are treated as untrusted data in the prompt.
- This project does not bulk crawl job boards.
- Only analyze user-provided text or a single user-provided job URL.
- Do not invent resume experience, projects, education, work experience, or skills.
- This version does not include interview answer materials.
- Public dev access is for testing only; production should use HTTPS and a proper deployment setup.

## Version History

- v1.1: Stability improvements
- v1.2: SQLite application tracking
- v1.3: Explainable scoring and ATS analysis
- v1.4: DOCX/PDF export and product polish
- v1.5: RAG knowledge base

## Roadmap

- v1.6: Agent workflow and orchestration
- v1.7: AI security and prompt injection mitigation
- v1.8: Monitoring and evaluation
- v1.9: Docker and cloud deployment
- v2.0: MCP server integration
