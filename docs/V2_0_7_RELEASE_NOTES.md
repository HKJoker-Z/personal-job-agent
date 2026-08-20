# Version 2.0.7 — History Analysis View Fix

Version 2.0.7 is a focused patch release for the saved-analysis History view.
It preserves the Version 2.0.6 production architecture, Analyze behavior, and
Alembic head `20260730_07`.

## Fix

- Clicking `View` now opens the selected saved analysis in a dedicated detail
  state instead of appending an easy-to-miss second result UI below the History
  table.
- History detail reuses the same `AnalysisResult` renderer used immediately
  after Analyze completes.
- The detail path reads only `GET /api/history/{id}` and never reruns Analyze or
  calls DeepSeek.
- Existing safe defaults keep older History rows usable when optional RAG,
  scoring, ATS, workflow, recommendation, or cover-letter fields are absent.
- History metadata, exports, and human next-action decisions remain available.

## Compatibility and operations

- No database schema or Alembic migration changes are included.
- History persistence, Analyze idempotency, DeepSeek, RAG, security scanning,
  Java normalization, Worker, Outbox, Redis, and production topology are
  unchanged.
- Backend, Worker, and Outbox use the same reviewed Backend image. Frontend and
  Edge use the same reviewed Frontend image. The existing Java image is reused.
- Release validation uses synthetic data and Mock Provider behavior and does
  not call DeepSeek or inspect production user content.

## Validation

The regression suite verifies that View requests only the History list/detail
endpoints, switches between list and saved-result detail states, uses the shared
Analyze result sections, and tolerates missing optional legacy fields. Full
frontend, backend, PostgreSQL, Docker, production-runtime, backup/restore, and
repository-safety checks remain release gates.

## Rollback

Restore the recorded immutable Version 2.0.6 Backend/Worker/Outbox and
Frontend/Edge image digests and the previous release configuration. Keep
PostgreSQL, Redis, Java, all volumes, files, and Alembic `20260730_07`; no
database downgrade is required.
