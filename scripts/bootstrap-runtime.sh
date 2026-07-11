#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/runtime"

install -d -m 0750 "${RUNTIME_DIR}/data" "${RUNTIME_DIR}/project-knowledge" "${RUNTIME_DIR}/backups"

TARGET_KNOWLEDGE="${RUNTIME_DIR}/project-knowledge/PROJECT_KNOWLEDGE.md"
if [[ ! -e "${TARGET_KNOWLEDGE}" ]]; then
  install -m 0640 "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" "${TARGET_KNOWLEDGE}"
fi

if [[ -e "${ROOT_DIR}/backend/data/app.db" && ! -e "${RUNTIME_DIR}/data/app.db" ]]; then
  printf '%s\n' 'Existing backend/data/app.db was not copied. Preview scripts/migrate-existing-data.sh first.'
fi

if [[ "${EUID}" -eq 0 ]]; then
  chown -R 10001:10001 "${RUNTIME_DIR}/data" "${RUNTIME_DIR}/project-knowledge" "${RUNTIME_DIR}/backups"
else
  owner_uid="$(stat -c '%u' "${RUNTIME_DIR}/data")"
  if [[ "${owner_uid}" != "10001" ]]; then
    printf '%s\n' 'Runtime ownership must be UID/GID 10001. Re-run bootstrap with sudo; chmod 777 is not used.' >&2
    exit 1
  fi
fi

printf '%s\n' 'Runtime directories are ready.'
