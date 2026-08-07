"""Manual-only, metadata-only DeepSeek candidate validation runner.

This module is intentionally outside the production request path.  It imports
the merged Provider boundary, sends ten synthetic cases sequentially, and
writes only bounded aggregate metadata.  The real run requires the explicit
``PJA_REAL_DEEPSEEK_CANDIDATE=1`` opt-in supplied by the wrapper script.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import statistics
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FIXTURE_PATH = BACKEND_DIR / "fixtures" / "deepseek_provider_real_candidate_v1" / "cases.json"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from analysis_contract import ModelOutputError, ProviderAnalysisResponse, safe_model_metadata
from analysis_fallback import (
    deterministic_scoring,
    local_fallback_result,
)
from config import MAX_PROVIDER_OUTPUT_TOKENS, load_config
from legacy_application import (
    build_default_rag_sources,
    build_safe_analysis_prompt,
    calculate_weighted_match_score,
    call_deepseek_raw,
    call_deepseek_repair,
    deterministic_job_summary,
    deterministic_match_reasons,
    enforce_analysis_grounding,
    ensure_deterministic_narratives,
    model_response_to_result,
    reconcile_result_with_rag_evidence,
    scan_llm_output,
    validate_model_evidence_references,
)
from security_utils import (
    empty_security_scan,
    merge_security_scans,
    normalized_security_scan,
    prepare_resume_for_llm,
    scan_and_sanitize_untrusted_text,
    scan_project_chunks,
    security_status_from_scan,
)
from provider_deadline import (
    ANALYZE_TOTAL_SAFETY_DEADLINE_SECONDS,
    ProviderDeadline,
)


EXPECTED_CONFIG = {
    "primary_output_tokens": 1600,
    "length_retry_output_tokens": 2400,
    "repair_output_tokens": 1000,
    "maximum_output_tokens": 5000,
    "thinking_enabled": False,
    "response_mode": "json_object",
    "maximum_provider_calls": 3,
}
UNAVAILABLE_SUMMARY = "Job Summary unavailable: no validated job-description content was available."
UNAVAILABLE_REASONS = "Match Reasons unavailable: no validated skill or evidence breakdown was available."
SAFE_LOG_FORBIDDEN_MARKERS = (
    "reasoning_content",
    "authorization",
    "deepseek_api_key",
    "api_key=",
    "sk-",
)


class CandidateBlocked(RuntimeError):
    """A safe candidate stop that contains no provider body or exception text."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:
            self.messages.append("unrenderable_log_record")


@contextmanager
def capture_safe_logs() -> Iterator[_CaptureHandler]:
    handler = _CaptureHandler()
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield handler
    finally:
        root_logger.removeHandler(handler)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile / 100) * len(ordered) + 0.999999) - 1))
    return round(ordered[index], 3)


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return round(max(0.0, float(value or 0)), 3)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _load_cases() -> list[dict[str, Any]]:
    with FIXTURE_PATH.open(encoding="utf-8") as fixture:
        cases = json.load(fixture)
    if not isinstance(cases, list) or len(cases) != 10:
        raise CandidateBlocked("synthetic_case_count_invalid")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != 10 or len(set(case_ids)) != 10 or any(not item for item in case_ids):
        raise CandidateBlocked("synthetic_case_ids_invalid")
    return cases


def _validate_candidate_environment() -> Any:
    if os.getenv("PJA_REAL_DEEPSEEK_CANDIDATE") != "1":
        raise CandidateBlocked("manual_opt_in_required")
    runtime_settings = load_config(validate_production=False)
    if runtime_settings.app_env == "production":
        raise CandidateBlocked("production_environment_forbidden")
    if getattr(runtime_settings, "deepseek_network_mode", None) != "direct":
        raise CandidateBlocked("direct_network_mode_required")
    if not runtime_settings.deepseek_api_key:
        raise CandidateBlocked("approved_deepseek_secret_unavailable")
    if not runtime_settings.deepseek_model.strip():
        raise CandidateBlocked("model_configuration_blank")
    configured = {
        "primary_output_tokens": runtime_settings.model_max_output_tokens,
        "length_retry_output_tokens": runtime_settings.model_length_retry_output_tokens,
        "repair_output_tokens": runtime_settings.model_repair_output_tokens,
        "maximum_output_tokens": MAX_PROVIDER_OUTPUT_TOKENS,
        "thinking_enabled": runtime_settings.deepseek_thinking_enabled,
        "response_mode": "json_object",
        "maximum_provider_calls": 3,
    }
    if configured != EXPECTED_CONFIG:
        raise CandidateBlocked("merged_candidate_configuration_mismatch")
    if os.getenv("APP_DATABASE_PATH", "").startswith(str(BACKEND_DIR / "data")):
        raise CandidateBlocked("nonisolated_database_path")
    if os.getenv("APP_DATABASE_PATH", "") in {"/app/data/app.db", ""}:
        raise CandidateBlocked("isolated_database_path_missing")
    if os.getenv("PROJECT_KNOWLEDGE_PATH", "").endswith("docs/PROJECT_KNOWLEDGE.md"):
        raise CandidateBlocked("production_project_knowledge_path_forbidden")
    return runtime_settings


def _safe_provider_metadata(*metadata: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in metadata:
        if isinstance(item, dict):
            merged.update(item)
    return safe_model_metadata(merged)


def _provider_tokens(primary: dict[str, Any], repair: dict[str, Any]) -> dict[str, int]:
    return {
        key: min(
            1_000_000,
            _safe_int(primary.get(key)) + _safe_int(repair.get(key)),
        )
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }


def _record_action(metadata: dict[str, Any], category: str) -> None:
    actions = metadata.setdefault("salvage_action_categories", [])
    if not isinstance(actions, list):
        actions = []
        metadata["salvage_action_categories"] = actions
    if category not in actions:
        actions.append(category)


def _public_contract_ok(result: dict[str, Any]) -> bool:
    required_lists = ("matched_skills", "missing_skills", "recommendations")
    if not isinstance(result, dict) or result.get("analysis_status") not in {
        "complete",
        "repaired",
        "partial",
        "fallback",
    }:
        return False
    if any(not isinstance(result.get(key), list) for key in required_lists):
        return False
    if not isinstance(result.get("scoring_breakdown"), dict):
        return False
    summary = result.get("job_summary")
    reasons = result.get("match_reason")
    if not isinstance(summary, str) or not summary.strip():
        return False
    if not isinstance(reasons, str) or not reasons.strip():
        return False
    json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
    return True


def _fallback_result(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    result = local_fallback_result(resume_text, job_description, rag_chunks)
    result["scoring_breakdown"] = deterministic_scoring(
        result,
        resume_text,
        job_description,
        rag_chunks,
    )
    result["match_score"] = calculate_weighted_match_score(result["scoring_breakdown"])
    result["job_summary"] = deterministic_job_summary(job_description)
    result["match_reason"] = deterministic_match_reasons(
        result["scoring_breakdown"],
        result.get("matched_skills") or [],
        result.get("missing_skills") or [],
    )
    result["analysis_status"] = "fallback"
    result["analysis_warnings"] = ["deterministic_fallback"]
    result["recommendations"] = list(result.get("recommendations") or result.get("resume_suggestions") or [])
    result["security_scan"] = empty_security_scan()
    result["security_status"] = security_status_from_scan(result["security_scan"])
    return result


def _run_case(case: dict[str, Any], runtime_settings: Any) -> dict[str, Any]:
    started = time.perf_counter()
    primary_metadata: dict[str, Any] = {}
    repair_metadata: dict[str, Any] = {}
    parse_metadata: dict[str, Any] = {}
    security_scan = empty_security_scan()
    case_id = str(case["case_id"])
    resume_text, resume_scan = prepare_resume_for_llm(str(case.get("resume") or ""))
    job_text, job_scan = scan_and_sanitize_untrusted_text(
        str(case.get("job_description") or ""),
        "job_description",
    )
    raw_chunks = case.get("project_knowledge") if isinstance(case.get("project_knowledge"), list) else []
    rag_chunks, project_scan, _filtered_sources = scan_project_chunks(raw_chunks)
    security_scan = merge_security_scans(security_scan, resume_scan, job_scan, project_scan)
    if security_scan.get("blocked") or security_scan.get("sensitive_data_detected"):
        raise CandidateBlocked("synthetic_input_security_rejected")

    safe_prompt = build_safe_analysis_prompt(
        resume_text=resume_text,
        job_description=job_text,
        rag_chunks=rag_chunks,
    )
    provider_started = time.perf_counter()
    provider_deadline = ProviderDeadline.for_phase(
        phase_started_monotonic=time.monotonic(),
        configured_deadline_seconds=runtime_settings.provider_overall_deadline_seconds,
        request_safety_deadline=time.monotonic() + ANALYZE_TOTAL_SAFETY_DEADLINE_SECONDS,
    )
    provider_available = False
    security_rejected = False
    fallback_reason = ""
    deadline_exhausted = False
    result: dict[str, Any] | None = None
    status = "fallback"

    try:
        provider_response = call_deepseek_raw(
            resume_text,
            job_text,
            rag_chunks,
            analysis_prompt=safe_prompt,
            usage_out=primary_metadata,
            deadline_monotonic=provider_deadline.absolute_deadline,
        )
        provider_available = True
        safe_content, output_scan, marker_leaked = scan_llm_output(provider_response.content)
        security_scan = merge_security_scans(security_scan, output_scan)
        if marker_leaked or output_scan.get("sensitive_data_detected") or output_scan.get("blocked"):
            security_rejected = True
            fallback_reason = "output_security_blocked"
        else:
            def repairer(raw_response: str) -> ProviderAnalysisResponse:
                repaired = call_deepseek_repair(
                    raw_response,
                    usage_out=repair_metadata,
                    deadline_monotonic=provider_deadline.absolute_deadline,
                )
                if not isinstance(repaired, ProviderAnalysisResponse):
                    return ProviderAnalysisResponse(content=str(repaired or ""), metadata={})
                return repaired

            try:
                result, status, _warnings = model_response_to_result(
                    safe_content,
                    repairer=repairer,
                    metadata_out=parse_metadata,
                )
            except Exception:
                fallback_reason = "minimum_safe_contract_failed"
                result = None
                status = "fallback"

    except ModelOutputError as exc:
        primary_metadata.update(exc.metadata)
        fallback_reason = str(exc.metadata.get("fallback_reason") or "provider_call_failed")
        deadline_exhausted = bool(exc.metadata.get("deadline_exhausted"))
    except Exception:
        fallback_reason = "provider_call_failed"
        deadline_exhausted = False

    provider_duration_ms = round((time.perf_counter() - provider_started) * 1000, 3)
    if provider_deadline.expired():
        deadline_exhausted = True
        fallback_reason = "provider_deadline_exhausted"
        if not security_rejected:
            result = None
            status = "fallback"
    if security_rejected:
        # A severe output is never repaired or converted to a partial result.
        provider_calls = _safe_int(primary_metadata.get("primary_attempt_count"))
        safe_metadata = _safe_provider_metadata(primary_metadata, parse_metadata)
        return _case_record(
            case_id=case_id,
            status="security_rejected",
            fallback_reason=fallback_reason,
            security_rejected=True,
            result=None,
            primary_metadata=safe_metadata,
            repair_metadata=repair_metadata,
            parse_metadata=parse_metadata,
            provider_calls=provider_calls,
            provider_duration_ms=provider_duration_ms,
            end_to_end_ms=round((time.perf_counter() - started) * 1000, 3),
            deadline_exhausted=deadline_exhausted,
        )

    if result is None:
        result = _fallback_result(resume_text, job_text, rag_chunks)
        status = "fallback"
    else:
        evidence_validation = validate_model_evidence_references(
            result,
            resume_text=resume_text,
            retrieved_chunks=rag_chunks,
        )
        if evidence_validation.get("rejected_reference_count"):
            _record_action(parse_metadata, "evidence_reference_cleanup")
            if status == "complete":
                status = "partial"
        corrected_terms = reconcile_result_with_rag_evidence(result, rag_chunks)
        if corrected_terms:
            _record_action(parse_metadata, "evidence_reconciliation")
        enforce_analysis_grounding(result, resume_text, rag_chunks)
        result["scoring_breakdown"] = deterministic_scoring(
            result,
            resume_text,
            job_text,
            rag_chunks,
        )
        result["match_score"] = calculate_weighted_match_score(result["scoring_breakdown"])
        ensure_deterministic_narratives(result, job_text)
        result["rag_sources"] = build_default_rag_sources(
            rag_chunks,
            result.get("matched_skills") or [],
        )
        result["analysis_status"] = status
        result["analysis_warnings"] = []
        result["recommendations"] = list(result.get("recommendations") or result.get("resume_suggestions") or [])
        if (result.get("claim_validation") or {}).get("unsupported_claim_count"):
            _record_action(parse_metadata, "unsupported_claim_cleanup")
            if status == "complete":
                status = "partial"
            result["analysis_status"] = status
        result["security_scan"] = normalized_security_scan(security_scan)
        result["security_status"] = security_status_from_scan(result["security_scan"])
        result["security_policy_version"] = result["security_scan"].get("policy_version")
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        _final_text, final_scan, final_marker = scan_llm_output(serialized)
        security_scan = merge_security_scans(security_scan, final_scan)
        if final_marker or final_scan.get("sensitive_data_detected") or final_scan.get("blocked"):
            security_rejected = True
            fallback_reason = "final_output_security_blocked"
            result = None

    primary_calls = _safe_int(primary_metadata.get("primary_attempt_count"))
    repair_calls = max(
        _safe_int(repair_metadata.get("repair_attempt_count")),
        _safe_int(parse_metadata.get("repair_attempt_count")),
    )
    provider_calls = primary_calls + repair_calls
    if provider_calls > EXPECTED_CONFIG["maximum_provider_calls"]:
        raise CandidateBlocked("provider_call_bound_exceeded")
    if security_rejected:
        status = "security_rejected"

    combined_metadata = _safe_provider_metadata(primary_metadata, parse_metadata)
    return _case_record(
        case_id=case_id,
        status=status,
        fallback_reason=fallback_reason,
        security_rejected=security_rejected,
        result=result,
        primary_metadata=combined_metadata,
        repair_metadata=repair_metadata,
        parse_metadata=parse_metadata,
        provider_calls=provider_calls,
        provider_duration_ms=provider_duration_ms,
        end_to_end_ms=round((time.perf_counter() - started) * 1000, 3),
        deadline_exhausted=deadline_exhausted,
    )


def _case_record(
    *,
    case_id: str,
    status: str,
    fallback_reason: str,
    security_rejected: bool,
    result: dict[str, Any] | None,
    primary_metadata: dict[str, Any],
    repair_metadata: dict[str, Any],
    parse_metadata: dict[str, Any],
    provider_calls: int,
    provider_duration_ms: float,
    end_to_end_ms: float,
    deadline_exhausted: bool,
) -> dict[str, Any]:
    public_contract_ok = bool(result is not None and _public_contract_ok(result))
    if result is not None and not public_contract_ok:
        raise CandidateBlocked("public_contract_serialization_failure")
    summary = result.get("job_summary") if result else ""
    reasons = result.get("match_reason") if result else ""
    summary_status = "present" if isinstance(summary, str) and summary.strip() else "explicit_unavailable"
    reasons_status = "present" if isinstance(reasons, str) and reasons.strip() else "explicit_unavailable"
    if summary_status not in {"present", "explicit_unavailable"}:
        raise CandidateBlocked("job_summary_representation_missing")
    if reasons_status not in {"present", "explicit_unavailable"}:
        raise CandidateBlocked("match_reasons_representation_missing")
    tokens = _provider_tokens(primary_metadata, repair_metadata)
    primary_attempts = min(2, _safe_int(primary_metadata.get("primary_attempt_count")))
    repair_attempts = min(1, max(
        _safe_int(repair_metadata.get("repair_attempt_count")),
        _safe_int(parse_metadata.get("repair_attempt_count")),
    ))
    active_provider_durations_ms: list[float] = []
    for metadata in (primary_metadata, repair_metadata):
        metadata_durations = 0
        for value in metadata.get("provider_attempt_durations_ms") or []:
            try:
                active_provider_durations_ms.append(round(max(0.0, float(value)), 3))
                metadata_durations += 1
            except (TypeError, ValueError, OverflowError):
                continue
        if metadata_durations == 0:
            try:
                active_provider_durations_ms.append(
                    round(max(0.0, float(metadata.get("provider_attempt_duration_ms") or 0.0)), 3)
                )
            except (TypeError, ValueError, OverflowError):
                pass
    retry_reason = primary_metadata.get("transient_retry_reason")
    retry_categories = [retry_reason] if isinstance(retry_reason, str) else []
    return {
        "case_id": case_id,
        "state": status,
        "security_rejected": bool(security_rejected),
        "public_contract_ok": public_contract_ok,
        "primary_attempt_count": primary_attempts,
        "retry_count": max(0, primary_attempts - 1),
        "repair_count": repair_attempts,
        "provider_call_count": provider_calls,
        "provider_attempt_durations_ms": active_provider_durations_ms[:3],
        "empty_content": bool(primary_metadata.get("empty_content")),
        "finish_reason": str(primary_metadata.get("finish_reason") or "unknown"),
        "length_retry_count": int(retry_reason == "finish_length"),
        "transient_retry_categories": retry_categories,
        "parse_outcome": str(parse_metadata.get("parse_outcome") or primary_metadata.get("parse_outcome") or "invalid"),
        "salvage_action_categories": list(parse_metadata.get("salvage_action_categories") or []),
        "rejected_field_count": min(100, _safe_int(parse_metadata.get("rejected_field_count"))),
        "accepted_field_count": min(32, _safe_int(parse_metadata.get("accepted_field_count"))),
        "fallback_reason": fallback_reason,
        "deadline_exhausted": bool(deadline_exhausted),
        "timeout_categories": list(primary_metadata.get("timeout_categories") or []),
        "provider_error_categories": list(
            primary_metadata.get("provider_error_categories") or []
        ),
        "job_summary": summary_status,
        "match_reasons": reasons_status,
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "total_tokens": tokens["total_tokens"],
        "provider_duration_ms": provider_duration_ms,
        "end_to_end_ms": end_to_end_ms,
    }


def _aggregate(records: list[dict[str, Any]], runtime_settings: Any, safe_logs: bool) -> dict[str, Any]:
    state_counts = {state: sum(record["state"] == state for record in records) for state in (
        "complete", "repaired", "partial", "fallback"
    )}
    finish_reason_counts: dict[str, int] = {}
    retry_categories: dict[str, int] = {}
    parse_outcomes: dict[str, int] = {}
    salvage_categories: dict[str, int] = {}
    fallback_reasons: dict[str, int] = {}
    timeout_categories: dict[str, int] = {}
    provider_error_categories: dict[str, int] = {}
    for record in records:
        finish = record["finish_reason"]
        finish_reason_counts[finish] = finish_reason_counts.get(finish, 0) + 1
        parse = record["parse_outcome"]
        parse_outcomes[parse] = parse_outcomes.get(parse, 0) + 1
        for category in record["transient_retry_categories"]:
            retry_categories[category] = retry_categories.get(category, 0) + 1
        for category in record["salvage_action_categories"]:
            salvage_categories[category] = salvage_categories.get(category, 0) + 1
        if record["fallback_reason"]:
            reason = record["fallback_reason"]
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
        for category in record.get("timeout_categories") or []:
            timeout_categories[category] = timeout_categories.get(category, 0) + 1
        for category in record.get("provider_error_categories") or []:
            provider_error_categories[category] = provider_error_categories.get(category, 0) + 1
    provider_latencies = [record["provider_duration_ms"] for record in records]
    end_to_end_latencies = [record["end_to_end_ms"] for record in records]
    active_provider_latencies = [
        duration
        for record in records
        for duration in record.get("provider_attempt_durations_ms") or []
    ]
    return {
        "candidate_execution_count": len(records),
        **state_counts,
        "security_rejection_count": sum(record["security_rejected"] for record in records),
        "public_contract_failure_count": sum(not record["public_contract_ok"] for record in records),
        "primary_attempt_count": sum(record["primary_attempt_count"] for record in records),
        "retry_count": sum(record["retry_count"] for record in records),
        "repair_count": sum(record["repair_count"] for record in records),
        "maximum_provider_calls": max((record["provider_call_count"] for record in records), default=0),
        "empty_content_count": sum(record["empty_content"] for record in records),
        "finish_reason_counts": finish_reason_counts,
        "length_retry_count": sum(record["length_retry_count"] for record in records),
        "transient_retry_categories": retry_categories,
        "parse_outcome_counts": parse_outcomes,
        "salvage_action_categories": salvage_categories,
        "fallback_reason_categories": fallback_reasons,
        "timeout_categories": timeout_categories,
        "provider_error_categories": provider_error_categories,
        "deadline_exhausted_count": sum(record.get("deadline_exhausted", False) for record in records),
        "job_summary_present_count": sum(record["job_summary"] == "present" for record in records),
        "job_summary_unavailable_count": sum(record["job_summary"] == "explicit_unavailable" for record in records),
        "match_reasons_present_count": sum(record["match_reasons"] == "present" for record in records),
        "match_reasons_unavailable_count": sum(record["match_reasons"] == "explicit_unavailable" for record in records),
        "input_tokens": {
            "min": min((record["input_tokens"] for record in records), default=0),
            "max": max((record["input_tokens"] for record in records), default=0),
            "total": sum(record["input_tokens"] for record in records),
        },
        "output_tokens": {
            "min": min((record["output_tokens"] for record in records), default=0),
            "max": max((record["output_tokens"] for record in records), default=0),
            "total": sum(record["output_tokens"] for record in records),
        },
        "total_tokens": {
            "min": min((record["total_tokens"] for record in records), default=0),
            "max": max((record["total_tokens"] for record in records), default=0),
            "total": sum(record["total_tokens"] for record in records),
        },
        "provider_latency_ms": {
            "median": round(statistics.median(provider_latencies), 3) if provider_latencies else 0.0,
            "p95": _percentile(provider_latencies, 95),
        },
        "end_to_end_latency_ms": {
            "median": round(statistics.median(end_to_end_latencies), 3) if end_to_end_latencies else 0.0,
            "p95": _percentile(end_to_end_latencies, 95),
        },
        "maximum_provider_duration_ms": max(provider_latencies, default=0.0),
        "maximum_end_to_end_duration_ms": max(end_to_end_latencies, default=0.0),
        "maximum_active_provider_operation_lifetime_ms": max(active_provider_latencies, default=0.0),
        "history_finalization": {
            "applicable": False,
            "status": "not_applicable_isolated_runner",
        },
        "idempotency": {
            "applicable": False,
            "status": "not_applicable_isolated_runner",
        },
        "model_id": runtime_settings.deepseek_model,
        "thinking_enabled": bool(runtime_settings.deepseek_thinking_enabled),
        "response_mode": "json_object",
        "primary_output_tokens": runtime_settings.model_max_output_tokens,
        "length_retry_output_tokens": runtime_settings.model_length_retry_output_tokens,
        "repair_output_tokens": runtime_settings.model_repair_output_tokens,
        "maximum_output_tokens": MAX_PROVIDER_OUTPUT_TOKENS,
        "sdk_automatic_retries": 0,
        "safe_log_inspection_passed": bool(safe_logs),
        "case_records": records,
    }


def run(output_path: Path) -> dict[str, Any]:
    runtime_settings = _validate_candidate_environment()
    cases = _load_cases()
    records: list[dict[str, Any]] = []
    with capture_safe_logs() as log_capture:
        for case in cases:
            records.append(_run_case(case, runtime_settings))
        rendered_logs = "\n".join(log_capture.messages).casefold()
    safe_logs = not any(marker.casefold() in rendered_logs for marker in SAFE_LOG_FORBIDDEN_MARKERS)
    summary = _aggregate(records, runtime_settings, safe_logs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.output)
    except CandidateBlocked as exc:
        print(json.dumps({"candidate_blocker": exc.category}, sort_keys=True))
        return 2
    print(json.dumps({
        "candidate_execution_count": summary["candidate_execution_count"],
        "complete": summary["complete"],
        "repaired": summary["repaired"],
        "partial": summary["partial"],
        "fallback": summary["fallback"],
        "security_rejection_count": summary["security_rejection_count"],
        "retry_count": summary["retry_count"],
        "repair_count": summary["repair_count"],
        "maximum_provider_calls": summary["maximum_provider_calls"],
        "deadline_exhausted_count": summary["deadline_exhausted_count"],
        "timeout_categories": summary["timeout_categories"],
        "provider_error_categories": summary["provider_error_categories"],
        "maximum_provider_duration_ms": summary["maximum_provider_duration_ms"],
        "maximum_end_to_end_duration_ms": summary["maximum_end_to_end_duration_ms"],
        "history_finalization": summary["history_finalization"]["status"],
        "idempotency": summary["idempotency"]["status"],
        "safe_log_inspection_passed": summary["safe_log_inspection_passed"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
