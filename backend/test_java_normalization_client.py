import asyncio
import hashlib
import json
import logging
import os
import unittest
from unittest.mock import patch

import httpx

from app.analyze.normalization_client import (
    JavaNormalizationClient,
    NormalizationClientError,
)
from config import JavaNormalizationConfig


REQUEST_ID = "phase-2-client-request"
API_KEY = "TEST_ONLY_NORMALIZATION_KEY_32_BYTES"


def client_config(**updates) -> JavaNormalizationConfig:
    values = {
        "mode": "shadow",
        "base_url": "http://java-normalization:8091",
        "api_key": API_KEY,
        "connect_timeout_ms": 200,
        "response_timeout_ms": 600,
        "total_timeout_ms": 800,
        "max_response_bytes": 256 * 1024,
        "expected_policy_version": "jd-normalization-v1",
        "expected_dictionary_version": "skills-v1",
        "shadow_sample_rate": 1.0,
        "pool_max_connections": 10,
        "pool_max_keepalive_connections": 5,
    }
    values.update(updates)
    return JavaNormalizationConfig(**values)


def valid_payload(text: str = "Required:\n- Python") -> dict:
    return {
        "normalized_text": text,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "normalization_policy_version": "jd-normalization-v1",
        "skill_dictionary_version": "skills-v1",
        "required_skills": [{"id": "python", "name": "Python"}],
        "preferred_skills": [],
        "mentioned_skills": [],
        "metadata": {
            "title": None,
            "company": None,
            "location": None,
            "canonical_url": None,
        },
    }


def json_response(
    request: httpx.Request,
    payload: object | None = None,
    *,
    status: int = 200,
    request_id: str | None = REQUEST_ID,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response_headers = {"Content-Type": "application/json"}
    if request_id is not None:
        response_headers["X-Request-ID"] = request_id
    response_headers.update(headers or {})
    return httpx.Response(
        status,
        headers=response_headers,
        content=json.dumps(payload if payload is not None else valid_payload()).encode(),
        request=request,
    )


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class JavaNormalizationClientTest(unittest.IsolatedAsyncioTestCase):
    async def call_with_handler(self, handler, *, config=None):
        client = JavaNormalizationClient(
            config or client_config(),
            transport=httpx.MockTransport(handler),
        )
        try:
            return await client.normalize("Synthetic bounded JD", REQUEST_ID)
        finally:
            await client.aclose()

    async def assert_outcome(self, outcome: str, handler, *, config=None):
        with self.assertRaises(NormalizationClientError) as raised:
            await self.call_with_handler(handler, config=config)
        self.assertEqual(raised.exception.outcome, outcome)
        self.assertEqual(str(raised.exception), outcome)

    async def test_success_sends_only_internal_contract_and_request_id(self):
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                request.url.path,
                "/api/v1/job-descriptions/normalize",
            )
            self.assertEqual(request.headers["Authorization"], f"Bearer {API_KEY}")
            self.assertEqual(request.headers["X-Request-ID"], REQUEST_ID)
            self.assertEqual(request.headers["Content-Type"], "application/json")
            self.assertEqual(
                json.loads(request.content),
                {"raw_text": "Synthetic bounded JD"},
            )
            for absent in ("Cookie", "Origin", "X-CSRF-Token"):
                self.assertNotIn(absent, request.headers)
            return json_response(request)

        result = await self.call_with_handler(handler)
        self.assertEqual(result.normalized_text, "Required:\n- Python")
        self.assertEqual(result.required_skills[0].id, "python")
        self.assertEqual(len(requests), 1)

    async def test_authorization_is_not_logged(self):
        private_body = "PRIVATE_REMOTE_BODY_" + API_KEY

        async def handler(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": REQUEST_ID,
                },
                content=private_body,
                request=request,
            )

        with self.assertLogs(level=logging.CRITICAL) as captured:
            logging.getLogger().critical("bounded-test-marker")
            await self.assert_outcome("invalid_json", handler)
        joined = "\n".join(captured.output)
        self.assertNotIn(API_KEY, joined)
        self.assertNotIn(private_body, joined)

    async def test_client_does_not_generate_request_ids(self):
        calls = 0

        async def handler(request: httpx.Request):
            nonlocal calls
            calls += 1
            return json_response(request)

        client = JavaNormalizationClient(
            client_config(),
            transport=httpx.MockTransport(handler),
        )
        try:
            with self.assertRaises(NormalizationClientError) as raised:
                await client.normalize("Synthetic JD", "invalid request id")
        finally:
            await client.aclose()
        self.assertEqual(raised.exception.outcome, "request_id_mismatch")
        self.assertEqual(calls, 0)

    async def test_outbound_text_and_encoded_body_are_bounded_before_transport(self):
        calls = 0

        async def handler(request: httpx.Request):
            nonlocal calls
            calls += 1
            return json_response(request)

        client = JavaNormalizationClient(
            client_config(),
            transport=httpx.MockTransport(handler),
        )
        try:
            for raw_text in ("", "X" * 100_001, "\x01" * 100_000):
                with self.assertRaises(NormalizationClientError) as raised:
                    await client.normalize(raw_text, REQUEST_ID)
                self.assertEqual(raised.exception.outcome, "client_error")
        finally:
            await client.aclose()
        self.assertEqual(calls, 0)

    async def test_one_attempt_and_redirects_disabled(self):
        calls = 0

        async def handler(request: httpx.Request):
            nonlocal calls
            calls += 1
            return httpx.Response(
                307,
                headers={"Location": "http://other-service/private"},
                request=request,
            )

        await self.assert_outcome("client_error", handler)
        self.assertEqual(calls, 1)

    async def test_proxy_inheritance_is_disabled(self):
        async def handler(request: httpx.Request):
            return json_response(request)

        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://proxy.invalid:3128",
                "HTTPS_PROXY": "http://proxy.invalid:3128",
            },
        ):
            client = JavaNormalizationClient(
                client_config(),
                transport=httpx.MockTransport(handler),
            )
        try:
            self.assertFalse(client._client._trust_env)
            await client.normalize("Synthetic JD", REQUEST_ID)
        finally:
            await client.aclose()

    async def test_response_cookies_are_never_forwarded(self):
        calls = 0

        async def handler(request: httpx.Request):
            nonlocal calls
            calls += 1
            self.assertNotIn("Cookie", request.headers)
            return json_response(
                request,
                headers={"Set-Cookie": "unwanted=server-state; Path=/"},
            )

        client = JavaNormalizationClient(
            client_config(),
            transport=httpx.MockTransport(handler),
        )
        try:
            await client.normalize("First synthetic JD", REQUEST_ID)
            await client.normalize("Second synthetic JD", REQUEST_ID)
        finally:
            await client.aclose()
        self.assertEqual(calls, 2)

    async def test_transport_timeouts_and_connection_failure_are_stable(self):
        cases = (
            (
                "connect_timeout",
                httpx.ConnectTimeout("private", request=httpx.Request("POST", "http://x")),
            ),
            (
                "response_timeout",
                httpx.ReadTimeout("private", request=httpx.Request("POST", "http://x")),
            ),
            (
                "response_timeout",
                httpx.WriteTimeout("private", request=httpx.Request("POST", "http://x")),
            ),
            (
                "unavailable",
                httpx.ConnectError("private", request=httpx.Request("POST", "http://x")),
            ),
        )
        for expected, exception in cases:
            async def handler(_request: httpx.Request, failure=exception):
                raise failure

            with self.subTest(expected=expected, exception=type(exception).__name__):
                await self.assert_outcome(expected, handler)

    async def test_total_deadline_includes_the_request(self):
        async def handler(request: httpx.Request):
            await asyncio.sleep(0.05)
            return json_response(request)

        await self.assert_outcome(
            "total_timeout",
            handler,
            config=client_config(total_timeout_ms=5),
        )

    async def test_http_failures_map_without_reading_or_retrying(self):
        expected = {
            400: "client_error",
            401: "unauthorized",
            413: "client_error",
            422: "client_error",
            429: "client_error",
            500: "server_error",
            503: "server_error",
        }
        for status, outcome in expected.items():
            calls = 0

            async def handler(request: httpx.Request, code=status):
                nonlocal calls
                calls += 1
                return httpx.Response(
                    code,
                    content=b"PRIVATE_RESPONSE_BODY",
                    request=request,
                )

            with self.subTest(status=status):
                await self.assert_outcome(outcome, handler)
                self.assertEqual(calls, 1)

    async def test_json_and_content_type_are_strict(self):
        async def malformed(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": REQUEST_ID,
                },
                content=b"{not-json",
                request=request,
            )

        async def wrong_type(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/html",
                    "X-Request-ID": REQUEST_ID,
                },
                content=b"{}",
                request=request,
            )

        async def duplicate_field(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": REQUEST_ID,
                },
                content=b'{"normalized_text":"one","normalized_text":"two"}',
                request=request,
            )

        await self.assert_outcome("invalid_json", malformed)
        await self.assert_outcome("invalid_schema", wrong_type)
        await self.assert_outcome("invalid_json", duplicate_field)

    async def test_declared_and_streamed_oversized_bodies_are_stopped(self):
        maximum = 1024

        async def declared(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(maximum + 1),
                    "X-Request-ID": REQUEST_ID,
                },
                stream=ChunkStream(b"{}"),
                request=request,
            )

        async def streamed(request: httpx.Request):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": REQUEST_ID,
                },
                stream=ChunkStream(b"X" * 700, b"Y" * 400),
                request=request,
            )

        config = client_config(max_response_bytes=maximum)
        await self.assert_outcome("oversized_response", declared, config=config)
        await self.assert_outcome("oversized_response", streamed, config=config)

    async def test_required_fields_and_bounds_are_strict(self):
        cases = []
        missing = valid_payload()
        missing.pop("metadata")
        cases.append(missing)
        unexpected = valid_payload()
        unexpected["unbounded_extra"] = {"private": "value"}
        cases.append(unexpected)
        empty = valid_payload("")
        cases.append(empty)
        overflow = valid_payload("X" * 100_001)
        cases.append(overflow)
        long_name = valid_payload()
        long_name["required_skills"][0]["name"] = "X" * 201
        cases.append(long_name)
        extra_skill_field = valid_payload()
        extra_skill_field["required_skills"][0]["extra"] = "value"
        cases.append(extra_skill_field)
        bad_metadata = valid_payload()
        bad_metadata["metadata"]["extra"] = "value"
        cases.append(bad_metadata)

        for index, payload in enumerate(cases):
            async def handler(request: httpx.Request, value=payload):
                return json_response(request, value)

            with self.subTest(index=index):
                await self.assert_outcome("invalid_schema", handler)

    async def test_hash_policy_and_dictionary_mismatches_are_distinct(self):
        invalid_hash = valid_payload()
        invalid_hash["content_hash"] = "not-a-hash"
        wrong_hash = valid_payload()
        wrong_hash["content_hash"] = "0" * 64
        wrong_policy = valid_payload()
        wrong_policy["normalization_policy_version"] = "future-policy"
        wrong_dictionary = valid_payload()
        wrong_dictionary["skill_dictionary_version"] = "future-dictionary"
        for outcome, payload in (
            ("hash_mismatch", invalid_hash),
            ("hash_mismatch", wrong_hash),
            ("policy_mismatch", wrong_policy),
            ("dictionary_mismatch", wrong_dictionary),
        ):
            async def handler(request: httpx.Request, value=payload):
                return json_response(request, value)

            with self.subTest(outcome=outcome):
                await self.assert_outcome(outcome, handler)

    async def test_skill_limit_duplicates_and_precedence_conflicts_are_rejected(self):
        too_many = valid_payload()
        too_many["required_skills"] = [
            {"id": f"skill-{index}", "name": f"Skill {index}"}
            for index in range(257)
        ]
        duplicate_within = valid_payload()
        duplicate_within["required_skills"].append(
            {"id": "python", "name": "Python duplicate"}
        )
        category_conflict = valid_payload()
        category_conflict["preferred_skills"] = [
            {"id": "python", "name": "Python"}
        ]
        for payload in (too_many, duplicate_within, category_conflict):
            async def handler(request: httpx.Request, value=payload):
                return json_response(request, value)

            await self.assert_outcome("invalid_schema", handler)

    async def test_response_request_id_must_be_present_valid_and_equal(self):
        for response_id in (None, "different-request", "invalid request/id"):
            async def handler(request: httpx.Request, value=response_id):
                return json_response(request, request_id=value)

            with self.subTest(response_id=response_id):
                await self.assert_outcome("request_id_mismatch", handler)

    async def test_shutdown_closes_connection_pool(self):
        async def handler(request: httpx.Request):
            return json_response(request)

        client = JavaNormalizationClient(
            client_config(),
            transport=httpx.MockTransport(handler),
        )
        self.assertFalse(client.is_closed)
        await client.normalize("Synthetic JD", REQUEST_ID)
        await client.aclose()
        self.assertTrue(client.is_closed)


if __name__ == "__main__":
    unittest.main()
