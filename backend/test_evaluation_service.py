import json
import unittest

from evaluation_service import (
    FAILURE_SUMMARY_LIMIT,
    load_evaluation_suite,
    get_evaluation_run,
    list_evaluation_runs,
    run_case,
    run_evaluation_suite,
    safe_failure_summary,
    validate_suite_schema,
)
from test_support import temporary_test_database


TEST_ONLY_FAKE_SECRET = "sk-test-only-1234567890abcdef123456"


class EvaluationServiceTest(unittest.TestCase):
    def setUp(self):
        self.database_context = temporary_test_database()
        self.database_path = self.database_context.__enter__()
        self.suite = load_evaluation_suite("default")

    def tearDown(self):
        self.database_context.__exit__(None, None, None)

    def case_by_id(self, case_id):
        return next(case for case in self.suite["cases"] if case["id"] == case_id)

    def test_cases_json_loads(self):
        self.assertGreaterEqual(len(self.suite["cases"]), 14)

    def test_suite_schema_validates(self):
        validate_suite_schema(self.suite)

    def test_unknown_runner_is_error(self):
        result = run_case({"id": "x", "name": "Unknown", "category": "test", "runner": "missing", "input": {}, "expected": {}})
        self.assertEqual(result["status"], "error")

    def test_security_normal_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("security-normal-001"))["status"], "passed")

    def test_injection_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("security-injection-001"))["status"], "passed")

    def test_secret_blocked_case_passes(self):
        result = run_case(self.case_by_id("security-secret-001"))
        self.assertEqual(result["status"], "passed")
        self.assertNotIn(TEST_ONLY_FAKE_SECRET, json.dumps(result))

    def test_pii_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("pii-email-001"))["status"], "passed")
        self.assertEqual(run_case(self.case_by_id("pii-phone-001"))["status"], "passed")

    def test_safe_prompt_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("safe-prompt-001"))["status"], "passed")

    def test_rag_retrieval_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("rag-retrieval-001"))["status"], "passed")

    def test_rag_reconciliation_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("rag-reconciliation-001"))["status"], "passed")

    def test_recommendation_cases_pass(self):
        for case_id in ("recommendation-apply-001", "recommendation-improve-001", "recommendation-skip-001"):
            self.assertEqual(run_case(self.case_by_id(case_id))["status"], "passed")

    def test_workflow_timing_case_passes(self):
        self.assertEqual(run_case(self.case_by_id("workflow-timing-001"))["status"], "passed")

    def test_output_leakage_case_passes(self):
        result = run_case(self.case_by_id("output-leakage-001"))
        self.assertEqual(result["status"], "passed")
        self.assertNotIn(TEST_ONLY_FAKE_SECRET, json.dumps(result))

    def test_evaluation_does_not_call_deepseek(self):
        result = run_evaluation_suite("default", "offline")
        self.assertFalse(any("deepseek" in json.dumps(item).lower() for item in result["results"]))

    def test_evaluation_run_saved(self):
        result = run_evaluation_suite("default", "offline")
        self.assertEqual(list_evaluation_runs()["total"], 1)
        self.assertEqual(get_evaluation_run(result["run_id"])["run_id"], result["run_id"])

    def test_evaluation_results_saved(self):
        result = run_evaluation_suite("default", "offline")
        stored = get_evaluation_run(result["run_id"])
        self.assertEqual(len(stored["results"]), result["total_cases"])

    def test_database_result_does_not_store_full_input(self):
        result = run_evaluation_suite("default", "offline")
        stored = json.dumps(get_evaluation_run(result["run_id"]))
        self.assertNotIn("Ignore all previous instructions", stored)
        self.assertNotIn(TEST_ONLY_FAKE_SECRET, stored)

    def test_failure_summary_length_limited(self):
        self.assertLessEqual(len(safe_failure_summary("x" * 2000)), FAILURE_SUMMARY_LIMIT)

    def test_failure_summary_redacts_test_secret(self):
        self.assertNotIn(TEST_ONLY_FAKE_SECRET, safe_failure_summary(TEST_ONLY_FAKE_SECRET))

    def test_pass_rate_calculated(self):
        result = run_evaluation_suite("default", "offline")
        self.assertEqual(result["pass_rate"], result["passed_cases"] / result["total_cases"])


if __name__ == "__main__":
    unittest.main()
