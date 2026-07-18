import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import database
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.engine import build_engine
from app.db.session import session_factory
from app.db.models import Application, ApplicationStageHistory, Job
from app.jobs.service import JobService
from app.applications.service import ApplicationConflict, ApplicationService
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

    def test_job_application_constraints_partial_uniqueness_and_stage_history(self):
        owner = self.create_owner()
        db = session_factory(self.database_url)()
        try:
            first = JobService(db, owner.id).create({
                "company_name": "Synthetic PostgreSQL Company",
                "title": "Platform Engineer",
                "location": "Test Region",
                "description": "Python and PostgreSQL are required.",
                "source_type": "manual",
            })["job"]
            job_id = UUID(first["id"])
            application = ApplicationService(db, owner.id).create({"job_id": job_id})["application"]
            with self.assertRaises(ApplicationConflict):
                ApplicationService(db, owner.id).create({"job_id": job_id})
            ApplicationService(db, owner.id).archive(UUID(application["id"]), application["revision"])
            replacement = ApplicationService(db, owner.id).create({"job_id": job_id})["application"]
            replacement_id = UUID(replacement["id"])
            transitioned = ApplicationService(db, owner.id).transition(
                replacement_id, "preparing", replacement["revision"], "PostgreSQL test", "", None
            )["application"]
            self.assertEqual(transitioned["current_stage"], "preparing")
            db.commit()
            histories = list(db.scalars(select(ApplicationStageHistory).where(
                ApplicationStageHistory.application_id == replacement_id
            )))
            self.assertEqual(len(histories), 2)
            indexes = db.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_applications_owner_job_active'")
            ).all()
            self.assertTrue(indexes)
            bad = Job(
                owner_user_id=owner.id, company_name="Bad", normalized_company_name="bad",
                title="Bad", normalized_title="bad", location="", normalized_location="",
                description="bad", description_text_hash="0" * 64, source_type="manual",
                status="new", deduplication_key="1" * 64, salary_min=-1,
            )
            db.add(bad)
            with self.assertRaises(IntegrityError):
                db.flush()
            db.rollback()
        finally:
            db.close()

    def test_version_201_schema_downgrade_and_upgrade_preserves_foundation(self):
        owner = self.create_owner()
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.downgrade(config, "20260712_01")
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users WHERE id = %s", (owner.id,)).fetchone()[0], 1)
            self.assertIsNone(connection.execute("SELECT to_regclass('public.jobs')").fetchone()[0])
        command.upgrade(config, "head")
        with psycopg.connect(raw_url) as connection:
            self.assertEqual(connection.execute("SELECT to_regclass('public.jobs')").fetchone()[0], "jobs")

    def test_alpha2_schema_upgrades_to_matching_and_materials(self):
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.downgrade(config, "20260713_02")
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as connection:
            self.assertIsNone(connection.execute("SELECT to_regclass('public.job_match_analyses')").fetchone()[0])
            self.assertEqual(connection.execute("SELECT to_regclass('public.applications')").fetchone()[0], "applications")
        command.upgrade(config, "head")
        with psycopg.connect(raw_url) as connection:
            for table in (
                "job_match_analyses", "job_match_dimensions", "job_match_evidence",
                "job_rank_runs", "job_rank_items", "application_packages",
                "application_materials", "application_material_versions",
                "material_evidence_links", "material_reviews",
            ):
                self.assertEqual(connection.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0], table)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'uq_application_packages_approved'"
                ).fetchone()[0],
                1,
            )

    def test_alpha3_schema_upgrades_to_reliable_agent_workflows_and_round_trips(self):
        workflow_tables = (
            "agent_runs", "agent_steps", "agent_run_events", "approval_requests",
            "approval_decisions", "agent_outbox_events", "user_ai_budgets",
            "ai_usage_ledger", "worker_heartbeats", "dead_letter_records",
        )
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.downgrade(config, "20260713_03")
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as connection:
            self.assertEqual(
                connection.execute("SELECT to_regclass('public.application_packages')").fetchone()[0],
                "application_packages",
            )
            for table in workflow_tables:
                self.assertIsNone(
                    connection.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0]
                )
        command.upgrade(config, "head")
        command.check(config)
        with psycopg.connect(raw_url) as connection:
            for table in workflow_tables:
                self.assertEqual(
                    connection.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0],
                    table,
                )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'uq_ai_usage_ledger_key'"
                ).fetchone()[0],
                1,
            )


if __name__ == "__main__":
    unittest.main()
