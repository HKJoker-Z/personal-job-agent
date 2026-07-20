# Personal Job Agent — Verified Project Knowledge

## 1. Project overview

Personal Job Agent is a privately operated, single-user-oriented web application for evidence-grounded resume and job-description analysis. Version 2.0.2 combines a React/Vite interface, a FastAPI backend, PostgreSQL persistence, Redis-backed Dramatiq workers, a transactional Outbox, Project Knowledge retrieval, and a hardened Docker Compose/Nginx production topology.

The application helps a user maintain resume versions, paste a job description or provide one safely fetched HTTPS job URL, run an explainable match analysis, review Project Knowledge evidence, save an analysis to History, and inspect monitoring or historical Agent Run data. AI output is assistive and requires human review. The system does not submit job applications.

## 2. Product scope

The Version 2.0.2 user workspace contains:

- Dashboard
- Analyze
- Profile
- Resume Library and immutable Resume Versions
- saved analysis History and document exports
- Project Knowledge status, replacement, index rebuild, and search
- historical Agent Runs, SSE progress, and safe cancellation
- administrator Monitoring and Evaluation
- Account and Session controls

Analyze does not require a Job, Application, Approval, or Task entity. It accepts exactly one Resume source and exactly one job-description source, then optionally saves the normalized result to History.

## 3. Current Version 2.0.2 feature set

Version 2.0.2 contains the full Version 2.0.1 feature set: secure Remember Me with a bounded server-side Session lifetime, optional email-only browser persistence, one responsive application navigation component, direct Resume-to-JD analysis, and Project Knowledge evidence retrieval that changes matching results when supported evidence is found. Its additional change is PostgreSQL 16 backup/restore compatibility and release safety, not product behavior.

Normal Sessions use a 30-minute idle timeout and a 24-hour absolute timeout by default. Remember Me Sessions have a configurable absolute limit of no more than 30 days. The browser receives only a random opaque Session cookie. Passwords are never persisted by application JavaScript.

The analysis result reports `used_knowledge_base`, `retrieval_count`, safe `rag_sources`, matched and missing skills, scoring details, and a skill-to-evidence mapping. Project Knowledge skills may move from missing to matched only when retrieved text directly supports them.

## 4. Removed features

Version 2.0.2 retains the Version 2.0.1 retirement of public Jobs, Job Rankings, Applications, Approvals, and Tasks workspaces and their mutation APIs. Old browser routes show a Feature Removed page. Authenticated calls to retired API prefixes return a uniform HTTP 410 `FEATURE_REMOVED` response.

The associated PostgreSQL tables, SQLAlchemy models, Alembic history, and existing rows are intentionally retained for backup, restore, rollback, and historical compatibility. No destructive migration drops these records. Existing `waiting_for_approval` Agent Runs are read-only and can be cancelled; the simplified Analyze flow creates no new Approval Request.

## 5. Technical architecture

The request path is Browser → HTTPS Nginx Edge → Nginx Frontend → FastAPI Backend. Backend traffic to PostgreSQL and Redis stays on private Docker networks. The backend performs authentication, ownership checks, input scanning, resume parsing, safe URL acquisition, Project Knowledge retrieval, prompt construction, model invocation, output validation, History persistence, and monitoring.

PostgreSQL is authoritative for application state and durable Outbox events. Redis is a private transient queue transport. Dramatiq consumes safe-ID-only messages. The standalone Outbox Dispatcher publishes database-owned work and recovers interrupted or lost transient deliveries. SSE exposes authenticated, sanitized progress events for retained Agent Runs.

## 6. Backend stack

- Python 3.12
- FastAPI and Uvicorn
- SQLAlchemy 2 typed ORM and repositories
- Alembic schema revisions through `20260717_04`
- psycopg 3 PostgreSQL connectivity
- Redis 7 client and Dramatiq workers
- OpenAI-compatible client for DeepSeek
- pypdf and python-docx for Resume extraction
- python-docx and ReportLab for saved-analysis exports
- deterministic security, matching, grounding, monitoring, and evaluation services

The code retains a reviewed compatibility layer for migrated Version 1 analysis and Project Knowledge operations while Version 2 domain modules use SQLAlchemy repositories and services.

## 7. Frontend stack

The frontend uses React 19, React Router, Vite 8, semantic HTML, and project-owned CSS variables. It does not depend on a large UI framework. One `AppLayout` component provides the desktop top navigation and the collapsible mobile/iPad navigation, including focus states and `aria-current="page"`.

The login form uses browser password-manager conventions: an email input with `autocomplete="username"` and a password input with `autocomplete="current-password"`. It includes password visibility, Caps Lock feedback, safe generic errors, loading state, and duplicate-submit prevention.

## 8. Database architecture

Production runs PostgreSQL 16. SQLAlchemy 2 models cover users, password hashes, server-side Sessions, profiles, resumes and versions, legacy analysis History, Project Knowledge documents and chunks, monitoring/evaluation, Agent Runs, Steps, Events, Outbox entries, worker heartbeats, usage records, and retained retired-feature tables.

Alembic owns the production schema. The current head is `20260717_04`. Version 2.0.2 adds no database migration. SQLite remains supported only for isolated development, compatibility tests, and the verified SQLite-to-PostgreSQL source migration workflow; it is not the production database.

The SQLite migration computes a source fingerprint, preserves primary keys where safe, assigns ownership, validates row counts and aggregate checksums, records the migration run, and verifies the source did not change. The known migrated source fingerprint is operational metadata, not an application claim.

## 9. Worker and queue architecture

Redis 7 is a private message broker, not the source of truth. Dramatiq executes background work with configured concurrency, heartbeats, step leases, bounded retries, token/cost budgets, and safe payload validation. PostgreSQL transactional Outbox rows are created in the same transaction as durable state.

The Outbox Dispatcher selects rows with database locking, publishes only validated identifiers, records publish state, retries with bounded delay, recovers stale publications, and moves exhausted deliveries to dead-letter records. Worker claims and leases make duplicate delivery safe. In production, the standalone dispatcher is enabled and duplicate dispatch inside the worker supervisor is disabled.

## 10. Authentication and Session security

Passwords are hashed with Argon2 and are never reversibly stored. Login errors do not reveal whether an email exists. Login attempts use database-backed throttling and fingerprinted identifiers.

Sessions are stored server-side with only a hash of the opaque cookie token. Cookies are `Secure`, `HttpOnly`, `SameSite=Lax`, and path-scoped. Login rotates any prior Session. Logout revokes the current Session. Logout-all provides user/admin revoke-all behavior. Password change revokes old Sessions and issues a new rotated Session. Inactive accounts fail authentication. Every Session has an absolute expiration.

Unsafe authenticated requests require a Session-bound CSRF token and a trusted Origin. Ownership filters and repository predicates prevent IDOR access. The optional remembered email uses only `pja.v2.login.rememberedEmail` in LocalStorage after trim, lowercase normalization, length bounding, and email validation. No password, Session token, or CSRF token is written there.

## 11. AI security

Resume text and external job descriptions are scanned for prompt injection, credential-like data, private keys, and PII before model use. Job URLs pass a guarded acquisition layer that restricts schemes, blocks unsafe/private destinations, validates redirects, limits size and time, and mitigates SSRF.

Prompts isolate `USER_PROVIDED_RESUME`, `UNTRUSTED_JOB_DESCRIPTION`, and `TRUSTED_PROJECT_EVIDENCE`. Evidence content is data, never executable instruction. Safe prompt rules forbid secret disclosure, invented experience, instruction override, and unsupported leadership, scale, revenue, user-count, or business-outcome claims.

Model output is scanned for secrets and internal-marker leakage, parsed as structured JSON, normalized, and independently checked against Resume and retrieved Project Knowledge evidence. Unsupported matched skills are removed. Unsupported generated letter claims block the letter from being returned or persisted.

## 12. RAG architecture

Project Knowledge is the only user-facing RAG corpus. A Git baseline exists at `docs/PROJECT_KNOWLEDGE.md`; production maintains a distinct runtime copy. Updating production requires hashing and backing up the runtime copy before an explicit replace and index rebuild.

The backend cleans and chunks the Markdown file, stores the document and chunks in PostgreSQL, and retrieves with `to_tsvector`, `websearch_to_tsquery`, and `ts_rank`. SQLite FTS5 and bounded keyword fallback remain only for development compatibility. The request default is top-k 5 with an enforced range of 1–10.

When RAG is off, retrieval is skipped, no Project Knowledge text enters the prompt, `used_knowledge_base` is false, `retrieval_count` is zero, and `rag_sources` is empty. When RAG is on, a bounded query is constructed from sanitized Resume and JD text, relevant chunks are retrieved and scanned, and only those chunks enter the trusted evidence zone. Empty retrieval degrades safely without fabricated evidence.

Responses expose only document, section, chunk ID, relevance score, and supported skills. Full chunk text is not returned in `rag_sources`.

## 13. Matching methodology

Matching combines model-generated structured analysis with backend normalization and deterministic evidence reconciliation. The final weighted score uses skills match 35%, project experience 25%, education 15%, work experience 15%, and keyword match 10%.

Synonym groups improve recall for PostgreSQL/Postgres, Redis/message broker, Dramatiq/background worker, FastAPI/Python API, React/frontend, Docker Compose/container orchestration, SSE/live progress, RAG/retrieval augmented generation, and CI/CD/GitHub Actions. A synonym match is not evidence by itself: the Resume or a retrieved Project Knowledge chunk must contain supporting facts.

## 14. Monitoring and evaluation

The monitoring service stores sanitized metadata such as workflow outcome, step timing, LLM latency, RAG hit/reconciliation counts, security finding counts, recommendation metadata, and workflow IDs. It does not store raw resumes, job descriptions, prompts, provider responses, passwords, or secrets in metrics.

Administrator-only monitoring and deterministic offline evaluations support regression review without calling DeepSeek. Data-management operations require explicit confirmation and preserve History and Project Knowledge unless the scoped operation states otherwise.

## 15. Deployment and infrastructure

Production uses Docker Compose with an HTTPS Nginx Edge, Nginx/React Frontend, FastAPI Backend, PostgreSQL 16, Redis 7, Dramatiq Worker, and Outbox Dispatcher. Backend 8000, PostgreSQL 5432, and Redis 6379 are not host-published.

Runtime fixes formalized in Version 2.0.1 include idempotent Redis ownership initialization without unconditional `chown -R`, read-only Nginx roots with UID/GID 101 writable tmpfs directories, `cap_drop: ALL` on long-running Edge and Frontend containers, unique `frontend-v2` and `backend-v2` Docker DNS aliases, unambiguous Nginx upstream names, exact release-version health assertions, and rollback-safe candidate deployment.

The stable `pja-br0` bridge, narrow IPv4 policy rule preference 8999, routing service, and Mihomo configuration remain outside application change scope. The production Edge joins only the necessary application network; retained Version 1.9 containers must be detached from that network during Version 2 service, with a documented reconnect rollback command.

## 16. Backup and recovery

The PostgreSQL backup tool uses PostgreSQL 16 `pg_dump` custom format with no owner or ACL and a synchronized exported snapshot. Before dump it parses the server, `pg_dump`, `pg_restore`, and `psql` numeric majors and requires all to equal 16. The manifest records safe server/client versions, immutable server/tool image digests, archive format/SHA-256, application/Alembic versions, every public table count and aggregate checksum, validated foreign keys, sequences, indexes, ownership, private files, and Project Knowledge hash without secrets.

Restore validates checksum and manifest before writes, requires archive dump major = restore major = empty target server major = 16 and the same controlled tool digest, then runs `pg_restore --exit-on-error --single-transaction`. It reports success only after the complete database inventory, file checksums, Project Knowledge, and application readiness match. Dump SQL or custom archives are never edited to bypass compatibility. A real CI rehearsal uses separate internal networks and temporary PostgreSQL 16 Volumes with no published 5432; a test-only PostgreSQL 17 client proves both dump and restore fail before writes.

Version 2.0.1 was formally released but never deployed because its required production Restore rehearsal exposed a PostgreSQL 17.10 client against PostgreSQL 16. Version 2.0.2 is the direct upgrade target from Version 2.0.0. Version 2.0.1 artifacts remain immutable and are neither deployed nor used as rollback targets.

Every production upgrade preserves PostgreSQL and Redis volumes, runtime files, the runtime Project Knowledge copy, Version 2.0.0 image digests/configuration, and Version 1.9 rollback assets. Rollback changes images/configuration; it does not delete volumes or tables.

## 17. Testing and CI

Backend unit/integration tests cover authentication, Session TTLs, CSRF, ownership, Profiles, Resumes, Project Knowledge indexing/search, RAG reconciliation, prompt security, output grounding, monitoring/evaluation, PostgreSQL migrations, Redis/Worker behavior, Outbox durability, backup/restore, and retired API boundaries.

Frontend Vitest/Testing Library coverage includes secure login behavior, email-only persistence, password visibility, single navigation, active/mobile states, removed navigation/routes, direct Analyze, RAG controls, and safe source display. CI also compiles Python, builds the Vite production bundle, runs PostgreSQL integration, builds both Docker images, validates Compose, runs ShellCheck and repository secret/path safety, executes an isolated Mock LLM smoke test, and performs a strict PostgreSQL 16 Backup/Restore rehearsal with client-17 pre-write negative gates. CI never calls real DeepSeek.

GitHub Actions publishes GHCR images from annotated semantic release tags. Version, major/minor, major, latest, tag, and commit SHA tags for each component resolve to that component’s immutable digest.

## 18. Evidence-backed resume bullets

- Built and deployed a private React/FastAPI resume-to-job analysis application backed by PostgreSQL 16, SQLAlchemy 2, Alembic, Redis 7, Dramatiq, and Docker Compose.
- Implemented server-side Argon2 authentication with opaque hashed Sessions, Secure/HttpOnly/SameSite cookies, Session-bound CSRF, rotation, absolute expiration, rate limiting, and ownership checks.
- Integrated PostgreSQL full-text Project Knowledge retrieval into a guarded RAG pipeline with top-k evidence, source metadata, skill reconciliation, prompt-injection scanning, and unsupported-claim blocking.
- Designed a PostgreSQL transactional Outbox with Redis delivery, Dramatiq workers, leases, heartbeat monitoring, recovery, and dead-letter handling.
- Migrated verified SQLite application, monitoring, evaluation, and Project Knowledge records into Alembic-managed PostgreSQL using source fingerprints, row-count checks, and aggregate checksum validation.
- Hardened an HTTPS Docker Compose deployment with private data services, non-root read-only Nginx containers, writable tmpfs, unique network aliases, exact version health checks, PostgreSQL client/server major gates, strict isolated restore, and rollback assets.
- Built GitHub Actions validation and GHCR release automation for Python, React, PostgreSQL, Docker, Compose, shell, repository-safety, and isolated Mock LLM tests.

These bullets describe implementation facts only. They do not claim automatic application submission, commercial scale, hiring outcomes, team leadership, revenue, or user counts.

## 19. Interview-ready project explanations

RAG: “I keep one curated Project Knowledge document as the only corpus. I chunk it, index it in PostgreSQL full-text search, retrieve only a bounded top-k set, scan it, and pass it in a distinct evidence zone. The backend then reconciles skills and strips unsupported claims instead of trusting the model response.”

Reliability: “PostgreSQL owns workflow and Outbox state; Redis is transient delivery. Publishing uses locked Outbox rows, and worker leases, recovery, heartbeat, and dead-letter logic allow safe retries after Redis or process restarts.”

Authentication: “The browser receives an opaque Secure/HttpOnly cookie. The database stores its hash plus idle and absolute expiries. Remember Me changes only the bounded server-side expiry and cookie persistence; application code never stores the password.”

Deployment: “I create a PostgreSQL 16 backup with matching major-version tools, prove it restores strictly into an isolated empty PostgreSQL 16 target, stage immutable application digests on a private localhost port, and only then switch the existing HTTPS Edge. Rollback restores the previous digests and config without removing volumes or historical tables.”

## 20. Feature-to-skill mapping

| Feature | Verifiable skills |
| --- | --- |
| Analyze and structured results | FastAPI, structured LLM output, normalization, explainable scoring |
| Project Knowledge RAG | PostgreSQL FTS, chunking, top-k retrieval, evidence mapping |
| Resume Library | React, SQLAlchemy repositories, immutable versioning, file validation |
| Server-side Sessions | Argon2, secure cookies, CSRF, rotation, revocation, rate limiting |
| Safe job URL | SSRF mitigation, redirect and response bounds, untrusted input handling |
| Worker/Outbox | Redis, Dramatiq, transactions, idempotency, recovery, observability |
| Monitoring/Evaluation | privacy-aware telemetry, deterministic evaluation, regression testing |
| Production Compose | Nginx, HTTPS, Docker networks, least privilege, health checks |
| Backup/Restore | PostgreSQL operations, manifests, checksums, recovery drills |
| CI/Release | GitHub Actions, Docker builds, GHCR immutable digests, release engineering |

## 21. Responsible AI controls

- AI content is advisory and requires human review.
- The system never automatically applies to a job.
- RAG is limited to one curated project evidence source.
- External JD and URL content remain untrusted.
- Secrets are blocked and PII is minimized before model invocation.
- The model cannot create source metadata; source fields come from retrieval.
- Skills require direct Resume or retrieved evidence support.
- Unsupported generated claims are blocked.
- Monitoring avoids raw user and provider content.
- Tests and CI use deterministic mock providers; real provider checks use only fictional data and bounded tokens.

## 22. Known limitations

The deployment is a single-host Compose architecture, not Kubernetes or high availability. PostgreSQL full-text retrieval is lexical rather than embedding-based. Evidence reconciliation relies on bounded normalization and synonym rules and can miss semantic equivalence. URL extraction cannot parse every job site. LLM analysis can still be incomplete or stylistically poor even after safety validation. Historical Agent Runs may reference retired workflows and are not resumable in Version 2.0.2.

## 23. Future roadmap

Future work may evaluate improved retrieval quality, more precise claim-to-evidence linking, accessibility refinements, operator observability, and safer zero-downtime deployment mechanics. Any future capability must be separately scoped, tested, and released. Version 2.0.2 does not include Version 2.1 features, an interview system, a browser extension, automatic application submission, or claims of guaranteed job-search success.
