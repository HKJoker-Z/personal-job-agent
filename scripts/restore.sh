#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${APP_ENV_FILE:-${ROOT_DIR}/.env.production}"
BASE_URL="${RESTORE_BASE_URL:-http://127.0.0.1:8080}"

if [[ " ${*} " != *" --confirmation "* ]]; then
  printf '%s\n' 'Restore requires: --confirmation "RESTORE BACKUP"' >&2
  exit 2
fi

command -v docker >/dev/null || {
  printf '%s\n' 'Docker is required to stop backend writes before restore.' >&2
  exit 1
}
docker compose version >/dev/null || {
  printf '%s\n' 'Docker Compose v2 is required.' >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || {
  printf '%s\n' 'Production env file was not found.' >&2
  exit 1
}

export APP_ENV_FILE="${ENV_FILE}"
compose=(docker compose --project-directory "${ROOT_DIR}" --env-file "${ENV_FILE}")
"${compose[@]}" stop backend

if ! python3 "${ROOT_DIR}/scripts/restore_runtime.py" "$@"; then
  "${compose[@]}" up -d backend
  printf '%s\n' 'Restore failed safely; backend restart was requested with current data.' >&2
  exit 1
fi

"${compose[@]}" up -d backend
for attempt in {1..20}; do
  if python3 - "${BASE_URL}" <<'PY'
import sys
import urllib.request
with urllib.request.urlopen(sys.argv[1].rstrip('/') + '/api/ready', timeout=5) as response:
    if response.status != 200:
        raise SystemExit(1)
PY
  then
    printf '%s\n' 'Restore readiness check passed.'
    exit 0
  fi
  sleep 3
done

printf '%s\n' 'Backend restarted, but readiness did not pass. Inspect container logs.' >&2
exit 1
