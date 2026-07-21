# Version 2.0.3 Architecture

Version 2.0.3 is a focused production release over Version 2.0.2. It changes only the analysis boundary and Resume ingestion/default-selection behavior. Navigation, authentication, retired features, PostgreSQL/Redis/Worker/Outbox topology, TLS, and host networking are unchanged.

## Resilient analysis flow

```text
normalized Resume + normalized Job Description + optional retrieved evidence
  -> one DeepSeek analysis call
  -> standard JSON parse
  -> fenced/prose JSON extraction and trailing-comma recovery
  -> tolerant field reconciliation
  -> at most one short format-repair call
  -> deterministic evidence reconciliation and score generation
  -> stable result / deterministic local fallback
  -> optional History save
```

DeepSeek owns concise skill judgments, assessments, short evidence references, and recommendations. The backend owns final scoring, scoring breakdown, RAG source metadata, evidence reconciliation, History identity, and runtime metadata. Unknown model fields are ignored; optional values receive safe defaults; aliases and narrowly safe scalar/list/number coercions are supported. No parser evaluates model content.

Provider errors and unusable model output return a deterministic local keyword analysis with `analysis_status="fallback"`. A repaired model response is marked `repaired`; usable output missing optional content is `partial`; fully usable output is `complete`. Unsupported claims and unknown evidence references create warnings and are removed or downgraded instead of rejecting the entire analysis.

Resume and job-description text is normalized before prompt construction. NUL bytes and HTML markup are removed, readable newlines and bullets are preserved, excess whitespace is compressed, and structure-aware truncation prioritizes relevant Resume and JD sections. Defaults are 100,000 Resume characters and 60,000 JD characters.

## Resume upload and primary selection

Authenticated PDF, DOCX, TXT, and Markdown uploads are accepted up to the configured 10 MB limit. Files are parsed before database mutation. A successful upload creates the existing Resume, Resume Version, and File Asset records and atomically makes the new Resume the user's only primary Resume. A failed parse leaves the previous primary unchanged.

The existing ownership-scoped repositories and transaction boundaries are reused. `resumes.is_primary` is protected by a PostgreSQL/SQLite partial unique index for one active primary per user. Archiving a primary selects the newest remaining active Resume. Analyze loads the primary Resume by default while allowing a one-request override without changing the stored primary.
