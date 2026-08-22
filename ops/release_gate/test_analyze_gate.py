from __future__ import annotations

import copy
import unittest

from ops.release_gate.analyze_gate import HARD_GATE_KEYS, evaluate


def passing_evidence() -> dict[str, object]:
    return {
        "hard_gates": {key: True for key in HARD_GATE_KEYS},
        "runs": [
            {
                "request_id": f"release-gate-{index}",
                "public_https": True,
                "http_status": 200,
                "backend_final_status": 200,
                "transport_error": None,
                "empty_reply": False,
                "connection_failure": False,
                "response_complete": True,
                "response_request_id_matches": True,
                "output_correct": True,
                "java_fallback": False,
                "fallback_result_correct": True,
                "java_observation_present": True,
                "edge_log_scanned": True,
                "frontend_log_scanned": True,
                "backend_log_scanned": True,
                "java_log_scanned": True,
                "rag_enabled": True,
                "history_persisted": True,
                "metrics_persisted": True,
                "persistent_runtime_error": False,
                "warnings": [],
            }
            for index in range(5)
        ],
        "warnings": [],
    }


class AnalyzeReleaseGateTests(unittest.TestCase):
    def test_zero_of_five_fallback_is_pass(self):
        result = evaluate(passing_evidence())
        self.assertEqual(result.verdict, "PASS")
        self.assertTrue(result.release_allowed)

    def test_one_of_five_fallback_is_pass_with_warning(self):
        evidence = passing_evidence()
        evidence["runs"][2]["java_fallback"] = True
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "PASS_WITH_WARNING")
        self.assertTrue(result.release_allowed)
        self.assertEqual(result.fallback_count, 1)

    def test_two_of_five_fallback_is_fail(self):
        evidence = passing_evidence()
        evidence["runs"][0]["java_fallback"] = True
        evidence["runs"][3]["java_fallback"] = True
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "FAIL")
        self.assertFalse(result.release_allowed)

    def test_two_consecutive_fallbacks_are_fail(self):
        evidence = passing_evidence()
        evidence["runs"][1]["java_fallback"] = True
        evidence["runs"][2]["java_fallback"] = True
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "FAIL")
        self.assertTrue(result.consecutive_fallback)
        self.assertIn("two_consecutive_java_fallbacks", result.failures)

    def test_one_empty_reply_is_hard_fail(self):
        evidence = passing_evidence()
        evidence["runs"][4].update(
            http_status=None,
            backend_final_status=None,
            empty_reply=True,
            transport_error="empty_reply",
            response_complete=False,
            output_correct=False,
            history_persisted=False,
            metrics_persisted=False,
            java_observation_present=False,
        )
        self.assertEqual(evaluate(evidence).verdict, "HARD_FAIL")

    def test_one_public_non_2xx_is_hard_fail(self):
        evidence = passing_evidence()
        evidence["runs"][1]["http_status"] = 503
        evidence["runs"][1]["backend_final_status"] = 503
        self.assertEqual(evaluate(evidence).verdict, "HARD_FAIL")

    def test_backup_database_and_immutable_gates_remain_hard(self):
        for key in ("backup", "postgresql", "immutable_images"):
            with self.subTest(key=key):
                evidence = copy.deepcopy(passing_evidence())
                evidence["hard_gates"][key] = False
                result = evaluate(evidence)
                self.assertEqual(result.verdict, "HARD_FAIL")
                self.assertIn(f"hard_gate_failed:{key}", result.hard_failures)

    def test_latency_warning_does_not_block_success(self):
        evidence = passing_evidence()
        evidence["runs"][0]["warnings"] = ["single_java_latency_spike"]
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "PASS")
        self.assertIn("run_1:single_java_latency_spike", result.warnings)


if __name__ == "__main__":
    unittest.main()
