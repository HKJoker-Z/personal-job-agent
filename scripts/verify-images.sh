#!/usr/bin/env bash
set -Eeuo pipefail

BACKEND_IMAGE="${1:-personal-job-agent-backend:local}"
FRONTEND_IMAGE="${2:-personal-job-agent-frontend:local}"

for image in "${BACKEND_IMAGE}" "${FRONTEND_IMAGE}"; do
  user="$(docker image inspect --format '{{.Config.User}}' "${image}")"
  [[ -n "${user}" && "${user}" != "0" && "${user}" != "root" ]] || {
    printf 'Image runs as root: %s\n' "${image}" >&2
    exit 1
  }
  docker run --rm --entrypoint sh "${image}" -c \
    'test -z "$(find / -xdev \( -name .env -o -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) -print -quit 2>/dev/null)"'
done

printf '%s\n' 'Image user and sensitive-path checks passed.'
