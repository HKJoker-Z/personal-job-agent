# Version 2.0.3 - Resilient Analysis and Primary Resume Upload

Version 2.0.3 is a focused upgrade from the production Version 2.0.2 release.

## Changes

- More tolerant DeepSeek response parsing for Markdown fences, surrounding prose, minor JSON errors, optional fields, aliases, and safe type coercion.
- One automatic, short response-format repair call at most; the complete analysis is never re-run for repair.
- Deterministic local fallback analysis for unusable model responses, provider timeouts, and provider 5xx responses.
- Stable `complete`, `repaired`, `partial`, and `fallback` API results; supported content is retained when individual claims or evidence references are invalid.
- Configurable 100,000-character Resume and 60,000-character JD defaults with normalization and structure-aware reduction.
- Resume-page PDF, DOCX, TXT, and Markdown upload up to a configurable 10 MB.
- Latest successful upload becomes the sole Primary Resume in one transaction.
- Analyze automatically loads the Primary Resume and still allows a one-request saved Resume or pasted-text override.

## Upgrade

Back up PostgreSQL, runtime configuration, Version 2.0.2 image digests, private Resume files, and runtime Project Knowledge. Verify the backup in one isolated PostgreSQL 16 restore. Run Alembic upgrade to `20260721_05`, then stage immutable Version 2.0.3 images on `127.0.0.1:18090` before switching public 8080.

The migration adds only `resumes.is_primary`, backfills the newest active Resume per user, and creates the active-primary uniqueness index. Existing Resumes and versions are retained.

## Rollback

Restore the recorded Version 2.0.2 immutable Backend/Frontend digests and saved Compose/configuration. The Version 2.0.3 database column is backward-compatible with Version 2.0.2, so routine image rollback does not require a destructive downgrade. Preserve all volumes, backups, runtime files, and Project Knowledge. Use a database restore only for a separately diagnosed data incident.
