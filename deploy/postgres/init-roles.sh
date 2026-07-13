#!/usr/bin/env bash
set -Eeuo pipefail

for variable in POSTGRES_APP_USER POSTGRES_MIGRATION_USER; do
  value="${!variable:-}"
  if [[ ! "${value}" =~ ^[a-z_][a-z0-9_]*$ ]]; then
    printf '%s must be a safe PostgreSQL role name.\n' "${variable}" >&2
    exit 1
  fi
done

psql --set=ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --set=db_name="${POSTGRES_DB}" \
  --set=app_user="${POSTGRES_APP_USER}" \
  --set=app_password="${POSTGRES_APP_PASSWORD}" \
  --set=migration_user="${POSTGRES_MIGRATION_USER}" \
  --set=migration_password="${POSTGRES_MIGRATION_PASSWORD}" <<'SQL'
CREATE ROLE :"migration_user" LOGIN PASSWORD :'migration_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE :"db_name" TO :"migration_user", :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"migration_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_user" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";
SQL
