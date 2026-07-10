import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
import monitoring_service
from database import init_db
from monitoring_service import (
    build_analysis_metric,
    get_overview,
    get_rag_metrics,
    get_recommendation_metrics,
    get_security_metrics,
    get_trace_detail,
    get_workflow_step_performance,
    nearest_rank_percentile,
    persist_analysis_metrics,
    persist_analysis_metrics_best_effort,
    record_step_metrics,
)


class MonitoringServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.tmpdir.name) / "app.db"
        init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def metric(self, workflow_id="wf-1", outcome="completed", **overrides):
        params = {
            "workflow_id": workflow_id,
            "workflow_status": outcome,
            "workflow_duration_ms": 100.0,
            "workflow_duration_us": 100000,
            "workflow_steps": [
                {"key": "run_llm_analysis", "status": "completed", "duration_ms": 80.0, "duration_us": 80000},
                {"key": "retrieve_project_evidence", "status": "completed", "duration_ms": 5.0, "duration_us": 5000},
            ],
            "outcome": outcome,
            "rag_mode": "project",
            "rag_source_count": 2,
            "rag_reconciliation_count": 1,
            "security_scan": {"risk_level": "low", "findings": []},
            "security_status": "passed",
            "json_parse_success": True,
            "saved_to_history": True,
            "application_id": 1,
            "next_action": "apply_now",
            "source_type": "text",
        }
        params.update(overrides)
        return build_analysis_metric(**params)

    def test_save_completed_analysis_metric(self):
        persist_analysis_metrics(self.metric(), [])
        self.assertEqual(get_overview()["completed"], 1)

    def test_save_blocked_analysis_metric(self):
        persist_analysis_metrics(
            self.metric(
                workflow_id="wf-blocked",
                outcome="blocked",
                workflow_status="failed",
                security_scan={"blocked": True, "risk_level": "critical", "sensitive_data_detected": True},
                security_status="blocked",
                saved_to_history=False,
                application_id=None,
            ),
            [],
        )
        self.assertEqual(get_overview()["blocked"], 1)

    def test_blocked_metric_does_not_contain_secret(self):
        persist_analysis_metrics(
            self.metric(
                workflow_id="wf-secret",
                outcome="blocked",
                security_scan={
                    "blocked": True,
                    "risk_level": "critical",
                    "sensitive_data_detected": True,
                    "findings": [{"code": "secret_api_key", "category": "secret", "severity": "critical", "source": "job_description", "message": "Credential-like content was detected."}],
                },
                security_status="blocked",
            ),
            [],
        )
        with database.get_connection() as connection:
            rows = connection.execute("SELECT * FROM analysis_metrics").fetchall()
        serialized = json.dumps([dict(row) for row in rows])
        self.assertNotIn("sk-test-only", serialized)

    def test_step_metrics_do_not_save_message(self):
        record_step_metrics("wf-step", [{"key": "parse_resume", "status": "completed", "message": "do not save", "duration_ms": 1.0}])
        with database.get_connection() as connection:
            row = connection.execute("SELECT * FROM analysis_step_metrics").fetchone()
        self.assertNotIn("message", dict(row))

    def test_workflow_id_unique_upserts(self):
        persist_analysis_metrics(self.metric("wf-unique"), [])
        persist_analysis_metrics(self.metric("wf-unique", workflow_duration_ms=200.0), [])
        with database.get_connection() as connection:
            total = connection.execute("SELECT COUNT(*) AS total FROM analysis_metrics").fetchone()["total"]
        self.assertEqual(total, 1)

    def test_overview_completion_rate(self):
        persist_analysis_metrics(self.metric("wf-a", "completed"), [])
        persist_analysis_metrics(self.metric("wf-b", "completed_with_warnings"), [])
        persist_analysis_metrics(self.metric("wf-c", "failed"), [])
        self.assertEqual(get_overview()["completion_rate"], 0.6667)

    def test_clean_success_rate(self):
        persist_analysis_metrics(self.metric("wf-a", "completed"), [])
        persist_analysis_metrics(self.metric("wf-b", "completed_with_warnings"), [])
        self.assertEqual(get_overview()["clean_success_rate"], 0.5)

    def test_zero_denominator_returns_zero(self):
        overview = get_overview()
        self.assertEqual(overview["completion_rate"], 0.0)
        self.assertEqual(overview["rag_hit_rate"], 0.0)

    def test_rag_hit_rate(self):
        persist_analysis_metrics(self.metric("wf-a", rag_source_count=1), [])
        persist_analysis_metrics(self.metric("wf-b", rag_source_count=0), [])
        self.assertEqual(get_rag_metrics()["rag_hit_rate"], 0.5)

    def test_security_warning_count(self):
        persist_analysis_metrics(self.metric("wf-warning", "completed_with_warnings", security_status="passed_with_warnings"), [])
        self.assertEqual(get_security_metrics()["passed_with_warnings"], 1)

    def test_reconciliation_count(self):
        persist_analysis_metrics(self.metric("wf-rag", rag_reconciliation_count=3), [])
        self.assertEqual(get_rag_metrics()["reconciliation_total"], 3)

    def test_finding_codes_aggregate(self):
        persist_analysis_metrics(
            self.metric(
                "wf-findings",
                security_scan={
                    "risk_level": "high",
                    "findings": [{"code": "prompt_injection_ignore_instructions", "category": "prompt_injection", "severity": "high", "source": "job_description", "message": "Instruction override language was detected."}],
                },
                security_status="passed_with_warnings",
            ),
            [],
        )
        self.assertEqual(get_security_metrics()["finding_codes"]["prompt_injection_ignore_instructions"], 1)

    def test_recommendation_distribution(self):
        persist_analysis_metrics(self.metric("wf-action", next_action="skip"), [])
        self.assertEqual(get_recommendation_metrics()["action_distribution"]["skip"], 1)

    def test_human_decision_distribution(self):
        with database.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO application_records (
                    created_at, updated_at, company_name, job_title, next_action_decision
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (monitoring_service.utc_now(), monitoring_service.utc_now(), "Co", "Role", "accepted"),
            )
        self.assertEqual(get_recommendation_metrics()["decision_distribution"]["accepted"], 1)

    def test_nearest_rank_p50(self):
        self.assertEqual(nearest_rank_percentile([10, 20, 30, 40], 50), 20.0)

    def test_nearest_rank_p95(self):
        self.assertEqual(nearest_rank_percentile([10, 20, 30, 40], 95), 40.0)

    def test_skipped_step_excluded_from_latency_percentile(self):
        record_step_metrics(
            "wf-steps",
            [
                {"key": "run_llm_analysis", "status": "skipped", "duration_ms": 9999.0},
                {"key": "run_llm_analysis", "status": "completed", "duration_ms": 10.0},
            ],
        )
        item = get_workflow_step_performance()["items"][0]
        self.assertEqual(item["p50_ms"], 10.0)

    def test_trace_detail_excludes_sensitive_fields(self):
        persist_analysis_metrics(self.metric("wf-trace"), [{"key": "run_llm_analysis", "status": "completed", "duration_ms": 1.0}])
        trace = get_trace_detail("wf-trace")
        serialized = json.dumps(trace)
        for forbidden in ("resume_text", "job_text", "job_description_text", "raw_prompt", "llm_raw_response", "message"):
            self.assertNotIn(forbidden, serialized)

    def test_missing_trace_returns_none(self):
        self.assertIsNone(get_trace_detail("missing"))

    def test_best_effort_write_failure_does_not_raise(self):
        with patch("monitoring_service.record_analysis_metric", side_effect=RuntimeError("boom")):
            with self.assertLogs("personal-job-agent.monitoring", level="WARNING"):
                persist_analysis_metrics_best_effort(self.metric("wf-safe"), [])


if __name__ == "__main__":
    unittest.main()
