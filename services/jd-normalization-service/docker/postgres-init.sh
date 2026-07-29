#!/bin/sh
set -eu

required_value() {
    variable_name="$1"
    eval "variable_value=\${${variable_name}:-}"
    if [ -z "${variable_value}" ]; then
        printf 'Required initialization value is missing: %s\n' "${variable_name}" >&2
        exit 1
    fi
}

valid_role() {
    role_name="$1"
    case "${role_name}" in
        [A-Za-z_]*)
            ;;
        *)
            return 1
            ;;
    esac
    case "${role_name}" in
        *[!A-Za-z0-9_]*)
            return 1
            ;;
    esac
    [ "${#role_name}" -le 63 ]
}

for variable_name in \
    POSTGRES_USER \
    POSTGRES_DB \
    JD_COMPOSE_MIGRATION_DB_USER \
    JD_COMPOSE_MIGRATION_DB_PASSWORD \
    JD_COMPOSE_APP_DB_USER \
    JD_COMPOSE_APP_DB_PASSWORD; do
    required_value "${variable_name}"
done

if ! valid_role "${POSTGRES_USER}" \
    || ! valid_role "${JD_COMPOSE_MIGRATION_DB_USER}" \
    || ! valid_role "${JD_COMPOSE_APP_DB_USER}"; then
    printf '%s\n' 'Database role names must use a bounded SQL identifier grammar.' >&2
    exit 1
fi

if [ "${POSTGRES_USER}" = "${JD_COMPOSE_MIGRATION_DB_USER}" ] \
    || [ "${POSTGRES_USER}" = "${JD_COMPOSE_APP_DB_USER}" ] \
    || [ "${JD_COMPOSE_MIGRATION_DB_USER}" = "${JD_COMPOSE_APP_DB_USER}" ]; then
    printf '%s\n' 'Bootstrap, migration, and application roles must be distinct.' >&2
    exit 1
fi

psql \
    --set=ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" \
    --set=migration_role="${JD_COMPOSE_MIGRATION_DB_USER}" \
    --set=migration_password="${JD_COMPOSE_MIGRATION_DB_PASSWORD}" \
    --set=application_role="${JD_COMPOSE_APP_DB_USER}" \
    --set=application_password="${JD_COMPOSE_APP_DB_PASSWORD}" \
    --set=database_name="${POSTGRES_DB}" <<'SQL'
CREATE ROLE :"migration_role"
    LOGIN
    PASSWORD :'migration_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;

CREATE ROLE :"application_role"
    LOGIN
    PASSWORD :'application_password'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;

GRANT CONNECT ON DATABASE :"database_name" TO :"migration_role";
GRANT CONNECT ON DATABASE :"database_name" TO :"application_role";
GRANT USAGE, CREATE ON SCHEMA public TO :"migration_role";
GRANT USAGE ON SCHEMA public TO :"application_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"application_role";

ALTER DEFAULT PRIVILEGES FOR ROLE :"migration_role" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"application_role";
SQL
