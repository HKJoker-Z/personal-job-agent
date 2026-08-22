from __future__ import annotations

import copy
import unittest

from ops.release_gate.analyze_gate import HARD_GATE_KEYS, evaluate
from ops.release_gate.collect_analyze import (
    PRODUCTION_DIRECT_PATH,
    direct_curl_options,
    direct_request_environment,
    production_target,
    proxy_environment_names,
)


def passing_evidence() -> dict[str, object]:
    return {
        "acceptance_path": "candidate-public-equivalent",
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
                "edge_access_observation_present": True,
                "edge_status": 200,
                "edge_upstream_status": 200,
                "edge_bytes_sent": 1024,
                "frontend_access_observation_present": True,
                "frontend_status": 200,
                "frontend_upstream_status": 200,
                "frontend_bytes_sent": 1024,
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


def production_direct_evidence() -> dict[str, object]:
    evidence = passing_evidence()
    evidence["acceptance_path"] = PRODUCTION_DIRECT_PATH
    direct = {
        "target_hostname": "203.0.113.20",
        "target_port": 8443,
        "target_resolved_ips": ["203.0.113.20"],
        "request_proxy_environment_removed": True,
        "direct_interface": "eth0",
        "target_source_ip": "10.0.0.4",
        "local_ip": "10.0.0.4",
        "direct_local_source_verified": True,
        "route_interface": "eth0",
        "route_source_ip": "10.0.0.4",
        "direct_route_verified": True,
        "remote_ip": "203.0.113.20",
        "remote_port": 8443,
        "http_status": 200,
        "response_bytes": 128,
        "https_scheme": True,
        "tls_verified": True,
        "direct_path_verified": True,
    }
    health_probe = dict(direct, path="/api/health")
    ready_probe = dict(direct, path="/api/ready")
    evidence["direct_path_probes"] = [health_probe, ready_probe]
    for run in evidence["runs"]:
        run.update(
            direct_path_required=True,
            direct_path_verified=True,
            request_proxy_environment_removed=True,
            direct_interface="eth0",
            target_source_ip="10.0.0.4",
            client_local_ip="10.0.0.4",
            direct_local_source_verified=True,
            route_interface="eth0",
            route_source_ip="10.0.0.4",
            direct_route_verified=True,
            client_remote_ip="203.0.113.20",
            client_remote_port=8443,
            target_hostname="203.0.113.20",
            target_port=8443,
            target_resolved_ips=["203.0.113.20"],
        )
    return evidence


class AnalyzeReleaseGateTests(unittest.TestCase):
    def test_https_proxy_is_bypassed_for_exact_production_host(self):
        environment = {
            "PATH": "/usr/bin",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
        }
        host, port = production_target("https://203.0.113.20:8443")
        self.assertEqual((host, port), ("203.0.113.20", 8443))
        self.assertEqual(
            direct_curl_options(host, "eth0"),
            ["--noproxy", "203.0.113.20", "--interface", "eth0"],
        )
        self.assertNotIn("HTTPS_PROXY", direct_request_environment(environment))

    def test_missing_no_proxy_does_not_disable_scoped_bypass(self):
        environment = {"HTTPS_PROXY": "http://127.0.0.1:7890", "PATH": "/usr/bin"}
        self.assertNotIn("NO_PROXY", environment)
        self.assertEqual(direct_curl_options("prod.example"), ["--noproxy", "prod.example"])
        self.assertEqual(direct_request_environment(environment), {"PATH": "/usr/bin"})

    def test_uppercase_and_lowercase_proxy_variables_are_removed(self):
        environment = {
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7891",
            "NO_PROXY": "localhost",
            "http_proxy": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
            "all_proxy": "socks5://127.0.0.1:7891",
            "no_proxy": "localhost",
            "SAFE": "kept",
        }
        self.assertEqual(set(proxy_environment_names(environment)), set(environment) - {"SAFE"})
        self.assertEqual(direct_request_environment(environment), {"SAFE": "kept"})

    def test_loopback_remote_socket_is_production_hard_fail(self):
        evidence = production_direct_evidence()
        evidence["runs"][0]["client_remote_ip"] = "127.0.0.1"
        evidence["runs"][0]["client_remote_port"] = 7890
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "HARD_FAIL")
        self.assertTrue(
            any("remote_is_loopback_proxy" in failure for failure in result.hard_failures)
        )

    def test_resolved_production_remote_socket_is_direct_path_pass(self):
        result = evaluate(production_direct_evidence())
        self.assertEqual(result.verdict, "PASS")
        self.assertTrue(result.release_allowed)

    def test_tun_local_source_is_production_hard_fail(self):
        evidence = production_direct_evidence()
        evidence["runs"][0]["client_local_ip"] = "198.18.0.1"
        evidence["runs"][0]["route_interface"] = "Meta"
        evidence["runs"][0]["route_source_ip"] = "198.18.0.1"
        evidence["runs"][0]["direct_local_source_verified"] = False
        evidence["runs"][0]["direct_route_verified"] = False
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "HARD_FAIL")
        self.assertTrue(
            any("local_source_not_bound_interface" in item for item in result.hard_failures)
        )

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

    def test_missing_nginx_access_observation_is_hard_fail(self):
        evidence = passing_evidence()
        evidence["runs"][0]["edge_access_observation_present"] = False
        result = evaluate(evidence)
        self.assertEqual(result.verdict, "HARD_FAIL")
        self.assertIn("run_1:edge_access_observation_missing", result.hard_failures)


if __name__ == "__main__":
    unittest.main()
