import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from analysis_contract import ModelOutputError, ProviderAnalysisResponse
from candidates import deepseek_provider_real_candidate as candidate


VALID_PROVIDER_CONTENT = json.dumps(
    {
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": ["Kubernetes"],
        "unknown_skills": [],
        "concise_dimension_assessments": {
            "skills_match": {
                "score": 80,
                "assessment": "The synthetic resume names the requested skills.",
                "evidence_ids": ["resume"],
            },
            "project_experience": {
                "score": 60,
                "assessment": "The synthetic project evidence is limited.",
                "evidence_ids": ["pk:101"],
            },
        },
        "evidence_references": [
            {"skill": "Python", "evidence_ids": ["resume"]},
            {"skill": "FastAPI", "evidence_ids": ["resume"]},
        ],
        "unsupported_claim_candidates": [],
        "concise_recommendations": ["Keep only verified API evidence."],
    }
)


def runtime_settings():
    return SimpleNamespace(
        app_env="test",
        deepseek_api_key="synthetic-test-key",
        deepseek_model="deepseek-v4-pro",
        deepseek_thinking_enabled=False,
        model_max_output_tokens=1600,
        model_length_retry_output_tokens=2400,
        model_repair_output_tokens=1000,
        provider_overall_deadline_seconds=130,
    )


class DeepSeekRealCandidateRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with candidate.FIXTURE_PATH.open(encoding="utf-8") as fixture:
            cls.cases = json.load(fixture)

    def setUp(self):
        self.environment = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "PJA_REAL_DEEPSEEK_CANDIDATE": "1",
                "APP_DATABASE_PATH": str(Path(self.environment.name) / "candidate.sqlite"),
                "PROJECT_KNOWLEDGE_PATH": str(Path(self.environment.name) / "synthetic.md"),
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.environment.cleanup()

    def test_fixture_is_ten_distinct_synthetic_cases(self):
        self.assertEqual(len(self.cases), 10)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 10)
        self.assertEqual(
            {case["role_family"] for case in self.cases},
            {
                "technical_backend",
                "support_engineering",
                "technical_frontend",
                "technical_platform",
                "technical_data",
                "technical_quality",
            },
        )

    def test_candidate_environment_requires_exact_merged_budgets(self):
        with patch.object(candidate, "load_config", return_value=runtime_settings()):
            settings = candidate._validate_candidate_environment()
        self.assertEqual(settings.deepseek_model, "deepseek-v4-pro")
        self.assertFalse(settings.deepseek_thinking_enabled)
        self.assertEqual(candidate.EXPECTED_CONFIG["maximum_provider_calls"], 3)

    def test_mocked_canonical_response_is_complete_and_bounded(self):
        case = self.cases[0]

        def fake_raw(*_args, usage_out=None, **_kwargs):
            usage_out.update(
                {
                    "model_id": "deepseek-v4-pro",
                    "thinking_enabled": False,
                    "response_mode": "json_object",
                    "primary_attempt_count": 1,
                    "finish_reason": "stop",
                    "input_tokens": 100,
                    "output_tokens": 80,
                    "total_tokens": 180,
                    "latency_ms": 12,
                }
            )
            return ProviderAnalysisResponse(content=VALID_PROVIDER_CONTENT)

        with patch.object(candidate, "call_deepseek_raw", side_effect=fake_raw) as raw:
            with patch.object(candidate, "call_deepseek_repair") as repair:
                record = candidate._run_case(case, runtime_settings())
        self.assertEqual(record["state"], "complete")
        self.assertTrue(record["public_contract_ok"])
        self.assertEqual(record["provider_call_count"], 1)
        self.assertEqual(record["repair_count"], 0)
        raw.assert_called_once()
        repair.assert_not_called()

    def test_format_repair_is_the_only_extra_call(self):
        case = self.cases[0]

        def fake_raw(*_args, usage_out=None, **_kwargs):
            usage_out.update(
                {
                    "model_id": "deepseek-v4-pro",
                    "thinking_enabled": False,
                    "response_mode": "json_object",
                    "primary_attempt_count": 2,
                    "finish_reason": "stop",
                    "transient_retry_reason": "finish_length",
                    "input_tokens": 120,
                    "output_tokens": 100,
                    "total_tokens": 220,
                    "latency_ms": 15,
                }
            )
            return ProviderAnalysisResponse(content="not valid structured output")

        def fake_repair(*_args, usage_out=None, **_kwargs):
            usage_out.update(
                {
                    "model_id": "deepseek-v4-pro",
                    "thinking_enabled": False,
                    "response_mode": "json_object",
                    "repair_attempt_count": 1,
                    "finish_reason": "stop",
                    "input_tokens": 70,
                    "output_tokens": 60,
                    "total_tokens": 130,
                    "latency_ms": 8,
                }
            )
            return ProviderAnalysisResponse(content=VALID_PROVIDER_CONTENT)

        with patch.object(candidate, "call_deepseek_raw", side_effect=fake_raw):
            with patch.object(candidate, "call_deepseek_repair", side_effect=fake_repair):
                record = candidate._run_case(case, runtime_settings())
        self.assertEqual(record["state"], "repaired")
        self.assertTrue(record["public_contract_ok"])
        self.assertEqual(record["retry_count"], 1)
        self.assertEqual(record["repair_count"], 1)
        self.assertEqual(record["provider_call_count"], 3)
        self.assertEqual(record["length_retry_count"], 1)

    def test_severe_output_is_rejected_before_repair(self):
        case = self.cases[0]

        def fake_raw(*_args, usage_out=None, **_kwargs):
            usage_out.update({"primary_attempt_count": 1, "finish_reason": "stop"})
            return ProviderAnalysisResponse(
                content='{"matched_skills":["Python"],"api_key":"sk-test-only-not-real"}'
            )

        with patch.object(candidate, "call_deepseek_raw", side_effect=fake_raw):
            with patch.object(candidate, "call_deepseek_repair") as repair:
                record = candidate._run_case(case, runtime_settings())
        self.assertEqual(record["state"], "security_rejected")
        self.assertTrue(record["security_rejected"])
        self.assertEqual(record["repair_count"], 0)
        repair.assert_not_called()

    def test_provider_error_is_classified_without_exception_text(self):
        case = self.cases[0]

        def fake_raw(*_args, usage_out=None, **_kwargs):
            usage_out.update({"primary_attempt_count": 1})
            raise ModelOutputError(
                "MODEL_PROVIDER_ERROR",
                metadata={"primary_attempt_count": 1, "finish_reason": "unknown"},
            )

        with patch.object(candidate, "call_deepseek_raw", side_effect=fake_raw):
            record = candidate._run_case(case, runtime_settings())
        self.assertEqual(record["state"], "fallback")
        self.assertEqual(record["fallback_reason"], "provider_call_failed")
        self.assertTrue(record["public_contract_ok"])


if __name__ == "__main__":
    unittest.main()
