# Personal Job Agent — Verified Project Knowledge

## Project Overview

Personal Job Agent is a private, administrator-led web application for
evidence-grounded Resume and Job Description analysis. The current stable and
production version is **2.0.3**. The current Alembic schema revision is
`20260721_05` (`head`).

The application uses a React/Vite frontend, a FastAPI/Python backend,
SQLAlchemy 2, PostgreSQL 16, Redis, Dramatiq, a Transactional Outbox, Nginx,
Docker Compose, and the DeepSeek API. It helps a user manage a Career Profile
and saved Resumes, analyze one Resume against one JD, optionally retrieve
verified Project Knowledge evidence, inspect the normalized result, and save it
to History.

AI output is advisory and requires human review. Personal Job Agent does not
automatically submit applications, send email, contact employers, or guarantee
Applicant Tracking System (ATS), interview, or hiring outcomes.

## Current Version 2.0.3 Changes

Version 2.0.3 adds tolerant JSON extraction/normalization, at most one
format-only DeepSeek repair, and deterministic local fallback. Results identify
`complete`, `repaired`, `partial`, or `fallback` state.

The Resume page now accepts PDF, DOCX, TXT, MD, and Markdown (10 MB default).
The latest successful upload becomes Primary and Analyze loads its active
Version. Alembic `20260721_05` adds `resumes.is_primary`, backfills the newest
active Resume per user, and preserves existing data.

## Current Product Workflow

1. An administrator creates an account through the trusted server CLI; there is
   no public registration endpoint.
2. The user signs in and may choose bounded Remember Me behavior.
3. The user maintains a Career Profile and its owned experience, education,
   project, skill, language, and certification data.
4. The user uploads a Resume on the Resume page. A successful upload creates a
   private File Asset, a Resume, and a Resume Version, then selects that Resume
   as Primary.
5. Analyze loads the Primary Resume automatically. The user may select another
   active Resume Version or provide a request-only PDF/DOCX override.
6. The user pastes a Job Description or provides one supported HTTPS job URL.
7. The user may enable or disable Project Knowledge RAG and choose top-k 1–10.
8. The backend normalizes and scans input, retrieves evidence when enabled,
   builds a safe prompt, and requests compact judgments from DeepSeek.
9. The backend parses, repairs or falls back, validates evidence, reconciles
   skills, calculates scoring, and generates trusted RAG source metadata.
10. The user reviews warnings and evidence and may save the result to History.
11. Saved History can be viewed, updated, removed, or exported as cover-letter
    DOCX and analysis-report PDF.

The direct Analyze workflow is independent of a Job, Application, Approval, or
Task database entity.

## Current Feature Scope

Current capabilities are Dashboard; Analyze with Primary/saved/request-only
Resume sources, pasted/safely fetched JD, optional Project RAG and History;
revision-aware Career Profile; Resume Library, Versions, private File Assets,
diff/finalize/archive; History detail, notes/status, decisions and DOCX/PDF
exports; Project Knowledge status/replace/rebuild/search; administrator
Monitoring and offline Evaluation; historical Agent Run detail/Steps/Events/SSE
and cancellation; and Account password/Session controls.

## Removed or Disabled Features

Jobs, Job Rankings, Applications, Approvals, and Tasks are removed or disabled
from the current workspace and public operating flow. Old browser routes show a
Feature Removed page. Authenticated retired API prefixes return HTTP
`410 FEATURE_REMOVED`.

New package-based Agent Runs and Agent retry/resume actions tied to the retired
Application workflow are also disabled. Existing Agent Runs remain readable
and cancellable. Existing waiting-for-approval runs cannot be resumed through
the retired Approval workflow.

Historical SQLAlchemy models, Alembic revisions, PostgreSQL tables, and existing
rows remain for backup, rollback, and compatibility. Their presence does not
make them current product features. No destructive retirement migration deletes
that historical data.

## Technical Architecture

Personal Job Agent is a modular monolith with supporting PostgreSQL, Redis,
worker, frontend, and operational processes. Concise companion references are
the [architecture overview](ARCHITECTURE.md), [ADR index](adr/README.md), and
[fictional Version 2.0.3 demo](demo/README.md). The authenticated frontend also
includes a static, read-only
[Architecture page (`/architecture`)](../frontend/src/pages/ArchitecturePage.jsx).

The production request path is:

`Browser → HTTPS Nginx Edge → Nginx Frontend → FastAPI Backend`

Nginx Edge terminates TLS. Frontend Nginx serves the React/Vite static bundle
and reverse-proxies `/api` to FastAPI. Backend 8000, PostgreSQL 5432, and Redis
6379 are not host-published.

FastAPI performs authentication, CSRF and ownership checks, input scanning,
Resume parsing, safe job URL acquisition, Project Knowledge retrieval, prompt
construction, DeepSeek invocation, tolerant parsing, evidence reconciliation,
History persistence, and monitoring.

PostgreSQL 16 is authoritative for application and durable workflow state.
Redis is a private transient queue broker. Dramatiq workers consume safe,
identifier-only messages. A standalone Outbox Dispatcher publishes durable
PostgreSQL Outbox events to Redis and recovers interrupted delivery. Worker and
Outbox services have separate heartbeats and health checks.

The current direct Resume/JD Analyze request is synchronous and does not create
a new public Agent Run. The Worker, Transactional Outbox, leases, retries,
dead-letter records, and SSE remain implemented and deployed as the reliable
Agent execution foundation and for retained workflow state.

## Backend Stack

Python 3.12, FastAPI 0.115.6, Uvicorn, Pydantic, SQLAlchemy 2.0.51, Alembic
1.18.5, and psycopg 3 implement the API, validation, repositories, services,
schema, and PostgreSQL access. Redis 7.4.1 and Dramatiq 2.2 implement queue
transport/workers. The OpenAI-compatible client calls DeepSeek `deepseek-chat`.
`pypdf`, `python-docx`, ReportLab, Beautiful Soup, and guarded HTTP acquisition
support extraction, exports, and job URL input.

A compatibility layer serves migrated Version 1 History, Project Knowledge,
monitoring, and Evaluation; Version 2 domains use SQLAlchemy services.

## Frontend Stack and Routes

React 19.2.7, React Router 7.18.1, Vite 8.1.3, semantic HTML, and project-owned
CSS implement the frontend. One `AppLayout` supplies responsive desktop,
mobile, and iPad navigation. Routes cover Login, Dashboard, Analyze, History,
Resumes, Profile, Project Knowledge, Agent Runs, Account, and administrator
Monitoring/Evaluation. The authenticated `/architecture` route renders a static,
read-only system overview without an API or external network request. Retired
workflow routes render Feature Removed and do not appear in navigation.

## Resume Management

### Supported Resume formats

The Resume page accepts PDF, DOCX, TXT, `.md`, and `.markdown`. PDF requires a
valid signature and selectable text. DOCX requires valid Office structure and
passes archive-bomb limits. Text is decoded as UTF-8 or a detected fallback.
Extracted text is capped at 200,000 characters.

The Analyze page's temporary file override accepts PDF or DOCX. TXT/Markdown
content is available to Analyze through a successfully saved Resume Version.

### Resume data relationships

- `file_assets.user_id` owns a private file with opaque `storage_key`, original
  filename, media type, size, SHA-256, and timestamps.
- `resumes.user_id` owns a logical Resume with title, status, `is_primary`,
  `active_version_id`, and archive time.
- `resume_versions.resume_id` links an immutable numbered Version. It stores
  parent/source IDs, `content_json`, `parsed_text`, draft/final status, and audit
  fields. `source_file_id` links imported content to its File Asset.

Repository queries always scope Resume, Version, and File Asset access to the
authenticated user. Referenced File Assets cannot be independently deleted.
Resume deletion is a non-destructive archive operation.

### Primary Resume behavior

Upload validation and text extraction finish before database or Primary Resume
state changes. A failed upload therefore cannot disturb the current primary.

A successful upload atomically creates the Resume/Version, clears the old
primary, and sets the new Resume. Partial unique index
`uq_resumes_user_primary_active` enforces at most one unarchived Primary Resume
per `user_id` in PostgreSQL and SQLite.

Analyze loads the Primary Resume's active Version. Another stored Version or
temporary PDF/DOCX changes one request only. Archiving Primary selects the most
recently updated active Resume; with none left, the endpoint returns `null` and
Analyze shows upload guidance.

## Analysis Pipeline

### Input normalization

Analyze accepts one Resume and one JD source. Empty input is rejected. It removes
NUL/HTML, normalizes whitespace/newlines, and preserves useful structure.
Defaults are 100,000 Resume and 60,000 JD characters; section-aware reduction
handles oversized text.

### RAG retrieval and safe prompt

With RAG on, a bounded query combines AI/skill terms, JD keywords, and limited
JD/Resume prefixes. Retrieved chunks enter `TRUSTED_PROJECT_EVIDENCE`; Resume
and JD enter `USER_PROVIDED_RESUME` and `UNTRUSTED_JOB_DESCRIPTION`.

### DeepSeek and structured output

One main DeepSeek request asks for matched/missing/unknown skills, concise
assessments, evidence references, unsupported-claim candidates, and
recommendations. DeepSeek does not own final scoring, sources, History identity,
or audit metadata.

Parsing proceeds in this order:

1. Standard JSON parsing.
2. Balanced-object extraction from fences or prose.
3. Wrapper/trailing-comma normalization.
4. Pydantic aliases, defaults, safe coercion, bounds, and ignored extras.
5. At most one format-only repair if local parsing is unusable.
6. Deterministic fallback if provider/repair remains unusable.

No parser evaluates model text as code.

### Evidence reconciliation and scoring

Evidence IDs are valid only for `resume` or current-request `pk:<chunk_id>`.
The Backend checks actual supporting text; unknown IDs/unsupported matches are
rejected without deleting unrelated valid fields.

One normalized skill has one final state. Direct chunk evidence may move a skill
from missing to matched. Unsupported candidate claims produce warnings;
unsupported generated letter/bullet content is cleared.

Final score weights are backend-owned:

- Skills Match: 35%.
- Project Experience: 25%.
- Education: 15%.
- Work Experience: 15%.
- Keyword Match: 10%.

The Backend generates scoring, `match_score`, `rag_sources`, evidence mapping,
workflow Steps, and safe provider metadata. Saving to History is optional.

## Analysis Result States

### `complete`

The main model response is directly usable and has no normalization, missing
optional-field, evidence-reference, or unsupported-claim warning that downgrades
the result.

### `repaired`

The result remains model-derived, but local wrapper/format normalization or the
single format-only repair call was needed. This state does not mean the complete
analysis was called twice.

### `partial`

Usable model content is returned, but optional fields required safe defaults,
aliases/null normalization produced warnings, or unsupported claim/evidence
content was removed. Valid fields remain available.

### `fallback`

The provider timed out, returned a provider error, emitted unusable/truncated
output, or could not be recovered by the one repair. The backend performs a
deterministic curated keyword/synonym comparison and returns the stable result
shape with local scoring, recommendations, and available RAG evidence.

Fallback is more basic than full AI analysis. The system guarantees a stable
fallback structure for covered failures, not a successful DeepSeek call or a
complete model analysis every time.

## Project Knowledge RAG

### Source and index

Project Knowledge is the only user-facing RAG corpus. Git baseline
`docs/PROJECT_KNOWLEDGE.md` and the separate production runtime copy are managed
by hash/backup. Generic `/api/knowledge/*` operations return HTTP 410.

The indexer cleans up to 30,000 characters, makes 1,000-character chunks with
125-character overlap, and stores one document plus chunks in PostgreSQL.

Production tokenizes technical terms, uses OR semantics (up to 20 tokens), and
ranks `to_tsvector('simple', content)` through `websearch_to_tsquery`/`ts_rank`.
No hit uses bounded keyword search. SQLite tests use FTS5 then keyword fallback.

### Top-k, evidence IDs, and sources

Top-k defaults to 5 and is clamped to 1–10. Chunk IDs become `pk:<chunk_id>`;
the model may cite them, but only the Backend validates them and builds sources.

`rag_sources` contains logical document, heading-derived section when available,
chunk ID, score, and supported skills. It excludes chunk/full-document content.

### Skill coordination and synonyms

Exact synonyms cover PostgreSQL/Postgres, Redis/message broker,
Dramatiq/background worker, FastAPI/Python API, React/frontend, Docker Compose,
SSE/live progress, RAG/Retrieval-Augmented Generation, and CI/CD/GitHub Actions.

A synonym is recall, not proof. Chunks detected under Known Limitations, Future
Roadmap, or Removed Features headings are rejected as positive skill evidence.
Project skills must not become invented employment, leadership, scale, revenue,
or user-count claims.

### RAG off and rebuild behavior

With RAG off, retrieval and evidence prompt injection are skipped,
`used_knowledge_base=false`, `retrieval_count=0`, and `rag_sources=[]`. With RAG
on but no hit, analysis continues without fabricated evidence.

The formal workflow is authenticated replace/upload, rebuild, status, and
search. Rebuild replaces Project Knowledge chunks and removes duplicate logical
records. Production requires hash, backup, database summary, baseline
comparison, rebuild, and search validation.

## Authentication and Session Security

`users` supports `admin`/`user`; there is no public registration. The trusted
CLI reads passwords without echo, never as command arguments.

Passwords are hashed with Argon2 through `pwdlib`. Login uses a generic invalid
credential message and database-backed throttling with keyed fingerprints.

Sessions are PostgreSQL records. The browser receives an opaque cookie; only
its SHA-256 hash and the CSRF hash are stored. Production cookies are `Secure`,
`HttpOnly`, `SameSite=Lax`, path `/`.

Normal defaults are 30-minute idle/24-hour absolute expiry. Remember Me is
bounded to 1–30 days (default 30), never infinite.

Login rotates; logout/logout-all/password change/deactivation revoke applicable
Sessions. Unsafe requests require trusted Origin and Session-bound CSRF.

Ownership predicates protect Profile, Resume, File, History, and Agent data from
cross-user access. The frontend stores the current CSRF token in React memory,
not browser storage.

Remember email stores only a normalized email at
`pja.v2.login.rememberedEmail`. JavaScript never stores plaintext password,
Session token, or CSRF token in browser storage.

## AI Reliability

DeepSeek can return Markdown fences, prose around JSON, wrapper objects,
trailing commas, unexpected aliases, nulls, optional-field omissions, scalar
values where a list was requested, numeric strings, truncated output, or no
usable response. Network timeouts and provider 5xx errors are also possible.

Version 2.0.3 treats these as expected reliability conditions. It uses bounded
local parsing first, tolerates non-critical schema differences, requests one
format-only repair only when necessary, and selects local fallback when the
model path is unusable. Non-critical omissions no longer force the entire
analysis to fail.

DeepSeek provides compact judgments; the backend remains authoritative for
evidence validation, scoring, RAG source metadata, status, warnings, workflow
audit data, and History identity. A complete network outage can only produce
the simpler deterministic fallback, not a full DeepSeek-quality analysis.

## AI Security and Grounding

Resume/JD is untrusted. Deterministic checks scan prompt injection, credentials,
API/private keys, and PII. Critical secret-like content blocks model use;
best-effort PII minimization and safe logging reduce exposure.

Prompt boundaries separate Resume, untrusted JD, and trusted Project evidence.
Rules forbid instruction override, secrets, invented experience, and unsupported
leadership, scale, revenue, user-count, or outcome claims.

Job URL acquisition restricts schemes/destinations/redirects, pins resolution,
bounds time/size, and mitigates Server-Side Request Forgery (SSRF).

Model output is parsed without evaluation and scanned for secret/marker leakage.
Only current Resume/chunk IDs are valid. Unknown IDs are ignored with warnings;
RAG sources come from retrieval state, not model output.

Ordinary unsupported claims/evidence do not block a usable result. The Backend
keeps legal fields, warns, removes unsupported skills/material, and may mark the
result partial. Output leakage or critical secrets still fail closed.

These controls reduce risk but do not guarantee immunity from every prompt
injection, secret pattern, or incorrect model judgment.

## Monitoring and Evaluation

Monitoring stores sanitized outcome/status, total/Step timing, LLM latency, RAG
counts, security summaries, recommendations, and workflow IDs. Metrics exclude
raw Resume/JD/prompt/response/chunks, passwords, and detected secrets.

Monitoring shows overview, Step timing, RAG/security/recommendation summaries,
and metadata-only traces. Administrator cleanup requires preview and exact
confirmation for filtered/all metrics, one trace, or Evaluation history, while
preserving History and Project Knowledge.

The PostgreSQL workflow-Step summary is aggregated in the database instead of
loading every matching metric into Python. In an isolated PostgreSQL 16.14
benchmark with 300,000 synthetic Step rows and 194,399 rows inside the measured
window, two warm-ups plus seven measured runs showed median database execution
falling from 541.065 ms to 185.212 ms and median application-level execution
falling from 1,308.238 ms to 163.765 ms. The six returned summaries were
identical, the 17,656 KiB disk sort and temporary I/O were removed, and no new
index or migration was required. These are local comparative benchmark results,
not production latency claims.

Offline Evaluation runs reviewed behavioral/security/retrieval/recommendation/
timing cases without DeepSeek. Pass rate is regression evidence, not model
accuracy or hiring probability.

History separately supports cover-letter DOCX and analysis-report PDF export.
Version 2.0.3 does not provide OpenTelemetry export, Prometheus, Grafana,
Langfuse, or distributed tracing.

Worker and Outbox health are part of readiness. Worker heartbeat, stale-worker
checks, dispatcher heartbeat, durable Outbox state, retries, leases, recovery,
and dead-letter records support operational diagnosis without logging unsafe
payload bodies.

## Deployment and Production Engineering

Production is single-host Docker Compose: Nginx HTTPS Edge, Nginx/React
Frontend, FastAPI Backend, PostgreSQL 16.9, Redis 7.4.1, Dramatiq Worker, and
Outbox Dispatcher. Only Edge 8080 is public.

Backend/Frontend use immutable GHCR digests. GitHub Actions validates and
publishes; production promotion remains manual.

Long-running services use non-root users, read-only roots, dropped capabilities,
`no-new-privileges`, bounded tmpfs, and rotated logs. Nginx tmpfs ownership is
set for UID/GID 101.

Retained fixes include idempotent Redis initialization, unique `frontend-v2`/
`backend-v2` aliases, exact version health, and rollback-safe candidates.

TLS uses TLS 1.2/1.3 and a Let's Encrypt IP certificate. `pja-br0`, IPv4 policy
preference 8999, routing service, and Mihomo are out-of-scope host infrastructure.

### Backup and Restore

Backup uses PostgreSQL 16 custom archive, no owner/ACL, synchronized snapshot,
private-file archive, and runtime Project Knowledge.

Server, `pg_dump`, `pg_restore`, and `psql` majors must all equal 16. Server/tool
images use immutable digests; client 17 fails before writes.

Manifest records application/Alembic versions, archive/file SHA-256, immutable
provenance, all public table counts/checksums, foreign keys, sequences, indexes,
ownership, and knowledge inventory. Restore validates an empty target, uses
`pg_restore --exit-on-error` in one transaction, and compares complete
inventory with explicit owner mapping where authorized.

Version 2.0.1 was not deployed after restore rehearsal exposed a PostgreSQL
17.10 archive incompatible with PostgreSQL 16. Version 2.0.2 added these strict
gates; Version 2.0.3 retains them.

### Candidate, health, and rollback

Upgrade stages immutable images on internal `127.0.0.1:18090`, then checks exact
2.0.3 health/readiness, head schema, healthy/private dependencies, stable
restarts, Resume/Primary, analysis, RAG, History, and restore assets.

Readiness checks database/schema, files, Project Knowledge/search, Redis, Worker,
disk, auth initialization, and LLM configuration without calling DeepSeek.

Rollback restores Version 2.0.2 digests/config without deleting volumes, Resume
files, backups, or knowledge. Additive `is_primary` is backward compatible;
database restore is only for a separate data incident.

## Data Migration

Version 1.9 production used SQLite for History, Project Knowledge, monitoring,
and Evaluation. Version 2 production requires PostgreSQL.

The verified migration reader inspects the SQLite source, computes a source
fingerprint, and records row counts. The PostgreSQL writer preserves primary
keys where safe, assigns the selected owner, migrates compatibility tables, and
validates row counts and aggregate checksums. It records a migration run and
rechecks that the source did not change during the operation.

Post-migration verification covers foreign-key consistency and PostgreSQL
sequences so future inserts do not collide. Reports contain safe summaries, not
production user content. SQLite remains only for isolated development,
compatibility tests, and the migration source workflow; it is not the current
production database.

Alembic history is linear through:

- `20260712_01`: Version 2 identity, Profile, Resume, compatibility, and base
  persistence.
- `20260713_02`: Job Library/Application Pipeline history.
- `20260713_03`: matching and Application materials history.
- `20260717_04`: reliable Agent Runs, Worker, Outbox, approvals, budgets, usage,
  heartbeats, and dead letters.
- `20260721_05`: one active Primary Resume per user.

Retired feature tables remain intentionally present after migration.

## Testing and CI

Backend tests cover config, auth/Session/CSRF/ownership, Profile, Resume/Primary,
analysis repair/fallback, RAG/security/grounding, History, monitoring/Evaluation,
Worker/Outbox, readiness, Backup Restore, and retirement boundaries.

PostgreSQL integration covers Alembic, services, migration, knowledge FTS,
cleanup, constraints, and ownership. SQLite tests use temporary safe databases.

Frontend tests cover login/email, navigation, retired routes, Profile, Resume
upload/Primary, Analyze override/four states/RAG, History, Agent pages, and
Monitoring.

CI compiles/tests Python, runs PostgreSQL 16 integration, tests/builds React,
builds images, validates Compose/Shell/repository safety, runs production-runtime
and Mock LLM smoke, and rehearses PostgreSQL 16 Backup Restore plus client-17
negative gates.

CI does not call DeepSeek. Any real-provider validation is explicit, bounded,
fictional, and separate from ordinary CI.

## Feature-to-Skill Mapping

| Implemented feature | Evidence-backed skill |
| --- | --- |
| FastAPI API and Pydantic contracts | REST API design, validation, safe error boundaries |
| SQLAlchemy 2 repositories and ownership | relational modeling, transactions, IDOR prevention |
| PostgreSQL 16 | production relational database design and full-text search |
| Alembic `20260721_05` | forward/backward schema migration and data backfill |
| Redis and Dramatiq | asynchronous processing, transient queue transport, worker health |
| Transactional Outbox | reliable event delivery, recovery, idempotency, dead-letter handling |
| React and Vite | authenticated frontend application and responsive navigation |
| Resume ingestion | PDF/DOCX/TXT/Markdown validation, parsing, private storage, versioning |
| Primary Resume | transactional default selection and user-experience design |
| Project Knowledge RAG | chunking, PostgreSQL FTS, top-k retrieval, evidence IDs and grounding |
| Resilient DeepSeek analysis | structured-output design, tolerant parsing, repair, deterministic fallback |
| Safe prompt and grounding | prompt-injection mitigation, secret protection, claim validation |
| Monitoring and offline Evaluation | privacy-aware observability and regression testing |
| Docker Compose and Nginx | containerized HTTPS deployment and private networking |
| GitHub Actions and GHCR | CI/CD validation and immutable image publication |
| PostgreSQL 16 Backup Restore | compatibility gates, manifests, checksums, recovery rehearsal |

## Evidence-backed Resume Bullets

- Built a FastAPI/React job-analysis application with PostgreSQL-backed Profile,
  Resume Version, History, monitoring, and Project Knowledge.
- Implemented PDF, DOCX, TXT, and Markdown ingestion with private File Assets,
  immutable Versions, and automatic Primary Resume selection.
- Designed resilient DeepSeek output handling with tolerant Pydantic parsing,
  one format repair, and deterministic fallback.
- Integrated PostgreSQL FTS Project Knowledge RAG with top-k evidence IDs,
  Backend sources, synonym recall, skill reconciliation, and claim filtering.
- Implemented Argon2, hashed server Sessions, Remember Me, CSRF/Origin,
  revocation, throttling, and ownership isolation.
- Designed a PostgreSQL Transactional Outbox with Redis/Dramatiq, leases,
  heartbeat, retry, recovery, and dead letters.
- Migrated verified SQLite data to PostgreSQL with source fingerprint, rows,
  checksums, ownership, foreign keys, and sequence validation.
- Implemented PostgreSQL 16 Backup Restore gates with custom archive, immutable
  tools, manifest checksums, empty target, inventory, and owner mapping.
- Deployed immutable GHCR images behind HTTPS Nginx with private data services,
  candidate staging, health assertions, and Version 2.0.2 rollback assets.
- Built GitHub Actions checks for Python, PostgreSQL, React, Docker Compose,
  repository safety, Mock LLM, and isolated recovery rehearsal.

These bullets describe implementation evidence only. They do not claim team
leadership, commercial scale, revenue, user counts, hiring outcomes, automatic
application submission, or employer adoption.

## Interview-ready Explanations

### Why not call DeepSeek directly from the browser?

The Backend protects the key, scans input, bounds prompts, classifies failure,
validates output/evidence, owns scoring/sources, and enforces isolation. A
browser call would expose secrets and bypass controls.

### Why use Project Knowledge RAG?

A reviewed single corpus supplies auditable transferable project evidence
without a generic document store. Top-k limits prompt size and exposes sources.

### How is unstable model formatting handled?

It tries JSON, safe extraction, aliases/defaults, then one format repair. On
provider/repair failure, deterministic matching returns the stable contract;
non-critical defects do not discard valid fields.

### Why PostgreSQL and Redis?

PostgreSQL owns durable user, Resume, History, knowledge, metrics, and Agent/
Outbox state. Redis is transient delivery, so broker loss does not erase state.

### Why a Transactional Outbox?

Business state and Outbox row commit together. The dispatcher publishes/retries
later, closing the database-commit versus Redis-send gap.

### How can an upgrade be rolled back?

Record Version 2.0.2 digests/config, rehearse PostgreSQL 16 recovery, validate
migration, and test an internal 2.0.3 candidate. Rollback restores old
images/config and preserves volumes because the schema is additive.

### How does Primary Resume improve the workflow?

Only a successfully parsed upload becomes Primary. Analyze preselects its active
Version but permits one-request override; archiving Primary selects a remaining
Resume without a stale reference.

## Known Limitations

- The product is private and administrator-led, with no public signup. It is not
  presented as a public multi-tenant SaaS platform.
- DeepSeek can be unavailable or wrong. Every AI result needs human review.
- Local fallback is deterministic and resilient but less nuanced than a full
  model response.
- PostgreSQL full-text RAG is lexical, not embedding/vector retrieval, and can
  miss semantic equivalents outside bounded synonyms.
- Scanned PDFs without selectable text require external OCR; OCR is not in
  Version 2.0.3.
- Safe job URL extraction cannot parse every site or client-rendered page.
- The system does not automatically apply, send email, contact employers, or
  guarantee ATS parsing, ranking, interviews, or hiring.
- Jobs, Job Rankings, Applications, Approvals, and Tasks remain disabled.
- Historical Agent Runs may refer to retired workflows and cannot be retried or
  resumed through the current public workflow.
- Production is single-host Docker Compose, not Kubernetes or high availability.
- The application provides privacy-aware local metrics, not distributed tracing
  or a full observability platform.

## Roadmap

Reasonable future directions include improved retrieval precision, more precise
claim-to-evidence links, optional OCR after a separate security review,
accessibility refinement, operator observability, and safer deployment-switch
mechanics.

Future ideas are not current capabilities until separately implemented, tested,
reviewed, and released. The Roadmap does not restore Jobs, Applications,
Approvals, or Tasks as current features and does not promise automatic job
submission, a browser extension, an interview platform, Kubernetes, or
guaranteed job-search outcomes.
