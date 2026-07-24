import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select

from app.db.engine import build_engine
from app.db.models import User
from app.db.session import session_factory
from app.migration.sqlite_reader import SQLiteV1Reader


class V2DatabaseMigrationTest(unittest.TestCase):
    def test_alembic_fresh_sqlite_upgrade_is_at_head(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "alembic-test.db"
            with patch.dict(os.environ, {"APP_ENV": "test", "TEST_DATABASE_URL": f"sqlite+pysqlite:///{database}"}):
                build_engine.cache_clear()
                config = Config(str(Path(__file__).parent / "alembic.ini"))
                command.upgrade(config, "head")
                engine = build_engine(os.environ["TEST_DATABASE_URL"])
                with engine.connect() as connection:
                    current = MigrationContext.configure(connection).get_current_revision()
                self.assertEqual(current, "20260724_06")
                command.check(config)
                engine.dispose()
                build_engine.cache_clear()

    def test_sqlalchemy_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            url = f"sqlite+pysqlite:///{Path(directory) / 'rollback-test.db'}"
            with patch.dict(os.environ, {"APP_ENV": "test", "TEST_DATABASE_URL": url}):
                build_engine.cache_clear()
                from app.db.base import Base
                engine = build_engine(url)
                Base.metadata.create_all(engine)
                db = session_factory(url)()
                db.add(User(email="rollback@example.com", normalized_email="rollback@example.com", password_hash="not-used", display_name="Rollback", role="user"))
                db.flush()
                db.rollback()
                self.assertIsNone(db.scalar(select(User.id)))
                db.close(); engine.dispose(); build_engine.cache_clear()

    def test_alpha3_downgrade_and_upgrade_adds_only_reliable_workflow_tables(self):
        workflow_tables = {
            "agent_runs", "agent_steps", "agent_run_events", "approval_requests",
            "approval_decisions", "agent_outbox_events", "user_ai_budgets",
            "ai_usage_ledger", "worker_heartbeats", "dead_letter_records",
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "alpha3-to-final.db"
            url = f"sqlite+pysqlite:///{database}"
            with patch.dict(os.environ, {"APP_ENV": "test", "TEST_DATABASE_URL": url}):
                build_engine.cache_clear()
                config = Config(str(Path(__file__).parent / "alembic.ini"))
                command.upgrade(config, "head")
                engine = build_engine(url)
                self.assertTrue(workflow_tables.issubset(set(inspect(engine).get_table_names())))
                engine.dispose()

                command.downgrade(config, "20260713_03")
                engine = build_engine(url)
                alpha3_tables = set(inspect(engine).get_table_names())
                self.assertTrue(workflow_tables.isdisjoint(alpha3_tables))
                self.assertIn("application_packages", alpha3_tables)
                engine.dispose()

                command.upgrade(config, "head")
                command.check(config)
                engine = build_engine(url)
                self.assertTrue(workflow_tables.issubset(set(inspect(engine).get_table_names())))
                engine.dispose()
                build_engine.cache_clear()

    def test_reader_accepts_missing_optional_tables_and_preserves_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "v1.db"
            connection = sqlite3.connect(source)
            connection.execute("CREATE TABLE application_records (id INTEGER PRIMARY KEY, created_at TEXT)")
            connection.execute("INSERT INTO application_records VALUES (1, '2026-01-01T00:00:00+00:00')")
            connection.commit(); connection.close()
            reader = SQLiteV1Reader(source)
            metadata = reader.inspect()
            self.assertEqual(metadata.row_counts, {"application_records": 1})
            self.assertEqual(len(list(reader.rows("application_records"))), 1)
            reader.assert_unchanged()

    def test_reader_rejects_unknown_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "unknown.db"
            connection = sqlite3.connect(source)
            connection.execute("CREATE TABLE application_records (id INTEGER PRIMARY KEY)")
            connection.execute("CREATE TABLE unexpected_business_data (id INTEGER PRIMARY KEY)")
            connection.commit(); connection.close()
            with self.assertRaisesRegex(ValueError, "unknown business schema"):
                SQLiteV1Reader(source).inspect()

    def test_test_database_guard_rejects_production_like_path(self):
        from app.core.config import V2ConfigError, load_v2_settings
        with patch.dict(os.environ, {"APP_ENV": "test", "TEST_DATABASE_URL": "sqlite+pysqlite:///runtime/data/app.db"}):
            with self.assertRaises(V2ConfigError):
                load_v2_settings()


if __name__ == "__main__":
    unittest.main()
