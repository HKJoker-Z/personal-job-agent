# Version 1.9 Deployment Guide

## Overview and Architecture

Version 1.9 provides a repeatable, single-instance Docker Compose topology:

`Browser → Frontend/Nginx → /api → Backend/FastAPI → SQLite + Project Knowledge`

Only the frontend publishes a host port. The backend is reachable only on the dedicated Compose network and requires outbound access for DeepSeek when Analyze is used.

## Prerequisites and Ubuntu Requirements

- A maintained Ubuntu server with Docker Engine and Docker Compose v2 installed and running
- Git for source-build deployments, or GHCR access for image deployments
- Adequate disk space and restricted filesystem permissions for runtime data and backups
- A user permitted to run Docker commands

Install Docker before running Compose. If `docker compose ps` reports `docker: command not found`, no Version 1.9 containers have been started. The project does not automatically modify cloud firewalls, DNS, system Nginx, systemd, or HTTPS configuration.

## Production Access URL and Ports

The Version 1.9 browser entry point is `http://SERVER_IP:8080`. Nginx publishes host TCP 8080 and proxies same-origin `/api/...` requests to the backend over the private Compose network.

- Open TCP 8080 in the Ubuntu firewall and cloud security group when required.
- Do not publish backend port 8000; it is internal to Docker Compose.
- Do not expose Vite port 5173; it is only used by the development workflow.
- Verify the entry point with `curl http://127.0.0.1:8080/api/health` and `curl http://SERVER_IP:8080/api/health`.

## Mihomo TUN and Docker Return Routing

Mihomo TUN policy routing may capture the SYN-ACK return path for a Docker published port. In that failure mode, the host listens on `0.0.0.0:8080` and localhost succeeds, but a remote client never completes the TCP handshake because the Frontend response is sent to the TUN routing table instead of the main table.

The Compose `application` network has the stable Linux bridge name `pja-br0`. Stable naming is required because Docker's default `br-<network-id>` interface changes when the Compose network is recreated. The project routing rule is deliberately narrow:

```text
pref 8999 iif pja-br0 ipproto tcp sport 8080 lookup main
```

This selects the main IPv4 routing table only for Frontend TCP responses sourced from port 8080. It does not bypass TUN for all Docker traffic, does not publish Backend port 8000, and does not change iptables, nftables, sysctl, the default route, or Mihomo configuration. Backend HTTPS traffic, including DeepSeek access, retains the host's existing policy routing.

The repository provides `scripts/configure-production-routing.sh` with `install`, `remove`, and `status` commands. Install it at the absolute path referenced by the unit, then install the unit:

```bash
sudo install -Dm0755 scripts/configure-production-routing.sh \
  /usr/local/libexec/personal-job-agent/configure-production-routing.sh
sudo install -Dm0644 deploy/systemd/personal-job-agent-routing.service \
  /etc/systemd/system/personal-job-agent-routing.service
sudo systemctl daemon-reload
sudo systemctl enable --now personal-job-agent-routing.service
```

The service waits up to 120 seconds for `pja-br0`; `TimeoutStartSec` is longer than that wait and `Restart=on-failure` retries a late Docker network. `PJA_ROUTING_WAIT_SECONDS` may be set to an integer from 1 through 600, although the production unit intentionally uses 120. Check it with:

```bash
sudo /usr/local/libexec/personal-job-agent/configure-production-routing.sh status
systemctl is-enabled personal-job-agent-routing.service
systemctl is-active personal-job-agent-routing.service
ip -4 rule show
```

Do not enable the service until the Compose network has been migrated to `pja-br0`. Network migration recreates containers and the Compose network, so create a verified runtime backup first and use `docker compose down` without `-v`. Never use `down -v`, delete bind-mounted runtime directories, or flush iptables/nftables to troubleshoot this condition. See [Client Proxy Troubleshooting](CLIENT_PROXY_TROUBLESHOOTING.md) for diagnosis and rollback guidance.

## Environment Configuration

Copy `.env.production.example` to an ignored `.env.production` and set values on the deployment host. Production requires a non-empty `DEEPSEEK_API_KEY` and explicit `TRUSTED_HOSTS`. `ALLOWED_ORIGINS` may be empty for same-origin operation but cannot contain `*`. API docs default to disabled.

For a direct IP deployment, set `PUBLIC_HTTP_PORT=8080`, `ALLOWED_ORIGINS=http://SERVER_IP:8080`, and `TRUSTED_HOSTS=SERVER_IP,localhost,127.0.0.1`. Never use wildcard origins or trusted hosts. Recreate the containers after changing `.env.production` so the backend receives the new values.

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
APP_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml config --quiet
APP_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.yaml -f compose.prod.yaml build
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

Run `scripts/health-check.sh http://127.0.0.1:8080`. For a complete host-side check, run `scripts/check-production-access.sh .env.production SERVER_IP`. `/api/health` is lightweight liveness. `/api/ready` verifies local configuration, SQLite connectivity/schema/writeability, Project Knowledge initialization/index status, and production LLM configuration without calling DeepSeek.

Use `docker compose -f compose.yaml -f compose.prod.yaml ps` and `docker compose -f compose.yaml -f compose.prod.yaml logs --tail=100 backend frontend`. A browser error after the homepage loads should be checked for stale requests to ports 8000/5173, Nginx 502 responses, backend health, trusted hosts, and stale browser cache. Application request logs are structured and exclude bodies, query strings, credentials, prompts, resumes, job descriptions, and token headers.

## Updates and Rollback Guidance

Create a verified backup before every update. Pull or build the intended version, run Compose config validation, start it, then check readiness. If an update fails, select the previous image tag or source commit and restart it manually. Do not delete runtime directories or volumes. Deployment scripts do not guarantee zero downtime or complete automatic rollback.

When rolling back the stable bridge migration, do not assume the regenerated dynamic bridge has its old name. Inspect the current Compose network ID, derive the actual `br-<network-id>` interface, and apply only the exact TCP source-port 8080 return-routing rule. Preserve a verified `pja-br0` pref 8998 rule if permanent unit installation fails, and stop before removing the last working return-path rule.

## Firewall and HTTPS Guidance

Expose only frontend TCP 8080. Place it behind a properly configured HTTPS reverse proxy for public use. HSTS belongs on the component that actually terminates HTTPS, not the HTTP-only container. Review cloud firewalls manually; if localhost succeeds but public access fails while Docker listens on `0.0.0.0:8080`, allow inbound TCP 8080 in the cloud security group. Do not open 8000 or 5173.

## Persistent Storage and Monitoring Administration

Host bind mounts persist `runtime/data/app.db` and `runtime/project-knowledge/PROJECT_KNOWLEDGE.md`. Backups live under `runtime/backups`. SQLite is appropriate for this current single-instance topology; never run multiple backend writers against the same SQLite file.

## Troubleshooting and Limitations

Use `docker compose config --quiet`, `docker compose ps`, container health status, and `/api/ready`. Check directory ownership for UID/GID 10001. This release does not claim Kubernetes, high availability, distributed tracing, zero-downtime deployment, automatic cloud deployment, or production deployment already completed.
