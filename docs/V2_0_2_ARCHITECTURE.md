# Version 2.0.2 Architecture

Version 2.0.2 is the `2.0.0-alpha.2` development milestone stacked on Version 2.0.1 PR #6. It is not deployed and is not independently mergeable to `main`.

## Components

- FastAPI routers validate HTTP contracts and map safe 400/404/409 errors.
- Domain services own transactions, revisions, stage transitions, evidence validation, merges, ownership checks, and safe audit metadata.
- Repositories contain SQLAlchemy 2.x persistence and always scope business resources by `owner_user_id`.
- PostgreSQL 16 is authoritative for Version 2; SQLite remains a unit-test fallback and Version 1 compatibility source.
- Alembic revision `20260713_02` follows `20260712_01`; no Version 2.0.1 migration was edited.
- Private file storage reuses the Version 2.0.1 provider with confined `jobs/` and `resumes/` namespaces.
- React reuses the authenticated router, Auth Provider, protected layout, in-memory CSRF client, and safe error handling.

## Request flow

```text
React -> authenticated/CSRF-aware API -> router schema -> owner-scoped service
      -> repository/SQLAlchemy -> PostgreSQL
      -> safe audit event without Job Description or Note bodies
```

Job URL acquisition uses a pinned resolved address, validates every redirect, rejects non-global targets, bounds time and compressed/expanded bodies, and never sends browser credentials. PDF/DOCX parsing and storage reuse the existing bounded parser and atomic private storage.

Job Description text is always untrusted. Deterministic extraction runs locally. LLM extraction is an explicit synchronous action, sends only the sanitized current description, allows no tools or network, validates a strict schema and exact evidence spans, and defaults every accepted item to `needs_review`.

Application stage changes use a row lock, revision check, transition matrix, and append-only history in one transaction. Job merges lock both Jobs in canonical order and preserve Sources, Requirements, Tasks, Application relations, Notes, and Stage History; two active Applications cause a conflict.

## Version 1.9 compatibility

Analyze, History, Project Knowledge, Monitoring, Evaluation, exports, and legacy integer Application records remain available. The overlapping `/api/applications` path uses compatibility dispatch: legacy list queries (`limit`, `offset`, `status`, or `search`) and integer IDs use Version 1 behavior; the Pipeline board and UUID IDs use Version 2 services.

No production Compose, database, routing bridge, policy rule, systemd unit, or live runtime is part of this architecture change.
