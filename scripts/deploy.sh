#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env.production"
MODE="build"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build) MODE="build" ;;
    --pull) MODE="pull" ;;
    --env-file)
      shift
      ENV_FILE="$1"
      ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

command -v docker >/dev/null || {
  printf '%s\n' 'Docker Engine was not found. Install Docker Engine and the Compose plugin first.' >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || { printf '%s\n' 'Production env file was not found.' >&2; exit 1; }
export APP_ENV_FILE="${ENV_FILE}"

docker_command=(docker)
if docker info >/dev/null 2>&1; then
  :
elif command -v sudo >/dev/null && sudo -n docker info >/dev/null 2>&1; then
  docker_command=(sudo env "APP_ENV_FILE=${ENV_FILE}" docker)
else
  printf '%s\n' 'Docker daemon is unavailable or this user cannot access it. Start Docker and retry with sudo access.' >&2
  exit 1
fi
"${docker_command[@]}" compose version >/dev/null || {
  printf '%s\n' 'Docker Compose v2 is required.' >&2
  exit 1
}

run_privileged() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null && sudo -n true >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

run_privileged "${ROOT_DIR}/scripts/bootstrap-runtime.sh"
compose=(
  "${docker_command[@]}" compose
  --project-directory "${ROOT_DIR}"
  --env-file "${ENV_FILE}"
  -f compose.yaml
  -f compose.prod.yaml
)
APP_ENV_FILE="${ENV_FILE}" "${compose[@]}" config --quiet

printf '%s\n' 'Production-style deployment can restart containers. It does not provide zero-downtime guarantees.'
read -r -p 'Type DEPLOY VERSION 1.9 to continue: ' confirmation
[[ "${confirmation}" == "DEPLOY VERSION 1.9" ]] || { printf '%s\n' 'Deployment cancelled.'; exit 2; }

if [[ -f "${ROOT_DIR}/runtime/data/app.db" && -f "${ROOT_DIR}/runtime/project-knowledge/PROJECT_KNOWLEDGE.md" ]]; then
  run_privileged "${ROOT_DIR}/scripts/backup.sh"
fi

if [[ "${MODE}" == "pull" ]]; then
  "${compose[@]}" pull
  "${compose[@]}" up -d --no-build
else
  "${compose[@]}" build
  "${compose[@]}" up -d --no-build
fi

published_address="$("${compose[@]}" port frontend 8080 | tail -n 1)"
published_port="${published_address##*:}"
for _ in {1..20}; do
  if "${ROOT_DIR}/scripts/health-check.sh" "http://127.0.0.1:${published_port}" >/dev/null 2>&1; then
    printf '%s\n' 'Deployment readiness checks passed.'
    exit 0
  fi
  sleep 3
done

printf '%s\n' 'Readiness did not pass. Inspect: docker compose ps and docker compose logs --tail=100.' >&2
printf '%s\n' 'No volumes were deleted and no automatic restore was attempted.' >&2
exit 1
