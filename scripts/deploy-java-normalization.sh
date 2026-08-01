#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SCRIPT_ROOT
readonly COMPOSE_FILE="${SCRIPT_ROOT}/compose.java-normalization.yaml"
readonly COMPOSE_PROJECT="pja-java-normalization"
readonly SERVICE_NAME="java-normalization"
readonly CONTAINER_NAME="pja-java-normalization-java-normalization-1"
readonly NETWORK_NAME="pja-java-normalization-internal"
readonly DEFAULT_SECRET_FILE="/etc/personal-job-agent/java-normalization/api-key"
readonly EXPECTED_REPOSITORY="HKJoker-Z/personal-job-agent"
readonly PROBE_MARKER="pja-stage-iva-synthetic-marker"

operation="${1:-}"
[[ -n "${operation}" ]] || {
  printf '%s\n' 'usage: deploy-java-normalization.sh OPERATION [--image IMAGE@sha256:DIGEST] [--secret-file PATH]' >&2
  exit 2
}
shift

image_ref="${JAVA_NORMALIZATION_IMAGE:-}"
secret_file="${JAVA_NORMALIZATION_SECRET_FILE:-${DEFAULT_SECRET_FILE}}"
temporary_directory=""

fail() {
  printf 'java-normalization: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  exit_status=$?
  trap - EXIT INT TERM
  if [[ -n "${temporary_directory}" && -d "${temporary_directory}" ]]; then
    rm -rf -- "${temporary_directory}"
  fi
  exit "${exit_status}"
}
trap cleanup EXIT INT TERM

while (($#)); do
  case "$1" in
    --image)
      (($# >= 2)) || fail '--image requires a value'
      image_ref="$2"
      shift 2
      ;;
    --secret-file)
      (($# >= 2)) || fail '--secret-file requires a value'
      secret_file="$2"
      shift 2
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

require_commands() {
  local command_name
  for command_name in docker curl jq openssl python3 stat awk grep; do
    command -v "${command_name}" >/dev/null 2>&1 \
      || fail "required command is unavailable: ${command_name}"
  done
  docker info >/dev/null 2>&1 || fail 'Docker is unavailable'
  docker compose version >/dev/null 2>&1 || fail 'Docker Compose is unavailable'
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || fail "${operation} must run as root"
}

validate_image_ref() {
  [[ "${image_ref}" =~ ^ghcr\.io/hkjoker-z/personal-job-agent-java-normalization@sha256:[0-9a-f]{64}$ ]] \
    || fail 'an exact approved GHCR image digest is required'
}

compose() {
  JAVA_NORMALIZATION_IMAGE="${image_ref}" \
  JAVA_NORMALIZATION_SECRET_FILE="${secret_file}" \
  JAVA_NORMALIZATION_NETWORK_NAME="${NETWORK_NAME}" \
    docker compose \
      --project-name "${COMPOSE_PROJECT}" \
      --file "${COMPOSE_FILE}" "$@"
}

validate_compose_scope() {
  local rendered_services
  [[ -f "${COMPOSE_FILE}" ]] || fail 'production Java Compose file is missing'
  rendered_services="$(compose config --services)"
  [[ "${rendered_services}" == "${SERVICE_NAME}" ]] \
    || fail 'Compose contains a service outside the exact Java scope'
  ! compose config | grep -Eq 'published:|host_ip:' \
    || fail 'Compose unexpectedly publishes a host port'
}

validate_network() {
  local network_driver network_internal repository_label purpose_label
  docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1 \
    || fail 'the private Java network does not exist'
  network_driver="$(docker network inspect --format '{{.Driver}}' "${NETWORK_NAME}")"
  network_internal="$(docker network inspect --format '{{.Internal}}' "${NETWORK_NAME}")"
  repository_label="$(docker network inspect --format '{{index .Labels "io.github.hkjokerz.repository"}}' "${NETWORK_NAME}")"
  purpose_label="$(docker network inspect --format '{{index .Labels "io.github.hkjokerz.purpose"}}' "${NETWORK_NAME}")"
  [[ "${network_driver}" == 'bridge' && "${network_internal}" == 'true' ]] \
    || fail 'the Java network is not an internal bridge'
  [[ "${repository_label}" == "${EXPECTED_REPOSITORY}" ]] \
    || fail 'the Java network repository ownership label is unexpected'
  [[ "${purpose_label}" == 'private-java-normalization' ]] \
    || fail 'the Java network purpose label is unexpected'
}

validate_secret() {
  local secret_mode secret_owner secret_group secret_size secret_parent
  [[ "${secret_file}" == /* ]] || fail 'the secret file path must be absolute'
  [[ -f "${secret_file}" && ! -L "${secret_file}" ]] \
    || fail 'the Java API key must be a regular non-symlink file'
  secret_mode="$(stat -c '%a' "${secret_file}")"
  secret_owner="$(stat -c '%u' "${secret_file}")"
  secret_group="$(stat -c '%g' "${secret_file}")"
  secret_size="$(stat -c '%s' "${secret_file}")"
  secret_parent="$(dirname "${secret_file}")"
  [[ "$(stat -c '%u:%g:%a' "${secret_parent}")" == '0:0:700' ]] \
    || fail 'the secret parent directory must be root:root mode 0700'
  [[ "${secret_mode}" == '400' && "${secret_owner}:${secret_group}" == '10001:10001' ]] \
    || fail 'the secret file must be UID/GID 10001 mode 0400 inside the root-controlled directory'
  [[ "${secret_size}" -eq 65 ]] || fail 'the Java API key file has an unexpected length'
  grep -Eq '^[0-9a-f]{64}$' "${secret_file}" \
    || fail 'the Java API key file does not contain one 32-byte hex key'
}

container_id() {
  docker ps --all \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" \
    --filter "label=com.docker.compose.service=${SERVICE_NAME}" \
    --format '{{.ID}}'
}

require_exact_container() {
  local resolved_id resolved_name count
  resolved_id="$(container_id)"
  count="$(grep -c . <<<"${resolved_id}" || true)"
  [[ "${count}" -eq 1 ]] || fail 'expected exactly one Java Compose service container'
  resolved_name="$(docker inspect --format '{{.Name}}' "${resolved_id}")"
  [[ "${resolved_name}" == "/${CONTAINER_NAME}" ]] \
    || fail 'the Java container name is outside the exact project scope'
  printf '%s\n' "${resolved_id}"
}

production_preflight() {
  local backend_name available_kib disk_available_kib version schema unhealthy legacy_state
  date --iso-8601=seconds
  uptime
  free -h
  df -h /
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
  docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}'
  docker system df

  available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  ((available_kib >= 1572864)) \
    || fail 'available memory is below the 1.5 GiB Stage IVA floor'
  disk_available_kib="$(df --output=avail -k / | awk 'NR == 2 {print $1}')"
  ((disk_available_kib >= 6291456)) \
    || fail 'root filesystem has less than 6 GiB available'
  if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    validate_network
  fi

  unhealthy="$(docker ps --filter 'name=personal-job-agent-v2-' --format '{{.Names}}' | while IFS= read -r name; do
    docker inspect --format '{{.Name}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}|{{.State.OOMKilled}}' "${name}"
  done | awk -F'|' '$2 != "running" || $3 != "healthy" || $4 != "0" || $5 != "false" {print}')"
  [[ -z "${unhealthy}" ]] || fail 'an existing Personal Job Agent container is unhealthy, restarted, or OOM-killed'
  [[ "$(docker ps --filter 'name=personal-job-agent-v2-' --format '{{.Names}}' | wc -l)" -eq 7 ]] \
    || fail 'the expected seven Personal Job Agent v2 containers are not running'
  legacy_state="$(docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}|{{.State.OOMKilled}}' job-agent-backend-1 2>/dev/null || true)"
  [[ "${legacy_state}" == 'running|healthy|0|false' ]] \
    || fail 'the existing legacy backend is missing, unhealthy, restarted, or OOM-killed'

  backend_name="$(docker ps --filter 'name=personal-job-agent-v2-backend-1' --format '{{.Names}}')"
  [[ "${backend_name}" == 'personal-job-agent-v2-backend-1' ]] \
    || fail 'the production backend container is missing'
  version="$(docker exec "${backend_name}" python -c 'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/ready",timeout=3))["version"])')"
  [[ "${version}" == '2.0.4' ]] || fail 'production version is not 2.0.4'
  schema="$(docker exec "${backend_name}" python -c 'import os,psycopg; u=os.environ["DATABASE_URL"].replace("postgresql+psycopg://","postgresql://",1); c=psycopg.connect(u); print(c.execute("SELECT version_num FROM alembic_version").fetchone()[0]); c.close()')"
  [[ "${schema}" == '20260724_06' ]] || fail 'production Alembic revision is not 20260724_06'

  docker ps -q | xargs -r docker inspect --format '{{.Name}}|health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|restart={{.RestartCount}}|oom={{.State.OOMKilled}}|configured_image={{.Config.Image}}|image_id={{.Image}}|ports={{json .HostConfig.PortBindings}}'
  docker network ls --format 'table {{.Name}}\t{{.Driver}}\t{{.Scope}}'
  printf 'production_version=%s production_schema=%s\n' "${version}" "${schema}"
}

ensure_network() {
  if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    validate_network
    printf 'network=%s state=existing-valid\n' "${NETWORK_NAME}"
    return
  fi
  docker network create \
    --driver bridge \
    --internal \
    --label "io.github.hkjokerz.repository=${EXPECTED_REPOSITORY}" \
    --label 'io.github.hkjokerz.purpose=private-java-normalization' \
    --label 'io.github.hkjokerz.owner=pja-java-normalization' \
    "${NETWORK_NAME}" >/dev/null
  validate_network
  printf 'network=%s state=created\n' "${NETWORK_NAME}"
}

create_secret() {
  local secret_parent temporary_secret
  if [[ -e "${secret_file}" ]]; then
    validate_secret
    printf 'secret_file=%s state=existing-preserved\n' "${secret_file}"
    return
  fi
  secret_parent="$(dirname "${secret_file}")"
  install -d -o root -g root -m 0700 "${secret_parent}"
  temporary_secret="$(mktemp "${secret_parent}/.api-key.XXXXXX")"
  chmod 0600 "${temporary_secret}"
  openssl rand -hex 32 >"${temporary_secret}"
  chown 10001:10001 "${temporary_secret}"
  chmod 0400 "${temporary_secret}"
  mv -n -- "${temporary_secret}" "${secret_file}"
  validate_secret
  printf 'secret_file=%s state=created\n' "${secret_file}"
}

pull_image() {
  docker pull "${image_ref}" >/dev/null
  docker image inspect --format '{{json .RepoDigests}}' "${image_ref}" \
    | jq -e --arg image "${image_ref}" 'index($image) != null' >/dev/null \
    || fail 'the locally pulled image digest does not match the approved reference'
  [[ "$(docker image inspect --format '{{.Config.User}}' "${image_ref}")" == '10001:10001' ]] \
    || fail 'the image does not declare the dedicated non-root user'
  printf 'image=%s state=pulled-verified\n' "${image_ref}"
}

deploy_service() {
  validate_network
  validate_secret
  validate_compose_scope
  docker image inspect "${image_ref}" >/dev/null 2>&1 \
    || fail 'the approved image digest is not present locally'
  compose up --detach --no-deps --pull never "${SERVICE_NAME}"
  printf 'compose_project=%s service=%s state=deployed\n' "${COMPOSE_PROJECT}" "${SERVICE_NAME}"
}

wait_healthy() {
  local id health state
  id="$(require_exact_container)"
  for ((attempt = 1; attempt <= 75; attempt++)); do
    state="$(docker inspect --format '{{.State.Status}}' "${id}")"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${id}")"
    [[ "${state}" != 'exited' && "${state}" != 'dead' ]] \
      || fail 'Java exited while readiness was pending'
    if [[ "${state}" == 'running' && "${health}" == 'healthy' ]]; then
      return
    fi
    ((attempt < 75)) || fail 'Java did not become healthy within 150 seconds'
    sleep 2
  done
}

probe_base() {
  docker run --rm \
    --network "${NETWORK_NAME}" \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=8m \
    --user 10001:10001 \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --entrypoint curl \
    "${image_ref}" "$@"
}

probe_authorized() {
  local request_id="$1" payload="$2"
  docker run --rm \
    --network "${NETWORK_NAME}" \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=8m \
    --user 10001:10001 \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --mount "type=bind,source=${secret_file},target=/run/pja-secret/api-key,readonly" \
    --entrypoint /bin/sh \
    "${image_ref}" -ec '
      api_key="$(cat /run/pja-secret/api-key)"
      exec curl --silent --show-error --max-time 8 --dump-header - \
        --write-out "\nPJA_STATUS:%{http_code}\n" \
        --request POST \
        --header "Authorization: Bearer ${api_key}" \
        --header "X-Request-ID: $1" \
        --header "Content-Type: application/json" \
        --data-binary "$2" \
        http://java-normalization:8080/api/v1/job-descriptions/normalize
    ' probe "${request_id}" "${payload}"
}

inspect_runtime() {
  local id inspect_file
  id="$(require_exact_container)"
  inspect_file="${temporary_directory}/container-inspect.json"
  docker inspect "${id}" >"${inspect_file}"
  jq -e --arg image "${image_ref}" --arg network "${NETWORK_NAME}" '
    .[0] as $c
    | ($c.Config.Image == $image)
    and ($c.Config.User == "10001:10001")
    and ($c.HostConfig.ReadonlyRootfs == true)
    and (($c.HostConfig.CapDrop | map(ascii_upcase)) == ["ALL"])
    and ($c.HostConfig.SecurityOpt | index("no-new-privileges:true") != null)
    and ($c.HostConfig.Privileged == false)
    and ($c.HostConfig.NetworkMode != "host")
    and ($c.HostConfig.PortBindings == {})
    and ($c.HostConfig.NanoCpus == 500000000)
    and ($c.HostConfig.Memory == 402653184)
    and ($c.HostConfig.MemorySwap == 402653184)
    and ($c.HostConfig.PidsLimit == 128)
    and ($c.HostConfig.RestartPolicy.Name == "on-failure")
    and ($c.HostConfig.RestartPolicy.MaximumRetryCount == 3)
    and (($c.NetworkSettings.Networks | keys) == [$network])
    and ($c.State.Status == "running")
    and ($c.State.Health.Status == "healthy")
    and ($c.RestartCount == 0)
    and ($c.State.OOMKilled == false)
  ' "${inspect_file}" >/dev/null || fail 'Java runtime security, isolation, resource, or health metadata is unexpected'

  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${id}" \
    | cut -d= -f1 >"${temporary_directory}/environment-names.txt"
  ! grep -Eq '^(DATABASE_URL|JD_NORMALIZATION_(JDBC_URL|DB_USERNAME|DB_PASSWORD|FLYWAY_USERNAME|FLYWAY_PASSWORD)|SPRING_DATASOURCE_|SPRING_FLYWAY_)' \
    "${temporary_directory}/environment-names.txt" \
    || fail 'Java unexpectedly has database or Flyway configuration'
}

validate_service() {
  local unauthorized_output authorized_output request_id payload id
  temporary_directory="$(mktemp -d)"
  wait_healthy
  validate_network
  validate_secret
  inspect_runtime

  probe_base --fail --silent --show-error --max-time 3 \
    http://java-normalization:8080/actuator/health/readiness \
    >"${temporary_directory}/readiness.json"
  jq -e '.status == "UP" and (keys == ["status"])' \
    "${temporary_directory}/readiness.json" >/dev/null \
    || fail 'readiness exposed more than the status-only contract'

  payload="{\"raw_text\":\"Synthetic ${PROBE_MARKER} required Java 21 and preferred Docker.\",\"metadata\":{\"title\":\"Synthetic Platform Engineer\",\"company\":\"Synthetic Stage IVA\",\"location\":\"Private Network\"}}"
  probe_base --silent --show-error --max-time 8 \
    --request POST \
    --header 'Content-Type: application/json' \
    --data-binary "${payload}" \
    --write-out '\nPJA_STATUS:%{http_code}\n' \
    http://java-normalization:8080/api/v1/job-descriptions/normalize \
    >"${temporary_directory}/unauthorized.txt"
  unauthorized_output="$(tail -n 1 "${temporary_directory}/unauthorized.txt")"
  [[ "${unauthorized_output}" == 'PJA_STATUS:401' ]] \
    || fail 'unauthenticated normalize did not return 401'
  sed '$d' "${temporary_directory}/unauthorized.txt" >"${temporary_directory}/unauthorized.json"
  jq -e '.error.code == "UNAUTHORIZED" and (.error.details | type == "object")' \
    "${temporary_directory}/unauthorized.json" >/dev/null \
    || fail 'unauthenticated normalize returned an unstable error contract'

  request_id='stage-iva-private-probe:0000000000000001'
  probe_authorized "${request_id}" "${payload}" >"${temporary_directory}/authorized.txt"
  authorized_output="$(tail -n 1 "${temporary_directory}/authorized.txt")"
  [[ "${authorized_output}" == 'PJA_STATUS:200' ]] \
    || fail 'authenticated normalize did not return 200'
  python3 - "${temporary_directory}/authorized.txt" "${temporary_directory}/authorized.json" "${temporary_directory}/authorized.headers" <<'PY'
import pathlib
import sys

raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
headers, body = raw.replace("\r\n", "\n").split("\n\n", 1)
body = body.rsplit("\nPJA_STATUS:", 1)[0]
pathlib.Path(sys.argv[2]).write_text(body, encoding="utf-8")
pathlib.Path(sys.argv[3]).write_text(headers, encoding="utf-8")
PY
  jq -e '
    .normalization_policy_version == "jd-normalization-v1"
    and .skill_dictionary_version == "skills-v1"
    and (.content_hash | test("^[0-9a-f]{64}$"))
  ' "${temporary_directory}/authorized.json" >/dev/null \
    || fail 'authenticated normalize returned an unexpected policy/dictionary contract'
  awk 'BEGIN {IGNORECASE=1} /^X-Request-ID:/ {sub(/\r$/, ""); sub(/^[^:]+:[[:space:]]*/, ""); print}' \
    "${temporary_directory}/authorized.headers" \
    | grep -Fx "${request_id}" >/dev/null \
    || fail 'X-Request-ID was not preserved'

  id="$(require_exact_container)"
  docker logs --since 15m --tail 400 "${id}" >"${temporary_directory}/java.log" 2>&1
  ! grep -Eqi 'jdbc:|HikariPool|Flyway|postgresql|database connection' "${temporary_directory}/java.log" \
    || fail 'Java logs indicate an unexpected database dependency or connection attempt'
  python3 - "${secret_file}" "${temporary_directory}/java.log" "${PROBE_MARKER}" <<'PY'
import pathlib
import sys

secret = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip()
logs = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace")
marker = sys.argv[3]
if secret in logs or marker in logs:
    raise SystemExit("secret or synthetic JD marker found in Java logs")
PY
  printf 'health=healthy restart_count=0 oom_killed=false auth=401/200 request_id=preserved policy=jd-normalization-v1 dictionary=skills-v1\n'
}

synthetic_sequence() {
  local count payload request_id output_file
  temporary_directory="$(mktemp -d)"
  wait_healthy
  for count in $(seq 1 20); do
    request_id="stage-iva-sequence:$(printf '%016d' "${count}")"
    payload="{\"raw_text\":\"Synthetic ${PROBE_MARKER}-${count} required Java 21 and preferred Docker.\"}"
    output_file="${temporary_directory}/normalize-${count}.txt"
    probe_authorized "${request_id}" "${payload}" >"${output_file}"
    [[ "$(tail -n 1 "${output_file}")" == 'PJA_STATUS:200' ]] \
      || fail "synthetic normalize call ${count} failed"
  done
  [[ "$(docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}} {{.State.Health.Status}}' "$(require_exact_container)")" == '0 false healthy' ]] \
    || fail 'Java became unhealthy during the bounded synthetic sequence'
  printf 'synthetic_normalize=20/20 health=healthy restart_count=0 oom_killed=false\n'
}

status_service() {
  local id
  id="$(require_exact_container)"
  docker inspect --format 'name={{.Name}} image={{.Config.Image}} status={{.State.Status}} health={{.State.Health.Status}} restart_count={{.RestartCount}} oom_killed={{.State.OOMKilled}} user={{.Config.User}} readonly={{.HostConfig.ReadonlyRootfs}} ports={{json .HostConfig.PortBindings}} networks={{json .NetworkSettings.Networks}}' "${id}"
  docker stats --no-stream --format 'name={{.Name}} cpu={{.CPUPerc}} memory={{.MemUsage}} pids={{.PIDs}}' "${id}"
}

rollback_check() {
  local id attachment_count
  id="$(require_exact_container)"
  [[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}' "${id}")" == \
    "${COMPOSE_PROJECT}/${SERVICE_NAME}" ]] \
    || fail 'rollback target labels are unexpected'
  attachment_count="$(docker network inspect --format '{{len .Containers}}' "${NETWORK_NAME}")"
  [[ "${attachment_count}" -eq 1 ]] \
    || fail 'rollback network has an unexpected attachment count'
  printf 'rollback_check=valid target=%s/%s network_removal=only-after-zero-attachments\n' \
    "${COMPOSE_PROJECT}" "${SERVICE_NAME}"
}

rollback_service() {
  local attachment_count id
  id="$(require_exact_container)"
  [[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}' "${id}")" == \
    "${COMPOSE_PROJECT}/${SERVICE_NAME}" ]] \
    || fail 'rollback target labels are unexpected'
  compose stop --timeout 20 "${SERVICE_NAME}"
  compose rm --force "${SERVICE_NAME}"
  if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    attachment_count="$(docker network inspect --format '{{len .Containers}}' "${NETWORK_NAME}")"
    if [[ "${attachment_count}" -eq 0 ]]; then
      docker network rm "${NETWORK_NAME}" >/dev/null
    else
      fail 'Java was removed but the private network still has attachments; network preserved'
    fi
  fi
  printf 'rollback=complete project=%s existing_production=unchanged secret=preserved\n' "${COMPOSE_PROJECT}"
}

require_commands
case "${operation}" in
  preflight)
    production_preflight
    ;;
  ensure-network)
    require_root
    ensure_network
    ;;
  create-secret)
    require_root
    create_secret
    ;;
  pull-image)
    require_root
    validate_image_ref
    pull_image
    ;;
  deploy)
    require_root
    validate_image_ref
    deploy_service
    ;;
  validate)
    require_root
    validate_image_ref
    validate_service
    ;;
  synthetic)
    require_root
    validate_image_ref
    synthetic_sequence
    ;;
  status)
    status_service
    ;;
  rollback-check)
    validate_image_ref
    validate_network
    rollback_check
    ;;
  rollback|stop)
    require_root
    validate_image_ref
    validate_compose_scope
    rollback_service
    ;;
  *)
    fail 'operation must be preflight, ensure-network, create-secret, pull-image, deploy, validate, synthetic, status, rollback-check, rollback, or stop'
    ;;
esac
