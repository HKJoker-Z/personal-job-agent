#!/usr/bin/env bash
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EPHEMERAL_MODE=false

if [[ "${1:-}" == "--ephemeral" ]]; then
  EPHEMERAL_MODE=true
  shift
else
  echo "container-smoke: refusing to run without the explicit --ephemeral flag" >&2
  exit 2
fi

ENV_FILE="${1:-${JD_COMPOSE_ENV_FILE:-${SERVICE_ROOT}/.env.compose}}"
if [[ "${ENV_FILE}" != /* ]]; then
  ENV_FILE="${PWD}/${ENV_FILE}"
fi

fail() {
  echo "container-smoke: $1" >&2
  exit 1
}

for command_name in docker curl jq openssl python3 awk cmp grep sha256sum stat; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "required command is unavailable: ${command_name}"
done

docker compose version >/dev/null 2>&1 \
  || fail "Docker Compose v2 is required"
docker info >/dev/null 2>&1 \
  || fail "the Docker daemon is unavailable"

[[ -f "${ENV_FILE}" ]] || fail "the Compose environment file does not exist"
case "$(stat -c '%a' "${ENV_FILE}")" in
  400|600)
    ;;
  *)
    fail "the Compose environment file must have mode 0400 or 0600"
    ;;
esac

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

required_variables=(
  JD_COMPOSE_API_KEY
  JD_COMPOSE_DB_NAME
  JD_COMPOSE_BOOTSTRAP_DB_USER
  JD_COMPOSE_BOOTSTRAP_DB_PASSWORD
  JD_COMPOSE_MIGRATION_DB_USER
  JD_COMPOSE_MIGRATION_DB_PASSWORD
  JD_COMPOSE_APP_DB_USER
  JD_COMPOSE_APP_DB_PASSWORD
)

for variable_name in "${required_variables[@]}"; do
  [[ -n "${!variable_name:-}" ]] || fail "a required environment value is missing"
  [[ "${!variable_name}" != replace_* ]] \
    || fail "placeholder values are not accepted"
done

[[ "${#JD_COMPOSE_API_KEY}" -ge 32 ]] \
  || fail "the internal API key must contain at least 32 ASCII characters"
for password_name in \
  JD_COMPOSE_BOOTSTRAP_DB_PASSWORD \
  JD_COMPOSE_MIGRATION_DB_PASSWORD \
  JD_COMPOSE_APP_DB_PASSWORD; do
  password_value="${!password_name}"
  [[ "${#password_value}" -ge 24 ]] \
    || fail "database passwords must contain at least 24 ASCII characters"
done
unset password_value

[[ "${JD_COMPOSE_DB_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] \
  || fail "the database name is invalid"
for role_name in \
  "${JD_COMPOSE_BOOTSTRAP_DB_USER}" \
  "${JD_COMPOSE_MIGRATION_DB_USER}" \
  "${JD_COMPOSE_APP_DB_USER}"; do
  [[ "${role_name}" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] \
    || fail "a database role name is invalid"
done
[[ "${JD_COMPOSE_BOOTSTRAP_DB_USER}" != "${JD_COMPOSE_MIGRATION_DB_USER}" ]] \
  || fail "database roles must be distinct"
[[ "${JD_COMPOSE_BOOTSTRAP_DB_USER}" != "${JD_COMPOSE_APP_DB_USER}" ]] \
  || fail "database roles must be distinct"
[[ "${JD_COMPOSE_MIGRATION_DB_USER}" != "${JD_COMPOSE_APP_DB_USER}" ]] \
  || fail "database roles must be distinct"

JD_COMPOSE_HOST_PORT="${JD_COMPOSE_HOST_PORT:-18082}"
[[ "${JD_COMPOSE_HOST_PORT}" =~ ^[0-9]+$ ]] \
  || fail "the host port must be numeric"
((JD_COMPOSE_HOST_PORT >= 1024 && JD_COMPOSE_HOST_PORT <= 65535)) \
  || fail "the host port must be between 1024 and 65535"
[[ "${JD_COMPOSE_HOST_PORT}" != "8080" ]] \
  || fail "the production-facing port 8080 must not be reused"
export JD_COMPOSE_HOST_PORT

cd "${SERVICE_ROOT}"

revision="$(git rev-parse HEAD)"
run_token="$(openssl rand -hex 16)"
project_suffix="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
project_suffix="${project_suffix,,}"
project_suffix="${project_suffix//[^a-z0-9_-]/-}"
PROJECT_NAME="${JD_COMPOSE_PROJECT_NAME:-jd-normalization-smoke-${project_suffix}}"
[[ "${PROJECT_NAME}" =~ ^jd-normalization-smoke-[a-z0-9_-]+$ ]] \
  || fail "the smoke project name is outside the isolated namespace"

export JD_COMPOSE_OCI_REVISION="${revision}"
export JD_COMPOSE_APP_IMAGE="jd-normalization-service:smoke-${project_suffix}"
export JD_COMPOSE_MIGRATION_IMAGE="jd-normalization-migration:smoke-${project_suffix}"

COMPOSE=(
  docker compose
  --project-name "${PROJECT_NAME}"
  --env-file "${ENV_FILE}"
  --file "${SERVICE_ROOT}/compose.yml"
)

temporary_directory="$(mktemp -d)"

redact_logs() {
  python3 -c '
import os
import sys

secret_names = (
    "JD_COMPOSE_API_KEY",
    "JD_COMPOSE_BOOTSTRAP_DB_PASSWORD",
    "JD_COMPOSE_MIGRATION_DB_PASSWORD",
    "JD_COMPOSE_APP_DB_PASSWORD",
)
text = sys.stdin.read()
for name in secret_names:
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
    echo "container-smoke: bounded sanitized failure logs follow" >&2
    "${COMPOSE[@]}" ps --all >&2 || true
    "${COMPOSE[@]}" logs --no-color --tail 80 2>&1 \
      | redact_logs >&2 || true
  fi
  if [[ "${EPHEMERAL_MODE}" == "true" ]]; then
    case "${PROJECT_NAME}" in
      jd-normalization-smoke-*)
        if ! "${COMPOSE[@]}" down \
          --volumes \
          --remove-orphans \
          --timeout 20 >/dev/null 2>&1; then
          echo "container-smoke: isolated cleanup failed" >&2
          exit_status=1
        fi
        ;;
      *)
        echo "container-smoke: refused cleanup outside the smoke namespace" >&2
        exit_status=1
        ;;
    esac
  fi
  rm -rf "${temporary_directory}"
  exit "${exit_status}"
}
trap cleanup EXIT INT TERM

container_id() {
  "${COMPOSE[@]}" ps --all --quiet "$1"
}

wait_for_health() {
  service_name="$1"
  attempts="$2"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    service_container="$(container_id "${service_name}")"
    if [[ -n "${service_container}" ]]; then
      health_status="$(docker inspect \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
        "${service_container}")"
      if [[ "${health_status}" == "healthy" ]]; then
        return 0
      fi
      state_status="$(docker inspect --format '{{.State.Status}}' "${service_container}")"
      [[ "${state_status}" != "exited" ]] \
        || fail "${service_name} exited while health was pending"
    fi
    sleep 1
  done
  fail "${service_name} did not become healthy within the bounded wait"
}

wait_for_readiness() {
  attempts="$1"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    status_code="$(curl \
      --silent \
      --output "${temporary_directory}/readiness.json" \
      --write-out '%{http_code}' \
      --max-time 3 \
      "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/actuator/health/readiness" \
      || true)"
    if [[ "${status_code}" == "200" ]] \
      && jq -e '.status == "UP" and (keys == ["status"])' \
        "${temporary_directory}/readiness.json" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  fail "application readiness did not become available within the bounded wait"
}

header_value() {
  header_name="$1"
  header_file="$2"
  awk -v expected="${header_name}" '
    BEGIN { IGNORECASE = 1 }
    {
      line = $0
      sub(/\r$/, "", line)
      separator = index(line, ":")
      if (separator > 0 && substr(line, 1, separator - 1) == expected) {
        value = substr(line, separator + 1)
        sub(/^[[:space:]]+/, "", value)
        result = value
      }
    }
    END { print result }
  ' "${header_file}"
}

json_equal() {
  left_file="$1"
  right_file="$2"
  jq --sort-keys --compact-output . "${left_file}" \
    >"${temporary_directory}/json-left.canonical"
  jq --sort-keys --compact-output . "${right_file}" \
    >"${temporary_directory}/json-right.canonical"
  cmp --silent \
    "${temporary_directory}/json-left.canonical" \
    "${temporary_directory}/json-right.canonical"
}

database_scalar() {
  sql="$1"
  "${COMPOSE[@]}" exec --no-TTY postgres \
    psql \
      --username "${JD_COMPOSE_BOOTSTRAP_DB_USER}" \
      --dbname "${JD_COMPOSE_DB_NAME}" \
      --tuples-only \
      --no-align \
      --command "${sql}" \
    | tr -d '[:space:]'
}

"${COMPOSE[@]}" config --quiet

if grep -Eiq '^[[:space:]]*(ARG|ENV)[[:space:]].*(API_KEY|PASSWORD|SECRET)' \
  Dockerfile; then
  fail "the Dockerfile contains a secret-bearing ARG or ENV declaration"
fi

DOCKER_BUILDKIT=1 "${COMPOSE[@]}" build --pull app migration

application_image_id="$(docker image inspect \
  --format '{{.Id}}' "${JD_COMPOSE_APP_IMAGE}")"
migration_image_id="$(docker image inspect \
  --format '{{.Id}}' "${JD_COMPOSE_MIGRATION_IMAGE}")"

[[ "$(docker image inspect --format '{{.Config.User}}' \
  "${JD_COMPOSE_APP_IMAGE}")" == "10001:10001" ]] \
  || fail "the application image user is not the dedicated numeric user"
[[ "$(docker image inspect --format '{{.Config.User}}' \
  "${JD_COMPOSE_MIGRATION_IMAGE}")" == "10002:10002" ]] \
  || fail "the migration image user is not the dedicated numeric user"
[[ "$(docker image inspect --format '{{json .Config.ExposedPorts}}' \
  "${JD_COMPOSE_APP_IMAGE}")" == '{"8080/tcp":{}}' ]] \
  || fail "the application image exposes an unexpected port set"
docker image inspect --format '{{json .Config.Healthcheck.Test}}' \
  "${JD_COMPOSE_APP_IMAGE}" \
  | grep -F '/actuator/health/readiness' >/dev/null \
  || fail "the application image health check is not readiness-based"
[[ "$(docker image inspect --format '{{json .Config.Entrypoint}}' \
  "${JD_COMPOSE_APP_IMAGE}")" \
  == '["java","-XX:MaxRAMPercentage=75.0","-Djava.io.tmpdir=/tmp","-jar","/opt/jd-normalization/application.jar"]' ]] \
  || fail "the application image entrypoint is unexpected"
[[ "$(docker image inspect --format '{{json .Config.Entrypoint}}' \
  "${JD_COMPOSE_MIGRATION_IMAGE}")" \
  == '["/usr/local/bin/migrate-and-validate"]' ]] \
  || fail "the migration image entrypoint is unexpected"

docker run \
  --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  --entrypoint /bin/sh \
  "${JD_COMPOSE_APP_IMAGE}" \
  -ceu '
    test "$(id -u)" = "10001"
    test -f /opt/jd-normalization/application.jar
    test "$(find /opt/jd-normalization -mindepth 1 -maxdepth 1 | wc -l)" = "1"
    test ! -e /workspace
    test ! -e /root/.m2
    test ! -e /.git
    test ! -e /.env
    ! command -v mvn >/dev/null
    ! command -v javac >/dev/null
  '

docker run \
  --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
  --entrypoint /bin/sh \
  "${JD_COMPOSE_MIGRATION_IMAGE}" \
  -ceu '
    test "$(id -u)" = "10002"
    test "$(find /flyway/sql -type f | wc -l)" = "2"
    test -f /flyway/sql/V1__create_job_description_schema.sql
    test -f /flyway/sql/V2__create_request_idempotency.sql
    test ! -e /flyway/sql/V3__placeholder.sql
    command -v flyway >/dev/null
  '

host_v1_hash="$(sha256sum \
  src/main/resources/db/migration/V1__create_job_description_schema.sql \
  | awk '{print $1}')"
host_v2_hash="$(sha256sum \
  src/main/resources/db/migration/V2__create_request_idempotency.sql \
  | awk '{print $1}')"
image_v1_hash="$(docker run \
  --rm \
  --read-only \
  --entrypoint sha256sum \
  "${JD_COMPOSE_MIGRATION_IMAGE}" \
  /flyway/sql/V1__create_job_description_schema.sql \
  | awk '{print $1}')"
image_v2_hash="$(docker run \
  --rm \
  --read-only \
  --entrypoint sha256sum \
  "${JD_COMPOSE_MIGRATION_IMAGE}" \
  /flyway/sql/V2__create_request_idempotency.sql \
  | awk '{print $1}')"
[[ "${host_v1_hash}" == "${image_v1_hash}" ]] \
  || fail "migration image V1 differs from the repository"
[[ "${host_v2_hash}" == "${image_v2_hash}" ]] \
  || fail "migration image V2 differs from the repository"

for image_name in "${JD_COMPOSE_APP_IMAGE}" "${JD_COMPOSE_MIGRATION_IMAGE}"; do
  image_metadata="$(docker image inspect "${image_name}")"
  image_history="$(docker history --no-trunc "${image_name}")"
  for secret_name in \
    JD_COMPOSE_API_KEY \
    JD_COMPOSE_BOOTSTRAP_DB_PASSWORD \
    JD_COMPOSE_MIGRATION_DB_PASSWORD \
    JD_COMPOSE_APP_DB_PASSWORD; do
    secret_value="${!secret_name}"
    ! grep -F -- "${secret_value}" <<<"${image_metadata}" >/dev/null \
      || fail "a secret was found in image metadata"
    ! grep -F -- "${secret_value}" <<<"${image_history}" >/dev/null \
      || fail "a secret was found in image history"
  done
  grep -F '"org.opencontainers.image.source": "https://github.com/HKJoker-Z/personal-job-agent"' \
    <<<"${image_metadata}" >/dev/null \
    || fail "the OCI source label is missing"
  grep -F "\"org.opencontainers.image.revision\": \"${revision}\"" \
    <<<"${image_metadata}" >/dev/null \
    || fail "the OCI revision label is missing"
done
unset image_metadata image_history secret_value

"${COMPOSE[@]}" up --detach --no-deps postgres
wait_for_health postgres 90

if ! "${COMPOSE[@]}" up \
  --no-deps \
  --abort-on-container-exit \
  --exit-code-from migration \
  migration >"${temporary_directory}/migration-first.log" 2>&1; then
  fail "the initial migration service failed"
fi

migration_container="$(container_id migration)"
[[ -n "${migration_container}" ]] \
  || fail "the migration container was not created"
[[ "$(docker inspect --format '{{.State.ExitCode}}' \
  "${migration_container}")" == "0" ]] \
  || fail "the migration container did not exit successfully"

"${COMPOSE[@]}" up --detach --no-deps app
wait_for_health app 90
wait_for_readiness 90

liveness_status="$(curl \
  --silent \
  --output "${temporary_directory}/liveness.json" \
  --write-out '%{http_code}' \
  --max-time 3 \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/actuator/health/liveness")"
[[ "${liveness_status}" == "200" ]] \
  || fail "liveness did not return HTTP 200"
jq -e '.status == "UP" and (keys == ["status"])' \
  "${temporary_directory}/liveness.json" >/dev/null \
  || fail "liveness exposed more than status"

normalize_unauthorized_status="$(curl \
  --silent \
  --output /dev/null \
  --write-out '%{http_code}' \
  --max-time 5 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"raw_text":"synthetic unauthorized smoke input"}' \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/api/v1/job-descriptions/normalize")"
[[ "${normalize_unauthorized_status}" == "401" ]] \
  || fail "unauthorized normalize did not return 401"

jq -n \
  --arg suffix "${run_token}" \
  '{
    raw_text: ("Synthetic container smoke " + $suffix + "\nRequired:\n- Java 21\n- PostgreSQL"),
    metadata: {
      title: "Synthetic Container Engineer",
      company: "Local Smoke Only",
      location: "Loopback",
      canonical_url: ("https://smoke.invalid/jobs/" + $suffix)
    }
  }' >"${temporary_directory}/create-request.json"

normalize_authorized_status="$(curl \
  --silent \
  --output "${temporary_directory}/normalize.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --request POST \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/create-request.json" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/api/v1/job-descriptions/normalize")"
[[ "${normalize_authorized_status}" == "200" ]] \
  || fail "authorized normalize did not return 200"
jq -e '.normalization_policy_version == "jd-normalization-v1"' \
  "${temporary_directory}/normalize.json" >/dev/null \
  || fail "normalize returned an unexpected policy"

idempotency_key="smoke-${run_token}"
create_status="$(curl \
  --silent \
  --show-error \
  --dump-header "${temporary_directory}/create.headers" \
  --output "${temporary_directory}/create.json" \
  --write-out '%{http_code}' \
  --max-time 15 \
  --request POST \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  --header "Idempotency-Key: ${idempotency_key}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/create-request.json" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/api/v1/job-descriptions")"
[[ "${create_status}" == "201" ]] \
  || fail "keyed create did not return 201"

resource_id="$(jq -r '.id // empty' "${temporary_directory}/create.json")"
[[ "${resource_id}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$ ]] \
  || fail "create did not return a UUIDv4 resource ID"
create_etag="$(header_value ETag "${temporary_directory}/create.headers")"
create_location="$(header_value Location "${temporary_directory}/create.headers")"
[[ "${create_etag}" == '"0"' ]] \
  || fail "create did not return ETag zero"
[[ "${create_location}" == "/api/v1/job-descriptions/${resource_id}" ]] \
  || fail "create returned an unexpected Location"

replay_status="$(curl \
  --silent \
  --show-error \
  --dump-header "${temporary_directory}/replay.headers" \
  --output "${temporary_directory}/replay.json" \
  --write-out '%{http_code}' \
  --max-time 15 \
  --request POST \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  --header "Idempotency-Key: ${idempotency_key}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/create-request.json" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/api/v1/job-descriptions")"
[[ "${replay_status}" == "${create_status}" ]] \
  || fail "create replay returned a different status"
cmp --silent \
  "${temporary_directory}/create.json" \
  "${temporary_directory}/replay.json" \
  || fail "create replay returned a different body"
[[ "$(header_value Location "${temporary_directory}/replay.headers")" \
  == "${create_location}" ]] \
  || fail "create replay returned a different Location"
[[ "$(header_value ETag "${temporary_directory}/replay.headers")" \
  == "${create_etag}" ]] \
  || fail "create replay returned a different ETag"
[[ "$(header_value Idempotency-Replayed "${temporary_directory}/replay.headers")" \
  == "true" ]] \
  || fail "create replay did not identify the replay"
[[ "$(database_scalar \
  "SELECT count(*) FROM job_descriptions WHERE id = '${resource_id}'::uuid")" == "1" ]] \
  || fail "create replay did not preserve a single aggregate"
[[ "$(database_scalar \
  "SELECT count(*) FROM job_description_versions WHERE job_description_id = '${resource_id}'::uuid")" == "1" ]] \
  || fail "create replay did not preserve one version"

get_status="$(curl \
  --silent \
  --show-error \
  --dump-header "${temporary_directory}/get-before.headers" \
  --output "${temporary_directory}/get-before.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}${create_location}")"
[[ "${get_status}" == "200" ]] \
  || fail "GET after create did not return 200"
json_equal \
  "${temporary_directory}/create.json" \
  "${temporary_directory}/get-before.json" \
  || fail "GET after create did not match the created resource"

jq -n \
  --arg suffix "${run_token}" \
  '{
    raw_text: ("Synthetic updated container smoke " + $suffix + "\nRequired:\n- Java 21\n- PostgreSQL\nPreferred:\n- Docker"),
    metadata: {
      title: "Synthetic Container Platform Engineer",
      company: "Local Smoke Only",
      location: "Loopback",
      canonical_url: ("https://smoke.invalid/jobs/" + $suffix)
    }
  }' >"${temporary_directory}/update-request.json"

update_status="$(curl \
  --silent \
  --show-error \
  --dump-header "${temporary_directory}/update.headers" \
  --output "${temporary_directory}/update.json" \
  --write-out '%{http_code}' \
  --max-time 15 \
  --request PUT \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  --header "If-Match: ${create_etag}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/update-request.json" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}${create_location}")"
[[ "${update_status}" == "200" ]] \
  || fail "conditional PUT did not return 200"
update_etag="$(header_value ETag "${temporary_directory}/update.headers")"
[[ "${update_etag}" == '"1"' ]] \
  || fail "conditional PUT did not advance the ETag"
jq -e '.optimistic_lock_version == 1 and .current_version_number == 2' \
  "${temporary_directory}/update.json" >/dev/null \
  || fail "conditional PUT did not advance to immutable version 2"

stale_status="$(curl \
  --silent \
  --show-error \
  --output "${temporary_directory}/stale.json" \
  --write-out '%{http_code}' \
  --max-time 15 \
  --request PUT \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  --header "If-Match: ${create_etag}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/update-request.json" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}${create_location}")"
[[ "${stale_status}" == "412" ]] \
  || fail "stale conditional PUT did not return 412"
jq -e '.error.code == "PRECONDITION_FAILED" and (.error.details | type == "object")' \
  "${temporary_directory}/stale.json" >/dev/null \
  || fail "stale conditional PUT returned an unstable error"

history_status="$(curl \
  --silent \
  --show-error \
  --output "${temporary_directory}/history.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/api/v1/job-descriptions/${resource_id}/versions")"
[[ "${history_status}" == "200" ]] \
  || fail "version history did not return 200"
jq -e \
  --arg id "${resource_id}" \
  '.job_description_id == $id
    and (.items | length == 2)
    and ([.items[].version_number] | sort == [1, 2])' \
  "${temporary_directory}/history.json" >/dev/null \
  || fail "version history did not contain exactly versions 1 and 2"

"${COMPOSE[@]}" restart --no-deps app >/dev/null
wait_for_health app 90
wait_for_readiness 90

get_after_restart_status="$(curl \
  --silent \
  --show-error \
  --output "${temporary_directory}/get-after-restart.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}${create_location}")"
[[ "${get_after_restart_status}" == "200" ]] \
  || fail "resource was unavailable after application restart"
json_equal \
  "${temporary_directory}/update.json" \
  "${temporary_directory}/get-after-restart.json" \
  || fail "application restart changed the persisted current resource"

migration_count_before="$(database_scalar \
  "SELECT count(*) FROM flyway_schema_history WHERE success")"
[[ "${migration_count_before}" == "2" ]] \
  || fail "the first migration run did not record exactly V1 and V2"
if ! "${COMPOSE[@]}" run \
  --rm \
  --no-deps \
  migration >"${temporary_directory}/migration-rerun.log" 2>&1; then
  fail "the no-op migration rerun or validation failed"
fi
migration_count_after="$(database_scalar \
  "SELECT count(*) FROM flyway_schema_history WHERE success")"
[[ "${migration_count_after}" == "${migration_count_before}" ]] \
  || fail "the migration rerun was not a no-op"

"${COMPOSE[@]}" stop --timeout 20 postgres >/dev/null
readiness_while_database_down="$(curl \
  --silent \
  --output /dev/null \
  --write-out '%{http_code}' \
  --max-time 3 \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/actuator/health/readiness" \
  || true)"
[[ "${readiness_while_database_down}" != "200" ]] \
  || fail "readiness remained available during a PostgreSQL outage"
liveness_while_database_down="$(curl \
  --silent \
  --output "${temporary_directory}/liveness-database-down.json" \
  --write-out '%{http_code}' \
  --max-time 3 \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}/actuator/health/liveness")"
[[ "${liveness_while_database_down}" == "200" ]] \
  || fail "liveness incorrectly failed during a PostgreSQL outage"
jq -e '.status == "UP" and (keys == ["status"])' \
  "${temporary_directory}/liveness-database-down.json" >/dev/null \
  || fail "liveness exposed details during a PostgreSQL outage"

"${COMPOSE[@]}" start postgres >/dev/null
wait_for_health postgres 90
wait_for_health app 90
wait_for_readiness 90

get_after_database_restart_status="$(curl \
  --silent \
  --show-error \
  --output "${temporary_directory}/get-after-database-restart.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --header "Authorization: Bearer ${JD_COMPOSE_API_KEY}" \
  "http://127.0.0.1:${JD_COMPOSE_HOST_PORT}${create_location}")"
[[ "${get_after_database_restart_status}" == "200" ]] \
  || fail "resource was unavailable after PostgreSQL stop/start"
json_equal \
  "${temporary_directory}/update.json" \
  "${temporary_directory}/get-after-database-restart.json" \
  || fail "the named volume did not preserve the current resource"

application_container="$(container_id app)"
postgres_container="$(container_id postgres)"
application_health="$(docker inspect \
  --format '{{.State.Health.Status}}' "${application_container}")"
postgres_health="$(docker inspect \
  --format '{{.State.Health.Status}}' "${postgres_container}")"
application_restart_count="$(docker inspect \
  --format '{{.RestartCount}}' "${application_container}")"
postgres_restart_count="$(docker inspect \
  --format '{{.RestartCount}}' "${postgres_container}")"
[[ "${application_health}" == "healthy" && "${postgres_health}" == "healthy" ]] \
  || fail "final container health is not healthy"
[[ "${application_restart_count}" == "0" && "${postgres_restart_count}" == "0" ]] \
  || fail "a container recorded an unexpected automatic restart"

docker inspect "${application_container}" \
  | jq -e '
      .[0].Config.User == "10001:10001"
      and .[0].HostConfig.ReadonlyRootfs == true
      and (.[0].HostConfig.CapDrop == ["ALL"])
      and (.[0].HostConfig.SecurityOpt | index("no-new-privileges:true") != null)
      and (.[0].HostConfig.Tmpfs["/tmp"] | test("(^|,)size=(64m|65536k|67108864)(,|$)"))
      and .[0].NetworkSettings.Ports["8080/tcp"][0].HostIp == "127.0.0.1"
    ' >/dev/null \
  || fail "the running application container security settings are incomplete"

docker inspect "${postgres_container}" \
  | jq -e '
      any(.[0].Mounts[];
        .Type == "volume"
        and .Destination == "/var/lib/postgresql/data")
      and .[0].HostConfig.PortBindings["5432/tcp"] == null
    ' >/dev/null \
  || fail "PostgreSQL persistence or port isolation is incomplete"

backend_network_id="$(docker inspect \
  --format '{{range $name, $network := .NetworkSettings.Networks}}{{if eq $name "'"${PROJECT_NAME}"'_backend"}}{{$network.NetworkID}}{{end}}{{end}}' \
  "${postgres_container}")"
edge_network_id="$(docker inspect \
  --format '{{range $name, $network := .NetworkSettings.Networks}}{{if eq $name "'"${PROJECT_NAME}"'_edge"}}{{$network.NetworkID}}{{end}}{{end}}' \
  "${application_container}")"
[[ -n "${backend_network_id}" && -n "${edge_network_id}" ]] \
  || fail "the isolated Compose networks are incomplete"
[[ "$(docker network inspect \
  --format '{{.Internal}}' "${backend_network_id}")" == "true" ]] \
  || fail "the database backend network is externally routable"
[[ "$(docker network inspect \
  --format '{{.Internal}} {{.Driver}}' "${edge_network_id}")" == "false bridge" ]] \
  || fail "the loopback publication network is unexpected"
[[ "$(docker inspect \
  --format '{{len .NetworkSettings.Networks}}' "${postgres_container}")" == "1" ]] \
  || fail "PostgreSQL is attached outside the backend network"
[[ "$(docker inspect \
  --format '{{len .NetworkSettings.Networks}}' "${application_container}")" == "2" ]] \
  || fail "the application network boundary is unexpected"

echo "container-smoke: application_image=${application_image_id}"
echo "container-smoke: migration_image=${migration_image_id}"
echo "container-smoke: app_health=${application_health} app_restart_count=${application_restart_count}"
echo "container-smoke: postgres_health=${postgres_health} postgres_restart_count=${postgres_restart_count}"
echo "container-smoke: migration_versions=${migration_count_after} replay=pass update=pass history=pass persistence=pass"
