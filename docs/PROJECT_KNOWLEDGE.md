# Personal Job Application Agent - Project Knowledge Base

## 1. Project Overview

Personal Job Application Agent is a full-stack AI-powered job application assistant. It helps a user analyze how well a resume matches a job description, generate an English cover letter, review ATS keyword coverage, track saved job applications, and export reusable application materials.

The project uses React and Vite on the frontend, FastAPI and Python on the backend, SQLite for local application storage, monitoring, evaluation, and RAG indexing, deterministic Python security utilities for AI safety controls, and the DeepSeek API as the LLM reasoning engine. It supports PDF and DOCX resume parsing, JD analysis from pasted text or one user-provided job URL, explainable scoring, ATS keyword analysis, application tracking, DOCX/PDF export, Project Knowledge RAG, custom agent workflow orchestration, deterministic next-action recommendation, human-in-the-loop decision recording, prompt injection mitigation, secret scanning, PII minimization, safe prompt construction, LLM output leakage scanning, security audit trails, local AI monitoring, sanitized trace lookup, and offline behavioral evaluation.

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
- Added high-resolution workflow timing with monotonic `perf_counter_ns`.
- Recorded per-step and total workflow execution duration.
- Improved workflow observability without artificial delays or fake minimum durations.
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

### Version 1.7 - AI Security and Prompt Injection Mitigation

Version 1.7 added a defense-in-depth AI security layer around the RAG-powered agent workflow.

- Added deterministic prompt injection detection.
- Added credential and secret scanning.
- Added PII minimization before LLM invocation.
- Added safe prompt section isolation.
- Added LLM output leakage scanning.
- Added security audit trails.
- Integrated security steps into the Agent workflow.
- Added security unit and integration tests.

Skills demonstrated:

- AI security
- Prompt injection mitigation
- Data leakage prevention
- Secure prompt construction
- Untrusted input isolation
- Secret detection
- PII minimization
- LLM output validation
- Responsible AI
- Defense-in-depth design

### Version 1.8 - AI Monitoring and Behavioral Evaluation

Version 1.8 added a lightweight monitoring and evaluation layer for the local AI workflow.

- Added local SQLite monitoring for every Analyze workflow.
- Recorded sanitized workflow and step metrics.
- Added LLM latency and workflow latency aggregation.
- Added RAG hit-rate and reconciliation monitoring.
- Added security event and PII redaction monitoring.
- Added recommendation and human-decision metrics.
- Added sanitized trace lookup by workflow ID.
- Added an offline deterministic behavioral evaluation suite.
- Added evaluation run and result persistence.
- Added a React Monitoring dashboard.

Skills demonstrated:

- AI observability
- LLM monitoring
- Workflow tracing
- Performance metrics
- Latency analysis
- RAG evaluation
- Security monitoring
- Behavioral evaluation
- Regression testing
- Data minimization
- SQLite analytics
- FastAPI metrics APIs
- Full-stack monitoring dashboard

### Version 1.8.1 - Monitoring Data Management and Test Isolation

- Added monitoring data lifecycle controls.
- Added clear-all and filtered monitoring cleanup.
- Added workflow-specific trace deletion.
- Added evaluation-history cleanup.
- Added transactional parent-child deletion.
- Added admin-token protection for destructive APIs.
- Disabled remote destructive operations by default.
- Added configurable SQLite database paths.
- Isolated automated tests from the application database.
- Added fail-fast safeguards preventing test writes to `app.db`.
- Added frontend Data Management controls with explicit confirmation.

Skills demonstrated:

- Data lifecycle management
- Test and real-data isolation
- Safe destructive API design
- Transactional database operations
- SQLite test infrastructure
- Environment-based configuration
- Administrative authorization
- Secure token handling
- Privacy-aware retention controls
- Full-stack operational tooling

Resume bullets:

- Implemented secure monitoring data lifecycle controls with transactional cleanup, scoped deletion, admin-token authorization, and preservation of application and RAG data.
- Isolated automated tests from the application database using temporary SQLite instances and fail-fast safeguards that prevent test metrics from contaminating real monitoring data.

### Version 1.9 - Containerized Deployment, CI/CD, and Production Hardening

- Containerized the FastAPI backend.
- Added a multi-stage React and Nginx frontend image.
- Added same-origin API reverse proxying.
- Added Docker Compose production topology.
- Persisted SQLite and Project Knowledge runtime data.
- Added production configuration validation.
- Added liveness and readiness checks.
- Added request IDs and privacy-aware structured logging.
- Added SQLite-safe backup and restore workflows.
- Added existing-data migration tooling.
- Added GitHub Actions CI.
- Added GHCR image publishing configuration.
- Added Ubuntu deployment and production-security documentation.
- Added the stable `pja-br0` Docker application bridge so Compose network recreation does not invalidate host policy routing.
- Added an idempotent systemd oneshot service that routes only Frontend TCP source-port 8080 responses through the main IPv4 table when Mihomo TUN would otherwise capture Docker published-port return traffic.
- Preserved private Backend port 8000 exposure and existing Mihomo routing for Backend HTTPS and DeepSeek access.

Skills demonstrated:

- Docker
- Docker Compose
- Container security
- Nginx reverse proxy
- CI/CD
- GitHub Actions
- GitHub Container Registry
- Production configuration
- Health and readiness probes
- Persistent storage
- SQLite backup and restore
- Release engineering
- Deployment automation
- Production hardening
- Operational documentation

Resume bullets:

- Containerized a React and FastAPI AI application with Docker Compose and Nginx, implementing persistent SQLite storage, Project Knowledge persistence, health checks, and production configuration validation.
- Built GitHub Actions pipelines for Python regression tests, React production builds, Docker image validation, Compose configuration checks, and versioned GHCR image publishing.
- Developed safe deployment, SQLite backup, restore, and existing-data migration workflows for repeatable Ubuntu server operations.
- Diagnosed and fixed asymmetric Docker published-port return routing under Mihomo TUN with stable bridge naming and a least-scope, restart-safe IPv4 policy rule.

## 3. Technical Stack

- React: Builds the frontend user interface for Analyze, History, and Project Knowledge workflows.
- Vite: Provides the frontend development and production build toolchain.
- FastAPI: Provides backend REST APIs for resume analysis, application tracking, export, Project Knowledge RAG, workflow audit trails, and next-action decisions.
- Python: Implements backend orchestration, parsing, validation, SQLite operations, deterministic recommendation rules, and document export.
- Python standard library security utilities: Implement deterministic regex-based prompt injection detection, credential scanning, PII redaction, output leakage scanning, and safe security finding normalization.
- SQLite: Stores application records and local RAG metadata/chunks.
- SQLite analytics: Stores metadata-only monitoring metrics, step timings, evaluation runs, and evaluation results.
- SQLite FTS5: Provides local full-text retrieval for Project Knowledge chunks.
- DeepSeek API: Provides LLM reasoning for resume-JD matching, ATS analysis, cover letter generation, and structured JSON output.
- pypdf: Extracts text from PDF resumes.
- python-docx: Extracts DOCX resume text and generates DOCX cover letters.
- reportlab: Generates PDF analysis reports.
- Custom orchestration layer: Tracks the synchronous Analyze workflow with stable steps, statuses, safe messages, and duration measurements.
- Safe prompt builder: Constructs prompts with explicit security rules, untrusted data delimiters, prompt size controls, and an internal non-secret leakage detection marker.
- Rule-based recommendation engine: Generates explainable next actions without an additional LLM call.
- Monitoring service: Records Analyze workflow metadata, step latency, RAG metrics, security metrics, recommendation metrics, and sanitized trace data.
- Evaluation service: Runs deterministic offline behavioral and regression checks without calling DeepSeek.
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
- AI security: The backend applies deterministic prompt injection detection, secret scanning, PII minimization, untrusted data isolation, and LLM output leakage checks.
- Prompt injection mitigation: The workflow filters suspicious instruction text from untrusted JD, resume, and Project Knowledge inputs before LLM invocation.
- Secret detection: The workflow blocks credential-like content such as API keys, bearer tokens, private key headers, password assignments, and database URLs before LLM invocation.
- PII minimization: The workflow redacts emails, phone numbers, stable address patterns, and token-like URL query parameters from the LLM-bound resume copy.
- Safe prompt construction: The prompt separates trusted security rules from untrusted resume, JD, and Project Knowledge evidence sections.
- LLM output validation: The backend scans model output for credential-like content and internal marker leakage before parsing and returning results.
- Structured JSON output validation: The backend parses and normalizes LLM JSON output before returning or saving it.
- Workflow automation: Resume parsing, JD analysis, retrieval, LLM scoring, cover letter generation, recommendation, tracking, and export are combined into one workflow.
- Agentic AI foundation: The app behaves like an agent-style workflow foundation by orchestrating inputs, retrieval, LLM reasoning, validation, evidence reconciliation, recommendation, persistence, and export.
- Custom workflow orchestration: The backend records real workflow steps for validation, parsing, retrieval, LLM analysis, output validation, evidence reconciliation, recommendation, saving, and finalization.
- Multi-step AI pipelines: The Analyze API is decomposed into explicit execution stages instead of a single opaque LLM call.
- Workflow state management: Workflow steps track pending, running, completed, skipped, and failed states with measured duration.
- AI observability: The system records metadata-only Analyze metrics for workflow outcomes, step latency, LLM duration, RAG behavior, security events, and recommendations.
- LLM monitoring: The system measures LLM step duration without storing prompts or model responses.
- Workflow tracing: Sanitized trace lookup by workflow ID exposes step status and duration without user content.
- RAG evaluation: The system tracks RAG hit rate and Project Knowledge reconciliation counts.
- Security monitoring: The system aggregates prompt injection, credential detection, output leakage, and PII redaction counts.
- Behavioral evaluation: The offline suite validates security, safe prompt, RAG, recommendation, workflow timing, legacy default, and output leakage behavior.
- Regression testing: Evaluation cases are deterministic and repeatable without external LLM calls.
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
| AI security layer | Python standard library regex, FastAPI, safe prompt builder, SQLite audit fields | Prompt injection mitigation, secret detection, PII minimization, untrusted input isolation, LLM output validation | AI security, prompt injection, data leakage prevention, secure prompt construction |
| Workflow Monitoring | FastAPI, SQLite, React | Workflow metrics, latency analysis, local AI observability | workflow monitoring, LLM monitoring, latency metrics |
| RAG Monitoring | SQLite metrics, Project Knowledge RAG | RAG hit-rate analysis, reconciliation monitoring, retrieval observability | RAG evaluation, retrieval monitoring, RAG metrics |
| Security Monitoring | Security utilities, SQLite analytics, React dashboard | Security event monitoring, PII redaction metrics, finding code aggregation | security monitoring, AI security metrics, data leakage monitoring |
| Trace Explorer | FastAPI trace APIs, React UI, workflow IDs | Sanitized trace lookup, metadata-only debugging, data minimization | trace explorer, workflow tracing, observability |
| Behavioral Evaluation Suite | Python standard library, SQLite, deterministic runners | Behavioral evaluation, regression testing, rule compliance testing | offline evaluation, regression evaluation, rule compliance |
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
- Uploaded resumes, pasted JDs, fetched job URL content, Project Knowledge chunks, and LLM output are treated as untrusted data.
- Deterministic prompt injection detection filters suspicious instruction text before LLM invocation.
- Critical credential-like content is blocked before LLM invocation.
- PII minimization redacts emails, phone numbers, stable address patterns, and token-like URL query parameters from the LLM-bound resume copy.
- Safe prompt construction isolates untrusted resume, JD, and Project Knowledge evidence from trusted security rules.
- LLM output leakage scanning redacts credential-like content and blocks internal marker leakage.
- Security findings use stable codes and safe messages without storing full malicious content or detected secret values.
- These controls are heuristic and reduce risk, but they cannot guarantee complete protection against every prompt injection attack.
- Monitoring stores metadata and counts only, not raw resumes, job descriptions, prompts, model outputs, RAG chunk content, detected secret values, or attack text.
- Evaluation runs offline without DeepSeek or external LLM calls.
- Evaluation pass rate measures deterministic behavioral and rule compliance checks, not model accuracy or hiring success probability.
- The trace explorer is a local sanitized trace lookup, not distributed tracing or production APM.
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

Q: How does Version 1.7 reduce prompt injection and data leakage risk?

A: Version 1.7 uses defense-in-depth controls around the LLM call. The backend scans untrusted resume, JD, fetched job URL, and Project Knowledge content for prompt injection patterns, blocks credential-like secrets before LLM invocation, redacts common PII from the LLM-bound resume copy, builds prompts with explicit untrusted data sections, and scans LLM output for credential-like content or internal marker leakage. These are deterministic heuristic controls that reduce risk, but they do not guarantee complete prompt injection prevention or represent a formal security certification.

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
- Implemented a defense-in-depth AI security layer with prompt injection detection, secret scanning, PII redaction, untrusted context isolation, and LLM output leakage checks.
- Built a privacy-aware AI monitoring layer using FastAPI and SQLite to track workflow latency, LLM execution time, RAG hit rates, security events, and recommendation outcomes without storing raw resumes or prompts.
- Developed an offline behavioral evaluation suite for RAG evidence consistency, prompt injection controls, structured workflow behavior, and rule-based recommendation regression testing.
- Implemented sanitized trace exploration by workflow ID to diagnose step-level performance, security outcomes, and RAG behavior without exposing user content.

## 9. Future Roadmap

- Version 1.9 Docker, CI/CD, and cloud deployment.
- Version 2.0 later phases may evaluate MCP integrations after the identity and data foundation is stable.

## 10. Version 2.0 Phase 1 Foundation

- Added SQLAlchemy 2.x, psycopg 3, PostgreSQL 16, and Alembic while preserving the Version 1.9 Analyze, Project Knowledge, Monitoring, Evaluation, History, and export workflows.
- Added explicit administrator bootstrap with no default account or public registration, Argon2 password hashing, opaque server-side Sessions, HttpOnly Cookies, Origin-bound CSRF, database-backed login throttling, Session revocation, and safe audit events.
- Added ownership-scoped Career Profiles with structured experience, education, project, skill, language, certification, and job-preference records; optimistic revisions; immutable snapshots; restore; verification states; and deterministic completeness.
- Added a Resume Library with append-only Resume Versions, immutable finalized content, structured diffs, PDF/DOCX import, human review gates, private opaque file storage, duplicate detection, and cross-user IDOR protection.
- Added PostgreSQL full-text Project Knowledge retrieval using a GIN expression index while retaining SQLite FTS5 and fallback retrieval for compatible development/test paths.
- Added read-only Version 1.9 SQLite inspection and transactional PostgreSQL migration with fingerprinting, row-count and aggregate-checksum verification, idempotent migration records, malformed JSON normalization, and sequence synchronization.
- Added Version 2 PostgreSQL/private-file/Project-Knowledge backup manifests, checksum verification, guarded empty-target restore, isolated Docker Smoke tests, PostgreSQL CI integration tests, and frontend authentication/Profile/Resume tests.
- Phase 1 is an alpha development foundation and was not deployed over the live Version 1.9 production runtime.

## 11. Version 2.0.2 Job Library and Application Pipeline Milestone

- Added an ownership-scoped PostgreSQL Job Library with deterministic normalization, canonical URLs, description hashes, optimistic revisions, search/filter/sort/pagination, provenance Sources, structured evidence-bound Requirements, and soft archive/restore.
- Added secure manual, URL, PDF/DOCX, and CSV Job imports. URL acquisition pins a validated address, revalidates redirects, blocks local/private/metadata/obfuscated targets, bounds time and decompression, sends no user credentials, and executes no JavaScript. File import reuses private atomic storage and bounded parsers.
- Added deterministic exact and near duplicate detection with explainable reason codes, explicit human resolution, and transactional merge history. Merge preserves Sources, Requirements, Tasks, Applications, Notes, and Stage History and never physically deletes a Job.
- Added an explicit requirement extraction endpoint. Job Description text remains untrusted data; tests Mock the model; output must match a strict schema and exact evidence spans; all LLM items begin in `needs_review`. Import never automatically calls the model.
- Added an Application Pipeline with a validated stage-transition matrix, PostgreSQL row locks, optimistic revisions, append-only Stage History, terminal reopen confirmation, owned Resume Version links, private Notes, and soft archive.
- Added owned Tasks with due date, priority, completion/reopen, filters, relation consistency, and deterministic user-confirmed suggestions. `reminder_at` is stored only; there is no Scheduler, Worker, browser notification, or email sender.
- Added real owner-isolated Dashboard aggregates plus React Dashboard, Job Library/Detail/Import, Application Board/Detail, and Tasks pages. Drag/drop has transition prechecks, important-stage confirmation, optimistic rollback, 409 refresh, and accessible non-drag controls.
- Added Alembic revision `20260713_02`, SQLite/PostgreSQL tests, IDOR/CSRF/SSRF/Prompt Injection/CSV injection tests, Docker builds, and an isolated `pja-v2-0-2-*` Smoke on `127.0.0.1:18082` with restart and backup/restore verification.
- Runtime development marker is `2.0.0-alpha.2`; latest stable remains `v1.9.0`. Version 2.0.1 PR #6 is still the unmerged base, so Version 2.0.2 is a stacked PR and cannot be merged independently to `main`.
- This milestone has no Job/Profile matching score, tailored Resume, Cover Letter generation, Worker, automatic application, production database migration, deployment, Version 2 tag, release, or published Version 2 image.

## 12. Version 2.0.3 Explainable Matching and Application Materials

- Published `v2.0.0-alpha.2` after merging PR #6 and PR #7 in dependency order; Alpha 2 images use prerelease/SHA tags without replacing stable `latest`, and production remains Version 1.9.
- Added a deterministic, versioned 100-point matching engine across required skills, experience, projects, education, location/work authorization, languages, seniority, and preferences. LLM output never determines numeric scores, and scores are not Offer probabilities.
- Added separately reported hard filters, explicit unknown-versus-missing semantics, confirmed-fact-only positive evidence, immutable Profile/Job/Resume revision snapshots, Match history, and user-isolated Match APIs.
- Added reproducible multi-Job Rank Runs with stored Match Analyses, deadline/priority/preparation factors, hard-filter ordering, explainable strengths/gaps, and stable tie-breaking.
- Added Application Packages that snapshot the Application, Job revision, Profile revision, finalized Resume Version, and Match Analysis without altering source records.
- Added Tailored Resume, Cover Letter, and Application Answer Drafts with immutable version lineage. Edits create new Versions; finalized content cannot be overwritten; nothing is sent or submitted automatically.
- Added an injectable safe generation adapter. Tests and Smoke use deterministic or Mock providers and make no DeepSeek/network call. Configured development generation uses strict JSON, PII/Secret minimization, isolated untrusted sections, Prompt Injection handling, and output-leak scanning.
- Added independent fact validation for numbers, dates, metrics, skills, education, certification, leadership/team size, location, authorization, and salary. Unsupported/partial claims remain visible and block finalization until edited or explicitly user-confirmed for that Material Version.
- Added an Evidence side panel, Match breakdown/history, `/job-ranking`, Application Package pages, Material editing/history/diff, review, explicit claim confirmation, and finalization gates in React.
- Added Alembic revision `20260713_03` with ten matching/ranking/package/material tables, PostgreSQL upgrade/downgrade coverage, offline Alpha 3 evaluations, and isolated `pja-v2-0-3-*` Smoke on `127.0.0.1:18083` including backup/restore.
- Runtime development marker is `2.0.0-alpha.3`; latest stable remains `v1.9.0`; latest prerelease remains `v2.0.0-alpha.2`. Alpha 3 has no Tag, Release, published image, Worker, queue, Scheduler, automatic application, interview center, production database migration, or deployment.

## 13. Version 2.0.4 Reliable Agent Workflows and Final v2 Foundation

- Published `v2.0.0-alpha.3`, based Version 2.0.4 on the latest Version 2.0.3 `main`, and retained the undeployed Version 1.9 production runtime.
- Added PostgreSQL-owned Agent Runs, 20 ordered Agent Steps, append-only privacy-bounded Agent Events, append-only Approval Decisions, Transactional Outbox events, per-user AI budgets, idempotent usage ledger entries, Worker heartbeats, and Dead Letter records in Alembic revision `20260717_04`.
- Added Redis 7.4.1 and Dramatiq 2.2.0 with JSON-only safe-ID queue payloads, row-lock and lease protected duplicate delivery, exponential retry with jitter, crash and Redis-loss recovery, graceful shutdown, configurable global Worker concurrency, and no Celery/RQ/ARQ.
- Added a durable asynchronous `generate_application_package` workflow. It snapshots Profile/Job/Resume revisions, reuses Match evidence and completed Materials, validates unsupported claims, pauses without a Worker for Resume/Cover Letter/Package approvals, and never sends an application or email.
- Added idempotent creation/force-new semantics; legal, revisioned Run/Step state machines; queued and step-boundary cancellation; explicit retry/resume; daily/Run/Step token and estimated-cost budget preflight; per-user concurrency; optional high-cost approval; exact usage accounting; heartbeat readiness; and Dead Letter handling.
- Added authenticated ownership-scoped Agent Run and Approval APIs, Origin/CSRF enforcement for mutations, stale-revision `409` responses, reconnecting SSE with `Last-Event-ID`, heartbeat frames and connection limits, and safe summaries that exclude Prompt, Resume, JD, Profile PII, Session, Cookie, CSRF, keys, and database URLs.
- Added React Agent Runs, Run detail/Timeline/live progress, Approvals, retry/cancel/resume controls, SSE reconnect state, cost warnings, duplicate-click protection, idempotent existing-Run reuse, and an asynchronous default for Application Package generation while preserving Version 2.0.3 synchronous APIs.
- Hardened production configuration and Compose with private PostgreSQL/Redis/backend ports, non-root application containers, read-only filesystems, capability drops, no-new-privileges, resource limits, log rotation, secure Cookie/Origin/CSP/header checks, request/upload and login controls, database pool limits, migration locking, pre-migration backup, readiness checks, disk checks, admin Session revocation, and verified backup/restore.
- Added Backend, PostgreSQL, Redis/Worker/Outbox, frontend, migration, Compose, backup/restore, repository-safety, secret-scan, ShellCheck, and isolated `pja-v2-final-*` Mock LLM Smoke coverage on `127.0.0.1:18088` without using port 8080.
- Runtime marker is `2.0.0-alpha.4-dev+031dfa9`. Version 2.0.4 is a PR-only development milestone: no Merge, `v2.0.0` Tag/Release, production deployment, automatic application, or automatic email is authorized. Interview Center, Mock Interview, formal STAR Stories, browser extension, and multi-model routing move to Version 2.1.x.
