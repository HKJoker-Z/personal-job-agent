# Version 2.0.3 production readiness

Version 2.0.3 may be promoted from production Version 2.0.2 only after required PR/main checks, immutable image publication, the standard PostgreSQL 16 backup, one isolated restore rehearsal, isolated migration validation, and the `127.0.0.1:18090` candidate all pass.

## Data gates

- Back up PostgreSQL, Compose/configuration, private Resume files, runtime Project Knowledge, and exact Version 2.0.2 Backend/Frontend digests.
- Preserve the existing PostgreSQL 16 client/server/digest and manifest verification gates; never edit a dump to bypass compatibility.
- Validate migration `20260721_05` first in isolation. It may add only `resumes.is_primary`, backfill newest active Resumes, and create `uq_resumes_user_primary_active`.
- Confirm every existing Resume and Resume Version remains present and only one active primary exists per user.
- Preserve all Volumes and rollback assets.

## Application gates

- Full Backend/PostgreSQL and Frontend suites, production bundle, Docker builds, image inspection, Compose validation, and isolated Mock smoke pass.
- Analysis returns stable `complete`, `repaired`, `partial`, or `fallback` structures. A repair invokes DeepSeek at most once and fallback works on provider timeout/5xx or unusable output.
- PDF, DOCX, TXT, and Markdown upload works at the configured 10 MB limit. No-text PDF fails safely. Failed upload does not change primary selection.
- Latest successful upload becomes primary, deletion chooses the newest remaining Resume, ownership isolation holds, and Analyze defaults to primary while allowing a request-only override.

## Infrastructure gates

Only Edge 8080 is public. Backend 8000, PostgreSQL 5432, and Redis 6379 remain unpublished. Production retains private authenticated Redis, Secure/HttpOnly/SameSite=Lax Sessions, trusted Origins/Hosts, CSRF, disabled API docs, configured cost rates, and `MOCK_PROVIDER_ENABLED=false`.

Stop promotion on any failed workflow, migration/data-count mismatch, backup/restore failure, floating application image, secret exposure, candidate/public version instability, unhealthy dependency, upload/primary/Analyze/History/RAG regression, inability to restore Version 2.0.2, or any requirement to alter TLS, Mihomo, `pja-br0`, preference 8999, or delete a Volume.
