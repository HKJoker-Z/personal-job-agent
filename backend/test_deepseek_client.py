"""Client-scoped DeepSeek transport and configuration tests."""

from __future__ import annotations

import io
import logging
import os
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from deepseek_client import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_NETWORK_MODE_DIRECT,
    DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
    build_deepseek_client,
    build_deepseek_http_client,
)
from provider_deadline import ProviderDeadline


class DeepSeekClientTest(unittest.TestCase):
    def runtime(self, mode: str) -> SimpleNamespace:
        return SimpleNamespace(
            deepseek_api_key="synthetic-api-key",
            deepseek_network_mode=mode,
            request_timeout_seconds=60,
        )

    def deadline(self, seconds: float = 100.0) -> ProviderDeadline:
        return ProviderDeadline(
            absolute_deadline=time.monotonic() + seconds,
            finalization_reserve_seconds=0,
            retry_reserve_seconds=0,
            repair_reserve_seconds=0,
        )

    def test_direct_mode_uses_trust_env_false_and_default_tls_verification(self):
        captured: dict[str, object] = {}

        def fake_client(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(close=lambda: None)

        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:1",
                "HTTPS_PROXY": "http://127.0.0.1:1",
                "ALL_PROXY": "http://127.0.0.1:1",
                "NO_PROXY": "",
                "http_proxy": "http://127.0.0.1:1",
                "https_proxy": "http://127.0.0.1:1",
                "all_proxy": "http://127.0.0.1:1",
                "no_proxy": "",
            },
            clear=False,
        ):
            client, http_client, timeout = build_deepseek_client(
                self.runtime(DEEPSEEK_NETWORK_MODE_DIRECT),
                deadline=self.deadline(),
                kind="primary",
                client_class=fake_client,
            )
        try:
            self.assertIsNotNone(client)
            self.assertFalse(http_client._trust_env)
            self.assertIsInstance(timeout.timeout, httpx.Timeout)
            self.assertEqual(captured["base_url"], DEEPSEEK_BASE_URL)
            self.assertEqual(captured["max_retries"], 0)
            self.assertEqual(captured["timeout"].connect, 5.0)
            self.assertIs(captured["http_client"], http_client)
            self.assertEqual(http_client._transport._pool._ssl_context.verify_mode, 2)
        finally:
            http_client.close()

    def test_environment_proxy_mode_uses_environment_aware_transport(self):
        with patch.dict(
            os.environ,
            {"ALL_PROXY": "", "all_proxy": "", "HTTPS_PROXY": "http://127.0.0.1:1"},
            clear=False,
        ):
            _, http_client, _timeout = build_deepseek_client(
                self.runtime(DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY),
                deadline=self.deadline(),
                kind="primary",
                client_class=lambda **_kwargs: SimpleNamespace(close=lambda: None),
            )
            try:
                self.assertTrue(http_client._trust_env)
            finally:
                http_client.close()

    def test_direct_mode_ignores_all_proxy_spellings_without_mutating_environment(self):
        proxy_values = {
            "HTTP_PROXY": "http://127.0.0.1:1",
            "HTTPS_PROXY": "http://127.0.0.1:1",
            "ALL_PROXY": "http://127.0.0.1:1",
            "NO_PROXY": "",
            "http_proxy": "http://127.0.0.1:1",
            "https_proxy": "http://127.0.0.1:1",
            "all_proxy": "http://127.0.0.1:1",
            "no_proxy": "",
        }
        with patch.dict(os.environ, proxy_values, clear=False):
            before = dict(os.environ)
            client = build_deepseek_http_client(
                network_mode=DEEPSEEK_NETWORK_MODE_DIRECT,
                deadline_monotonic=10**10,
                timeout=httpx.Timeout(1),
            )
            try:
                origin = httpx.URL(DEEPSEEK_BASE_URL)
                self.assertFalse(client._trust_env)
                self.assertIs(client._transport_for_url(origin), client._transport)
            finally:
                client.close()
            self.assertEqual(dict(os.environ), before)

    def test_environment_proxy_and_unrelated_client_still_select_environment_transport(self):
        proxy_values = {
            "HTTP_PROXY": "http://127.0.0.1:1",
            "HTTPS_PROXY": "http://127.0.0.1:1",
            "ALL_PROXY": "",
            "NO_PROXY": "",
            "http_proxy": "http://127.0.0.1:1",
            "https_proxy": "http://127.0.0.1:1",
            "all_proxy": "",
            "no_proxy": "",
        }
        with patch.dict(os.environ, proxy_values, clear=False):
            deepseek = build_deepseek_http_client(
                network_mode=DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
                deadline_monotonic=10**10,
                timeout=httpx.Timeout(1),
            )
            unrelated = httpx.Client(trust_env=True)
            try:
                origin = httpx.URL(DEEPSEEK_BASE_URL)
                self.assertIsNot(deepseek._transport_for_url(origin), deepseek._transport)
                self.assertIsNot(unrelated._transport_for_url(origin), unrelated._transport)
            finally:
                deepseek.close()
                unrelated.close()

    def test_effective_connect_timeout_is_capped_by_same_deadline_budget(self):
        _, http_client, timeout = build_deepseek_client(
            self.runtime(DEEPSEEK_NETWORK_MODE_DIRECT),
            deadline=ProviderDeadline(
                absolute_deadline=time.monotonic() + 8.0,
                finalization_reserve_seconds=0,
                retry_reserve_seconds=0,
                repair_reserve_seconds=0,
            ),
            kind="primary",
            client_class=lambda **_kwargs: SimpleNamespace(close=lambda: None),
        )
        try:
            self.assertEqual(timeout.budget_seconds, 8.0)
            self.assertEqual(timeout.timeout.connect, 5.0)
        finally:
            http_client.close()

    def test_builder_and_client_logs_never_contain_secret_or_proxy_values(self):
        secret = "synthetic-api-key-do-not-log"
        proxy = "http://user:password@proxy.invalid:3128"
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            with patch.dict(os.environ, {"HTTPS_PROXY": proxy}, clear=False):
                runtime = self.runtime(DEEPSEEK_NETWORK_MODE_DIRECT)
                runtime.deepseek_api_key = secret
                _client, http_client, _timeout = build_deepseek_client(
                    runtime,
                    deadline=self.deadline(),
                    kind="primary",
                    client_class=lambda **_kwargs: SimpleNamespace(close=lambda: None),
                )
                http_client.close()
        finally:
            logger.removeHandler(handler)
        rendered = stream.getvalue()
        self.assertNotIn(secret, rendered)
        self.assertNotIn(proxy, rendered)


if __name__ == "__main__":
    unittest.main()
