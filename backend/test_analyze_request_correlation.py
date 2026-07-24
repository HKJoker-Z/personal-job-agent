import io
import json
import logging
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.routers import auth
from app.application import extend_application
from app.auth.middleware import V2SecurityMiddleware
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.base import Base
from app.db.engine import build_engine
from app.db.models import User, UserSession, utc_now
from app.db.session import session_factory
from logging_utils import JsonFormatter, RequestLoggingMiddleware


class AnalyzeRequestCorrelationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "AUTH_ENABLED": "true",
                "TEST_DATABASE_URL": f"sqlite+pysqlite:///{root / 'correlation-test.db'}",
                "FILE_STORAGE_ROOT": str(root / "files"),
                "SESSION_COOKIE_SECURE": "false",
                "AUTH_TRUSTED_ORIGINS": "http://testserver",
                "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
                "REQUEST_MAX_BODY_MB": "1",
            },
        )
        self.environment.start()
        build_engine.cache_clear()
        self.settings = load_v2_settings()
        self.engine = build_engine(self.settings.database_url)
        Base.metadata.create_all(self.engine)
        db = session_factory(self.settings.database_url)()
        try:
            service = AuthService(db, self.settings)
            admin = service.create_user(
                "admin@example.com",
                "correct horse battery staple",
                "Admin",
                "admin",
            )
            user = service.create_user(
                "user@example.com",
                "another correct passphrase",
                "User",
                "user",
            )
            self.admin_id = admin.id
            self.user_id = user.id
            db.commit()
        finally:
            db.close()

        self.stream = io.StringIO()
        self.logger = logging.getLogger(f"test.correlation.{id(self)}")
        self.logger.handlers.clear()
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)

        app = FastAPI()
        app.include_router(auth.router)

        @app.post("/api/analyze")
        async def analyze(request: Request):
            if request.headers.get("x-test-failure") == "unknown":
                raise RuntimeError("PRIVATE_EXCEPTION_TEXT")
            return {"analysis_status": "complete"}

        @app.delete("/api/monitoring/private")
        async def admin_only():
            return {"deleted": True}

        app.add_middleware(V2SecurityMiddleware, settings=self.settings)
        app.add_middleware(RequestLoggingMiddleware, logger=self.logger)
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    def login(
        self,
        *,
        email: str = "admin@example.com",
        password: str = "correct horse battery staple",
    ) -> str:
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    @staticmethod
    def unsafe_headers(csrf: str, request_id: str = "phase-a1-request") -> dict[str, str]:
        return {
            "Origin": "http://testserver",
            "X-CSRF-Token": csrf,
            "X-Request-ID": request_id,
        }

    def assert_analyze_error(
        self,
        response,
        *,
        status_code: int,
        code: str,
    ) -> dict:
        self.assertEqual(response.status_code, status_code, response.text)
        payload = response.json()
        self.assertEqual(set(payload), {"error"})
        error = payload["error"]
        self.assertEqual(
            set(error),
            {"code", "message", "request_id", "details"},
        )
        self.assertEqual(error["code"], code)
        self.assertIsInstance(error["details"], dict)
        self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
        return error

    def latest_session(self) -> UserSession:
        db = session_factory(self.settings.database_url)()
        try:
            value = db.scalar(select(UserSession).order_by(UserSession.created_at.desc()))
            db.expunge(value)
            return value
        finally:
            db.close()

    def test_missing_authentication_has_stable_envelope_and_request_id(self):
        response = self.client.post(
            "/api/analyze",
            headers={"X-Request-ID": "client-correlation_1"},
        )
        error = self.assert_analyze_error(
            response,
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
        )
        self.assertEqual(error["request_id"], "client-correlation_1")

    def test_composed_middleware_has_one_outer_request_logger(self):
        legacy = FastAPI()
        legacy.add_middleware(RequestLoggingMiddleware, logger=self.logger)
        composed = extend_application(legacy)
        middleware_names = [
            middleware.cls.__name__
            for middleware in composed.user_middleware
        ]
        self.assertEqual(
            middleware_names[:3],
            [
                "RequestLoggingMiddleware",
                "V2SecurityMiddleware",
                "FeatureRetirementMiddleware",
            ],
        )
        self.assertEqual(
            middleware_names.count("RequestLoggingMiddleware"),
            1,
        )

    def test_invalid_and_overlong_request_ids_are_replaced(self):
        for request_id in ("invalid request/id", "a" * 65):
            response = self.client.post(
                "/api/analyze",
                headers={"X-Request-ID": request_id},
            )
            error = self.assert_analyze_error(
                response,
                status_code=401,
                code="AUTHENTICATION_REQUIRED",
            )
            self.assertNotEqual(error["request_id"], request_id)
            UUID(error["request_id"], version=4)

    def test_body_size_rejection_has_request_id_before_authentication(self):
        response = self.client.post(
            "/api/analyze",
            headers={
                "Content-Length": str(2 * 1024 * 1024),
                "X-Request-ID": "large-request",
            },
        )
        self.assert_analyze_error(
            response,
            status_code=413,
            code="REQUEST_TOO_LARGE",
        )

    def test_untrusted_origin_and_csrf_failures_have_stable_envelopes(self):
        csrf = self.login()
        origin = self.client.post(
            "/api/analyze",
            headers={
                "Origin": "http://untrusted.test",
                "X-CSRF-Token": csrf,
                "X-Request-ID": "origin-request",
            },
        )
        self.assert_analyze_error(
            origin,
            status_code=403,
            code="REQUEST_ORIGIN_NOT_TRUSTED",
        )

        csrf_failure = self.client.post(
            "/api/analyze",
            headers={
                "Origin": "http://testserver",
                "X-Request-ID": "csrf-request",
            },
        )
        self.assert_analyze_error(
            csrf_failure,
            status_code=403,
            code="CSRF_VALIDATION_FAILED",
        )

    def test_disabled_expired_and_revoked_sessions_have_request_ids(self):
        csrf = self.login()
        db = session_factory(self.settings.database_url)()
        try:
            user = db.get(User, self.admin_id)
            user.is_active = False
            db.commit()
        finally:
            db.close()
        disabled = self.client.post(
            "/api/analyze",
            headers=self.unsafe_headers(csrf, "disabled-request"),
        )
        self.assert_analyze_error(
            disabled,
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
        )

        db = session_factory(self.settings.database_url)()
        try:
            user = db.get(User, self.admin_id)
            user.is_active = True
            db.commit()
        finally:
            db.close()
        csrf = self.login()
        db = session_factory(self.settings.database_url)()
        try:
            session = db.scalar(
                select(UserSession).order_by(UserSession.created_at.desc())
            )
            session.idle_expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        expired = self.client.post(
            "/api/analyze",
            headers=self.unsafe_headers(csrf, "expired-request"),
        )
        self.assert_analyze_error(
            expired,
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
        )

        csrf = self.login()
        db = session_factory(self.settings.database_url)()
        try:
            session = db.scalar(
                select(UserSession).order_by(UserSession.created_at.desc())
            )
            session.revoked_at = utc_now()
            session.revoke_reason = "test"
            db.commit()
        finally:
            db.close()
        revoked = self.client.post(
            "/api/analyze",
            headers=self.unsafe_headers(csrf, "revoked-request"),
        )
        self.assert_analyze_error(
            revoked,
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
        )

    def test_database_failure_is_safe_and_correlated(self):
        private_database_text = "PRIVATE SQL SELECT secret_column"
        with patch(
            "app.auth.middleware.AuthService.authenticate",
            side_effect=OperationalError(
                private_database_text,
                {},
                RuntimeError("PRIVATE_DATABASE_EXCEPTION"),
            ),
        ):
            response = self.client.post(
                "/api/analyze",
                headers={"X-Request-ID": "database-request"},
            )
        self.assert_analyze_error(
            response,
            status_code=503,
            code="ANALYZE_PERSISTENCE_FAILED",
        )
        self.assertNotIn(private_database_text, response.text)
        self.assertNotIn("PRIVATE_DATABASE_EXCEPTION", self.stream.getvalue())

    def test_unknown_exception_is_safe_and_correlated(self):
        csrf = self.login()
        response = self.client.post(
            "/api/analyze",
            headers={
                **self.unsafe_headers(csrf, "unknown-request"),
                "X-Test-Failure": "unknown",
            },
        )
        self.assert_analyze_error(
            response,
            status_code=500,
            code="UNEXPECTED_SERVER_ERROR",
        )
        self.assertNotIn("PRIVATE_EXCEPTION_TEXT", response.text)
        self.assertNotIn("PRIVATE_EXCEPTION_TEXT", self.stream.getvalue())

    def test_success_and_admin_rejection_are_correlated_without_contract_expansion(self):
        csrf = self.login()
        success = self.client.post(
            "/api/analyze",
            headers=self.unsafe_headers(csrf, "successful-request"),
        )
        self.assertEqual(success.status_code, 200, success.text)
        self.assertEqual(success.headers["X-Request-ID"], "successful-request")

        self.client.cookies.clear()
        user_csrf = self.login(
            email="user@example.com",
            password="another correct passphrase",
        )
        rejection = self.client.delete(
            "/api/monitoring/private",
            headers=self.unsafe_headers(user_csrf, "admin-rejection"),
        )
        self.assertEqual(rejection.status_code, 403)
        self.assertEqual(
            rejection.json(),
            {"detail": "Administrator role required."},
        )
        self.assertEqual(rejection.headers["X-Request-ID"], "admin-rejection")

    def test_structured_completion_log_correlates_without_secrets(self):
        csrf = self.login()
        secret = "TEST_ONLY_COOKIE_AND_CSRF_SECRET"
        self.client.cookies.set("unrelated_secret", secret)
        response = self.client.post(
            "/api/analyze",
            headers={
                **self.unsafe_headers(csrf, "logged-request"),
                "X-Private-Value": secret,
            },
        )
        self.assertEqual(response.status_code, 200)
        events = [
            json.loads(line)
            for line in self.stream.getvalue().splitlines()
            if line.strip()
        ]
        completion = [
            event
            for event in events
            if event.get("message") == "http_request_completed"
            and event.get("route") == "/api/analyze"
        ][-1]
        self.assertEqual(completion["request_id"], "logged-request")
        self.assertEqual(completion["status_code"], 200)
        self.assertNotIn(secret, self.stream.getvalue())


if __name__ == "__main__":
    unittest.main()
