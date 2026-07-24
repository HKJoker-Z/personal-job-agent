# Version 2.0.3 API

All endpoints retain the current Session, ownership, Origin, and CSRF requirements. Cross-user Resume IDs are never returned.

## Request correlation

Clients may send `X-Request-ID` using this exact syntax:

```text
^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$
```

A valid value is preserved exactly. An absent or invalid value is replaced
with a server-generated UUIDv4. Every HTTP response includes `X-Request-ID`,
including body-size, authentication, Origin, CSRF, validation, database, and
unexpected-error responses. Browser clients may read this response header
through the existing CORS policy.

The request ID is observational support metadata. It is not an authentication,
authorization, ownership, or idempotency credential, and it does not represent
distributed tracing.

## Analyze

`POST /api/analyze` accepts the existing multipart Resume/JD sources. Resume and JD input limits are configured by `ANALYSIS_RESUME_MAX_CHARS` and `ANALYSIS_JOB_DESCRIPTION_MAX_CHARS` (defaults 100,000 and 60,000). Oversized text is normalized and safely reduced before model use rather than causing a server error.

All successful model, repaired, partial, and local fallback paths return the same core fields:

```json
{
  "analysis_status": "complete | repaired | partial | fallback",
  "analysis_warnings": [],
  "match_score": 0,
  "matched_skills": [],
  "missing_skills": [],
  "unknown_skills": [],
  "scoring_breakdown": {},
  "recommendations": [],
  "used_knowledge_base": false,
  "retrieval_count": 0,
  "rag_sources": [],
  "evidence_mapping": []
}
```

Optional legacy result fields such as cover letter, upgraded bullets, ATS analysis, and dimension assessments receive safe defaults. Provider timeout/5xx and unrepairable output return HTTP 200 with `analysis_status="fallback"`. Empty Resume or JD is still rejected. A database failure while saving History remains a true failure.

Analyze failures use one four-field envelope:

```json
{
  "error": {
    "code": "REQUEST_VALIDATION_FAILED",
    "message": "The request could not be processed.",
    "request_id": "uuid-or-valid-client-id",
    "details": {}
  }
}
```

All four fields are always present and `details` is always an object. The
focused Analyze codes are:

- `AUTHENTICATION_REQUIRED`
- `REQUEST_ORIGIN_NOT_TRUSTED`
- `CSRF_VALIDATION_FAILED`
- `REQUEST_TOO_LARGE`
- `REQUEST_VALIDATION_FAILED`
- `RESUME_SOURCE_INVALID`
- `RESUME_NOT_FOUND`
- `RESUME_PARSING_FAILED`
- `JOB_SOURCE_INVALID`
- `JOB_DESCRIPTION_ACQUISITION_FAILED`
- `INPUT_SECURITY_BLOCKED`
- `PROJECT_KNOWLEDGE_RETRIEVAL_FAILED`
- `OUTPUT_SECURITY_BLOCKED`
- `ANALYZE_PERSISTENCE_FAILED`
- `IDEMPOTENCY_KEY_INVALID`
- `IDEMPOTENCY_KEY_REUSED`
- `IDEMPOTENCY_REQUEST_IN_PROGRESS`
- `IDEMPOTENCY_OUTCOME_UNKNOWN`
- `IDEMPOTENCY_PERSISTENCE_FAILED`
- `UNEXPECTED_SERVER_ERROR`

`details` contains only bounded, allowlisted workflow or security metadata.
It never contains Resume/JD text, prompts, provider output, cookies, CSRF
values, credentials, SQL, stack traces, filesystem paths, or raw exception
text. The frontend maps the stable code to a safe user message and displays
`request_id` as a support reference for terminal failures.

This envelope is intentionally limited to `POST /api/analyze` and security or
validation failures for that route. Other endpoints retain their existing
`detail` behavior for compatibility.

### Analyze idempotency

`Idempotency-Key` is optional. Omitting it preserves existing synchronous
behavior. A key contains 8–128 ASCII letters, digits, `.`, `_`, `:`, or `-`,
starting with a letter or digit. It is scoped to the authenticated user and
Analyze operation, is not an authentication credential, and is stored only as
a domain-separated SHA-256 hash.

The authoritative server fingerprint covers effective normalized Resume/JD
hashes, Resume Version ID, normalized Job URL, RAG/top-k, current Project
Knowledge version hash, History choice, model, analysis contract, and security
policy. Canonical JSON uses stable keys, explicit nulls, UTF-8, and a version.

- completed duplicate: stored status/body and `Idempotency-Replayed: true`;
- changed effective inputs: `409 IDEMPOTENCY_KEY_REUSED`;
- active lease: `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` and bounded `Retry-After`;
- stale pre-provider lease: atomic takeover with a new attempt token;
- stale provider-started lease: `409 IDEMPOTENCY_OUTCOME_UNKNOWN`, without an
  automatic provider retry.

Only `Idempotency-Replayed` and `X-Request-ID` are exposed through CORS.
PostgreSQL is the source of truth. The SDK uses `max_retries=0`; one primary
application call and at most one explicit format-repair call remain possible.
This prevents duplicate completed work but does not claim external exactly-once
execution.

## Resumes

- `GET /api/resumes` lists active owned Resumes, primary first.
- `GET /api/resumes/primary` returns the owned primary Resume with its active version, or `null` when none exists.
- `POST /api/resumes/upload` accepts `multipart/form-data` field `file` for PDF, DOCX, TXT, MD, or Markdown. It returns `resume`, `version`, and `file`, and makes the Resume primary after successful extraction.
- `POST /api/resumes/import` remains compatible and uses the same primary-selection behavior.
- `DELETE /api/resumes/{id}` archives an owned Resume. If it was primary, the newest remaining active Resume becomes primary.

The upload response preserves existing file keys and also exposes `original_filename`, `mime_type`, `file_size`, `content_hash`, and extracted text through the Resume Version content. A selectable-text-free PDF returns the safe message `No selectable text was found in this PDF.`
