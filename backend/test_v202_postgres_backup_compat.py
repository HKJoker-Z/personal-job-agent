import contextlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from app.core.config import load_v2_settings


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from v2_backup_restore import (
    ARCHIVE_FORMAT,
    APPLICATION_VERSION,
    ClientInfo,
    ImageInfo,
    MANIFEST_VERSION,
    PostgresPreflight,
    REQUIRED_INDEXES,
    REQUIRED_TABLES,
    RestoreTargetIdentity,
    RestoreTargetStructure,
    SafeOperationError,
    ServerInfo,
    _safe_error,
    _drop_public_schema_restrict,
    archive_schema_names,
    compare_database_inventories,
    create_backup,
    parse_owner_mappings,
    parse_client_version,
    parse_image_reference,
    parse_server_version,
    restore_backup,
    sha256_file,
    sha256_json,
    target_public_schema_drop_required,
    validate_restore_test_database_names,
    validate_backup_preflight,
    validate_restore_preflight,
    verify_backup,
    write_inventory_diff_report,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def target_structure(**overrides: object) -> RestoreTargetStructure:
    values: dict[str, object] = {
        "database_name": "pja_restore_target_test_1784544727_989283",
        "schemas": ("public",),
        "relation_count": 0,
        "sequence_count": 0,
        "function_count": 0,
        "type_count": 0,
        "extension_count": 0,
        "public_dependency_count": 0,
        "writable": True,
    }
    values.update(overrides)
    return RestoreTargetStructure(**values)


def target_identity(**overrides: object) -> RestoreTargetIdentity:
    project = "pja-pg16-restore-1784544727-989283"
    values: dict[str, object] = {
        "enabled": True,
        "project_name": project,
        "expected_database": "pja_restore_target_test_1784544727_989283",
        "target_volume": f"{project}_target-data",
    }
    values.update(overrides)
    return RestoreTargetIdentity(**values)


def preflight(client_major: int = 16, server_major: int = 16) -> PostgresPreflight:
    return PostgresPreflight(
        server=ServerInfo(f"{server_major}.9", server_major * 10000 + 9, server_major),
        pg_dump=ClientInfo("pg_dump", f"{client_major}.9", client_major),
        pg_restore=ClientInfo("pg_restore", f"{client_major}.9", client_major),
        psql=ClientInfo("psql", f"{client_major}.9", client_major),
        server_image=ImageInfo("postgres:16.9-alpine", DIGEST_A),
        tool_image=ImageInfo("ghcr.io/example/backend:2.0.2", DIGEST_B),
    )


def manifest(major: int = 16, tool_digest: str = DIGEST_B) -> dict[str, object]:
    tables = sorted(f"public.{table}" for table in REQUIRED_TABLES)
    inventory: dict[str, object] = {
        "alembic_revision": "20260717_04",
        "tables": tables,
        "table_row_counts": {table: 0 for table in tables},
        "table_checksums": {table: "0" * 64 for table in tables},
        "foreign_keys": {"count": 0, "sha256": "0" * 64},
        "sequences": {"count": 0, "sha256": "0" * 64},
        "indexes": {
            "count": len(REQUIRED_INDEXES),
            "names": sorted(REQUIRED_INDEXES),
            "sha256": "0" * 64,
        },
        "ownership": {"count": len(tables), "sha256": "0" * 64},
    }
    inventory["aggregate_sha256"] = sha256_json(inventory)
    return {
        "manifest_version": MANIFEST_VERSION,
        "application_version": APPLICATION_VERSION,
        "created_at": "2026-07-20T00:00:00+00:00",
        "alembic_revision": "20260717_04",
        "database_server_version": "16.9",
        "database_server_version_num": 160009,
        "database_server_major": major,
        "postgresql_server_image": "postgres:16.9-alpine",
        "postgresql_server_image_digest": DIGEST_A,
        "pg_dump_version": f"{major}.9",
        "pg_dump_major": major,
        "pg_restore_version": f"{major}.9",
        "pg_restore_major": major,
        "psql_version": f"{major}.9",
        "psql_major": major,
        "pg_dump_tool_image": "ghcr.io/example/backend:2.0.2",
        "pg_dump_tool_image_digest": tool_digest,
        "expected_restore_target_major": major,
        "archive_format": ARCHIVE_FORMAT,
        "archive_sha256": "0" * 64,
        "database_inventory": inventory,
        "table_row_counts": inventory["table_row_counts"],
        "files": {},
    }


class PostgresVersionCompatibilityTest(unittest.TestCase):
    def test_postgresql_16_server_and_clients_pass(self):
        validate_backup_preflight(preflight())

    def test_pg_dump_17_is_rejected_for_postgresql_16(self):
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_CLIENT_MAJOR_MISMATCH"):
            validate_backup_preflight(preflight(client_major=17))

    def test_pg_restore_17_is_rejected_for_postgresql_16_target(self):
        mismatched = preflight()
        mismatched = PostgresPreflight(
            mismatched.server,
            mismatched.pg_dump,
            ClientInfo("pg_restore", "17.10", 17),
            mismatched.psql,
            mismatched.server_image,
            mismatched.tool_image,
        )
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_CLIENT_MAJOR_MISMATCH"):
            validate_restore_preflight(manifest(), mismatched)

    def test_manifest_server_major_mismatch_is_rejected(self):
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_RESTORE_MAJOR_MISMATCH"):
            validate_restore_preflight(manifest(major=17), preflight())

    def test_restore_must_use_same_controlled_tool_digest(self):
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_RESTORE_TOOL_IMAGE_MISMATCH"):
            validate_restore_preflight(manifest(tool_digest=DIGEST_A), preflight())

    def test_client_version_parser_handles_distribution_suffix(self):
        parsed = parse_client_version(
            "pg_dump", "pg_dump (PostgreSQL) 16.9 (Debian 16.9-1.pgdg120+1)\n"
        )
        self.assertEqual((parsed.version, parsed.major), ("16.9", 16))

    def test_server_version_parser_handles_distribution_suffix(self):
        self.assertEqual(parse_server_version("16.9 (Debian 16.9-1.pgdg120+1)"), 16)

    def test_floating_latest_tool_image_is_rejected(self):
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_IMAGE_NOT_IMMUTABLE"):
            parse_image_reference("postgres:latest", "POSTGRES_TOOL_IMAGE")
        with self.assertRaisesRegex(SafeOperationError, "POSTGRES_IMAGE_NOT_IMMUTABLE"):
            parse_image_reference("postgres:16", "POSTGRES_TOOL_IMAGE")

    def test_safe_compatibility_log_contains_no_database_url_or_password(self):
        error = SafeOperationError(
            "POSTGRES_CLIENT_MAJOR_MISMATCH",
            server_major=16,
            pg_dump_major=17,
            pg_restore_major=17,
            tool_image=f"ghcr.io/example/backend:2.0.2@{DIGEST_B}",
        )
        rendered = _safe_error(error)
        self.assertIn("POSTGRES_CLIENT_MAJOR_MISMATCH", rendered)
        self.assertNotIn("postgresql://", rendered)
        self.assertNotIn("secret-password", rendered)
        self.assertEqual(_safe_error(ValueError("secret-password")), "Operation refused safely: ValueError")


class BackupRestoreGateTest(unittest.TestCase):
    def _backup_fixture(self, root: Path) -> Path:
        backup = root / "v2-20260720-000000-aaaaaaaa"
        backup.mkdir()
        (backup / "postgres.dump").write_bytes(b"custom archive")
        with tarfile.open(backup / "files.tar.gz", "w:gz"):
            pass
        (backup / "PROJECT_KNOWLEDGE.md").write_text("safe knowledge\n", encoding="utf-8")
        value = manifest()
        value["archive_sha256"] = sha256_file(backup / "postgres.dump")
        value["files"] = {
            name: sha256_file(backup / name)
            for name in ("postgres.dump", "files.tar.gz", "PROJECT_KNOWLEDGE.md")
        }
        (backup / "manifest.json").write_text(
            json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
        )
        return backup

    def test_archive_checksum_error_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = self._backup_fixture(Path(directory))
            (backup / "postgres.dump").write_bytes(b"corrupt")
            with self.assertRaisesRegex(SafeOperationError, "BACKUP_CHECKSUM_MISMATCH"):
                verify_backup(backup)

    def test_manifest_version_string_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = self._backup_fixture(Path(directory))
            value = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
            value["pg_dump_version"] = "17.10"
            (backup / "manifest.json").write_text(
                json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SafeOperationError, "BACKUP_MANIFEST_INVALID"):
                verify_backup(backup)

    def test_pg_dump_major_failure_occurs_before_dump_or_temporary_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = root / "files"
            files.mkdir()
            knowledge = root / "PROJECT_KNOWLEDGE.md"
            knowledge.write_text("knowledge", encoding="utf-8")
            destination = root / "backups"
            with mock.patch.dict(
                os.environ,
                {"DATABASE_URL": "postgresql://user:secret-password@db/example"},
                clear=False,
            ):
                with mock.patch(
                    "v2_backup_restore.postgres_preflight",
                    side_effect=SafeOperationError("POSTGRES_CLIENT_MAJOR_MISMATCH"),
                ):
                    with mock.patch("v2_backup_restore.subprocess.run") as run:
                        with self.assertRaisesRegex(
                            SafeOperationError, "POSTGRES_CLIENT_MAJOR_MISMATCH"
                        ):
                            create_backup("DATABASE_URL", files, knowledge, destination)
                        run.assert_not_called()
            self.assertFalse(destination.exists())

    def test_nonempty_restore_target_is_rejected_before_pg_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = self._backup_fixture(root)
            with mock.patch.dict(
                os.environ,
                {"DATABASE_URL": "postgresql://user:secret-password@db/example"},
                clear=False,
            ):
                with mock.patch("v2_backup_restore.postgres_preflight", return_value=preflight()):
                    with mock.patch("v2_backup_restore.database_is_empty", return_value=False):
                        with mock.patch("v2_backup_restore.subprocess.run") as run:
                            with self.assertRaisesRegex(
                                SafeOperationError, "POSTGRES_RESTORE_TARGET_NOT_EMPTY"
                            ):
                                restore_backup(
                                    "DATABASE_URL",
                                    backup,
                                    root / "restored-files",
                                    root / "restored-knowledge.md",
                                    "RESTORE V2 BACKUP",
                                )
                            run.assert_not_called()

    def test_pg_restore_nonzero_never_marks_restore_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = self._backup_fixture(root)
            with mock.patch.dict(
                os.environ,
                {"DATABASE_URL": "postgresql://user:secret-password@db/example"},
                clear=False,
            ):
                with mock.patch("v2_backup_restore.postgres_preflight", return_value=preflight()):
                    with mock.patch("v2_backup_restore.database_is_empty", return_value=True):
                        with mock.patch("v2_backup_restore.prepare_restore_target"):
                            with mock.patch(
                                "v2_backup_restore.subprocess.run",
                                side_effect=[
                                    __import__("subprocess").CompletedProcess(
                                        ["pg_restore", "--list"], 0, stdout=""
                                    ),
                                    __import__("subprocess").CalledProcessError(1, "pg_restore"),
                                ],
                            ) as run:
                                with self.assertRaises(__import__("subprocess").CalledProcessError):
                                    restore_backup(
                                        "DATABASE_URL",
                                        backup,
                                        root / "restored-files",
                                        root / "restored-knowledge.md",
                                        "RESTORE V2 BACKUP",
                                    )
                                list_command = run.call_args_list[0].args[0]
                                restore_command = run.call_args_list[-1].args[0]
                                self.assertEqual(list_command[:2], ["pg_restore", "--list"])
                                self.assertIn("--exit-on-error", restore_command)
                                self.assertIn("--single-transaction", restore_command)
                                self.assertNotIn("--clean", restore_command)
                                self.assertFalse((root / "restored-files").exists())

    def test_verify_output_does_not_include_secret_manifest_content(self):
        rendered = io.StringIO()
        with contextlib.redirect_stderr(rendered):
            print(_safe_error(ValueError("secret-password")), file=sys.stderr)
        self.assertNotIn("secret-password", rendered.getvalue())


class RestoreTargetPreparationTest(unittest.TestCase):
    def test_archive_toc_finds_public_schema(self):
        toc = "6; 2615 2200 SCHEMA - public postgres\n7; 1259 1 TABLE public users postgres\n"
        self.assertEqual(archive_schema_names(toc), frozenset({"public"}))

    def test_empty_public_collision_requires_restricted_drop(self):
        self.assertTrue(
            target_public_schema_drop_required(
                frozenset({"public"}), target_structure(), target_identity()
            )
        )

    def test_public_table_function_type_or_sequence_blocks_preparation(self):
        for field in ("relation_count", "function_count", "type_count", "sequence_count"):
            with self.subTest(field=field):
                values = {field: 1}
                if field == "sequence_count":
                    values["relation_count"] = 1
                with self.assertRaisesRegex(
                    SafeOperationError, "RESTORE_TARGET_PUBLIC_SCHEMA_NOT_EMPTY"
                ):
                    target_public_schema_drop_required(
                        frozenset({"public"}), target_structure(**values), target_identity()
                    )

    def test_extra_user_schema_fails_without_deletion(self):
        with self.assertRaisesRegex(SafeOperationError, "RESTORE_TARGET_SCHEMA_CONFLICT"):
            target_public_schema_drop_required(
                frozenset({"public"}),
                target_structure(schemas=("public", "private_fixture")),
                target_identity(),
            )

    def test_non_disposable_database_project_or_volume_is_rejected(self):
        cases = (
            (target_structure(database_name="personal_job_agent_v2"), target_identity()),
            (target_structure(), target_identity(project_name="personal-job-agent-v2")),
            (target_structure(), target_identity(target_volume="personal-job-agent-v2-postgres-data")),
            (
                target_structure(),
                target_identity(project_name="pja-pg16-restore-1784544728-989283"),
            ),
        )
        for structure, identity in cases:
            with self.subTest(structure=structure, identity=identity):
                with self.assertRaisesRegex(SafeOperationError, "RESTORE_TARGET_NOT_DISPOSABLE"):
                    target_public_schema_drop_required(
                        frozenset({"public"}), structure, identity
                    )

    def test_default_restore_mode_reports_schema_collision(self):
        with self.assertRaisesRegex(SafeOperationError, "RESTORE_TARGET_SCHEMA_CONFLICT"):
            target_public_schema_drop_required(
                frozenset({"public"}),
                target_structure(),
                RestoreTargetIdentity(False, "", "", ""),
            )

    def test_archive_without_public_schema_does_not_drop(self):
        self.assertFalse(
            target_public_schema_drop_required(
                frozenset(), target_structure(), RestoreTargetIdentity(False, "", "", "")
            )
        )

    def test_restrict_drop_failure_is_terminal_without_cascade(self):
        class FailingConnection:
            def __init__(self):
                self.commands: list[str] = []

            def execute(self, command: str):
                self.commands.append(command)
                raise RuntimeError("synthetic dependency")

        connection = FailingConnection()
        with self.assertRaisesRegex(SafeOperationError, "RESTORE_TARGET_PREPARATION_FAILED"):
            _drop_public_schema_restrict(connection)  # type: ignore[arg-type]
        self.assertEqual(connection.commands, ["DROP SCHEMA public RESTRICT"])
        self.assertNotIn("CASCADE", connection.commands[0])


class RestoreTestDatabaseNamePolicyTest(unittest.TestCase):
    run_id = "1784544727-989283"
    source = "pja_restore_source_test_1784544727_989283"
    target = "pja_restore_target_test_1784544727_989283"

    @staticmethod
    def url(database: str) -> str:
        return f"postgresql+psycopg://fixture:test-only@db:5432/{database}"

    def validate(self, source: str | None = None, target: str | None = None) -> None:
        source = self.source if source is None else source
        target = self.target if target is None else target
        validate_restore_test_database_names(
            self.run_id,
            source,
            target,
            self.url(source),
            self.url(target),
        )

    def test_fixed_source_and_target_names_pass(self):
        self.validate()
        target_public_schema_drop_required(
            frozenset({"public"}), target_structure(), target_identity()
        )

    def test_target_name_passes_application_test_database_url_gate(self):
        target_url = self.url(self.target)
        with mock.patch.dict(
            os.environ,
            {"APP_ENV": "test", "TEST_DATABASE_URL": target_url},
            clear=False,
        ):
            self.assertEqual(load_v2_settings().database_url, target_url)

    def test_old_target_without_test_is_rejected(self):
        with self.assertRaisesRegex(
            SafeOperationError, "RESTORE_TEST_DATABASE_NAME_INVALID"
        ):
            self.validate(target="pja_restore_target_1784544727_989283")

    def test_arbitrary_test_database_without_fixed_prefix_is_rejected(self):
        with self.assertRaisesRegex(
            SafeOperationError, "RESTORE_TEST_DATABASE_NAME_INVALID"
        ):
            self.validate(target="random_test_database")

    def test_forbidden_and_template_databases_are_rejected(self):
        for database in ("postgres", "template0", "template1"):
            with self.subTest(database=database):
                with self.assertRaisesRegex(
                    SafeOperationError, "RESTORE_TEST_DATABASE_NAME_INVALID"
                ):
                    self.validate(target=database)

    def test_invalid_or_oversized_run_id_is_rejected(self):
        for run_id in ("unsafe/run", "1784544727-12345678901"):
            with self.subTest(run_id=run_id):
                with self.assertRaisesRegex(
                    SafeOperationError, "RESTORE_TEST_DATABASE_NAME_INVALID"
                ):
                    validate_restore_test_database_names(
                        run_id,
                        self.source,
                        self.target,
                        self.url(self.source),
                        self.url(self.target),
                    )

    def test_source_or_target_url_name_mismatch_is_rejected(self):
        for source_url, target_url in (
            (self.url("different_source_test"), self.url(self.target)),
            (self.url(self.source), self.url("different_target_test")),
        ):
            with self.subTest(source_url=source_url.rsplit("/", 1)[-1]):
                with self.assertRaisesRegex(
                    SafeOperationError, "RESTORE_TEST_DATABASE_NAME_INVALID"
                ):
                    validate_restore_test_database_names(
                        self.run_id,
                        self.source,
                        self.target,
                        source_url,
                        target_url,
                    )

    def test_safe_name_error_does_not_include_url_or_password(self):
        try:
            self.validate(target="random_test_database")
        except SafeOperationError as error:
            rendered = _safe_error(error)
        else:
            self.fail("invalid target unexpectedly passed")
        self.assertNotIn("postgresql", rendered)
        self.assertNotIn("test-only", rendered)

    def test_cli_uses_explicit_safe_names_and_url_environment(self):
        command = [
            sys.executable,
            str(SCRIPTS / "v2_backup_restore.py"),
            "validate-test-database-names",
            "--run-id",
            self.run_id,
            "--source-database-name",
            self.source,
            "--target-database-name",
            self.target,
            "--source-database-url-env",
            "PJA_TEST_SOURCE_DATABASE_URL",
            "--target-database-url-env",
            "PJA_TEST_TARGET_DATABASE_URL",
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "PJA_TEST_SOURCE_DATABASE_URL": self.url(self.source),
                "PJA_TEST_TARGET_DATABASE_URL": self.url(self.target),
            }
        )
        completed = subprocess.run(
            command, env=environment, check=False, capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("test-only", " ".join(command))
        self.assertNotIn("postgresql", " ".join(command))

        environment["PJA_TEST_TARGET_DATABASE_URL"] = self.url("wrong_target_test")
        failed = subprocess.run(
            command, env=environment, check=False, capture_output=True, text=True
        )
        self.assertEqual(failed.returncode, 1)
        self.assertIn("RESTORE_TEST_DATABASE_NAME_INVALID", failed.stderr)
        self.assertNotIn("test-only", failed.stderr)
        self.assertNotIn("postgresql", failed.stderr)


def comparison_inventory() -> dict[str, object]:
    value: dict[str, object] = {
        "database": {
            "name": "pja_restore_source_test_1784544727_989283",
            "encoding": "UTF8",
            "collation": "C",
            "ctype": "C",
            "owner": "postgres",
            "oid": 100,
        },
        "schemas": {"public": {"owner": "pja_migrate", "privileges": "source acl"}},
        "alembic_revision": "20260717_04",
        "tables": ["public.parent", "public.child"],
        "table_details": {
            "public.parent": {"owner": "pja_migrate"},
            "public.child": {"owner": "pja_migrate"},
        },
        "table_row_counts": {"public.parent": 1, "public.child": 1},
        "table_checksums": {"public.parent": "a" * 64, "public.child": "b" * 64},
        "key_constraints": {
            "count": 1,
            "items": {"public.parent.parent_pkey": {"type": "primary_key"}},
            "sha256": "c" * 64,
        },
        "foreign_keys": {
            "count": 1,
            "items": {
                "public.child.child_parent_id_fkey": {
                    "definition": "FOREIGN KEY (parent_id) REFERENCES parent(id)",
                    "validated": True,
                }
            },
            "sha256": "d" * 64,
        },
        "sequences": {
            "count": 1,
            "items": {
                "public.parent_id_seq": {
                    "owner": "pja_migrate",
                    "last_value": "1",
                    "is_called": True,
                    "increment": "1",
                    "min_value": "1",
                    "max_value": "9223372036854775807",
                    "owned_by": "public.parent.id",
                }
            },
            "sha256": "e" * 64,
        },
        "indexes": {
            "count": 1,
            "names": ["parent_pkey"],
            "items": {
                "public.parent.parent_pkey": {
                    "definition": "CREATE UNIQUE INDEX parent_pkey ON public.parent USING btree (id)",
                    "unique": True,
                    "valid": True,
                    "owner": "pja_migrate",
                }
            },
            "sha256": "f" * 64,
        },
        "ownership": {
            "count": 2,
            "items": {"public.parent": "pja_migrate", "public.child": "pja_migrate"},
            "sha256": "0" * 64,
        },
        "project_knowledge": {
            "document_count": 1,
            "chunk_count": 2,
            "documents_sha256": "1" * 64,
            "chunks_sha256": "2" * 64,
            "fts_index_valid": True,
        },
        "auth": {"user_count": 1, "admin_count": 1, "authentication_structure_count": 1},
    }
    value["aggregate_sha256"] = sha256_json(value)
    return value


class InventoryComparatorTest(unittest.TestCase):
    def compare(self, mutate=None, owner_mapping=None, allow_name_difference=True):
        source = comparison_inventory()
        target = deepcopy(source)
        target["database"]["name"] = "pja_restore_target_test_1784544727_989283"  # type: ignore[index]
        target["database"]["oid"] = 900  # type: ignore[index]
        target["schemas"]["public"]["privileges"] = ""  # type: ignore[index]
        if mutate is not None:
            mutate(target)
        return compare_database_inventories(
            source, target, owner_mapping, allow_name_difference
        )

    def assert_failed_at(self, field: str, mutate) -> None:
        result = self.compare(mutate)
        self.assertEqual(result["status"], "failed")
        paths = [
            entry["path"]
            for category in ("missing_in_target", "extra_in_target", "value_mismatch")
            for entry in result[category]
        ]
        self.assertTrue(any(field in path for path in paths), paths)

    def test_table_missing_fails(self):
        self.assert_failed_at(
            "tables", lambda target: target["tables"].remove("public.child")
        )

    def test_row_count_difference_fails(self):
        self.assert_failed_at(
            "table_row_counts.public.child",
            lambda target: target["table_row_counts"].__setitem__("public.child", 0),
        )

    def test_stable_table_checksum_difference_fails(self):
        self.assert_failed_at(
            "table_checksums.public.child",
            lambda target: target["table_checksums"].__setitem__("public.child", "9" * 64),
        )

    def test_foreign_key_missing_fails(self):
        self.assert_failed_at(
            "foreign_keys.items",
            lambda target: target["foreign_keys"]["items"].clear(),
        )

    def test_sequence_state_difference_fails(self):
        self.assert_failed_at(
            "sequences.items.public.parent_id_seq.last_value",
            lambda target: target["sequences"]["items"]["public.parent_id_seq"].__setitem__(
                "last_value", "2"
            ),
        )

    def test_index_missing_or_invalid_fails(self):
        self.assert_failed_at(
            "indexes.items.public.parent.parent_pkey.valid",
            lambda target: target["indexes"]["items"]["public.parent.parent_pkey"].__setitem__(
                "valid", False
            ),
        )

    def test_alembic_difference_fails(self):
        self.assert_failed_at(
            "alembic_revision",
            lambda target: target.__setitem__("alembic_revision", "older_revision"),
        )

    def test_database_name_oid_acl_and_object_order_are_normalized(self):
        result = self.compare(lambda target: target["tables"].reverse())
        self.assertEqual(result["status"], "passed", result)
        ignored_paths = {entry["path"] for entry in result["ignored_non_deterministic_fields"]}
        self.assertIn("database.name", ignored_paths)
        self.assertIn("database.oid", ignored_paths)
        self.assertIn("schemas.public.privileges", ignored_paths)

    def test_database_name_difference_requires_explicit_isolated_policy(self):
        result = self.compare(allow_name_difference=False)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(
            [item["path"] for item in result["value_mismatch"]], ["database.name"]
        )

    def test_explicit_owner_mapping_passes_and_is_reported(self):
        def map_owner(target):
            target["schemas"]["public"]["owner"] = "pja_bootstrap"
            for detail in target["table_details"].values():
                detail["owner"] = "pja_bootstrap"
            for detail in target["sequences"]["items"].values():
                detail["owner"] = "pja_bootstrap"
            for detail in target["indexes"]["items"].values():
                detail["owner"] = "pja_bootstrap"
            for table in target["ownership"]["items"]:
                target["ownership"]["items"][table] = "pja_bootstrap"

        result = self.compare(map_owner, {"pja_migrate": "pja_bootstrap"})
        self.assertEqual(result["status"], "passed", result)
        self.assertGreater(len(result["normalized_fields"]), 0)

    def test_unauthorized_owner_change_fails(self):
        self.assert_failed_at(
            "table_details.public.parent.owner",
            lambda target: target["table_details"]["public.parent"].__setitem__(
                "owner", "unexpected_owner"
            ),
        )

    def test_snapshot_drift_is_detected(self):
        result = self.compare(
            lambda target: (
                target["table_row_counts"].__setitem__("public.child", 2),
                target["table_checksums"].__setitem__("public.child", "8" * 64),
            )
        )
        paths = {entry["path"] for entry in result["value_mismatch"]}
        self.assertIn("table_row_counts.public.child", paths)
        self.assertIn("table_checksums.public.child", paths)

    def test_owner_mapping_parser_is_narrow_and_rejects_duplicates(self):
        self.assertEqual(
            parse_owner_mappings(["pja_migrate=pja_bootstrap"]),
            {"pja_migrate": "pja_bootstrap"},
        )
        for values in (
            ["pja_migrate"],
            ["pja-migrate=pja_bootstrap"],
            ["pja_migrate=pja_migrate"],
            ["pja_migrate=pja_bootstrap", "pja_migrate=postgres"],
        ):
            with self.subTest(values=values):
                with self.assertRaisesRegex(
                    SafeOperationError, "RESTORE_OWNER_MAPPING_INVALID"
                ):
                    parse_owner_mappings(values)

    def test_machine_readable_diff_reports_exact_safe_paths(self):
        source = comparison_inventory()
        target = deepcopy(source)
        target["table_row_counts"]["public.child"] = 2
        target["table_checksums"]["public.child"] = "7" * 64
        diff = compare_database_inventories(source, target)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "inventory-diff.json"
            write_inventory_diff_report(
                destination,
                source,
                target,
                {"archive_sha256": "6" * 64},
                diff,
            )
            report = json.loads(destination.read_text(encoding="utf-8"))
            paths = {item["path"] for item in report["diff"]["value_mismatch"]}
            self.assertEqual(
                paths,
                {"table_row_counts.public.child", "table_checksums.public.child"},
            )
            self.assertEqual(report["pg_restore_exit_code"], 0)
            self.assertFalse(report["secrets_included"])
            serialized = json.dumps(report).lower()
            for forbidden in ("database_url", "password_hash", "session_id", "csrf_token"):
                self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
