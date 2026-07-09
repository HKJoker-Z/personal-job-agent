# Personal Job Application Agent

Version 1.2

Personal Job Application Agent is a local-first MVP for job application preparation and tracking. It parses a PDF or DOCX resume, accepts either pasted job description text or one job URL, uses the DeepSeek API to generate a fit analysis and English cover letter, then can save successful analysis results to a local SQLite application history.

## Current Features

- Upload a PDF or DOCX resume
- Paste a job description
- Provide one job posting URL and extract readable page text
- Analyze resume and JD fit with DeepSeek
- Return company name, job title, job summary, match score, match reason, matched skills, and missing skills
- Generate Chinese resume improvement suggestions
- Generate an English cover letter
- Save successful analysis results to local SQLite history
- View historical application records
- Update application status: `Saved`, `Applied`, `Interview`, `Rejected`, `Offer`
- Delete application records
- Search and filter records by status, company name, or job title

## Version 1.2 Updates

- SQLite local application tracking
- Save analysis result to history from `POST /api/analyze`
- History page with list, detail, edit, and delete actions
- Status and search filters for historical records
- AI output now includes `company_name` and `job_title`
- Database records do not store uploaded resume files
- Database records do not store complete `resume_text`

## Tech Stack

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Resume parsing: `pypdf`, `python-docx`
- URL extraction: `requests`, `beautifulsoup4`
- Storage: SQLite through Python `sqlite3`

## Project Structure

```text
.
├── backend/
│   ├── data/
│   │   └── app.db            # generated locally, not committed
│   ├── database.py
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       └── styles.css
├── .env.example
├── .gitignore
└── README.md
```

## Database

SQLite database file:

```text
backend/data/app.db
```

The backend creates `backend/data/` and `app.db` automatically when it starts or when database helpers are imported.

The database stores application tracking records only. It saves `resume_filename`, AI analysis results, status, and notes. It does not save uploaded resume files, and it does not save complete `resume_text`. Database files are ignored by Git.

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
  "version": "1.2"
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

If both `job_text` and `job_url` are provided, `job_text` is used first.

Example:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "resume=@/path/to/resume.pdf" \
  -F "job_text=We are hiring a full-stack engineer..." \
  -F "save_to_history=true"
```

Response shape:

```json
{
  "company_name": "string",
  "job_title": "string",
  "job_summary": "string",
  "match_score": 0,
  "match_reason": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "resume_suggestions": ["string"],
  "cover_letter": "string",
  "application_id": 1,
  "saved_to_history": true
}
```

### `GET /api/applications`

Returns historical application records without heavy detail fields.

Query parameters:

- `status`: optional, one of `Saved`, `Applied`, `Interview`, `Rejected`, `Offer`
- `search`: optional, searches `company_name` and `job_title`
- `limit`: optional, default `50`
- `offset`: optional, default `0`

### `GET /api/applications/{id}`

Returns one full application record, including match reason, job summary, skill lists, suggestions, cover letter, and notes.

### `PATCH /api/applications/{id}`

Updates application status and optional notes.

```json
{
  "application_status": "Applied",
  "notes": "Followed up with recruiter."
}
```

### `DELETE /api/applications/{id}`

Deletes one historical application record.

```json
{
  "deleted": true,
  "id": 1
}
```

## Safety Notes

- Do not commit `.env`, `.env.local`, or `*.env` files.
- Do not commit SQLite database files such as `backend/data/app.db`.
- Do not put real API keys in source code, README examples, screenshots, logs, or frontend output.
- Backend logs record steps and error types, not full resume content or full JD content.
- Uploaded resumes are processed in memory and are not saved to disk.
- The database does not store complete `resume_text`.
- This project does not bulk crawl job boards.
- Only analyze user-provided text or a single user-provided job URL.
- Public dev access is for testing only; production should use HTTPS and a proper deployment setup.

## Roadmap

- Version 1.3: explainable scoring breakdown and ATS keyword analysis
- Version 1.4: DOCX/PDF export and deployment polish
