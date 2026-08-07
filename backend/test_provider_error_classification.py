"""Deterministic tests for the HTTPX/SDK Provider error boundary."""

from __future__ import annotations

import ssl

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI
import unittest

from provider_deadline import (
    DeadlineHttpxClient,
    ProviderAttemptDeadlineExceeded,
    ProviderPhaseDeadlineExceeded,
)
from provider_errors import (
    classify_provider_exception,
    CONNECT_ERROR,
    CONNECT_TIMEOUT,
    LOCAL_PROTOCOL_ERROR,
    POOL_TIMEOUT,
    PROXY_ERROR,
    PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED,
    PROVIDER_PHASE_DEADLINE_EXHAUSTED,
    READ_ERROR,
    READ_TIMEOUT,
    REMOTE_PROTOCOL_ERROR,
    safe_exception_class_names,
    TLS_OR_CONNECT_ERROR,
    TRANSIENT_HTTP_429,
    TRANSIENT_HTTP_5XX,
    TRANSPORT_ERROR_OTHER,
    UNKNOWN_BOUNDED_PROVIDER_ERROR,
    WRITE_ERROR,
    WRITE_TIMEOUT,
)


class _StatusError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code


def _request() -> httpx.Request:
    return httpx.Request("GET", "https://api.deepseek.com")


class ProviderErrorClassificationTest(unittest.TestCase):
    def test_exact_httpx_component_categories(self):
        self.assertEqual(classify_provider_exception(httpx.ConnectTimeout("x")), CONNECT_TIMEOUT)
        self.assertEqual(classify_provider_exception(httpx.ReadTimeout("x")), READ_TIMEOUT)
        self.assertEqual(classify_provider_exception(httpx.WriteTimeout("x")), WRITE_TIMEOUT)
        self.assertEqual(classify_provider_exception(httpx.PoolTimeout("x")), POOL_TIMEOUT)

    def test_sdk_timeout_wrapper_uses_the_concrete_httpx_cause(self):
        cases = (
            (httpx.ConnectTimeout("x"), CONNECT_TIMEOUT),
            (httpx.ReadTimeout("x"), READ_TIMEOUT),
            (httpx.WriteTimeout("x"), WRITE_TIMEOUT),
            (httpx.PoolTimeout("x"), POOL_TIMEOUT),
        )
        for cause, expected in cases:
            with self.subTest(expected=expected):
                error = APITimeoutError(request=_request())
                error.__cause__ = cause
                self.assertEqual(classify_provider_exception(error), expected)

    def test_installed_sdk_wraps_mock_httpx_timeout_with_the_concrete_cause(self):
        def handler(_request: httpx.Request):
            raise httpx.ReadTimeout("synthetic read boundary")

        http_client = DeadlineHttpxClient(
            deadline_monotonic=10**10,
            timeout=httpx.Timeout(1),
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )
        sdk = OpenAI(
            api_key="synthetic-api-key",
            base_url="https://api.deepseek.com",
            max_retries=0,
            http_client=http_client,
        )
        try:
            with self.assertRaises(APITimeoutError) as raised:
                sdk.chat.completions.create(
                    model="deepseek-v4-pro",
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": "synthetic"}],
                )
            self.assertEqual(classify_provider_exception(raised.exception), READ_TIMEOUT)
        finally:
            sdk.close()

    def test_installed_sdk_connection_wrapper_requires_transport_cause(self):
        def handler(_request: httpx.Request):
            raise httpx.ConnectError("synthetic connection failure")

        http_client = DeadlineHttpxClient(
            deadline_monotonic=10**10,
            timeout=httpx.Timeout(1),
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )
        sdk = OpenAI(
            api_key="synthetic-api-key",
            base_url="https://api.deepseek.com",
            max_retries=0,
            http_client=http_client,
        )
        try:
            with self.assertRaises(APIConnectionError) as raised:
                sdk.chat.completions.create(
                    model="deepseek-v4-pro",
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": "synthetic"}],
                )
            self.assertEqual(classify_provider_exception(raised.exception), CONNECT_ERROR)
        finally:
            sdk.close()

    def test_installed_sdk_protocol_wrapper_preserves_protocol_cause(self):
        def handler(_request: httpx.Request):
            raise httpx.RemoteProtocolError("synthetic protocol boundary")

        http_client = httpx.Client(
            trust_env=False,
            transport=httpx.MockTransport(handler),
        )
        sdk = OpenAI(
            api_key="synthetic-api-key",
            base_url="https://api.deepseek.com",
            max_retries=0,
            http_client=http_client,
        )
        try:
            with self.assertRaises(APIConnectionError) as raised:
                sdk.chat.completions.create(
                    model="deepseek-v4-pro",
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": "synthetic"}],
                )
            self.assertEqual(classify_provider_exception(raised.exception), REMOTE_PROTOCOL_ERROR)
        finally:
            sdk.close()

    def test_sdk_connection_wrapper_is_not_assumed_to_be_connect_timeout(self):
        connection = APIConnectionError(request=_request())
        self.assertEqual(classify_provider_exception(connection), UNKNOWN_BOUNDED_PROVIDER_ERROR)
        wrapped = APIConnectionError(request=_request())
        wrapped.__cause__ = httpx.ConnectError("synthetic")
        self.assertEqual(classify_provider_exception(wrapped), CONNECT_ERROR)

    def test_exact_concrete_transport_categories(self):
        cases = (
            (httpx.ConnectError("private"), CONNECT_ERROR),
            (httpx.ReadError("private"), READ_ERROR),
            (httpx.WriteError("private"), WRITE_ERROR),
            (httpx.RemoteProtocolError("private"), REMOTE_PROTOCOL_ERROR),
            (httpx.LocalProtocolError("private"), LOCAL_PROTOCOL_ERROR),
            (httpx.ProxyError("private"), PROXY_ERROR),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_provider_exception(error), expected)

    def test_tls_cause_is_bounded_without_exposing_exception_text(self):
        error = APIConnectionError(request=_request())
        error.__cause__ = OSError("private")
        error.__cause__.__cause__ = ssl.SSLError("private")
        self.assertEqual(classify_provider_exception(error), TLS_OR_CONNECT_ERROR)

    def test_generic_transport_is_bounded_as_transport_error_other(self):
        self.assertEqual(classify_provider_exception(ConnectionError("private")), TRANSPORT_ERROR_OTHER)

    def test_allowlisted_exception_class_metadata_has_no_exception_text(self):
        error = APIConnectionError(request=_request())
        error.__cause__ = httpx.RemoteProtocolError("PRIVATE BODY OR URL")
        self.assertEqual(
            safe_exception_class_names(error),
            ["APIConnectionError", "RemoteProtocolError"],
        )

    def test_deadline_categories_are_distinct_from_read_timeout(self):
        request = _request()
        self.assertEqual(
            classify_provider_exception(ProviderAttemptDeadlineExceeded("x", request=request)),
            PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED,
        )
        self.assertEqual(
            classify_provider_exception(ProviderPhaseDeadlineExceeded("x", request=request)),
            PROVIDER_PHASE_DEADLINE_EXHAUSTED,
        )

    def test_explicit_http_status_categories_are_bounded(self):
        self.assertEqual(classify_provider_exception(_StatusError(429)), TRANSIENT_HTTP_429)
        self.assertEqual(classify_provider_exception(_StatusError(503)), TRANSIENT_HTTP_5XX)

    def test_generic_timeout_and_exception_text_are_not_component_categories(self):
        self.assertEqual(classify_provider_exception(TimeoutError("private")), UNKNOWN_BOUNDED_PROVIDER_ERROR)
        self.assertEqual(classify_provider_exception(Exception("private")), UNKNOWN_BOUNDED_PROVIDER_ERROR)


if __name__ == "__main__":
    unittest.main()
