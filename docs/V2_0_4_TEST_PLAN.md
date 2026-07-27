# Version 2.0.4 Verification Plan

- Run targeted Analyze idempotency tests, the complete Backend suite, and the
  opt-in PostgreSQL 16 integration suite.
- Validate fresh Alembic upgrade, `20260721_05` to `20260724_06`, supported
  downgrade, re-upgrade, `heads`, `current`, and `check`.
- Run all Frontend tests and the production Vite build.
- Build and inspect both Docker images, validate Compose, run the isolated Mock
  LLM Docker smoke, and run the strict PostgreSQL 16 backup/restore regression.
- Run repository generated/sensitive-path safety, credential-pattern scanning,
  ShellCheck, and `git diff --check`.
- Publish only immutable Version 2.0.4 image digests after final main passes.
- Restore the exact production backup once in isolation and validate the
  migration and inventory.
- Validate one private candidate on `127.0.0.1:18091`, then synchronize Project
  Knowledge and perform the public cutover and 100 exact-version health checks.
- Use only synthetic functional data and remove it precisely.

No release, candidate, migration rehearsal, Project Knowledge check, or public
acceptance test may call real DeepSeek. Deterministic mocks and Mock LLM cover
provider behavior.
