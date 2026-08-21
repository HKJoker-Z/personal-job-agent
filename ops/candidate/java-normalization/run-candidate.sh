#!/usr/bin/env bash
set -euo pipefail

CANDIDATE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${CANDIDATE_ROOT}/../../.." && pwd)"
COMPOSE_FILE="${CANDIDATE_ROOT}/compose.yaml"
ENV_FILE="${CANDIDATE_ROOT}/.env.candidate"
RESULTS_DIR="${CANDIDATE_ROOT}/.candidate-results"
ASSERTIONS="${CANDIDATE_ROOT}/assertions.py"

if [[ "${1:-}" != "--ephemeral" || $# -ne 1 ]]; then
  printf '%s\n' 'candidate: refusing to run without the exact --ephemeral flag' >&2
  exit 2
fi

fail() {
  printf 'candidate: %s\n' "$1" >&2
  exit 1
}

step() {
  printf 'candidate: PASS - %s\n' "$1"
}

for command_name in docker curl python3 openssl; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "required command is unavailable: ${command_name}"
done
docker info >/dev/null 2>&1 || fail "Docker is unavailable"
docker compose version >/dev/null 2>&1 || fail "Docker Compose is unavailable"

if [[ ! -f "${ENV_FILE}" ]]; then
  "${CANDIDATE_ROOT}/generate-secrets.sh"
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
export PJA_TEST_ADMIN_PASSWORD="${CANDIDATE_ADMIN_PASSWORD}"

run_suffix="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}-$(openssl rand -hex 4)"
run_suffix="${run_suffix,,}"
run_suffix="${run_suffix//[^a-z0-9-]/-}"
PROJECT_NAME="pja-java-candidate-${run_suffix}"
[[ "${PROJECT_NAME}" =~ ^pja-java-candidate-[a-z0-9-]+$ ]] \
  || fail "generated Compose project name is outside the candidate namespace"

COMPOSE=(
  docker compose
  --project-name "${PROJECT_NAME}"
  --file "${COMPOSE_FILE}"
  --env-file "${ENV_FILE}"
)

temporary_directory="$(mktemp -d)"
mkdir -p "${RESULTS_DIR}"
rm -f "${RESULTS_DIR}/summary.json" "${RESULTS_DIR}/resources.json"

sanitize() {
  python3 -c '
import os
import sys
text = sys.stdin.read()
for name in (
    "CANDIDATE_POSTGRES_PASSWORD",
    "CANDIDATE_ADMIN_PASSWORD",
    "CANDIDATE_AUTH_FINGERPRINT_KEY",
    "CANDIDATE_JAVA_API_KEY",
    "CANDIDATE_MOCK_PROVIDER_KEY",
    "CANDIDATE_MONITORING_TOKEN",
):
    value = os.environ.get(name, "")
    if value:
        text = text.replace(value, "[REDACTED]")
sys.stdout.write(text)
'
}

cleanup() {
  exit_status=$?
  trap - EXIT INT TERM
  if ((exit_status != 0)); then
    printf '%s\n' 'candidate: bounded sanitized failure state follows' >&2
    "${COMPOSE[@]}" ps --all 2>&1 | sanitize >&2 || true
    "${COMPOSE[@]}" logs --no-color --tail 120 \
      backend java-normalization fault-stub migrate postgres 2>&1 \
      | sanitize >&2 || true
  fi
  case "${PROJECT_NAME}" in
    pja-java-candidate-*)
      "${COMPOSE[@]}" down --remove-orphans --volumes --timeout 20 \
        >/dev/null 2>&1 || true
      ;;
    *)
      printf '%s\n' 'candidate: refused cleanup outside candidate namespace' >&2
      exit_status=1
      ;;
  esac
  rm -rf "${temporary_directory}"
  if [[ "${ENV_FILE}" == "${CANDIDATE_ROOT}/.env.candidate" ]]; then
    rm -f "${ENV_FILE}"
  else
    exit_status=1
  fi
  if [[ "${CANDIDATE_JAVA_KEY_FILE}" == "${CANDIDATE_ROOT}/.candidate-secrets/java-api-key" ]]; then
    rm -f "${CANDIDATE_JAVA_KEY_FILE}"
    rmdir "${CANDIDATE_ROOT}/.candidate-secrets" 2>/dev/null || true
  else
    printf '%s\n' 'candidate: refused secret cleanup outside candidate directory' >&2
    exit_status=1
  fi
  exit "${exit_status}"
}
trap cleanup EXIT INT TERM

cd "${REPOSITORY_ROOT}"

if [[ "${CANDIDATE_SKIP_BUILD:-0}" != "1" ]]; then
  docker build \
    --file backend/Dockerfile \
    --tag "${CANDIDATE_BACKEND_BASE_IMAGE}" \
    . >/dev/null
  docker build \
    --file "${CANDIDATE_ROOT}/backend-candidate.Dockerfile" \
    --build-arg "BASE_IMAGE=${CANDIDATE_BACKEND_BASE_IMAGE}" \
    --tag "${CANDIDATE_BACKEND_IMAGE}" \
    . >/dev/null
  docker build \
    --file services/jd-normalization-service/Dockerfile \
    --target application \
    --build-arg "OCI_REVISION=${CANDIDATE_OCI_REVISION}" \
    --tag "${CANDIDATE_JAVA_IMAGE}" \
    services/jd-normalization-service >/dev/null
else
  docker image inspect "${CANDIDATE_BACKEND_IMAGE}" "${CANDIDATE_JAVA_IMAGE}" \
    >/dev/null
fi
step "candidate backend and real Java normalization-only images built locally"

"${COMPOSE[@]}" config --quiet
rendered_services="$("${COMPOSE[@]}" config --services)"
rendered_services="$(printf '%s\n' "${rendered_services}" | sort)"
[[ "${rendered_services}" == $'backend\nfault-stub\njava-normalization\nmigrate\npostgres' ]] \
  || fail "candidate Compose service set differs"
step "Compose configuration contains only the isolated candidate services"

"${COMPOSE[@]}" up --detach --wait postgres >/dev/null
"${COMPOSE[@]}" run --rm migrate >/dev/null
head_value="$("${COMPOSE[@]}" run --rm --no-deps migrate \
  alembic -c alembic.ini heads | sed -n 's/ .*//p')"
current_value="$("${COMPOSE[@]}" run --rm --no-deps migrate \
  alembic -c alembic.ini current | sed -n 's/ .*//p')"
[[ "${head_value}" == "20260820_08" && "${current_value}" == "20260820_08" ]] \
  || fail "candidate Alembic revision is not 20260820_08"
"${COMPOSE[@]}" run --rm --no-deps migrate \
  alembic -c alembic.ini upgrade head >/dev/null
schema_ok="$("${COMPOSE[@]}" exec -T postgres \
  psql -U "${CANDIDATE_POSTGRES_USER}" -d "${CANDIDATE_POSTGRES_DB}" -Atqc \
  "SELECT (
     (SELECT version_num FROM alembic_version) = '20260820_08'
     AND EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_name = 'analyze_idempotency_records'
         AND column_name = 'execution_fingerprint'
     )
     AND (
       SELECT count(*) FROM pg_constraint
       WHERE conrelid = 'analyze_idempotency_records'::regclass
         AND contype = 'c'
     ) >= 5
   );")"
[[ "${schema_ok}" == "t" ]] || fail "candidate execution-binding schema is incomplete"
step "fresh migration, single head, schema constraints, and no-op rerun validated"

"${COMPOSE[@]}" run --rm --no-deps \
  -e PJA_TEST_ADMIN_PASSWORD \
  migrate python -m app.cli users create-admin \
  --email "${CANDIDATE_ADMIN_EMAIL}" \
  --display-name "Synthetic Candidate Admin" >/dev/null

ORIGIN="http://127.0.0.1:${CANDIDATE_API_PORT}"
COOKIE_JAR="${temporary_directory}/cookies.txt"
RESPONSE="${temporary_directory}/response.json"
HEADERS="${temporary_directory}/headers.txt"
RAW_JOB="${temporary_directory}/synthetic-job.txt"
LOCAL_JOB="${temporary_directory}/synthetic-local-job.txt"

printf '%s\n' \
  $'Synthetic Cafe\u0301   Platform Engineer' \
  'Contact synthetic candidate team' \
  'Required:' \
  '- FastAPI' \
  '- PostgreSQL' \
  '' \
  '' \
  'Preferred:' \
  '- Java' >"${RAW_JOB}"

"${COMPOSE[@]}" run --rm --no-deps -T migrate python -c '
import sys
from analysis_fallback import structure_aware_truncate
from security_utils import scan_and_sanitize_untrusted_text
raw = sys.stdin.read().strip()
local_text, truncated = structure_aware_truncate(raw, 120_000)
assert truncated is False
sanitized, scan = scan_and_sanitize_untrusted_text(local_text, "job_description")
assert scan["blocked"] is False
assert scan["findings"] == []
assert sanitized == local_text
sys.stdout.write(sanitized)
' <"${RAW_JOB}" >"${LOCAL_JOB}"

wait_backend() {
  for attempt in $(seq 1 60); do
    if curl --noproxy '*' --fail --silent --max-time 3 \
      "${ORIGIN}/api/health" >/dev/null \
      && curl --noproxy '*' --fail --silent --max-time 3 \
      "${ORIGIN}/api/ready" >/dev/null; then
      return
    fi
    if ((attempt == 60)); then
      fail "FastAPI did not become healthy within the bounded wait"
    fi
    sleep 1
  done
}

wait_service_health() {
  local service=$1
  local container_id
  container_id="$("${COMPOSE[@]}" ps -q "${service}")"
  [[ -n "${container_id}" ]] || fail "${service} has no candidate container"
  for attempt in $(seq 1 90); do
    health="$(docker inspect --format \
      '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "${container_id}")"
    if [[ "${health}" == "healthy" || "${health}" == "running" ]]; then
      return
    fi
    if ((attempt == 90)); then
      fail "${service} did not become healthy within the bounded wait"
    fi
    sleep 1
  done
}

start_backend() {
  local mode=$1
  local base_url=${2:-http://java-normalization:8080}
  local barrier=${3:-0}
  CANDIDATE_NORMALIZATION_MODE="${mode}" \
  CANDIDATE_JAVA_BASE_URL="${base_url}" \
  CANDIDATE_PROVIDER_BARRIER="${barrier}" \
    "${COMPOSE[@]}" up --detach --no-deps --force-recreate backend >/dev/null
  wait_backend
}

login() {
  curl --noproxy '*' --fail --silent --show-error \
    --dump-header "${HEADERS}" \
    --cookie-jar "${COOKIE_JAR}" \
    -H 'Content-Type: application/json' \
    --data "$(python3 -c 'import json,os; print(json.dumps({"email":os.environ["CANDIDATE_ADMIN_EMAIL"],"password":os.environ["CANDIDATE_ADMIN_PASSWORD"],"remember_me":True}))')" \
    "${ORIGIN}/api/auth/login" >"${RESPONSE}"
  CSRF_TOKEN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "${RESPONSE}")"
  export CSRF_TOKEN
}

api_json_write() {
  local method=$1
  local path=$2
  local body=${3:-}
  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X "${method}" \
    -H "Origin: ${ORIGIN}" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H 'Content-Type: application/json' \
    --data "${body}" \
    "${ORIGIN}${path}" >"${RESPONSE}"
}

analyze() {
  local request_id=$1
  local key=$2
  local job_file=$3
  local output=$4
  local headers=$5
  curl --noproxy '*' --silent --show-error \
    --dump-header "${headers}" \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -H "Origin: ${ORIGIN}" \
    -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "X-Request-ID: ${request_id}" \
    -H "Idempotency-Key: ${key}" \
    -F "resume_version_id=${VERSION_ID}" \
    -F "job_text=<${job_file}" \
    -F 'save_to_history=true' \
    -F 'use_project_knowledge=true' \
    -F 'project_knowledge_top_k=5' \
    "${ORIGIN}/api/analyze" >"${output}"
}

copy_evidence() {
  local output=$1
  local container_id
  container_id="$("${COMPOSE[@]}" ps -q backend)"
  docker logs "${container_id}" 2>&1 \
    | grep -F '"event":"candidate_' >"${output}" || true
}

sql_scalar() {
  local query=$1
  "${COMPOSE[@]}" exec -T postgres \
    psql -U "${CANDIDATE_POSTGRES_USER}" -d "${CANDIDATE_POSTGRES_DB}" \
    -Atqc "${query}"
}

assert_ledger() {
  local request_id=$1
  local expected=$2
  actual="$(sql_scalar \
    "SELECT status || '|' || normalization_source || '|' ||
            execution_contract_version || '|' || normalization_policy_version || '|' ||
            COALESCE(skill_dictionary_version, 'null') || '|' ||
            (octet_length(execution_fingerprint) = 32)::text || '|' ||
            (execution_bound_at <= provider_started_at)::text
       FROM analyze_idempotency_records
      WHERE request_id = '${request_id}';")"
  [[ "${actual}" == "${expected}" ]] \
    || fail "ledger assertion failed for a synthetic request"
}

json_equal() {
  python3 - "$1" "$2" <<'PY'
import json,sys
with open(sys.argv[1], encoding="utf-8") as left:
    a=json.load(left)
with open(sys.argv[2], encoding="utf-8") as right:
    b=json.load(right)
assert a == b
PY
}

new_token() {
  openssl rand -hex 12
}

start_backend local
login
api_json_write POST /api/project-knowledge/rebuild '{}'
api_json_write POST /api/resumes \
  '{"title":"Synthetic Candidate Resume","language":"en","target_role":"Platform Engineer"}'
RESUME_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE}")"
api_json_write POST "/api/resumes/${RESUME_ID}/versions" \
  '{"content":{"schema_version":1,"header":{},"summary":"Synthetic FastAPI and PostgreSQL candidate evidence.","sections":[]},"change_summary":"Candidate fixture"}'
VERSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE}")"
api_json_write POST "/api/resumes/${RESUME_ID}/versions/${VERSION_ID}/finalize" '{}'

LOCAL_REQUEST="candidate-local-$(new_token)"
LOCAL_KEY="candidate-local-key-$(new_token)"
LOCAL_RESPONSE="${temporary_directory}/local-response.json"
LOCAL_HEADERS="${temporary_directory}/local-headers.txt"
analyze "${LOCAL_REQUEST}" "${LOCAL_KEY}" "${RAW_JOB}" "${LOCAL_RESPONSE}" "${LOCAL_HEADERS}"
python3 "${ASSERTIONS}" response "${LOCAL_RESPONSE}"
assert_ledger "${LOCAL_REQUEST}" \
  "completed|local|analyze-execution-v1|fastapi-local-jd-v1|null|true|true"
copy_evidence "${temporary_directory}/local-evidence.jsonl"
python3 "${ASSERTIONS}" evidence "${temporary_directory}/local-evidence.jsonl" \
  "${LOCAL_REQUEST}" "${LOCAL_JOB}" local fastapi-local-jd-v1 null
LOCAL_HISTORY_COUNT="$(sql_scalar "SELECT count(*) FROM application_records;")"
LOCAL_REPLAY_REQUEST="candidate-local-replay-$(new_token)"
analyze "${LOCAL_REPLAY_REQUEST}" "${LOCAL_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/local-replay.json" "${temporary_directory}/local-replay.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/local-replay.headers" \
  || fail "local completed replay header is absent"
json_equal "${LOCAL_RESPONSE}" "${temporary_directory}/local-replay.json"
[[ "$(sql_scalar "SELECT count(*) FROM application_records;")" == "${LOCAL_HISTORY_COUNT}" ]] \
  || fail "local replay duplicated History"
copy_evidence "${temporary_directory}/local-evidence-after-replay.jsonl"
python3 "${ASSERTIONS}" no-events \
  "${temporary_directory}/local-evidence-after-replay.jsonl" "${LOCAL_REPLAY_REQUEST}"
[[ -z "$("${COMPOSE[@]}" ps -q java-normalization)" ]] \
  || fail "Java was started during local validation"
step "local mode, binding, History, mock-provider count, and completed replay"

"${COMPOSE[@]}" up --detach --no-deps java-normalization >/dev/null
wait_service_health java-normalization
JAVA_CONTAINER="$("${COMPOSE[@]}" ps -q java-normalization)"
SHADOW_REQUEST="candidate-shadow-$(new_token)"
SHADOW_KEY="candidate-shadow-key-$(new_token)"
start_backend shadow
analyze "${SHADOW_REQUEST}" "${SHADOW_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/shadow-response.json" "${temporary_directory}/shadow.headers"
python3 "${ASSERTIONS}" response "${temporary_directory}/shadow-response.json"
assert_ledger "${SHADOW_REQUEST}" \
  "completed|local|analyze-execution-v1|fastapi-local-jd-v1|null|true|true"
copy_evidence "${temporary_directory}/shadow-evidence.jsonl"
python3 "${ASSERTIONS}" evidence "${temporary_directory}/shadow-evidence.jsonl" \
  "${SHADOW_REQUEST}" "${LOCAL_JOB}" local fastapi-local-jd-v1 null
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -F "${SHADOW_REQUEST}" | grep -c 'jd_normalization_completed' || true)" == "1" ]] \
  || fail "shadow mode did not make exactly one real Java request"
SHADOW_HISTORY_COUNT="$(sql_scalar "SELECT count(*) FROM application_records;")"
SHADOW_REPLAY_REQUEST="candidate-shadow-replay-$(new_token)"
analyze "${SHADOW_REPLAY_REQUEST}" "${SHADOW_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/shadow-replay.json" "${temporary_directory}/shadow-replay.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/shadow-replay.headers" \
  || fail "shadow replay header is absent"
[[ "$(sql_scalar "SELECT count(*) FROM application_records;")" == "${SHADOW_HISTORY_COUNT}" ]] \
  || fail "shadow replay duplicated History"
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -F "${SHADOW_REQUEST}" | grep -c 'jd_normalization_completed' || true)" == "1" ]] \
  || fail "shadow replay made an extra Java request"

"${COMPOSE[@]}" stop java-normalization >/dev/null
SHADOW_DOWN_REQUEST="candidate-shadow-down-$(new_token)"
SHADOW_DOWN_KEY="candidate-shadow-down-key-$(new_token)"
analyze "${SHADOW_DOWN_REQUEST}" "${SHADOW_DOWN_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/shadow-down.json" "${temporary_directory}/shadow-down.headers"
python3 "${ASSERTIONS}" response "${temporary_directory}/shadow-down.json"
assert_ledger "${SHADOW_DOWN_REQUEST}" \
  "completed|local|analyze-execution-v1|fastapi-local-jd-v1|null|true|true"
step "shadow sampling, observation-only authority, replay, and non-fatal unavailability"

"${COMPOSE[@]}" start java-normalization >/dev/null
wait_service_health java-normalization
JAVA_CONTAINER="$("${COMPOSE[@]}" ps -q java-normalization)"
JAVA_REQUEST="candidate-java-$(new_token)"
JAVA_KEY="candidate-java-key-$(new_token)"
JAVA_RESPONSE="${temporary_directory}/java-response.json"
start_backend java http://java-normalization:8080 1
analyze "${JAVA_REQUEST}" "${JAVA_KEY}" "${RAW_JOB}" "${JAVA_RESPONSE}" \
  "${temporary_directory}/java.headers" &
analyze_pid=$!
backend_container="$("${COMPOSE[@]}" ps -q backend)"
for attempt in $(seq 1 100); do
  if docker exec "${backend_container}" test -f /tmp/candidate-provider.entered; then
    break
  fi
  if ((attempt == 100)); then
    kill "${analyze_pid}" 2>/dev/null || true
    fail "mock-provider barrier was not reached"
  fi
  sleep 0.1
done
binding_before_provider="$(sql_scalar \
  "SELECT status = 'processing'
          AND normalization_source = 'java'
          AND execution_contract_version = 'analyze-execution-v1'
          AND normalization_policy_version = 'jd-normalization-v1'
          AND skill_dictionary_version = 'skills-v1'
          AND octet_length(execution_fingerprint) = 32
          AND execution_bound_at IS NOT NULL
          AND provider_started_at IS NOT NULL
          AND execution_bound_at <= provider_started_at
          AND history_record_id IS NULL
     FROM analyze_idempotency_records
    WHERE request_id = '${JAVA_REQUEST}';")"
[[ "${binding_before_provider}" == "t" ]] \
  || fail "execution binding was not durable before the paused provider"
docker exec "${backend_container}" touch /tmp/candidate-provider.release
wait "${analyze_pid}"
python3 "${ASSERTIONS}" response "${JAVA_RESPONSE}"
assert_ledger "${JAVA_REQUEST}" \
  "completed|java|analyze-execution-v1|jd-normalization-v1|skills-v1|true|true"
copy_evidence "${temporary_directory}/java-evidence.jsonl"
python3 "${ASSERTIONS}" evidence "${temporary_directory}/java-evidence.jsonl" \
  "${JAVA_REQUEST}" "${LOCAL_JOB}" java jd-normalization-v1 skills-v1
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -F "${JAVA_REQUEST}" | grep -c 'jd_normalization_completed' || true)" == "1" ]] \
  || fail "Java-authoritative mode did not make exactly one real Java request"
history_matches="$(sql_scalar \
  "SELECT (
      a.match_score = (i.response_body->>'match_score')::integer
      AND a.matched_skills::jsonb = (i.response_body->'matched_skills')::jsonb
      AND a.missing_skills::jsonb = (i.response_body->'missing_skills')::jsonb
      AND a.rag_sources::jsonb = (i.response_body->'rag_sources')::jsonb
      AND i.history_record_id = a.id
      AND (i.response_body->>'application_id')::integer = a.id
    )
   FROM analyze_idempotency_records i
   JOIN application_records a ON a.id = i.history_record_id
   WHERE i.request_id = '${JAVA_REQUEST}';")"
[[ "${history_matches}" == "t" ]] || fail "History differs from the derived Java result"
step "real Java authority, sanitized input, Request ID, effective path, and binding barrier"

JAVA_HISTORY_COUNT="$(sql_scalar "SELECT count(*) FROM application_records;")"
JAVA_LOG_COUNT="$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)"
start_backend local
JAVA_REPLAY_LOCAL_REQUEST="candidate-java-replay-local-$(new_token)"
analyze "${JAVA_REPLAY_LOCAL_REQUEST}" "${JAVA_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/java-replay-local.json" "${temporary_directory}/java-replay-local.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/java-replay-local.headers" \
  || fail "Java result replay in local mode is absent"
json_equal "${JAVA_RESPONSE}" "${temporary_directory}/java-replay-local.json"
[[ "$(sql_scalar "SELECT count(*) FROM application_records;")" == "${JAVA_HISTORY_COUNT}" ]] \
  || fail "Java result replay rewrote History"
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)" == "${JAVA_LOG_COUNT}" ]] \
  || fail "Java result replay made a Java request"
copy_evidence "${temporary_directory}/java-replay-local-evidence.jsonl"
python3 "${ASSERTIONS}" no-events \
  "${temporary_directory}/java-replay-local-evidence.jsonl" \
  "${JAVA_REPLAY_LOCAL_REQUEST}"

start_backend java
LOCAL_REPLAY_JAVA_REQUEST="candidate-local-replay-java-$(new_token)"
java_count_before_local_replay="$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)"
analyze "${LOCAL_REPLAY_JAVA_REQUEST}" "${LOCAL_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/local-replay-java.json" "${temporary_directory}/local-replay-java.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/local-replay-java.headers" \
  || fail "local result replay in Java mode is absent"
json_equal "${LOCAL_RESPONSE}" "${temporary_directory}/local-replay-java.json"
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)" == "${java_count_before_local_replay}" ]] \
  || fail "local result replay made a Java request"
[[ "$(sql_scalar "SELECT count(*) FROM application_records;")" == "${JAVA_HISTORY_COUNT}" ]] \
  || fail "local result replay rewrote History"
step "completed replay remains terminal across Java-to-local and local-to-Java changes"

run_fallback() {
  local label=$1
  local base_url=$2
  local request_id
  local key
  request_id="candidate-fb-${label:0:8}-$(new_token)"
  key="candidate-fallback-${label}-key-$(new_token)"
  start_backend java "${base_url}"
  analyze "${request_id}" "${key}" "${RAW_JOB}" \
    "${temporary_directory}/fallback-${label}.json" \
    "${temporary_directory}/fallback-${label}.headers"
  python3 "${ASSERTIONS}" response "${temporary_directory}/fallback-${label}.json"
  assert_ledger "${request_id}" \
    "completed|fallback_local|analyze-execution-v1|fastapi-local-jd-v1|null|true|true"
  copy_evidence "${temporary_directory}/fallback-${label}.evidence"
  python3 "${ASSERTIONS}" evidence \
    "${temporary_directory}/fallback-${label}.evidence" \
    "${request_id}" "${LOCAL_JOB}" fallback_local fastapi-local-jd-v1 null
}

run_fallback unavailable http://java-unavailable:8080
for fault_mode in timeout malformed invalid_version request_id_mismatch second_scan_rejection; do
  CANDIDATE_FAULT_MODE="${fault_mode}" \
    "${COMPOSE[@]}" up --detach --no-deps --force-recreate fault-stub >/dev/null
  wait_service_health fault-stub
  run_fallback "${fault_mode}" http://fault-stub:8081
done
step "unavailable, timeout, malformed, version, Request ID, and authoritative-scan fallback matrix"

"${COMPOSE[@]}" start java-normalization >/dev/null
wait_service_health java-normalization
start_backend java
BLOCKED_JOB="${temporary_directory}/blocked-job.txt"
printf '%s\n' 'Synthetic role' 'SYNTHETIC_API_KEY=abcdefghijklmnop1234567890' \
  >"${BLOCKED_JOB}"
BLOCKED_REQUEST="candidate-blocked-$(new_token)"
BLOCKED_KEY="candidate-blocked-key-$(new_token)"
java_count_before_block="$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)"
blocked_status="$(curl --noproxy '*' --silent --show-error \
  --output "${temporary_directory}/blocked.json" --write-out '%{http_code}' \
  --cookie "${COOKIE_JAR}" \
  -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -H "X-Request-ID: ${BLOCKED_REQUEST}" -H "Idempotency-Key: ${BLOCKED_KEY}" \
  -F "resume_version_id=${VERSION_ID}" -F "job_text=<${BLOCKED_JOB}" \
  -F 'save_to_history=true' -F 'use_project_knowledge=true' \
  "${ORIGIN}/api/analyze")"
[[ "${blocked_status}" == "422" ]] || fail "first security scan did not block"
python3 "${ASSERTIONS}" error "${temporary_directory}/blocked.json" INPUT_SECURITY_BLOCKED
[[ "$(docker logs "${JAVA_CONTAINER}" 2>&1 | grep -c 'jd_normalization_completed' || true)" == "${java_count_before_block}" ]] \
  || fail "blocked first-scan input reached Java"
copy_evidence "${temporary_directory}/blocked-evidence.jsonl"
python3 "${ASSERTIONS}" no-events \
  "${temporary_directory}/blocked-evidence.jsonl" "${BLOCKED_REQUEST}"

port_inventory="$("${COMPOSE[@]}" ps --format json)"
python3 -c '
import json,sys
rows=[json.loads(line) for line in sys.stdin if line.strip()]
for row in rows:
    publishers=[
        item for item in (row.get("Publishers") or [])
        if int(item.get("PublishedPort") or 0) > 0
    ]
    if row["Service"] == "backend":
        assert len(publishers) == 1
        assert publishers[0]["URL"] == "127.0.0.1"
' <<<"${port_inventory}"
for service in java-normalization postgres fault-stub; do
  candidate_id="$("${COMPOSE[@]}" ps -q "${service}")"
  [[ -n "${candidate_id}" ]] || continue
  [[ -z "$(docker port "${candidate_id}")" ]] \
    || fail "${service} unexpectedly publishes a host port"
done
step "security ordering and host-port isolation"

LOCAL_RECORD_ID="$(sql_scalar \
  "SELECT id FROM analyze_idempotency_records WHERE request_id = '${LOCAL_REQUEST}';")"
history_before_conflict="$(sql_scalar "SELECT count(*) FROM application_records;")"
sql_scalar \
  "UPDATE analyze_idempotency_records
      SET status = 'processing',
          response_status = NULL,
          response_body = NULL,
          history_record_id = NULL,
          provider_started_at = NULL,
          lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute',
          completed_at = NULL,
          error_code = NULL,
          attempt_token = '00000000-0000-4000-8000-000000000001'
    WHERE id = '${LOCAL_RECORD_ID}';" >/dev/null
CONFLICT_REQUEST="candidate-conflict-$(new_token)"
conflict_status="$(curl --noproxy '*' --silent --show-error \
  --output "${temporary_directory}/conflict.json" --write-out '%{http_code}' \
  --cookie "${COOKIE_JAR}" \
  -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -H "X-Request-ID: ${CONFLICT_REQUEST}" -H "Idempotency-Key: ${LOCAL_KEY}" \
  -F "resume_version_id=${VERSION_ID}" -F "job_text=<${RAW_JOB}" \
  -F 'save_to_history=true' -F 'use_project_knowledge=true' \
  -F 'project_knowledge_top_k=5' "${ORIGIN}/api/analyze")"
[[ "${conflict_status}" == "409" ]] || fail "execution conflict did not return HTTP 409"
python3 "${ASSERTIONS}" error \
  "${temporary_directory}/conflict.json" IDEMPOTENCY_EXECUTION_CONFLICT
[[ "$(sql_scalar "SELECT count(*) FROM application_records;")" == "${history_before_conflict}" ]] \
  || fail "execution conflict duplicated History"
copy_evidence "${temporary_directory}/conflict-evidence.jsonl"
provider_conflict_count="$(python3 - "${temporary_directory}/conflict-evidence.jsonl" "${CONFLICT_REQUEST}" <<'PY'
import json,sys
count=0
for line in open(sys.argv[1], encoding="utf-8"):
    value=json.loads(line)
    if value.get("request_id") == sys.argv[2] and value.get("event") == "candidate_mock_provider_observation":
        count += 1
print(count)
PY
)"
[[ "${provider_conflict_count}" == "0" ]] \
  || fail "execution conflict reached the provider"
step "isolated SQL takeover fixture demonstrates stable execution conflict"

docker restart "${JAVA_CONTAINER}" >/dev/null
wait_service_health java-normalization
RESTART_REQUEST="candidate-java-restart-$(new_token)"
RESTART_KEY="candidate-java-restart-key-$(new_token)"
start_backend java
analyze "${RESTART_REQUEST}" "${RESTART_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/restart-response.json" "${temporary_directory}/restart.headers"
assert_ledger "${RESTART_REQUEST}" \
  "completed|java|analyze-execution-v1|jd-normalization-v1|skills-v1|true|true"

"${COMPOSE[@]}" restart postgres >/dev/null
wait_service_health postgres
start_backend local
PERSIST_REPLAY_REQUEST="candidate-persistence-replay-$(new_token)"
analyze "${PERSIST_REPLAY_REQUEST}" "${JAVA_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/persistence-replay.json" \
  "${temporary_directory}/persistence-replay.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/persistence-replay.headers" \
  || fail "PostgreSQL restart did not preserve completed response"
json_equal "${JAVA_RESPONSE}" "${temporary_directory}/persistence-replay.json"
"${COMPOSE[@]}" run --rm --no-deps migrate \
  alembic -c alembic.ini upgrade head >/dev/null
step "candidate Java, FastAPI, and PostgreSQL restart/persistence behavior"

"${COMPOSE[@]}" start java-normalization >/dev/null
wait_service_health java-normalization
start_backend java
ANALYZE_DURATIONS="${temporary_directory}/analyze-duration-ms.txt"
JAVA_DURATIONS="${temporary_directory}/java-duration-ms.txt"
: >"${ANALYZE_DURATIONS}"
LOAD_REQUESTS="${temporary_directory}/load-request-ids.txt"
: >"${LOAD_REQUESTS}"
for index in $(seq 1 20); do
  load_request="candidate-sequence-${index}-$(new_token)"
  load_key="candidate-sequence-key-${index}-$(new_token)"
  printf '%s\n' "${load_request}" >>"${LOAD_REQUESTS}"
  duration_seconds="$(curl --noproxy '*' --silent --show-error \
    --output "${temporary_directory}/sequence-${index}.json" \
    --write-out '%{time_total}' \
    --cookie "${COOKIE_JAR}" \
    -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "X-Request-ID: ${load_request}" -H "Idempotency-Key: ${load_key}" \
    -F "resume_version_id=${VERSION_ID}" -F "job_text=<${RAW_JOB}" \
    -F 'save_to_history=false' -F 'use_project_knowledge=true' \
    -F 'project_knowledge_top_k=5' "${ORIGIN}/api/analyze")"
  python3 -c 'import sys; print(round(float(sys.argv[1])*1000,3))' \
    "${duration_seconds}" >>"${ANALYZE_DURATIONS}"
done

backend_logs="${temporary_directory}/backend-sequence.log"
"${COMPOSE[@]}" logs --no-color backend >"${backend_logs}"
python3 - "${backend_logs}" "${LOAD_REQUESTS}" "${JAVA_DURATIONS}" <<'PY'
import json,sys
wanted=set(open(sys.argv[2], encoding="utf-8").read().splitlines())
values={}
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    candidate=line.split(" | ",1)[-1].strip()
    try:
        item=json.loads(candidate)
    except json.JSONDecodeError:
        continue
    if (
        item.get("request_id") in wanted
        and item.get("message") == "jd_normalization_execution_observation"
        and item.get("normalization_source") == "java"
    ):
        values[item["request_id"]]=float(item["duration_ms"])
assert set(values) == wanted
with open(sys.argv[3], "w", encoding="utf-8") as output:
    for request_id in open(sys.argv[2], encoding="utf-8").read().splitlines():
        output.write(f"{values[request_id]}\n")
PY

container_ids=()
for service in backend java-normalization postgres fault-stub; do
  service_id="$("${COMPOSE[@]}" ps -q "${service}")"
  [[ -z "${service_id}" ]] || container_ids+=("${service_id}")
done
docker stats --no-stream --format '{{json .}}' "${container_ids[@]}" \
  >"${temporary_directory}/stats.jsonl"
python3 - "${temporary_directory}/stats.jsonl" "${RESULTS_DIR}/resources.json" \
  "${CANDIDATE_BACKEND_IMAGE}" "${CANDIDATE_JAVA_IMAGE}" \
  "$("${COMPOSE[@]}" ps -q backend)" "$("${COMPOSE[@]}" ps -q java-normalization)" \
  "$("${COMPOSE[@]}" ps -q postgres)" "$("${COMPOSE[@]}" ps -q fault-stub)" <<'PY'
import json,subprocess,sys
stats=[json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
ids={"backend":sys.argv[5],"java":sys.argv[6],"postgres":sys.argv[7],"mock_fault_stub":sys.argv[8]}
states={}
for name,container in ids.items():
    if not container:
        continue
    raw=subprocess.check_output([
        "docker","inspect","--format",
        "{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}|{{.State.Pid}}",
        container,
    ], text=True).strip().split("|")
    states[name]={
        "status":raw[0],
        "restart_count":int(raw[1]),
        "oom_killed":raw[2]=="true",
        "pid":int(raw[3]),
    }
sizes={}
for image in sys.argv[3:5]:
    sizes[image]=int(subprocess.check_output(
        ["docker","image","inspect","--format","{{.Size}}",image], text=True
    ).strip())
value={"docker_stats":stats,"container_states":states,"image_sizes_bytes":sizes}
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(value, output, indent=2, sort_keys=True)
    output.write("\n")
assert all(not state["oom_killed"] for state in states.values())
assert all(state["restart_count"] == 0 for state in states.values())
PY
candidate_volume_bytes="$(sql_scalar \
  "SELECT pg_database_size('${CANDIDATE_POSTGRES_DB}');")"
python3 - "${RESULTS_DIR}/resources.json" "${candidate_volume_bytes}" <<'PY'
import json,sys
path=sys.argv[1]
value=json.load(open(path, encoding="utf-8"))
value["candidate_database_bytes"]=int(sys.argv[2])
with open(path, "w", encoding="utf-8") as output:
    json.dump(value, output, indent=2, sort_keys=True)
    output.write("\n")
PY
python3 "${ASSERTIONS}" durations \
  "${ANALYZE_DURATIONS}" "${JAVA_DURATIONS}" \
  "${RESULTS_DIR}/summary.json" "${RESULTS_DIR}/resources.json"
step "20 sequential synthetic samples and bounded resource observations"

start_backend local
ROLLBACK_REQUEST="candidate-rollback-local-$(new_token)"
ROLLBACK_KEY="candidate-rollback-local-key-$(new_token)"
analyze "${ROLLBACK_REQUEST}" "${ROLLBACK_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/rollback-local.json" "${temporary_directory}/rollback-local.headers"
assert_ledger "${ROLLBACK_REQUEST}" \
  "completed|local|analyze-execution-v1|fastapi-local-jd-v1|null|true|true"
ROLLBACK_REPLAY_REQUEST="candidate-rollback-replay-$(new_token)"
analyze "${ROLLBACK_REPLAY_REQUEST}" "${JAVA_KEY}" "${RAW_JOB}" \
  "${temporary_directory}/rollback-replay.json" "${temporary_directory}/rollback-replay.headers"
grep -qi '^Idempotency-Replayed: true' "${temporary_directory}/rollback-replay.headers" \
  || fail "rollback did not preserve completed Java response"
json_equal "${JAVA_RESPONSE}" "${temporary_directory}/rollback-replay.json"
"${COMPOSE[@]}" stop java-normalization >/dev/null
[[ "$(sql_scalar "SELECT version_num FROM alembic_version;")" == "20260820_08" ]] \
  || fail "rollback unexpectedly changed the database schema"
step "configuration-only rollback to local without rebuild or schema downgrade"

all_candidate_logs="${temporary_directory}/all-candidate.log"
"${COMPOSE[@]}" logs --no-color backend java-normalization fault-stub \
  >"${all_candidate_logs}"
for forbidden_marker in \
  $'Synthetic Cafe\u0301 Platform Engineer' \
  'Contact synthetic candidate team' \
  'SYNTHETIC_API_KEY=abcdefghijklmnop1234567890'; do
  if grep -F -- "${forbidden_marker}" "${all_candidate_logs}" >/dev/null; then
    fail "candidate logs contain synthetic JD text"
  fi
done
for secret_name in \
  CANDIDATE_POSTGRES_PASSWORD CANDIDATE_ADMIN_PASSWORD \
  CANDIDATE_AUTH_FINGERPRINT_KEY CANDIDATE_JAVA_API_KEY \
  CANDIDATE_MOCK_PROVIDER_KEY CANDIDATE_MONITORING_TOKEN; do
  secret_value="${!secret_name}"
  if grep -F -- "${secret_value}" "${all_candidate_logs}" >/dev/null; then
    fail "candidate logs contain generated secret material"
  fi
done
step "bounded logs contain no synthetic JD text or generated secrets"

printf '%s\n' 'candidate: GO - all required isolated candidate cases passed with zero skips'
