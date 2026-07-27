import os
import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from docx import Document
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from analysis_contract import ModelOutputError
from app.analyze.idempotency import (
    AnalyzeIdempotencyService,
    IdempotencyError,
    hash_key,
    request_fingerprint,
    validate_key,
)
from app.db.engine import build_engine
from app.db.models import AnalyzeIdempotencyRecord, ApplicationRecord, User, utc_now
from app.db.session import session_factory
from app.api.routers import auth
from app.analyze.idempotency import AnalyzeIdempotencyFailureMiddleware
from app.auth.middleware import V2SecurityMiddleware
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.base import Base
from legacy_application import (
    analyze,
    call_deepseek_raw,
    call_deepseek_repair,
    http_exception_handler,
    validation_exception_handler,
)


class AnalyzeIdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        database = Path(self.temporary.name) / "idempotency-test.db"
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "TEST_DATABASE_URL": f"sqlite+pysqlite:///{database}",
                "ANALYZE_IDEMPOTENCY_LEASE_SECONDS": "5",
                "ANALYZE_IDEMPOTENCY_RETENTION_HOURS": "24",
            },
        )
        self.environment.start()
        build_engine.cache_clear()
        migration_config = Config()
        migration_config.set_main_option(
            "script_location", str(Path(__file__).parent / "alembic")
        )
        command.upgrade(migration_config, "head")
        db = session_factory()()
        self.user_id = uuid4()
        self.other_user_id = uuid4()
        db.add_all(
            [
                User(
                    id=self.user_id,
                    email="one@example.com",
                    normalized_email="one@example.com",
                    password_hash="test",
                    display_name="One",
                    role="user",
                ),
                User(
                    id=self.other_user_id,
                    email="two@example.com",
                    normalized_email="two@example.com",
                    password_hash="test",
                    display_name="Two",
                    role="user",
                ),
            ]
        )
        db.commit()
        db.close()
        self.service = AnalyzeIdempotencyService()

    def tearDown(self):
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    def claim(self, key="12345678-1234-4123-8123-123456789abc", fingerprint="a" * 64, user_id=None):
        return self.service.claim(
            user_id=user_id or self.user_id,
            key_hash=hash_key(key),
            fingerprint=fingerprint,
            request_id="test-request-id",
        )

    @staticmethod
    def response():
        return {
            "company_name": "Example",
            "job_title": "Engineer",
            "match_score": 70,
            "workflow_id": "workflow-test",
            "workflow_steps": [],
            "analysis_status": "complete",
        }

    def test_key_validation_hashes_domain_and_never_returns_raw_key(self):
        key = "12345678-1234-4123-8123-123456789abc"
        self.assertEqual(validate_key(key), key)
        self.assertEqual(len(hash_key(key)), 64)
        self.assertNotIn(key, hash_key(key))
        for invalid in ("short", "contains space", "x" * 129, "ümlaut-key"):
            with self.assertRaisesRegex(IdempotencyError, "8-128"):
                validate_key(invalid)

    def test_fingerprint_is_canonical_and_effective_fields_change_it(self):
        values = dict(
            resume_version_id=None,
            resume_text="Python\r\nFastAPI  ",
            job_text="Backend role",
            job_url=None,
            rag_enabled=False,
            rag_top_k=5,
            project_knowledge=None,
            save_to_history=False,
            model="deepseek-chat",
            security_policy_version="v1",
        )
        first = request_fingerprint(**values)
        self.assertEqual(first, request_fingerprint(**values))
        changed = dict(values, job_text="Different role")
        self.assertNotEqual(first, request_fingerprint(**changed))

    def test_first_completion_replays_identically_without_history(self):
        claim = self.claim()
        body, history_id = self.service.finalize(
            claim,
            self.response(),
            save_to_history=False,
            user_id=self.user_id,
            job_url=None,
            resume_filename="resume.docx",
        )
        self.assertIsNone(history_id)
        replay = self.claim()
        self.assertTrue(replay.is_replay)
        self.assertEqual(replay.replay_body, body)

    def test_history_and_completed_response_finalize_together_once(self):
        claim = self.claim()
        body, history_id = self.service.finalize(
            claim,
            self.response(),
            save_to_history=True,
            user_id=self.user_id,
            job_url=None,
            resume_filename="resume.docx",
        )
        self.assertEqual(body["application_id"], history_id)
        self.assertTrue(body["saved_to_history"])
        replay = self.claim()
        self.assertEqual(replay.replay_body, body)
        db = session_factory()()
        self.assertEqual(db.scalar(select(func.count(ApplicationRecord.id))), 1)
        db.close()

    def test_same_key_changed_request_is_rejected(self):
        self.claim(fingerprint="a" * 64)
        with self.assertRaisesRegex(IdempotencyError, "different Analyze"):
            self.claim(fingerprint="b" * 64)

    def test_same_textual_key_is_independent_between_users(self):
        one = self.claim(user_id=self.user_id)
        two = self.claim(user_id=self.other_user_id)
        self.assertNotEqual(one.record_id, two.record_id)

    def test_active_lease_is_in_progress(self):
        self.claim()
        with self.assertRaises(IdempotencyError) as raised:
            self.claim()
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_REQUEST_IN_PROGRESS")
        self.assertGreaterEqual(raised.exception.retry_after, 1)

    def test_known_pre_provider_failure_can_retry_with_the_same_key(self):
        failed = self.claim()
        self.service.fail_unfinalized(failed, "INPUT_SECURITY_BLOCKED")
        retry = self.claim()
        self.assertNotEqual(failed.attempt_token, retry.attempt_token)
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, retry.record_id)
        self.assertEqual(record.status, "processing")
        self.assertEqual(record.attempt_count, 2)
        self.assertIsNone(record.provider_started_at)
        db.close()

    def test_stale_pre_provider_attempt_is_reclaimed_and_old_token_loses(self):
        old = self.claim()
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, old.record_id)
        record.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        db.close()
        newer = self.claim()
        self.assertNotEqual(old.attempt_token, newer.attempt_token)
        with self.assertRaisesRegex(IdempotencyError, "stale"):
            self.service.finalize(
                old,
                self.response(),
                save_to_history=False,
                user_id=self.user_id,
                job_url=None,
                resume_filename=None,
            )

    def test_stale_post_provider_attempt_becomes_indeterminate(self):
        claim = self.claim()
        self.service.provider_started(claim)
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        record.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        db.close()
        with self.assertRaises(IdempotencyError) as raised:
            self.claim()
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_OUTCOME_UNKNOWN")

    def test_finalization_rollback_leaves_no_partial_history(self):
        claim = self.claim()
        huge = self.response()
        huge["analysis_warnings"] = ["x" * (600 * 1024)]
        with self.assertRaises(IdempotencyError) as raised:
            self.service.finalize(
                claim,
                huge,
                save_to_history=True,
                user_id=self.user_id,
                job_url=None,
                resume_filename=None,
            )
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_PERSISTENCE_FAILED")
        db = session_factory()()
        self.assertEqual(db.scalar(select(func.count(ApplicationRecord.id))), 0)
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        self.assertEqual(record.status, "processing")
        db.close()

    def test_cleanup_deletes_only_expired_terminal_records(self):
        completed = self.claim()
        self.service.finalize(
            completed,
            self.response(),
            save_to_history=False,
            user_id=self.user_id,
            job_url=None,
            resume_filename=None,
        )
        active = self.claim(key="87654321-1234-4123-8123-123456789abc")
        db = session_factory()()
        terminal = db.get(AnalyzeIdempotencyRecord, completed.record_id)
        terminal.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        db.close()
        self.assertEqual(self.service.cleanup(), 1)
        db = session_factory()()
        self.assertIsNone(db.get(AnalyzeIdempotencyRecord, completed.record_id))
        self.assertIsNotNone(db.get(AnalyzeIdempotencyRecord, active.record_id))
        db.close()

    def test_sdk_transport_retries_are_zero_for_primary_and_repair(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only-key"}):
            with patch("legacy_application.OpenAI") as openai:
                openai.return_value.chat.completions.create.side_effect = RuntimeError("offline")
                with self.assertRaises(ModelOutputError):
                    call_deepseek_raw("resume", "job")
                self.assertEqual(openai.call_args.kwargs["max_retries"], 0)
            with patch("legacy_application.OpenAI") as openai:
                openai.return_value.chat.completions.create.side_effect = RuntimeError("offline")
                with self.assertRaises(ModelOutputError):
                    call_deepseek_repair("invalid")
                self.assertEqual(openai.call_args.kwargs["max_retries"], 0)


class AnalyzeEndpointIdempotencyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "AUTH_ENABLED": "true",
                "TEST_DATABASE_URL": f"sqlite+pysqlite:///{root / 'endpoint-test.db'}",
                "APP_DATABASE_PATH": str(root / "legacy-test.db"),
                "FILE_STORAGE_ROOT": str(root / "files"),
                "SESSION_COOKIE_SECURE": "false",
                "AUTH_TRUSTED_ORIGINS": "http://testserver",
                "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
                "SESSION_TOUCH_INTERVAL_SECONDS": "900",
            },
        )
        self.environment.start()
        build_engine.cache_clear()
        settings = load_v2_settings()
        engine = build_engine(settings.database_url)
        Base.metadata.create_all(engine)
        db = session_factory()()
        AuthService(db, settings).create_user(
            "idempotency@example.com",
            "correct horse battery staple",
            "Idempotency User",
            "user",
        )
        db.commit()
        db.close()

        app = FastAPI()
        app.include_router(auth.router)
        app.post("/api/analyze")(analyze)
        app.add_exception_handler(HTTPException, http_exception_handler)
        app.add_exception_handler(RequestValidationError, validation_exception_handler)
        app.add_middleware(AnalyzeIdempotencyFailureMiddleware)
        app.add_middleware(V2SecurityMiddleware, settings=settings)
        self.client = TestClient(app)
        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "idempotency@example.com",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = login.json()["csrf_token"]

    def tearDown(self):
        self.client.close()
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    @staticmethod
    def document_bytes():
        document = Document()
        document.add_paragraph("Python FastAPI engineer")
        stream = io.BytesIO()
        document.save(stream)
        return stream.getvalue()

    @staticmethod
    def provider_response():
        from analysis_contract import ProviderAnalysisResponse

        content = json.dumps(
            {
                "matched_skills": ["Python"],
                "missing_skills": ["PostgreSQL"],
                "unknown_skills": [],
                "concise_dimension_assessments": {
                    "skills_match": {
                        "score": 70,
                        "assessment": "Python matches.",
                        "evidence_ids": ["resume"],
                    }
                },
                "evidence_references": [
                    {"skill": "Python", "evidence_ids": ["resume"]}
                ],
                "unsupported_claim_candidates": [],
                "concise_recommendations": ["Add verified PostgreSQL evidence."],
            }
        )
        return ProviderAnalysisResponse(
            content=content,
            metadata={"finish_reason": "stop", "response_length": len(content)},
        )

    def request(self, key=None, *, job_text="Python backend role", save=True, csrf=None):
        headers = {
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf if csrf is not None else self.csrf,
            "X-Request-ID": f"request-{uuid4().hex[:12]}",
        }
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(
            "/api/analyze",
            files={
                "resume": (
                    "resume.docx",
                    self.document_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={
                "job_text": job_text,
                "save_to_history": "true" if save else "false",
                "use_project_knowledge": "false",
            },
            headers=headers,
        )

    def test_first_request_and_completed_duplicate_replay_without_new_provider_or_history(self):
        key = "12345678-1234-4123-8123-123456789abc"
        with patch(
            "legacy_application.call_deepseek_raw",
            return_value=self.provider_response(),
        ) as provider:
            first = self.request(key)
            second = self.request(key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json(), second.json())
        self.assertNotIn("Idempotency-Replayed", first.headers)
        self.assertEqual(second.headers["Idempotency-Replayed"], "true")
        self.assertEqual(provider.call_count, 1)
        db = session_factory()()
        self.assertEqual(db.scalar(select(func.count(ApplicationRecord.id))), 1)
        db.close()

    def test_changed_request_reuses_key_with_stable_conflict(self):
        key = "22345678-1234-4123-8123-123456789abc"
        with patch("legacy_application.call_deepseek_raw", return_value=self.provider_response()):
            self.assertEqual(self.request(key, save=False).status_code, 200)
            changed = self.request(key, job_text="Different role", save=False)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["error"]["code"], "IDEMPOTENCY_KEY_REUSED")

    def test_missing_key_preserves_existing_behavior_and_invalid_key_is_stable(self):
        with patch("legacy_application.call_deepseek_raw", return_value=self.provider_response()):
            self.assertEqual(self.request(None, save=False).status_code, 200)
        invalid = self.request("bad key", save=False)
        self.assertEqual(invalid.status_code, 400, invalid.text)
        self.assertEqual(invalid.json()["error"]["code"], "IDEMPOTENCY_KEY_INVALID")

    def test_auth_origin_and_csrf_run_before_replay(self):
        key = "32345678-1234-4123-8123-123456789abc"
        with patch("legacy_application.call_deepseek_raw", return_value=self.provider_response()):
            self.assertEqual(self.request(key, save=False).status_code, 200)
        no_session = TestClient(self.client.app)
        try:
            unauthenticated = no_session.post(
                "/api/analyze",
                headers={
                    "Origin": "http://testserver",
                    "Idempotency-Key": key,
                    "X-CSRF-Token": self.csrf,
                },
            )
        finally:
            no_session.close()
        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(unauthenticated.json()["error"]["code"], "AUTHENTICATION_REQUIRED")
        wrong_csrf = self.request(key, save=False, csrf="wrong")
        self.assertEqual(wrong_csrf.status_code, 403)
        self.assertEqual(wrong_csrf.json()["error"]["code"], "CSRF_VALIDATION_FAILED")

    def test_fallback_is_stored_and_replayed(self):
        key = "42345678-1234-4123-8123-123456789abc"
        with patch(
            "legacy_application.call_deepseek_raw",
            side_effect=TimeoutError("deterministic timeout"),
        ) as provider:
            first = self.request(key, save=False)
            replay = self.request(key, save=False)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["analysis_status"], "fallback")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(provider.call_count, 1)

    def test_primary_and_explicit_repair_are_each_called_at_most_once(self):
        from analysis_contract import ProviderAnalysisResponse

        key = "52345678-1234-4123-8123-123456789abc"
        malformed = ProviderAnalysisResponse(
            content="not valid JSON",
            metadata={"finish_reason": "stop", "response_length": 14},
        )
        with patch(
            "legacy_application.call_deepseek_raw",
            return_value=malformed,
        ) as primary, patch(
            "legacy_application.call_deepseek_repair",
            return_value=self.provider_response(),
        ) as repair:
            first = self.request(key, save=False)
            replay = self.request(key, save=False)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["analysis_status"], "repaired")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(primary.call_count, 1)
        self.assertEqual(repair.call_count, 1)


if __name__ == "__main__":
    unittest.main()
