import io
import json
import logging
import unittest

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from logging_utils import JsonFormatter, RequestLoggingMiddleware, safe_request_id


class LoggingUtilsTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.logger = logging.getLogger(f"test.request.{id(self)}")
        self.logger.handlers.clear()
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(JsonFormatter())
        self.logger.addHandler(handler)
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=self.logger)

        @app.get("/ok")
        async def ok():
            return {"ok": True}

        @app.post("/body")
        async def body():
            return {"ok": True}

        @app.get("/error")
        async def error(request: Request):
            request.state.error_code = "SAFE_TEST_ERROR"
            return JSONResponse(status_code=400, content={"detail": "safe"})

        @app.get("/workflow")
        async def workflow(request: Request):
            request.state.workflow_id = "workflow-safe-1"
            return {"ok": True}

        self.client = TestClient(app)

    def last_log(self):
        lines = [line for line in self.stream.getvalue().splitlines() if line]
        return json.loads(lines[-1])

    def test_request_id_is_generated(self):
        self.assertTrue(safe_request_id(None))

    def test_valid_request_id_is_preserved(self):
        request_id = "client-request_123"
        self.assertEqual(safe_request_id(request_id), request_id)

    def test_invalid_request_id_is_replaced(self):
        self.assertNotEqual(safe_request_id("invalid request/id"), "invalid request/id")

    def test_overlong_request_id_is_replaced(self):
        candidate = "a" * 65
        self.assertNotEqual(safe_request_id(candidate), candidate)

    def test_response_contains_request_id(self):
        response = self.client.get("/ok", headers={"X-Request-ID": "incoming-id"})
        self.assertEqual(response.headers["X-Request-ID"], "incoming-id")

    def test_duration_is_non_negative(self):
        self.client.get("/ok")
        self.assertGreaterEqual(self.last_log()["duration_ms"], 0)

    def test_log_does_not_include_admin_token(self):
        secret = "TEST_ONLY_ADMIN_TOKEN_VALUE"
        self.client.get("/ok", headers={"X-Monitoring-Admin-Token": secret})
        self.assertNotIn(secret, self.stream.getvalue())

    def test_log_does_not_include_api_key_or_query_token(self):
        secret = "TEST_ONLY_API_KEY_VALUE"
        self.client.get(f"/ok?token={secret}")
        self.assertNotIn(secret, self.stream.getvalue())

    def test_log_does_not_include_resume_or_job_body(self):
        private_body = "candidate@example.com resume text and private job description"
        self.client.post("/body", content=private_body)
        self.assertNotIn(private_body, self.stream.getvalue())
        self.assertNotIn("candidate@example.com", self.stream.getvalue())

    def test_safe_error_code_is_recorded(self):
        self.client.get("/error")
        self.assertEqual(self.last_log()["error_code"], "SAFE_TEST_ERROR")

    def test_workflow_id_can_be_correlated(self):
        self.client.get("/workflow")
        self.assertEqual(self.last_log()["workflow_id"], "workflow-safe-1")

    def test_log_is_valid_json_with_stable_fields(self):
        self.client.get("/ok")
        payload = self.last_log()
        for field in ("timestamp", "level", "request_id", "method", "route", "status_code", "duration_ms"):
            self.assertIn(field, payload)


if __name__ == "__main__":
    unittest.main()
