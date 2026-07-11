# Monitoring Data Management and Test Isolation

## Version 1.8.1 Overview

Version 1.8.1 adds local data lifecycle controls for monitoring metadata and offline evaluation history. Cleanup is explicit, permanent, scoped, and protected by an administrator token.

## Why Cleanup Is Needed

Monitoring data is useful during development and operation, but local SQLite metrics can accumulate over time. The cleanup tools let an administrator remove monitoring or evaluation history without changing job-application history or Project Knowledge.

## Monitoring Data vs Application History

Monitoring cleanup affects only `analysis_metrics` and `analysis_step_metrics`. Application history in `application_records`, including workflow audit records, remains intact. Project Knowledge and its RAG index remain intact.

## Data That Can Be Deleted

- `analysis_metrics`
- `analysis_step_metrics`
- `evaluation_runs`
- `evaluation_results`

## Data That Is Never Deleted

- `application_records` and application workflow history
- `docs/PROJECT_KNOWLEDGE.md`
- `knowledge_documents`, `knowledge_chunks`, and `knowledge_chunks_fts`
- Resume source files, which are not stored by the application
- `backend/evals/cases.json` and `backend/evals/README.md`

## Clear All Monitoring Data

Use the Monitoring Data Management panel to preview totals, type `DELETE ALL MONITORING DATA`, and complete the browser confirmation. The operation first deletes child step metrics, then parent analysis metrics in one SQLite transaction. It does not run `VACUUM`.

## Filtered Monitoring Cleanup

Filtered cleanup supports UTC date ranges, outcomes, security statuses, and risk levels. It requires at least one filter, a preview, and the exact confirmation `DELETE FILTERED MONITORING DATA`.

## Delete One Workflow Trace

Trace Detail provides a separate metadata deletion control. It requires the exact phrase `DELETE TRACE` and deletes only the monitoring rows for that workflow ID. Any application history workflow audit trail is preserved.

## Clear Evaluation History

Evaluation cleanup previews evaluation run/result counts before deletion. Clear-all requires `DELETE EVALUATION HISTORY`; filtered cleanup requires `DELETE FILTERED EVALUATION HISTORY`. Results are deleted before their parent runs in one transaction. The offline cases remain available for later evaluation runs.

## Admin Token Protection

Destructive APIs are disabled unless `MONITORING_ADMIN_TOKEN` is configured. Clients must send the token in the `X-Monitoring-Admin-Token` request header. The backend uses constant-time comparison and never returns, logs, persists, or exposes the token. This is a local administrative safeguard, not a complete multi-user authentication or RBAC system.

## Local-Only Default and Remote Warning

`MONITORING_ALLOW_REMOTE_ADMIN=false` is the default. In this mode destructive requests are accepted only from `127.0.0.1` or `::1`, and still require the admin token. If remote administration is deliberately enabled, use HTTPS or a protected reverse proxy. Never put the admin token in frontend source code.

## Transactional Deletion

All cleanup validation occurs before `BEGIN IMMEDIATE`. A failed delete rolls back the transaction. SQL table and column identifiers are fixed in code; date and enum values are passed with parameterized placeholders.

## Test Database Isolation

`APP_DATABASE_PATH` optionally selects the local SQLite database. If it is unset, the normal application path remains `backend/data/app.db`, resolved from the backend code location rather than the process working directory.

`APP_ENV` supports `development`, `production`, and `test`. Automated tests set `APP_ENV=test` and point `APP_DATABASE_PATH` at a new `TemporaryDirectory` database. In test mode, the application fails fast if the configured path resolves to the default `app.db`, including a symbolic link to it. This prevents test metrics, evaluation history, security records, and workflow data from contaminating real monitoring data.

## Privacy and Limitations

The UI keeps the admin token in component memory only; it does not use local storage, session storage, cookies, URL parameters, or logs. Cleanup is permanent and cannot be undone. Version 1.8.1 does not provide backups, restoration, data-deletion certification, distributed database operations, or a production migration service.
