import os
import unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from alembic import command
from alembic.config import Config

import database
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.engine import build_engine
from app.db.session import session_factory
from app.migration.postgres_writer import PostgreSQLV1Writer
from app.migration.sqlite_reader import SQLiteV1Reader
from data_management_service import delete_monitoring_data, preview_monitoring_deletion
from monitoring_service import build_analysis_metric, get_overview, persist_analysis_metrics
from test_support import temporary_test_database


POSTGRES_ENABLED = os.getenv("PJA_RUN_POSTGRES_TESTS") == "1"


@unittest.skipUnless(POSTGRES_ENABLED, "PostgreSQL integration tests are opt-in")
class V2PostgreSQLIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.environ["TEST_DATABASE_URL"]
        if "test" not in cls.database_url.lower():
            raise RuntimeError("PostgreSQL integration database must be explicitly test-named.")

    def setUp(self):
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
            connection.execute("CREATE SCHEMA public")
        build_engine.cache_clear()
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.upgrade(config, "head")

    def tearDown(self):
        build_engine.cache_clear()

    def create_owner(self):
        db = session_factory(self.database_url)()
        try:
            user = AuthService(db, load_v2_settings()).create_user(
                "postgres-owner@example.com",
                "postgres integration passphrase",
                "PostgreSQL Owner",
                "admin",
            )
            db.commit()
            return user
        finally:
            db.close()

    def test_legacy_knowledge_monitoring_and_cleanup_use_postgresql(self):
        document = database.rebuild_project_knowledge_document(
            title="PostgreSQL Integration Knowledge",
            category="Project Experience",
            source_filename="integration.md",
            content="FastAPI PostgreSQL integration evidence",
            chunks=["FastAPI PostgreSQL integration evidence"],
        )
        items, mode = database.search_knowledge_chunks("FastAPI PostgreSQL", 5)
        self.assertEqual(mode, "postgresql_fts")
        self.assertEqual(items[0]["document_id"], document["id"])
        database.rebuild_project_knowledge_document(
            title="PostgreSQL Integration Knowledge",
            category="Project Experience",
            source_filename="integration.md",
            content="Updated PostgreSQL search evidence",
            chunks=["Updated PostgreSQL search evidence"],
        )

        metric = build_analysis_metric(
            workflow_id="postgres-workflow",
            workflow_status="completed",
            workflow_duration_ms=10.0,
            workflow_duration_us=10000,
            workflow_steps=[],
            outcome="completed",
            security_scan={"risk_level": "low", "findings": []},
            security_status="passed",
        )
        persist_analysis_metrics(metric, [])
        self.assertEqual(get_overview()["completed"], 1)
        preview = preview_monitoring_deletion({"mode": "all"})
        self.assertEqual(preview["analysis_metrics_count"], 1)
        deleted = delete_monitoring_data(
            {"mode": "all", "confirmation": "DELETE ALL MONITORING DATA"}
        )
        self.assertEqual(deleted["analysis_metrics_deleted"], 1)
        self.assertTrue(database.delete_knowledge_document(document["id"]))

    def test_sqlite_migration_preserves_rows_and_advances_sequences(self):
        owner = self.create_owner()
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with temporary_test_database() as source:
                migrated_id = database.insert_application_record(
                    {
                        "company_name": "Migrated Company",
                        "job_title": "Migrated Role",
                        "match_score": 80,
                    },
                    job_url=None,
                    resume_filename=None,
                )
                reader = SQLiteV1Reader(source)
                metadata = reader.inspect()
                with patch.dict(os.environ, {"DATABASE_URL": self.database_url}):
                    report = PostgreSQLV1Writer(self.database_url).migrate(
                        reader, metadata, owner.email
                    )
                    self.assertEqual(report["status"], "completed")
                    new_id = database.insert_application_record(
                        {
                            "company_name": "Post-migration Company",
                            "job_title": "Post-migration Role",
                            "match_score": 90,
                        },
                        job_url=None,
                        resume_filename=None,
                    )
        self.assertGreater(new_id, migrated_id)


if __name__ == "__main__":
    unittest.main()
