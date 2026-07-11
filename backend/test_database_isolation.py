import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import (
    BACKEND_DIR,
    DEFAULT_DATABASE_PATH,
    assert_safe_test_database,
    get_connection,
    get_database_path,
    init_db,
    is_default_application_database,
)
from test_support import temporary_test_database


class DatabaseIsolationTest(unittest.TestCase):
    def test_development_without_config_uses_default_path(self):
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            os.environ.pop("APP_DATABASE_PATH", None)
            self.assertEqual(get_database_path(), DEFAULT_DATABASE_PATH)

    def test_test_environment_uses_explicit_temporary_path(self):
        with temporary_test_database() as database_path:
            self.assertEqual(get_database_path(), database_path.resolve())
            self.assertFalse(is_default_application_database(database_path))

    def test_test_environment_rejects_default_application_database(self):
        with self.assertRaisesRegex(RuntimeError, "non-default temporary SQLite database"):
            assert_safe_test_database(DEFAULT_DATABASE_PATH, "test")

    def test_temporary_database_runs_all_migrations(self):
        with temporary_test_database():
            with get_connection() as connection:
                tables = {
                    row["name"]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                }
        self.assertTrue({"analysis_metrics", "analysis_step_metrics", "evaluation_runs", "evaluation_results"} <= tables)

    def test_temporary_database_can_write_analysis_metric_table(self):
        with temporary_test_database():
            with get_connection() as connection:
                connection.execute(
                    "INSERT INTO analysis_metrics (workflow_id, created_at, outcome) VALUES (?, ?, ?)",
                    ("isolation-analysis", "2026-01-01T00:00:00+00:00", "completed"),
                )
                total = connection.execute("SELECT COUNT(*) AS total FROM analysis_metrics").fetchone()["total"]
        self.assertEqual(total, 1)

    def test_temporary_database_can_write_evaluation_run_table(self):
        with temporary_test_database():
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO evaluation_runs (
                        run_id, suite_name, suite_version, mode, status, started_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("isolation-run", "default", "1", "offline", "completed", "2026-01-01T00:00:00+00:00"),
                )
                total = connection.execute("SELECT COUNT(*) AS total FROM evaluation_runs").fetchone()["total"]
        self.assertEqual(total, 1)

    def test_temporary_database_file_is_removed_after_context(self):
        with temporary_test_database() as database_path:
            self.assertTrue(database_path.exists())
        self.assertFalse(database_path.exists())

    def test_temporary_database_cannot_be_the_default_database(self):
        with temporary_test_database() as database_path:
            self.assertFalse(is_default_application_database(database_path))
            self.assertNotEqual(database_path.resolve(), DEFAULT_DATABASE_PATH)

    def test_no_default_database_is_created_by_path_resolution(self):
        existed_before = DEFAULT_DATABASE_PATH.exists()
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
            os.environ.pop("APP_DATABASE_PATH", None)
            self.assertEqual(get_database_path(), DEFAULT_DATABASE_PATH)
        self.assertEqual(DEFAULT_DATABASE_PATH.exists(), existed_before)

    def test_environment_variables_are_restored_after_temporary_database(self):
        previous_env = os.environ.get("APP_ENV")
        previous_path = os.environ.get("APP_DATABASE_PATH")
        with temporary_test_database():
            self.assertEqual(os.environ.get("APP_ENV"), "test")
        self.assertEqual(os.environ.get("APP_ENV"), previous_env)
        self.assertEqual(os.environ.get("APP_DATABASE_PATH"), previous_path)

    def test_different_temporary_databases_do_not_share_rows(self):
        with temporary_test_database():
            with get_connection() as connection:
                connection.execute(
                    "INSERT INTO analysis_metrics (workflow_id, created_at, outcome) VALUES (?, ?, ?)",
                    ("first-database", "2026-01-01T00:00:00+00:00", "completed"),
                )
        with temporary_test_database():
            with get_connection() as connection:
                total = connection.execute("SELECT COUNT(*) AS total FROM analysis_metrics").fetchone()["total"]
        self.assertEqual(total, 0)

    def test_connection_factory_reads_current_environment_each_time(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first.db"
            second = Path(temporary_directory) / "second.db"
            with patch.dict(os.environ, {"APP_ENV": "test", "APP_DATABASE_PATH": str(first)}, clear=False):
                init_db()
                with get_connection() as connection:
                    connection.execute(
                        "INSERT INTO analysis_metrics (workflow_id, created_at, outcome) VALUES (?, ?, ?)",
                        ("first-current-config", "2026-01-01T00:00:00+00:00", "completed"),
                    )
                os.environ["APP_DATABASE_PATH"] = str(second)
                init_db()
                with get_connection() as connection:
                    total = connection.execute("SELECT COUNT(*) AS total FROM analysis_metrics").fetchone()["total"]
        self.assertEqual(total, 0)

    def test_relative_and_absolute_database_paths_resolve_safely(self):
        with tempfile.TemporaryDirectory(dir=BACKEND_DIR) as temporary_directory:
            absolute_path = Path(temporary_directory) / "absolute.db"
            relative_path = absolute_path.relative_to(BACKEND_DIR)
            with patch.dict(
                os.environ,
                {"APP_ENV": "test", "APP_DATABASE_PATH": str(relative_path)},
                clear=False,
            ):
                self.assertEqual(get_database_path(), absolute_path.resolve())
            with patch.dict(
                os.environ,
                {"APP_ENV": "test", "APP_DATABASE_PATH": str(absolute_path)},
                clear=False,
            ):
                self.assertEqual(get_database_path(), absolute_path.resolve())

    def test_symlink_to_default_database_is_rejected_in_test_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            link = Path(temporary_directory) / "default-link.db"
            link.symlink_to(DEFAULT_DATABASE_PATH)
            with self.assertRaisesRegex(RuntimeError, "non-default temporary SQLite database"):
                assert_safe_test_database(link, "test")

    def test_consecutive_test_databases_do_not_reuse_old_data(self):
        counts = []
        for index in range(2):
            with temporary_test_database():
                with get_connection() as connection:
                    counts.append(connection.execute("SELECT COUNT(*) AS total FROM evaluation_runs").fetchone()["total"])
                    connection.execute(
                        """
                        INSERT INTO evaluation_runs (
                            run_id, suite_name, suite_version, mode, status, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (f"run-{index}", "default", "1", "offline", "completed", "2026-01-01T00:00:00+00:00"),
                    )
        self.assertEqual(counts, [0, 0])


if __name__ == "__main__":
    unittest.main()
