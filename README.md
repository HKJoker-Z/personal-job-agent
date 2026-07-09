# Personal Job Application Agent

Current version: v1.4

Personal Job Application Agent is a local-first Job Application Assistant. It parses a PDF or DOCX resume, accepts pasted job description text or one job URL, uses the DeepSeek API to generate explainable Resume-JD matching results, creates an English cover letter, tracks saved applications in SQLite, and exports application materials as DOCX/PDF files.

## Core Features

- Resume parsing from PDF and DOCX
- Job description analysis from pasted text or one user-provided job URL
- DeepSeek-powered resume and job matching analysis
- Explainable scoring breakdown across skills, projects, education, work experience, and keyword match
- Backend-controlled weighted match score calculation
- ATS keyword analysis
- Resume bullet optimization suggestions based only on existing resume content
- English cover letter generation
- SQLite application history tracking
- Status updates: `Saved`, `Applied`, `Interview`, `Rejected`, `Offer`
- History search and filtering
- DOCX cover letter export
- PDF analysis report export

## Demo / Screenshots

Screenshots can be added here after running the app.

## Tech Stack

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Storage: SQLite through Python `sqlite3`
- Resume parsing: `pypdf`, `python-docx`
- DOCX export: `python-docx`
- PDF export: `reportlab`
- URL extraction: `requests`, `beautifulsoup4`

## Project Structure

```text
.
├── backend/
│   ├── data/
│   │   └── app.db            # generated locally, not committed
│   ├── database.py
│   ├── export_utils.py
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
  "version": "1.4"
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

The backend creates `backend/data/` and `app.db` automatically. The database stores application tracking records, normalized AI analysis results, scoring breakdowns, ATS analysis, upgraded resume bullets, status, and notes.

The database does not store uploaded resume files, and it does not store complete `resume_text`. Database files are ignored by Git.

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

Response includes:

- `company_name`
- `job_title`
- `job_summary`
- `match_score`
- `match_reason`
- `matched_skills`
- `missing_skills`
- `resume_suggestions`
- `cover_letter`
- `scoring_breakdown`
- `ats_analysis`
- `upgraded_resume_bullets`
- `application_id`
- `saved_to_history`

### `GET /api/applications`

Returns historical application records without heavy detail fields.

Query parameters:

- `status`: optional, one of `Saved`, `Applied`, `Interview`, `Rejected`, `Offer`
- `search`: optional, searches `company_name` and `job_title`
- `limit`: optional, default `50`
- `offset`: optional, default `0`

### `GET /api/applications/{id}`

Returns one full application record, including match reason, job summary, skill lists, suggestions, cover letter, scoring breakdown, ATS analysis, upgraded resume bullets, status, and notes.

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

### `GET /api/applications/{id}/cover-letter.docx`

Exports the saved cover letter for one application record as a DOCX file.

The generated document contains:

- Cover Letter title
- Company Name
- Job Title
- Generated Cover Letter

If no cover letter was generated, the DOCX contains `No cover letter generated.`.

### `GET /api/applications/{id}/report.pdf`

Exports a full application analysis report as a PDF file.

The generated report contains:

- Company Name
- Job Title
- Job URL
- Application Status
- Match Score
- Match Reason
- Job Summary
- Scoring Breakdown
- ATS Keyword Analysis
- Matched Skills
- Missing Skills
- Resume Suggestions
- Upgraded Resume Bullets
- Cover Letter

## Export Behavior

- Cover Letter DOCX files are generated in memory with `python-docx`.
- Analysis Report PDF files are generated in memory with `reportlab`.
- Exported files are returned directly to the browser.
- Exported files are not stored long-term on the server.
- Exported files do not include API keys, uploaded resume files, or complete `resume_text`.

## Scoring Weights

The final `match_score` returned by the backend is calculated from `scoring_breakdown`:

- Skills Match: 35%
- Project Experience: 25%
- Education: 15%
- Work Experience: 15%
- Keyword Match: 10%

If the AI returns a separate `match_score`, it is treated only as a reference. The backend normalized weighted score is the final score returned by the API.

## Safety Notes

- Do not commit `.env`, `.env.local`, or `*.env` files.
- Do not commit SQLite database files such as `backend/data/app.db`.
- Do not commit generated DOCX/PDF export files.
- Do not put real API keys in source code, README examples, screenshots, logs, or frontend output.
- Uploaded resumes are processed in memory and are not saved to disk.
- The database does not store complete `resume_text`.
- Backend logs record steps and error types, not full resume content, full JD content, cover letter content, or report content.
- This project does not bulk crawl job boards.
- Only analyze user-provided text or a single user-provided job URL.
- Do not invent resume experience, projects, education, work experience, or skills.
- Resume bullet improvements must be based only on existing resume content.
- ATS keyword suggestions should only recommend adding keywords when the user truly has relevant experience.
- Public dev access is for testing only; production should use HTTPS and a proper deployment setup.

## Version History

- v1.1: Stability improvements
- v1.2: SQLite application tracking
- v1.3: Explainable scoring and ATS analysis
- v1.4: DOCX/PDF export and product polish

## Roadmap

- v1.5: Docker and production deployment
- v1.6: Agent workflow and next-action recommendation
- v1.7: Evaluation and testing suite
