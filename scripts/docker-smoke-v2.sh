#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%s)-$$"
PROJECT_NAME="${PJA_TEST_PROJECT:-pja-v2-phase1-${STAMP}}"
HTTP_PORT="${PJA_TEST_HTTP_PORT:-18080}"
POSTGRES_PORT="${PJA_TEST_POSTGRES_PORT:-15432}"
TEST_ROOT="$(mktemp -d "/tmp/pja-v2-phase1-${STAMP}.XXXXXX")"
ENV_FILE="${TEST_ROOT}/test.env"
COOKIE_JAR="${TEST_ROOT}/cookies.txt"
RESPONSE_FILE="${TEST_ROOT}/response.json"
ORIGIN="http://127.0.0.1:${HTTP_PORT}"
ADMIN_EMAIL="phase1-admin@example.com"
ADMIN_PASSWORD="Phase-1-Smoke-Passphrase-Only-2026"

valid_project_name() {
  [[ "$1" =~ ^pja-v2-phase1-[a-zA-Z0-9_.-]+$ ]]
}

if ! valid_project_name "${PROJECT_NAME}"; then
  printf '%s\n' 'Refusing to run: isolated Compose project must start with pja-v2-phase1-.' >&2
  exit 1
fi

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  printf '%s\n' 'Docker access is required for the isolated smoke test.' >&2
  exit 1
fi

COMPOSE=("${DOCKER[@]}" compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${ROOT_DIR}/compose.yaml" -f "${ROOT_DIR}/compose.test.yaml")

cleanup() {
  local exit_code=$?
  trap - EXIT
  if valid_project_name "${PROJECT_NAME}"; then
    "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  if [[ "${TEST_ROOT}" =~ ^/tmp/pja-v2-phase1- ]]; then
    "${DOCKER[@]}" run --rm -v "${TEST_ROOT}:/cleanup" alpine:3.21 sh -c 'rm -rf /cleanup/*' >/dev/null 2>&1 || true
    rm -rf "${TEST_ROOT}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT

smoke_step() {
  printf 'Smoke passed: %s\n' "$1"
}

umask 077
install -d -m 0700 "${TEST_ROOT}/files" "${TEST_ROOT}/knowledge" "${TEST_ROOT}/backup"
install -m 0600 "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md"
"${DOCKER[@]}" run --rm \
  -v "${TEST_ROOT}:/test-root" \
  alpine:3.21 chown -R 10001:10001 /test-root/files /test-root/knowledge

{
  printf 'APP_ENV=development\n'
  printf 'APP_ENV_FILE=%s\n' "${ENV_FILE}"
  printf 'POSTGRES_DB=personal_job_agent_smoke_test\n'
  printf 'POSTGRES_BOOTSTRAP_USER=pja_bootstrap\n'
  printf 'POSTGRES_BOOTSTRAP_PASSWORD=smoke_bootstrap_password_2026\n'
  printf 'POSTGRES_MIGRATION_USER=pja_migrate\n'
  printf 'POSTGRES_MIGRATION_PASSWORD=smoke_migration_password_2026\n'
  printf 'POSTGRES_APP_USER=pja_app\n'
  printf 'POSTGRES_APP_PASSWORD=smoke_application_password_2026\n'
  printf 'POSTGRES_TEST_PORT=%s\n' "${POSTGRES_PORT}"
  printf 'PUBLIC_HTTP_BIND=127.0.0.1\n'
  printf 'PUBLIC_HTTP_PORT=%s\n' "${HTTP_PORT}"
  printf 'APPLICATION_BRIDGE_NAME=pja2-%s\n' "$(( $$ % 100000 ))"
  printf 'PROJECT_KNOWLEDGE_DIR=%s\n' "${TEST_ROOT}/knowledge"
  printf 'FILE_STORAGE_DIR=%s\n' "${TEST_ROOT}/files"
  printf 'SESSION_COOKIE_SECURE=false\n'
  printf 'AUTH_TRUSTED_ORIGINS=%s\n' "${ORIGIN}"
  printf 'AUTH_FINGERPRINT_KEY=phase1-smoke-fingerprint-key-2026-only\n'
  printf 'AUTH_ENABLED=true\n'
  printf 'TRUSTED_HOSTS=127.0.0.1,localhost\n'
  printf 'ALLOWED_ORIGINS=%s\n' "${ORIGIN}"
  printf 'ENABLE_API_DOCS=false\n'
  printf '%s=%s\n' 'DEEPSEEK_API_KEY' 'TEST_ONLY_NEVER_SENT'
  printf '%s=%s\n' 'MONITORING_ADMIN_TOKEN' 'TEST_ONLY_MONITORING_TOKEN'
} >"${ENV_FILE}"
chmod 0600 "${ENV_FILE}"

"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" up --detach --build --wait

ALEMBIC_HEAD="$("${COMPOSE[@]}" run --rm --no-deps migrate alembic -c alembic.ini heads | sed -n 's/ .*//p')"
ALEMBIC_CURRENT="$("${COMPOSE[@]}" run --rm --no-deps migrate alembic -c alembic.ini current | sed -n 's/ .*//p')"
test -n "${ALEMBIC_HEAD}"
test "${ALEMBIC_CURRENT}" = "${ALEMBIC_HEAD}"
smoke_step 'Alembic fresh upgrade and current=head'

INITIAL_USER_COUNT="$("${COMPOSE[@]}" exec -T database \
  psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc 'SELECT COUNT(*) FROM users')"
test "${INITIAL_USER_COUNT}" = 0
smoke_step 'no default administrator exists'

TEST_DATABASE_URL='postgresql+psycopg://pja_migrate:smoke_migration_password_2026@database:5432/personal_job_agent_smoke_test'
"${COMPOSE[@]}" run --rm --no-deps \
  -e APP_ENV=test \
  -e TEST_DATABASE_URL="${TEST_DATABASE_URL}" \
  -e PJA_TEST_ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
  migrate python -m app.cli users create-admin \
  --email "${ADMIN_EMAIL}" --display-name 'Phase 1 Smoke Admin'
smoke_step 'administrator CLI initialization'

for attempt in $(seq 1 60); do
  if curl --noproxy '*' --fail --silent "${ORIGIN}/api/health" >"${RESPONSE_FILE}" \
    && curl --noproxy '*' --fail --silent "${ORIGIN}/api/ready" >"${RESPONSE_FILE}"; then
    break
  fi
  if [[ "${attempt}" == 60 ]]; then
    "${COMPOSE[@]}" ps
    "${COMPOSE[@]}" logs --no-color backend frontend migrate database | tail -300
    printf '%s\n' 'Timed out waiting for the isolated application.' >&2
    exit 1
  fi
  sleep 2
done

curl --noproxy '*' --fail --silent --show-error \
  --cookie-jar "${COOKIE_JAR}" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
  "${ORIGIN}/api/auth/login" >"${RESPONSE_FILE}"

CSRF_TOKEN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["csrf_token"])' "${RESPONSE_FILE}")"
if [[ -z "${CSRF_TOKEN}" ]]; then
  printf '%s\n' 'Login did not return the in-memory CSRF token.' >&2
  exit 1
fi

MISSING_CSRF_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --cookie "${COOKIE_JAR}" -X PUT -H "Origin: ${ORIGIN}" \
  -H 'Content-Type: application/json' --data '{"revision":1,"headline":"Rejected"}' \
  "${ORIGIN}/api/profile")"
test "${MISSING_CSRF_STATUS}" = 403
WRONG_CSRF_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
  --cookie "${COOKIE_JAR}" -X PUT -H "Origin: ${ORIGIN}" -H 'X-CSRF-Token: invalid' \
  -H 'Content-Type: application/json' --data '{"revision":1,"headline":"Rejected"}' \
  "${ORIGIN}/api/profile")"
test "${WRONG_CSRF_STATUS}" = 403
smoke_step 'login, Session Cookie, and negative CSRF enforcement'

api_write() {
  local method=$1
  local path=$2
  local body=${3:-}
  local arguments=(
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X "${method}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H 'Content-Type: application/json'
  )
  if [[ -n "${body}" ]]; then
    arguments+=(--data "${body}")
  fi
  curl --noproxy '*' --fail --silent --show-error \
    "${arguments[@]}" "${ORIGIN}${path}" >"${RESPONSE_FILE}"
}

api_write POST /api/project-knowledge/rebuild
curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/project-knowledge/search?query=FastAPI&top_k=3" >"${RESPONSE_FILE}"
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["retrieval_method"] == "postgresql_fts"; assert value["items"]' "${RESPONSE_FILE}"
smoke_step 'existing Project Knowledge workflow with PostgreSQL full-text search'

curl --noproxy '*' --fail --silent --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/profile" >"${RESPONSE_FILE}"
PROFILE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"

api_write PUT /api/profile \
  "{\"revision\":${PROFILE_REVISION},\"headline\":\"Phase 1 smoke profile\",\"professional_summary\":\"Deterministic smoke test data.\",\"current_location\":\"Test only\"}"
PROFILE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"

curl --noproxy '*' --fail --silent --show-error \
  --cookie "${COOKIE_JAR}" -X POST -H "Origin: ${ORIGIN}" \
  -H "X-CSRF-Token: ${CSRF_TOKEN}" -H "If-Match: ${PROFILE_REVISION}" \
  -H 'Content-Type: application/json' \
  --data '{"company":"Example Test Company","role_title":"Engineer","is_current":true,"verification_status":"confirmed"}' \
  "${ORIGIN}/api/profile/experiences" >"${RESPONSE_FILE}"
smoke_step 'Career Profile and Experience persistence'

api_write POST /api/resumes \
  '{"title":"Smoke Resume","language":"en","target_role":"Engineer"}'
RESUME_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"

api_write POST "/api/resumes/${RESUME_ID}/versions" \
  '{"content":{"schema_version":1,"header":{},"summary":"Test summary","sections":[]},"change_summary":"Initial smoke version"}'
VERSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
api_write POST "/api/resumes/${RESUME_ID}/versions/${VERSION_ID}/finalize"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "final"' "${RESPONSE_FILE}"
smoke_step 'Resume Library, empty request body, and immutable finalize flow'

DOCX_FIXTURE="${TEST_ROOT}/smoke-resume.docx"
python3 - "${DOCX_FIXTURE}" <<'PY'
import sys, zipfile
path = sys.argv[1]
content_types = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
relationships = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
document = '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Test Candidate</w:t></w:r></w:p><w:p><w:r><w:t>Experience</w:t></w:r></w:p><w:p><w:r><w:t>Deterministic imported resume fixture.</w:t></w:r></w:p><w:sectPr/></w:body></w:document>'
with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('[Content_Types].xml', content_types)
    archive.writestr('_rels/.rels', relationships)
    archive.writestr('word/document.xml', document)
PY

curl --noproxy '*' --fail --silent --show-error \
  --cookie "${COOKIE_JAR}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -F "file=@${DOCX_FIXTURE};type=application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
  "${ORIGIN}/api/resumes/import" >"${RESPONSE_FILE}"
IMPORTED_RESUME_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["resume"]["id"])' "${RESPONSE_FILE}")"
IMPORTED_VERSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"]["id"])' "${RESPONSE_FILE}")"
IMPORTED_FILE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["file"]["id"])' "${RESPONSE_FILE}")"
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["needs_review"] is True; assert value["version"]["status"] == "draft"; assert any(item.get("verification_status") == "needs_review" for section in value["version"]["content"]["sections"] for item in section["items"])' "${RESPONSE_FILE}"
api_write POST /api/resumes/import/confirm \
  "{\"resume_id\":\"${IMPORTED_RESUME_ID}\",\"version_id\":\"${IMPORTED_VERSION_ID}\",\"action\":\"finalize\"}"
python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["version"]["status"] == "final"' "${RESPONSE_FILE}"
smoke_step 'DOCX import review state and JSON request body finalize flow'

api_write POST /api/auth/logout
UNAUTH_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' "${ORIGIN}/api/resumes")"
test "${UNAUTH_STATUS}" = 401

"${COMPOSE[@]}" restart backend frontend >/dev/null
for attempt in $(seq 1 60); do
  if curl --noproxy '*' --fail --silent "${ORIGIN}/api/ready" >/dev/null; then break; fi
  test "${attempt}" != 60
  sleep 2
done

curl --noproxy '*' --fail --silent --show-error \
  --cookie-jar "${COOKIE_JAR}" -H 'Content-Type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}" \
  "${ORIGIN}/api/auth/login" >"${RESPONSE_FILE}"
curl --noproxy '*' --fail --silent --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/resumes/${IMPORTED_RESUME_ID}" >"${RESPONSE_FILE}"
curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/files/${IMPORTED_FILE_ID}/download" >"${TEST_ROOT}/downloaded-resume.docx"
cmp --silent "${DOCX_FIXTURE}" "${TEST_ROOT}/downloaded-resume.docx"
smoke_step 'PostgreSQL and private file persistence across container restart'

SOURCE_URL="postgresql+psycopg://pja_bootstrap:smoke_bootstrap_password_2026@127.0.0.1:${POSTGRES_PORT}/personal_job_agent_smoke_test"
"${COMPOSE[@]}" exec -T database createdb -U pja_bootstrap personal_job_agent_restore_test
RESTORE_URL="postgresql+psycopg://pja_bootstrap:smoke_bootstrap_password_2026@127.0.0.1:${POSTGRES_PORT}/personal_job_agent_restore_test"
sudo -n true
PYTHON_BIN="${PYTHON_BIN:-python3}" \
  DATABASE_URL="${SOURCE_URL}" FILE_STORAGE_ROOT="${TEST_ROOT}/files" \
  PROJECT_KNOWLEDGE_PATH="${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md" \
  sudo -n --preserve-env=PYTHON_BIN,DATABASE_URL,FILE_STORAGE_ROOT,PROJECT_KNOWLEDGE_PATH \
  "${ROOT_DIR}/scripts/backup-v2.sh" --backup-dir "${TEST_ROOT}/backup" \
  --files-root "${TEST_ROOT}/files" \
  --project-knowledge "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md"
mapfile -t BACKUP_PATHS < <(find "${TEST_ROOT}/backup" -mindepth 1 -maxdepth 1 -type d -name 'v2-*' -print)
test "${#BACKUP_PATHS[@]}" = 1
BACKUP_PATH="$(realpath "${BACKUP_PATHS[0]}")"
BACKUP_ROOT="$(realpath "${TEST_ROOT}/backup")"
[[ "${BACKUP_PATH}" == "${BACKUP_ROOT}"/v2-* ]]
[[ "$(basename "${BACKUP_PATH}")" =~ ^v2-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$ ]]
PYTHON_BIN="${PYTHON_BIN:-python3}" \
  sudo -n --preserve-env=PYTHON_BIN "${ROOT_DIR}/scripts/verify-v2-backup.sh" \
  --backup "${BACKUP_PATH}"
smoke_step 'PostgreSQL/file backup manifest and checksum verification'
PYTHON_BIN="${PYTHON_BIN:-python3}" \
  DATABASE_URL="${RESTORE_URL}" FILE_STORAGE_ROOT="${TEST_ROOT}/restored-files" \
  PROJECT_KNOWLEDGE_PATH="${TEST_ROOT}/restored-knowledge/PROJECT_KNOWLEDGE.md" \
  sudo -n --preserve-env=PYTHON_BIN,DATABASE_URL,FILE_STORAGE_ROOT,PROJECT_KNOWLEDGE_PATH \
  "${ROOT_DIR}/scripts/restore-v2.sh" --backup "${BACKUP_PATH}" \
  --files-root "${TEST_ROOT}/restored-files" \
  --project-knowledge "${TEST_ROOT}/restored-knowledge/PROJECT_KNOWLEDGE.md" \
  --confirmation 'RESTORE V2 BACKUP'

SOURCE_COUNTS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap \
  -d personal_job_agent_smoke_test -Atqc \
  "SELECT (SELECT COUNT(*) FROM users) || ':' || (SELECT COUNT(*) FROM resumes) || ':' || (SELECT COUNT(*) FROM resume_versions) || ':' || (SELECT COUNT(*) FROM file_assets)")"
RESTORED_COUNTS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap \
  -d personal_job_agent_restore_test -Atqc \
  "SELECT (SELECT COUNT(*) FROM users) || ':' || (SELECT COUNT(*) FROM resumes) || ':' || (SELECT COUNT(*) FROM resume_versions) || ':' || (SELECT COUNT(*) FROM file_assets)")"
test "${RESTORED_COUNTS}" = "${SOURCE_COUNTS}"
sudo -n python3 - "${TEST_ROOT}/files" "${TEST_ROOT}/restored-files" <<'PY'
import hashlib
import sys
from pathlib import Path

def checksums(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }

assert checksums(Path(sys.argv[1])) == checksums(Path(sys.argv[2]))
PY
sudo -n cmp --silent "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md" \
  "${TEST_ROOT}/restored-knowledge/PROJECT_KNOWLEDGE.md"
smoke_step 'isolated restore row counts and file checksums'

"${COMPOSE[@]}" ps
printf '%s\n' 'Version 2 Phase 1 isolated smoke test passed.'
