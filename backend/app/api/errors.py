"""Stable, privacy-bounded error responses for the Analyze HTTP workflow."""

from __future__ import annotations

from typing import Any, Mapping

from fastapi import Request
from fastapi.responses import JSONResponse

from logging_utils import safe_request_id


ANALYZE_METHOD = "POST"
ANALYZE_PATH = "/api/analyze"
MAX_ERROR_MESSAGE_CHARS = 500
MAX_DETAIL_STRING_CHARS = 500
MAX_WORKFLOW_STEPS = 32
MAX_SECURITY_FINDINGS = 32

ANALYZE_ERROR_CODES = {
    "AUTHENTICATION_REQUIRED",
    "REQUEST_ORIGIN_NOT_TRUSTED",
    "CSRF_VALIDATION_FAILED",
    "REQUEST_TOO_LARGE",
    "REQUEST_VALIDATION_FAILED",
    "RESUME_SOURCE_INVALID",
    "RESUME_NOT_FOUND",
    "RESUME_PARSING_FAILED",
    "JOB_SOURCE_INVALID",
    "JOB_DESCRIPTION_ACQUISITION_FAILED",
    "INPUT_SECURITY_BLOCKED",
    "PROJECT_KNOWLEDGE_RETRIEVAL_FAILED",
    "OUTPUT_SECURITY_BLOCKED",
    "ANALYZE_PERSISTENCE_FAILED",
    "IDEMPOTENCY_KEY_INVALID",
    "IDEMPOTENCY_KEY_REUSED",
    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
    "IDEMPOTENCY_OUTCOME_UNKNOWN",
    "IDEMPOTENCY_PERSISTENCE_FAILED",
    "UNEXPECTED_SERVER_ERROR",
}
SAFE_DETAIL_KEYS = {
    "field",
    "reason",
    "workflow_id",
    "error_stage",
    "retryable",
    "security_finding_category",
    "security_status",
    "security_scan",
    "workflow_status",
    "workflow_steps",
    "workflow_duration_ms",
    "workflow_duration_us",
    "model_metadata",
    "rag_diagnostics",
}
SAFE_MODEL_METADATA_KEYS = {
    "finish_reason",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "response_length",
    "reached_token_limit",
    "latency_ms",
}
SAFE_RAG_DIAGNOSTIC_KEYS = {"retrieval_succeeded", "retrieval_count"}
SAFE_SECURITY_SCAN_KEYS = {
    "policy_version",
    "risk_level",
    "prompt_injection_detected",
    "sensitive_data_detected",
    "pii_redacted",
    "blocked",
    "findings",
    "redaction_summary",
}
SAFE_SECURITY_FINDING_KEYS = {"code", "category", "severity", "source", "message"}
SAFE_REDACTION_KEYS = {
    "email_count",
    "phone_count",
    "address_count",
    "secret_count",
    "private_key_count",
}
SAFE_WORKFLOW_STEP_KEYS = {
    "key",
    "name",
    "status",
    "message",
    "duration_ms",
    "duration_us",
}


def is_analyze_request(request: Request) -> bool:
    return request.method.upper() == ANALYZE_METHOD and request.url.path == ANALYZE_PATH


def request_id_for(request: Request) -> str:
    request_id = getattr(request.state, "request_id", "")
    if not request_id:
        request_id = safe_request_id(None)
        request.state.request_id = request_id
    return str(request_id)


def _bounded_string(value: Any, fallback: str = "") -> str:
    text = str(value or fallback)
    return text[:MAX_DETAIL_STRING_CHARS]


def _safe_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _bounded_string(value)


def _safe_mapping(
    value: Any,
    allowed_keys: set[str],
) -> dict[str, str | int | float | bool | None]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: _safe_scalar(value[key])
        for key in allowed_keys
        if key in value and isinstance(value[key], (str, int, float, bool, type(None)))
    }


def _safe_security_scan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    scan: dict[str, Any] = {
        key: _safe_scalar(value[key])
        for key in SAFE_SECURITY_SCAN_KEYS - {"findings", "redaction_summary"}
        if key in value and isinstance(value[key], (str, int, float, bool, type(None)))
    }
    findings = value.get("findings")
    if isinstance(findings, list):
        scan["findings"] = [
            _safe_mapping(item, SAFE_SECURITY_FINDING_KEYS)
            for item in findings[:MAX_SECURITY_FINDINGS]
            if isinstance(item, Mapping)
        ]
    summary = value.get("redaction_summary")
    if isinstance(summary, Mapping):
        scan["redaction_summary"] = _safe_mapping(summary, SAFE_REDACTION_KEYS)
    return scan


def _safe_workflow_steps(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        _safe_mapping(item, SAFE_WORKFLOW_STEP_KEYS)
        for item in value[:MAX_WORKFLOW_STEPS]
        if isinstance(item, Mapping)
    ]


def safe_analyze_details(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    details: dict[str, Any] = {}
    for key in SAFE_DETAIL_KEYS:
        if key not in value:
            continue
        item = value[key]
        if key == "security_scan":
            details[key] = _safe_security_scan(item)
        elif key == "workflow_steps":
            details[key] = _safe_workflow_steps(item)
        elif key == "model_metadata":
            details[key] = _safe_mapping(item, SAFE_MODEL_METADATA_KEYS)
        elif key == "rag_diagnostics":
            details[key] = _safe_mapping(item, SAFE_RAG_DIAGNOSTIC_KEYS)
        elif isinstance(item, (str, int, float, bool, type(None))):
            details[key] = _safe_scalar(item)
    return details


def analyze_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    error_stage: str = "",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_for(request)
    safe_code = _bounded_string(code or "UNEXPECTED_SERVER_ERROR")[:80]
    if safe_code not in ANALYZE_ERROR_CODES:
        safe_code = "UNEXPECTED_SERVER_ERROR"
        message = "Unexpected server error. Please try again."
    safe_message = _bounded_string(message or "The request could not be processed.")[
        :MAX_ERROR_MESSAGE_CHARS
    ]
    safe_details = safe_analyze_details(details or {})
    request.state.error_code = safe_code
    request.state.error_stage = _bounded_string(
        error_stage or safe_details.get("error_stage") or ""
    )[:80]
    response_headers = dict(headers or {})
    response_headers.setdefault("X-Request-ID", request_id)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": safe_code,
                "message": safe_message,
                "request_id": request_id,
                "details": safe_details,
            }
        },
        headers=response_headers,
    )


def route_error_response(
    request: Request,
    *,
    status_code: int,
    legacy_message: str,
    analyze_code: str,
    analyze_message: str | None = None,
    details: Mapping[str, Any] | None = None,
    error_stage: str = "",
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    if is_analyze_request(request):
        return analyze_error_response(
            request,
            status_code=status_code,
            code=analyze_code,
            message=analyze_message or legacy_message,
            details=details,
            error_stage=error_stage,
            headers=headers,
        )
    return JSONResponse(
        status_code=status_code,
        content={"detail": legacy_message},
        headers=dict(headers or {}),
    )


def analyze_exception_response(
    request: Request,
    *,
    status_code: int,
    detail: Any,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    if isinstance(detail, Mapping):
        code = str(detail.get("error_code") or "REQUEST_VALIDATION_FAILED")
        message = str(detail.get("message") or "The request could not be processed.")
        error_stage = str(detail.get("error_stage") or "")
        detail_source = {
            key: value
            for key, value in detail.items()
            if key not in {"error_code", "message", "details"}
        }
        nested_details = detail.get("details")
        if isinstance(nested_details, Mapping):
            detail_source.update(nested_details)
    else:
        code = "UNEXPECTED_SERVER_ERROR" if status_code >= 500 else "REQUEST_VALIDATION_FAILED"
        message = str(detail or "The request could not be processed.")
        error_stage = ""
        detail_source = {}
    return analyze_error_response(
        request,
        status_code=status_code,
        code=code,
        message=message,
        details=detail_source,
        error_stage=error_stage,
        headers=headers,
    )
