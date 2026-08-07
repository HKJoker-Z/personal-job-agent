import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx

from candidates import deepseek_direct_connectivity_candidate as candidate


class DeepSeekDirectConnectivityCandidateTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "",
                "NO_PROXY": "",
                "http_proxy": "http://127.0.0.1:1",
                "https_proxy": "http://127.0.0.1:1",
                "all_proxy": "",
                "no_proxy": "",
            },
            clear=False,
        )
        self.environment.start()
        self.origin = urlsplit("https://api.deepseek.com")

    def tearDown(self):
        self.environment.stop()

    def test_path_a_uses_environment_proxy_transport(self):
        candidate._configure_path("A", self.origin.hostname, container_mode=False)
        client = httpx.Client(trust_env=True)
        try:
            self.assertTrue(candidate._transport_selected(client, self.origin))
        finally:
            client.close()

    def test_path_b_appends_only_deepseek_hostname_and_bypasses_proxy(self):
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"
        os.environ["no_proxy"] = "localhost,127.0.0.1"
        configured = candidate._configure_path("B", self.origin.hostname, container_mode=False)
        self.assertTrue(configured["selective_no_proxy_appended"])
        self.assertIn("localhost", os.environ["NO_PROXY"])
        self.assertIn("127.0.0.1", os.environ["NO_PROXY"])
        self.assertIn("api.deepseek.com", os.environ["NO_PROXY"])
        client = httpx.Client(trust_env=True)
        try:
            self.assertFalse(candidate._transport_selected(client, self.origin))
        finally:
            client.close()

    def test_path_c_ignores_environment_proxy_for_its_client_only(self):
        candidate._configure_path("C", self.origin.hostname, container_mode=False)
        direct_client = httpx.Client(trust_env=False)
        try:
            self.assertFalse(candidate._transport_selected(direct_client, self.origin))
        finally:
            direct_client.close()
        proxy_client = httpx.Client(trust_env=True)
        try:
            self.assertTrue(candidate._transport_selected(proxy_client, self.origin))
        finally:
            proxy_client.close()

    def test_container_loopback_proxy_rewrite_preserves_secretless_shape(self):
        original = "http://127.0.0.1:7890"
        rewritten, changed = candidate._rewrite_loopback_proxy(
            original,
            container_mode=True,
        )
        self.assertTrue(changed)
        self.assertTrue(rewritten.startswith("http://"))
        self.assertIn("host.docker.internal", rewritten)
        self.assertTrue(rewritten.endswith(":7890"))

    def test_preflight_summary_has_no_proxy_values_or_auth_fields(self):
        configured = {
            "original_proxy_presence": {
                "HTTP_PROXY": True,
                "HTTPS_PROXY": True,
                "ALL_PROXY": False,
                "NO_PROXY": False,
                "http_proxy": True,
                "https_proxy": True,
                "all_proxy": False,
                "no_proxy": False,
            },
            "all_proxy_cleared_for_candidate": True,
            "container_loopback_proxy_rewritten": False,
            "selective_no_proxy_appended": False,
        }
        record = {
            "category": "transport_success",
            "status": 401,
            "transport_success": True,
            "proxy_transport_selected": True,
            "proxy_connection_observed": True,
            "tcp_connect_ms": 2.0,
            "tls_ms": 3.0,
            "total_ms": 8.0,
            "configured": configured,
            "trust_env": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preflight.json"
            with (
                patch.object(candidate, "_source_origin", return_value=self.origin),
                patch.object(candidate, "_origin_metadata", return_value={"hostname": "api.deepseek.com"}),
                patch.object(candidate, "_one_preflight", return_value=record),
            ):
                summary = candidate._preflight("A", 20, Path("unused"), output)
            rendered = output.read_text(encoding="utf-8")
        self.assertEqual(summary["attempt_count"], 20)
        self.assertNotIn("127.0.0.1:1", rendered)
        self.assertIn('"authorization_header_sent": false', rendered)
        json.loads(rendered)

    def test_transport_error_categories_are_stable(self):
        self.assertEqual(
            candidate._classify_transport_error(TimeoutError()),
            "other_transport_failure",
        )
        self.assertEqual(
            candidate._classify_transport_error(ConnectionRefusedError()),
            "connection_refused",
        )

    def test_candidate_builder_requires_bounded_timeout_and_zero_sdk_retries(self):
        fake_deadline = SimpleNamespace(
            call_timeout=lambda **_kwargs: SimpleNamespace(
                timeout=httpx.Timeout(connect=1, read=2, write=1, pool=1),
            ),
            absolute_deadline=9999999999.0,
        )
        runtime = SimpleNamespace(
            request_timeout_seconds=60,
            deepseek_api_key="synthetic-test-key",
        )
        with patch.dict(os.environ, {"APP_ENV": "test", "APP_DATABASE_PATH": str(Path(tempfile.gettempdir()) / "pja-direct-builder-test.sqlite")}):
            with patch("legacy_application.OpenAI") as openai:
                candidate._candidate_build_provider_client(
                    runtime,
                    deadline=fake_deadline,
                    kind="primary",
                    trust_env=False,
                )
                self.assertEqual(openai.call_args.kwargs["max_retries"], 0)
                self.assertFalse(openai.call_args.kwargs["http_client"].trust_env)
                openai.call_args.kwargs["http_client"].close()


if __name__ == "__main__":
    unittest.main()
