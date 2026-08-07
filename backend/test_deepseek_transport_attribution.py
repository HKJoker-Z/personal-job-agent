"""Deterministic local tests for authenticated transport attribution seams."""

from __future__ import annotations

import threading
import time
import socket
import unittest

import httpcore
import httpx

from candidates.deepseek_transport_attribution import (
    _body_bucket,
    _content_shape,
    _http_completion_shape,
    _request_headers,
    _request_body,
)
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
    TLS_OR_CONNECT_ERROR,
    TRANSPORT_ERROR_OTHER,
    WRITE_ERROR,
    WRITE_TIMEOUT,
)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.deepseek.com/chat/completions")


class _BlockingStream(httpx.SyncByteStream):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.released = threading.Event()
        self.closed = threading.Event()

    def __iter__(self):
        self.started.set()
        self.released.wait(2.0)
        yield b"{}"

    def close(self) -> None:
        self.closed.set()
        self.released.set()


def _run_one_shot_http_server(payload: bytes) -> tuple[int, threading.Thread]:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen(1)
    port = int(server_socket.getsockname()[1])

    def serve() -> None:
        try:
            connection, _address = server_socket.accept()
            try:
                connection.recv(4096)
                if payload:
                    connection.sendall(payload)
            finally:
                connection.close()
        finally:
            server_socket.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return port, thread


class DeepSeekTransportAttributionTest(unittest.TestCase):
    def test_httpx_and_httpcore_concrete_categories_are_exact(self):
        cases = (
            (httpx.ConnectError("private"), CONNECT_ERROR),
            (httpcore.ConnectError("private"), CONNECT_ERROR),
            (httpx.ConnectTimeout("private"), CONNECT_TIMEOUT),
            (httpx.ReadError("private"), READ_ERROR),
            (httpcore.ReadError("private"), READ_ERROR),
            (httpx.ReadTimeout("private"), READ_TIMEOUT),
            (httpx.WriteError("private"), WRITE_ERROR),
            (httpcore.WriteError("private"), WRITE_ERROR),
            (httpx.WriteTimeout("private"), WRITE_TIMEOUT),
            (httpx.PoolTimeout("private"), POOL_TIMEOUT),
            (httpx.RemoteProtocolError("private"), REMOTE_PROTOCOL_ERROR),
            (httpcore.RemoteProtocolError("private"), REMOTE_PROTOCOL_ERROR),
            (httpx.LocalProtocolError("private"), LOCAL_PROTOCOL_ERROR),
            (httpcore.LocalProtocolError("private"), LOCAL_PROTOCOL_ERROR),
            (httpx.ProxyError("private"), PROXY_ERROR),
            (httpcore.ProxyError("private"), PROXY_ERROR),
        )
        for error, expected in cases:
            with self.subTest(expected=expected, actual=type(error).__name__):
                self.assertEqual(classify_provider_exception(error), expected)

    def test_mock_transport_wraps_remote_boundaries_without_using_text(self):
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
                client = httpx.Client(
                    trust_env=False,
                    transport=httpx.MockTransport(lambda _request, error=error: (_ for _ in ()).throw(error)),
                )
                try:
                    with self.assertRaises(type(error)) as raised:
                        client.post("https://api.deepseek.com/chat/completions", content=b"{}")
                finally:
                    client.close()
                self.assertEqual(classify_provider_exception(raised.exception), expected)

    def test_local_server_boundaries_are_classified_at_the_httpx_boundary(self):
        cases = (
            (b"", {REMOTE_PROTOCOL_ERROR, READ_ERROR}),
            (b"HTTP/1.1 200 OK\r\nContent-Type: application/json", {READ_ERROR, REMOTE_PROTOCOL_ERROR}),
            (b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}", {READ_ERROR, REMOTE_PROTOCOL_ERROR}),
            (b"not an HTTP response\r\n\r\n", {REMOTE_PROTOCOL_ERROR}),
            (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\n{}", {READ_ERROR, REMOTE_PROTOCOL_ERROR}),
        )
        for payload, expected in cases:
            with self.subTest(expected=sorted(expected)):
                port, thread = _run_one_shot_http_server(payload)
                try:
                    with httpx.Client(
                        trust_env=False,
                        timeout=httpx.Timeout(connect=1, read=0.2, write=1, pool=1),
                    ) as client:
                        with self.assertRaises(httpx.TransportError) as raised:
                            client.post(f"http://127.0.0.1:{port}/", content=b"{}")
                finally:
                    thread.join(timeout=1.0)
                self.assertIn(classify_provider_exception(raised.exception), expected)

    def test_local_plaintext_peer_during_tls_is_not_mislabeled_as_tls_when_httpx_hides_it(self):
        port, thread = _run_one_shot_http_server(b"not TLS")
        try:
            with httpx.Client(
                trust_env=False,
                verify=True,
                timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1),
            ) as client:
                with self.assertRaises(httpx.ConnectError) as raised:
                    client.get(f"https://127.0.0.1:{port}/")
        finally:
            thread.join(timeout=1.0)
        self.assertEqual(classify_provider_exception(raised.exception), CONNECT_ERROR)

    def test_timeout_and_deadline_categories_remain_separate(self):
        request = _request()
        cases = (
            (httpx.ConnectTimeout("private"), CONNECT_TIMEOUT),
            (httpx.ReadTimeout("private"), READ_TIMEOUT),
            (httpx.WriteTimeout("private"), WRITE_TIMEOUT),
            (httpx.PoolTimeout("private"), POOL_TIMEOUT),
            (ProviderAttemptDeadlineExceeded("private", request=request), PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED),
            (ProviderPhaseDeadlineExceeded("private", request=request), PROVIDER_PHASE_DEADLINE_EXHAUSTED),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_provider_exception(error), expected)

    def test_generic_socket_reset_has_bounded_other_category(self):
        self.assertEqual(classify_provider_exception(ConnectionResetError("private")), TRANSPORT_ERROR_OTHER)

    def test_deadline_stream_closes_the_underlying_response_at_attempt_deadline(self):
        stream = _BlockingStream()
        client = DeadlineHttpxClient(
            deadline_monotonic=time.monotonic() + 2.0,
            attempt_deadline_monotonic=time.monotonic() + 0.1,
            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1),
            trust_env=False,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream, request=request)
            ),
        )
        try:
            with self.assertRaises(ProviderAttemptDeadlineExceeded):
                client.post("https://api.deepseek.com/chat/completions", content=b"{}")
            self.assertTrue(stream.started.is_set())
            self.assertTrue(stream.closed.is_set())
        finally:
            client.close()

    def test_client_close_releases_an_active_response_without_a_sleep_race(self):
        stream = _BlockingStream()
        client = DeadlineHttpxClient(
            deadline_monotonic=time.monotonic() + 5.0,
            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1),
            trust_env=False,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream, request=request)
            ),
        )
        request = client.build_request(
            "POST",
            "https://api.deepseek.com/chat/completions",
            content=b"{}",
        )
        response = client.send(request, stream=True)
        errors: list[BaseException] = []

        def read_response() -> None:
            try:
                response.read()
            except BaseException as exc:
                errors.append(exc)

        reader = threading.Thread(target=read_response)
        reader.start()
        self.assertTrue(stream.started.wait(1.0))
        response.close()
        reader.join(timeout=1.0)
        try:
            self.assertFalse(reader.is_alive())
            self.assertTrue(stream.closed.is_set())
            self.assertFalse(errors)
        finally:
            client.close()

    def test_normal_response_is_consumed_before_client_cleanup(self):
        stream = _BlockingStream()
        stream.released.set()
        client = DeadlineHttpxClient(
            deadline_monotonic=time.monotonic() + 5.0,
            timeout=httpx.Timeout(connect=1, read=1, write=1, pool=1),
            trust_env=False,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=stream, request=request)
            ),
        )
        try:
            response = client.post("https://api.deepseek.com/chat/completions", content=b"{}")
            self.assertEqual(response.content, b"{}")
            self.assertTrue(stream.closed.is_set())
        finally:
            client.close()

    def test_bounded_response_shape_and_size_helpers_never_retain_content(self):
        self.assertEqual(_body_bucket(0), "empty")
        self.assertEqual(_body_bucket(128), "small")
        self.assertEqual(_body_bucket(257), "medium")
        self.assertEqual(_body_bucket(4097), "large")
        valid_content = '{"ok":true}'
        self.assertEqual(_content_shape(valid_content), (True, len(valid_content)))
        self.assertEqual(_content_shape("not-json"), (False, len("not-json")))
        valid_response = b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'
        self.assertEqual(_http_completion_shape(valid_response), (True, len(valid_response)))

    def test_wire_body_matches_sdk_extra_body_expansion(self):
        settings = type(
            "Settings",
            (),
            {"deepseek_model": "deepseek-v4-pro", "deepseek_thinking_enabled": False},
        )()
        body = _request_body(settings)
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertNotIn("extra_body", body)

    def test_plain_httpx_request_has_bounded_auth_headers(self):
        headers = _request_headers("synthetic-key")
        self.assertEqual(headers["Authorization"], "Bearer synthetic-key")
        self.assertEqual(headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
