# Personal Job Application Agent

Version 1.1

Personal Job Application Agent is a local-first MVP for job application preparation. It parses a PDF or DOCX resume, accepts either pasted job description text or one job URL, then uses the DeepSeek API to generate a fit analysis, resume suggestions, and an English cover letter.

## Current Features

- Upload a PDF or DOCX resume
- Paste a job description
- Provide one job posting URL and extract readable page text
- Analyze resume and JD fit with DeepSeek
- Return a job summary, match score, match reason, matched skills, and missing skills
- Generate Chinese resume improvement suggestions
- Generate an English cover letter
- Process files in memory without a database

## Version 1.1 Stability Updates

- `GET /api/health` health check with service name and version
- Root API response at `GET /`
- More robust AI JSON parsing
- Safe defaults for missing AI response fields
- Match score normalization to a 0-100 integer
- Better backend validation and user-facing error messages
- Request timeouts for job URL fetching and DeepSeek calls
- Resume and JD length limits before sending content to the LLM
- Safer backend logging without resume text, full JD text, or API keys
- Frontend validation for resume and job input
- Frontend loading, error, and empty states
- Stable result rendering when optional fields are empty

## Tech Stack

- Frontend: React + Vite
- Backend: Python FastAPI
- LLM Provider: DeepSeek API
- Resume parsing: `pypdf`, `python-docx`
- URL extraction: `requests`, `beautifulsoup4`
- Storage: no database

## Project Structure

```text
.
├── backend/
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
  "version": "1.1"
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
```

If another device cannot connect, check that the cloud security group or firewall allows TCP ports `5173` and `8000`.

## API

API documentation:

```text
http://localhost:8000/docs
```

Analyze endpoint:

```text
POST /api/analyze
```

Request type: `multipart/form-data`

- `resume`: required, PDF or DOCX
- `job_text`: optional job description text
- `job_url`: optional single job posting URL

If both `job_text` and `job_url` are provided, `job_text` is used first.

Example:

```bash
curl -X POST http://localhost:8000/api/analyze \
  -F "resume=@/path/to/resume.pdf" \
  -F "job_text=We are hiring a full-stack engineer..."
```

Response shape:

```json
{
  "job_summary": "string",
  "match_score": 0,
  "match_reason": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "resume_suggestions": ["string"],
  "cover_letter": "string"
}
```

## Safety Notes

- Do not commit `.env`, `.env.local`, or `*.env` files.
- Do not put real API keys in source code, README examples, screenshots, logs, or frontend output.
- Backend logs record steps and error types, not full resume content or full JD content.
- Uploaded resumes are processed in memory and are not saved to a database.
- This project does not bulk crawl job boards.
- Only analyze user-provided text or a single user-provided job URL.
- Public dev access is for testing only; production should use HTTPS and a proper deployment setup.

## Roadmap

- Version 1.2: SQLite application tracking
- Version 1.3: explainable scoring breakdown and ATS keyword analysis
- Version 1.4: DOCX/PDF export and deployment polish
