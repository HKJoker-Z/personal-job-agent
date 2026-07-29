#!/usr/bin/env bash
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FILE="${1:-${SERVICE_ROOT}/.env.compose}"
HOST_PORT="${JD_COMPOSE_HOST_PORT:-18082}"

command -v openssl >/dev/null 2>&1 || {
  echo "generate-compose-env: openssl is required" >&2
  exit 1
}

if ! [[ "${HOST_PORT}" =~ ^[0-9]+$ ]] \
  || ((HOST_PORT < 1024 || HOST_PORT > 65535)) \
  || [[ "${HOST_PORT}" == "8080" ]]; then
    echo "generate-compose-env: invalid loopback host port" >&2
    exit 1
fi

if [[ -e "${OUTPUT_FILE}" ]]; then
  echo "generate-compose-env: refusing to overwrite an existing file" >&2
  exit 1
fi

output_directory="$(dirname "${OUTPUT_FILE}")"
[[ -d "${output_directory}" ]] || {
  echo "generate-compose-env: output directory does not exist" >&2
  exit 1
}

umask 077
temporary_file="$(mktemp "${output_directory}/.env.compose.tmp.XXXXXX")"
cleanup() {
  rm -f "${temporary_file}"
}
trap cleanup EXIT INT TERM

api_key="$(openssl rand -hex 32)"
bootstrap_password="$(openssl rand -hex 32)"
migration_password="$(openssl rand -hex 32)"
application_password="$(openssl rand -hex 32)"

{
  printf 'JD_COMPOSE_API_KEY=%s\n' "${api_key}"
  printf 'JD_COMPOSE_DB_NAME=jd_normalization\n'
  printf 'JD_COMPOSE_BOOTSTRAP_DB_USER=jd_bootstrap\n'
  printf 'JD_COMPOSE_BOOTSTRAP_DB_PASSWORD=%s\n' "${bootstrap_password}"
  printf 'JD_COMPOSE_MIGRATION_DB_USER=jd_migration\n'
  printf 'JD_COMPOSE_MIGRATION_DB_PASSWORD=%s\n' "${migration_password}"
  printf 'JD_COMPOSE_APP_DB_USER=jd_application\n'
  printf 'JD_COMPOSE_APP_DB_PASSWORD=%s\n' "${application_password}"
  printf 'JD_COMPOSE_HOST_PORT=%s\n' "${HOST_PORT}"
} >"${temporary_file}"

chmod 0600 "${temporary_file}"
mv "${temporary_file}" "${OUTPUT_FILE}"
trap - EXIT INT TERM

unset api_key bootstrap_password migration_password application_password
echo "generate-compose-env: created a mode-0600 local environment file"
