#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/.env.production}"
PUBLIC_HOST="${2:-}"

command -v docker >/dev/null || {
  printf '%s\n' 'Docker Engine was not found.' >&2
  exit 1
}
[[ -f "${ENV_FILE}" ]] || {
  printf 'Production env file not found: %s\n' "${ENV_FILE}" >&2
  exit 1
}

docker_command=(docker)
if docker info >/dev/null 2>&1; then
  :
elif command -v sudo >/dev/null && sudo -n docker info >/dev/null 2>&1; then
  docker_command=(sudo env "APP_ENV_FILE=${ENV_FILE}" docker)
else
  printf '%s\n' 'Docker daemon is unavailable or inaccessible.' >&2
  exit 1
fi

compose=(
  "${docker_command[@]}" compose
  --project-directory "${ROOT_DIR}"
  --env-file "${ENV_FILE}"
  -f compose.yaml
  -f compose.prod.yaml
)
export APP_ENV_FILE="${ENV_FILE}"

running_services="$("${compose[@]}" ps --status running --services)"
for service in backend frontend; do
  if ! grep -Fxq "${service}" <<<"${running_services}"; then
    printf 'Compose service is not running: %s\n' "${service}" >&2
    exit 1
  fi
done
"${compose[@]}" ps

published_address="$("${compose[@]}" port frontend 8080 | head -n 1)"
published_port="${published_address##*:}"
if [[ -z "${published_port}" || ! "${published_port}" =~ ^[0-9]+$ ]]; then
  printf '%s\n' 'Unable to determine the published frontend port.' >&2
  exit 1
fi

ss_command=(ss)
if command -v sudo >/dev/null && sudo -n true >/dev/null 2>&1; then
  ss_command=(sudo ss)
fi
listen_rows="$("${ss_command[@]}" -ltnH "sport = :${published_port}")"
if ! grep -Eq '(^|[[:space:]])(0\.0\.0\.0|\*):' <<<"${listen_rows}"; then
  printf 'Frontend port is not listening on all IPv4 interfaces: %s\n' "${published_port}" >&2
  exit 1
fi
printf 'ok all-interface listener 0.0.0.0:%s\n' "${published_port}"

base_url="http://127.0.0.1:${published_port}"
for path in / /api/health /api/ready; do
  curl --fail --silent --show-error --connect-timeout 10 --output /dev/null "${base_url}${path}"
  printf 'ok %s\n' "${path}"
done

if [[ -n "${PUBLIC_HOST}" ]]; then
  for host_header in "${PUBLIC_HOST}" "${PUBLIC_HOST}:${published_port}"; do
    curl --fail --silent --show-error --connect-timeout 10 --output /dev/null \
      -H "Host: ${host_header}" "${base_url}/api/health"
    printf 'ok Host: %s\n' "${host_header}"
  done
else
  printf '%s\n' 'Public Host header check skipped; pass SERVER_IP as the second argument.'
fi

if command -v ufw >/dev/null; then
  if command -v sudo >/dev/null && sudo -n true >/dev/null 2>&1; then
    sudo ufw status verbose || true
  else
    ufw status verbose || true
  fi
fi
