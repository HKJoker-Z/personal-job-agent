#!/usr/bin/env python3
"""PostgreSQL 16/private-file backup, verification, and guarded restore."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql


APPLICATION_VERSION = "2.0.2"
EXPECTED_POSTGRES_MAJOR = 16
MANIFEST_VERSION = 2
ARCHIVE_FORMAT = "custom"
RESTORE_SOURCE_DATABASE_PREFIX = "pja_restore_source_test_"
DISPOSABLE_DATABASE_PREFIX = "pja_restore_target_test_"
RESTORE_RUN_ID_PATTERN = re.compile(r"^[0-9]{10}-[0-9]{1,10}$")
DISPOSABLE_PROJECT_PATTERN = re.compile(
    r"^pja-pg16-restore-(?P<run_id>[0-9]{10}-[0-9]{1,10})$"
)
DISPOSABLE_DATABASE_PATTERN = re.compile(
    rf"^{re.escape(DISPOSABLE_DATABASE_PREFIX)}"
    r"(?P<run_id>[0-9]{10}_[0-9]{1,10})$"
)
POSTGRES_IDENTIFIER_MAX_BYTES = 63
FORBIDDEN_TEST_DATABASE_NAMES = frozenset({"postgres", "template0", "template1"})
REQUIRED_TABLES = frozenset(
    {
        "alembic_version",
        "users",
        "application_records",
        "analysis_metrics",
        "evaluation_runs",
        "knowledge_documents",
        "knowledge_chunks",
        "resumes",
        "resume_versions",
        "file_assets",
        "agent_runs",
        "agent_steps",
        "agent_run_events",
        "approval_requests",
        "approval_decisions",
        "agent_outbox_events",
        "user_ai_budgets",
        "ai_usage_ledger",
        "worker_heartbeats",
        "dead_letter_records",
    }
)
REQUIRED_INDEXES = frozenset({"ix_knowledge_chunks_fts"})
IMAGE_REFERENCE_PATTERN = re.compile(
    r"^(?P<name>[^@\s]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)
CLIENT_VERSION_PATTERN = re.compile(
    r"^(?P<tool>pg_dump|pg_restore|psql) \(PostgreSQL\) "
    r"(?P<version>[0-9]+(?:\.[0-9]+)*)(?:[ \t].*)?$"
)
POSTGRES_ROLE_NAME_PATTERN = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class SafeOperationError(RuntimeError):
    """An operator-safe failure with fields that cannot contain credentials."""

    def __init__(self, code: str, **summary: str | int) -> None:
        super().__init__(code)
        self.code = code
        self.summary = summary


@dataclass(frozen=True)
class ImageInfo:
    name: str
    digest: str

    @property
    def reference(self) -> str:
        return f"{self.name}@{self.digest}"


@dataclass(frozen=True)
class ServerInfo:
    version: str
    version_num: int
    major: int


@dataclass(frozen=True)
class ClientInfo:
    tool: str
    version: str
    major: int


@dataclass(frozen=True)
class PostgresPreflight:
    server: ServerInfo
    pg_dump: ClientInfo
    pg_restore: ClientInfo
    psql: ClientInfo
    server_image: ImageInfo
    tool_image: ImageInfo


@dataclass(frozen=True)
class RestoreTargetIdentity:
    enabled: bool
    project_name: str
    expected_database: str
    target_volume: str


@dataclass(frozen=True)
class RestoreTargetStructure:
    database_name: str
    schemas: tuple[str, ...]
    relation_count: int
    sequence_count: int
    function_count: int
    type_count: int
    extension_count: int
    public_dependency_count: int
    writable: bool

    @property
    def public_exists(self) -> bool:
        return "public" in self.schemas

    @property
    def object_count(self) -> int:
        return (
            self.relation_count
            + self.function_count
            + self.type_count
            + self.extension_count
            + self.public_dependency_count
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_image_reference(value: str, field: str) -> ImageInfo:
    match = IMAGE_REFERENCE_PATTERN.fullmatch(value.strip())
    if not match or match.group("name").endswith(":latest"):
        raise SafeOperationError("POSTGRES_IMAGE_NOT_IMMUTABLE", field=field)
    return ImageInfo(match.group("name"), match.group("digest"))


def configured_image(environment_name: str) -> ImageInfo:
    return parse_image_reference(os.getenv(environment_name, ""), environment_name)


def parse_server_major(version_num: str | int) -> int:
    try:
        parsed = int(version_num)
    except (TypeError, ValueError) as exc:
        raise SafeOperationError("POSTGRES_SERVER_VERSION_INVALID") from exc
    if parsed < 10000:
        raise SafeOperationError("POSTGRES_SERVER_VERSION_INVALID")
    return parsed // 10000


def parse_server_version(version: str) -> int:
    match = re.match(r"^(?P<major>[0-9]+)(?:\.|$)", version.strip())
    if match is None:
        raise SafeOperationError("POSTGRES_SERVER_VERSION_INVALID")
    return int(match.group("major"))


def parse_client_version(tool: str, output: str) -> ClientInfo:
    match = CLIENT_VERSION_PATTERN.fullmatch(output.strip())
    if not match or match.group("tool") != tool:
        raise SafeOperationError("POSTGRES_CLIENT_VERSION_INVALID", tool=tool)
    version = match.group("version")
    major_match = re.match(r"^(\d+)", version)
    if major_match is None:
        raise SafeOperationError("POSTGRES_CLIENT_VERSION_INVALID", tool=tool)
    return ClientInfo(tool=tool, version=version, major=int(major_match.group(1)))


def client_info(tool: str) -> ClientInfo:
    completed = subprocess.run(
        [tool, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_client_version(tool, completed.stdout)


def database_parts(environment_name: str) -> tuple[str, dict[str, str], list[str]]:
    value = os.getenv(environment_name, "").strip()
    parsed = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("Configured database URL must be PostgreSQL.")
    database = parsed.path.lstrip("/")
    env = os.environ.copy()
    env["PGPASSWORD"] = unquote(parsed.password or "")
    args = [
        "--host",
        parsed.hostname,
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or ""),
        "--dbname",
        database,
    ]
    return value.replace("postgresql+psycopg://", "postgresql://", 1), env, args


def database_name_from_url(value: str) -> str:
    parsed = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    database = unquote(parsed.path.lstrip("/"))
    if parsed.scheme != "postgresql" or not parsed.hostname or not database or "/" in database:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="database_url"
        )
    return database


def expected_restore_test_database_names(run_id: str) -> tuple[str, str]:
    if RESTORE_RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="run_id"
        )
    suffix = run_id.replace("-", "_")
    return (
        f"{RESTORE_SOURCE_DATABASE_PREFIX}{suffix}",
        f"{DISPOSABLE_DATABASE_PREFIX}{suffix}",
    )


def validate_restore_test_database_names(
    run_id: str,
    source_database: str,
    target_database: str,
    source_database_url: str,
    target_database_url: str,
) -> None:
    expected_source, expected_target = expected_restore_test_database_names(run_id)
    values = {
        "source_database": source_database,
        "target_database": target_database,
    }
    for field, database in values.items():
        if (
            database.lower() in FORBIDDEN_TEST_DATABASE_NAMES
            or "test" not in database.lower()
            or len(database.encode("utf-8")) > POSTGRES_IDENTIFIER_MAX_BYTES
            or re.fullmatch(r"[a-z0-9_]+", database) is None
        ):
            raise SafeOperationError(
                "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field=field
            )
    if source_database != expected_source or target_database != expected_target:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="database_identity"
        )
    if source_database == target_database:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="database_separation"
        )
    if database_name_from_url(source_database_url) != source_database:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="source_database_url"
        )
    if database_name_from_url(target_database_url) != target_database:
        raise SafeOperationError(
            "RESTORE_TEST_DATABASE_NAME_INVALID", failure_field="target_database_url"
        )


def server_info(database_url: str) -> ServerInfo:
    with psycopg.connect(database_url) as connection:
        version = str(connection.execute("SHOW server_version").fetchone()[0])
        version_num = int(connection.execute("SHOW server_version_num").fetchone()[0])
    return ServerInfo(version=version, version_num=version_num, major=parse_server_major(version_num))


def compatibility_error(preflight: PostgresPreflight) -> SafeOperationError:
    return SafeOperationError(
        "POSTGRES_CLIENT_MAJOR_MISMATCH",
        server_major=preflight.server.major,
        pg_dump_major=preflight.pg_dump.major,
        pg_restore_major=preflight.pg_restore.major,
        tool_image=preflight.tool_image.reference,
    )


def validate_backup_preflight(preflight: PostgresPreflight) -> None:
    majors = {
        preflight.server.major,
        preflight.pg_dump.major,
        preflight.pg_restore.major,
        preflight.psql.major,
    }
    if majors != {EXPECTED_POSTGRES_MAJOR}:
        raise compatibility_error(preflight)


def validate_restore_preflight(manifest: dict[str, Any], preflight: PostgresPreflight) -> None:
    validate_backup_preflight(preflight)
    manifest_majors = {
        manifest.get("database_server_major"),
        manifest.get("pg_dump_major"),
        manifest.get("pg_restore_major"),
        manifest.get("expected_restore_target_major"),
    }
    if manifest_majors != {EXPECTED_POSTGRES_MAJOR}:
        raise SafeOperationError(
            "POSTGRES_RESTORE_MAJOR_MISMATCH",
            archive_pg_dump_major=int(manifest.get("pg_dump_major", -1)),
            pg_restore_major=preflight.pg_restore.major,
            target_server_major=preflight.server.major,
            tool_image=preflight.tool_image.reference,
        )
    if manifest.get("pg_dump_tool_image_digest") != preflight.tool_image.digest:
        raise SafeOperationError(
            "POSTGRES_RESTORE_TOOL_IMAGE_MISMATCH",
            pg_restore_major=preflight.pg_restore.major,
            target_server_major=preflight.server.major,
            tool_image=preflight.tool_image.reference,
        )


def postgres_preflight(database_url: str) -> PostgresPreflight:
    preflight = PostgresPreflight(
        server=server_info(database_url),
        pg_dump=client_info("pg_dump"),
        pg_restore=client_info("pg_restore"),
        psql=client_info("psql"),
        server_image=configured_image("POSTGRES_SERVER_IMAGE"),
        tool_image=configured_image("POSTGRES_TOOL_IMAGE"),
    )
    validate_backup_preflight(preflight)
    return preflight


def safe_files(root: Path) -> list[Path]:
    if root.is_symlink():
        raise ValueError("File storage root cannot be a symlink.")
    root = root.resolve(strict=True)
    values: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("File storage contains a symlink.")
        if path.is_file():
            values.append(path)
    return values


def _rows_checksum(rows: list[tuple[object, ...]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            json.dumps(row, default=str, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def _normalize_sql_definition(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _database_inventory(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    database_row = connection.execute(
        """
        SELECT database_record.datname,
               pg_encoding_to_char(database_record.encoding),
               database_record.datcollate,
               database_record.datctype,
               owner.rolname
        FROM pg_database AS database_record
        JOIN pg_roles AS owner ON owner.oid = database_record.datdba
        WHERE database_record.datname = current_database()
        """
    ).fetchone()
    if database_row is None:
        raise SafeOperationError("POSTGRES_DATABASE_INVENTORY_FAILED")
    extension_rows = connection.execute(
        """
        SELECT extension.extname, extension.extversion, namespace.nspname, owner.rolname
        FROM pg_extension AS extension
        JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace
        JOIN pg_roles AS owner ON owner.oid = extension.extowner
        ORDER BY extension.extname
        """
    ).fetchall()
    schema_rows = connection.execute(
        """
        SELECT namespace.nspname, owner.rolname,
               COALESCE(array_to_string(namespace.nspacl, ','), '')
        FROM pg_namespace AS namespace
        JOIN pg_roles AS owner ON owner.oid = namespace.nspowner
        WHERE namespace.nspname = 'public'
        ORDER BY namespace.nspname
        """
    ).fetchall()
    table_rows = connection.execute(
        """
        SELECT schemaname, tablename, tableowner
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY schemaname, tablename
        """
    ).fetchall()
    tables = [str(row[1]) for row in table_rows]
    missing = sorted(REQUIRED_TABLES.difference(tables))
    if missing:
        raise SafeOperationError("POSTGRES_REQUIRED_TABLES_MISSING", count=len(missing))

    counts: dict[str, int] = {}
    table_checksums: dict[str, str] = {}
    for schema_name, table_name, _owner in table_rows:
        key = f"{schema_name}.{table_name}"
        identifier = sql.Identifier(str(schema_name), str(table_name))
        counts[key] = int(
            connection.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(identifier)).fetchone()[0]
        )
        json_rows = connection.execute(
            sql.SQL(
                "SELECT to_jsonb(table_row)::text FROM {} AS table_row "
                "ORDER BY to_jsonb(table_row)::text"
            ).format(identifier)
        ).fetchall()
        table_checksums[key] = _rows_checksum(json_rows)

    foreign_keys = connection.execute(
        """
        SELECT namespace.nspname, relation.relname, constraint_record.conname,
               pg_get_constraintdef(constraint_record.oid, true),
               constraint_record.convalidated
        FROM pg_constraint AS constraint_record
        JOIN pg_class AS relation ON relation.oid = constraint_record.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE constraint_record.contype = 'f' AND namespace.nspname = 'public'
        ORDER BY namespace.nspname, relation.relname, constraint_record.conname
        """
    ).fetchall()
    if any(not bool(row[4]) for row in foreign_keys):
        raise SafeOperationError("POSTGRES_FOREIGN_KEY_NOT_VALIDATED")

    key_constraints = connection.execute(
        """
        SELECT namespace.nspname, relation.relname, constraint_record.conname,
               constraint_record.contype,
               pg_get_constraintdef(constraint_record.oid, true),
               constraint_record.convalidated
        FROM pg_constraint AS constraint_record
        JOIN pg_class AS relation ON relation.oid = constraint_record.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE constraint_record.contype IN ('p', 'u')
          AND namespace.nspname = 'public'
        ORDER BY namespace.nspname, relation.relname, constraint_record.conname
        """
    ).fetchall()

    sequence_metadata = connection.execute(
        """
        SELECT schemaname, sequencename, sequenceowner, data_type, start_value,
               min_value, max_value, increment_by, cycle, cache_size, last_value
        FROM pg_sequences
        WHERE schemaname = 'public'
        ORDER BY schemaname, sequencename
        """
    ).fetchall()
    sequences: list[tuple[object, ...]] = []
    sequence_items: dict[str, dict[str, object]] = {}
    for sequence_row in sequence_metadata:
        state = connection.execute(
            sql.SQL("SELECT last_value, is_called FROM {}").format(
                sql.Identifier(str(sequence_row[0]), str(sequence_row[1]))
            )
        ).fetchone()
        sequences.append((*sequence_row, *state))
        owned_row = connection.execute(
            """
            SELECT table_namespace.nspname, table_record.relname, attribute.attname
            FROM pg_class AS sequence_record
            JOIN pg_namespace AS sequence_namespace
              ON sequence_namespace.oid = sequence_record.relnamespace
            LEFT JOIN pg_depend AS dependency
              ON dependency.classid = 'pg_class'::regclass
             AND dependency.objid = sequence_record.oid
             AND dependency.deptype IN ('a', 'i')
            LEFT JOIN pg_class AS table_record ON table_record.oid = dependency.refobjid
            LEFT JOIN pg_namespace AS table_namespace
              ON table_namespace.oid = table_record.relnamespace
            LEFT JOIN pg_attribute AS attribute
              ON attribute.attrelid = table_record.oid
             AND attribute.attnum = dependency.refobjsubid
            WHERE sequence_namespace.nspname = %s
              AND sequence_record.relname = %s
              AND sequence_record.relkind = 'S'
            ORDER BY table_namespace.nspname, table_record.relname, attribute.attname
            LIMIT 1
            """,
            (str(sequence_row[0]), str(sequence_row[1])),
        ).fetchone()
        sequence_name = f"{sequence_row[0]}.{sequence_row[1]}"
        sequence_items[sequence_name] = {
            "owner": str(sequence_row[2]),
            "data_type": str(sequence_row[3]),
            "start_value": str(sequence_row[4]),
            "min_value": str(sequence_row[5]),
            "max_value": str(sequence_row[6]),
            "increment": str(sequence_row[7]),
            "cycle": bool(sequence_row[8]),
            "cache_size": str(sequence_row[9]),
            "last_value": str(state[0]),
            "is_called": bool(state[1]),
            "owned_by": (
                ".".join(str(value) for value in owned_row)
                if owned_row and all(value is not None for value in owned_row)
                else None
            ),
        }
    indexes = connection.execute(
        """
        SELECT namespace.nspname, table_record.relname, index_record.relname,
               pg_get_indexdef(index_record.oid), index_metadata.indisunique,
               index_metadata.indisvalid, owner.rolname
        FROM pg_index AS index_metadata
        JOIN pg_class AS index_record ON index_record.oid = index_metadata.indexrelid
        JOIN pg_class AS table_record ON table_record.oid = index_metadata.indrelid
        JOIN pg_namespace AS namespace ON namespace.oid = table_record.relnamespace
        JOIN pg_roles AS owner ON owner.oid = index_record.relowner
        WHERE namespace.nspname = 'public'
        ORDER BY namespace.nspname, table_record.relname, index_record.relname
        """
    ).fetchall()
    missing_indexes = sorted(REQUIRED_INDEXES.difference(str(row[2]) for row in indexes))
    if missing_indexes:
        raise SafeOperationError("POSTGRES_REQUIRED_INDEXES_MISSING", count=len(missing_indexes))
    ownership = [(str(row[0]), str(row[1]), str(row[2])) for row in table_rows]
    function_rows = connection.execute(
        """
        SELECT namespace.nspname, procedure.proname,
               pg_get_function_identity_arguments(procedure.oid), owner.rolname,
               pg_get_functiondef(procedure.oid)
        FROM pg_proc AS procedure
        JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
        JOIN pg_roles AS owner ON owner.oid = procedure.proowner
        WHERE namespace.nspname = 'public'
        ORDER BY namespace.nspname, procedure.proname,
                 pg_get_function_identity_arguments(procedure.oid)
        """
    ).fetchall()
    type_rows = connection.execute(
        """
        SELECT namespace.nspname, type_record.typname, type_record.typtype,
               owner.rolname,
               COALESCE(string_agg(enum_record.enumlabel, ',' ORDER BY enum_record.enumsortorder), '')
        FROM pg_type AS type_record
        JOIN pg_namespace AS namespace ON namespace.oid = type_record.typnamespace
        JOIN pg_roles AS owner ON owner.oid = type_record.typowner
        LEFT JOIN pg_class AS relation ON relation.reltype = type_record.oid
        LEFT JOIN pg_enum AS enum_record ON enum_record.enumtypid = type_record.oid
        WHERE namespace.nspname = 'public'
          AND relation.oid IS NULL
          AND type_record.typname !~ '^_'
          AND type_record.typtype IN ('d', 'e', 'm', 'r')
        GROUP BY namespace.nspname, type_record.typname, type_record.typtype, owner.rolname
        ORDER BY namespace.nspname, type_record.typname
        """
    ).fetchall()
    revision_row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    revision = str(revision_row[0]) if revision_row else ""

    inventory: dict[str, Any] = {
        "database": {
            "name": str(database_row[0]),
            "encoding": str(database_row[1]),
            "collation": str(database_row[2]),
            "ctype": str(database_row[3]),
            "owner": str(database_row[4]),
            "extensions": {
                str(row[0]): {
                    "version": str(row[1]),
                    "schema": str(row[2]),
                    "owner": str(row[3]),
                }
                for row in extension_rows
            },
        },
        "schemas": {
            str(row[0]): {"owner": str(row[1]), "privileges": str(row[2])}
            for row in schema_rows
        },
        "alembic_revision": revision,
        "tables": [f"{row[0]}.{row[1]}" for row in table_rows],
        "table_details": {
            f"{row[0]}.{row[1]}": {"owner": str(row[2])} for row in table_rows
        },
        "table_row_counts": counts,
        "table_checksums": table_checksums,
        "key_constraints": {
            "count": len(key_constraints),
            "items": {
                f"{row[0]}.{row[1]}.{row[2]}": {
                    "type": "primary_key" if str(row[3]) == "p" else "unique",
                    "definition": _normalize_sql_definition(row[4]),
                    "validated": bool(row[5]),
                }
                for row in key_constraints
            },
            "sha256": _rows_checksum(key_constraints),
        },
        "foreign_keys": {
            "count": len(foreign_keys),
            "items": {
                f"{row[0]}.{row[1]}.{row[2]}": {
                    "definition": _normalize_sql_definition(row[3]),
                    "validated": bool(row[4]),
                }
                for row in foreign_keys
            },
            "sha256": _rows_checksum(foreign_keys),
        },
        "sequences": {
            "count": len(sequences),
            "items": sequence_items,
            "sha256": _rows_checksum(sequences),
        },
        "indexes": {
            "count": len(indexes),
            "names": [str(row[2]) for row in indexes],
            "items": {
                f"{row[0]}.{row[1]}.{row[2]}": {
                    "definition": _normalize_sql_definition(row[3]),
                    "unique": bool(row[4]),
                    "valid": bool(row[5]),
                    "owner": str(row[6]),
                }
                for row in indexes
            },
            "sha256": _rows_checksum(indexes),
        },
        "ownership": {
            "count": len(ownership),
            "items": {f"{row[0]}.{row[1]}": str(row[2]) for row in table_rows},
            "sha256": _rows_checksum(ownership),
        },
        "functions": {
            f"{row[0]}.{row[1]}({row[2]})": {
                "owner": str(row[3]),
                "definition_sha256": hashlib.sha256(
                    _normalize_sql_definition(row[4]).encode("utf-8")
                ).hexdigest(),
            }
            for row in function_rows
        },
        "types": {
            f"{row[0]}.{row[1]}": {
                "kind": str(row[2]),
                "owner": str(row[3]),
                "definition_sha256": hashlib.sha256(str(row[4]).encode("utf-8")).hexdigest(),
            }
            for row in type_rows
        },
        "project_knowledge": {
            "document_count": counts.get("public.knowledge_documents", 0),
            "chunk_count": counts.get("public.knowledge_chunks", 0),
            "documents_sha256": table_checksums.get("public.knowledge_documents", ""),
            "chunks_sha256": table_checksums.get("public.knowledge_chunks", ""),
            "fts_index_valid": any(
                str(row[2]) == "ix_knowledge_chunks_fts" and bool(row[5]) for row in indexes
            ),
        },
        "auth": {
            "user_count": counts.get("public.users", 0),
            "admin_count": int(
                connection.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
            ),
            "authentication_structure_count": int(
                connection.execute(
                    "SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL AND password_hash <> ''"
                ).fetchone()[0]
            ),
        },
    }
    inventory["aggregate_sha256"] = sha256_json(inventory)
    return inventory


def database_inventory(database_url: str) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return _database_inventory(connection)


def _canonical_inventory_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_inventory_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        normalized = [_canonical_inventory_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item, sort_keys=True, default=str, separators=(",", ":")
            ),
        )
    return value


def _owner_inventory_path(path: str) -> bool:
    return path.endswith(".owner") or path.startswith("ownership.items.")


def parse_owner_mappings(values: list[str] | None) -> dict[str, str]:
    """Parse an explicit, narrow source-role to restore-role policy."""
    mappings: dict[str, str] = {}
    for index, value in enumerate(values or []):
        if value.count("=") != 1:
            raise SafeOperationError(
                "RESTORE_OWNER_MAPPING_INVALID", failure_field=f"mapping_{index}"
            )
        source_owner, target_owner = value.split("=", 1)
        if (
            POSTGRES_ROLE_NAME_PATTERN.fullmatch(source_owner) is None
            or POSTGRES_ROLE_NAME_PATTERN.fullmatch(target_owner) is None
            or source_owner == target_owner
            or source_owner in mappings
        ):
            raise SafeOperationError(
                "RESTORE_OWNER_MAPPING_INVALID", failure_field=f"mapping_{index}"
            )
        mappings[source_owner] = target_owner
    return mappings


def compare_database_inventories(
    source: dict[str, Any],
    target: dict[str, Any],
    allowed_owner_mapping: dict[str, str] | None = None,
    allow_isolated_database_name_difference: bool = False,
) -> dict[str, Any]:
    owner_mapping = allowed_owner_mapping or {}
    missing: list[dict[str, object]] = []
    extra: list[dict[str, object]] = []
    mismatched: list[dict[str, object]] = []
    normalized_fields: list[dict[str, str]] = []
    ignored: list[dict[str, object]] = []

    source_value = _canonical_inventory_value(source)
    target_value = _canonical_inventory_value(target)

    def compare(path: str, expected: Any, actual: Any) -> None:
        path_field = path.rsplit(".", 1)[-1]
        if path_field in {"oid", "database_oid", "table_oid", "index_oid", "relfilenode"}:
            ignored.append(
                {
                    "path": path,
                    "source": expected,
                    "target": actual,
                    "reason": "PostgreSQL physical object identity is environment-specific.",
                }
            )
            return
        if path == "aggregate_sha256":
            ignored.append(
                {
                    "path": path,
                    "reason": "Derived from the detailed inventory and would duplicate field-level differences.",
                }
            )
            return
        if path in {
            "key_constraints.sha256",
            "foreign_keys.sha256",
            "sequences.sha256",
            "indexes.sha256",
            "ownership.sha256",
        }:
            ignored.append(
                {
                    "path": path,
                    "reason": "Derived from the corresponding detailed object inventory.",
                }
            )
            return
        if path == "database.name":
            if allow_isolated_database_name_difference:
                ignored.append(
                    {
                        "path": path,
                        "source": expected,
                        "target": actual,
                        "reason": "An explicitly authorized isolated restore target uses a different database name.",
                    }
                )
                return
        if path.startswith("schemas.") and path.endswith(".privileges"):
            ignored.append(
                {
                    "path": path,
                    "source": expected,
                    "target": actual,
                    "reason": "The controlled archive is created and restored with no privileges/no ACL policy.",
                }
            )
            return
        if isinstance(expected, dict) and isinstance(actual, dict):
            source_keys = set(expected)
            target_keys = set(actual)
            for key in sorted(source_keys - target_keys):
                missing.append({"path": f"{path}.{key}".lstrip("."), "source": expected[key]})
            for key in sorted(target_keys - source_keys):
                extra.append({"path": f"{path}.{key}".lstrip("."), "target": actual[key]})
            for key in sorted(source_keys & target_keys):
                compare(f"{path}.{key}".lstrip("."), expected[key], actual[key])
            return
        if isinstance(expected, list) and isinstance(actual, list):
            if expected != actual:
                mismatched.append({"path": path, "source": expected, "target": actual})
            return
        normalized_expected = expected
        if _owner_inventory_path(path) and isinstance(expected, str) and expected in owner_mapping:
            normalized_expected = owner_mapping[expected]
            normalized_fields.append(
                {
                    "path": path,
                    "source_owner": expected,
                    "expected_target_owner": normalized_expected,
                    "reason": "Explicit no-owner restore role mapping.",
                }
            )
        if normalized_expected != actual:
            mismatched.append({"path": path, "source": expected, "target": actual})

    compare("", source_value, target_value)
    return {
        "status": "passed" if not (missing or extra or mismatched) else "failed",
        "missing_in_target": missing,
        "extra_in_target": extra,
        "value_mismatch": mismatched,
        "ignored_non_deterministic_fields": ignored,
        "normalized_fields": normalized_fields,
        "final_mismatch_count": len(missing) + len(extra) + len(mismatched),
        "secrets_included": False,
    }


def write_inventory_diff_report(
    destination: Path,
    source: dict[str, Any],
    target: dict[str, Any],
    manifest: dict[str, Any],
    diff: dict[str, Any],
) -> None:
    if destination.exists() and destination.is_symlink():
        raise ValueError("Inventory diff report cannot be a symlink.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.parent.is_symlink():
        raise ValueError("Inventory diff report parent cannot be a symlink.")
    report = {
        "status": diff["status"],
        "validation_code": "POSTGRES_RESTORE_INVENTORY_MISMATCH",
        "archive_sha256": manifest["archive_sha256"],
        "pg_restore_exit_code": 0,
        "source_inventory": source,
        "target_inventory": target,
        "diff": diff,
        "secrets_included": False,
    }
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def database_is_empty(database_url: str) -> bool:
    with psycopg.connect(database_url) as connection:
        return bool(
            connection.execute(
                """
                SELECT NOT EXISTS (
                    SELECT 1
                    FROM pg_class AS relation
                    JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
                    WHERE namespace.nspname = 'public'
                      AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                )
                """
            ).fetchone()[0]
        )


def archive_schema_names(toc: str) -> frozenset[str]:
    schemas: set[str] = set()
    for line in toc.splitlines():
        match = re.match(
            r"^[0-9]+;\s+[0-9]+\s+[0-9]+\s+SCHEMA\s+-\s+(?P<schema>\S+)\s+\S+\s*$",
            line.strip(),
        )
        if match:
            schemas.add(match.group("schema"))
    return frozenset(schemas)


def archive_toc(archive: Path, pg_env: dict[str, str]) -> tuple[str, frozenset[str]]:
    completed = subprocess.run(
        ["pg_restore", "--list", str(archive)],
        env=pg_env,
        check=True,
        capture_output=True,
        text=True,
    )
    toc = completed.stdout or ""
    return toc, archive_schema_names(toc)


def disposable_target_identity() -> RestoreTargetIdentity:
    return RestoreTargetIdentity(
        enabled=os.getenv("PJA_RESTORE_DISPOSABLE_TARGET", "") == "1",
        project_name=os.getenv("PJA_RESTORE_COMPOSE_PROJECT", "").strip(),
        expected_database=os.getenv("PJA_RESTORE_EXPECTED_DATABASE", "").strip(),
        target_volume=os.getenv("PJA_RESTORE_TARGET_VOLUME", "").strip(),
    )


def _user_schema_filter(alias: str) -> str:
    return (
        f"{alias}.nspname NOT IN ('pg_catalog', 'information_schema') "
        f"AND {alias}.nspname !~ '^pg_(toast|temp|toast_temp)'"
    )


def _restore_target_structure(connection: psycopg.Connection[Any]) -> RestoreTargetStructure:
    database_name = str(connection.execute("SELECT current_database()").fetchone()[0])
    schemas = tuple(
        str(row[0])
        for row in connection.execute(
            f"SELECT namespace.nspname FROM pg_namespace AS namespace "
            f"WHERE {_user_schema_filter('namespace')} ORDER BY namespace.nspname"
        ).fetchall()
    )
    relation_rows = connection.execute(
        f"""
        SELECT relation.relkind, COUNT(*)
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE {_user_schema_filter('namespace')}
          AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'i', 'I')
        GROUP BY relation.relkind
        """
    ).fetchall()
    relation_counts = {str(row[0]): int(row[1]) for row in relation_rows}
    function_count = int(
        connection.execute(
            f"""
            SELECT COUNT(*) FROM pg_proc AS procedure
            JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
            WHERE {_user_schema_filter('namespace')}
            """
        ).fetchone()[0]
    )
    type_count = int(
        connection.execute(
            f"""
            SELECT COUNT(*) FROM pg_type AS type_record
            JOIN pg_namespace AS namespace ON namespace.oid = type_record.typnamespace
            WHERE {_user_schema_filter('namespace')}
            """
        ).fetchone()[0]
    )
    extension_count = int(
        connection.execute("SELECT COUNT(*) FROM pg_extension WHERE extname <> 'plpgsql'").fetchone()[0]
    )
    public_dependency_count = int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM pg_depend AS dependency
            JOIN pg_namespace AS namespace ON namespace.oid = dependency.refobjid
            WHERE dependency.refclassid = 'pg_namespace'::regclass
              AND namespace.nspname = 'public'
            """
        ).fetchone()[0]
    )
    writable = bool(
        connection.execute(
            "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
        ).fetchone()[0]
    )
    return RestoreTargetStructure(
        database_name=database_name,
        schemas=schemas,
        relation_count=sum(relation_counts.values()),
        sequence_count=relation_counts.get("S", 0),
        function_count=function_count,
        type_count=type_count,
        extension_count=extension_count,
        public_dependency_count=public_dependency_count,
        writable=writable,
    )


def validate_disposable_target_identity(
    structure: RestoreTargetStructure,
    identity: RestoreTargetIdentity,
) -> None:
    project_match = DISPOSABLE_PROJECT_PATTERN.fullmatch(identity.project_name)
    database_match = DISPOSABLE_DATABASE_PATTERN.fullmatch(identity.expected_database)
    if (
        not identity.enabled
        or project_match is None
        or database_match is None
        or project_match.group("run_id").replace("-", "_")
        != database_match.group("run_id")
        or structure.database_name != identity.expected_database
        or identity.target_volume != f"{identity.project_name}_target-data"
    ):
        raise SafeOperationError("RESTORE_TARGET_NOT_DISPOSABLE")


def target_public_schema_drop_required(
    archive_schemas: frozenset[str],
    structure: RestoreTargetStructure,
    identity: RestoreTargetIdentity,
) -> bool:
    extra_schemas = set(structure.schemas).difference({"public"})
    if extra_schemas:
        raise SafeOperationError(
            "RESTORE_TARGET_SCHEMA_CONFLICT",
            schema_count=len(structure.schemas),
            extra_schema_count=len(extra_schemas),
        )
    if structure.object_count or not structure.writable:
        raise SafeOperationError(
            "RESTORE_TARGET_PUBLIC_SCHEMA_NOT_EMPTY",
            relation_count=structure.relation_count,
            sequence_count=structure.sequence_count,
            function_count=structure.function_count,
            type_count=structure.type_count,
            extension_count=structure.extension_count,
            dependency_count=structure.public_dependency_count,
        )
    collision = structure.public_exists and "public" in archive_schemas
    if not collision:
        return False
    if not identity.enabled:
        raise SafeOperationError(
            "RESTORE_TARGET_SCHEMA_CONFLICT",
            schema_count=len(structure.schemas),
            archive_schema_count=len(archive_schemas),
        )
    validate_disposable_target_identity(structure, identity)
    return True


def _drop_public_schema_restrict(connection: psycopg.Connection[Any]) -> None:
    try:
        connection.execute("DROP SCHEMA public RESTRICT")
    except Exception as exc:
        raise SafeOperationError("RESTORE_TARGET_PREPARATION_FAILED") from exc


def prepare_restore_target(
    database_url: str,
    archive_schemas: frozenset[str],
    allow_disposable_target_preparation: bool,
) -> RestoreTargetStructure:
    identity = disposable_target_identity()
    if allow_disposable_target_preparation and not identity.enabled:
        raise SafeOperationError("RESTORE_TARGET_NOT_DISPOSABLE")
    with psycopg.connect(database_url, autocommit=True) as connection:
        before = _restore_target_structure(connection)
        should_drop = target_public_schema_drop_required(
            archive_schemas,
            before,
            identity if allow_disposable_target_preparation else RestoreTargetIdentity(False, "", "", ""),
        )
        if should_drop:
            if not allow_disposable_target_preparation:
                raise SafeOperationError("RESTORE_TARGET_SCHEMA_CONFLICT", schema_count=1)
            _drop_public_schema_restrict(connection)
            after = _restore_target_structure(connection)
            if after.public_exists or after.schemas or after.object_count or not after.writable:
                raise SafeOperationError("RESTORE_TARGET_PREPARATION_FAILED")
            return after
        return before


def _manifest(preflight: PostgresPreflight, inventory: dict[str, Any], temporary: Path) -> dict[str, Any]:
    archive_sha256 = sha256_file(temporary / "postgres.dump")
    return {
        "manifest_version": MANIFEST_VERSION,
        "application_version": APPLICATION_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alembic_revision": inventory["alembic_revision"],
        "database_server_version": preflight.server.version,
        "database_server_version_num": preflight.server.version_num,
        "database_server_major": preflight.server.major,
        "postgresql_server_image": preflight.server_image.name,
        "postgresql_server_image_digest": preflight.server_image.digest,
        "pg_dump_version": preflight.pg_dump.version,
        "pg_dump_major": preflight.pg_dump.major,
        "pg_restore_version": preflight.pg_restore.version,
        "pg_restore_major": preflight.pg_restore.major,
        "psql_version": preflight.psql.version,
        "psql_major": preflight.psql.major,
        "pg_dump_tool_image": preflight.tool_image.name,
        "pg_dump_tool_image_digest": preflight.tool_image.digest,
        "expected_restore_target_major": EXPECTED_POSTGRES_MAJOR,
        "archive_format": ARCHIVE_FORMAT,
        "archive_sha256": archive_sha256,
        "database_inventory": inventory,
        "table_row_counts": inventory["table_row_counts"],
        "files": {
            name: sha256_file(temporary / name)
            for name in ("postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md")
        },
    }


def create_backup(database_url_env: str, files_root: Path, knowledge: Path, destination: Path) -> Path:
    database_url, pg_env, pg_args = database_parts(database_url_env)
    preflight = postgres_preflight(database_url)
    if files_root.is_symlink() or knowledge.is_symlink() or destination.is_symlink():
        raise ValueError("Backup source and destination paths cannot be symlinks.")
    files_root = files_root.resolve(strict=True)
    knowledge = knowledge.resolve(strict=True)
    destination = destination.resolve(strict=False)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    minimum_free_mb = int(os.getenv("BACKUP_MINIMUM_FREE_DISK_MB", "256"))
    if minimum_free_mb < 16:
        raise ValueError("Backup minimum free disk threshold is invalid.")
    if shutil.disk_usage(destination).free < minimum_free_mb * 1024 * 1024:
        raise OSError("Backup destination does not have enough free disk space.")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    final = destination / f"v2-{timestamp}-{uuid4().hex[:8]}"
    temporary = destination / f".{final.name}.incomplete"
    temporary.mkdir(mode=0o700)
    try:
        dump = temporary / "postgres.dump"
        with psycopg.connect(database_url) as snapshot_connection:
            snapshot_connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            snapshot_id = str(
                snapshot_connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            )
            inventory = _database_inventory(snapshot_connection)
            subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    "--schema=public",
                    "--snapshot",
                    snapshot_id,
                    "--file",
                    str(dump),
                    *pg_args,
                ],
                env=pg_env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
        subprocess.run(
            ["pg_restore", "--list", str(dump)],
            env=pg_env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        os.chmod(dump, 0o600)
        archive = temporary / "files.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            for path in safe_files(files_root):
                output.add(path, arcname=path.relative_to(files_root), recursive=False)
        os.chmod(archive, 0o600)
        knowledge_copy = temporary / "PROJECT_KNOWLEDGE.md"
        shutil.copyfile(knowledge, knowledge_copy)
        os.chmod(knowledge_copy, 0o600)
        manifest = _manifest(preflight, inventory, temporary)
        manifest_path = temporary / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(manifest_path, 0o600)
        os.replace(temporary, final)
        return final
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validate_manifest(manifest: object) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    required = {
        "manifest_version",
        "application_version",
        "created_at",
        "alembic_revision",
        "database_server_version",
        "database_server_version_num",
        "database_server_major",
        "postgresql_server_image",
        "postgresql_server_image_digest",
        "pg_dump_version",
        "pg_dump_major",
        "pg_restore_version",
        "pg_restore_major",
        "psql_version",
        "psql_major",
        "pg_dump_tool_image",
        "pg_dump_tool_image_digest",
        "expected_restore_target_major",
        "archive_format",
        "archive_sha256",
        "database_inventory",
        "table_row_counts",
        "files",
    }
    if not required.issubset(manifest) or manifest.get("manifest_version") != MANIFEST_VERSION:
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    if manifest.get("archive_format") != ARCHIVE_FORMAT:
        raise SafeOperationError("BACKUP_ARCHIVE_FORMAT_INVALID")
    digest_fields = (
        "postgresql_server_image_digest",
        "pg_dump_tool_image_digest",
        "archive_sha256",
    )
    if any(
        not re.fullmatch(
            r"sha256:[0-9a-f]{64}" if key != "archive_sha256" else r"[0-9a-f]{64}",
            str(manifest.get(key, "")),
        )
        for key in digest_fields
    ):
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    try:
        created_at = datetime.fromisoformat(str(manifest["created_at"]))
        if created_at.tzinfo is None:
            raise ValueError
        server_major = parse_server_major(manifest["database_server_version_num"])
        server_version_major = parse_server_version(str(manifest["database_server_version"]))
        integer_fields = (
            "database_server_major",
            "pg_dump_major",
            "pg_restore_major",
            "psql_major",
            "expected_restore_target_major",
        )
        majors = {int(manifest[field]) for field in integer_fields}
        client_versions = {
            tool: parse_client_version(
                tool,
                f"{tool} (PostgreSQL) {manifest[f'{tool}_version']}",
            )
            for tool in ("pg_dump", "pg_restore", "psql")
        }
    except (TypeError, ValueError, SafeOperationError) as exc:
        raise SafeOperationError("BACKUP_MANIFEST_INVALID") from exc
    if (
        manifest["application_version"] != APPLICATION_VERSION
        or server_major != int(manifest["database_server_major"])
        or server_version_major != server_major
        or majors != {EXPECTED_POSTGRES_MAJOR}
        or any(
            parsed.major != int(manifest[f"{tool}_major"])
            for tool, parsed in client_versions.items()
        )
    ):
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    parse_image_reference(
        f"{manifest['postgresql_server_image']}@{manifest['postgresql_server_image_digest']}",
        "postgresql_server_image",
    )
    parse_image_reference(
        f"{manifest['pg_dump_tool_image']}@{manifest['pg_dump_tool_image_digest']}",
        "pg_dump_tool_image",
    )
    inventory = manifest.get("database_inventory")
    if not isinstance(inventory, dict):
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    inventory_without_aggregate = dict(inventory)
    aggregate = inventory_without_aggregate.pop("aggregate_sha256", None)
    tables = inventory.get("tables")
    counts = inventory.get("table_row_counts")
    table_checksums = inventory.get("table_checksums")
    foreign_keys = inventory.get("foreign_keys")
    sequences = inventory.get("sequences")
    indexes = inventory.get("indexes")
    ownership = inventory.get("ownership")
    checksum_sections = (foreign_keys, sequences, indexes, ownership)
    if (
        not isinstance(tables, list)
        or len(tables) != len(set(tables))
        or any(not re.fullmatch(r"public\.[A-Za-z_][A-Za-z0-9_]*", str(table)) for table in tables)
        or not isinstance(counts, dict)
        or any(type(count) is not int or count < 0 for count in counts.values())
        or not isinstance(table_checksums, dict)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(digest)) for digest in table_checksums.values())
        or any(not isinstance(section, dict) for section in checksum_sections)
        or any(
            type(section.get("count")) is not int
            or section["count"] < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(section.get("sha256", "")))
            for section in checksum_sections
        )
        or not isinstance(indexes, dict)
        or not isinstance(indexes.get("names"), list)
        or indexes.get("count") != len(indexes.get("names", []))
        or not REQUIRED_TABLES.issubset(
            str(table).removeprefix("public.") for table in tables
        )
        or not REQUIRED_INDEXES.issubset(str(name) for name in indexes.get("names", []))
        or set(counts) != set(tables)
        or set(table_checksums) != set(tables)
        or manifest.get("table_row_counts") != counts
        or manifest.get("alembic_revision") != inventory.get("alembic_revision")
        or not re.fullmatch(r"[0-9a-f]{64}", str(aggregate or ""))
        or sha256_json(inventory_without_aggregate) != aggregate
    ):
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    return manifest


def verify_backup(backup: Path) -> dict[str, Any]:
    if backup.is_symlink():
        raise ValueError("Backup directory cannot be a symlink.")
    backup = backup.resolve(strict=True)
    if any(path.is_symlink() for path in backup.iterdir()):
        raise ValueError("Backup directory cannot contain symlinks.")
    actual_entries = {path.name for path in backup.iterdir()}
    expected_entries = {"manifest.json", "postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md"}
    if actual_entries != expected_entries or not all(
        (backup / name).is_file() for name in expected_entries
    ):
        raise SafeOperationError("BACKUP_FILE_SET_INVALID")
    try:
        raw_manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafeOperationError("BACKUP_MANIFEST_INVALID") from exc
    manifest = _validate_manifest(raw_manifest)
    expected = {"postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md"}
    if set(manifest.get("files", {})) != expected:
        raise SafeOperationError("BACKUP_MANIFEST_INVALID")
    for name, digest in manifest["files"].items():
        if (
            Path(name).name != name
            or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
            or sha256_file(backup / name) != digest
        ):
            raise SafeOperationError("BACKUP_CHECKSUM_MISMATCH")
    if sha256_file(backup / "postgres.dump") != manifest["archive_sha256"]:
        raise SafeOperationError("BACKUP_CHECKSUM_MISMATCH")
    with tarfile.open(backup / "files.tar.gz", "r:gz") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("File archive contains an unsafe member.")
    return manifest


def restore_backup(
    database_url_env: str,
    backup: Path,
    files_root: Path,
    knowledge: Path,
    confirmation: str,
    allow_disposable_target_preparation: bool = False,
    inventory_diff_report: Path | None = None,
    allowed_owner_mapping: dict[str, str] | None = None,
    allow_isolated_database_name_difference: bool = False,
) -> None:
    if confirmation != "RESTORE V2 BACKUP":
        raise ValueError("Restore confirmation did not match.")
    manifest = verify_backup(backup)
    database_url, pg_env, pg_args = database_parts(database_url_env)
    preflight = postgres_preflight(database_url)
    validate_restore_preflight(manifest, preflight)
    if not database_is_empty(database_url):
        raise SafeOperationError("POSTGRES_RESTORE_TARGET_NOT_EMPTY")
    if files_root.is_symlink() or knowledge.is_symlink():
        raise ValueError("Restore targets cannot be symlinks.")
    files_root = files_root.resolve(strict=False)
    if files_root.exists() and any(files_root.iterdir()):
        raise ValueError("Restore file target is not empty.")
    if knowledge.exists():
        raise ValueError("Restore Project Knowledge target already exists.")
    if knowledge.parent.exists() and knowledge.parent.is_symlink():
        raise ValueError("Restore Project Knowledge parent cannot be a symlink.")

    backup = backup.resolve(strict=True)
    _toc, archive_schemas = archive_toc(backup / "postgres.dump", pg_env)
    prepare_restore_target(
        database_url,
        archive_schemas,
        allow_disposable_target_preparation,
    )
    subprocess.run(
        [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--single-transaction",
            *pg_args,
            str(backup / "postgres.dump"),
        ],
        env=pg_env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    restored_inventory = database_inventory(database_url)
    inventory_diff = compare_database_inventories(
        manifest["database_inventory"],
        restored_inventory,
        allowed_owner_mapping,
        allow_isolated_database_name_difference,
    )
    if inventory_diff["final_mismatch_count"]:
        if inventory_diff_report is not None:
            write_inventory_diff_report(
                inventory_diff_report,
                manifest["database_inventory"],
                restored_inventory,
                manifest,
                inventory_diff,
            )
        raise SafeOperationError(
            "POSTGRES_RESTORE_INVENTORY_MISMATCH",
            mismatch_count=int(inventory_diff["final_mismatch_count"]),
        )

    files_root.mkdir(parents=True, exist_ok=True, mode=0o750)
    with tarfile.open(backup / "files.tar.gz", "r:gz") as archive:
        archive.extractall(files_root, filter="data")
    knowledge.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
    shutil.copyfile(backup / "PROJECT_KNOWLEDGE.md", knowledge)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    test_names = commands.add_parser("validate-test-database-names")
    test_names.add_argument("--run-id", required=True)
    test_names.add_argument("--source-database-name", required=True)
    test_names.add_argument("--target-database-name", required=True)
    test_names.add_argument(
        "--source-database-url-env", default="PJA_TEST_SOURCE_DATABASE_URL"
    )
    test_names.add_argument(
        "--target-database-url-env", default="PJA_TEST_TARGET_DATABASE_URL"
    )
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--database-url-env", default="DATABASE_URL")
    backup = commands.add_parser("backup")
    backup.add_argument("--database-url-env", default="DATABASE_URL")
    backup.add_argument("--backup-dir", type=Path, default=Path("runtime/backups"))
    backup.add_argument("--files-root", type=Path, default=Path("runtime/files"))
    backup.add_argument(
        "--project-knowledge",
        type=Path,
        default=Path("runtime/project-knowledge/PROJECT_KNOWLEDGE.md"),
    )
    verify = commands.add_parser("verify")
    verify.add_argument("--backup", type=Path, required=True)
    restore = commands.add_parser("restore")
    restore.add_argument("--database-url-env", default="DATABASE_URL")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--files-root", type=Path, default=Path("runtime/files"))
    restore.add_argument(
        "--project-knowledge",
        type=Path,
        default=Path("runtime/project-knowledge/PROJECT_KNOWLEDGE.md"),
    )
    restore.add_argument("--confirmation", required=True)
    restore.add_argument("--prepare-disposable-target", action="store_true")
    restore.add_argument("--inventory-diff-report", type=Path)
    restore.add_argument(
        "--allowed-owner-mapping",
        action="append",
        default=[],
        metavar="SOURCE_ROLE=TARGET_ROLE",
        help="Explicit role mapping required by a controlled --no-owner restore.",
    )
    restore.add_argument(
        "--allow-isolated-database-name-difference",
        action="store_true",
        help="Allow only an already identity-guarded isolated target database name to differ.",
    )
    return root


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, SafeOperationError):
        fields = " ".join(f"{key}={value}" for key, value in sorted(exc.summary.items()))
        return f"Operation refused safely: {exc.code}{' ' + fields if fields else ''}"
    return f"Operation refused safely: {type(exc).__name__}"


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate-test-database-names":
            validate_restore_test_database_names(
                args.run_id,
                args.source_database_name,
                args.target_database_name,
                os.getenv(args.source_database_url_env, ""),
                os.getenv(args.target_database_url_env, ""),
            )
            print("Restore test database name preflight passed.")
        elif args.command == "preflight":
            database_url, _pg_env, _pg_args = database_parts(args.database_url_env)
            checked = postgres_preflight(database_url)
            print(
                "PostgreSQL compatibility preflight passed: "
                f"server_major={checked.server.major} "
                f"pg_dump_major={checked.pg_dump.major} "
                f"pg_restore_major={checked.pg_restore.major} "
                f"tool_image={checked.tool_image.reference}"
            )
        elif args.command == "backup":
            result = create_backup(
                args.database_url_env,
                args.files_root,
                args.project_knowledge,
                args.backup_dir,
            )
            print(f"Backup created: {result}")
        elif args.command == "verify":
            verify_backup(args.backup)
            print("Backup verification passed.")
        else:
            restore_backup(
                args.database_url_env,
                args.backup,
                args.files_root,
                args.project_knowledge,
                args.confirmation or "",
                args.prepare_disposable_target,
                args.inventory_diff_report,
                parse_owner_mappings(args.allowed_owner_mapping),
                args.allow_isolated_database_name_difference,
            )
            print("Restore completed and verified.")
    except Exception as exc:
        print(_safe_error(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
