# Version 2.0.3 Test Plan

The Alpha 3 matrix preserves every Alpha 2 test and adds:

- deterministic score, weights, synonym/related matching, duplicate evidence, unknown/missing, hard filters, revision snapshots, reuse/force-new, CSRF, and IDOR;
- reproducible ranking, stable ties, factor contributions, failed hard-filter ordering, filters, and ownership;
- Package consistency, finalized Resume policy, optimistic revisions, archive, approval prerequisites, and approved uniqueness;
- deterministic and Mock generation, Prompt Injection isolation, PII minimization, malformed JSON, timeout/error handling boundary, Secret/internal-marker output rejection, and metadata-only monitoring;
- Tailored Resume, Cover Letter, and Answer grounding; unsupported metric/leadership/skill/certification/authorization/salary cases; evidence coverage; explicit claim confirmation; immutable edits/reviews/finalization;
- React Match, Ranking, Package, Material Editor, Evidence, history/diff, conflict/error, responsive, and keyboard-visible workflows;
- fresh Alembic upgrade, Alpha 2→Alpha 3, downgrade/re-upgrade, constraints, indexes, PostgreSQL opt-in, and SQLite fallback;
- Docker builds, Compose validation, and `pja-v2-0-3-*` Smoke on `127.0.0.1:18083` with restart, backup, verify, restore, counts, checksums, auth/CSRF, and cleanup.

`backend/evals/v203_cases.json` is a fictitious offline regression set. No test calls DeepSeek or a real recruitment site. CI never connects to production, publishes Alpha 3 images, deploys, or merges.
