"""Candidate-only bounded evidence adapter around the existing mock provider.

This module is copied only into the disposable candidate image. It does not
change or get imported by the production backend image.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import legacy_application
from app.application import extend_application
from logging_utils import request_id_context


EVIDENCE_PATH = Path("/tmp/candidate-evidence.jsonl")
BARRIER_ENTERED = Path("/tmp/candidate-provider.entered")
BARRIER_RELEASE = Path("/tmp/candidate-provider.release")
_provider_call_count = 0
_candidate_request_id: ContextVar[str] = ContextVar(
    "candidate_request_id", default=""
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _emit(event: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "request_id": _candidate_request_id.get() or request_id_context.get(),
        **fields,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    with EVIDENCE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
    print(encoded, flush=True)


_original_select = legacy_application.select_effective_normalization
_original_retrieval_query = legacy_application.build_knowledge_retrieval_query
_original_safe_prompt = legacy_application.build_safe_analysis_prompt
_original_provider = legacy_application.call_deepseek_raw


async def _candidate_select_effective_normalization(**kwargs: Any):
    _candidate_request_id.set(str(kwargs["request_id"]))
    local_text = kwargs["local_sanitized_job_text"]
    result = await _original_select(**kwargs)
    _emit(
        "candidate_effective_normalization",
        local_input_sha256=_sha256(local_text),
        effective_input_sha256=_sha256(result.text),
        effective_source=result.source,
        policy_version=result.policy_version,
        dictionary_version=result.dictionary_version,
        java_attempted=result.java_attempted,
        java_outcome=result.java_outcome,
        authoritative_second_scan_outcome=result.authoritative_second_scan_outcome,
    )
    return result


def _candidate_retrieval_query(job_description: str, resume_text: str) -> str:
    _emit(
        "candidate_rag_input",
        effective_input_sha256=_sha256(job_description),
    )
    return _original_retrieval_query(job_description, resume_text)


def _candidate_safe_prompt(
    *,
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]],
) -> str:
    prompt = _original_safe_prompt(
        resume_text=resume_text,
        job_description=job_description,
        rag_chunks=rag_chunks,
    )
    _emit(
        "candidate_prompt_input",
        effective_input_sha256=_sha256(job_description),
        exact_effective_input_present=job_description in prompt,
        prompt_sha256=_sha256(prompt),
    )
    return prompt


def _candidate_provider(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]] | None = None,
    analysis_prompt: str | None = None,
    usage_out: dict[str, Any] | None = None,
    deadline_monotonic: float | None = None,
):
    global _provider_call_count
    settings = legacy_application.load_config(validate_production=False)
    if settings.app_env != "test" or not settings.mock_provider_enabled:
        raise RuntimeError("Candidate adapter requires the test-only mock provider.")
    _provider_call_count += 1
    _emit(
        "candidate_mock_provider_observation",
        call_count=_provider_call_count,
        effective_input_sha256=_sha256(job_description),
        exact_effective_input_present=bool(
            analysis_prompt and job_description in analysis_prompt
        ),
    )
    if os.getenv("CANDIDATE_PROVIDER_BARRIER", "0") == "1":
        BARRIER_ENTERED.touch(mode=0o600, exist_ok=True)
        deadline = time.monotonic() + 20
        while not BARRIER_RELEASE.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Candidate provider barrier timed out.")
            time.sleep(0.05)
    return _original_provider(
        resume_text,
        job_description,
        rag_chunks,
        analysis_prompt,
        usage_out,
        deadline_monotonic,
    )


legacy_application.select_effective_normalization = (
    _candidate_select_effective_normalization
)
legacy_application.build_knowledge_retrieval_query = _candidate_retrieval_query
legacy_application.build_safe_analysis_prompt = _candidate_safe_prompt
legacy_application.call_deepseek_raw = _candidate_provider

app = extend_application(legacy_application.app)
