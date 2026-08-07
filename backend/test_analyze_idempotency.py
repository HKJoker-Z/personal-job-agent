import hashlib
import os
import io
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
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
from app.analyze.execution import (
    EXECUTION_CONTRACT_VERSION,
    LOCAL_NORMALIZATION_CONTRACT_VERSION,
    execution_fingerprint,
)
from app.analyze.normalization_client import NormalizationClientError
import legacy_application
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
    def binding(
        *,
        stable_fingerprint: str = "a" * 64,
        source: str = "local",
        text: str = "Python backend role",
        policy_version: str | None = None,
        dictionary_version: str | None = None,
    ):
        return execution_fingerprint(
            stable_request_fingerprint=stable_fingerprint,
            effective_normalization_source=source,
            effective_job_text=text,
            normalization_policy_version=(
                policy_version
                or (
                    "jd-normalization-v1"
                    if source == "java"
                    else LOCAL_NORMALIZATION_CONTRACT_VERSION
                )
            ),
            skill_dictionary_version=(
                dictionary_version
                if source == "java"
                else None
            ),
        )

    def bind(self, claim, binding=None):
        selected = binding or self.binding()
        self.service.bind_execution(claim, selected)
        return selected

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
            model="deepseek-v4-pro",
            security_policy_version="v1",
        )
        first = request_fingerprint(**values)
        self.assertEqual(first, request_fingerprint(**values))
        changed = dict(values, job_text="Different role")
        self.assertNotEqual(first, request_fingerprint(**changed))

    def test_execution_fingerprint_is_binary_canonical_and_domain_separated(self):
        local = self.binding()
        same = self.binding()
        java = self.binding(
            source="java",
            text="Python backend role",
            dictionary_version="skills-v1",
        )
        fallback = self.binding(source="fallback_local")
        changed_text = self.binding(text="Different effective role")
        changed_request = self.binding(stable_fingerprint="b" * 64)

        self.assertEqual(len(local.fingerprint), 32)
        self.assertEqual(local, same)
        self.assertEqual(local.contract_version, EXECUTION_CONTRACT_VERSION)
        self.assertEqual(
            local.normalization_policy_version,
            LOCAL_NORMALIZATION_CONTRACT_VERSION,
        )
        self.assertIsNone(local.skill_dictionary_version)
        self.assertNotEqual(local.fingerprint, java.fingerprint)
        self.assertNotEqual(local.fingerprint, fallback.fingerprint)
        self.assertNotEqual(local.fingerprint, changed_text.fingerprint)
        self.assertNotEqual(local.fingerprint, changed_request.fingerprint)

    def test_first_completion_replays_identically_without_history(self):
        claim = self.claim()
        binding = self.bind(claim)
        body, history_id = self.service.finalize(
            claim,
            self.response(),
            execution_binding=binding,
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
        binding = self.bind(claim)
        body, history_id = self.service.finalize(
            claim,
            self.response(),
            execution_binding=binding,
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
        old_binding = self.bind(old)
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
                execution_binding=old_binding,
                save_to_history=False,
                user_id=self.user_id,
                job_url=None,
                resume_filename=None,
            )

    def test_stale_post_provider_attempt_becomes_indeterminate(self):
        claim = self.claim()
        binding = self.bind(claim)
        self.service.provider_started(claim, binding)
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
        binding = self.bind(claim)
        huge = self.response()
        huge["analysis_warnings"] = ["x" * (600 * 1024)]
        with self.assertRaises(IdempotencyError) as raised:
            self.service.finalize(
                claim,
                huge,
                execution_binding=binding,
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
        binding = self.bind(completed)
        self.service.finalize(
            completed,
            self.response(),
            execution_binding=binding,
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

    def test_binding_is_attempt_protected_idempotent_and_immutable(self):
        claim = self.claim()
        local = self.bind(claim)
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        first_bound_at = record.execution_bound_at
        self.assertEqual(record.execution_fingerprint, local.fingerprint)
        self.assertEqual(record.normalization_source, "local")
        self.assertEqual(
            record.normalization_policy_version,
            LOCAL_NORMALIZATION_CONTRACT_VERSION,
        )
        self.assertIsNone(record.skill_dictionary_version)
        self.assertIsNone(record.provider_started_at)
        db.close()

        self.service.bind_execution(claim, local)
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        self.assertEqual(record.execution_bound_at, first_bound_at)
        record.lease_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()
        db.close()

        takeover = self.claim()
        self.service.bind_execution(takeover, local)
        with self.assertRaises(IdempotencyError) as stale:
            self.service.bind_execution(claim, local)
        self.assertEqual(stale.exception.code, "IDEMPOTENCY_PERSISTENCE_FAILED")

        java = self.binding(
            source="java",
            dictionary_version="skills-v1",
        )
        with self.assertRaises(IdempotencyError) as conflict:
            self.service.bind_execution(takeover, java)
        self.assertEqual(
            conflict.exception.code,
            "IDEMPOTENCY_EXECUTION_CONFLICT",
        )
        self.assertNotIn(local.fingerprint.hex(), str(conflict.exception))
        changed_text = self.binding(text="Different local effective role")
        with self.assertRaises(IdempotencyError) as changed:
            self.service.bind_execution(takeover, changed_text)
        self.assertEqual(
            changed.exception.code,
            "IDEMPOTENCY_EXECUTION_CONFLICT",
        )

    def test_provider_and_finalization_require_the_expected_binding(self):
        claim = self.claim()
        local = self.binding()
        with self.assertRaises(IdempotencyError) as provider:
            self.service.provider_started(claim, local)
        self.assertEqual(provider.exception.code, "IDEMPOTENCY_PERSISTENCE_FAILED")
        with self.assertRaises(IdempotencyError) as finalization:
            self.service.finalize(
                claim,
                self.response(),
                execution_binding=local,
                save_to_history=False,
                user_id=self.user_id,
                job_url=None,
                resume_filename=None,
            )
        self.assertEqual(
            finalization.exception.code,
            "IDEMPOTENCY_PERSISTENCE_FAILED",
        )

    def test_legacy_completed_null_binding_replays_without_mutation(self):
        claim = self.claim()
        stored = self.response()
        stored["application_id"] = None
        stored["saved_to_history"] = False
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        record.status = "completed"
        record.response_status = 200
        record.response_body = stored
        record.completed_at = utc_now()
        db.commit()
        db.close()

        replay = self.claim()
        self.assertTrue(replay.is_replay)
        self.assertEqual(replay.replay_body, stored)
        db = session_factory()()
        record = db.get(AnalyzeIdempotencyRecord, claim.record_id)
        self.assertIsNone(record.execution_fingerprint)
        self.assertIsNone(record.execution_bound_at)
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

    @staticmethod
    def mode_settings(mode: str):
        normalization = replace(
            legacy_application.settings.jd_normalization,
            mode=mode,
            base_url=(
                "http://java-normalization:8091"
                if mode in {"shadow", "java"}
                else None
            ),
            api_key=("T" * 32 if mode in {"shadow", "java"} else None),
            shadow_sample_rate=1 if mode == "shadow" else 0,
        )
        return replace(
            legacy_application.settings,
            jd_normalization=normalization,
        )

    @staticmethod
    def java_result(text="JAVA EFFECTIVE Python backend role"):
        return SimpleNamespace(
            normalized_text=text,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            normalization_policy_version="jd-normalization-v1",
            skill_dictionary_version="skills-v1",
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

    def test_completed_shadow_replay_does_not_call_java_or_rewrite_history(self):
        key = "72345678-1234-4123-8123-123456789abc"
        normalization = replace(
            legacy_application.settings.jd_normalization,
            mode="shadow",
            base_url="http://java-normalization:8091",
            api_key="T" * 32,
            shadow_sample_rate=1,
        )
        shadow_settings = replace(
            legacy_application.settings,
            jd_normalization=normalization,
        )
        java_result = SimpleNamespace(
            normalized_text="Java observation only",
            content_hash=hashlib.sha256(b"Java observation only").hexdigest(),
            normalization_policy_version="jd-normalization-v1",
            skill_dictionary_version="skills-v1",
        )
        java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=java_result)
        )
        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch.object(
                legacy_application,
                "settings",
                shadow_settings,
            ), patch(
                "legacy_application.call_deepseek_raw",
                return_value=self.provider_response(),
            ) as provider:
                first = self.request(key)
                replay = self.request(key)
        finally:
            self.client.app.state.jd_normalization_client = None

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(java_client.normalize.await_count, 1)
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

    def test_detected_client_disconnect_finalizes_fallback_once_without_provider(self):
        key = "42345679-1234-4123-8123-123456789abc"
        with patch.object(
            legacy_application,
            "_request_client_disconnected",
            new=AsyncMock(return_value=True),
        ), patch("legacy_application.call_deepseek_raw") as provider:
            response = self.request(key, save=False)
            replay = self.request(key, save=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["analysis_status"], "fallback")
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), response.json())
        provider.assert_not_called()
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertEqual(record.status, "completed")
        self.assertIsNotNone(record.response_body)
        db.close()

    def test_disconnect_after_provider_returns_still_finalizes_one_result(self):
        key = "42345679-1234-4123-8123-123456789abd"
        disconnected = AsyncMock(side_effect=[False, True])
        with patch.object(
            legacy_application,
            "_request_client_disconnected",
            new=disconnected,
        ), patch(
            "legacy_application.call_deepseek_raw",
            return_value=self.provider_response(),
        ) as provider:
            response = self.request(key, save=False)
            replay = self.request(key, save=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["analysis_status"], "complete")
        self.assertTrue(response.json()["model_completion"]["client_disconnected"])
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), response.json())
        self.assertEqual(disconnected.await_count, 2)
        provider.assert_called_once()
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertEqual(record.status, "completed")
        db.close()

    def test_provider_deadline_exhaustion_returns_fallback_before_any_attempt(self):
        key = "42345680-1234-4123-8123-123456789abc"
        with patch.dict(
            os.environ,
            {
                "PROVIDER_OVERALL_DEADLINE_SECONDS": "10",
                "REQUEST_TIMEOUT_SECONDS": "5",
            },
        ), patch("legacy_application.OpenAI") as openai:
            response = self.request(key, save=False)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["analysis_status"], "fallback")
        self.assertEqual(
            body["model_completion"]["fallback_reason"],
            "provider_deadline_exhausted",
        )
        self.assertTrue(body["model_completion"]["deadline_exhausted"])
        openai.assert_not_called()

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

    def test_completed_local_result_replays_in_java_mode_without_java_or_provider(self):
        key = "62345678-1234-4123-8123-123456789abc"
        java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=self.java_result())
        )
        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch(
                "legacy_application.call_deepseek_raw",
                return_value=self.provider_response(),
            ) as provider:
                with patch.object(
                    legacy_application,
                    "settings",
                    self.mode_settings("local"),
                ):
                    first = self.request(key)
                with patch.object(
                    legacy_application,
                    "settings",
                    self.mode_settings("java"),
                ):
                    replay = self.request(key)
        finally:
            self.client.app.state.jd_normalization_client = None

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), first.json())
        java_client.normalize.assert_not_awaited()
        self.assertEqual(provider.call_count, 1)
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertEqual(record.normalization_source, "local")
        self.assertEqual(
            record.normalization_policy_version,
            LOCAL_NORMALIZATION_CONTRACT_VERSION,
        )
        self.assertEqual(len(record.execution_fingerprint), 32)
        self.assertIsNotNone(record.execution_bound_at)
        db.close()

    def test_legacy_completed_null_binding_replays_across_mode_change_without_side_effects(self):
        key = "b2345678-1234-4123-8123-123456789abc"
        with patch(
            "legacy_application.call_deepseek_raw",
            return_value=self.provider_response(),
        ):
            first = self.request(key)
        self.assertEqual(first.status_code, 200, first.text)
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        record.execution_fingerprint = None
        record.execution_contract_version = None
        record.normalization_source = None
        record.normalization_policy_version = None
        record.skill_dictionary_version = None
        record.execution_bound_at = None
        db.commit()
        history_count = db.scalar(select(func.count(ApplicationRecord.id)))
        db.close()

        java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=self.java_result())
        )
        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch.object(
                legacy_application,
                "settings",
                self.mode_settings("java"),
            ), patch(
                "legacy_application.call_deepseek_raw"
            ) as provider:
                replay = self.request(key)
        finally:
            self.client.app.state.jd_normalization_client = None
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), first.json())
        java_client.normalize.assert_not_awaited()
        provider.assert_not_called()
        db = session_factory()()
        self.assertEqual(
            db.scalar(select(func.count(ApplicationRecord.id))),
            history_count,
        )
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertIsNone(record.execution_fingerprint)
        db.close()

    def test_completed_java_result_replays_in_local_mode_without_provider_or_history_rewrite(self):
        key = "82345678-1234-4123-8123-123456789abc"
        java_text = "JAVA HISTORY DERIVATION Python platform role"
        java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=self.java_result(java_text))
        )
        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch(
                "legacy_application.call_deepseek_raw",
                return_value=self.provider_response(),
            ) as provider:
                with patch.object(
                    legacy_application,
                    "settings",
                    self.mode_settings("java"),
                ):
                    first = self.request(key)
                with patch.object(
                    legacy_application,
                    "settings",
                    self.mode_settings("local"),
                ):
                    replay = self.request(key)
        finally:
            self.client.app.state.jd_normalization_client = None

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["Idempotency-Replayed"], "true")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(java_client.normalize.await_count, 1)
        self.assertEqual(provider.call_count, 1)
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertEqual(record.normalization_source, "java")
        self.assertEqual(
            record.normalization_policy_version,
            "jd-normalization-v1",
        )
        self.assertEqual(record.skill_dictionary_version, "skills-v1")
        self.assertEqual(db.scalar(select(func.count(ApplicationRecord.id))), 1)
        history = db.scalar(select(ApplicationRecord))
        self.assertNotIn(java_text, history.notes or "")
        db.close()

    def test_java_failure_is_selected_and_bound_before_provider_as_fallback_local(self):
        key = "92345678-1234-4123-8123-123456789abc"
        java_client = SimpleNamespace(
            normalize=AsyncMock(
                side_effect=NormalizationClientError("response_timeout")
            )
        )
        observed_sources: list[str] = []

        def provider(*args, **kwargs):
            db = session_factory()()
            record = db.scalar(select(AnalyzeIdempotencyRecord))
            observed_sources.append(record.normalization_source)
            self.assertEqual(len(record.execution_fingerprint), 32)
            self.assertIsNotNone(record.provider_started_at)
            db.close()
            return self.provider_response()

        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch.object(
                legacy_application,
                "settings",
                self.mode_settings("java"),
            ), patch(
                "legacy_application.call_deepseek_raw",
                side_effect=provider,
            ) as provider_call:
                response = self.request(key, save=False)
        finally:
            self.client.app.state.jd_normalization_client = None

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(java_client.normalize.await_count, 1)
        self.assertEqual(provider_call.call_count, 1)
        self.assertEqual(observed_sources, ["fallback_local"])
        db = session_factory()()
        record = db.scalar(select(AnalyzeIdempotencyRecord))
        self.assertEqual(record.normalization_source, "fallback_local")
        self.assertEqual(
            record.normalization_policy_version,
            LOCAL_NORMALIZATION_CONTRACT_VERSION,
        )
        self.assertIsNone(record.skill_dictionary_version)
        db.close()

    def test_execution_binding_database_failure_prevents_provider(self):
        key = "a2345678-1234-4123-8123-123456789abc"
        with patch.object(
            AnalyzeIdempotencyService,
            "bind_execution",
            side_effect=IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                "The Analyze execution binding could not be persisted.",
            ),
        ), patch(
            "legacy_application.call_deepseek_raw"
        ) as provider:
            response = self.request(key, save=False)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["error"]["code"],
            "IDEMPOTENCY_PERSISTENCE_FAILED",
        )
        provider.assert_not_called()
        self.assertNotIn("fingerprint", response.text.lower())

    def test_bound_java_execution_does_not_silently_fallback_on_retry(self):
        key = "c2345678-1234-4123-8123-123456789abc"
        java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=self.java_result())
        )
        self.client.app.state.jd_normalization_client = java_client
        try:
            with patch.object(
                legacy_application,
                "settings",
                self.mode_settings("java"),
            ), patch.object(
                AnalyzeIdempotencyService,
                "provider_started",
                side_effect=IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The provider boundary could not be persisted.",
                ),
            ), patch(
                "legacy_application.call_deepseek_raw"
            ) as provider:
                first = self.request(key, save=False)
            self.assertEqual(first.status_code, 503, first.text)
            provider.assert_not_called()
            db = session_factory()()
            record = db.scalar(select(AnalyzeIdempotencyRecord))
            self.assertEqual(record.status, "failed")
            self.assertEqual(record.normalization_source, "java")
            db.close()

            java_client.normalize.side_effect = NormalizationClientError(
                "unavailable"
            )
            with patch.object(
                legacy_application,
                "settings",
                self.mode_settings("java"),
            ), patch(
                "legacy_application.call_deepseek_raw"
            ) as provider:
                retry = self.request(key, save=False)
        finally:
            self.client.app.state.jd_normalization_client = None
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(
            retry.json()["error"]["code"],
            "IDEMPOTENCY_EXECUTION_CONFLICT",
        )
        provider.assert_not_called()
        self.assertNotIn("java", retry.text.lower())
        self.assertNotIn("fingerprint", retry.text.lower())


if __name__ == "__main__":
    unittest.main()
