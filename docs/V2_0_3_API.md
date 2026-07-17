# Version 2.0.3 API

All mutation routes require authentication, trusted Origin, and CSRF. All reads and writes are ownership-scoped; missing and cross-user IDs return safe not-found responses.

## Matching and ranking

- `POST /api/jobs/{job_id}/match`
- `GET /api/jobs/{job_id}/matches`
- `GET /api/jobs/{job_id}/matches/{analysis_id}`
- `GET /api/jobs/{job_id}/latest-match`
- `POST /api/jobs/rank`
- `GET /api/job-rank-runs`
- `GET /api/job-rank-runs/{run_id}`

Match accepts optional Profile revision, Resume Version, exact 100-point weight config, and `force_new`. Rank accepts owned Job IDs or allowlisted filters and bounded factor weights.

## Packages and Materials

- `POST/GET /api/applications/{application_id}/packages`
- `GET/PATCH /api/application-packages/{package_id}`
- `POST /api/application-packages/{package_id}/archive`
- `POST /api/application-packages/{package_id}/approve`
- `POST /api/application-packages/{package_id}/generate-resume`
- `POST /api/application-packages/{package_id}/generate-cover-letter`
- `POST /api/application-packages/{package_id}/answers`
- `GET /api/application-materials/{material_id}`
- `GET/POST /api/application-materials/{material_id}/versions`
- `POST /api/material-versions/{version_id}/validate`
- `GET /api/material-versions/{version_id}/evidence`
- `POST /api/material-versions/{version_id}/evidence/{evidence_id}/confirm`
- `POST /api/material-versions/{version_id}/review`
- `POST /api/material-versions/{version_id}/finalize`

Expected revision/active-version conflicts return 409. Invalid confirmation strings and schemas return 422/400 without content disclosure. Generation remains synchronous and explicit; failure never overwrites an existing Version.
