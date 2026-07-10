# Personal Job Application Agent - Project Knowledge Base

## 1. Project Overview

Personal Job Application Agent is a full-stack AI-powered job application assistant. It helps a user analyze how well a resume matches a job description, generate an English cover letter, review ATS keyword coverage, track saved job applications, and export reusable application materials.

The project uses React and Vite on the frontend, FastAPI and Python on the backend, SQLite for local application storage and RAG indexing, and the DeepSeek API as the LLM reasoning engine. It supports PDF and DOCX resume parsing, JD analysis from pasted text or one user-provided job URL, explainable scoring, ATS keyword analysis, application tracking, DOCX/PDF export, Project Knowledge RAG, custom agent workflow orchestration, deterministic next-action recommendation, and human-in-the-loop decision recording.

The RAG design is intentionally project-centered. Instead of behaving like a general-purpose document storage product, the system retrieves evidence from a curated and auditable project skill evidence file: `docs/PROJECT_KNOWLEDGE.md`. This evidence helps the model ground job matching, cover letter generation, ATS analysis, and resume bullet optimization in real project experience.

## 2. Version Roadmap and Technical Evolution

### Version 1.1 - Stability Improvements

Version 1.1 focused on reliability and stable local/public development access.

- Added a FastAPI health check endpoint.
- Improved robust DeepSeek JSON parsing.
- Added structured error handling for resume parsing, JD fetching, validation, and AI response failures.
- Added frontend validation for resume files and job input.
- Improved safe logging so sensitive resume, JD, cover letter, and API key content are not printed.
- Improved CORS and public access stability for local and server-based development.

Skills demonstrated:

- API reliability
- Full-stack debugging
- Structured LLM output validation
- Error handling
- Production-style stability thinking
- CORS/public IP debugging

### Version 1.2 - Application Tracking

Version 1.2 introduced persistent application workflow management.

- Added SQLite `application_records`.
- Added FastAPI CRUD APIs for saved application records.
- Added a History tab in the React frontend.
- Added application status tracking with statuses such as Saved, Applied, Interview, Rejected, and Offer.
- Added notes for each application record.

Skills demonstrated:

- Database design
- FastAPI CRUD API development
- Workflow management
- Persistent storage
- Application lifecycle tracking
- SQLite-backed application storage

### Version 1.3 - Explainable Scoring and ATS Analysis

Version 1.3 improved the quality and transparency of AI analysis.

- Added weighted scoring breakdowns across skills, project experience, education, work experience, and keyword matching.
- Added backend-controlled score normalization and weighted final scoring.
- Added ATS keyword analysis with important, matched, missing, and suggested keywords.
- Added upgraded resume bullet suggestions grounded in the existing resume and available evidence.

Skills demonstrated:

- Explainable AI
- ATS optimization
- Structured scoring
- LLM result normalization
- Resume-JD matching
- Structured JSON output validation

### Version 1.4 - Export and Product Polish

Version 1.4 made the workflow more reusable and product-ready.

- Added DOCX cover letter export using `python-docx`.
- Added PDF analysis report export using `reportlab`.
- Added export endpoints for saved application records.
- Improved UI structure around analysis results, history detail, scoring, ATS analysis, and export workflow.

Skills demonstrated:

- Productization
- Document generation
- Workflow automation
- User-facing AI application delivery
- REST API integration

### Version 1.5 - RAG Knowledge Base

Version 1.5 introduced local Retrieval-Augmented Generation.

- Added a SQLite RAG knowledge base.
- Added document chunking.
- Added SQLite FTS5 retrieval.
- Added fallback keyword retrieval when FTS5 is unavailable.
- Added top-k RAG source retrieval.
- Added RAG Sources display in Analyze, History, and PDF report flows.
- Added `application_records.rag_sources` for explainability.

Skills demonstrated:

- RAG
- Retrieval-Augmented Generation
- Retrieval pipeline design
- Chunking
- Evidence-based generation
- Data minimization
- SQLite FTS5 retrieval

### Version 1.5.2 - Project Knowledge RAG Only

Version 1.5.2 simplified RAG from generic knowledge uploads to a curated Project Knowledge RAG workflow.

- Simplified RAG from a generic knowledge upload system to a curated project knowledge file.
- Uses `docs/PROJECT_KNOWLEDGE.md` as the only recommended RAG source.
- Added a dedicated upload/replace function for `PROJECT_KNOWLEDGE.md`.
- Added Project Knowledge rebuild, status, and search APIs.
- Analyze supports Project Knowledge RAG or RAG off.
- Reduced retrieval noise and data leakage risk by removing arbitrary knowledge upload workflows from the product UI.

Skills demonstrated:

- Project-centered RAG design
- Retrieval scope control
- Data minimization
- Responsible AI
- Maintainable AI application architecture
- Evidence-grounded job matching
- Responsible LLM application design

### Version 1.6 - Agent Workflow Orchestration

Version 1.6 added a custom lightweight orchestration layer for the Analyze workflow.

- Broke resume-job analysis into explicit backend workflow steps: input validation, resume parsing, job description acquisition, Project Knowledge retrieval, LLM analysis, structured output validation, evidence reconciliation, next-action recommendation, application saving, and result finalization.
- Added workflow IDs and execution audit trails with step status, safe messages, timestamps, and measured duration.
- Added a deterministic rule-based next-action recommendation engine without making an extra LLM call.
- Added human-in-the-loop decision recording so the user can accept, dismiss, or complete a recommendation.
- Persisted workflow steps, next-action recommendations, and user decisions in SQLite.
- Displayed workflow data and recommendations in Analyze, History, and PDF reports.
- Preserved Project Knowledge RAG and RAG evidence reconciliation so RAG-supported skills are not incorrectly listed as missing.

Skills demonstrated:

- Agentic AI foundation
- Custom workflow orchestration
- Multi-step AI pipelines
- Workflow state management
- Human-in-the-loop design
- Rule-based decision support
- RAG-enhanced reasoning workflow
- Full-stack system integration
- API development
- SQLite schema migration

## 3. Technical Stack

- React: Builds the frontend user interface for Analyze, History, and Project Knowledge workflows.
- Vite: Provides the frontend development and production build toolchain.
- FastAPI: Provides backend REST APIs for resume analysis, application tracking, export, Project Knowledge RAG, workflow audit trails, and next-action decisions.
- Python: Implements backend orchestration, parsing, validation, SQLite operations, deterministic recommendation rules, and document export.
- SQLite: Stores application records and local RAG metadata/chunks.
- SQLite FTS5: Provides local full-text retrieval for Project Knowledge chunks.
- DeepSeek API: Provides LLM reasoning for resume-JD matching, ATS analysis, cover letter generation, and structured JSON output.
- pypdf: Extracts text from PDF resumes.
- python-docx: Extracts DOCX resume text and generates DOCX cover letters.
- reportlab: Generates PDF analysis reports.
- Custom orchestration layer: Tracks the synchronous Analyze workflow with stable steps, statuses, safe messages, and duration measurements.
- Rule-based recommendation engine: Generates explainable next actions without an additional LLM call.
- REST API: Connects the React frontend with FastAPI backend workflows.
- Git/GitHub: Used for version control, feature branches, release history, and project documentation.
- Ubuntu server: Used for development and public IP testing.
- CORS/public IP debugging: Supports local and public development URLs for frontend-backend integration testing.

## 4. AI and GenAI Skills Demonstrated

- Generative AI: The system uses an LLM to generate match analysis, cover letters, keyword suggestions, and resume bullet improvements.
- LLM applications: The project wraps the DeepSeek API in a real application workflow with validation, persistence, UI, and exports.
- RAG: The system retrieves relevant project evidence before calling the LLM.
- Retrieval-Augmented Generation: Top-k Project Knowledge chunks are injected into the analysis prompt to ground generated outputs.
- Project-centered RAG: The RAG source is scoped to a curated project evidence file instead of arbitrary document uploads.
- Document chunking: The backend splits `docs/PROJECT_KNOWLEDGE.md` into searchable chunks before indexing.
- SQLite FTS5 retrieval: Project Knowledge chunks are indexed with SQLite FTS5 when available.
- Top-k evidence injection: Only the most relevant retrieved chunks are inserted into the LLM prompt.
- DeepSeek API integration: The backend calls the DeepSeek API through an OpenAI-compatible client and validates JSON responses.
- FastAPI API development: The backend exposes REST APIs for Analyze, History, Export, and Project Knowledge status/rebuild/upload/search.
- Prompt engineering: The backend prompt includes output schema rules, grounding rules, untrusted input handling, and anti-fabrication instructions.
- Structured JSON output validation: The backend parses and normalizes LLM JSON output before returning or saving it.
- Workflow automation: Resume parsing, JD analysis, retrieval, LLM scoring, cover letter generation, recommendation, tracking, and export are combined into one workflow.
- Agentic AI foundation: The app behaves like an agent-style workflow foundation by orchestrating inputs, retrieval, LLM reasoning, validation, evidence reconciliation, recommendation, persistence, and export.
- Custom workflow orchestration: The backend records real workflow steps for validation, parsing, retrieval, LLM analysis, output validation, evidence reconciliation, recommendation, saving, and finalization.
- Multi-step AI pipelines: The Analyze API is decomposed into explicit execution stages instead of a single opaque LLM call.
- Workflow state management: Workflow steps track pending, running, completed, skipped, and failed states with measured duration.
- Human-in-the-loop design: The Agent recommends the next action while the user controls accept, dismiss, or complete decisions.
- Rule-based decision support: The next-action recommendation uses deterministic backend rules instead of an additional model call.
- RAG-enhanced reasoning workflow: Project Knowledge retrieval and evidence reconciliation influence matching, ATS keywords, scoring, and recommendations.
- API development: FastAPI endpoints support analysis, application history, Project Knowledge rebuild/search/status/upload, and exports.
- System integration: The project integrates frontend, backend, SQLite, file parsing, LLM API calls, and document export.
- SQLite-backed application storage: Application records and RAG indexes are persisted locally in SQLite.
- Document parsing: PDF and DOCX resumes are parsed into text for LLM analysis.
- ATS keyword analysis: The system extracts important JD keywords, matched keywords, missing keywords, and optimization suggestions.
- Explainable AI: Match scores include dimension-level scoring breakdowns and evidence.
- Responsible AI: The prompt and backend validation discourage fabrication and preserve data minimization.
- Data leakage prevention: Only top-k Project Knowledge chunks are sent to the LLM, not the entire knowledge base.
- Evidence-based generation: Cover letters and scoring evidence must be grounded in the resume or retrieved Project Knowledge evidence.
- Export workflow automation: The system generates DOCX cover letters and PDF analysis reports from saved records.

## 5. Feature-to-Skill Mapping

| Project Feature | Technologies Used | Skills Demonstrated | Relevant Job Keywords |
|---|---|---|---|
| Resume parsing | FastAPI, pypdf, python-docx, Python | Document parsing, backend validation, file handling | PDF parsing, DOCX parsing, resume parsing, backend engineering |
| DeepSeek analysis | DeepSeek API, OpenAI-compatible client, prompt engineering | LLM application development, structured output, GenAI integration | LLM applications, Generative AI, API integration, prompt engineering |
| Explainable scoring | Python, FastAPI, structured JSON, weighted scoring | Explainable AI, scoring normalization, backend-controlled ranking | explainable AI, ranking, scoring, evaluation |
| ATS keyword analysis | DeepSeek API, JSON validation, React UI | ATS optimization, keyword extraction, resume-JD matching | ATS, keyword matching, resume optimization |
| Application tracking | SQLite, FastAPI CRUD APIs, React | Database design, workflow management, persistent storage | SQLite, CRUD, application lifecycle, workflow automation |
| DOCX/PDF export | python-docx, reportlab, FastAPI streaming responses | Document generation, export workflow automation, productization | DOCX export, PDF generation, automation |
| Project Knowledge RAG | docs/PROJECT_KNOWLEDGE.md, chunking, SQLite | Project-centered RAG, evidence-based generation, retrieval scope control | RAG, Retrieval-Augmented Generation, evidence grounding |
| SQLite FTS5 retrieval | SQLite FTS5, fallback keyword retrieval | Retrieval pipeline design, local search, resilient implementation | full-text search, FTS5, information retrieval |
| Agent workflow orchestration | Python dataclasses, FastAPI, SQLite | Custom workflow orchestration, multi-step AI pipeline, execution audit trail | agentic AI foundation, workflow orchestration, audit trail |
| Next-action recommendation | Deterministic Python rules, scoring breakdown, ATS analysis | Rule-based decision support, critical skill analysis, recommendation logic | decision support, next best action, explainable recommendation |
| Human-in-the-loop decision | FastAPI PATCH API, SQLite, React UI | User-controlled AI workflow, decision recording, workflow governance | human-in-the-loop, HITL, AI governance |
| Frontend/Backend integration | React, Vite, Fetch API, FastAPI REST API | Full-stack integration, state management, UI workflow design | React, FastAPI, REST API, full-stack |
| Safe environment variable handling | .env, python-dotenv, .gitignore | Secrets management, safe configuration, operational hygiene | environment variables, API key security, secure configuration |

## 6. Security and Responsible AI Design

- API keys are stored in `.env` and ignored by Git.
- The DeepSeek API key is never printed in backend logs.
- Uploaded resume files are processed temporarily.
- Original resume files are not stored.
- Full `resume_text` is not saved in `application_records`.
- Logs avoid printing sensitive user content, including full resumes, full JDs, cover letters, knowledge chunks, and API keys.
- RAG sends only top-k relevant chunks from `docs/PROJECT_KNOWLEDGE.md`.
- The RAG source is curated and auditable.
- Job descriptions and project knowledge content are treated as untrusted data.
- The system instructs the LLM not to fabricate user experience.
- Cover letters must be grounded in the resume and retrieved evidence.
- Generic arbitrary knowledge upload is removed from the product UI in v1.5.2 to reduce retrieval noise and data leakage risk.
- Workflow step messages are safe status messages and do not include full resumes, full JDs, full Project Knowledge chunks, or API keys.
- The next-action recommendation is rule-based and explainable; it is not presented as a hiring probability.
- The Agent does not automatically submit applications or modify the user's resume.

## 7. Interview Talking Points

Q: Why not just use DeepSeek directly?

A: DeepSeek is the reasoning engine, but this project provides the workflow layer around it. The application parses resumes, accepts job descriptions, retrieves project evidence, validates structured JSON output, normalizes scoring, stores application records, shows RAG sources, and exports DOCX/PDF materials. That workflow layer turns an LLM call into a usable job application assistant.

Q: How does your RAG implementation work?

A: The system uses a curated project knowledge file, chunks it, indexes it with SQLite FTS5, retrieves top-k relevant evidence, and injects it into the LLM prompt. If FTS5 is unavailable, the backend falls back to lightweight keyword retrieval. The final analysis shows RAG sources so the user can see which evidence influenced the output.

Q: Why did you simplify the RAG knowledge base?

A: The goal was not to build a general document storage product. I simplified the RAG source to a curated project evidence file to reduce noise, improve auditability, and focus the retrieval on AI job application use cases.

Q: How do you reduce hallucination?

A: The system requires evidence from the resume or project knowledge file, validates structured JSON output, normalizes scoring fields, and shows RAG sources. The prompt explicitly tells the model not to fabricate user experience, skills, education, companies, or project claims.

Q: What did you learn from this project?

A: I learned full-stack AI application development, RAG, structured LLM output validation, API design, data minimization, document export, workflow orchestration, human-in-the-loop design, and productization. I also learned how to turn an LLM API into a practical workflow with persistence, explainability, and user-facing controls.

Q: Is the workflow built with LangGraph or another orchestration framework?

A: No. Version 1.6 uses a custom lightweight orchestration layer. It records real backend steps, durations, statuses, and safe messages for the synchronous Analyze workflow. This creates a foundation that could later be migrated to a framework such as LangGraph, but the current implementation does not claim to use LangGraph, CrewAI, AutoGen, MCP, or real-time streaming orchestration.

Q: How does the next-action recommendation work?

A: The backend uses deterministic rules based on match score, critical missing skills, ATS keyword gaps, scoring breakdown, and Project Knowledge evidence. It recommends applying now, improving the resume first, upskilling first, saving for later, or skipping the role. The rule-based confidence is an explainable indicator, not a machine learning probability.

## 8. Resume Bullet Examples

- Built a full-stack AI job application assistant using React, FastAPI, SQLite, and DeepSeek API to automate resume-JD matching, ATS analysis, and cover letter generation.
- Implemented a project-centered RAG pipeline with document chunking, SQLite FTS5 retrieval, fallback keyword retrieval, and top-k evidence injection to improve evidence-based job matching.
- Designed explainable scoring logic with weighted breakdowns across skills, project experience, education, work experience, and keyword matching.
- Developed application tracking features with SQLite-backed CRUD APIs, status management, notes, and historical analysis records.
- Added DOCX/PDF export workflows using python-docx and reportlab to generate reusable job application materials.
- Simplified the RAG design to a curated project knowledge file to reduce retrieval noise, improve auditability, and improve maintainability.
- Designed a custom agent orchestration layer that decomposes resume-job analysis into traceable workflow steps, including resume parsing, RAG retrieval, LLM analysis, evidence validation, and recommendation generation.
- Implemented a deterministic next-action engine with human-in-the-loop decisions to recommend applying, improving the resume, upskilling, saving, or skipping a role.
- Persisted workflow audit trails and user decisions in SQLite and exposed them through FastAPI, React, and PDF reports.

## 9. Future Roadmap

- Version 1.7 AI security and prompt injection mitigation.
- Version 1.8 Monitoring and evaluation.
- Version 1.9 Docker and cloud deployment.
- Version 2.0 MCP server integration.
