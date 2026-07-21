# Version 2.0.3 Test Plan

The full pre-existing backend and frontend regression suites remain required. Version 2.0.3 adds focused coverage for:

- standard, fenced, and prose-wrapped JSON;
- trailing commas, BOM, aliases, missing/null/extra fields, scalar-to-list conversion, numeric-string conversion, score normalization, trimming, and de-duplication;
- exactly one short repair call, repair success, repair failure, provider timeout/5xx, and stable local fallback results;
- unknown evidence and unsupported claims producing warnings without blocking usable output;
- partial and fallback History persistence and empty-input rejection;
- PDF, DOCX, TXT, and Markdown uploads; invalid type, size, no-text PDF, filename/text handling, duplicate upload, and ownership isolation;
- atomic latest-upload primary selection, failed-upload preservation, primary API, and primary reassignment after deletion;
- Resume upload loading/success/error UI, Primary Resume badges, Analyze primary auto-selection/override/no-primary guidance, all analysis status messages, and button recovery.

Release gates are:

1. full backend discovery and Python compilation;
2. fresh/upgrade/downgrade Alembic checks and PostgreSQL integration;
3. full frontend Vitest suite and production build;
4. Backend and Frontend Docker builds, image checks, and Compose validation;
5. isolated Mock provider smoke including Resume upload/primary, analysis, RAG, History, restart, and backup/restore compatibility;
6. at most two explicitly enabled real DeepSeek checks using entirely fictional Resume/JD data, one with RAG off and one with RAG on.

CI never receives a production Resume/JD and does not call DeepSeek. Production candidate validation may use Mock behavior for repaired and fallback paths.
