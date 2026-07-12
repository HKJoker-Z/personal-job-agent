import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backup_runtime import create_backup, sha256_file
from restore_runtime import restore_backup, verify_backup

from database import get_connection
from test_support import temporary_test_database


class BackupRestoreTest(unittest.TestCase):
    def create_runtime(self, directory):
        knowledge = Path(directory) / "runtime" / "PROJECT_KNOWLEDGE.md"
        knowledge.parent.mkdir(parents=True, exist_ok=True)
        knowledge.write_text("original knowledge", encoding="utf-8")
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, suite_name, suite_version, mode, status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("backup-run", "default", "1.9", "offline", "completed", "2026-01-01T00:00:00+00:00"),
            )
        return knowledge

    def test_backup_contains_database_knowledge_and_manifest(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            result = create_backup(database_path, knowledge, Path(directory) / "backups")
            self.assertTrue((result / "app.db").is_file())
            self.assertTrue((result / "PROJECT_KNOWLEDGE.md").is_file())
            self.assertTrue((result / "manifest.json").is_file())

    def test_manifest_checksums_are_correct_and_paths_are_logical(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            result = create_backup(database_path, knowledge, Path(directory) / "backups")
            manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
            for entry in manifest["included_files"]:
                self.assertEqual(entry["sha256"], sha256_file(result / entry["name"]))
                self.assertFalse(Path(entry["name"]).is_absolute())
            self.assertNotIn(str(database_path), json.dumps(manifest))

    def test_restore_recovers_original_database_and_knowledge(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            backup_root = Path(directory) / "backups"
            result = create_backup(database_path, knowledge, backup_root)
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO evaluation_runs (
                        run_id, suite_name, suite_version, mode, status, started_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("later-run", "default", "1.9", "offline", "completed", "2026-01-02T00:00:00+00:00"),
                )
            knowledge.write_text("changed knowledge", encoding="utf-8")
            restore_backup(result, database_path, knowledge, backup_root)
            with get_connection() as connection:
                run_ids = [row[0] for row in connection.execute("SELECT run_id FROM evaluation_runs").fetchall()]
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(run_ids, ["backup-run"])
            self.assertIn("analysis_metrics", tables)
            self.assertEqual(knowledge.read_text(encoding="utf-8"), "original knowledge")

    def test_corrupted_checksum_is_rejected(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            result = create_backup(database_path, knowledge, Path(directory) / "backups")
            with (result / "PROJECT_KNOWLEDGE.md").open("a", encoding="utf-8") as handle:
                handle.write("corruption")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verify_backup(result)

    def test_manifest_path_traversal_is_rejected(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            result = create_backup(database_path, knowledge, Path(directory) / "backups")
            manifest_path = result / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["included_files"][0]["name"] = "../app.db"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                verify_backup(result)

    def test_restore_creates_pre_restore_backup(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            backup_root = Path(directory) / "backups"
            result = create_backup(database_path, knowledge, backup_root)
            pre_restore = restore_backup(result, database_path, knowledge, backup_root)
            self.assertIsNotNone(pre_restore)
            self.assertTrue((pre_restore / "manifest.json").is_file())

    def test_backup_never_includes_environment_or_log_files(self):
        with temporary_test_database() as database_path, tempfile.TemporaryDirectory() as directory:
            knowledge = self.create_runtime(directory)
            result = create_backup(database_path, knowledge, Path(directory) / "backups")
            names = {path.name for path in result.iterdir()}
            self.assertEqual(names, {"app.db", "PROJECT_KNOWLEDGE.md", "manifest.json"})


if __name__ == "__main__":
    unittest.main()
