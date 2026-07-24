import io
import json
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from analysis_contract import (
    MODEL_OUTPUT_INVALID_JSON,
    ModelOutputError,
    ProviderAnalysisResponse,
    parse_model_json,
    parse_model_json_result,
    validate_compact_analysis,
)
from database import deserialize_analysis_metadata, serialize_analysis_metadata
from legacy_application import (
    app,
    enforce_analysis_grounding,
    local_fallback_result,
    model_response_to_result,
    validate_model_evidence_references,
)
from security_utils import INTERNAL_SECURITY_MARKER


def docx_bytes(text="Python FastAPI engineer"):
    document = Document()
    document.add_paragraph(text)
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def complete_payload(**updates):
    value = {
        "matched_skills": ["Python"],
        "missing_skills": ["Kubernetes"],
        "unknown_skills": [],
        "concise_dimension_assessments": {
            "skills_match": {"score": 70, "assessment": "Python matches.", "evidence_ids": ["resume"]}
        },
        "evidence_references": [{"skill": "Python", "evidence_ids": ["resume"]}],
        "unsupported_claim_candidates": [],
        "concise_recommendations": ["Add verified Kubernetes evidence."],
    }
    value.update(updates)
    return value


class V203AnalysisContractTest(unittest.TestCase):
    def test_standard_json(self):
        value = validate_compact_analysis(parse_model_json(json.dumps(complete_payload())))
        self.assertEqual(value.matched_skills, ["Python"])

    def test_json_code_fence(self):
        parsed = parse_model_json_result("```json\n" + json.dumps(complete_payload()) + "\n```")
        self.assertTrue(parsed.normalized)
        self.assertEqual(parsed.data["matched_skills"], ["Python"])

    def test_explanatory_text_around_json(self):
        parsed = parse_model_json_result("Here is the result:\n" + json.dumps(complete_payload()) + "\nDone.")
        self.assertTrue(parsed.normalized)

    def test_missing_noncritical_fields_is_partial(self):
        result, status, warnings = model_response_to_result('{"matched_skills":["Python"]}', repairer=lambda _: "")
        self.assertEqual(status, "partial")
        self.assertEqual(result["matched_skills"], ["Python"])
        self.assertTrue(warnings)

    def test_extra_fields_are_ignored(self):
        value = validate_compact_analysis({**complete_payload(), "rag_sources": [{"content": "ignored"}]})
        self.assertFalse(hasattr(value, "rag_sources"))

    def test_null_fields_use_defaults(self):
        value = validate_compact_analysis({"matched_skills": None, "recommendations": "Keep it concise"})
        self.assertEqual(value.matched_skills, [])
        self.assertEqual(value.concise_recommendations, ["Keep it concise"])

    def test_string_skill_becomes_list(self):
        value = validate_compact_analysis({"matched_skills": " python ", "recommendations": "Verify"})
        self.assertEqual(value.matched_skills, ["Python"])

    def test_aliases_are_recognized(self):
        value = validate_compact_analysis({"matches": "FastAPI", "gaps": "Redis", "suggestions": "Verify Redis"})
        self.assertEqual(value.matched_skills, ["FastAPI"])
        self.assertEqual(value.missing_skills, ["Redis"])

    def test_single_analysis_wrapper_is_unwrapped(self):
        parsed = parse_model_json_result(json.dumps({
            "analysis": {"matched_skills": ["Python"], "recommendations": ["Keep it concise"]}
        }))
        value = validate_compact_analysis(parsed.data)
        self.assertTrue(parsed.normalized)
        self.assertEqual(value.matched_skills, ["Python"])

    def test_evidence_object_and_named_dimension_list_are_coordinated(self):
        value = validate_compact_analysis({
            "matches": ["Python"],
            "evidence_mapping": {"Python": "resume"},
            "dimensions": [
                {"name": "skills", "score": "105%", "assessment": "Supported", "evidence": "resume"},
                {"dimension": "experience", "assessment": "Concise evidence"},
            ],
        })
        self.assertEqual(value.evidence_references[0].evidence_ids, ["resume"])
        self.assertEqual(value.concise_dimension_assessments.skills_match.score, 100)
        self.assertEqual(value.concise_dimension_assessments.work_experience.assessment, "Concise evidence")

    def test_numeric_strings_and_out_of_range_scores_are_safe(self):
        value = validate_compact_analysis({
            "matched_skills": ["Python"],
            "assessments": {"skills": {"rating": "145.2 percent", "summary": None}},
        })
        self.assertEqual(value.concise_dimension_assessments.skills_match.score, 100)
        self.assertEqual(value.concise_dimension_assessments.skills_match.assessment, "")

    def test_trailing_comma_is_recovered(self):
        parsed = parse_model_json_result('{"matched_skills":["Python"],"recommendations":["Verify"],}')
        self.assertTrue(parsed.normalized)
        self.assertIn("trailing", " ".join(parsed.warnings).lower())

    def test_one_format_repair_can_succeed(self):
        calls = []
        result, status, _warnings = model_response_to_result(
            "matched Python but missing JSON",
            repairer=lambda raw: calls.append(raw) or json.dumps(complete_payload()),
        )
        self.assertEqual(status, "repaired")
        self.assertEqual(result["matched_skills"], ["Python"])
        self.assertEqual(len(calls), 1)

    def test_format_repair_is_called_at_most_once(self):
        calls = []
        with self.assertRaises(ModelOutputError) as raised:
            model_response_to_result(
                "not JSON",
                repairer=lambda raw: calls.append(raw) or "still not JSON",
            )
        self.assertEqual(raised.exception.error_code, MODEL_OUTPUT_INVALID_JSON)
        self.assertEqual(len(calls), 1)

    def test_unknown_evidence_only_warns_and_drops_match(self):
        result, _status, _warnings = model_response_to_result(json.dumps(complete_payload(
            matched_skills=["Kubernetes"],
            evidence_references=[{"skill": "Kubernetes", "evidence_ids": ["pk:999"]}],
        )))
        validation = validate_model_evidence_references(result, resume_text="Python engineer", retrieved_chunks=[])
        self.assertEqual(validation["status"], "completed_with_rejections")
        self.assertNotIn("Kubernetes", result["matched_skills"])

    def test_unsupported_candidate_does_not_block_all_output(self):
        result = {
            "matched_skills": ["Python"], "missing_skills": [], "unknown_skills": [],
            "cover_letter": "I led 50 people.", "upgraded_resume_bullets": [],
            "_unsupported_claim_candidates": ["Generated $10M revenue."],
        }
        enforce_analysis_grounding(result, "Python engineer", [])
        self.assertGreater(result["claim_validation"]["unsupported_claim_count"], 0)
        self.assertNotIn("output_blocked", result["claim_validation"])

    def test_partial_history_round_trip_is_marked(self):
        stored = serialize_analysis_metadata(
            {"analysis_status": "partial", "analysis_warnings": ["Optional field missing"]}
        )
        value = deserialize_analysis_metadata(stored)
        self.assertEqual(value["analysis_status"], "partial")
        self.assertEqual(value["analysis_warnings"], ["Optional field missing"])

    def test_fallback_history_round_trip_is_marked(self):
        fallback = local_fallback_result("Python FastAPI", "Python Kubernetes")
        fallback.update({"analysis_status": "fallback", "analysis_warnings": ["Local fallback"]})
        value = deserialize_analysis_metadata(serialize_analysis_metadata(fallback))
        self.assertEqual(value["analysis_status"], "fallback")


class V203AnalysisApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def analyze(self, provider_error, *, request_id="phase-a1-provider-test"):
        with patch("legacy_application.call_deepseek_raw", side_effect=provider_error):
            return self.client.post(
                "/api/analyze",
                files={"resume": ("fictional.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"job_text": "Python and Kubernetes role", "save_to_history": "false", "use_project_knowledge": "false"},
                headers={"X-Request-ID": request_id},
            )

    def assert_analyze_error(self, response, *, status_code, code):
        self.assertEqual(response.status_code, status_code, response.text)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(
            set(error),
            {"code", "message", "request_id", "details"},
        )
        self.assertEqual(error["code"], code)
        self.assertIsInstance(error["details"], dict)
        self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
        return error

    def valid_analyze_request(self, **data_updates):
        data = {
            "job_text": "Python and Kubernetes role",
            "save_to_history": "false",
            "use_project_knowledge": "false",
        }
        data.update(data_updates)
        return {
            "files": {
                "resume": (
                    "fictional.docx",
                    docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            "data": data,
            "headers": {"X-Request-ID": "phase-a1-contract-test"},
        }

    def test_provider_timeout_returns_stable_fallback(self):
        response = self.analyze(TimeoutError("fictional timeout"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.headers["X-Request-ID"],
            "phase-a1-provider-test",
        )
        value = response.json()
        self.assertEqual(value["analysis_status"], "fallback")
        for key in (
            "analysis_warnings", "match_score", "matched_skills", "missing_skills", "unknown_skills",
            "scoring_breakdown", "recommendations", "used_knowledge_base", "retrieval_count", "rag_sources", "evidence_mapping",
        ):
            self.assertIn(key, value)

    def test_provider_5xx_returns_fallback(self):
        response = self.analyze(RuntimeError("fictional provider 503"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis_status"], "fallback")

    def test_cors_exposes_only_the_expected_safe_response_headers(self):
        response = self.client.post(
            "/api/analyze",
            headers={
                "Origin": "http://localhost:5173",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)
        exposed = response.headers["Access-Control-Expose-Headers"]
        self.assertIn("Idempotency-Replayed", exposed)
        self.assertIn("X-Request-ID", exposed)
        self.assertNotIn("Content-Disposition", exposed)

    def test_empty_job_input_is_rejected(self):
        response = self.client.post(
            "/api/analyze",
            files={"resume": ("fictional.docx", docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"job_text": ""},
        )
        self.assert_analyze_error(
            response,
            status_code=400,
            code="JOB_SOURCE_INVALID",
        )

    def test_empty_resume_text_is_rejected(self):
        response = self.client.post(
            "/api/analyze",
            files={"resume": ("fictional.docx", docx_bytes(""), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"job_text": "Python role"},
        )
        self.assert_analyze_error(
            response,
            status_code=400,
            code="RESUME_PARSING_FAILED",
        )

    def test_request_validation_failure_uses_stable_envelope(self):
        request = self.valid_analyze_request(rag_top_k="not-an-integer")
        response = self.client.post("/api/analyze", **request)
        error = self.assert_analyze_error(
            response,
            status_code=400,
            code="REQUEST_VALIDATION_FAILED",
        )
        self.assertEqual(error["details"], {})

    def test_resume_source_failure_uses_stable_envelope(self):
        response = self.client.post(
            "/api/analyze",
            files={"resume": ("fictional.txt", b"fictional", "text/plain")},
            data={"job_text": "Python role"},
        )
        self.assert_analyze_error(
            response,
            status_code=400,
            code="RESUME_SOURCE_INVALID",
        )

    def test_job_acquisition_failure_uses_stable_envelope(self):
        request = self.valid_analyze_request(
            job_text="",
            job_url="https://jobs.example.test/fictional",
        )
        with patch(
            "legacy_application.fetch_job_text_from_url",
            side_effect=RuntimeError("PRIVATE_FETCH_FAILURE"),
        ):
            response = self.client.post("/api/analyze", **request)
        self.assert_analyze_error(
            response,
            status_code=500,
            code="JOB_DESCRIPTION_ACQUISITION_FAILED",
        )
        self.assertNotIn("PRIVATE_FETCH_FAILURE", response.text)

    def test_input_security_block_is_safe_and_skips_provider(self):
        private_secret = "SYNTHETIC_API_KEY=abcdefghijklmnop1234567890"
        request = self.valid_analyze_request()
        request["files"] = {
            "resume": (
                "fictional.docx",
                docx_bytes(f"Python engineer {private_secret}"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        with patch("legacy_application.call_deepseek_raw") as provider:
            response = self.client.post("/api/analyze", **request)
        error = self.assert_analyze_error(
            response,
            status_code=422,
            code="INPUT_SECURITY_BLOCKED",
        )
        self.assertEqual(error["details"]["security_status"], "blocked")
        self.assertNotIn(private_secret, response.text)
        provider.assert_not_called()

    def test_project_knowledge_failure_uses_stable_envelope(self):
        request = self.valid_analyze_request(use_project_knowledge="true")
        with patch(
            "legacy_application.search_project_knowledge",
            side_effect=RuntimeError("PRIVATE_RETRIEVAL_FAILURE"),
        ):
            response = self.client.post("/api/analyze", **request)
        self.assert_analyze_error(
            response,
            status_code=500,
            code="PROJECT_KNOWLEDGE_RETRIEVAL_FAILED",
        )
        self.assertNotIn("PRIVATE_RETRIEVAL_FAILURE", response.text)

    def test_output_security_block_uses_stable_envelope(self):
        provider_response = ProviderAnalysisResponse(
            content=f"{INTERNAL_SECURITY_MARKER}\n{json.dumps(complete_payload())}",
            metadata={"finish_reason": "stop"},
        )
        request = self.valid_analyze_request()
        with patch(
            "legacy_application.call_deepseek_raw",
            return_value=provider_response,
        ):
            response = self.client.post("/api/analyze", **request)
        self.assert_analyze_error(
            response,
            status_code=502,
            code="OUTPUT_SECURITY_BLOCKED",
        )
        self.assertNotIn(INTERNAL_SECURITY_MARKER, response.text)

    def test_persistence_failure_uses_safe_stable_envelope(self):
        request = self.valid_analyze_request(save_to_history="true")
        with patch(
            "legacy_application.call_deepseek_raw",
            side_effect=TimeoutError("fictional timeout"),
        ), patch(
            "legacy_application.insert_application_record",
            side_effect=RuntimeError("PRIVATE_DATABASE_FAILURE"),
        ):
            response = self.client.post("/api/analyze", **request)
        self.assert_analyze_error(
            response,
            status_code=503,
            code="ANALYZE_PERSISTENCE_FAILED",
        )
        self.assertNotIn("PRIVATE_DATABASE_FAILURE", response.text)

    def test_unknown_exception_uses_generic_stable_envelope(self):
        request = self.valid_analyze_request(save_to_history="true")
        with patch(
            "legacy_application.call_deepseek_raw",
            side_effect=TimeoutError("fictional timeout"),
        ), patch(
            "legacy_application.insert_application_record",
            return_value=123,
        ), patch(
            "legacy_application.update_application_workflow_steps",
            side_effect=RuntimeError("PRIVATE_UNKNOWN_FAILURE"),
        ):
            response = self.client.post("/api/analyze", **request)
        error = self.assert_analyze_error(
            response,
            status_code=500,
            code="UNEXPECTED_SERVER_ERROR",
        )
        self.assertEqual(
            error["message"],
            "Unexpected server error. Please try again.",
        )
        self.assertNotIn("PRIVATE_UNKNOWN_FAILURE", response.text)

    def test_malformed_provider_output_still_returns_fallback_200(self):
        provider_response = ProviderAnalysisResponse(
            content='{"matched_skills":["PRIVATE_MODEL_FRAGMENT"]',
            metadata={"finish_reason": "stop", "output_tokens": 20},
        )
        request = self.valid_analyze_request()
        with patch(
            "legacy_application.call_deepseek_raw",
            return_value=provider_response,
        ), patch(
            "legacy_application.call_deepseek_repair",
            side_effect=ModelOutputError(MODEL_OUTPUT_INVALID_JSON),
        ):
            response = self.client.post("/api/analyze", **request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["analysis_status"], "fallback")
        self.assertNotIn("PRIVATE_MODEL_FRAGMENT", response.text)


if __name__ == "__main__":
    unittest.main()
