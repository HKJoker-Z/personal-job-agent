# Version 1.9 Deployment Guide

## Overview and Architecture

Version 1.9 provides a repeatable, single-instance Docker Compose topology:

`Browser → Frontend/Nginx → /api → Backend/FastAPI → SQLite + Project Knowledge`

Only the frontend publishes a host port. The backend is reachable only on the dedicated Compose network and requires outbound access for DeepSeek when Analyze is used.

## Prerequisites and Ubuntu Requirements

- A maintained Ubuntu server with Docker Engine and Docker Compose v2 already installed
- Git for source-build deployments, or GHCR access for image deployments
- Adequate disk space and restricted filesystem permissions for runtime data and backups
- A user permitted to run Docker commands

Version 1.9 does not install Docker or automatically modify firewall, DNS, system Nginx, systemd, or HTTPS configuration.

## Environment Configuration

Copy `.env.production.example` to an ignored `.env.production` and set values on the deployment host. Production requires a non-empty `DEEPSEEK_API_KEY` and explicit `TRUSTED_HOSTS`. `ALLOWED_ORIGINS` may be empty for same-origin operation but cannot contain `*`. API docs default to disabled.

Never commit the production env file or place the Monitoring admin token in frontend source code. Keep `MONITORING_ALLOW_REMOTE_ADMIN=false` unless destructive APIs are deliberately exposed behind HTTPS and additional access controls.

## Runtime Directories and First Bootstrap

For a fresh deployment, run bootstrap. If migrating an existing `backend/data/app.db`, perform the migration workflow below **before** bootstrap so the migration target remains absent as required.

Run:

```bash
sudo scripts/bootstrap-runtime.sh
```

This creates `runtime/data`, `runtime/project-knowledge`, and `runtime/backups` without overwriting existing data and assigns them to the fixed container UID/GID 10001 without using mode 777. The initial Project Knowledge file is copied from the repository seed only when the runtime copy does not exist.

## Existing Data Migration

For an existing non-container installation, preview migration before running bootstrap:

```bash
scripts/migrate-existing-data.sh
```

Stop writes from the old backend before migrating, then explicitly confirm:

```bash
scripts/migrate-existing-data.sh --confirmation "MIGRATE EXISTING DATA"
```

The migration uses the SQLite backup API, creates a backup first, refuses to overwrite runtime targets, and preserves the source files.

## Source-Build Deployment

Validate and build without starting current services:

```bash
APP_ENV_FILE=.env.production docker compose config --quiet
docker compose build
```

Start through the guarded deployment script:

```bash
scripts/deploy.sh --build --env-file .env.production
```

## Image-Based Deployment

Use the production override with a published image tag:

```bash
IMAGE_TAG=v1.9.0 docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml up -d --no-build
```

Version 1.9 development does not publish a tag automatically.

## Health, Readiness, and Logs

Run `scripts/health-check.sh http://127.0.0.1:8080`. `/api/health` is lightweight liveness. `/api/ready` verifies local configuration, SQLite connectivity/schema/writeability, Project Knowledge initialization/index status, and production LLM configuration without calling DeepSeek.

Use `docker compose ps` and `docker compose logs --tail=100 backend frontend`. Application request logs are structured and exclude bodies, query strings, credentials, prompts, resumes, job descriptions, and token headers.

## Updates and Rollback Guidance

Create a verified backup before every update. Pull or build the intended version, run Compose config validation, start it, then check readiness. If an update fails, select the previous image tag or source commit and restart it manually. Do not delete runtime directories or volumes. Deployment scripts do not guarantee zero downtime or complete automatic rollback.

## Firewall and HTTPS Guidance

Expose only the frontend port required by the deployment. Place it behind a properly configured HTTPS reverse proxy for public use. HSTS belongs on the component that actually terminates HTTPS, not the HTTP-only container. Review cloud firewalls manually; the project does not change them.

## Persistent Storage and Monitoring Administration

Host bind mounts persist `runtime/data/app.db` and `runtime/project-knowledge/PROJECT_KNOWLEDGE.md`. Backups live under `runtime/backups`. SQLite is appropriate for this current single-instance topology; never run multiple backend writers against the same SQLite file.

## Troubleshooting and Limitations

Use `docker compose config --quiet`, `docker compose ps`, container health status, and `/api/ready`. Check directory ownership for UID/GID 10001. This release does not claim Kubernetes, high availability, distributed tracing, zero-downtime deployment, automatic cloud deployment, or production deployment already completed.
