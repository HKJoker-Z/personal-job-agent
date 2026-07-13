#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%s)-$$"
SMOKE_MILESTONE="${PJA_SMOKE_MILESTONE:-2.0.1}"
if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  TEST_PREFIX='pja-v2-0-2'
  DEFAULT_HTTP_PORT=18082
  DEFAULT_POSTGRES_PORT=15434
elif [[ "${SMOKE_MILESTONE}" == "2.0.1" ]]; then
  TEST_PREFIX='pja-v2-phase1'
  DEFAULT_HTTP_PORT=18080
  DEFAULT_POSTGRES_PORT=15432
else
  printf '%s\n' 'Refusing to run: unsupported isolated Smoke milestone.' >&2
  exit 1
fi
PROJECT_NAME="${PJA_TEST_PROJECT:-${TEST_PREFIX}-${STAMP}}"
HTTP_PORT="${PJA_TEST_HTTP_PORT:-${DEFAULT_HTTP_PORT}}"
POSTGRES_PORT="${PJA_TEST_POSTGRES_PORT:-${DEFAULT_POSTGRES_PORT}}"
TEST_ROOT="$(mktemp -d "/tmp/${TEST_PREFIX}-${STAMP}.XXXXXX")"
ENV_FILE="${TEST_ROOT}/test.env"
COOKIE_JAR="${TEST_ROOT}/cookies.txt"
RESPONSE_FILE="${TEST_ROOT}/response.json"
ORIGIN="http://127.0.0.1:${HTTP_PORT}"
ADMIN_EMAIL="phase1-admin@example.com"
ADMIN_PASSWORD="Phase-1-Smoke-Passphrase-Only-2026"

valid_project_name() {
  [[ "$1" =~ ^${TEST_PREFIX}-[a-zA-Z0-9_.-]+$ ]]
}

if ! valid_project_name "${PROJECT_NAME}"; then
  printf 'Refusing to run: isolated Compose project must start with %s-.\n' "${TEST_PREFIX}" >&2
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
if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  COMPOSE+=(-f "${ROOT_DIR}/compose.v202-smoke.yaml")
fi

cleanup() {
  local exit_code=$?
  trap - EXIT
  if valid_project_name "${PROJECT_NAME}"; then
    "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
  if [[ "${TEST_ROOT}" == "/tmp/${TEST_PREFIX}-"* ]]; then
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
install -d -m 0700 "${TEST_ROOT}/files" "${TEST_ROOT}/knowledge" "${TEST_ROOT}/backup" "${TEST_ROOT}/mock-job"
install -m 0600 "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md"
python3 - "${TEST_ROOT}/mock-job/job.html" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    '<!doctype html><html><head><title>Mock URL Engineer</title>'
    '<script type="application/ld+json">{"@type":"JobPosting","title":"Mock URL Engineer",'
    '"hiringOrganization":{"name":"Synthetic URL Company"},'
    '"jobLocation":{"address":{"addressLocality":"Mock City","addressCountry":"XX"}}}</script>'
    '</head><body><main><h1>Mock URL Engineer</h1><p>Required: Python and PostgreSQL. Remote.</p></main></body></html>',
    encoding='utf-8',
)
PY
chmod 0755 "${TEST_ROOT}/mock-job"
chmod 0644 "${TEST_ROOT}/mock-job/job.html"
"${DOCKER[@]}" run --rm \
  -v "${TEST_ROOT}:/test-root" \
  alpine:3.21 chown -R 10001:10001 /test-root/files /test-root/knowledge

{
  if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then printf 'APP_ENV=test\n'; else printf 'APP_ENV=development\n'; fi
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
  printf 'MOCK_JOB_DIR=%s\n' "${TEST_ROOT}/mock-job"
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
if [[ "${PJA_SMOKE_SKIP_BUILD:-0}" == "1" ]]; then
  "${COMPOSE[@]}" up --detach --no-build --wait
else
  "${COMPOSE[@]}" up --detach --build --wait
fi

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

if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  api_write POST /api/jobs/import/manual \
    '{"company_name":"Synthetic Manual Company","title":"Platform Engineer","location":"Test City","description":"Required: Python and PostgreSQL. 5 years experience. Remote.","url":"https://jobs.example.test/platform?utm_source=smoke","employment_type":"permanent","work_mode":"remote","salary_min":100,"salary_max":200,"salary_currency":"USD","application_deadline":"2030-01-01T00:00:00Z"}'
  JOB_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["result"] in {"created","duplicate_candidate"}; print(value["job"]["id"])' "${RESPONSE_FILE}")"
  api_write POST /api/jobs/import/manual \
    '{"company_name":"Synthetic Manual Company","title":"Platform Engineer","location":"Test City","description":"Required: Python and PostgreSQL. 5 years experience. Remote.","url":"https://jobs.example.test/platform?utm_source=second","employment_type":"permanent","work_mode":"remote","salary_min":100,"salary_max":200,"salary_currency":"USD","application_deadline":"2030-01-01T00:00:00Z"}'
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["result"] == "existing"' "${RESPONSE_FILE}"
  smoke_step 'manual Job import, normalization, and exact duplicate detection'

  api_write POST /api/jobs/import/url '{"url":"http://mock-job:8085/job.html"}'
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["job"]["title"] == "Mock URL Engineer"; assert value["job"]["company_name"] == "Synthetic URL Company"' "${RESPONSE_FILE}"
  smoke_step 'SSRF-guarded URL import through isolated local Mock HTTP Server'

  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -F "file=@${DOCX_FIXTURE};type=application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
    "${ORIGIN}/api/jobs/import/file" >"${RESPONSE_FILE}"
  JOB_FILE_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["file"]["kind"] == "job_source"; print(value["file"]["id"])' "${RESPONSE_FILE}")"
  smoke_step 'private DOCX Job import and File Asset source link'

  CSV_FIXTURE="${TEST_ROOT}/jobs.csv"
  python3 - "${CSV_FIXTURE}" <<'PY'
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    'company,title,location,description,url,employment_type,work_mode,salary_min,salary_max,salary_currency,application_deadline\n'
    'Synthetic CSV Company,CSV Engineer,Test City,Docker and SQL required.,https://jobs.example.test/csv,permanent,hybrid,90,180,USD,2030-02-01T00:00:00+00:00\n',
    encoding='utf-8',
)
PY
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -F "file=@${CSV_FIXTURE};type=text/csv" \
    "${ORIGIN}/api/jobs/import/csv?validate_only=true" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["validate_only"] is True; assert value["rows"][0]["status"] == "valid"' "${RESPONSE_FILE}"
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -F "file=@${CSV_FIXTURE};type=text/csv" \
    "${ORIGIN}/api/jobs/import/csv?validate_only=false" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["validate_only"] is False; assert value["rows"][0]["status"] in {"created","duplicate_candidate"}' "${RESPONSE_FILE}"
  smoke_step 'CSV validate-only preview and confirmed row import'

  api_write POST "/api/jobs/${JOB_ID}/requirements" \
    '{"category":"skill","requirement_type":"required","name":"Python","evidence_text":"Python","evidence_start":10,"evidence_end":16,"extraction_source":"user","confidence":1,"verification_status":"confirmed"}'
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["verification_status"] == "confirmed"' "${RESPONSE_FILE}"

  api_write POST /api/applications "{\"job_id\":\"${JOB_ID}\"}"
  APPLICATION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["application"]["id"])' "${RESPONSE_FILE}")"
  APPLICATION_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["application"]["revision"])' "${RESPONSE_FILE}")"
  api_write POST "/api/applications/${APPLICATION_ID}/transition" \
    "{\"to_stage\":\"preparing\",\"expected_revision\":${APPLICATION_REVISION},\"reason\":\"Isolated Smoke\"}"
  APPLICATION_REVISION="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["application"]["current_stage"] == "preparing"; print(value["application"]["revision"])' "${RESPONSE_FILE}")"
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/applications/${APPLICATION_ID}/history" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert len(value) == 2; assert value[-1]["to_stage"] == "preparing"' "${RESPONSE_FILE}"
  api_write POST "/api/applications/${APPLICATION_ID}/resume" \
    "{\"resume_version_id\":\"${VERSION_ID}\",\"expected_revision\":${APPLICATION_REVISION}}"
  APPLICATION_REVISION="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["warning"] is None; print(value["application"]["revision"])' "${RESPONSE_FILE}")"
  api_write POST "/api/applications/${APPLICATION_ID}/notes" \
    '{"content":"Synthetic private Smoke note.","note_type":"general"}'
  smoke_step 'Requirement, Application transition/history, Resume Version link, and private Note'

  api_write POST /api/tasks \
    "{\"application_id\":\"${APPLICATION_ID}\",\"title\":\"Prepare synthetic application\",\"task_type\":\"prepare_application\",\"priority\":\"high\"}"
  TASK_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
  TASK_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
  api_write POST "/api/tasks/${TASK_ID}/complete" "{\"expected_revision\":${TASK_REVISION}}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["status"] == "completed"; assert value["completed_at"]' "${RESPONSE_FILE}"
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/dashboard/summary" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["jobs_total"] >= 4; assert value["applications_total"] == 1' "${RESPONSE_FILE}"
  smoke_step 'Task completion and owned Dashboard aggregates'
fi

api_write POST /api/auth/logout
UNAUTH_PATH='/api/jobs'
if [[ "${SMOKE_MILESTONE}" == "2.0.1" ]]; then UNAUTH_PATH='/api/resumes'; fi
UNAUTH_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' "${ORIGIN}${UNAUTH_PATH}")"
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
smoke_step 'login after container restart'
curl --noproxy '*' --fail --silent --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/resumes/${IMPORTED_RESUME_ID}" >"${RESPONSE_FILE}"
smoke_step 'Resume row after container restart'
curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/files/${IMPORTED_FILE_ID}/download" >"${TEST_ROOT}/downloaded-resume.docx"
cmp --silent "${DOCX_FIXTURE}" "${TEST_ROOT}/downloaded-resume.docx"
smoke_step 'private Resume file after container restart'
if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/jobs/${JOB_ID}" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["id"] == sys.argv[2]' "${RESPONSE_FILE}" "${JOB_ID}"
  smoke_step 'Job row after container restart'
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/applications/${APPLICATION_ID}" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["current_stage"] == "preparing"' "${RESPONSE_FILE}"
  smoke_step 'Application row after container restart'
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/tasks/${TASK_ID}" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "completed"' "${RESPONSE_FILE}"
  smoke_step 'Task row after container restart'
fi
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

COUNT_SQL="SELECT (SELECT COUNT(*) FROM users) || ':' || (SELECT COUNT(*) FROM resumes) || ':' || (SELECT COUNT(*) FROM resume_versions) || ':' || (SELECT COUNT(*) FROM file_assets)"
if [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  COUNT_SQL="${COUNT_SQL} || ':' || (SELECT COUNT(*) FROM jobs) || ':' || (SELECT COUNT(*) FROM applications) || ':' || (SELECT COUNT(*) FROM application_tasks)"
fi
SOURCE_COUNTS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap \
  -d personal_job_agent_smoke_test -Atqc "${COUNT_SQL}")"
RESTORED_COUNTS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap \
  -d personal_job_agent_restore_test -Atqc "${COUNT_SQL}")"
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
printf 'Version %s isolated Smoke Test passed. Project: %s\n' "${SMOKE_MILESTONE}" "${PROJECT_NAME}"
