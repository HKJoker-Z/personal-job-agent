#!/usr/bin/env python3
"""Collect a five-run production-equivalent Analyze release-gate sample.

This is operations tooling, not application runtime code.  It uses a dedicated
test account, normal HTTPS authentication, RAG, History, monitoring, Java, and
PostgreSQL-backed APIs.  Response bodies and credentials are never written to
the evidence report.  Bounded raw container logs are retained mode 0600 for
diagnosis, especially if a public connection closes without a response.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import secrets
import ssl
import subprocess
import time
from dataclasses import asdict
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

try:
    from ops.release_gate.analyze_gate import RUN_COUNT, evaluate
except ModuleNotFoundError:  # Direct execution from this directory.
    from analyze_gate import RUN_COUNT, evaluate


ALLOWED_ANALYSIS_STATES = {"complete", "repaired", "partial", "fallback"}
ERROR_PATTERN = re.compile(
    r"connection reset|broken pipe|premature(?:ly)? close|upstream timed out|"
    r"empty reply|traceback|\bfatal\b|\bpanic\b|\boom\b|uncaught|\bcritical\b",
    re.IGNORECASE,
)


class CollectionFailure(RuntimeError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def rfc3339(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def read_secret(path: Path) -> str:
    mode = path.stat().st_mode & 0o777
    if mode & 0o077:
        raise CollectionFailure("password_file_permissions_not_0600")
    value = path.read_text(encoding="utf-8").strip("\r\n")
    if not value:
        raise CollectionFailure("password_file_empty")
    return value


def multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"pja_release_gate_{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class PublicClient:
    def __init__(self, base_url: str, origin: str, ca_file: Path | None, timeout: float):
        context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        self.opener = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(CookieJar()))
        self.base_url = base_url.rstrip("/")
        self.origin = origin
        self.timeout = timeout
        self.csrf = ""

    def call(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        request_id: str,
        idempotency_key: str | None = None,
    ) -> tuple[int | None, bytes, dict[str, str], str | None]:
        headers = {
            "Accept": "application/json",
            "Origin": self.origin,
            "User-Agent": "PJA-production-equivalent-release-gate/1",
            "X-Request-ID": request_id,
        }
        if self.csrf and method not in {"GET", "HEAD"}:
            headers["X-CSRF-Token"] = self.csrf
        if content_type:
            headers["Content-Type"] = content_type
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return response.status, response.read(), dict(response.headers.items()), None
        except HTTPError as error:
            return error.code, error.read(), dict(error.headers.items()), None
        except http.client.RemoteDisconnected:
            return None, b"", {}, "empty_reply"
        except (URLError, TimeoutError, ssl.SSLError, ConnectionError, OSError) as error:
            message = str(error).lower()
            category = (
                "empty_reply"
                if "remote end closed" in message or "empty reply" in message
                else "connection_failure"
            )
            return None, b"", {}, category

    def json_call(
        self,
        path: str,
        *,
        method: str = "GET",
        value: object | None = None,
        request_id: str,
    ) -> tuple[int | None, object | None, bytes, dict[str, str], str | None]:
        body = None
        content_type = None
        if value is not None:
            body = json.dumps(value, separators=(",", ":")).encode()
            content_type = "application/json"
        status, raw, headers, error = self.call(
            path,
            method=method,
            body=body,
            content_type=content_type,
            request_id=request_id,
        )
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return status, parsed, raw, headers, error


def docker_logs(container: str, start: dt.datetime, end: dt.datetime) -> tuple[bool, str]:
    process = subprocess.run(
        [
            "docker",
            "logs",
            "--since",
            rfc3339(start),
            "--until",
            rfc3339(end),
            container,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return process.returncode == 0, process.stdout


def json_lines(raw: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def matching(values: list[dict[str, Any]], request_id: str, message: str) -> list[dict[str, Any]]:
    return [
        value
        for value in values
        if str(value.get("request_id") or "") == request_id
        and str(value.get("message") or "") == message
    ]


def response_is_complete(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = {
        "analysis_status",
        "application_id",
        "saved_to_history",
        "workflow_id",
        "workflow_duration_ms",
        "workflow_steps",
        "used_knowledge_base",
        "retrieval_count",
        "rag_sources",
        "analysis_warnings",
        "scoring_breakdown",
        "security_status",
    }
    return required.issubset(value)


def output_is_correct(value: object) -> bool:
    if not response_is_complete(value):
        return False
    assert isinstance(value, dict)
    return bool(
        value.get("analysis_status") in ALLOWED_ANALYSIS_STATES
        and isinstance(value.get("application_id"), int)
        and value.get("saved_to_history") is True
        and isinstance(value.get("workflow_id"), str)
        and value.get("workflow_id")
        and isinstance(value.get("workflow_duration_ms"), (int, float))
        and value.get("used_knowledge_base") is True
        and isinstance(value.get("retrieval_count"), int)
        and value.get("retrieval_count") > 0
        and isinstance(value.get("rag_sources"), list)
        and value.get("rag_sources")
        and isinstance(value.get("analysis_warnings"), list)
        and isinstance(value.get("scoring_breakdown"), dict)
        and isinstance(value.get("workflow_steps"), list)
        and value.get("workflow_steps")
    )


def safe_request_id(prefix: str, label: str) -> str:
    value = f"{prefix}-{label}-{secrets.token_hex(6)}"
    if len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value):
        raise CollectionFailure("request_prefix_invalid")
    return value


def require_json_success(
    client: PublicClient,
    path: str,
    *,
    method: str,
    value: object | None,
    request_id: str,
) -> dict[str, Any]:
    status, parsed, _raw, _headers, error = client.json_call(
        path, method=method, value=value, request_id=request_id
    )
    if error or not isinstance(status, int) or not 200 <= status < 300 or not isinstance(parsed, dict):
        raise CollectionFailure(f"setup_request_failed:{path}")
    return parsed


def collect(args: argparse.Namespace) -> dict[str, Any]:
    hard_gates = json.loads(args.hard_gates.read_text(encoding="utf-8"))
    if not isinstance(hard_gates, dict):
        raise CollectionFailure("hard_gates_not_object")
    resume_content = json.loads(args.resume_file.read_text(encoding="utf-8"))
    job_text = args.job_file.read_text(encoding="utf-8")
    if not isinstance(resume_content, dict) or not 1_500 <= len(json.dumps(resume_content)) <= 30_000:
        raise CollectionFailure("resume_fixture_not_production_equivalent_length")
    if not 1_500 <= len(job_text) <= 20_000:
        raise CollectionFailure("job_fixture_not_production_equivalent_length")

    password = read_secret(args.password_file)
    client = PublicClient(args.base_url, args.origin, args.ca_file, args.timeout)
    prefix = args.request_prefix

    login = require_json_success(
        client,
        "/api/auth/login",
        method="POST",
        value={"email": args.email, "password": password, "remember_me": False},
        request_id=safe_request_id(prefix, "login"),
    )
    password = ""
    csrf = login.get("csrf_token")
    if login.get("authenticated") is not True or not isinstance(csrf, str) or not csrf:
        raise CollectionFailure("authentication_contract_failed")
    client.csrf = csrf

    resume = require_json_success(
        client,
        "/api/resumes",
        method="POST",
        value={
            "title": "Isolated release acceptance resume",
            "language": "en",
            "target_role": "Senior Platform Engineer",
        },
        request_id=safe_request_id(prefix, "resume"),
    )
    resume_id = str(resume.get("id") or "")
    version = require_json_success(
        client,
        f"/api/resumes/{resume_id}/versions",
        method="POST",
        value={"content": resume_content, "change_summary": "Release acceptance fixture"},
        request_id=safe_request_id(prefix, "version"),
    )
    version_id = str(version.get("id") or "")
    require_json_success(
        client,
        f"/api/resumes/{resume_id}/versions/{version_id}/finalize",
        method="POST",
        value=None,
        request_id=safe_request_id(prefix, "finalize"),
    )
    require_json_success(
        client,
        "/api/project-knowledge/rebuild",
        method="POST",
        value=None,
        request_id=safe_request_id(prefix, "rag"),
    )

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "started_at": rfc3339(utc_now()),
        "base_url": args.base_url,
        "production_equivalent": {
            "public_https": True,
            "authentication": True,
            "rag": True,
            "history": True,
            "metrics": True,
            "java": True,
            "postgresql_persistence": True,
            "production_length_fixtures": True,
        },
        "hard_gates": hard_gates,
        "runs": [],
        "warnings": [],
        "test_resources": {"resume_id": resume_id, "resume_version_id": version_id},
    }
    atomic_json(args.output, evidence)

    containers = {
        "edge": args.edge_container,
        "frontend": args.frontend_container,
        "backend": args.backend_container,
        "java": args.java_container,
    }
    error_run_indexes: list[int] = []
    for index in range(1, RUN_COUNT + 1):
        request_id = safe_request_id(prefix, f"analyze{index}")
        idempotency_key = f"release-gate-{secrets.token_urlsafe(32)}"
        body, content_type = multipart(
            {
                "resume_version_id": version_id,
                "job_text": job_text,
                "save_to_history": "true",
                "use_project_knowledge": "true",
                "project_knowledge_top_k": "5",
            }
        )
        started = utc_now()
        start_monotonic = time.monotonic()
        status, raw, headers, transport_error = client.call(
            "/api/analyze",
            method="POST",
            body=body,
            content_type=content_type,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        duration_ms = round((time.monotonic() - start_monotonic) * 1000, 3)
        ended = utc_now()
        try:
            response: object = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            response = None

        time.sleep(0.25)
        log_end = utc_now()
        log_scan: dict[str, bool] = {}
        raw_logs: dict[str, str] = {}
        for layer, container in containers.items():
            scanned, log_value = docker_logs(container, started - dt.timedelta(seconds=1), log_end)
            log_scan[layer] = scanned
            raw_logs[layer] = log_value
            destination = args.artifact_dir / f"run-{index}-{request_id}-{layer}.log"
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_text(log_value, encoding="utf-8")
            os.chmod(destination, 0o600)

        backend_values = json_lines(raw_logs["backend"])
        normalization = matching(
            backend_values, request_id, "jd_normalization_execution_observation"
        )
        backend_completed = matching(backend_values, request_id, "http_request_completed")
        backend_completed = [
            value for value in backend_completed if value.get("route") == "/api/analyze"
        ]
        observation = normalization[-1] if len(normalization) == 1 else {}
        completion = backend_completed[-1] if len(backend_completed) == 1 else {}

        java_values = json_lines(raw_logs["java"])
        java_completed = matching(java_values, request_id, "http_request_completed")
        java_completed = [
            value
            for value in java_completed
            if "normalize" in str(value.get("route") or "")
        ]

        relevant_errors = [
            layer for layer, log_value in raw_logs.items() if ERROR_PATTERN.search(log_value)
        ]
        if relevant_errors:
            error_run_indexes.append(index - 1)

        response_headers = {str(key).lower(): str(value) for key, value in headers.items()}
        response_request_id = response_headers.get("x-request-id")
        complete = response_is_complete(response)
        correct = output_is_correct(response)
        workflow_id = response.get("workflow_id") if isinstance(response, dict) else None
        history_id = response.get("application_id") if isinstance(response, dict) else None

        history_persisted = False
        metrics_persisted = False
        if isinstance(history_id, int):
            history_status, history_value, *_ = client.json_call(
                f"/api/history/{history_id}",
                request_id=safe_request_id(prefix, f"history{index}"),
            )
            history_persisted = bool(
                history_status == 200
                and isinstance(history_value, dict)
                and history_value.get("id") == history_id
            )
        if isinstance(workflow_id, str) and workflow_id:
            metric_status, metric_value, *_ = client.json_call(
                f"/api/monitoring/traces/{workflow_id}",
                request_id=safe_request_id(prefix, f"metrics{index}"),
            )
            metrics_persisted = bool(metric_status == 200 and isinstance(metric_value, dict))

        warnings: list[str] = []
        java_duration = observation.get("duration_ms")
        if isinstance(java_duration, (int, float)) and java_duration >= args.latency_warning_ms:
            warnings.append("single_java_latency_spike")
        if relevant_errors and status is not None and 200 <= status < 300:
            warnings.append("transient_runtime_warning_recovered")

        run = {
            "request_id": request_id,
            "timestamp_started": rfc3339(started),
            "timestamp_completed": rfc3339(ended),
            "public_https": args.base_url.lower().startswith("https://"),
            "http_status": status,
            "backend_final_status": completion.get("status_code"),
            "transport_error": transport_error,
            "empty_reply": transport_error == "empty_reply",
            "connection_failure": transport_error not in (None, "", "empty_reply"),
            "response_bytes": len(raw),
            "response_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "response_request_id_matches": response_request_id == request_id,
            "response_complete": complete,
            "output_correct": correct and response_request_id == request_id,
            "end_to_end_duration_ms": duration_ms,
            "java_duration_ms": java_duration,
            "java_fallback": observation.get("fallback") is True,
            "java_outcome": observation.get("normalization_outcome"),
            "fallback_result_correct": (
                correct if observation.get("fallback") is True else True
            ),
            "java_observation_present": len(normalization) == 1,
            "java_http_status": (
                java_completed[-1].get("status") if len(java_completed) == 1 else None
            ),
            "rag_enabled": bool(
                isinstance(response, dict)
                and response.get("used_knowledge_base") is True
                and int(response.get("retrieval_count") or 0) > 0
            ),
            "history_persisted": history_persisted,
            "metrics_persisted": metrics_persisted,
            "edge_log_scanned": log_scan["edge"],
            "frontend_log_scanned": log_scan["frontend"],
            "backend_log_scanned": log_scan["backend"],
            "java_log_scanned": log_scan["java"],
            "relevant_errors": relevant_errors,
            "persistent_runtime_error": False,
            "warnings": warnings,
        }
        evidence["runs"].append(run)
        atomic_json(args.output, evidence)

        # Preserve all evidence and stop immediately on a public availability
        # hard failure.  The evaluator will classify the partial group HARD_FAIL.
        if transport_error or not isinstance(status, int) or not 200 <= status < 300 or not complete:
            break

    if len(error_run_indexes) >= 2:
        for index in error_run_indexes:
            evidence["runs"][index]["persistent_runtime_error"] = True

    evidence["completed_at"] = rfc3339(utc_now())
    result = evaluate(evidence)
    evidence["gate_result"] = asdict(result)
    atomic_json(args.output, evidence)
    return evidence


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--base-url", required=True)
    value.add_argument("--origin", required=True)
    value.add_argument("--email", required=True)
    value.add_argument("--password-file", type=Path, required=True)
    value.add_argument("--ca-file", type=Path)
    value.add_argument("--resume-file", type=Path, required=True)
    value.add_argument("--job-file", type=Path, required=True)
    value.add_argument("--hard-gates", type=Path, required=True)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--artifact-dir", type=Path, required=True)
    value.add_argument("--request-prefix", required=True)
    value.add_argument("--backend-container", required=True)
    value.add_argument("--java-container", required=True)
    value.add_argument("--frontend-container", required=True)
    value.add_argument("--edge-container", required=True)
    value.add_argument("--timeout", type=float, default=240.0)
    value.add_argument("--latency-warning-ms", type=float, default=500.0)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        evidence = collect(args)
    except Exception as error:
        failure = {
            "schema_version": 1,
            "collection_failure": type(error).__name__,
            "failure_code": str(error) if isinstance(error, CollectionFailure) else "unexpected_collection_error",
            "runs": [],
            "hard_gates": {},
        }
        atomic_json(args.output, failure)
        print(json.dumps(failure, sort_keys=True))
        return 2
    result = evidence["gate_result"]
    print(json.dumps(result, sort_keys=True))
    if result["verdict"] == "HARD_FAIL":
        return 2
    if result["verdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
