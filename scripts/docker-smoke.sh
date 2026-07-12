#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="pja-v19-smoke"
TEMP_ROOT="$(mktemp -d -t pja-v19-smoke-XXXXXX)"
ENV_FILE="${TEMP_ROOT}/smoke.env"
COMPOSE_OVERRIDE="${TEMP_ROOT}/compose.override.yaml"
APP_DATA_DIR="${TEMP_ROOT}/data"
PROJECT_KNOWLEDGE_DIR="${TEMP_ROOT}/project-knowledge"
BACKUP_DIR="${TEMP_ROOT}/backups"
PUBLIC_HTTP_PORT="$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    print(sock.getsockname()[1])
PY
)"

mkdir -p "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}"
cp "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
chmod 0750 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}"
chmod 0640 "${PROJECT_KNOWLEDGE_DIR}/PROJECT_KNOWLEDGE.md"
if [[ "${EUID}" -eq 0 ]]; then
  chown -R 10001:10001 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}"
else
  sudo chown -R 10001:10001 "${APP_DATA_DIR}" "${PROJECT_KNOWLEDGE_DIR}" "${BACKUP_DIR}"
fi

{
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
  'networks:' \
  '  application:' \
  '    driver_opts:' \
  '      com.docker.network.bridge.name: pja-smoke-br0' \
  >"${COMPOSE_OVERRIDE}"

export APP_ENV_FILE="${ENV_FILE}" APP_DATA_DIR PROJECT_KNOWLEDGE_DIR BACKUP_DIR PUBLIC_HTTP_PORT
compose=(
  docker compose
  --project-directory "${ROOT_DIR}"
  --env-file "${ENV_FILE}"
  -p "${PROJECT_NAME}"
  -f "${ROOT_DIR}/compose.yaml"
  -f "${COMPOSE_OVERRIDE}"
)

cleanup() {
  "${compose[@]}" down --remove-orphans >/dev/null 2>&1 || true
  if [[ "${EUID}" -eq 0 ]]; then
    rm -rf "${TEMP_ROOT}"
  else
    sudo rm -rf "${TEMP_ROOT}"
  fi
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
  for attempt in {1..40}; do
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
