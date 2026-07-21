#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_IMAGE="${1:-personal-job-agent-backend:local}"
NEGATIVE_IMAGE="${2:-}"
STAMP="$(date +%s)-$$"
PROJECT_NAME="pja-pg16-restore-${STAMP}"
SOURCE_DATABASE="pja_restore_source_test_${STAMP//-/_}"
TARGET_DATABASE="pja_restore_target_test_${STAMP//-/_}"
TARGET_VOLUME="${PROJECT_NAME}_target-data"
REPORT_PATH="${PJA_RESTORE_REPORT_PATH:-/tmp/${PROJECT_NAME}-report.json}"
POSTGRES_IMAGE='postgres:16.9-alpine@sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7'
POSTGRES_PASSWORD='strict_restore_test_only_2026'
SOURCE_DATABASE_URL="postgresql+psycopg://postgres:${POSTGRES_PASSWORD}@source-db:5432/${SOURCE_DATABASE}"
TARGET_DATABASE_URL="postgresql+psycopg://postgres:${POSTGRES_PASSWORD}@target-db:5432/${TARGET_DATABASE}"
ADMIN_PASSWORD='Synthetic-Restore-Test-Only-2026'
FIXTURE_DISPLAY_NAME='Restore Regression'
FIXTURE_EMAIL="${PJA_RESTORE_FIXTURE_EMAIL:-restore-regression+${STAMP}@example.com}"
CURRENT_STAGE='initialization'
BACKUP_STARTED=false
RESTORE_STARTED=false

if [[ ! "${PROJECT_NAME}" =~ ^pja-pg16-restore-[0-9]+-[0-9]+$ ]]; then
  printf '%s\n' 'Refusing unsafe Restore regression project name.' >&2
  exit 1
fi
if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  printf '%s\n' 'Docker access is required for the PostgreSQL 16 Restore regression.' >&2
  exit 1
fi

TOOL_IMAGE_ID="$("${DOCKER[@]}" image inspect --format '{{.Id}}' "${BACKEND_IMAGE}")"
if [[ ! "${TOOL_IMAGE_ID}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  printf '%s\n' 'Backend tool image does not have an immutable local image ID.' >&2
  exit 1
fi
TOOL_IMAGE_REFERENCE="${BACKEND_IMAGE}@${TOOL_IMAGE_ID}"
NEGATIVE_IMAGE_REFERENCE=""
if [[ -n "${NEGATIVE_IMAGE}" ]]; then
  NEGATIVE_IMAGE_ID="$("${DOCKER[@]}" image inspect --format '{{.Id}}' "${NEGATIVE_IMAGE}")"
  [[ "${NEGATIVE_IMAGE_ID}" =~ ^sha256:[a-f0-9]{64}$ ]]
  NEGATIVE_IMAGE_REFERENCE="${NEGATIVE_IMAGE}@${NEGATIVE_IMAGE_ID}"
fi

TEST_ROOT="$(mktemp -d "/tmp/${PROJECT_NAME}.XXXXXX")"
ENV_FILE="${TEST_ROOT}/test.env"
NEGATIVE_SOURCE_ENV="${TEST_ROOT}/negative-source.env"
NEGATIVE_TARGET_ENV="${TEST_ROOT}/negative-target.env"
REPORT_DRAFT="${TEST_ROOT}/report-draft.json"
PREFLIGHT_REPORT="${TEST_ROOT}/fixture-preflight.json"
NEGATIVE_PREFLIGHT_REPORT="${TEST_ROOT}/negative-fixture-preflight.json"
if [[ ! "${TEST_ROOT}" == /tmp/pja-pg16-restore-* ]]; then
  printf '%s\n' 'Refusing unsafe Restore regression temporary root.' >&2
  exit 1
fi

umask 077
install -d -m 0700 "${TEST_ROOT}/backups" "${TEST_ROOT}/files" \
  "${TEST_ROOT}/knowledge" "${TEST_ROOT}/restored-files" \
  "${TEST_ROOT}/restored-knowledge" "${TEST_ROOT}/negative-backups" \
  "${TEST_ROOT}/negative-restored-files" "${TEST_ROOT}/negative-restored-knowledge"
install -m 0600 "${ROOT_DIR}/docs/PROJECT_KNOWLEDGE.md" \
  "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md"
printf '%s\n' 'synthetic resume file for PostgreSQL 16 Restore regression' \
  >"${TEST_ROOT}/files/synthetic-resume.txt"
sudo -n chown -R 10001:10001 "${TEST_ROOT}/backups" "${TEST_ROOT}/files" \
  "${TEST_ROOT}/knowledge" "${TEST_ROOT}/restored-files" \
  "${TEST_ROOT}/restored-knowledge" "${TEST_ROOT}/negative-backups" \
  "${TEST_ROOT}/negative-restored-files" "${TEST_ROOT}/negative-restored-knowledge"

{
  printf 'PJA_TEST_BACKEND_IMAGE=%s\n' "${BACKEND_IMAGE}"
  printf 'PJA_TEST_TOOL_IMAGE_REFERENCE=%s\n' "${TOOL_IMAGE_REFERENCE}"
  printf 'PJA_TEST_POSTGRES_PASSWORD=%s\n' "${POSTGRES_PASSWORD}"
  printf 'PJA_TEST_ADMIN_PASSWORD=%s\n' "${ADMIN_PASSWORD}"
  printf 'PJA_TEST_ADMIN_EMAIL=%s\n' "${FIXTURE_EMAIL}"
  printf 'PJA_TEST_PROJECT_NAME=%s\n' "${PROJECT_NAME}"
  printf 'PJA_TEST_RUN_ID=%s\n' "${STAMP}"
  printf 'PJA_TEST_SOURCE_DATABASE=%s\n' "${SOURCE_DATABASE}"
  printf 'PJA_TEST_TARGET_DATABASE=%s\n' "${TARGET_DATABASE}"
  printf 'PJA_TEST_SOURCE_DATABASE_URL=%s\n' "${SOURCE_DATABASE_URL}"
  printf 'PJA_TEST_TARGET_DATABASE_URL=%s\n' "${TARGET_DATABASE_URL}"
  printf 'PJA_TEST_TARGET_VOLUME=%s\n' "${TARGET_VOLUME}"
  printf 'PJA_TEST_ROOT=%s\n' "${TEST_ROOT}"
} >"${ENV_FILE}"
chmod 0600 "${ENV_FILE}"

if [[ -n "${NEGATIVE_IMAGE}" ]]; then
  {
    printf 'APP_ENV=test\n'
    printf 'DATABASE_URL=postgresql+psycopg://postgres:%s@source-db:5432/%s\n' \
      "${POSTGRES_PASSWORD}" "${SOURCE_DATABASE}"
    printf 'POSTGRES_SERVER_IMAGE=%s\n' "${POSTGRES_IMAGE}"
    printf 'POSTGRES_TOOL_IMAGE=%s\n' "${NEGATIVE_IMAGE_REFERENCE}"
  } >"${NEGATIVE_SOURCE_ENV}"
  {
    printf 'APP_ENV=test\n'
    printf 'DATABASE_URL=postgresql+psycopg://postgres:%s@target-db:5432/%s\n' \
      "${POSTGRES_PASSWORD}" "${TARGET_DATABASE}"
    printf 'POSTGRES_SERVER_IMAGE=%s\n' "${POSTGRES_IMAGE}"
    printf 'POSTGRES_TOOL_IMAGE=%s\n' "${NEGATIVE_IMAGE_REFERENCE}"
  } >"${NEGATIVE_TARGET_ENV}"
  chmod 0600 "${NEGATIVE_SOURCE_ENV}" "${NEGATIVE_TARGET_ENV}"
fi

COMPOSE=("${DOCKER[@]}" compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" \
  -f "${ROOT_DIR}/compose.postgres16-restore.yaml")

cleanup() {
  local exit_code=$?
  local cleanup_status=passed
  trap - EXIT
  "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  "${DOCKER[@]}" volume rm "${PROJECT_NAME}_source-data" "${PROJECT_NAME}_target-data" \
    >/dev/null 2>&1 || true
  "${DOCKER[@]}" network rm "${PROJECT_NAME}_source-data" "${PROJECT_NAME}_restore-data" \
    >/dev/null 2>&1 || true
  for volume in "${PROJECT_NAME}_source-data" "${PROJECT_NAME}_target-data"; do
    if "${DOCKER[@]}" volume inspect "${volume}" >/dev/null 2>&1; then
      cleanup_status=failed
      exit_code=1
    fi
  done
  for network in "${PROJECT_NAME}_source-data" "${PROJECT_NAME}_restore-data"; do
    if "${DOCKER[@]}" network inspect "${network}" >/dev/null 2>&1; then
      cleanup_status=failed
      exit_code=1
    fi
  done
  if [[ "${exit_code}" -ne 0 && -f "${PREFLIGHT_REPORT}" ]]; then
    cp "${PREFLIGHT_REPORT}" "${REPORT_DRAFT}"
  fi
  python3 - "${REPORT_DRAFT}" "${REPORT_PATH}" "${exit_code}" "${CURRENT_STAGE}" \
    "${BACKUP_STARTED}" "${RESTORE_STARTED}" "${cleanup_status}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

draft_path, report_path, exit_code, stage, backup_started, restore_started, cleanup = sys.argv[1:]
draft = Path(draft_path)
try:
    report = json.loads(draft.read_text(encoding="utf-8")) if draft.is_file() else {}
except (OSError, json.JSONDecodeError):
    report = {}
if int(exit_code) != 0 and report.get("status") != "failed":
    report = {
        "status": "failed",
        "stage": stage,
        "exception_type": "ShellCommandError",
        "validation_code": "POSTGRES16_RESTORE_REGRESSION_FAILED",
        "safe_message": "Strict PostgreSQL 16 Restore regression stage failed.",
        "backup_started": backup_started == "true",
        "restore_started": restore_started == "true",
        "secrets_included": False,
    }
report["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
report["cleanup"] = cleanup
report["secrets_included"] = False
destination = Path(report_path).resolve(strict=False)
if destination.exists() and destination.is_symlink():
    raise SystemExit("Refusing symlink report destination")
destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
temporary = destination.with_name(f".{destination.name}.tmp")
temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, destination)
PY
  if grep --fixed-strings --quiet "${POSTGRES_PASSWORD}" "${REPORT_PATH}" \
    || grep --fixed-strings --quiet "${ADMIN_PASSWORD}" "${REPORT_PATH}"; then
    printf '%s\n' 'Sanitized Restore report contained a test credential.' >&2
    exit_code=1
  fi
  if [[ "${TEST_ROOT}" == /tmp/pja-pg16-restore-* ]]; then
    sudo -n rm -rf -- "${TEST_ROOT}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT

CURRENT_STAGE='test_database_name_preflight'
"${DOCKER[@]}" run --rm --network none --env-file "${ENV_FILE}" \
  "${BACKEND_IMAGE}" python /app/scripts/v2_backup_restore.py \
  validate-test-database-names \
  --run-id "${STAMP}" \
  --source-database-name "${SOURCE_DATABASE}" \
  --target-database-name "${TARGET_DATABASE}" \
  --source-database-url-env PJA_TEST_SOURCE_DATABASE_URL \
  --target-database-url-env PJA_TEST_TARGET_DATABASE_URL

CURRENT_STAGE='synthetic_admin_fixture_preflight'
if "${DOCKER[@]}" run --rm --network none --env-file "${ENV_FILE}" "${BACKEND_IMAGE}" \
  python /app/scripts/postgres_restore_fixture.py \
  --email 'restore-regression@example.test' --display-name "${FIXTURE_DISPLAY_NAME}" \
  --run-id "${STAMP}" >"${NEGATIVE_PREFLIGHT_REPORT}"; then
  printf '%s\n' 'Reserved special-use fixture email unexpectedly passed preflight.' >&2
  exit 1
fi
python3 - "${NEGATIVE_PREFLIGHT_REPORT}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["validation_code"] == "SYNTHETIC_FIXTURE_VALIDATION_FAILED", report
assert report["failure_field"] == "email", report
assert report["cause_type"] == "EmailSyntaxError", report
assert report["backup_started"] is False, report
assert report["restore_started"] is False, report
assert report["secrets_included"] is False, report
PY
if [[ -n "$("${DOCKER[@]}" volume ls --filter "name=${PROJECT_NAME}" --quiet)" ]]; then
  printf '%s\n' 'Fixture preflight created a persistent Docker Volume.' >&2
  exit 1
fi
if ! "${DOCKER[@]}" run --rm --network none --env-file "${ENV_FILE}" "${BACKEND_IMAGE}" \
  python /app/scripts/postgres_restore_fixture.py \
  --email "${FIXTURE_EMAIL}" --display-name "${FIXTURE_DISPLAY_NAME}" \
  --run-id "${STAMP}" >"${PREFLIGHT_REPORT}"; then
  exit 1
fi
cp "${PREFLIGHT_REPORT}" "${REPORT_DRAFT}"

CURRENT_STAGE='compose_validation'
"${COMPOSE[@]}" config --quiet
if "${COMPOSE[@]}" config | grep -Eq 'published:|host_ip:'; then
  printf '%s\n' 'Restore regression must not publish a database port.' >&2
  exit 1
fi
"${COMPOSE[@]}" up --detach --wait source-db target-db

CURRENT_STAGE='source_database_initialization'
TARGET_CONTAINER_ID="$("${COMPOSE[@]}" ps --quiet target-db)"
[[ "${TARGET_CONTAINER_ID}" =~ ^[a-f0-9]{64}$ ]]
TARGET_CONTAINER_LABELS="$("${DOCKER[@]}" inspect --format \
  '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}' \
  "${TARGET_CONTAINER_ID}")"
[[ "${TARGET_CONTAINER_LABELS}" == "${PROJECT_NAME}|target-db" ]]
TARGET_MOUNT_SOURCE="$("${DOCKER[@]}" inspect --format \
  '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' \
  "${TARGET_CONTAINER_ID}")"
[[ "${TARGET_MOUNT_SOURCE}" == "${TARGET_VOLUME}" ]]
TARGET_VOLUME_LABELS="$("${DOCKER[@]}" volume inspect --format \
  '{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}' \
  "${TARGET_VOLUME}")"
[[ "${TARGET_VOLUME_LABELS}" == "${PROJECT_NAME}|target-data" ]]
"${COMPOSE[@]}" exec -T target-db createdb -U postgres --template=template0 \
  "${TARGET_DATABASE}"

SOURCE_SERVER_VERSION="$("${COMPOSE[@]}" exec -T source-db \
  psql -U postgres -d "${SOURCE_DATABASE}" -Atqc 'SHOW server_version')"
SOURCE_SERVER_VERSION_NUM="$("${COMPOSE[@]}" exec -T source-db \
  psql -U postgres -d "${SOURCE_DATABASE}" -Atqc 'SHOW server_version_num')"
TARGET_SERVER_VERSION_NUM="$("${COMPOSE[@]}" exec -T target-db \
  psql -U postgres -d "${TARGET_DATABASE}" -Atqc 'SHOW server_version_num')"
SOURCE_DATABASE_ACTUAL="$("${COMPOSE[@]}" exec -T source-db \
  psql -U postgres -d "${SOURCE_DATABASE}" -Atqc 'SELECT current_database()')"
TARGET_DATABASE_ACTUAL="$("${COMPOSE[@]}" exec -T target-db \
  psql -U postgres -d "${TARGET_DATABASE}" -Atqc 'SELECT current_database()')"
[[ "${SOURCE_DATABASE_ACTUAL}" == "${SOURCE_DATABASE}" ]]
[[ "${TARGET_DATABASE_ACTUAL}" == "${TARGET_DATABASE}" ]]
[[ "${SOURCE_SERVER_VERSION_NUM}" == 16* ]]
[[ "${TARGET_SERVER_VERSION_NUM}" == 16* ]]

"${COMPOSE[@]}" run --rm -T source-tool alembic -c alembic.ini upgrade head
CURRENT_STAGE='synthetic_admin_fixture_creation'
"${COMPOSE[@]}" run --rm -T source-tool python -m app.cli users create-admin \
  --email "${FIXTURE_EMAIL}" --display-name "${FIXTURE_DISPLAY_NAME}"
CURRENT_STAGE='synthetic_business_fixture_creation'
"${COMPOSE[@]}" run --rm -T source-tool python - <<'PY'
import json
import os

from sqlalchemy import select

from app.core.security import normalize_email, verify_password
from app.db.models import ApplicationRecord, User, utc_now
from app.db.session import session_factory

email = os.environ["PJA_TEST_ADMIN_EMAIL"]
password = os.environ["PJA_TEST_ADMIN_PASSWORD"]
database = session_factory()()
try:
    user = database.scalar(select(User).where(User.normalized_email == normalize_email(email)))
    assert user is not None and user.role == "admin" and user.is_active
    assert user.email == normalize_email(email) == user.normalized_email
    assert user.password_hash != password and verify_password(password, user.password_hash)
    now = utc_now()
    database.add(
        ApplicationRecord(
            owner_user_id=user.id,
            created_at=now,
            updated_at=now,
            company_name="Synthetic Restore Company",
            job_title="Synthetic Restore Role",
            application_status="Saved",
            match_score=88,
            match_reason="Synthetic deterministic backup and restore fixture.",
            rag_mode="mock",
        )
    )
    database.commit()
finally:
    database.close()
print(json.dumps({"admin_fixture": "passed", "synthetic_business_fixture": "passed"}))
PY
"${COMPOSE[@]}" run --rm -T source-tool python - <<'PY'
from legacy_application import rebuild_project_knowledge_index

result = rebuild_project_knowledge_index()
assert int(result["chunk_count"]) > 0, result
print(f"Project Knowledge regression chunks: {result['chunk_count']}")
PY

TARGET_RELATIONS_BEFORE="$("${COMPOSE[@]}" exec -T target-db psql -U postgres \
  -d "${TARGET_DATABASE}" -Atqc "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f','i','I')")"
[[ "${TARGET_RELATIONS_BEFORE}" == "0" ]]

CURRENT_STAGE='postgresql16_backup'
BACKUP_STARTED=true
"${COMPOSE[@]}" run --rm -T source-tool python /app/scripts/v2_backup_restore.py backup \
  --database-url-env DATABASE_URL --backup-dir /work/backups \
  --files-root /work/files --project-knowledge /work/knowledge/PROJECT_KNOWLEDGE.md

mapfile -t BACKUP_NAMES < <(sudo -n find "${TEST_ROOT}/backups" -mindepth 1 -maxdepth 1 \
  -type d -name 'v2-*' -printf '%f\n')
[[ "${#BACKUP_NAMES[@]}" == "1" ]]
BACKUP_NAME="${BACKUP_NAMES[0]}"
[[ "${BACKUP_NAME}" =~ ^v2-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$ ]]

"${COMPOSE[@]}" run --rm -T source-tool python /app/scripts/v2_backup_restore.py verify \
  --backup "/work/backups/${BACKUP_NAME}"

CURRENT_STAGE='archive_toc_validation'
"${COMPOSE[@]}" run --rm -T source-tool python - "/work/backups/${BACKUP_NAME}/postgres.dump" <<'PY'
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/scripts")
from v2_backup_restore import archive_toc

_toc, schemas = archive_toc(Path(sys.argv[1]), os.environ.copy())
assert schemas == {"public"}, schemas
print(json.dumps({"archive_schema_count": len(schemas), "archive_contains_public": True}))
PY

CURRENT_STAGE='schema_aware_target_preflight'
"${COMPOSE[@]}" run --rm -T target-tool python - <<'PY'
import json
import os
import sys

import psycopg

sys.path.insert(0, "/app/scripts")
from v2_backup_restore import _restore_target_structure, database_parts

database_url, _pg_env, _pg_args = database_parts("DATABASE_URL")
with psycopg.connect(database_url) as connection:
    structure = _restore_target_structure(connection)
assert structure.database_name == os.environ["PJA_RESTORE_EXPECTED_DATABASE"]
assert structure.schemas == ("public",)
assert structure.object_count == 0
assert structure.writable is True
print(json.dumps({
    "database_identity": "passed",
    "non_system_schemas": list(structure.schemas),
    "relation_count": structure.relation_count,
    "sequence_count": structure.sequence_count,
    "function_count": structure.function_count,
    "type_count": structure.type_count,
    "extension_count": structure.extension_count,
    "dependency_count": structure.public_dependency_count,
}))
PY

if [[ -n "${NEGATIVE_IMAGE}" ]]; then
  NEGATIVE_BACKUP_LOG="${TEST_ROOT}/negative-backup.log"
  if "${DOCKER[@]}" run --rm --network "${PROJECT_NAME}_source-data" \
    --env-file "${NEGATIVE_SOURCE_ENV}" \
    --volume "${TEST_ROOT}/negative-backups:/work/backups" \
    --volume "${TEST_ROOT}/files:/work/files:ro" \
    --volume "${TEST_ROOT}/knowledge:/work/knowledge:ro" \
    "${NEGATIVE_IMAGE}" python /app/scripts/v2_backup_restore.py backup \
    --database-url-env DATABASE_URL --backup-dir /work/backups \
    --files-root /work/files --project-knowledge /work/knowledge/PROJECT_KNOWLEDGE.md \
    >"${NEGATIVE_BACKUP_LOG}" 2>&1; then
    printf '%s\n' 'PostgreSQL 17 pg_dump negative gate unexpectedly passed.' >&2
    exit 1
  fi
  grep -q 'POSTGRES_CLIENT_MAJOR_MISMATCH' "${NEGATIVE_BACKUP_LOG}"
  if grep -q "${POSTGRES_PASSWORD}" "${NEGATIVE_BACKUP_LOG}"; then
    printf '%s\n' 'Negative backup log exposed a test credential.' >&2
    exit 1
  fi
  [[ -z "$(sudo -n find "${TEST_ROOT}/negative-backups" -mindepth 1 -print -quit)" ]]

  NEGATIVE_RESTORE_LOG="${TEST_ROOT}/negative-restore.log"
  if "${DOCKER[@]}" run --rm --network "${PROJECT_NAME}_restore-data" \
    --env-file "${NEGATIVE_TARGET_ENV}" \
    --volume "${TEST_ROOT}/backups:/work/backups:ro" \
    --volume "${TEST_ROOT}/negative-restored-files:/work/restored-files" \
    --volume "${TEST_ROOT}/negative-restored-knowledge:/work/restored-knowledge" \
    "${NEGATIVE_IMAGE}" python /app/scripts/v2_backup_restore.py restore \
    --database-url-env DATABASE_URL --backup "/work/backups/${BACKUP_NAME}" \
    --files-root /work/restored-files \
    --project-knowledge /work/restored-knowledge/PROJECT_KNOWLEDGE.md \
    --confirmation 'RESTORE V2 BACKUP' >"${NEGATIVE_RESTORE_LOG}" 2>&1; then
    printf '%s\n' 'PostgreSQL 17 pg_restore negative gate unexpectedly passed.' >&2
    exit 1
  fi
  grep -q 'POSTGRES_CLIENT_MAJOR_MISMATCH' "${NEGATIVE_RESTORE_LOG}"
  if grep -q "${POSTGRES_PASSWORD}" "${NEGATIVE_RESTORE_LOG}"; then
    printf '%s\n' 'Negative restore log exposed a test credential.' >&2
    exit 1
  fi
  TARGET_RELATIONS_AFTER_NEGATIVE="$("${COMPOSE[@]}" exec -T target-db psql -U postgres \
    -d "${TARGET_DATABASE}" -Atqc "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f','i','I')")"
  [[ "${TARGET_RELATIONS_AFTER_NEGATIVE}" == "0" ]]
fi

CURRENT_STAGE='postgresql16_strict_restore'
RESTORE_STARTED=true
"${COMPOSE[@]}" run --rm -T target-tool python /app/scripts/v2_backup_restore.py restore \
  --database-url-env DATABASE_URL --backup "/work/backups/${BACKUP_NAME}" \
  --files-root /work/restored-files \
  --project-knowledge /work/restored-knowledge/PROJECT_KNOWLEDGE.md \
  --prepare-disposable-target \
  --allow-isolated-database-name-difference \
  --allowed-owner-mapping pg_database_owner=postgres \
  --confirmation 'RESTORE V2 BACKUP'

PUBLIC_SCHEMA_OWNER="$("${COMPOSE[@]}" exec -T target-db psql -U postgres \
  -d "${TARGET_DATABASE}" -Atqc \
  "SELECT owner.rolname FROM pg_namespace AS namespace JOIN pg_roles AS owner ON owner.oid=namespace.nspowner WHERE namespace.nspname='public'")"
PUBLIC_SCHEMA_ACL_IS_NULL="$("${COMPOSE[@]}" exec -T target-db psql -U postgres \
  -d "${TARGET_DATABASE}" -Atqc \
  "SELECT nspacl IS NULL FROM pg_namespace WHERE nspname='public'")"
[[ "${PUBLIC_SCHEMA_OWNER}" == "postgres" ]]
[[ "${PUBLIC_SCHEMA_ACL_IS_NULL}" == "t" ]]

sudo -n cmp --silent "${TEST_ROOT}/files/synthetic-resume.txt" \
  "${TEST_ROOT}/restored-files/synthetic-resume.txt"
sudo -n cmp --silent "${TEST_ROOT}/knowledge/PROJECT_KNOWLEDGE.md" \
  "${TEST_ROOT}/restored-knowledge/PROJECT_KNOWLEDGE.md"

CURRENT_STAGE='restored_admin_authentication_validation'
"${COMPOSE[@]}" run --rm -T target-tool python - <<'PY'
import json
import os

from sqlalchemy import select

from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.core.security import normalize_email, verify_password
from app.db.models import ApplicationRecord, User
from app.db.session import session_factory

email = os.environ["PJA_TEST_ADMIN_EMAIL"]
password = os.environ["PJA_TEST_ADMIN_PASSWORD"]
database = session_factory()()
try:
    user = database.scalar(select(User).where(User.normalized_email == normalize_email(email)))
    assert user is not None and user.email == normalize_email(email) == user.normalized_email
    assert user.role == "admin" and user.is_active
    assert user.password_hash != password and verify_password(password, user.password_hash)
    assert database.scalar(select(ApplicationRecord).where(ApplicationRecord.owner_user_id == user.id))
    service = AuthService(database, load_v2_settings())
    credentials = service.login(email, password, "restore-regression", "restore-regression")
    session, authenticated_user = service.authenticate(credentials.token, touch=False)
    assert authenticated_user.id == user.id and session.user_id == user.id
    database.rollback()
finally:
    database.close()
print(json.dumps({"admin_record": "passed", "authentication_structure": "passed"}))
PY

CURRENT_STAGE='application_readiness_validation'
"${COMPOSE[@]}" run --rm -T target-tool python - <<'PY'
import json
from app.readiness import readiness_status

payload, status = readiness_status()
assert status == 200, payload
assert payload["ready"] is True, payload
assert payload["version"] == "2.0.3", payload
assert payload["database_schema"] == "ready", payload
assert payload["knowledge_search"] == "ready", payload
print(json.dumps({"status": payload["status"], "version": payload["version"]}, sort_keys=True))
PY

CURRENT_STAGE='success_report_generation'
sudo -n python3 - "${TEST_ROOT}/backups/${BACKUP_NAME}/manifest.json" \
  "${REPORT_DRAFT}" "${SOURCE_SERVER_VERSION}" "${POSTGRES_IMAGE}" \
  "${TOOL_IMAGE_REFERENCE}" "${NEGATIVE_IMAGE_REFERENCE}" \
  "${PUBLIC_SCHEMA_OWNER}" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    manifest_path,
    report_path,
    server_version,
    server_image,
    tool_image,
    negative_image,
    public_schema_owner,
) = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
inventory = manifest["database_inventory"]
server_image_digest = server_image.rsplit("@", 1)[-1]
tool_image_digest = tool_image.rsplit("@", 1)[-1]
report = {
    "status": "passed",
    "synthetic_fixture_preflight": "passed",
    "test_database_name_policy": "passed",
    "source_database_identity": "passed",
    "target_database_identity": "passed",
    "fixture_email_domain_category": "reserved_documentation_example_com",
    "application_version": manifest["application_version"],
    "server_version": server_version,
    "server_major": manifest["database_server_major"],
    "server_image_digest": server_image_digest,
    "pg_dump_version": manifest["pg_dump_version"],
    "pg_dump_major": manifest["pg_dump_major"],
    "pg_restore_version": manifest["pg_restore_version"],
    "pg_restore_major": manifest["pg_restore_major"],
    "tool_image_digest": tool_image_digest,
    "archive_format": manifest["archive_format"],
    "archive_sha256": manifest["archive_sha256"],
    "backup_result": "passed",
    "manifest_result": "passed",
    "manifest_validation": "passed",
    "archive_toc_result": "passed",
    "archive_toc_validation": "passed",
    "archive_contains_public_schema": True,
    "target_original_non_system_schemas": ["public"],
    "target_original_public_object_count": 0,
    "target_created_from_template0": True,
    "target_identity_validation": "passed",
    "public_schema_preparation": "passed_restrict",
    "public_schema_drop": "DROP SCHEMA public RESTRICT",
    "cascade_used": False,
    "clean_used": False,
    "public_schema_absent_before_restore": True,
    "restore_result": "passed",
    "restore_exit_code": 0,
    "alembic_revision": manifest["alembic_revision"],
    "table_count": len(inventory["tables"]),
    "row_count_summary": inventory["table_row_counts"],
    "row_count_validation": "passed",
    "table_checksums": inventory["table_checksums"],
    "checksum_validation": "passed",
    "foreign_key_count": inventory["foreign_keys"]["count"],
    "foreign_key_validation": "passed",
    "sequence_validation": {"status": "passed", **inventory["sequences"]},
    "index_validation": {
        "status": "passed",
        "count": inventory["indexes"]["count"],
        "sha256": inventory["indexes"]["sha256"],
    },
    "ownership_validation": {"status": "passed", **inventory["ownership"]},
    "aggregate_validation": {
        "status": "passed",
        "sha256": inventory["aggregate_sha256"],
    },
    "admin_fixture_validation": "passed",
    "restored_admin_validation": "passed",
    "restored_admin_authentication": "passed",
    "authentication_structure": "passed",
    "public_schema_restored": True,
    "public_schema_owner": public_schema_owner,
    "public_schema_acl": "default_owner_only",
    "target_was_empty": True,
    "exit_on_error": True,
    "single_transaction": True,
    "database_ports_published": False,
    "source_and_target_volumes_independent": True,
    "files_checksum_match": True,
    "project_knowledge_checksum_match": True,
    "application_readiness": "passed",
    "postgresql_17_dump_rejected_before_write": bool(negative_image),
    "postgresql_17_restore_rejected_before_write": bool(negative_image),
}
destination = Path(report_path)
destination.parent.mkdir(parents=True, exist_ok=True)
temporary = destination.with_name(f".{destination.name}.tmp")
temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, destination)
PY
sudo -n chown "$(id -u):$(id -g)" "${REPORT_DRAFT}"

CURRENT_STAGE='completed'
printf 'PostgreSQL 16 strict Restore regression passed. Report: %s\n' "${REPORT_PATH}"
