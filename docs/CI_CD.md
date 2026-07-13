# CI/CD and Container Image Publishing

Version 2 Phase 1 extends pull-request CI with full Python test discovery, a real PostgreSQL 16 service test, frontend Vitest coverage, the retained Version 1.9 compatibility Smoke, and a separate isolated Version 2 identity/Profile/Resume/backup/restore Smoke. Release publishing remains tag-driven and is not performed for the Phase 1 development branch.

## Continuous Integration

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, and manual dispatch. It uses read-only repository permissions and concurrency cancellation. Jobs cover:

- Python compilation and all backend unittest suites with temporary SQLite databases
- Alembic and real PostgreSQL integration coverage
- React dependency installation, Vitest, and production build
- Backend and frontend Docker builds plus non-root/sensitive-path checks
- An isolated Version 1.9 compatibility run that verifies readiness and SQLite/Project Knowledge persistence across restart and rebuild
- An isolated `pja-v2-phase1-*` run that verifies identity, CSRF, PostgreSQL, Profile, Resume/DOCX, persistence, backup, verification, and restore
- Docker Compose configuration validation with test-only configuration
- Shell syntax validation
- Repository checks for tracked databases, runtime data, build output, environment files, and obvious credentials

CI does not use a real DeepSeek key, call the external LLM, deploy a server, or cache secrets. It does not use `pull_request_target`.

## GHCR Release Images

`.github/workflows/release-images.yml` runs only when a semantic `v*.*.*` Git tag is pushed. It validates tests/builds, logs into GHCR using `GITHUB_TOKEN`, and publishes:

- `ghcr.io/hkjoker-z/personal-job-agent-backend`
- `ghcr.io/hkjoker-z/personal-job-agent-frontend`

Images receive the full semantic version, original Git tag, and commit-SHA tags. Stable tags update `latest`; prerelease tags do not. The workflow needs `contents: read` and `packages: write`. It does not pass deployment secrets as build arguments or perform automatic SSH/server deployment.

Server promotion remains an explicit operator action because firewall, DNS, HTTPS, runtime backups, maintenance windows, and rollback decisions are deployment-specific. Version 1.9 provides repeatable artifacts and checks, not automatic cloud deployment, high availability, or zero-downtime guarantees.
