#!/usr/bin/env bash
set -euo pipefail

CANDIDATE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${CANDIDATE_ROOT}/.env.candidate"
SECRET_DIR="${CANDIDATE_ROOT}/.candidate-secrets"
JAVA_KEY_FILE="${SECRET_DIR}/java-api-key"

fail() {
  printf 'candidate-secrets: %s\n' "$1" >&2
  exit 1
}

for command_name in openssl python3; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "required command is unavailable: ${command_name}"
done

if [[ -e "${ENV_FILE}" || -e "${SECRET_DIR}" ]]; then
  fail "candidate secret state already exists; remove only this candidate state explicitly first"
fi

umask 077
mkdir -p "${SECRET_DIR}"
java_key="$(openssl rand -hex 32)"
printf '%s\n' "${java_key}" >"${JAVA_KEY_FILE}"

api_port="$(python3 - <<'PY'
import socket
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
)"
revision="$(git -C "${CANDIDATE_ROOT}/../../.." rev-parse HEAD)"

{
  printf 'CANDIDATE_POSTGRES_DB=pja_java_normalization_candidate_test\n'
  printf 'CANDIDATE_POSTGRES_USER=pja_candidate\n'
  printf 'CANDIDATE_POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  printf 'CANDIDATE_ADMIN_EMAIL=candidate-admin@example.com\n'
  printf 'CANDIDATE_ADMIN_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '\n')"
  printf 'CANDIDATE_AUTH_FINGERPRINT_KEY=%s\n' "$(openssl rand -hex 32)"
  printf 'CANDIDATE_JAVA_API_KEY=%s\n' "${java_key}"
  printf 'CANDIDATE_JAVA_KEY_FILE=%s\n' "${JAVA_KEY_FILE}"
  printf 'CANDIDATE_MOCK_PROVIDER_KEY=%s\n' "$(openssl rand -hex 32)"
  printf 'CANDIDATE_MONITORING_TOKEN=%s\n' "$(openssl rand -hex 32)"
  printf 'CANDIDATE_API_PORT=%s\n' "${api_port}"
  printf 'CANDIDATE_BACKEND_BASE_IMAGE=pja-java-candidate-backend-base:%s\n' "${revision:0:12}"
  printf 'CANDIDATE_BACKEND_IMAGE=pja-java-candidate-backend:%s\n' "${revision:0:12}"
  printf 'CANDIDATE_JAVA_IMAGE=pja-java-candidate-normalization:%s\n' "${revision:0:12}"
  printf 'CANDIDATE_OCI_REVISION=%s\n' "${revision}"
} >"${ENV_FILE}"

# The directory remains mode 0700 on the host. The key itself is read-only to
# the non-root backend UID after Compose bind-mounts it as a local secret.
chmod 0600 "${ENV_FILE}"
chmod 0644 "${JAVA_KEY_FILE}"
unset java_key
printf 'candidate-secrets: generated isolated candidate configuration (values withheld)\n'
