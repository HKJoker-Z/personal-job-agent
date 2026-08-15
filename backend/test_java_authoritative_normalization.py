import io
import json
import logging
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from docx import Document
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

import legacy_application
from analysis_contract import ProviderAnalysisResponse
from app.analyze.execution import LOCAL_NORMALIZATION_CONTRACT_VERSION
from app.analyze.normalization_client import (
    NormalizationClientError,
    NormalizedJobDescription,
    NormalizedSkill,
)
from app.analyze.normalization_runtime import select_effective_normalization
from logging_utils import JsonFormatter, RequestLoggingMiddleware


def java_settings():
    normalization = replace(
        legacy_application.settings.jd_normalization,
        mode="java",
        base_url="http://java-normalization:8091",
        api_key="T" * 32,
        shadow_sample_rate=0,
    )
    return replace(
        legacy_application.settings,
        jd_normalization=normalization,
    )


def normalized_result(text: str) -> NormalizedJobDescription:
    import hashlib

    return NormalizedJobDescription(
        normalized_text=text,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        normalization_policy_version="jd-normalization-v1",
        skill_dictionary_version="skills-v1",
        required_skills=(NormalizedSkill("python", "Python"),),
        preferred_skills=(),
        mentioned_skills=(),
        metadata={
            "title": None,
            "company": None,
            "location": None,
            "canonical_url": None,
        },
    )


def docx_bytes(text: str = "Python FastAPI engineer") -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def provider_response() -> ProviderAnalysisResponse:
    content = json.dumps(
        {
            "matched_skills": ["Python"],
            "missing_skills": ["PostgreSQL"],
            "unknown_skills": [],
            "concise_dimension_assessments": {
                "skills_match": {
                    "score": 70,
                    "assessment": "Python matches.",
                    "evidence_ids": ["resume"],
                }
            },
            "evidence_references": [
                {"skill": "Python", "evidence_ids": ["resume"]}
            ],
            "unsupported_claim_candidates": [],
            "concise_recommendations": ["Add verified PostgreSQL evidence."],
        }
    )
    return ProviderAnalysisResponse(
        content=content,
        metadata={"finish_reason": "stop", "response_length": len(content)},
    )


class JavaNormalizationSelectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_java_success_selects_scanned_text_and_versions(self):
        java_text = "JAVA NORMALIZED Python backend role"
        client = SimpleNamespace(
            normalize=AsyncMock(return_value=normalized_result(java_text))
        )
        result = await select_effective_normalization(
            client=client,
            config=java_settings().jd_normalization,
            local_sanitized_job_text="Local Python backend role",
            request_id="java-success-request",
            logger=logging.getLogger("test.java.success"),
        )

        self.assertEqual(result.text, java_text)
        self.assertEqual(result.source, "java")
        self.assertEqual(result.policy_version, "jd-normalization-v1")
        self.assertEqual(result.dictionary_version, "skills-v1")
        self.assertTrue(result.java_attempted)
        self.assertFalse(result.fallback)
        self.assertEqual(result.authoritative_second_scan_outcome, "accepted")
        client.normalize.assert_awaited_once_with(
            "Local Python backend role",
            "java-success-request",
        )
        binding = result.execution_binding("a" * 64)
        self.assertEqual(binding.normalization_source, "java")
        self.assertEqual(len(binding.fingerprint), 32)

    async def test_every_stable_client_failure_falls_back_once(self):
        outcomes = (
            "connect_timeout",
            "response_timeout",
            "total_timeout",
            "unavailable",
            "unauthorized",
            "client_error",
            "server_error",
            "oversized_response",
            "invalid_json",
            "invalid_schema",
            "hash_mismatch",
            "policy_mismatch",
            "dictionary_mismatch",
            "request_id_mismatch",
        )
        for outcome in outcomes:
            with self.subTest(outcome=outcome):
                client = SimpleNamespace(
                    normalize=AsyncMock(
                        side_effect=NormalizationClientError(outcome)
                    )
                )
                result = await select_effective_normalization(
                    client=client,
                    config=java_settings().jd_normalization,
                    local_sanitized_job_text="Local authoritative fallback",
                    request_id="java-fallback-request",
                    logger=logging.getLogger(f"test.java.{outcome}"),
                )
                self.assertEqual(result.text, "Local authoritative fallback")
                self.assertEqual(result.source, "fallback_local")
                self.assertEqual(
                    result.policy_version,
                    LOCAL_NORMALIZATION_CONTRACT_VERSION,
                )
                self.assertIsNone(result.dictionary_version)
                self.assertTrue(result.fallback)
                self.assertEqual(result.java_outcome, outcome)
                self.assertEqual(client.normalize.await_count, 1)

    async def test_authoritative_scan_rejection_falls_back_without_java_text(self):
        secret_java_text = (
            "Java role SYNTHETIC_API_KEY=abcdefghijklmnop1234567890"
        )
        client = SimpleNamespace(
            normalize=AsyncMock(return_value=normalized_result(secret_java_text))
        )
        result = await select_effective_normalization(
            client=client,
            config=java_settings().jd_normalization,
            local_sanitized_job_text="Local safe role",
            request_id="java-scan-rejection",
            logger=logging.getLogger("test.java.rejection"),
        )
        self.assertEqual(result.text, "Local safe role")
        self.assertEqual(result.source, "fallback_local")
        self.assertEqual(result.java_outcome, "second_scan_rejected")
        self.assertEqual(result.authoritative_second_scan_outcome, "rejected")
        self.assertEqual(result.accepted_security_scan, {})

    async def test_safe_observation_never_logs_text_hash_key_or_exception(self):
        local_text = "PRIVATE LOCAL JD"
        java_text = "PRIVATE JAVA JD"
        config = java_settings().jd_normalization
        client = SimpleNamespace(
            normalize=AsyncMock(return_value=normalized_result(java_text))
        )
        stream = io.StringIO()
        logger = logging.getLogger(f"test.java.logging.{id(self)}")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

        result = await select_effective_normalization(
            client=client,
            config=config,
            local_sanitized_job_text=local_text,
            request_id="java-safe-log",
            logger=logger,
        )
        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["message"],
            "jd_normalization_execution_observation",
        )
        self.assertEqual(payload["normalization_mode"], "java")
        self.assertEqual(payload["normalization_source"], "java")
        self.assertTrue(payload["java_attempted"])
        self.assertFalse(payload["fallback"])
        serialized = stream.getvalue()
        self.assertNotIn(local_text, serialized)
        self.assertNotIn(java_text, serialized)
        self.assertNotIn(normalized_result(java_text).content_hash, serialized)
        self.assertNotIn(config.api_key or "", serialized)
        self.assertNotIn(result.execution_binding("a" * 64).fingerprint.hex(), serialized)


class JavaNormalizationAnalyzeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.post("/api/analyze")(legacy_application.analyze)
        self.app.add_exception_handler(
            legacy_application.HTTPException,
            legacy_application.http_exception_handler,
        )
        self.app.add_exception_handler(
            RequestValidationError,
            legacy_application.validation_exception_handler,
        )
        self.app.add_middleware(
            RequestLoggingMiddleware,
            logger=logging.getLogger("personal-job-agent"),
        )
        self.client = TestClient(self.app)
        self.java_text = "JAVA EFFECTIVE Python PostgreSQL platform role"
        self.java_client = SimpleNamespace(
            normalize=AsyncMock(return_value=normalized_result(self.java_text))
        )
        self.app.state.jd_normalization_client = self.java_client

    def tearDown(self):
        self.client.close()
        self.app.state.jd_normalization_client = None

    def request(self, job_text: str = "Local Python role"):
        return self.client.post(
            "/api/analyze",
            files={
                "resume": (
                    "synthetic.docx",
                    docx_bytes(),
                    (
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                )
            },
            data={
                "job_text": job_text,
                "save_to_history": "false",
                "use_project_knowledge": "true",
            },
            headers={"X-Request-ID": "java-integration-request"},
        )

    def test_java_text_is_the_single_rag_prompt_provider_fallback_and_scoring_input(self):
        calls: dict[str, list[str]] = {
            "rag": [],
            "prompt": [],
            "provider": [],
            "scoring": [],
        }
        original_prompt = legacy_application.build_safe_analysis_prompt
        from app.analyze import result_refinement

        original_scoring = result_refinement.deterministic_scoring

        def retrieval_query(job_text, resume_text):
            calls["rag"].append(job_text)
            return "synthetic retrieval query"

        def prompt(*, resume_text, job_description, rag_chunks):
            calls["prompt"].append(job_description)
            return original_prompt(
                resume_text=resume_text,
                job_description=job_description,
                rag_chunks=rag_chunks,
            )

        def provider(resume_text, job_text, rag_chunks, **kwargs):
            calls["provider"].append(job_text)
            return provider_response()

        def scoring(result, resume_text, job_text, rag_chunks):
            calls["scoring"].append(job_text)
            return original_scoring(result, resume_text, job_text, rag_chunks)

        with patch.object(
            legacy_application,
            "settings",
            java_settings(),
        ), patch(
            "legacy_application.build_knowledge_retrieval_query",
            side_effect=retrieval_query,
        ), patch(
            "legacy_application.search_project_knowledge",
            return_value=([], "none"),
        ), patch(
            "legacy_application.build_safe_analysis_prompt",
            side_effect=prompt,
        ), patch(
            "legacy_application.call_deepseek_raw",
            side_effect=provider,
        ) as provider_call, patch(
            "app.analyze.result_refinement.deterministic_scoring",
            side_effect=scoring,
        ):
            response = self.request()

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.java_client.normalize.await_count, 1)
        sent_text, sent_request_id = self.java_client.normalize.await_args.args
        self.assertEqual(sent_text, "Local Python role")
        self.assertEqual(sent_request_id, "java-integration-request")
        self.assertEqual(calls["rag"], [self.java_text])
        self.assertEqual(calls["prompt"], [self.java_text])
        self.assertEqual(calls["provider"], [self.java_text])
        self.assertEqual(calls["scoring"], [self.java_text])
        self.assertEqual(provider_call.call_count, 1)
        self.assertNotIn("normalization_source", response.json())
        self.assertNotIn("execution_fingerprint", response.json())

    def test_blocked_first_scan_prevents_java_and_provider(self):
        blocked = "SYNTHETIC_API_KEY=abcdefghijklmnop1234567890"
        with patch.object(
            legacy_application,
            "settings",
            java_settings(),
        ), patch(
            "legacy_application.call_deepseek_raw"
        ) as provider:
            response = self.request(job_text=f"Python role {blocked}")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            response.json()["error"]["code"],
            "INPUT_SECURITY_BLOCKED",
        )
        self.assertNotIn(blocked, response.text)
        self.java_client.normalize.assert_not_awaited()
        provider.assert_not_called()

    def test_java_failure_uses_local_text_and_keeps_public_response_available(self):
        self.java_client.normalize.side_effect = NormalizationClientError(
            "total_timeout"
        )
        provider_jobs: list[str] = []

        def provider(resume_text, job_text, rag_chunks, **kwargs):
            provider_jobs.append(job_text)
            return provider_response()

        with patch.object(
            legacy_application,
            "settings",
            java_settings(),
        ), patch(
            "legacy_application.search_project_knowledge",
            return_value=([], "none"),
        ), patch(
            "legacy_application.call_deepseek_raw",
            side_effect=provider,
        ):
            response = self.request(job_text="Local fallback role")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.java_client.normalize.await_count, 1)
        self.assertEqual(provider_jobs, ["Local fallback role"])
        self.assertNotIn("total_timeout", response.text)

    def test_authoritative_second_scan_rejection_uses_local_provider_input(self):
        rejected_java_text = (
            "Java role SYNTHETIC_API_KEY=abcdefghijklmnop1234567890"
        )
        self.java_client.normalize.return_value = normalized_result(
            rejected_java_text
        )
        provider_jobs: list[str] = []

        def provider(resume_text, job_text, rag_chunks, **kwargs):
            provider_jobs.append(job_text)
            return provider_response()

        with patch.object(
            legacy_application,
            "settings",
            java_settings(),
        ), patch(
            "legacy_application.search_project_knowledge",
            return_value=([], "none"),
        ), patch(
            "legacy_application.call_deepseek_raw",
            side_effect=provider,
        ):
            response = self.request(job_text="Local second-scan fallback")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.java_client.normalize.await_count, 1)
        self.assertEqual(provider_jobs, ["Local second-scan fallback"])
        self.assertNotIn(rejected_java_text, response.text)


if __name__ == "__main__":
    unittest.main()
