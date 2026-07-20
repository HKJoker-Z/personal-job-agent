#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%s)-$$"
VOLUME_NAME="pja-v201-redis-init-test-${STAMP}"
V1_NETWORK="pja-v201-v1-network-${STAMP}"
V2_NETWORK="pja-v201-v2-network-${STAMP}"
V1_CONTAINER="pja-v201-v1-service-${STAMP}"
V2_CONTAINER="pja-v201-v2-service-${STAMP}"
CONFIG_JSON="$(mktemp /tmp/pja-v201-compose.XXXXXX.json)"
SERVER_LOG="$(mktemp /tmp/pja-v201-health.XXXXXX.log)"
SERVER_PID=""

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  printf '%s\n' 'Docker is required.' >&2
  exit 1
fi

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -n "$SERVER_PID" ]]; then kill "$SERVER_PID" >/dev/null 2>&1 || true; fi
  "${DOCKER[@]}" rm --force "$V1_CONTAINER" "$V2_CONTAINER" >/dev/null 2>&1 || true
  "${DOCKER[@]}" network rm "$V1_NETWORK" "$V2_NETWORK" >/dev/null 2>&1 || true
  "${DOCKER[@]}" volume rm "$VOLUME_NAME" >/dev/null 2>&1 || true
  rm -f "$CONFIG_JSON" "$SERVER_LOG"
  exit "$status"
}
trap cleanup EXIT

FAKE_DIGEST="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PROVIDER_KEY_NAME=DEEPSEEK_API_KEY
COMPOSE_ENV=(
  "BACKEND_IMAGE=ghcr.io/example/backend@${FAKE_DIGEST}"
  "FRONTEND_IMAGE=ghcr.io/example/frontend@${FAKE_DIGEST}"
  RELEASE_VERSION=2.0.1 "RELEASE_ROOT=${ROOT_DIR}/deploy/production"
  FILES_DIR=/tmp/pja-v201-files PROJECT_KNOWLEDGE_DIR=/tmp/pja-v201-knowledge
  BACKUP_DIR=/tmp/pja-v201-backup TLS_DIR=/tmp/pja-v201-tls
  "REDIS_CONFIG_FILE=${ROOT_DIR}/deploy/production/redis.conf.example"
  AUTH_TRUSTED_ORIGINS=https://example.test AUTH_FINGERPRINT_KEY=test-only-32-character-fingerprint-key
  ALLOWED_ORIGINS=https://example.test TRUSTED_HOSTS=example.test "${PROVIDER_KEY_NAME}=test-only"
  REDIS_PASSWORD=test-only POSTGRES_DB=pja POSTGRES_BOOTSTRAP_USER=bootstrap
  POSTGRES_BOOTSTRAP_PASSWORD=test-only POSTGRES_APP_USER=app POSTGRES_APP_PASSWORD=test-only
  POSTGRES_MIGRATION_USER=migrate POSTGRES_MIGRATION_PASSWORD=test-only
  MODEL_INPUT_COST_PER_MILLION_USD=1 MODEL_OUTPUT_COST_PER_MILLION_USD=1
)
if [[ "${DOCKER[0]}" == "sudo" ]]; then
  # The Compose process needs Docker privileges; the destination is intentionally
  # the invoking user's private temporary file.
  # shellcheck disable=SC2024
  sudo -n env "${COMPOSE_ENV[@]}" docker compose \
    -f "${ROOT_DIR}/deploy/production/compose.yaml" config --format json >"$CONFIG_JSON"
else
  env "${COMPOSE_ENV[@]}" docker compose \
    -f "${ROOT_DIR}/deploy/production/compose.yaml" config --format json >"$CONFIG_JSON"
fi

python3 - "$CONFIG_JSON" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
services = value["services"]
edge = services["edge"]
assert edge["read_only"] is True
assert edge["user"] == "101:101"
assert edge["cap_drop"] == ["ALL"]
assert list(edge["networks"]) == ["application"]
assert all("uid=101" in item and "gid=101" in item for item in edge["tmpfs"])
assert services["backend"]["networks"]["application"]["aliases"] == ["backend-v2"]
assert services["frontend"]["networks"]["application"]["aliases"] == ["frontend-v2"]
assert services["redis-init"]["cap_add"] == ["CHOWN", "FOWNER", "DAC_READ_SEARCH"]
assert all("@sha256:" in services[name]["image"] for name in ("backend", "worker", "outbox-dispatcher", "frontend", "edge"))
PY

if rg -n 'proxy_pass http://(frontend|backend):' \
  "${ROOT_DIR}/deploy/production/edge-nginx.conf" \
  "${ROOT_DIR}/deploy/production/frontend-nginx.conf"; then
  printf '%s\n' 'Ambiguous Docker upstream detected.' >&2
  exit 1
fi
rg -q 'frontend-v2' "${ROOT_DIR}/deploy/production/edge-nginx.conf"
rg -q 'backend-v2' "${ROOT_DIR}/deploy/production/frontend-nginx.conf"
if rg -n 'chown[[:space:]]+-R' "${ROOT_DIR}/deploy/production/redis-init-idempotent.sh"; then
  printf '%s\n' 'Redis initialization must not perform an unconditional recursive chown.' >&2
  exit 1
fi

"${DOCKER[@]}" network create "$V1_NETWORK" >/dev/null
"${DOCKER[@]}" network create "$V2_NETWORK" >/dev/null
"${DOCKER[@]}" run --detach --name "$V1_CONTAINER" --network "$V1_NETWORK" \
  --network-alias backend alpine:3.21 sleep 300 >/dev/null
"${DOCKER[@]}" run --detach --name "$V2_CONTAINER" --network "$V2_NETWORK" \
  --network-alias frontend-v2 alpine:3.21 sleep 300 >/dev/null
# The variable intentionally expands inside the isolated probe container.
# shellcheck disable=SC2016
"${DOCKER[@]}" run --rm --network "$V2_NETWORK" -e LEGACY_HOST="$V1_CONTAINER" alpine:3.21 \
  sh -eu -c 'getent hosts frontend-v2 >/dev/null; ! getent hosts backend >/dev/null; ! getent hosts "$LEGACY_HOST" >/dev/null'

"${DOCKER[@]}" volume create "$VOLUME_NAME" >/dev/null
OUTPUT="$("${DOCKER[@]}" run --rm --network none --user 0:0 --entrypoint /bin/sh \
  --read-only --security-opt no-new-privileges --cap-drop ALL \
  --cap-add CHOWN --cap-add FOWNER --cap-add DAC_READ_SEARCH \
  -v "$VOLUME_NAME:/data" \
  -v "${ROOT_DIR}/deploy/production/redis-init-idempotent.sh:/opt/pja/init.sh:ro" \
  redis:7.4.1-alpine -c '/opt/pja/init.sh; /opt/pja/init.sh; /opt/pja/init.sh')"
[[ "$OUTPUT" == *'"redis_init":"repaired"'* || "$OUTPUT" == *'"redis_init":"already_valid"'* ]]
[[ "$(grep -c '"redis_init":"already_valid"' <<<"$OUTPUT")" -ge 2 ]]

python3 - <<'PY' >"$SERVER_LOG" 2>&1 &
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status":"ok","version":"2.0.1"}'
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(("127.0.0.1", 18079), Handler).serve_forever()
PY
SERVER_PID=$!
for _ in $(seq 1 20); do
  if curl --noproxy '*' --silent --fail http://127.0.0.1:18079 >/dev/null; then break; fi
  sleep 0.1
done
"${ROOT_DIR}/scripts/assert-release-health.sh" http://127.0.0.1:18079 2.0.1 >/dev/null
if "${ROOT_DIR}/scripts/assert-release-health.sh" http://127.0.0.1:18079 2.0.0 >/dev/null 2>&1; then
  printf '%s\n' 'Health assertion accepted the wrong release.' >&2
  exit 1
fi

printf '%s\n' 'Version 2.0.1 production runtime regression tests passed.'
