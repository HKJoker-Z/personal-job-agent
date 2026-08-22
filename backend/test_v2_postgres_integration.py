import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

import database
import monitoring_service
from app.auth.service import AuthService
from app.analyze.execution import (
    LOCAL_NORMALIZATION_CONTRACT_VERSION,
    execution_fingerprint,
)
from app.analyze.idempotency import AnalyzeIdempotencyService, IdempotencyError, hash_key
from app.core.config import load_v2_settings
from app.db.engine import build_engine
from app.db.session import session_factory
from app.db.models import (
    AnalyzeIdempotencyRecord,
    Application,
    ApplicationRecord,
    ApplicationStageHistory,
    Job,
    Resume,
    ResumeVersion,
)
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
        self.reset_schema("head")

    def reset_schema(self, revision):
        raw_url = self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(raw_url, autocommit=True) as connection:
            connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
            connection.execute("CREATE SCHEMA public")
        build_engine.cache_clear()
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.upgrade(config, revision)

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

    def test_analyze_idempotency_unique_claim_is_process_safe(self):
        owner = self.create_owner()
        barrier = Barrier(2)

        def claim():
            service = AnalyzeIdempotencyService()
            barrier.wait()
            try:
                return service.claim(
                    user_id=owner.id,
                    key_hash=hash_key("postgres-12345678-1234-4123-8123-123456789abc"),
                    fingerprint="f" * 64,
                    request_id="postgres-concurrent-claim",
                )
            except IdempotencyError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: claim(), range(2)))
        winners = [item for item in outcomes if not isinstance(item, IdempotencyError)]
        losers = [item for item in outcomes if isinstance(item, IdempotencyError)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        self.assertEqual(losers[0].code, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
        db = session_factory(self.database_url)()
        try:
            records = db.scalars(select(AnalyzeIdempotencyRecord)).all()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].attempt_count, 1)
        finally:
            db.close()

    def test_analyze_execution_migration_preserves_legacy_rows_and_enforces_constraints(self):
        self.reset_schema("20260724_06")
        owner = self.create_owner()
        record_id = uuid4()
        attempt_token = uuid4()
        key = "postgres-legacy-execution-12345678"
        key_hash = hash_key(key)
        raw_url = self.database_url.replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )
        with psycopg.connect(raw_url) as connection:
            connection.execute(
                """
                INSERT INTO analyze_idempotency_records (
                    id, user_id, operation, idempotency_key_hash,
                    request_fingerprint, status, request_id, attempt_token,
                    response_status, response_body, lease_expires_at,
                    attempt_count, created_at, updated_at, expires_at,
                    completed_at
                )
                VALUES (
                    %s, %s, 'analyze:v1', %s,
                    %s, 'completed', 'legacy-completed-request', %s,
                    200, %s::json, CURRENT_TIMESTAMP,
                    1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP + INTERVAL '1 day', CURRENT_TIMESTAMP
                )
                """,
                (
                    record_id,
                    owner.id,
                    key_hash,
                    "a" * 64,
                    attempt_token,
                    '{"legacy":true,"saved_to_history":false,"application_id":null}',
                ),
            )

        config = Config(str(Path(__file__).parent / "alembic.ini"))
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)

        with psycopg.connect(raw_url) as connection:
            row = connection.execute(
                """
                SELECT response_body, execution_fingerprint,
                       execution_contract_version, normalization_source,
                       normalization_policy_version, skill_dictionary_version,
                       execution_bound_at
                FROM analyze_idempotency_records
                WHERE id = %s
                """,
                (record_id,),
            ).fetchone()
            self.assertTrue(row[0]["legacy"])
            self.assertEqual(tuple(row[1:]), (None, None, None, None, None, None))
            self.assertEqual(
                connection.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()[0],
                "20260820_08",
            )

        replay = AnalyzeIdempotencyService().claim(
            user_id=owner.id,
            key_hash=key_hash,
            fingerprint="a" * 64,
            request_id="legacy-replay-after-upgrade",
        )
        self.assertTrue(replay.is_replay)
        self.assertTrue(replay.replay_body["legacy"])

        invalid_updates = (
            (
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s
                WHERE id = %s
                """,
                (b"x" * 32, record_id),
            ),
            (
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s,
                    execution_contract_version = 'analyze-execution-v1',
                    normalization_source = 'local',
                    normalization_policy_version = 'fastapi-local-jd-v1',
                    execution_bound_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (b"x" * 31, record_id),
            ),
            (
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s,
                    execution_contract_version = 'analyze-execution-v1',
                    normalization_source = 'invalid',
                    normalization_policy_version = 'fastapi-local-jd-v1',
                    execution_bound_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (b"x" * 32, record_id),
            ),
            (
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s,
                    execution_contract_version = '   ',
                    normalization_source = 'local',
                    normalization_policy_version = 'fastapi-local-jd-v1',
                    execution_bound_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (b"x" * 32, record_id),
            ),
            (
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s,
                    execution_contract_version = 'analyze-execution-v1',
                    normalization_source = 'java',
                    normalization_policy_version = 'jd-normalization-v1',
                    skill_dictionary_version = NULL,
                    execution_bound_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (b"x" * 32, record_id),
            ),
        )
        for sql, parameters in invalid_updates:
            with self.subTest(sql=sql.split("SET", 1)[1].strip()[:40]):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with psycopg.connect(raw_url) as connection:
                        connection.execute(sql, parameters)

        with psycopg.connect(raw_url) as connection:
            connection.execute(
                """
                UPDATE analyze_idempotency_records
                SET execution_fingerprint = %s,
                    execution_contract_version = 'analyze-execution-v1',
                    normalization_source = 'local',
                    normalization_policy_version = 'fastapi-local-jd-v1',
                    skill_dictionary_version = NULL,
                    execution_bound_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (b"l" * 32, record_id),
            )
        with psycopg.connect(raw_url) as connection:
            source, size = connection.execute(
                """
                SELECT normalization_source, length(execution_fingerprint)
                FROM analyze_idempotency_records WHERE id = %s
                """,
                (record_id,),
            ).fetchone()
            self.assertEqual((source, size), ("local", 32))

    def test_postgres_execution_binding_takeover_conflict_and_atomic_rollback(self):
        owner = self.create_owner()
        service = AnalyzeIdempotencyService()
        stable_fingerprint = "f" * 64
        claim = service.claim(
            user_id=owner.id,
            key_hash=hash_key("postgres-binding-12345678"),
            fingerprint=stable_fingerprint,
            request_id="postgres-binding-first",
        )
        local = execution_fingerprint(
            stable_request_fingerprint=stable_fingerprint,
            effective_normalization_source="local",
            effective_job_text="Local PostgreSQL binding",
            normalization_policy_version=LOCAL_NORMALIZATION_CONTRACT_VERSION,
            skill_dictionary_version=None,
        )
        service.bind_execution(claim, local)
        service.bind_execution(claim, local)

        db = session_factory(self.database_url)()
        try:
            record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
            bound_at = record.execution_bound_at
            record.lease_expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=1
            )
            db.commit()
        finally:
            db.close()

        takeover = service.claim(
            user_id=owner.id,
            key_hash=claim.key_hash,
            fingerprint=stable_fingerprint,
            request_id="postgres-binding-takeover",
        )
        service.bind_execution(takeover, local)
        db = session_factory(self.database_url)()
        try:
            record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
            self.assertEqual(record.execution_bound_at, bound_at)
        finally:
            db.close()

        with self.assertRaises(IdempotencyError) as stale:
            service.bind_execution(claim, local)
        self.assertEqual(stale.exception.code, "IDEMPOTENCY_PERSISTENCE_FAILED")
        java = execution_fingerprint(
            stable_request_fingerprint=stable_fingerprint,
            effective_normalization_source="java",
            effective_job_text="Java PostgreSQL binding",
            normalization_policy_version="jd-normalization-v1",
            skill_dictionary_version="skills-v1",
        )
        with self.assertRaises(IdempotencyError) as conflict:
            service.bind_execution(takeover, java)
        self.assertEqual(
            conflict.exception.code,
            "IDEMPOTENCY_EXECUTION_CONFLICT",
        )

        unbound = service.claim(
            user_id=owner.id,
            key_hash=hash_key("postgres-unbound-finalize-12345678"),
            fingerprint="e" * 64,
            request_id="postgres-unbound-finalize",
        )
        unbound_binding = execution_fingerprint(
            stable_request_fingerprint="e" * 64,
            effective_normalization_source="local",
            effective_job_text="Unbound PostgreSQL execution",
            normalization_policy_version=LOCAL_NORMALIZATION_CONTRACT_VERSION,
            skill_dictionary_version=None,
        )
        with self.assertRaises(IdempotencyError):
            service.finalize(
                unbound,
                {"company_name": "No partial history"},
                execution_binding=unbound_binding,
                save_to_history=True,
                user_id=owner.id,
                job_url=None,
                resume_filename=None,
            )
        db = session_factory(self.database_url)()
        try:
            self.assertEqual(db.scalar(select(func.count(ApplicationRecord.id))), 0)
            record = db.get(AnalyzeIdempotencyRecord, unbound.record_id)
            self.assertEqual(record.status, "processing")
            self.assertIsNone(record.execution_fingerprint)
        finally:
            db.close()

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

    def test_submitted_application_delete_is_physical_and_preserves_sources(self):
        owner = self.create_owner()
        db = session_factory(self.database_url)()
        try:
            resume_service = ResumeService(db, owner.id, load_v2_settings())
            resume = resume_service.create({
                "title": "PostgreSQL Delete Resume",
                "language": "en",
                "target_role": "Engineer",
            })
            version = resume_service.create_version(
                UUID(resume["id"]),
                {"schema_version": 1, "header": {}, "summary": "PostgreSQL snapshot", "sections": []},
                None,
                "DELETE integration fixture",
            )
            analysis = ApplicationRecord(
                owner_user_id=owner.id,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                company_name="PostgreSQL Analysis Company",
                job_title="PostgreSQL Analysis Role",
            )
            db.add(analysis)
            db.flush()
            deleted = ApplicationService(db, owner.id).create_submitted({
                "company_name": analysis.company_name,
                "job_title": analysis.job_title,
                "job_description": "Physical DELETE fixture",
                "source_analysis_id": analysis.id,
                "resume_version_id": version["id"],
            })["application"]
            retained = ApplicationService(db, owner.id).create_submitted({
                "company_name": "Retained Company",
                "job_title": "Retained Role",
                "job_description": "Unaffected fixture",
                "source_analysis_id": None,
                "resume_version_id": None,
            })["application"]
            db.commit()

            ApplicationService(db, owner.id).delete(UUID(deleted["id"]))
            db.commit()

            self.assertIsNone(db.get(Application, UUID(deleted["id"])))
            self.assertIsNotNone(db.get(Application, UUID(retained["id"])))
            self.assertIsNotNone(db.get(ApplicationRecord, analysis.id))
            self.assertIsNotNone(db.get(Resume, UUID(resume["id"])))
            self.assertIsNotNone(db.get(ResumeVersion, UUID(version["id"])))
            self.assertEqual(
                db.scalar(select(func.count(Application.id)).where(
                    Application.id == UUID(deleted["id"])
                )),
                0,
            )
        finally:
            db.close()

    def test_version_201_schema_downgrade_and_upgrade_preserves_foundation(self):
        self.reset_schema("20260724_06")
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
        self.reset_schema("20260724_06")
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
        self.reset_schema("20260724_06")
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
        self.reset_schema("20260724_06")
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
