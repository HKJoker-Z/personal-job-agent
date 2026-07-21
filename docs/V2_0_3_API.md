# Version 2.0.3 API

All endpoints retain the current Session, ownership, Origin, and CSRF requirements. Cross-user Resume IDs are never returned.

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

## Resumes

- `GET /api/resumes` lists active owned Resumes, primary first.
- `GET /api/resumes/primary` returns the owned primary Resume with its active version, or `null` when none exists.
- `POST /api/resumes/upload` accepts `multipart/form-data` field `file` for PDF, DOCX, TXT, MD, or Markdown. It returns `resume`, `version`, and `file`, and makes the Resume primary after successful extraction.
- `POST /api/resumes/import` remains compatible and uses the same primary-selection behavior.
- `DELETE /api/resumes/{id}` archives an owned Resume. If it was primary, the newest remaining active Resume becomes primary.

The upload response preserves existing file keys and also exposes `original_filename`, `mime_type`, `file_size`, `content_hash`, and extracted text through the Resume Version content. A selectable-text-free PDF returns the safe message `No selectable text was found in this PDF.`
