#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%s)-$$"
PROJECT_NAME="pja-v2-phase1-v19compat-${STAMP}"
TEMP_ROOT="$(mktemp -d -t pja-v19-smoke-XXXXXX)"
ENV_FILE="${TEMP_ROOT}/smoke.env"
COMPOSE_OVERRIDE="${TEMP_ROOT}/compose.override.yaml"
APP_DATA_DIR="${TEMP_ROOT}/data"
PROJECT_KNOWLEDGE_DIR="${TEMP_ROOT}/project-knowledge"
BACKUP_DIR="${TEMP_ROOT}/backups"
FILE_STORAGE_DIR="${TEMP_ROOT}/files"
PUBLIC_HTTP_PORT="$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    print(sock.getsockname()[1])
PY
)"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  printf '%s\n' 'Docker access is required for the compatibility smoke test.' >&2
  exit 1
fi

mkdir -p "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}" "${FILE_STORAGE_DIR}"
cp "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
chmod 0750 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}" "${FILE_STORAGE_DIR}"
chmod 0640 "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
if [[ "${EUID}" -eq 0 ]]; then
  chown -R 10001:10001 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}" "${FILE_STORAGE_DIR}"
else
  sudo chown -R 10001:10001 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}" "${FILE_STORAGE_DIR}"
fi

{
  printf '%s=%s\n' 'APP_ENV' 'development'
  printf '%s=%s\n' 'APP_DATABASE_PATH' '/app/backend/data/app.db'
  printf '%s=%s\n' 'AUTH_ENABLED' 'false'
  printf '%s=%s\n' 'POSTGRES_DB' 'personal_job_agent_v19_compat_test'
  printf '%s=%s\n' 'POSTGRES_BOOTSTRAP_USER' 'pja_v19_bootstrap'
  printf '%s=%s\n' 'POSTGRES_BOOTSTRAP_PASSWORD' 'v19_compat_bootstrap_test_only'
  printf '%s=%s\n' 'POSTGRES_MIGRATION_USER' 'pja_v19_migrate'
  printf '%s=%s\n' 'POSTGRES_MIGRATION_PASSWORD' 'v19_compat_migration_test_only'
  printf '%s=%s\n' 'POSTGRES_APP_USER' 'pja_v19_app'
  printf '%s=%s\n' 'POSTGRES_APP_PASSWORD' 'v19_compat_application_test_only'
  printf '%s=%s\n' 'PUBLIC_HTTP_BIND' '127.0.0.1'
  printf '%s=%s\n' 'PUBLIC_HTTP_PORT' "${PUBLIC_HTTP_PORT}"
  printf '%s=%s\n' 'DEEPSEEK_API_KEY' 'TEST_ONLY_SMOKE_CONFIGURATION'
  printf '%s=%s\n' 'TRUSTED_HOSTS' '127.0.0.1,localhost'
  printf '%s=%s\n' 'ALLOWED_ORIGINS' ''
  printf '%s=%s\n' 'ENABLE_API_DOCS' 'false'
  printf '%s=%s\n' 'LOG_LEVEL' 'INFO'
  printf '%s=%s\n' 'MONITORING_ALLOW_REMOTE_ADMIN' 'false'
} > "${ENV_FILE}"
chmod 0600 "${ENV_FILE}"

# The production network owns pja-br0. Give this isolated smoke project a
# separate bridge so it can run safely on a production host.
printf '%s\n' \
  'services:' \
  '  backend:' \
  '    environment:' \
  '      APP_ENV: development' \
  '      APP_DATABASE_PATH: /app/backend/data/app.db' \
  '      AUTH_ENABLED: "false"' \
  '      DATABASE_URL: ""' \
  '      TEST_DATABASE_URL: ""' \
  '    volumes:' \
  '      - type: bind' \
  "        source: ${APP_DATA_DIR}" \
  '        target: /app/backend/data' \
  'networks:' \
  '  application:' \
  '    driver_opts:' \
  "      com.docker.network.bridge.name: pja19-$(( $$ % 100000 ))" \
  >"${COMPOSE_OVERRIDE}"

export APP_ENV_FILE="${ENV_FILE}" APP_DATA_DIR PROJECT_KNOWLEDGE_DIR BACKUP_DIR FILE_STORAGE_DIR PUBLIC_HTTP_PORT
compose=(
  "${DOCKER[@]}" compose
  --project-directory "${ROOT_DIR}"
  --env-file "${ENV_FILE}"
  -p "${PROJECT_NAME}"
  -f "${ROOT_DIR}/compose.yaml"
  -f "${COMPOSE_OVERRIDE}"
)

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [[ "${exit_code}" != 0 ]]; then
    "${compose[@]}" ps >&2 || true
    "${compose[@]}" logs --no-color --tail 150 backend migrate database >&2 || true
  fi
  if [[ "${PROJECT_NAME}" =~ ^pja-v2-phase1-[A-Za-z0-9_.-]+$ ]]; then
    "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  if [[ "${EUID}" -eq 0 ]]; then
    rm -rf "${TEMP_ROOT}"
  else
    sudo rm -rf "${TEMP_ROOT}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  python3 - "http://127.0.0.1:${PUBLIC_HTTP_PORT}" "${method}" "${path}" "${body}" <<'PY'
import sys
import urllib.request

base, method, path, body = sys.argv[1:]
data = body.encode() if body else None
request = urllib.request.Request(base + path, data=data, method=method)
if data is not None:
    request.add_header('Content-Type', 'application/json')
with urllib.request.urlopen(request, timeout=20) as response:
    if not 200 <= response.status < 300:
        raise SystemExit(1)
    print(response.read().decode())
PY
}

wait_ready() {
  for _ in {1..40}; do
    if request GET /api/ready >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

"${compose[@]}" config --quiet
"${compose[@]}" up -d --build
wait_ready
request GET / >/dev/null
request GET /api/health >/dev/null
request GET /api/monitoring/status >/dev/null
request GET /api/security/policy >/dev/null
request GET /api/project-knowledge/status >/dev/null

evaluation="$(request POST /api/evaluations/run '{"suite_name":"default","mode":"offline"}')"
run_id="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["run_id"])' "${evaluation}")"
rebuild="$(request POST /api/project-knowledge/rebuild)"
chunk_count="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["chunk_count"])' "${rebuild}")"

"${compose[@]}" restart
wait_ready
request GET "/api/evaluations/runs/${run_id}" >/dev/null
status="$(request GET /api/project-knowledge/status)"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data["exists"] and data["indexed"]; assert data["chunk_count"] == int(sys.argv[2])' "${status}" "${chunk_count}"

"${compose[@]}" up -d --build
wait_ready
request GET "/api/evaluations/runs/${run_id}" >/dev/null
request GET /api/project-knowledge/status >/dev/null
if [[ "${EUID}" -eq 0 ]]; then
  test -s "${APP_DATA_DIR}/app.db"
  test -s "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
else
  sudo test -s "${APP_DATA_DIR}/app.db"
  sudo test -s "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
fi

printf '%s\n' 'Independent Docker smoke and persistence checks passed.'
