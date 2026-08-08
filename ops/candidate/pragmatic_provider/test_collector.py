"""Deterministic tests for the operations-only pragmatic candidate collector."""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

try:
    from .collector import (
        BoundedEvidenceCollector,
        DatabaseObservation,
        HttpResponse,
        LogObservation,
        SyntheticFixture,
        _write_bounded,
    )
except ImportError:  # pragma: no cover - supports direct local invocation.
    from collector import (
        BoundedEvidenceCollector,
        DatabaseObservation,
        HttpResponse,
        LogObservation,
        SyntheticFixture,
        _write_bounded,
    )


FIXTURE = SyntheticFixture(
    case_id="offline-case",
    resume_filename="synthetic.docx",
    resume_bytes=b"synthetic-resume-bytes",
    job_text="synthetic-jd-content",
)


def response(*, state: str = "fallback", include_tokens: bool = True) -> HttpResponse:
    completion = {
        "primary_attempt_count": 2,
        "repair_attempt_count": 0,
        "deadline_exhausted": False,
        "history_finalized": True,
        "idempotency_finalized": True,
    }
    if include_tokens:
        completion.update({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
    return HttpResponse(
        status_code=200,
        headers={"X-Request-ID": "observed", "Idempotency-Replayed": "true" if state == "replay" else ""},
        body={
            "analysis_status": "fallback" if state == "replay" else state,
            "job_summary": "Job Summary unavailable: synthetic bounded fixture.",
            "match_reason": "Match Reasons unavailable: synthetic bounded fixture.",
            "saved_to_history": True,
            "application_id": 31,
            "security_status": "safe",
            "model_completion": completion,
        },
        elapsed_ms=42.0,
    )


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[SyntheticFixture, str, str]] = []
        self.mocked_provider_calls = 0

    def analyze(self, fixture, *, idempotency_key, request_id):
        self.calls.append((fixture, idempotency_key, request_id))
        if len(self.calls) == 1:
            self.mocked_provider_calls += 2
        return response(state="replay" if len(self.calls) == 2 else "fallback")


class FakeLogs:
    def __init__(self, *, missing_tokens: bool = False, missing_timeout: bool = False) -> None:
        self.observations: list[LogObservation] = []
        self.missing_tokens = missing_tokens
        self.missing_timeout = missing_timeout

    def observe(self, request_id, started_at):
        del request_id, started_at
        if not self.observations:
            observation = LogObservation(
                provider_call_count=2,
                deadline_exhausted=False,
                duration_ms=None if self.missing_timeout else 42.0,
            )
        else:
            observation = LogObservation(provider_call_count=0, deadline_exhausted=False, duration_ms=1.0)
        self.observations.append(observation)
        return observation


class FakeDatabase:
    def __init__(self, *, fail=False) -> None:
        self.calls = 0
        self.fail = fail

    def observe(self, user_id, idempotency_key_hash):
        del user_id, idempotency_key_hash
        self.calls += 1
        if self.fail:
            raise RuntimeError("secret Resume and Provider response must not be logged")
        return DatabaseObservation(
            record_count=1,
            status="completed",
            idempotency_finalized=True,
            history_count=1,
            history_finalized=True,
            history_record_id=77,
        )


class CollectorTests(unittest.TestCase):
    def collect(self, *, logs="default", database="default", key="pja-owned-key-123456"):
        client = FakeClient()
        collector = BoundedEvidenceCollector(
            client,
            log_observer=FakeLogs() if logs == "default" else logs,
            database_verifier=FakeDatabase() if database == "default" else database,
            key_factory=lambda: key,
            request_id_factory=lambda prefix: f"{prefix}-request",
        )
        return client, collector.collect(FIXTURE, user_id="synthetic-user-id")

    def test_successful_analyze_followed_by_completed_replay(self):
        client, evidence = self.collect()
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(evidence.replay)
        self.assertTrue(evidence.replay_recognized)
        self.assertEqual(evidence.replay_result, "completed")

    def test_replay_uses_exact_same_caller_owned_key_and_identical_payload(self):
        client, _evidence = self.collect()
        self.assertEqual(client.calls[0][1], client.calls[1][1])
        self.assertIs(client.calls[0][0], client.calls[1][0])
        self.assertEqual(client.calls[0][0].job_text, client.calls[1][0].job_text)
        self.assertEqual(client.calls[0][0].resume_bytes, client.calls[1][0].resume_bytes)

    def test_replay_performs_zero_mocked_provider_calls(self):
        client, evidence = self.collect()
        self.assertEqual(client.mocked_provider_calls, 2)
        self.assertEqual(evidence.replay_provider_call_delta, 0)

    def test_replay_does_not_create_duplicate_history(self):
        _client, evidence = self.collect()
        self.assertFalse(evidence.duplicate_history)
        self.assertTrue(evidence.same_history_record)

    def test_job_summary_boolean_is_captured(self):
        _client, evidence = self.collect()
        self.assertTrue(evidence.job_summary_present_or_unavailable)

    def test_match_reasons_boolean_is_captured(self):
        _client, evidence = self.collect()
        self.assertTrue(evidence.match_reasons_present_or_unavailable)

    def test_collector_survives_missing_optional_metadata(self):
        _client, evidence = self.collect(logs=None, database=None)
        self.assertTrue(evidence.http_success)
        self.assertTrue(evidence.job_summary_present_or_unavailable)
        self.assertTrue(evidence.match_reasons_present_or_unavailable)
        self.assertTrue(
            any(item.startswith("first_log_metadata_") for item in evidence.optional_metadata_failures)
        )

    def test_collector_survives_missing_token_metadata(self):
        client = FakeClient()
        logs = FakeLogs(missing_tokens=True)
        collector = BoundedEvidenceCollector(
            client,
            log_observer=logs,
            database_verifier=FakeDatabase(),
            key_factory=lambda: "pja-owned-key-123456",
            request_id_factory=lambda prefix: f"{prefix}-request",
        )
        first = response(include_tokens=False)
        original = client.analyze
        calls = 0

        def no_token_analyze(fixture, *, idempotency_key, request_id):
            nonlocal calls
            calls += 1
            value = first if calls == 1 else response(state="replay", include_tokens=False)
            client.calls.append((fixture, idempotency_key, request_id))
            return value

        client.analyze = no_token_analyze
        evidence = collector.collect(FIXTURE, user_id="synthetic-user-id")
        self.assertTrue(evidence.http_success)
        self.assertIsNotNone(evidence.provider_call_count)
        del original

    def test_collector_survives_missing_timeout_aggregate(self):
        _client, evidence = self.collect(logs=FakeLogs(missing_timeout=True))
        self.assertTrue(evidence.inside_authoritative_deadline)
        self.assertEqual(evidence.duration_ms, 42.0)

    def test_partial_aggregate_failure_does_not_erase_hard_gate_fields(self):
        _client, evidence = self.collect(database=FakeDatabase(fail=True))
        self.assertTrue(evidence.http_success)
        self.assertTrue(evidence.recognized_state)
        self.assertTrue(evidence.job_summary_present_or_unavailable)
        self.assertTrue(evidence.match_reasons_present_or_unavailable)
        self.assertIn("first_database_metadata_unavailable", evidence.optional_metadata_failures)
        self.assertIn("replay_database_metadata_unavailable", evidence.optional_metadata_failures)

    def test_secrets_and_content_are_not_logged(self):
        logger = logging.getLogger("pja.candidate.collector")
        with self.assertLogs(logger, level="WARNING") as captured:
            self.collect(database=FakeDatabase(fail=True))
        rendered = "\n".join(captured.output)
        for forbidden in (
            "secret Resume",
            "Provider response",
            "synthetic-resume-bytes",
            "synthetic-jd-content",
            "pja-owned-key-123456",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_bounded_evidence_can_be_written_after_optional_failure(self):
        _client, evidence = self.collect(database=FakeDatabase(fail=True))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            _write_bounded(path, {"supplemental_evidence": evidence.__dict__})
            value = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(value["supplemental_evidence"]["http_success"])


if __name__ == "__main__":
    unittest.main()
