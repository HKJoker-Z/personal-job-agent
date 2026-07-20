import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.feature_retirement import FeatureRetirementMiddleware, is_removed_api
from database import get_connection, insert_application_record, list_application_records
from test_support import temporary_test_database
from unittest.mock import patch
from app.agent_runs.worker import embedded_dispatcher_enabled


class FeatureRetirementTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()

        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
        def fallback(path: str):
            return {"path": path}

        app.add_middleware(FeatureRetirementMiddleware)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_removed_routes_return_one_safe_410_contract(self):
        paths = [
            "/api/jobs", "/api/jobs/one", "/api/applications", "/api/approvals/one",
            "/api/tasks", "/api/application-packages/one", "/api/material-versions/one",
            "/api/job-rank-runs",
        ]
        for path in paths:
            for method in ("GET", "POST", "PATCH", "DELETE"):
                response = self.client.request(method, path)
                self.assertEqual(response.status_code, 410, (method, path, response.text))
                self.assertEqual(response.json(), {
                    "error": {
                        "code": "FEATURE_REMOVED",
                        "message": "This feature is not available in Version 2.0.1.",
                    }
                })

    def test_removed_mutations_cannot_reach_the_route_handler(self):
        for path in ("/api/jobs", "/api/applications", "/api/approvals", "/api/tasks"):
            self.assertTrue(is_removed_api(path, "POST"))
            self.assertEqual(self.client.post(path).status_code, 410)

    def test_agent_runs_are_readable_and_cancellable_but_not_created_or_resumed(self):
        self.assertFalse(is_removed_api("/api/agent-runs", "GET"))
        self.assertFalse(is_removed_api("/api/agent-runs/one", "GET"))
        self.assertFalse(is_removed_api("/api/agent-runs/one/cancel", "POST"))
        self.assertTrue(is_removed_api("/api/agent-runs", "POST"))
        self.assertTrue(is_removed_api("/api/agent-runs/one/retry", "POST"))
        self.assertTrue(is_removed_api("/api/agent-runs/one/resume", "POST"))

    def test_unrelated_analysis_and_history_routes_remain_available(self):
        self.assertEqual(self.client.post("/api/analyze").status_code, 200)
        self.assertEqual(self.client.get("/api/history").status_code, 200)

    def test_standalone_dispatcher_can_disable_the_worker_copy(self):
        with patch.dict("os.environ", {"OUTBOX_DISPATCH_IN_WORKER": "false"}):
            self.assertFalse(embedded_dispatcher_enabled())

    def test_retirement_does_not_delete_historical_rows(self):
        with temporary_test_database():
            row_id = insert_application_record(
                {"company_name": "Historical Example", "job_title": "Archived Role"},
                job_url=None,
                resume_filename=None,
            )
            self.assertEqual(self.client.post("/api/applications").status_code, 410)
            rows, total = list_application_records(status=None, search=None, limit=10, offset=0)
            self.assertEqual(total, 1)
            self.assertEqual(rows[0]["id"], row_id)
            with get_connection() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) AS count FROM application_records").fetchone()["count"], 1)


if __name__ == "__main__":
    unittest.main()
