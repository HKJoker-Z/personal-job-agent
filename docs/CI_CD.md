# CI/CD and Container Image Publishing

Version 2.0.2 CI includes full Python test discovery, a real PostgreSQL 16 service test, frontend Vitest coverage, the retained compatibility/product smoke, and a separate strict PostgreSQL 16 Backup/Restore rehearsal. Release publishing remains tag-driven and never deploys production automatically.

## Continuous Integration

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, and manual dispatch. It uses read-only repository permissions and concurrency cancellation. Jobs cover:

- Python compilation and all backend unittest suites with temporary SQLite databases
- Alembic and real PostgreSQL integration coverage
- React dependency installation, Vitest, and production build
- Backend and frontend Docker builds plus non-root/sensitive-path checks
- An isolated Version 1.9 compatibility run that verifies readiness and SQLite/Project Knowledge persistence across restart and rebuild
- An isolated `pja-v2-phase1-*` run that verifies identity, CSRF, PostgreSQL, Profile, Resume/DOCX, persistence, backup, verification, and restore
- A unique `pja-pg16-restore-*` Compose project with separate private source/target networks and temporary Volumes, no published 5432, matching PostgreSQL 16 clients, exact inventory/file/readiness checks, and PostgreSQL 17 pre-write rejection tests
- Docker Compose configuration validation with test-only configuration
- Shell syntax validation
- Repository checks for tracked databases, runtime data, build output, environment files, and obvious credentials

CI does not use a real DeepSeek key, call the external LLM, deploy a server, or cache secrets. The PostgreSQL 17 image is test-only negative coverage and is never published or referenced by operational Compose. CI does not use `pull_request_target`.

## GHCR Release Images

`.github/workflows/release-images.yml` runs only when a semantic `v*.*.*` Git tag is pushed. It validates tests/builds, logs into GHCR using `GITHUB_TOKEN`, and publishes:

- `ghcr.io/hkjoker-z/personal-job-agent-backend`
- `ghcr.io/hkjoker-z/personal-job-agent-frontend`

Images receive the full semantic version, original Git tag, and commit-SHA tags. Stable tags update `latest`; prerelease tags do not. The workflow needs `contents: read` and `packages: write`. It does not pass deployment secrets as build arguments or perform automatic SSH/server deployment.

Server promotion remains an explicit operator action because firewall, DNS, HTTPS, runtime backups, maintenance windows, and rollback decisions are deployment-specific. Version 1.9 provides repeatable artifacts and checks, not automatic cloud deployment, high availability, or zero-downtime guarantees.
