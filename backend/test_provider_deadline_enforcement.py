"""Offline regression tests for the bounded synchronous Provider boundary."""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

import legacy_application
from analysis_contract import MODEL_PROVIDER_ERROR, ModelOutputError, ProviderAnalysisResponse
from analysis_fallback import deterministic_job_summary, deterministic_match_reasons, local_fallback_result
from provider_deadline import DeadlineHttpxClient, ProviderDeadline


VALID_CONTENT = json.dumps(
    {
        "matched_skills": ["Python"],
        "missing_skills": ["Kubernetes"],
        "unknown_skills": [],
        "concise_dimension_assessments": {
            "skills_match": {"score": 80, "assessment": "Synthetic evidence.", "evidence_ids": ["resume"]}
        },
        "evidence_references": [{"skill": "Python", "evidence_ids": ["resume"]}],
        "unsupported_claim_candidates": [],
        "concise_recommendations": ["Keep evidence bounded."],
    }
)


def completion(content: str = VALID_CONTENT) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


class _ProviderDeadlineTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "DEEPSEEK_API_KEY": "synthetic-test-key",
                "MOCK_PROVIDER_ENABLED": "false",
                "PROVIDER_RETRY_BACKOFF_SECONDS": "0",
                "HTTP_PROXY": "",
                "HTTPS_PROXY": "",
                "ALL_PROXY": "",
                "http_proxy": "",
                "https_proxy": "",
                "all_proxy": "",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()


class ProviderDeadlineContractTest(_ProviderDeadlineTestBase):
    def test_one_absolute_deadline_covers_phase_and_request_safety_cap(self):
        deadline = ProviderDeadline.for_phase(
            phase_started_monotonic=100.0,
            configured_deadline_seconds=130,
            request_safety_deadline=300.0,
        )
        self.assertEqual(deadline.absolute_deadline, 230.0)
        self.assertEqual(
            deadline.call_timeout(configured_timeout_seconds=60, now=100.0).budget_seconds,
            60.0,
        )
        self.assertEqual(
            deadline.call_timeout(
                configured_timeout_seconds=60,
                kind="retry",
                now=100.0,
            ).budget_seconds,
            60.0,
        )
        self.assertEqual(deadline.call_timeout(configured_timeout_seconds=60, now=100.0).timeout.read, 60.0)

    def test_per_attempt_timeout_is_derived_from_remaining_deadline(self):
        deadline = ProviderDeadline(100.0)
        timeout = deadline.call_timeout(configured_timeout_seconds=60, now=0.0)
        self.assertIsNotNone(timeout)
        assert timeout is not None
        self.assertEqual(timeout.budget_seconds, 60.0)
        self.assertEqual(timeout.timeout.connect, 5.0)
        self.assertEqual(timeout.timeout.read, 60.0)
        self.assertEqual(timeout.timeout.write, 10.0)
        self.assertEqual(timeout.timeout.pool, 5.0)
        self.assertIsNone(deadline.call_timeout(configured_timeout_seconds=60, now=70.0))

    def test_retry_reserve_prevents_new_call_when_only_finalization_time_remains(self):
        deadline = ProviderDeadline(100.0)
        self.assertIsNone(
            deadline.call_timeout(configured_timeout_seconds=60, kind="retry", now=69.8)
        )

    def test_repair_reserve_prevents_new_call_when_repair_cannot_finish_safely(self):
        deadline = ProviderDeadline(100.0)
        self.assertIsNone(
            deadline.call_timeout(configured_timeout_seconds=60, kind="repair", now=65.1)
        )

    def test_expired_primary_does_not_construct_a_provider_client(self):
        with patch("legacy_application.OpenAI") as openai:
            with self.assertRaises(ModelOutputError) as raised:
                legacy_application.call_deepseek_raw(
                    "Synthetic resume",
                    "Synthetic job",
                    deadline_monotonic=time.monotonic() - 0.01,
                )
        self.assertEqual(raised.exception.error_code, MODEL_PROVIDER_ERROR)
        self.assertEqual(raised.exception.metadata["fallback_reason"], "provider_deadline_exhausted")
        self.assertTrue(raised.exception.metadata["deadline_exhausted"])
        openai.assert_not_called()

    def test_empty_provider_response_is_bounded_and_retryable(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [completion(""), completion()]
        with patch("legacy_application.OpenAI", return_value=client):
            response = legacy_application.call_deepseek_raw(
                "Synthetic resume",
                "Synthetic job",
                deadline_monotonic=time.monotonic() + 60,
            )
        self.assertIsInstance(response, ProviderAnalysisResponse)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_initial_timeout_is_followed_by_one_successful_retry(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            httpx.ReadTimeout("synthetic timeout"),
            completion(),
        ]
        with patch("legacy_application.OpenAI", return_value=client):
            response = legacy_application.call_deepseek_raw(
                "Synthetic resume",
                "Synthetic job",
                deadline_monotonic=time.monotonic() + 60,
            )
        self.assertTrue(response.metadata["retry_started"])
        self.assertIn("read_timeout", response.metadata["timeout_categories"])
        self.assertEqual(response.metadata["primary_attempt_count"], 2)

    def test_initial_timeout_followed_by_retry_timeout_stays_safe(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            httpx.ReadTimeout("synthetic timeout"),
            httpx.ReadTimeout("synthetic timeout"),
        ]
        with patch("legacy_application.OpenAI", return_value=client):
            with self.assertRaises(ModelOutputError) as raised:
                legacy_application.call_deepseek_raw(
                    "Synthetic resume",
                    "Synthetic job",
                    deadline_monotonic=time.monotonic() + 60,
                )
        self.assertEqual(raised.exception.error_code, MODEL_PROVIDER_ERROR)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        self.assertIn("read_timeout", raised.exception.metadata["timeout_categories"])

    def test_format_repair_uses_the_same_absolute_deadline(self):
        client = MagicMock()
        with patch("legacy_application.OpenAI", return_value=client) as openai:
            with self.assertRaises(ModelOutputError) as raised:
                legacy_application.call_deepseek_repair(
                    "Synthetic invalid JSON",
                    deadline_monotonic=time.monotonic() - 0.01,
                )
        self.assertEqual(raised.exception.metadata["fallback_reason"], "provider_deadline_exhausted")
        openai.assert_not_called()

    def test_maximum_provider_call_count_remains_two_primary_attempts(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            httpx.ReadTimeout("synthetic timeout"),
            httpx.ReadTimeout("synthetic timeout"),
            completion(),
        ]
        with patch("legacy_application.OpenAI", return_value=client):
            with self.assertRaises(ModelOutputError):
                legacy_application.call_deepseek_raw(
                    "Synthetic resume",
                    "Synthetic job",
                    deadline_monotonic=time.monotonic() + 60,
                )
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_sdk_automatic_retries_are_zero_and_timeout_components_are_explicit(self):
        client = MagicMock()
        client.chat.completions.create.return_value = completion()
        with patch("legacy_application.OpenAI", return_value=client) as openai:
            legacy_application.call_deepseek_raw(
                "Synthetic resume",
                "Synthetic job",
                deadline_monotonic=time.monotonic() + 60,
            )
        kwargs = openai.call_args.kwargs
        self.assertEqual(kwargs["max_retries"], 0)
        self.assertIsInstance(kwargs["timeout"], httpx.Timeout)
        self.assertEqual(kwargs["timeout"].connect, 5.0)
        self.assertEqual(kwargs["timeout"].write, 10.0)
        self.assertEqual(kwargs["timeout"].pool, 5.0)

    def test_timeout_categories_are_stable_and_do_not_include_exception_text(self):
        self.assertEqual(
            legacy_application.provider_retry_reason(httpx.ConnectTimeout("private")),
            "connect_timeout",
        )
        self.assertEqual(
            legacy_application.provider_retry_reason(httpx.WriteTimeout("private")),
            "write_timeout",
        )
        self.assertEqual(
            legacy_application.provider_retry_reason(httpx.PoolTimeout("private")),
            "pool_timeout",
        )
        self.assertEqual(
            legacy_application.provider_retry_reason(httpx.ReadTimeout("private")),
            "read_timeout",
        )

    def test_provider_metadata_contains_only_bounded_observability(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = httpx.ReadTimeout("PRIVATE BODY")
        with patch("legacy_application.OpenAI", return_value=client):
            with self.assertRaises(ModelOutputError) as raised:
                legacy_application.call_deepseek_raw(
                    "Synthetic resume",
                    "Synthetic job",
                deadline_monotonic=time.monotonic() + 60,
                )
        rendered = json.dumps(raised.exception.metadata, sort_keys=True)
        self.assertNotIn("PRIVATE BODY", rendered)
        self.assertIn("timeout_categories", raised.exception.metadata)

    def test_fallback_is_deterministic_after_deadline_transition(self):
        result = local_fallback_result("Synthetic Python resume", "Synthetic FastAPI job", [])
        self.assertIsInstance(result.get("matched_skills"), list)
        self.assertTrue(deterministic_job_summary("Synthetic FastAPI job"))
        self.assertTrue(
            deterministic_match_reasons(
                {"skills_match": {"score": 0}},
                result.get("matched_skills") or [],
                result.get("missing_skills") or [],
            )
        )


class ProviderTransportDeadlineTest(unittest.TestCase):
    def _server(self, mode: str) -> tuple[ThreadingHTTPServer, threading.Thread]:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                if length:
                    self.rfile.read(length)
                if mode == "no_response":
                    time.sleep(0.2)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                if mode == "body_stall":
                    self.send_header("Content-Length", "3")
                    self.end_headers()
                    self.wfile.write(b"{")
                    self.wfile.flush()
                    time.sleep(0.2)
                    return
                if mode == "deadline_body_stall":
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{")
                    self.wfile.flush()
                    time.sleep(0.3)
                    self.wfile.write(b"}")
                    self.wfile.flush()
                    return
                if mode == "slow_stream":
                    self.send_header("Content-Length", "4")
                    self.end_headers()
                    for chunk in (b"{", b"\"", b"x", b"}"):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        time.sleep(0.06)
                    return
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def _request(self, mode: str, *, read_timeout: float, deadline_seconds: float) -> float:
        server, thread = self._server(mode)
        client = DeadlineHttpxClient(
            deadline_monotonic=time.monotonic() + deadline_seconds,
            timeout=httpx.Timeout(
                connect=read_timeout,
                read=read_timeout,
                write=read_timeout,
                pool=read_timeout,
            ),
            trust_env=False,
        )
        started = time.monotonic()
        elapsed = 0.0
        try:
            with self.assertRaises(httpx.TimeoutException):
                client.post(
                    f"http://127.0.0.1:{server.server_port}/chat/completions",
                    content=b"synthetic",
                )
            elapsed = time.monotonic() - started
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)
        return elapsed

    def test_server_accepts_connection_but_never_sends_response(self):
        self.assertLess(self._request("no_response", read_timeout=0.03, deadline_seconds=0.5), 0.15)

    def test_server_sends_headers_then_stalls_response_body(self):
        self.assertLess(self._request("body_stall", read_timeout=0.03, deadline_seconds=0.5), 0.15)

    def test_slow_stream_is_cut_off_by_absolute_body_deadline(self):
        self.assertLess(self._request("slow_stream", read_timeout=0.2, deadline_seconds=0.16), 0.3)

    def test_one_blocking_body_read_is_closed_at_absolute_deadline(self):
        self.assertLess(
            self._request("deadline_body_stall", read_timeout=0.5, deadline_seconds=0.08),
            0.2,
        )

    def test_active_provider_transport_can_be_closed_without_leaving_call_blocked(self):
        server, thread = self._server("deadline_body_stall")
        client = DeadlineHttpxClient(
            deadline_monotonic=time.monotonic() + 3,
            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1),
            trust_env=False,
        )
        errors: list[type[BaseException]] = []

        def request() -> None:
            try:
                client.post(
                    f"http://127.0.0.1:{server.server_port}/chat/completions",
                    content=b"synthetic",
                )
            except BaseException as exc:
                errors.append(type(exc))

        worker = threading.Thread(target=request, daemon=True)
        worker.start()
        time.sleep(0.05)
        client.close()
        worker.join(timeout=0.5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertTrue(errors)

    def test_tls_or_connect_stall_is_classified_without_external_network(self):
        self.assertEqual(
            legacy_application.provider_retry_reason(httpx.ConnectTimeout("synthetic TLS stall")),
            "connect_timeout",
        )

    def test_connection_attempt_that_never_completes_is_refused_when_budget_is_exhausted(self):
        deadline = ProviderDeadline(time.monotonic() + 0.01)
        self.assertIsNone(deadline.call_timeout(configured_timeout_seconds=60))

    def test_fallback_and_finalization_reserve_are_preserved_near_deadline(self):
        deadline = ProviderDeadline(time.monotonic() + 30.5)
        self.assertIsNone(deadline.call_timeout(configured_timeout_seconds=60, kind="repair"))
        self.assertEqual(deadline.remaining_bucket(), "31_60s")

    def test_client_disconnect_policy_is_safe_at_async_boundary(self):
        class Request:
            async def is_disconnected(self):
                return True

        result = __import__("asyncio").run(legacy_application._request_client_disconnected(Request()))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
