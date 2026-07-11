# CI/CD and Container Image Publishing

## Continuous Integration

`.github/workflows/ci.yml` runs for pull requests, pushes to `main`, and manual dispatch. It uses read-only repository permissions and concurrency cancellation. Jobs cover:

- Python compilation and all backend unittest suites with a temporary test database
- React dependency installation and production build
- Backend and frontend Docker builds plus non-root/sensitive-path checks
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
