#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%s)-$$"
SMOKE_MILESTONE="${PJA_SMOKE_MILESTONE:-2.0.1}"
REAL_LLM_VALIDATION="${PJA_REAL_LLM_VALIDATION:-0}"
if [[ "${REAL_LLM_VALIDATION}" != "0" && "${REAL_LLM_VALIDATION}" != "1" ]]; then
  printf '%s\n' 'PJA_REAL_LLM_VALIDATION must be 0 or 1.' >&2
  exit 1
fi
if [[ "${REAL_LLM_VALIDATION}" == "1" && -z "${PJA_REAL_DEEPSEEK_API_KEY:-}" ]]; then
  printf '%s\n' 'Controlled DeepSeek validation requires an explicitly supplied API key.' >&2
  exit 1
fi
V202_SCOPE=0
V203_SCOPE=0
V204_SCOPE=0
if [[ "${SMOKE_MILESTONE}" == "2.0.4" ]]; then
  TEST_PREFIX='pja-v2-final'
  DEFAULT_HTTP_PORT=18088
  DEFAULT_POSTGRES_PORT=15438
  V202_SCOPE=1
  V203_SCOPE=1
  V204_SCOPE=1
elif [[ "${SMOKE_MILESTONE}" == "2.0.3" ]]; then
  TEST_PREFIX='pja-v2-0-3'
  DEFAULT_HTTP_PORT=18083
  DEFAULT_POSTGRES_PORT=15435
  V202_SCOPE=1
  V203_SCOPE=1
elif [[ "${SMOKE_MILESTONE}" == "2.0.2" ]]; then
  TEST_PREFIX='pja-v2-0-2'
  DEFAULT_HTTP_PORT=18082
  DEFAULT_POSTGRES_PORT=15434
  V202_SCOPE=1
elif [[ "${SMOKE_MILESTONE}" == "2.0.1" ]]; then
  TEST_PREFIX='pja-v2-0-1'
  DEFAULT_HTTP_PORT=18089
  DEFAULT_POSTGRES_PORT=15439
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
HEADER_FILE="${TEST_ROOT}/headers.txt"
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
if [[ "${V202_SCOPE}" == "1" ]]; then
  COMPOSE+=(-f "${ROOT_DIR}/compose.v202-smoke.yaml")
fi

cleanup() {
  local exit_code=$?
  trap - EXIT
  if valid_project_name "${PROJECT_NAME}"; then
    if [[ "${exit_code}" != 0 ]]; then
      "${COMPOSE[@]}" ps >&2 || true
      "${COMPOSE[@]}" logs --no-color --tail=200 \
        database redis backup-before-migrate migrate worker backend frontend >&2 || true
    fi
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
install -d -m 0700 "${TEST_ROOT}/files" "${TEST_ROOT}/knowledge" "${TEST_ROOT}/backup" \
  "${TEST_ROOT}/verified-backup" "${TEST_ROOT}/mock-job"
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
  alpine:3.21 chown -R 10001:10001 /test-root/files /test-root/knowledge /test-root/backup \
  /test-root/mock-job

{
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    printf 'APP_ENV=development\n'
    printf 'PJA_COMPOSE_APP_ENV=development\n'
  elif [[ "${V202_SCOPE}" == "1" ]]; then
    printf 'APP_ENV=test\n'
    printf 'PJA_COMPOSE_APP_ENV=test\n'
  else
    printf 'APP_ENV=development\n'
    printf 'PJA_COMPOSE_APP_ENV=development\n'
  fi
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
  printf 'BACKUP_DIR=%s\n' "${TEST_ROOT}/backup"
  printf 'MOCK_JOB_DIR=%s\n' "${TEST_ROOT}/mock-job"
  printf 'SESSION_COOKIE_SECURE=false\n'
  printf 'REMEMBER_ME_SESSION_TTL_DAYS=30\n'
  printf 'APP_VERSION=2.0.1\n'
  printf 'AUTH_TRUSTED_ORIGINS=%s\n' "${ORIGIN}"
  printf 'AUTH_FINGERPRINT_KEY=phase1-smoke-fingerprint-key-2026-only\n'
  printf 'AUTH_ENABLED=true\n'
  printf 'TRUSTED_HOSTS=127.0.0.1,localhost\n'
  printf 'ALLOWED_ORIGINS=%s\n' "${ORIGIN}"
  printf 'ENABLE_API_DOCS=false\n'
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    printf '%s=%s\n' 'DEEPSEEK_API_KEY' "${PJA_REAL_DEEPSEEK_API_KEY}"
    printf 'AGENT_MODEL_MAX_OUTPUT_TOKENS=800\n'
    printf 'MODEL_INPUT_COST_PER_MILLION_USD=1\n'
    printf 'MODEL_OUTPUT_COST_PER_MILLION_USD=1\n'
  else
    printf '%s=%s\n' 'DEEPSEEK_API_KEY' 'TEST_ONLY_NEVER_SENT'
    printf 'MOCK_PROVIDER_ENABLED=true\n'
  fi
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

"${ROOT_DIR}/scripts/assert-release-health.sh" "${ORIGIN}/api/health" 2.0.1 >/dev/null
smoke_step 'health version equals the target release'

curl --noproxy '*' --fail --silent --show-error \
  --dump-header "${HEADER_FILE}" \
  --cookie-jar "${COOKIE_JAR}" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\",\"remember_me\":true}" \
  "${ORIGIN}/api/auth/login" >"${RESPONSE_FILE}"

grep -qi '^set-cookie: pja_session=' "${HEADER_FILE}"
grep -qi '^set-cookie: pja_session=.*HttpOnly' "${HEADER_FILE}"
grep -qi '^set-cookie: pja_session=.*Max-Age=2592000' "${HEADER_FILE}"
grep -qi '^set-cookie: pja_session=.*SameSite=lax' "${HEADER_FILE}"

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
smoke_step 'Remember Me, opaque HttpOnly Session Cookie, and negative CSRF enforcement'

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

for removed_path in /api/jobs /api/applications /api/approvals /api/tasks /api/job-rank-runs; do
  REMOVED_GET_STATUS="$(curl --noproxy '*' --silent --output "${RESPONSE_FILE}" --write-out '%{http_code}' \
    --cookie "${COOKIE_JAR}" "${ORIGIN}${removed_path}")"
  test "${REMOVED_GET_STATUS}" = 410
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["error"]["code"] == "FEATURE_REMOVED"' "${RESPONSE_FILE}"
  REMOVED_POST_STATUS="$(curl --noproxy '*' --silent --output "${RESPONSE_FILE}" --write-out '%{http_code}' \
    --cookie "${COOKIE_JAR}" -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H 'Content-Type: application/json' --data '{}' "${ORIGIN}${removed_path}")"
  test "${REMOVED_POST_STATUS}" = 410
done
smoke_step 'retired routes and mutations return the uniform Feature Removed response'

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

curl --noproxy '*' --fail --silent --show-error \
  --cookie "${COOKIE_JAR}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -F "resume_version_id=${VERSION_ID}" \
  -F 'job_text=Synthetic role requiring FastAPI PostgreSQL RAG and Redis.' \
  -F 'save_to_history=false' -F 'use_project_knowledge=false' -F 'project_knowledge_top_k=5' \
  "${ORIGIN}/api/analyze" >"${RESPONSE_FILE}"
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["used_knowledge_base"] is False; assert value["retrieval_count"] == 0; assert value["rag_sources"] == []' "${RESPONSE_FILE}"
smoke_step 'direct Resume-to-JD Analyze with Project Knowledge disabled'

curl --noproxy '*' --fail --silent --show-error \
  --cookie "${COOKIE_JAR}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
  -F "resume_version_id=${VERSION_ID}" \
  -F 'job_text=Synthetic role requiring FastAPI PostgreSQL RAG and Redis.' \
  -F 'save_to_history=true' -F 'use_project_knowledge=true' -F 'project_knowledge_top_k=5' \
  "${ORIGIN}/api/analyze" >"${RESPONSE_FILE}"
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["used_knowledge_base"] is True; assert 1 <= value["retrieval_count"] <= 5; assert value["rag_sources"]; assert all(set(item) == {"document","section","chunk_id","relevance_score","supported_skills"} for item in value["rag_sources"]); assert any(item["source"] == "project_knowledge" for item in value["evidence_mapping"]); assert not (set(value["matched_skills"]) & set(value["missing_skills"])); assert value["claim_validation"]["unsupported_claim_count"] == 0' "${RESPONSE_FILE}"
HISTORY_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["application_id"])' "${RESPONSE_FILE}")"
curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
  "${ORIGIN}/api/history/${HISTORY_ID}" >"${RESPONSE_FILE}"
python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["id"] == int(sys.argv[2]); assert value["rag_sources"]' "${RESPONSE_FILE}" "${HISTORY_ID}"
smoke_step 'Project Knowledge RAG changes matching with safe sources, evidence mapping, grounding, and History persistence'

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

if [[ "${V202_SCOPE}" == "1" ]]; then
  api_write POST /api/jobs/import/manual \
    '{"company_name":"Synthetic Manual Company","title":"Platform Engineer","location":"Test City","description":"Required: Python and PostgreSQL. 5 years experience. Remote.","url":"https://jobs.example.test/platform?utm_source=smoke","employment_type":"permanent","work_mode":"remote","salary_min":100,"salary_max":200,"salary_currency":"USD","application_deadline":"2030-01-01T00:00:00Z"}'
  JOB_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["result"] in {"created","duplicate_candidate"}; print(value["job"]["id"])' "${RESPONSE_FILE}")"
  api_write POST /api/jobs/import/manual \
    '{"company_name":"Synthetic Manual Company","title":"Platform Engineer","location":"Test City","description":"Required: Python and PostgreSQL. 5 years experience. Remote.","url":"https://jobs.example.test/platform?utm_source=second","employment_type":"permanent","work_mode":"remote","salary_min":100,"salary_max":200,"salary_currency":"USD","application_deadline":"2030-01-01T00:00:00Z"}'
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["result"] == "existing"' "${RESPONSE_FILE}"
  smoke_step 'manual Job import, normalization, and exact duplicate detection'

  if [[ "${REAL_LLM_VALIDATION}" == "0" ]]; then
    api_write POST /api/jobs/import/url '{"url":"http://mock-job:8085/job.html"}'
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["job"]["title"] == "Mock URL Engineer"; assert value["job"]["company_name"] == "Synthetic URL Company"' "${RESPONSE_FILE}"
    smoke_step 'SSRF-guarded URL import through isolated local Mock HTTP Server'
  fi

  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -F "file=@${DOCX_FIXTURE};type=application/vnd.openxmlformats-officedocument.wordprocessingml.document" \
    "${ORIGIN}/api/jobs/import/file" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["file"]["kind"] == "job_source"; assert value["file"]["id"]' "${RESPONSE_FILE}"
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
  MINIMUM_JOB_COUNT=4
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then MINIMUM_JOB_COUNT=3; fi
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["jobs_total"] >= int(sys.argv[2]); assert value["applications_total"] == 1' \
    "${RESPONSE_FILE}" "${MINIMUM_JOB_COUNT}"
  smoke_step 'Task completion and owned Dashboard aggregates'
fi

if [[ "${V203_SCOPE}" == "1" ]]; then
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/profile" >"${RESPONSE_FILE}"
  PROFILE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "If-Match: ${PROFILE_REVISION}" -H 'Content-Type: application/json' \
    --data '{"name":"Python","years_experience":6,"verification_status":"confirmed"}' \
    "${ORIGIN}/api/profile/skills" >"${RESPONSE_FILE}"
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/profile" >"${RESPONSE_FILE}"
  PROFILE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X PUT -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "If-Match: ${PROFILE_REVISION}" -H 'Content-Type: application/json' \
    --data '{"target_roles":["Platform Engineer"],"target_locations":["Test City"],"employment_types":["permanent"],"work_modes":["remote"],"work_authorization":"Authorized to work in Testland","sponsorship_required":false}' \
    "${ORIGIN}/api/profile/preferences" >"${RESPONSE_FILE}"
  smoke_step 'confirmed Profile facts for deterministic matching'

  api_write POST "/api/jobs/${JOB_ID}/requirements" \
    '{"category":"work_authorization","requirement_type":"hard_filter","name":"Authorized to work in Testland","extraction_source":"user","confidence":1,"verification_status":"confirmed"}'
  api_write POST "/api/jobs/${JOB_ID}/match" "{\"resume_version_id\":\"${VERSION_ID}\"}"
  MATCH_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert 0 <= value["overall_score"] <= 100; assert value["hard_filter_status"] == "passed"; assert len(value["dimensions"]) == 8; print(value["id"])' "${RESPONSE_FILE}")"
  api_write POST /api/jobs/rank "{\"job_ids\":[\"${JOB_ID}\"],\"resume_version_id\":\"${VERSION_ID}\"}"
  RANK_RUN_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["job_count"] == 1; assert value["items"][0]["hard_filter_status"] == "passed"; print(value["id"])' "${RESPONSE_FILE}")"
  smoke_step 'deterministic Match, hard filter, and reproducible Job Ranking'

  if [[ "${REAL_LLM_VALIDATION}" == "0" ]]; then
    api_write POST "/api/applications/${APPLICATION_ID}/packages" \
      "{\"source_resume_version_id\":\"${VERSION_ID}\",\"match_analysis_id\":\"${MATCH_ID}\",\"title\":\"Synthetic Smoke Package\"}"
    PACKAGE_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["status"] == "draft"; print(value["id"])' "${RESPONSE_FILE}")"
    api_write POST "/api/application-packages/${PACKAGE_ID}/generate-resume" '{}'
    RESUME_MATERIAL_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["material_id"])' "${RESPONSE_FILE}")"
    GENERATED_RESUME_VERSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
    api_write POST "/api/application-packages/${PACKAGE_ID}/generate-cover-letter" '{}'
    COVER_VERSION_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["validation_status"] == "valid"; print(value["id"])' "${RESPONSE_FILE}")"
    api_write POST "/api/application-packages/${PACKAGE_ID}/answers" \
      '{"questions":[{"key":"role","question":"Why are you interested in this role?"},{"key":"authorization","question":"What is your work authorization?"}]}'
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert len(value) == 2; assert all(item["validation_status"] in {"valid","needs_user_input"} for item in value)' "${RESPONSE_FILE}"
    smoke_step 'Application Package and grounded Resume, Cover Letter, and Answer drafts'

    api_write POST "/api/application-materials/${RESUME_MATERIAL_ID}/versions" \
      "{\"expected_active_version_id\":\"${GENERATED_RESUME_VERSION_ID}\",\"content_json\":{},\"content_text\":\"Led a team of 20 and increased revenue by 75% using Kubernetes.\",\"change_summary\":\"Synthetic unsupported claim test\"}"
    UNSUPPORTED_VERSION_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["unsupported_claim_count"] > 0; print(value["id"])' "${RESPONSE_FILE}")"
    BLOCKED_FINALIZE_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' \
      --cookie "${COOKIE_JAR}" -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
      -H 'Content-Type: application/json' --data '{"confirmation":"FINALIZE MATERIAL"}' \
      "${ORIGIN}/api/material-versions/${UNSUPPORTED_VERSION_ID}/finalize")"
    test "${BLOCKED_FINALIZE_STATUS}" = 409
    api_write POST "/api/application-materials/${RESUME_MATERIAL_ID}/versions" \
      "{\"expected_active_version_id\":\"${UNSUPPORTED_VERSION_ID}\",\"content_json\":{},\"content_text\":\"Python Platform Engineer.\",\"change_summary\":\"Grounded correction\"}"
    SUPPORTED_VERSION_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["unsupported_claim_count"] == 0; print(value["id"])' "${RESPONSE_FILE}")"
    for MATERIAL_VERSION_ID in "${SUPPORTED_VERSION_ID}" "${COVER_VERSION_ID}"; do
      api_write POST "/api/material-versions/${MATERIAL_VERSION_ID}/review" \
        '{"decision":"approve","notes":"Synthetic Smoke review."}'
      api_write POST "/api/material-versions/${MATERIAL_VERSION_ID}/finalize" \
        '{"confirmation":"FINALIZE MATERIAL"}'
      python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["finalized_at"]' "${RESPONSE_FILE}"
    done
    curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
      "${ORIGIN}/api/application-packages/${PACKAGE_ID}" >"${RESPONSE_FILE}"
    PACKAGE_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
    if [[ "${V204_SCOPE}" == "1" ]]; then
      python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "draft"' "${RESPONSE_FILE}"
      smoke_step 'Evidence validation blocks unsupported claims and permits reviewed grounded Material finalization'
    else
      api_write POST "/api/application-packages/${PACKAGE_ID}/approve" \
        "{\"expected_revision\":${PACKAGE_REVISION},\"confirmation\":\"APPROVE PACKAGE\"}"
      python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "approved"' "${RESPONSE_FILE}"
      smoke_step 'Evidence validation blocks unsupported claims and permits reviewed grounded finalization'
    fi
  fi
fi

if [[ "${V204_SCOPE}" == "1" ]]; then
  api_write POST "/api/applications/${APPLICATION_ID}/packages" \
    "{\"source_resume_version_id\":\"${VERSION_ID}\",\"match_analysis_id\":\"${MATCH_ID}\",\"title\":\"Async Agent Smoke Package\"}"
  AGENT_PACKAGE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
  AGENT_IDEMPOTENCY_KEY="smoke-agent-${STAMP}"
  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "Idempotency-Key: ${AGENT_IDEMPOTENCY_KEY}" -H 'Content-Type: application/json' \
    --data "{\"workflow_type\":\"generate_application_package\",\"package_id\":\"${AGENT_PACKAGE_ID}\"}" \
    "${ORIGIN}/api/agent-runs" >"${RESPONSE_FILE}"
  AGENT_RUN_ID="$(python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["reused"] is False; print(value["run"]["id"])' "${RESPONSE_FILE}")"

  curl --noproxy '*' --silent --show-error --max-time 3 \
    --cookie "${COOKIE_JAR}" -H 'Last-Event-ID: 0' \
    "${ORIGIN}/api/agent-runs/${AGENT_RUN_ID}/events/stream" \
    >"${TEST_ROOT}/agent-events.sse" || test "$?" = 28
  grep -q '^id: ' "${TEST_ROOT}/agent-events.sse"
  grep -q '^event: ' "${TEST_ROOT}/agent-events.sse"
  smoke_step 'authenticated SSE progress with Last-Event-ID and reconnect framing'

  APPROVAL_COUNT=0
  for attempt in $(seq 1 240); do
    curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
      "${ORIGIN}/api/agent-runs/${AGENT_RUN_ID}" >"${RESPONSE_FILE}"
    AGENT_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "${RESPONSE_FILE}")"
    if [[ "${AGENT_STATUS}" == "completed" ]]; then
      break
    fi
    if [[ "${AGENT_STATUS}" == "failed" || "${AGENT_STATUS}" == "dead_letter" || "${AGENT_STATUS}" == "cancelled" ]]; then
      cat "${RESPONSE_FILE}" >&2
      exit 1
    fi
    if [[ "${AGENT_STATUS}" == "waiting_for_approval" ]]; then
      APPROVAL_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pending_approval"]["id"])' "${RESPONSE_FILE}")"
      APPROVAL_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["pending_approval"]["revision"])' "${RESPONSE_FILE}")"
      APPROVAL_COUNT=$((APPROVAL_COUNT + 1))
      if [[ "${REAL_LLM_VALIDATION}" == "1" && "${APPROVAL_COUNT}" == 3 ]]; then
        break
      fi
      if [[ "${APPROVAL_COUNT}" == 1 ]]; then
        "${COMPOSE[@]}" restart redis >/dev/null
        "${COMPOSE[@]}" up --detach --wait redis worker backend >/dev/null
      elif [[ "${APPROVAL_COUNT}" == 2 ]]; then
        "${COMPOSE[@]}" restart worker >/dev/null
        "${COMPOSE[@]}" up --detach --wait worker backend >/dev/null
      fi
      api_write POST "/api/approvals/${APPROVAL_ID}/decide" \
        "{\"decision\":\"approve\",\"expected_revision\":${APPROVAL_REVISION},\"idempotency_key\":\"smoke-decision-${APPROVAL_COUNT}\",\"safe_reason\":\"Synthetic isolated Smoke approval.\"}"
    fi
    sleep 1
  done
  test "${APPROVAL_COUNT}" = 3
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/agent-runs/${AGENT_RUN_ID}/steps" >"${RESPONSE_FILE}"
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    test "${AGENT_STATUS}" = "waiting_for_approval"
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert len(value) == 20; assert all(item["status"] == "completed" for item in value[:18]); assert value[18]["status"] == "waiting_for_approval"; assert value[19]["status"] == "pending"' "${RESPONSE_FILE}"
  else
    test "${AGENT_STATUS}" = "completed"
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert len(value) == 20; assert all(item["status"] == "completed" for item in value)' "${RESPONSE_FILE}"
  fi
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/agent-runs/${AGENT_RUN_ID}/events?after_id=0" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value; raw=json.dumps(value); assert "Synthetic private Smoke note" not in raw; assert "Phase-1-Smoke-Passphrase" not in raw; assert "TEST_ONLY_NEVER_SENT" not in raw' "${RESPONSE_FILE}"
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    smoke_step 'controlled DeepSeek workflow reached final Package Approval without automatic finalization'
  else
    smoke_step '20-step asynchronous Package Workflow, Redis/Worker restart, three Approvals, and completion'
  fi

  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "Idempotency-Key: ${AGENT_IDEMPOTENCY_KEY}" -H 'Content-Type: application/json' \
    --data "{\"workflow_type\":\"generate_application_package\",\"package_id\":\"${AGENT_PACKAGE_ID}\"}" \
    "${ORIGIN}/api/agent-runs" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["reused"] is True; assert value["run"]["id"] == sys.argv[2]' "${RESPONSE_FILE}" "${AGENT_RUN_ID}"
  smoke_step 'Agent Run Idempotency-Key returns the existing Run'

  "${COMPOSE[@]}" stop worker >/dev/null
  api_write POST "/api/applications/${APPLICATION_ID}/packages" \
    "{\"source_resume_version_id\":\"${VERSION_ID}\",\"match_analysis_id\":\"${MATCH_ID}\",\"title\":\"Cancelled Agent Smoke Package\"}"
  CANCEL_PACKAGE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
  curl --noproxy '*' --fail --silent --show-error \
    --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
    -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
    -H "Idempotency-Key: smoke-cancel-${STAMP}" -H 'Content-Type: application/json' \
    --data "{\"workflow_type\":\"generate_application_package\",\"package_id\":\"${CANCEL_PACKAGE_ID}\"}" \
    "${ORIGIN}/api/agent-runs" >"${RESPONSE_FILE}"
  CANCEL_RUN_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["id"])' "${RESPONSE_FILE}")"
  CANCEL_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["revision"])' "${RESPONSE_FILE}")"
  api_write POST "/api/agent-runs/${CANCEL_RUN_ID}/cancel" "{\"expected_revision\":${CANCEL_REVISION}}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "cancelled"' "${RESPONSE_FILE}"
  "${COMPOSE[@]}" up --detach --wait worker backend >/dev/null
  smoke_step 'queued Agent Run cancellation is immediate and idempotent'

  if [[ "${REAL_LLM_VALIDATION}" == "0" ]]; then
    USER_ID="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc \
      "SELECT id FROM users WHERE normalized_email='phase1-admin@example.com'")"
    "${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -v ON_ERROR_STOP=1 \
      -c "UPDATE user_ai_budgets SET step_token_limit=100 WHERE user_id='${USER_ID}'" >/dev/null
    api_write POST "/api/applications/${APPLICATION_ID}/packages" \
      "{\"source_resume_version_id\":\"${VERSION_ID}\",\"match_analysis_id\":\"${MATCH_ID}\",\"title\":\"Retry Agent Smoke Package\"}"
    RETRY_PACKAGE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "${RESPONSE_FILE}")"
    curl --noproxy '*' --fail --silent --show-error \
      --cookie "${COOKIE_JAR}" --cookie-jar "${COOKIE_JAR}" \
      -X POST -H "Origin: ${ORIGIN}" -H "X-CSRF-Token: ${CSRF_TOKEN}" \
      -H "Idempotency-Key: smoke-retry-${STAMP}" -H 'Content-Type: application/json' \
      --data "{\"workflow_type\":\"generate_application_package\",\"package_id\":\"${RETRY_PACKAGE_ID}\"}" \
      "${ORIGIN}/api/agent-runs" >"${RESPONSE_FILE}"
    RETRY_RUN_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run"]["id"])' "${RESPONSE_FILE}")"
    for attempt in $(seq 1 120); do
      curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
        "${ORIGIN}/api/agent-runs/${RETRY_RUN_ID}" >"${RESPONSE_FILE}"
      RETRY_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "${RESPONSE_FILE}")"
      [[ "${RETRY_STATUS}" == "failed" ]] && break
      sleep 1
    done
    test "${RETRY_STATUS}" = "failed"
    RETRY_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
    "${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -v ON_ERROR_STOP=1 \
      -c "UPDATE user_ai_budgets SET step_token_limit=20000 WHERE user_id='${USER_ID}'" >/dev/null
    api_write POST "/api/agent-runs/${RETRY_RUN_ID}/retry" \
      "{\"expected_revision\":${RETRY_REVISION},\"acknowledge_possible_cost\":true}"
    for attempt in $(seq 1 120); do
      curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
        "${ORIGIN}/api/agent-runs/${RETRY_RUN_ID}" >"${RESPONSE_FILE}"
      RETRY_STATUS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "${RESPONSE_FILE}")"
      [[ "${RETRY_STATUS}" == "waiting_for_approval" ]] && break
      [[ "${RETRY_STATUS}" == "failed" || "${RETRY_STATUS}" == "dead_letter" ]] && exit 1
      sleep 1
    done
    test "${RETRY_STATUS}" = "waiting_for_approval"
    RETRY_REVISION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["revision"])' "${RESPONSE_FILE}")"
    api_write POST "/api/agent-runs/${RETRY_RUN_ID}/cancel" "{\"expected_revision\":${RETRY_REVISION}}"
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["status"] == "cancelled"; assert value["partial"] is True' "${RESPONSE_FILE}"
    smoke_step 'budget preflight failure, explicit Retry with cost acknowledgment, and partial cancellation'
  fi

  HEARTBEATS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc \
    "SELECT COUNT(*) FROM worker_heartbeats WHERE status IN ('ready','busy')")"
  OUTBOX_ROWS="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc \
    'SELECT COUNT(*) FROM agent_outbox_events')"
  test "${HEARTBEATS}" -ge 1
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    test "${OUTBOX_ROWS}" -ge 15
  else
    test "${OUTBOX_ROWS}" -ge 20
  fi
  smoke_step 'Worker heartbeat and PostgreSQL Transactional Outbox persistence'
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    REAL_USAGE="$("${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc \
      "SELECT COUNT(*) || ':' || COALESCE(SUM(total_tokens),0) FROM ai_usage_ledger WHERE run_id='${AGENT_RUN_ID}' AND provider='deepseek'")"
    test "${REAL_USAGE%%:*}" = 3
    test "${REAL_USAGE##*:}" -gt 0
    "${COMPOSE[@]}" exec -T database psql -U pja_bootstrap -d personal_job_agent_smoke_test -Atqc \
      "SELECT COUNT(*) FROM application_material_versions v JOIN application_materials m ON m.id=v.material_id WHERE m.package_id='${AGENT_PACKAGE_ID}' AND v.unsupported_claim_count > 0" \
      | grep -qx '0'
    smoke_step 'three bounded DeepSeek calls recorded with valid grounded evidence and no unsupported claims'
  fi
fi

api_write POST /api/auth/logout
UNAUTH_PATH='/api/jobs'
if [[ "${SMOKE_MILESTONE}" == "2.0.1" ]]; then UNAUTH_PATH='/api/resumes'; fi
UNAUTH_STATUS="$(curl --noproxy '*' --silent --output /dev/null --write-out '%{http_code}' "${ORIGIN}${UNAUTH_PATH}")"
test "${UNAUTH_STATUS}" = 401

if [[ "${V204_SCOPE}" == "1" ]]; then
  "${COMPOSE[@]}" restart redis worker backend frontend >/dev/null
else
  "${COMPOSE[@]}" restart backend frontend >/dev/null
fi
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
if [[ "${V202_SCOPE}" == "1" ]]; then
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
if [[ "${V203_SCOPE}" == "1" ]]; then
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/jobs/${JOB_ID}/matches/${MATCH_ID}" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "completed"' "${RESPONSE_FILE}"
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/job-rank-runs/${RANK_RUN_ID}" >"${RESPONSE_FILE}"
  python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["job_count"] == 1' "${RESPONSE_FILE}"
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
      "${ORIGIN}/api/application-packages/${AGENT_PACKAGE_ID}" >"${RESPONSE_FILE}"
    python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "draft"' "${RESPONSE_FILE}"
  else
    curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
      "${ORIGIN}/api/application-packages/${PACKAGE_ID}" >"${RESPONSE_FILE}"
    if [[ "${V204_SCOPE}" == "1" ]]; then
      python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "draft"' "${RESPONSE_FILE}"
    else
      python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["status"] == "approved"' "${RESPONSE_FILE}"
    fi
  fi
  smoke_step 'Match, Ranking, Package, and Material rows after container restart'
fi
if [[ "${V204_SCOPE}" == "1" ]]; then
  curl --noproxy '*' --fail --silent --show-error --cookie "${COOKIE_JAR}" \
    "${ORIGIN}/api/agent-runs/${AGENT_RUN_ID}" >"${RESPONSE_FILE}"
  if [[ "${REAL_LLM_VALIDATION}" == "1" ]]; then
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["status"] == "waiting_for_approval"; assert len(value["steps"]) == 20; assert value["pending_approval"]["approval_type"] == "application_package"' "${RESPONSE_FILE}"
  else
    python3 -c 'import json,sys; value=json.load(open(sys.argv[1])); assert value["status"] == "completed"; assert len(value["steps"]) == 20' "${RESPONSE_FILE}"
  fi
  smoke_step 'Agent Run, Steps, Events, and usage persist across Redis/Worker restart'
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
  "${ROOT_DIR}/scripts/backup-v2.sh" --backup-dir "${TEST_ROOT}/verified-backup" \
  --files-root "${TEST_ROOT}/files" \
  --project-knowledge "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md"
mapfile -t BACKUP_PATHS < <(find "${TEST_ROOT}/verified-backup" -mindepth 1 -maxdepth 1 -type d -name 'v2-*' -print)
test "${#BACKUP_PATHS[@]}" = 1
BACKUP_PATH="$(realpath "${BACKUP_PATHS[0]}")"
BACKUP_ROOT="$(realpath "${TEST_ROOT}/verified-backup")"
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
if [[ "${V202_SCOPE}" == "1" ]]; then
  COUNT_SQL="${COUNT_SQL} || ':' || (SELECT COUNT(*) FROM jobs) || ':' || (SELECT COUNT(*) FROM applications) || ':' || (SELECT COUNT(*) FROM application_tasks)"
fi
if [[ "${V203_SCOPE}" == "1" ]]; then
  COUNT_SQL="${COUNT_SQL} || ':' || (SELECT COUNT(*) FROM job_match_analyses) || ':' || (SELECT COUNT(*) FROM job_rank_runs) || ':' || (SELECT COUNT(*) FROM application_packages) || ':' || (SELECT COUNT(*) FROM application_materials) || ':' || (SELECT COUNT(*) FROM application_material_versions) || ':' || (SELECT COUNT(*) FROM material_evidence_links)"
fi
if [[ "${V204_SCOPE}" == "1" ]]; then
  COUNT_SQL="${COUNT_SQL} || ':' || (SELECT COUNT(*) FROM agent_runs) || ':' || (SELECT COUNT(*) FROM agent_steps) || ':' || (SELECT COUNT(*) FROM agent_run_events) || ':' || (SELECT COUNT(*) FROM approval_requests) || ':' || (SELECT COUNT(*) FROM approval_decisions) || ':' || (SELECT COUNT(*) FROM agent_outbox_events) || ':' || (SELECT COUNT(*) FROM ai_usage_ledger) || ':' || (SELECT COUNT(*) FROM worker_heartbeats) || ':' || (SELECT COUNT(*) FROM dead_letter_records)"
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
