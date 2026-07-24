import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import database
import monitoring_service
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.engine import build_engine
from app.db.session import session_factory
from app.db.models import Application, ApplicationStageHistory, Job
from app.jobs.service import JobService
from app.applications.service import ApplicationConflict, ApplicationService
from app.resumes.service import ResumeService
from app.migration.postgres_writer import PostgreSQLV1Writer
from app.migration.sqlite_reader import SQLiteV1Reader
from data_management_service import delete_monitoring_data, preview_monitoring_deletion
from monitoring_service import (
    build_analysis_metric,
    get_overview,
    get_workflow_step_performance,
    persist_analysis_metrics,
)
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
            content="FastAPI PostgreSQL integration evidence. Redis 7 and Dramatiq background worker evidence.",
            chunks=[
                "FastAPI PostgreSQL integration evidence",
                "Redis 7 and Dramatiq background worker evidence",
            ],
        )
        items, mode = database.search_knowledge_chunks("FastAPI PostgreSQL", 5)
        self.assertEqual(mode, "postgresql_fts")
        self.assertEqual(items[0]["document_id"], document["id"])
        worker_items, worker_mode = database.search_knowledge_chunks("Redis Dramatiq", 5)
        self.assertEqual(worker_mode, "postgresql_fts")
        self.assertTrue(worker_items)
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

    def test_workflow_step_aggregate_preserves_counts_latency_and_date_boundaries(self):
        start = datetime(2026, 6, 24, 4, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 24, 4, 0, tzinfo=timezone.utc)
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        rows = [
            ("wf-start", "parse_resume", "completed", 10.0, start),
            ("wf-middle-a", "parse_resume", "completed", 20.0, start + timedelta(days=1)),
            ("wf-middle-b", "parse_resume", "failed", 30.0, start + timedelta(days=2)),
            ("wf-middle-c", "parse_resume", "running", 40.0, start + timedelta(days=3)),
            ("wf-null", "parse_resume", "completed", None, start + timedelta(days=4)),
            ("wf-end", "parse_resume", "skipped", 9999.0, end),
            ("wf-other-a", "run_llm_analysis", "failed", 5.0, start + timedelta(days=5)),
            ("wf-other-b", "run_llm_analysis", "completed", 7.0, start + timedelta(days=6)),
            ("wf-before", "parse_resume", "completed", 1.0, start - timedelta(microseconds=1)),
            ("wf-after", "parse_resume", "completed", 1.0, end + timedelta(microseconds=1)),
        ]
        with psycopg.connect(raw_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO analysis_step_metrics (
                        workflow_id, step_key, status, duration_ms, duration_us, created_at
                    )
                    VALUES (%s, %s, %s, %s, NULL, %s)
                    """,
                    rows,
                )

        with patch(
            "monitoring_service.period_bounds",
            return_value=(start.isoformat(), end.isoformat(), 30),
        ):
            result = get_workflow_step_performance(30)

        self.assertEqual(result["period_start"], start.isoformat())
        self.assertEqual(result["period_end"], end.isoformat())
        self.assertEqual([item["step_key"] for item in result["items"]], ["parse_resume", "run_llm_analysis"])
        self.assertEqual(
            result["items"][0],
            {
                "step_key": "parse_resume",
                "total_count": 6,
                "completed_count": 3,
                "failed_count": 1,
                "skipped_count": 1,
                "average_ms": 25.0,
                "minimum_ms": 10.0,
                "maximum_ms": 40.0,
                "p50_ms": 20.0,
                "p95_ms": 40.0,
            },
        )
        self.assertEqual(result["items"][1]["total_count"], 2)
        self.assertEqual(result["items"][1]["average_ms"], 6.0)
        self.assertEqual(result["items"][1]["p50_ms"], 5.0)
        self.assertEqual(result["items"][1]["p95_ms"], 7.0)
        with patch(
            "monitoring_service.period_bounds",
            return_value=(
                datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat(),
                datetime(2030, 1, 2, tzinfo=timezone.utc).isoformat(),
                1,
            ),
        ):
            self.assertEqual(get_workflow_step_performance(1)["items"], [])

    def test_workflow_step_aggregate_plan_returns_bounded_grouped_rows(self):
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as connection:
            connection.execute(
                """
                INSERT INTO analysis_step_metrics (
                    workflow_id, step_key, status, duration_ms, duration_us, created_at
                )
                SELECT
                    'plan-workflow-' || value,
                    (ARRAY[
                        'parse_resume',
                        'parse_job',
                        'retrieve_project_evidence',
                        'build_prompt',
                        'run_llm_analysis',
                        'normalize_result'
                    ])[(value % 6) + 1],
                    CASE
                        WHEN value % 10 = 0 THEN 'skipped'
                        WHEN value % 17 = 0 THEN 'failed'
                        ELSE 'completed'
                    END,
                    CASE WHEN value % 29 = 0 THEN NULL ELSE (value % 2000) + 0.125 END,
                    NULL,
                    CURRENT_TIMESTAMP - INTERVAL '1 day'
                FROM generate_series(1, 50000) AS fixture(value)
                """
            )
            connection.execute("ANALYZE analysis_step_metrics")
            start = datetime.now(timezone.utc) - timedelta(days=2)
            end = datetime.now(timezone.utc) + timedelta(minutes=1)
            plan_document = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON) "
                + monitoring_service._POSTGRES_WORKFLOW_STEP_AGGREGATE_SQL.replace("?", "%s"),
                (start, end),
            ).fetchone()[0][0]

        def plan_nodes(node):
            yield node
            for child in node.get("Plans", []):
                yield from plan_nodes(child)

        root = plan_document["Plan"]
        nodes = list(plan_nodes(root))
        self.assertEqual(root["Actual Rows"], 6)
        self.assertEqual(sum(item["total_count"] for item in get_workflow_step_performance(2)["items"]), 50000)
        self.assertFalse(
            any(
                node.get("Node Type") in {"Sort", "Incremental Sort"}
                and node.get("Sort Space Type") == "Disk"
                for node in nodes
            )
        )

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

    def test_v203_primary_resume_migration_backfills_and_enforces_one_active_primary(self):
        owner = self.create_owner()
        db = session_factory(self.database_url)()
        try:
            service = ResumeService(db, owner.id, load_v2_settings())
            first = service.create({"title": "Older Resume", "language": "en", "target_role": ""})
            second = service.create({"title": "Newest Resume", "language": "en", "target_role": ""})
            db.commit()
        finally:
            db.close()

        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.downgrade(config, "20260717_04")
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name='resumes' AND column_name='is_primary'"
                ).fetchone()
            )

        command.upgrade(config, "head")
        with psycopg.connect(raw_url) as connection:
            primary_ids = connection.execute(
                "SELECT id::text FROM resumes WHERE user_id=%s AND is_primary IS TRUE AND archived_at IS NULL",
                (owner.id,),
            ).fetchall()
            self.assertEqual(primary_ids, [(second["id"],)])
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM pg_indexes WHERE indexname='uq_resumes_user_primary_active'"
                ).fetchone()[0],
                1,
            )
            with self.assertRaises(psycopg.errors.UniqueViolation):
                connection.execute(
                    "UPDATE resumes SET is_primary=TRUE WHERE id::text IN (%s,%s)",
                    (first["id"], second["id"]),
                )


if __name__ == "__main__":
    unittest.main()
