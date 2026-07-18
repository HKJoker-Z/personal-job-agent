import asyncio
import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

import data_management_service
from database import get_connection
from evaluation_service import list_evaluation_runs
from monitoring_service import get_overview, list_traces
from test_support import temporary_test_database


ADMIN_TOKEN = "test-admin-token-only"


class ApiClient:
    """Small synchronous wrapper that controls ASGI client IP for policy tests."""

    def __init__(self, app, client_address):
        self.app = app
        self.client_address = client_address

    def request(self, method, url, **kwargs):
        async def send_request():
            transport = httpx.ASGITransport(app=self.app, client=self.client_address)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send_request())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class DataManagementServiceTest(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_test_database()
        self.database_path = self.database_context.__enter__()
        self.previous_token = os.environ.get("MONITORING_ADMIN_TOKEN")
        self.previous_remote = os.environ.get("MONITORING_ALLOW_REMOTE_ADMIN")
        os.environ["MONITORING_ADMIN_TOKEN"] = ADMIN_TOKEN
        os.environ["MONITORING_ALLOW_REMOTE_ADMIN"] = "false"
        from main import app

        self.app = app
        self.client = ApiClient(self.app, ("127.0.0.1", 50100))

    def tearDown(self):
        if self.previous_token is None:
            os.environ.pop("MONITORING_ADMIN_TOKEN", None)
        else:
            os.environ["MONITORING_ADMIN_TOKEN"] = self.previous_token
        if self.previous_remote is None:
            os.environ.pop("MONITORING_ALLOW_REMOTE_ADMIN", None)
        else:
            os.environ["MONITORING_ALLOW_REMOTE_ADMIN"] = self.previous_remote
        self.database_context.__exit__(None, None, None)

    def headers(self, token=ADMIN_TOKEN):
        return {"X-Monitoring-Admin-Token": token}

    def monitoring_payload(self, **overrides):
        payload = {
            "mode": "all",
            "date_from": None,
            "date_to": None,
            "outcomes": [],
            "security_statuses": [],
            "risk_levels": [],
        }
        payload.update(overrides)
        return payload

    def evaluation_payload(self, **overrides):
        payload = {"mode": "all", "date_from": None, "date_to": None, "statuses": []}
        payload.update(overrides)
        return payload

    def insert_metric(
        self,
        workflow_id="workflow-1",
        created_at="2026-07-10T12:00:00+00:00",
        outcome="completed",
        security_status="passed",
        risk_level="low",
        step_count=2,
    ):
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO analysis_metrics (
                    workflow_id, created_at, outcome, security_status, security_risk_level
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (workflow_id, created_at, outcome, security_status, risk_level),
            )
            for index in range(step_count):
                connection.execute(
                    """
                    INSERT INTO analysis_step_metrics (
                        workflow_id, step_key, status, duration_ms, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (workflow_id, f"step-{index}", "completed", 1.0, created_at),
                )

    def insert_evaluation_run(self, run_id="run-1", started_at="2026-07-10T12:00:00+00:00", status="completed", result_count=2):
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (run_id, suite_name, suite_version, mode, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, "default", "1.8", "offline", status, started_at),
            )
            for index in range(result_count):
                connection.execute(
                    """
                    INSERT INTO evaluation_results (
                        run_id, case_id, case_name, category, status, checks_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, f"case-{index}", "Case", "test", "passed", "{}", started_at),
                )

    def test_destructive_endpoint_disabled_without_admin_token_configuration(self):
        os.environ.pop("MONITORING_ADMIN_TOKEN", None)
        response = self.client.post("/api/monitoring/data/preview", json=self.monitoring_payload())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error_code"], "DATA_MANAGEMENT_DISABLED")

    def test_wrong_token_is_rejected(self):
        response = self.client.post(
            "/api/monitoring/data/preview", json=self.monitoring_payload(), headers=self.headers("wrong-token")
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error_code"], "INVALID_ADMIN_TOKEN")

    def test_token_comparison_uses_compare_digest(self):
        with patch("data_management_service.hmac.compare_digest", return_value=True) as compare:
            data_management_service.authorize_destructive_request("any-value", "127.0.0.1")
        compare.assert_called_once_with("any-value", ADMIN_TOKEN)

    def test_remote_requests_are_disabled_by_default(self):
        remote_client = ApiClient(self.app, ("198.51.100.20", 50100))
        response = remote_client.post(
            "/api/monitoring/data/preview", json=self.monitoring_payload(), headers=self.headers()
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error_code"], "REMOTE_ADMIN_DISABLED")

    def test_loopback_request_still_requires_token(self):
        response = self.client.post("/api/monitoring/data/preview", json=self.monitoring_payload())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error_code"], "INVALID_ADMIN_TOKEN")

    def test_correct_token_and_loopback_can_preview(self):
        response = self.client.post(
            "/api/monitoring/data/preview", json=self.monitoring_payload(), headers=self.headers()
        )
        self.assertEqual(response.status_code, 200)

    def test_preview_all_returns_only_counts(self):
        self.insert_metric("preview-a", step_count=3)
        self.insert_metric("preview-b", step_count=1)
        response = self.client.post(
            "/api/monitoring/data/preview", json=self.monitoring_payload(), headers=self.headers()
        )
        data = response.json()
        self.assertEqual(data["analysis_metrics_count"], 2)
        self.assertEqual(data["analysis_step_metrics_count"], 4)
        self.assertNotIn("workflow_id", data)

    def test_filtered_preview_by_date(self):
        self.insert_metric("old-date", created_at="2026-06-01T12:00:00+00:00")
        self.insert_metric("new-date", created_at="2026-07-10T12:00:00+00:00")
        payload = self.monitoring_payload(mode="filtered", date_from="2026-07-10")
        response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
        self.assertEqual(response.json()["analysis_metrics_count"], 1)

    def test_filtered_preview_by_outcome(self):
        self.insert_metric("completed-outcome", outcome="completed")
        self.insert_metric("blocked-outcome", outcome="blocked")
        payload = self.monitoring_payload(mode="filtered", outcomes=["blocked"])
        response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
        self.assertEqual(response.json()["analysis_metrics_count"], 1)

    def test_filtered_preview_by_security_status(self):
        self.insert_metric("security-pass", security_status="passed")
        self.insert_metric("security-blocked", security_status="blocked")
        payload = self.monitoring_payload(mode="filtered", security_statuses=["blocked"])
        response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
        self.assertEqual(response.json()["analysis_metrics_count"], 1)

    def test_filtered_preview_by_risk_level(self):
        self.insert_metric("risk-low", risk_level="low")
        self.insert_metric("risk-critical", risk_level="critical")
        payload = self.monitoring_payload(mode="filtered", risk_levels=["critical"])
        response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
        self.assertEqual(response.json()["analysis_metrics_count"], 1)

    def test_filtered_mode_without_filter_is_rejected(self):
        response = self.client.post(
            "/api/monitoring/data/preview",
            json=self.monitoring_payload(mode="filtered"),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_all_mode_with_filter_is_rejected(self):
        response = self.client.post(
            "/api/monitoring/data/preview",
            json=self.monitoring_payload(outcomes=["completed"]),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_order_is_rejected(self):
        response = self.client.post(
            "/api/monitoring/data/preview",
            json=self.monitoring_payload(mode="filtered", date_from="2026-07-11", date_to="2026-07-10"),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_filter_values_are_rejected(self):
        for field in ("outcomes", "security_statuses", "risk_levels"):
            payload = self.monitoring_payload(mode="filtered", **{field: ["' OR 1=1 --"]})
            response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
            self.assertEqual(response.status_code, 400)

    def test_all_confirmation_mismatch_is_rejected(self):
        payload = self.monitoring_payload(confirmation="DELETE FILTERED MONITORING DATA")
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["error_code"], "CONFIRMATION_MISMATCH")

    def test_filtered_confirmation_mismatch_is_rejected(self):
        payload = self.monitoring_payload(
            mode="filtered", outcomes=["completed"], confirmation="DELETE ALL MONITORING DATA"
        )
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 400)

    def test_clear_all_deletes_parent_and_child_metrics(self):
        self.insert_metric("clear-all", step_count=3)
        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis_metrics_deleted"], 1)
        self.assertEqual(response.json()["analysis_step_metrics_deleted"], 3)
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_metrics").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_step_metrics").fetchone()[0], 0)

    def test_filtered_delete_preserves_nonmatching_metrics(self):
        self.insert_metric("delete-blocked", outcome="blocked")
        self.insert_metric("keep-completed", outcome="completed")
        payload = self.monitoring_payload(
            mode="filtered", outcomes=["blocked"], confirmation="DELETE FILTERED MONITORING DATA"
        )
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        with get_connection() as connection:
            remaining = connection.execute("SELECT workflow_id FROM analysis_metrics").fetchall()
        self.assertEqual([row["workflow_id"] for row in remaining], ["keep-completed"])

    def test_delete_one_trace_preserves_other_traces(self):
        self.insert_metric("trace-delete", step_count=2)
        self.insert_metric("trace-keep", step_count=1)
        response = self.client.request(
            "DELETE",
            "/api/monitoring/traces/trace-delete",
            json={"confirmation": "DELETE TRACE", "notes": "not persisted"},
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis_step_metrics_deleted"], 2)
        with get_connection() as connection:
            deleted_trace = connection.execute(
                "SELECT 1 FROM analysis_metrics WHERE workflow_id = ?", ("trace-delete",)
            ).fetchone()
        self.assertIsNone(deleted_trace)

    def test_delete_missing_trace_returns_not_found(self):
        response = self.client.request(
            "DELETE", "/api/monitoring/traces/missing-trace", json={"confirmation": "DELETE TRACE"}, headers=self.headers()
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["error_code"], "TRACE_NOT_FOUND")

    def test_monitoring_cleanup_preserves_application_and_project_knowledge_tables(self):
        self.insert_metric("protected")
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO application_records (created_at, updated_at, company_name, job_title) VALUES (?, ?, ?, ?)",
                ("2026-07-10T12:00:00+00:00", "2026-07-10T12:00:00+00:00", "Co", "Role"),
            )
            connection.execute(
                "INSERT INTO knowledge_documents (created_at, updated_at, title, category) VALUES (?, ?, ?, ?)",
                ("2026-07-10T12:00:00+00:00", "2026-07-10T12:00:00+00:00", "Knowledge", "Other"),
            )
        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM application_records").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0], 1)

    def test_monitoring_cleanup_preserves_evaluation_history(self):
        self.insert_metric("monitoring-only")
        self.insert_evaluation_run()
        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0], 1)

    def test_evaluation_preview_and_delete_preserve_monitoring_metrics(self):
        self.insert_metric("keep-monitoring")
        self.insert_evaluation_run(result_count=3)
        preview = self.client.post(
            "/api/evaluations/data/preview", json=self.evaluation_payload(), headers=self.headers()
        )
        self.assertEqual(preview.json()["evaluation_results_count"], 3)
        payload = self.evaluation_payload(confirmation="DELETE EVALUATION HISTORY")
        response = self.client.request("DELETE", "/api/evaluations/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evaluation_runs_deleted"], 1)
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_metrics").fetchone()[0], 1)

    def test_evaluation_filtered_preview_and_confirmation(self):
        self.insert_evaluation_run("completed-run", status="completed")
        self.insert_evaluation_run("failed-run", status="failed")
        payload = self.evaluation_payload(mode="filtered", statuses=["failed"])
        preview = self.client.post("/api/evaluations/data/preview", json=payload, headers=self.headers())
        self.assertEqual(preview.json()["evaluation_runs_count"], 1)
        response = self.client.request("DELETE", "/api/evaluations/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 400)
        payload["confirmation"] = "DELETE FILTERED EVALUATION HISTORY"
        response = self.client.request("DELETE", "/api/evaluations/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)

    def test_evaluation_cases_file_is_not_deleted(self):
        cases_path = Path(__file__).resolve().parent / "evals" / "cases.json"
        self.insert_evaluation_run()
        payload = self.evaluation_payload(confirmation="DELETE EVALUATION HISTORY")
        self.client.request("DELETE", "/api/evaluations/data", json=payload, headers=self.headers())
        self.assertTrue(cases_path.exists())

    def test_transaction_failure_rolls_back_monitoring_deletion(self):
        self.insert_metric("rollback", step_count=1)
        real_connection = get_connection()

        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            @property
            def in_transaction(self):
                return self.connection.in_transaction

            def execute(self, sql, params=()):
                if "DELETE FROM analysis_metrics" in sql:
                    raise sqlite3.OperationalError("simulated failure")
                return self.connection.execute(sql, params)

            def commit(self):
                return self.connection.commit()

            def rollback(self):
                return self.connection.rollback()

            def close(self):
                return self.connection.close()

        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        with patch("data_management_service.get_connection", return_value=FailingConnection(real_connection)):
            with self.assertRaises(data_management_service.DataManagementError):
                data_management_service.delete_monitoring_data(payload)
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_metrics").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_step_metrics").fetchone()[0], 1)

    def test_zero_record_deletion_is_successful_and_monitoring_zero_state_is_valid(self):
        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis_metrics_deleted"], 0)
        self.assertEqual(get_overview()["total_analyses"], 0)
        self.assertEqual(list_traces()["items"], [])

    def test_injection_style_filter_and_extra_table_field_cannot_delete_data(self):
        self.insert_metric("safe-filter")
        payload = self.monitoring_payload(
            mode="filtered",
            outcomes=["completed'; DELETE FROM application_records; --"],
            table="application_records",
        )
        response = self.client.post("/api/monitoring/data/preview", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 400)
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM analysis_metrics").fetchone()[0], 1)

    def test_safe_responses_do_not_include_deleted_data_or_token(self):
        self.insert_metric("safe-response")
        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        response = self.client.request("DELETE", "/api/monitoring/data", json=payload, headers=self.headers())
        serialized = json.dumps(response.json())
        self.assertNotIn(ADMIN_TOKEN, serialized)
        self.assertNotIn("safe-response", serialized)

    def test_remote_enabled_still_requires_correct_token(self):
        os.environ["MONITORING_ALLOW_REMOTE_ADMIN"] = "true"
        remote_client = ApiClient(self.app, ("203.0.113.5", 50100))
        response = remote_client.post(
            "/api/monitoring/data/preview", json=self.monitoring_payload(), headers=self.headers("bad")
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error_code"], "INVALID_ADMIN_TOKEN")

    def test_evaluation_all_mode_rejects_status_filter(self):
        response = self.client.post(
            "/api/evaluations/data/preview",
            json=self.evaluation_payload(statuses=["completed"]),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_evaluation_rejects_invalid_status_filter(self):
        response = self.client.post(
            "/api/evaluations/data/preview",
            json=self.evaluation_payload(mode="filtered", statuses=["DROP TABLE"]),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_cleanup_rejects_date_range_larger_than_ten_years(self):
        response = self.client.post(
            "/api/monitoring/data/preview",
            json=self.monitoring_payload(mode="filtered", date_from="2010-01-01", date_to="2026-01-01"),
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_trace_identifier_is_rejected(self):
        response = self.client.request(
            "DELETE", "/api/monitoring/traces/invalid%20trace", json={"confirmation": "DELETE TRACE"}, headers=self.headers()
        )
        self.assertEqual(response.status_code, 400)

    def test_empty_evaluation_cleanup_returns_success_and_empty_run_list(self):
        payload = self.evaluation_payload(confirmation="DELETE EVALUATION HISTORY")
        response = self.client.request("DELETE", "/api/evaluations/data", json=payload, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evaluation_runs_deleted"], 0)
        self.assertEqual(list_evaluation_runs()["items"], [])

    def test_trace_cleanup_preserves_application_record(self):
        self.insert_metric("trace-preserves-history")
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO application_records (created_at, updated_at, company_name, job_title) VALUES (?, ?, ?, ?)",
                ("2026-07-10T12:00:00+00:00", "2026-07-10T12:00:00+00:00", "Co", "Role"),
            )
        self.client.request(
            "DELETE",
            "/api/monitoring/traces/trace-preserves-history",
            json={"confirmation": "DELETE TRACE"},
            headers=self.headers(),
        )
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM application_records").fetchone()[0], 1)

    def test_monitoring_delete_executes_child_before_parent(self):
        self.insert_metric("ordered-delete", step_count=1)
        real_connection = get_connection()
        statements = []

        class RecordingConnection:
            def __init__(self, connection):
                self.connection = connection

            @property
            def in_transaction(self):
                return self.connection.in_transaction

            def execute(self, sql, params=()):
                statements.append(" ".join(sql.split()))
                return self.connection.execute(sql, params)

            def commit(self):
                return self.connection.commit()

            def rollback(self):
                return self.connection.rollback()

            def close(self):
                return self.connection.close()

        payload = self.monitoring_payload(confirmation="DELETE ALL MONITORING DATA")
        with patch("data_management_service.get_connection", return_value=RecordingConnection(real_connection)):
            data_management_service.delete_monitoring_data(payload)
        child_index = next(index for index, sql in enumerate(statements) if "DELETE FROM analysis_step_metrics" in sql)
        parent_index = next(index for index, sql in enumerate(statements) if "DELETE FROM analysis_metrics" in sql)
        self.assertLess(child_index, parent_index)

    def test_authentication_error_does_not_echo_token(self):
        with self.assertRaises(data_management_service.DataManagementError) as caught:
            data_management_service.authorize_destructive_request("not-the-token", "127.0.0.1")
        self.assertNotIn("not-the-token", caught.exception.message)
        self.assertNotIn(ADMIN_TOKEN, caught.exception.message)

    def test_status_does_not_leak_token_or_database_path(self):
        response = self.client.get("/api/monitoring/data-management/status")
        serialized = json.dumps(response.json())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(ADMIN_TOKEN, serialized)
        self.assertNotIn(str(self.database_path), serialized)
        self.assertTrue(response.json()["test_database_isolation"])

    def test_health_endpoint_reports_stable_version(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], "2.0.0")


if __name__ == "__main__":
    unittest.main()
