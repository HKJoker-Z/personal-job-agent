"""Manual-only, metadata-only authenticated DeepSeek transport attribution.

The four levels intentionally make one tiny request ten times each.  The
runner keeps response bodies in memory only long enough to check the bounded
JSON shape and writes aggregate metadata without content, exception text,
headers, URLs with credentials, or request data.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import subprocess
import statistics
import sys
import time
from typing import Any, Callable, Iterator

import httpx
from dotenv import load_dotenv
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import load_config  # noqa: E402
from deepseek_client import DEEPSEEK_BASE_URL, build_deepseek_client  # noqa: E402
from provider_deadline import ProviderDeadline  # noqa: E402
from provider_errors import (  # noqa: E402
    COMPONENT_TIMEOUT_CATEGORIES,
    classify_provider_exception,
    safe_exception_class_names,
)


ATTEMPTS_PER_LEVEL = 10
MATRIX_DEADLINE_SECONDS = 130
TINY_MAX_TOKENS = 32
MATRIX_PROMPT = "Return exactly one JSON object with the boolean field ok set to true."
MATRIX_SYSTEM = "Return JSON only. Do not include Markdown or prose outside the object."
LEVELS = ("A_raw_https", "B_plain_httpx", "C_sdk_plain_httpx", "D_production_client")
SAFE_CURL_FAILURE_CODES = {
    7: "connect_error",
    28: "bounded_curl_timeout",
    35: "tls_or_connect_error",
    52: "transport_error_other",
    55: "write_error",
    56: "read_error",
}


class AttributionBlocked(RuntimeError):
    """A safe manual-run stop that contains no secret or provider content."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _body_bucket(size: int) -> str:
    if size <= 0:
        return "empty"
    if size <= 256:
        return "small"
    if size <= 4096:
        return "medium"
    return "large"


def _status_category(status: int | None) -> str:
    if status is None:
        return "none"
    if 200 <= status <= 299:
        return "2xx"
    if 400 <= status <= 499:
        return "4xx"
    if 500 <= status <= 599:
        return "5xx"
    return "other"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(
        0,
        min(
            len(ordered) - 1,
            int((percentile / 100) * len(ordered) + 0.999999) - 1,
        ),
    )
    return round(ordered[index], 3)


def _request_body(runtime_settings: Any) -> dict[str, Any]:
    if runtime_settings.deepseek_thinking_enabled:
        raise AttributionBlocked("thinking_must_be_disabled")
    return {
        "model": runtime_settings.deepseek_model,
        "response_format": {"type": "json_object"},
        "max_tokens": TINY_MAX_TOKENS,
        "temperature": 0.2,
        # This is the wire representation.  The SDK receives the equivalent
        # value through its ``extra_body`` keyword below.
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": MATRIX_SYSTEM},
            {"role": "user", "content": MATRIX_PROMPT},
        ],
    }


def _request_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _content_shape(content: Any) -> tuple[bool, int]:
    if not isinstance(content, str):
        return False, 0
    encoded_size = len(content.encode("utf-8"))
    try:
        decoded = json.loads(content)
    except (TypeError, ValueError, UnicodeError):
        return False, encoded_size
    return isinstance(decoded, dict) and decoded.get("ok") is True, encoded_size


def _http_completion_shape(body: bytes) -> tuple[bool, int]:
    body_size = len(body)
    try:
        payload = json.loads(body)
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError):
        return False, body_size
    valid, _content_size = _content_shape(content)
    return valid, body_size


def _openai_completion_shape(completion: Any) -> tuple[bool, int]:
    try:
        content = completion.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return False, 0
    return _content_shape(content)


def _timeout_for(runtime_settings: Any) -> tuple[ProviderDeadline, Any]:
    deadline = ProviderDeadline.for_phase(
        phase_started_monotonic=time.monotonic(),
        configured_deadline_seconds=MATRIX_DEADLINE_SECONDS,
    )
    timeout = deadline.call_timeout(
        configured_timeout_seconds=runtime_settings.request_timeout_seconds,
        kind="primary",
    )
    if timeout is None:
        raise AttributionBlocked("provider_deadline_has_no_safe_call_budget")
    return deadline, timeout


def _new_record() -> dict[str, Any]:
    return {
        "success": False,
        "http_success": False,
        "expected_json_shape": False,
        "failure_category": None,
        "timeout_category": None,
        "status_category": "none",
        "body_size_bucket": "empty",
        "duration_ms": 0.0,
        "exception_classes": [],
        "cleanup_categories": [],
    }


def _record_exception(record: dict[str, Any], exc: BaseException) -> None:
    category = classify_provider_exception(exc)
    record["failure_category"] = category
    if category in COMPONENT_TIMEOUT_CATEGORIES or category.endswith("deadline_exhausted"):
        record["timeout_category"] = category
    record["exception_classes"] = safe_exception_class_names(exc)


def _close_safely(record: dict[str, Any], close: Callable[[], Any] | None) -> None:
    if close is None:
        return
    try:
        close()
    except BaseException as exc:
        record["cleanup_categories"] = [classify_provider_exception(exc)]


def _plain_httpx_request(runtime_settings: Any) -> dict[str, Any]:
    record = _new_record()
    record["direct_transport"] = True
    body = _request_body(runtime_settings)
    _deadline, timeout = _timeout_for(runtime_settings)
    client: httpx.Client | None = None
    started = time.perf_counter()
    try:
        client = httpx.Client(
            trust_env=False,
            verify=True,
            timeout=timeout.timeout,
        )
        response = client.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers=_request_headers(runtime_settings.deepseek_api_key),
            json=body,
        )
        response_body = response.content
        record["http_success"] = response.is_success
        record["status_category"] = _status_category(response.status_code)
        record["body_size_bucket"] = _body_bucket(len(response_body))
        record["expected_json_shape"], _content_size = _http_completion_shape(response_body)
        record["success"] = record["http_success"] and record["expected_json_shape"]
        if not record["success"]:
            record["failure_category"] = (
                f"http_status_{record['status_category']}"
                if not record["http_success"]
                else "completion_shape_invalid"
            )
        response.close()
    except BaseException as exc:
        _record_exception(record, exc)
    finally:
        _close_safely(record, client.close if client is not None else None)
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return record


def _sdk_request(
    runtime_settings: Any,
    *,
    production_client: bool,
    request_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _new_record()
    body = request_body or _request_body(runtime_settings)
    client: Any | None = None
    http_client: Any | None = None
    started = time.perf_counter()
    try:
        deadline, timeout = _timeout_for(runtime_settings)
        if production_client:
            client, http_client, _effective_timeout = build_deepseek_client(
                runtime_settings,
                deadline=deadline,
                kind="primary",
            )
            record["direct_transport"] = getattr(http_client, "_trust_env", None) is False
        else:
            http_client = httpx.Client(
                trust_env=False,
                verify=True,
                timeout=timeout.timeout,
            )
            client = OpenAI(
                api_key=runtime_settings.deepseek_api_key,
                base_url=DEEPSEEK_BASE_URL,
                timeout=timeout.timeout,
                max_retries=0,
                http_client=http_client,
            )
            record["direct_transport"] = getattr(http_client, "_trust_env", None) is False
        sdk_body = dict(body)
        thinking = sdk_body.pop("thinking")
        completion = client.chat.completions.create(
            **sdk_body,
            extra_body={"thinking": thinking},
        )
        record["http_success"] = True
        record["status_category"] = "2xx"
        record["expected_json_shape"], content_size = _openai_completion_shape(completion)
        record["body_size_bucket"] = _body_bucket(content_size)
        record["success"] = record["expected_json_shape"]
        if not record["success"]:
            record["failure_category"] = "completion_shape_invalid"
    except BaseException as exc:
        _record_exception(record, exc)
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            record["status_category"] = _status_category(status)
    finally:
        _close_safely(record, client.close if client is not None else None)
        if http_client is not None and http_client is not client:
            _close_safely(record, http_client.close)
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return record


def _curl_config(api_key: str, body: dict[str, Any], timeout_seconds: float) -> bytes:
    body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    lines = [
        f"url = {json.dumps(f'{DEEPSEEK_BASE_URL}/chat/completions')}",
        "request = POST",
        f"header = {json.dumps(f'Authorization: Bearer {api_key}')}",
        "header = \"Content-Type: application/json\"",
        f"data = {json.dumps(body_text)}",
        "noproxy = \"*\"",
        "connect-timeout = \"5\"",
        f"max-time = {json.dumps(str(max(5, int(timeout_seconds)) ))}",
        "silent",
        "show-error",
        "write-out = \"PJA_STATUS:%{http_code}\"",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _curl_request(runtime_settings: Any) -> dict[str, Any]:
    record = _new_record()
    record["direct_transport"] = True
    body = _request_body(runtime_settings)
    _deadline, timeout = _timeout_for(runtime_settings)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            ["curl", "--config", "-"],
            input=_curl_config(runtime_settings.deepseek_api_key, body, timeout.budget_seconds),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=max(5.0, timeout.budget_seconds + 2.0),
            check=False,
        )
        marker = b"PJA_STATUS:"
        output = completed.stdout
        marker_index = output.rfind(marker)
        if marker_index >= 0:
            response_body = output[:marker_index]
            try:
                status = int(output[marker_index + len(marker):].strip() or b"0")
            except ValueError:
                status = None
        else:
            response_body = b""
            status = None
        record["http_success"] = status is not None and 200 <= status <= 299
        record["status_category"] = _status_category(status)
        record["body_size_bucket"] = _body_bucket(len(response_body))
        if record["http_success"]:
            record["expected_json_shape"], _content_size = _http_completion_shape(response_body)
            record["success"] = record["expected_json_shape"]
        if not record["success"]:
            if completed.returncode in SAFE_CURL_FAILURE_CODES:
                record["failure_category"] = SAFE_CURL_FAILURE_CODES[completed.returncode]
            elif not record["http_success"]:
                record["failure_category"] = f"http_status_{record['status_category']}"
            else:
                record["failure_category"] = "completion_shape_invalid"
    except subprocess.TimeoutExpired:
        record["failure_category"] = "bounded_curl_timeout"
        record["timeout_category"] = "bounded_curl_timeout"
    except OSError:
        record["failure_category"] = "transport_error_other"
    finally:
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return record


def _summarize_records(name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    failures = Counter(
        record["failure_category"]
        for record in records
        if not record["success"] and record["failure_category"]
    )
    timeouts = Counter(
        record["timeout_category"]
        for record in records
        if record["timeout_category"]
    )
    cleanup = Counter(
        category
        for record in records
        for category in record["cleanup_categories"]
    )
    durations = [record["duration_ms"] for record in records]
    return {
        "attempts": len(records),
        "http_success_count": sum(record["http_success"] for record in records),
        "completion_success_count": sum(record["success"] for record in records),
        "failure_count": sum(not record["success"] for record in records),
        "failure_categories": dict(sorted(failures.items())),
        "timeout_categories": dict(sorted(timeouts.items())),
        "cleanup_categories": dict(sorted(cleanup.items())),
        "duration_ms": {
            "median": round(statistics.median(durations), 3) if durations else 0.0,
            "p95": _percentile(durations, 95),
            "max": round(max(durations), 3) if durations else 0.0,
        },
        "direct_transport_used": name == "A_raw_https" or all(
            record.get("direct_transport") is True for record in records
        ),
        "expected_json_shape_completion_count": sum(
            record["expected_json_shape"] for record in records
        ),
        "body_size_buckets": dict(
            sorted(Counter(record["body_size_bucket"] for record in records).items())
        ),
        "status_categories": dict(
            sorted(Counter(record["status_category"] for record in records).items())
        ),
        "exception_classes": dict(
            sorted(
                Counter(
                    class_name
                    for record in records
                    for class_name in record["exception_classes"]
                ).items()
            )
        ),
    }


def _run_level(name: str, runtime_settings: Any) -> dict[str, Any]:
    request = {
        "A_raw_https": _curl_request,
        "B_plain_httpx": _plain_httpx_request,
        "C_sdk_plain_httpx": lambda settings: _sdk_request(settings, production_client=False),
        "D_production_client": lambda settings: _sdk_request(settings, production_client=True),
    }[name]
    records = [request(runtime_settings) for _index in range(ATTEMPTS_PER_LEVEL)]
    return _summarize_records(name, records)


def _realistic_request_body(runtime_settings: Any) -> dict[str, Any]:
    fixture_path = BACKEND_DIR / "fixtures" / "deepseek_provider_real_candidate_v1" / "cases.json"
    with fixture_path.open(encoding="utf-8") as fixture:
        cases = json.load(fixture)
    if not isinstance(cases, list) or not cases or not isinstance(cases[0], dict):
        raise AttributionBlocked("synthetic_fixture_unavailable")
    case = cases[0]
    from legacy_application import build_safe_analysis_prompt

    prompt = build_safe_analysis_prompt(
        resume_text=str(case.get("resume") or ""),
        job_description=str(case.get("job_description") or ""),
        rag_chunks=case.get("project_knowledge") if isinstance(case.get("project_knowledge"), list) else [],
    )
    return {
        "model": runtime_settings.deepseek_model,
        "response_format": {"type": "json_object"},
        "max_tokens": runtime_settings.model_max_output_tokens,
        "temperature": 0.2,
        "thinking": {"type": "disabled"},
        "messages": [
            {"role": "system", "content": MATRIX_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }


def _run_realistic_control(runtime_settings: Any) -> dict[str, Any]:
    body = _realistic_request_body(runtime_settings)
    levels: dict[str, dict[str, Any]] = {}
    for name, production_client in (("C_sdk_plain_httpx", False), ("D_production_client", True)):
        records = [
            _sdk_request(
                runtime_settings,
                production_client=production_client,
                request_body=body,
            )
            for _index in range(5)
        ]
        levels[name] = _summarize_records(name, records)
    return {
        "attempts_per_level": 5,
        "fixture": "deepseek_provider_real_candidate_v1/cases.json:first_case",
        "resume_job_data_stored": False,
        "max_tokens": runtime_settings.model_max_output_tokens,
        "levels": levels,
    }


@contextmanager
def _quiet_logging() -> Iterator[None]:
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def _validate_environment() -> Any:
    if os.getenv("PJA_REAL_DEEPSEEK_ATTRIBUTION") != "1":
        raise AttributionBlocked("manual_opt_in_required")
    if (os.getenv("APP_ENV", "development").strip().lower() or "development") == "production":
        raise AttributionBlocked("production_environment_forbidden")
    runtime_settings = load_config(validate_production=False)
    if runtime_settings.deepseek_network_mode != "direct":
        raise AttributionBlocked("direct_network_mode_required")
    if runtime_settings.deepseek_thinking_enabled:
        raise AttributionBlocked("thinking_must_be_disabled")
    if not runtime_settings.deepseek_api_key:
        raise AttributionBlocked("approved_deepseek_secret_unavailable")
    if not runtime_settings.deepseek_model.strip():
        raise AttributionBlocked("model_configuration_blank")
    return runtime_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--realistic-control", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT_DIR / ".env")
    try:
        runtime_settings = _validate_environment()
        with _quiet_logging():
            levels = (
                _run_realistic_control(runtime_settings)
                if args.realistic_control
                else {name: _run_level(name, runtime_settings) for name in LEVELS}
            )
    except AttributionBlocked as exc:
        print(json.dumps({"attribution_blocker": exc.category}, sort_keys=True))
        return 2
    output = {
        "schema": "deepseek-authenticated-transport-attribution-v1",
        "levels": levels,
        "request": {
            "model_configured": True,
            "thinking_enabled": False,
            "response_mode": "json_object",
            "max_tokens": TINY_MAX_TOKENS,
            "attempts_per_level": ATTEMPTS_PER_LEVEL,
            "direct_transport_required": True,
            "configured_connect_timeout_seconds": 5.0,
            "configured_request_timeout_seconds": runtime_settings.request_timeout_seconds,
            "provider_deadline_seconds": MATRIX_DEADLINE_SECONDS,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"levels": list(levels), "output_written": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
