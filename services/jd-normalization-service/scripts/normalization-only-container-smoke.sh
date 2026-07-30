#!/usr/bin/env bash
set -euo pipefail

SERVICE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" != "--ephemeral" || $# -ne 1 ]]; then
  echo "normalization-only-smoke: refusing to run without the exact --ephemeral flag" >&2
  exit 2
fi

fail() {
  echo "normalization-only-smoke: $1" >&2
  exit 1
}

for command_name in docker curl jq openssl awk grep stat python3; do
  command -v "${command_name}" >/dev/null 2>&1 \
    || fail "required command is unavailable: ${command_name}"
done
docker info >/dev/null 2>&1 \
  || fail "the Docker daemon is unavailable"

cd "${SERVICE_ROOT}"

revision="$(git rev-parse HEAD)"
run_token="$(openssl rand -hex 16)"
smoke_suffix="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
smoke_suffix="${smoke_suffix,,}"
smoke_suffix="${smoke_suffix//[^a-z0-9_-]/-}"
image_name="jd-normalization-service:normalization-only-smoke-${smoke_suffix}"
container_name="jd-normalization-only-smoke-${smoke_suffix}"
network_name="jd-normalization-only-smoke-${smoke_suffix}"

[[ "${container_name}" =~ ^jd-normalization-only-smoke-[a-z0-9_-]+$ ]] \
  || fail "the container name is outside the isolated smoke namespace"
[[ "${network_name}" =~ ^jd-normalization-only-smoke-[a-z0-9_-]+$ ]] \
  || fail "the network name is outside the isolated smoke namespace"

temporary_directory="$(mktemp -d)"
api_key="$(openssl rand -base64 48 | tr -d '\n')"
raw_marker="synthetic-normalization-only-${run_token}"
request_id="normalization-only-smoke:${run_token}"

sanitize_logs() {
  python3 -c '
import os
import sys

text = sys.stdin.read()
for name in ("JD_NORMALIZATION_ONLY_SMOKE_API_KEY", "JD_NORMALIZATION_ONLY_RAW_MARKER"):
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
    echo "normalization-only-smoke: bounded sanitized failure state follows" >&2
    docker inspect \
      --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restart_count={{.RestartCount}} oom_killed={{.State.OOMKilled}}' \
      "${container_name}" >&2 2>/dev/null || true
    docker logs --tail 80 "${container_name}" 2>&1 \
      | sanitize_logs >&2 || true
  fi
  case "${container_name}" in
    jd-normalization-only-smoke-*)
      docker rm --force "${container_name}" >/dev/null 2>&1 || true
      ;;
    *)
      echo "normalization-only-smoke: refused container cleanup outside namespace" >&2
      exit_status=1
      ;;
  esac
  case "${network_name}" in
    jd-normalization-only-smoke-*)
      docker network rm "${network_name}" >/dev/null 2>&1 || true
      ;;
    *)
      echo "normalization-only-smoke: refused network cleanup outside namespace" >&2
      exit_status=1
      ;;
  esac
  rm -rf "${temporary_directory}"
  unset api_key JD_NORMALIZATION_API_KEY
  exit "${exit_status}"
}
trap cleanup EXIT INT TERM

export JD_NORMALIZATION_ONLY_SMOKE_API_KEY="${api_key}"
export JD_NORMALIZATION_ONLY_RAW_MARKER="${raw_marker}"
printf -v JD_NORMALIZATION_API_KEY '%s' "${api_key}"
export JD_NORMALIZATION_API_KEY

DOCKER_BUILDKIT=1 docker build \
  --pull \
  --target application \
  --build-arg "OCI_REVISION=${revision}" \
  --tag "${image_name}" \
  .

image_id="$(docker image inspect --format '{{.Id}}' "${image_name}")"
[[ "${image_id}" =~ ^sha256:[0-9a-f]{64}$ ]] \
  || fail "the application image identifier is invalid"
[[ "$(docker image inspect --format '{{.Config.User}}' "${image_name}")" \
  == "10001:10001" ]] \
  || fail "the application image user is not the dedicated numeric user"
[[ "$(docker image inspect --format '{{json .Config.ExposedPorts}}' \
  "${image_name}")" == '{"8080/tcp":{}}' ]] \
  || fail "the application image exposes an unexpected port set"

docker image inspect "${image_name}" \
  >"${temporary_directory}/image-inspect.json"
docker history --no-trunc "${image_name}" \
  >"${temporary_directory}/image-history.txt"
for image_evidence in \
  "${temporary_directory}/image-inspect.json" \
  "${temporary_directory}/image-history.txt"; do
  ! grep -F -- "${api_key}" "${image_evidence}" >/dev/null \
    || fail "the generated API key was found in image metadata or history"
  ! grep -F -- "${raw_marker}" "${image_evidence}" >/dev/null \
    || fail "synthetic request data was found in image metadata or history"
done

docker network create "${network_name}" >/dev/null
[[ "$(docker network inspect --format '{{.Internal}} {{.Driver}}' \
  "${network_name}")" == "false bridge" ]] \
  || fail "the isolated loopback-validation network is unexpected"

docker run \
  --detach \
  --name "${container_name}" \
  --network "${network_name}" \
  --restart no \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --cpus 0.50 \
  --memory 384m \
  --memory-swap 384m \
  --pids-limit 128 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 127.0.0.1::8080 \
  --env SPRING_PROFILES_ACTIVE=normalization-only \
  --env JD_NORMALIZATION_API_KEY \
  --env "JAVA_TOOL_OPTIONS=-Xms64m -Xmx256m" \
  "${image_name}" >/dev/null

host_binding="$(docker port "${container_name}" 8080/tcp)"
[[ "${host_binding}" =~ ^127\.0\.0\.1:[0-9]+$ ]] \
  || fail "the smoke port is not published only on loopback"
host_port="${host_binding##*:}"

for ((attempt = 1; attempt <= 90; attempt++)); do
  state="$(docker inspect --format '{{.State.Status}}' "${container_name}")"
  [[ "${state}" != "exited" && "${state}" != "dead" ]] \
    || fail "the application exited while readiness was pending"
  health="$(docker inspect \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    "${container_name}")"
  readiness_status="$(curl \
    --silent \
    --output "${temporary_directory}/readiness.json" \
    --write-out '%{http_code}' \
    --max-time 3 \
    "http://127.0.0.1:${host_port}/actuator/health/readiness" \
    || true)"
  if [[ "${health}" == "healthy" && "${readiness_status}" == "200" ]] \
    && jq -e '.status == "UP" and (keys == ["status"])' \
      "${temporary_directory}/readiness.json" >/dev/null; then
    break
  fi
  if ((attempt == 90)); then
    fail "readiness did not become healthy within the bounded wait"
  fi
  sleep 1
done

for health_path in health health/liveness health/readiness; do
  health_status="$(curl \
    --silent \
    --output "${temporary_directory}/${health_path//\//-}.json" \
    --write-out '%{http_code}' \
    --max-time 3 \
    "http://127.0.0.1:${host_port}/actuator/${health_path}")"
  [[ "${health_status}" == "200" ]] \
    || fail "${health_path} did not return HTTP 200"
  jq -e '.status == "UP" and (keys == ["status"])' \
    "${temporary_directory}/${health_path//\//-}.json" >/dev/null \
    || fail "${health_path} exposed more than status"
done

jq -n \
  --arg marker "${raw_marker}" \
  '{
    raw_text: ("Synthetic normalization-only smoke " + $marker
      + "\nRequired:\n- Java 21\nPreferred:\n- Docker"),
    metadata: {
      title: "Synthetic Platform Engineer",
      company: "Local Smoke Only",
      location: "Loopback"
    }
  }' >"${temporary_directory}/normalize-request.json"

unauthorized_status="$(curl \
  --silent \
  --output "${temporary_directory}/unauthorized.json" \
  --write-out '%{http_code}' \
  --max-time 5 \
  --request POST \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/normalize-request.json" \
  "http://127.0.0.1:${host_port}/api/v1/job-descriptions/normalize")"
[[ "${unauthorized_status}" == "401" ]] \
  || fail "unauthenticated normalize did not return 401"
jq -e '.error.code == "UNAUTHORIZED" and (.error.details | type == "object")' \
  "${temporary_directory}/unauthorized.json" >/dev/null \
  || fail "unauthenticated normalize returned an unstable error"
! grep -F -- "${raw_marker}" "${temporary_directory}/unauthorized.json" >/dev/null \
  || fail "the unauthorized response leaked synthetic request data"

authorized_status="$(curl \
  --silent \
  --show-error \
  --dump-header "${temporary_directory}/normalize.headers" \
  --output "${temporary_directory}/normalize.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --request POST \
  --header "Authorization: Bearer ${api_key}" \
  --header "X-Request-ID: ${request_id}" \
  --header 'Content-Type: application/json' \
  --data-binary "@${temporary_directory}/normalize-request.json" \
  "http://127.0.0.1:${host_port}/api/v1/job-descriptions/normalize")"
[[ "${authorized_status}" == "200" ]] \
  || fail "authenticated normalize did not return 200"
jq -e '
    .normalization_policy_version == "jd-normalization-v1"
    and .skill_dictionary_version == "skills-v1"
    and (.content_hash | test("^[0-9a-f]{64}$"))
    and (.required_skills | map(.id) | index("java") != null)
    and (.preferred_skills | map(.id) | index("docker") != null)
  ' "${temporary_directory}/normalize.json" >/dev/null \
  || fail "authenticated normalize returned an unexpected contract"
propagated_request_id="$(awk '
  BEGIN { IGNORECASE = 1 }
  /^X-Request-ID:/ {
    sub(/\r$/, "")
    sub(/^[^:]+:[[:space:]]*/, "")
    result = $0
  }
  END { print result }
' "${temporary_directory}/normalize.headers")"
[[ "${propagated_request_id}" == "${request_id}" ]] \
  || fail "the supplied request ID was not propagated"

persistence_status="$(curl \
  --silent \
  --output "${temporary_directory}/persistence.json" \
  --write-out '%{http_code}' \
  --max-time 5 \
  --header "Authorization: Bearer ${api_key}" \
  "http://127.0.0.1:${host_port}/api/v1/job-descriptions")"
[[ "${persistence_status}" == "404" ]] \
  || fail "a persistence route is exposed"
jq -e '.error.code == "ROUTE_NOT_FOUND"' \
  "${temporary_directory}/persistence.json" >/dev/null \
  || fail "the inactive persistence route did not use safe not-found behavior"

openapi_status="$(curl \
  --silent \
  --output "${temporary_directory}/openapi.json" \
  --write-out '%{http_code}' \
  --max-time 10 \
  --header "Authorization: Bearer ${api_key}" \
  "http://127.0.0.1:${host_port}/v3/api-docs")"
[[ "${openapi_status}" == "200" ]] \
  || fail "authenticated JSON OpenAPI was unavailable"
jq -e '
    (.paths | keys) == ["/api/v1/job-descriptions/normalize"]
    and .paths["/api/v1/job-descriptions/normalize"].post != null
    and .components.securitySchemes.internalApiKey.scheme == "bearer"
    and .components.schemas.ApiErrorResponse != null
  ' "${temporary_directory}/openapi.json" >/dev/null \
  || fail "JSON OpenAPI did not describe only the active normalize API"

swagger_status="$(curl \
  --silent \
  --output "${temporary_directory}/swagger.json" \
  --write-out '%{http_code}' \
  --max-time 5 \
  "http://127.0.0.1:${host_port}/swagger-ui/index.html")"
[[ "${swagger_status}" == "404" ]] \
  || fail "Swagger UI is unexpectedly available"

curl \
  --silent \
  --dump-header "${temporary_directory}/cors.headers" \
  --output /dev/null \
  --max-time 5 \
  --request OPTIONS \
  --header 'Origin: https://browser.example.test' \
  --header 'Access-Control-Request-Method: POST' \
  "http://127.0.0.1:${host_port}/api/v1/job-descriptions/normalize" \
  || true
! grep -Eiq '^Access-Control-Allow-(Origin|Methods):' \
  "${temporary_directory}/cors.headers" \
  || fail "CORS headers were enabled"

docker inspect "${container_name}" \
  >"${temporary_directory}/container-inspect.json"
jq -e '
    .[0].Config.User == "10001:10001"
    and .[0].HostConfig.ReadonlyRootfs == true
    and .[0].HostConfig.CapDrop == ["ALL"]
    and (.[0].HostConfig.SecurityOpt | index("no-new-privileges:true") != null)
    and (.[0].HostConfig.Tmpfs["/tmp"]
      | test("(^|,)size=(64m|65536k|67108864)(,|$)"))
    and .[0].HostConfig.Memory == 402653184
    and .[0].HostConfig.MemorySwap == 402653184
    and .[0].HostConfig.NanoCpus == 500000000
    and .[0].HostConfig.PidsLimit == 128
    and .[0].HostConfig.RestartPolicy.Name == "no"
    and .[0].HostConfig.PortBindings["8080/tcp"][0].HostIp == "127.0.0.1"
    and .[0].State.Running == true
    and .[0].State.OOMKilled == false
    and .[0].State.Health.Status == "healthy"
    and .[0].RestartCount == 0
    and (.[0].Config.Env | index("SPRING_PROFILES_ACTIVE=normalization-only") != null)
    and (.[0].Config.Env | index("JAVA_TOOL_OPTIONS=-Xms64m -Xmx256m") != null)
    and (.[0].Config.Env | all(.[];
      (startswith("JD_NORMALIZATION_JDBC_URL" + "=")
        or startswith("JD_NORMALIZATION_DB_USERNAME" + "=")
        or startswith("JD_NORMALIZATION_DB_PASSWORD" + "=")
        or startswith("JD_NORMALIZATION_FLYWAY_USERNAME" + "=")
        or startswith("JD_NORMALIZATION_FLYWAY_PASSWORD" + "=")) | not))
  ' "${temporary_directory}/container-inspect.json" >/dev/null \
  || fail "container security, resources, state, or database isolation is incomplete"

network_container_count="$(docker network inspect \
  --format '{{len .Containers}}' "${network_name}")"
[[ "${network_container_count}" == "1" ]] \
  || fail "the isolated network contains an unexpected container"
network_container_name="$(docker network inspect "${network_name}" \
  | jq -r '.[0].Containers | to_entries[0].value.Name')"
[[ "${network_container_name}" == "${container_name}" ]] \
  || fail "a database or unrelated container joined the isolated network"

docker logs "${container_name}" \
  >"${temporary_directory}/application.log" 2>&1
! grep -F -- "${api_key}" "${temporary_directory}/application.log" >/dev/null \
  || fail "the generated API key appeared in application logs"
! grep -F -- "${raw_marker}" "${temporary_directory}/application.log" >/dev/null \
  || fail "synthetic request data appeared in application logs"
if grep -Eiq \
  'jdbc:postgresql|HikariPool|com\.zaxxer\.hikari|org\.flywaydb|Flyway migration|org\.hibernate\.orm|HHH[0-9]+|database_unavailable|PSQLException|Unable to obtain connection' \
  "${temporary_directory}/application.log"; then
  fail "application logs contain a database, JPA, or migration startup attempt"
fi

memory_point_in_time="$(docker stats \
  --no-stream \
  --format '{{.MemUsage}}' \
  "${container_name}")"
[[ "${memory_point_in_time}" == *"/ 384MiB" ]] \
  || fail "the point-in-time memory evidence does not show the enforced limit"

final_health="$(docker inspect --format '{{.State.Health.Status}}' \
  "${container_name}")"
final_restart_count="$(docker inspect --format '{{.RestartCount}}' \
  "${container_name}")"
final_oom_killed="$(docker inspect --format '{{.State.OOMKilled}}' \
  "${container_name}")"
[[ "${final_health}" == "healthy" ]] \
  || fail "the final application health is not healthy"
[[ "${final_restart_count}" == "0" ]] \
  || fail "the application container restarted"
[[ "${final_oom_killed}" == "false" ]] \
  || fail "the application container was OOM-killed"

echo "normalization-only-smoke: application_image=${image_id}"
echo "normalization-only-smoke: health=${final_health} restart_count=${final_restart_count} oom_killed=${final_oom_killed}"
echo "normalization-only-smoke: memory_point_in_time=${memory_point_in_time}"
echo "normalization-only-smoke: database_containers=0 persistence_route=absent openapi=normalize-only"
