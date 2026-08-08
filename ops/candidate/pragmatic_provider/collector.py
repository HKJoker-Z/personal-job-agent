"""Bounded production-candidate evidence collection.

This module is deliberately outside the application import path.  It owns the
caller idempotency key before the first request, performs one completed replay,
and retains only bounded hard-gate observations.  It never logs request
content, Provider content, credentials, or raw exception text.

The default command-line path is an explicitly invoked production operation.
The test suite injects HTTP, log, and database observers, so it never calls a
real Provider or network endpoint.
"""

from __future__ import annotations

import argparse
import datetime as dt
import getpass
import hashlib
import html
import io
import json
import logging
import secrets
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPCookieProcessor,
    HTTPSHandler,
    Request,
    build_opener,
)
from http.cookiejar import CookieJar
import ssl


LOGGER = logging.getLogger("pja.candidate.collector")

SUPPORTED_STATES = frozenset({"complete", "repaired", "partial", "fallback"})
MAX_PROVIDER_CALLS = 3
ANALYZE_SAFETY_DEADLINE_MS = 175_000.0
IDEMPOTENCY_OPERATION = "analyze:v1"
IDEMPOTENCY_KEY_DOMAIN = b"personal-job-agent:analyze:idempotency-key:v1\x00"

# These are the immutable values recorded by the previous production-candidate
# report.  The command refuses supplemental execution when any runtime value
# differs, so old evidence is never silently treated as current evidence.
EXPECTED_SOURCE_REVISION = "7b834dd469892d2798661dca14f2f906e7b339cf"
EXPECTED_BACKEND_DIGEST = (
    "sha256:6bf10ee441ff50db693dfec31e6c2cdfac353d3e3bf62be59733aeb210adb1fa"
)
EXPECTED_FRONTEND_DIGEST = (
    "sha256:70df317280ad5acd5e2916a0de65844b1add1bb54636cdeec1f793c8c93b174b"
)
EXPECTED_JAVA_DIGEST = (
    "sha256:57e3e68c96ca629e4216e4cb19d55c0d9a52ad9bfb2d49c289fdc94f61f0d47f"
)
EXPECTED_PUBLIC_VERSION = "2.0.5"
EXPECTED_ALEMBIC_REVISION = "20260730_07"
EXPECTED_JD_MODE = "java"
EXPECTED_JD_POLICY = "jd-normalization-v1"
EXPECTED_SKILL_DICTIONARY = "skills-v1"


class CollectorFailure(RuntimeError):
    """A bounded operational failure category without sensitive details."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


class OptionalMetadataUnavailable(CollectorFailure):
    """An optional observer failed after request evidence was captured."""


@dataclass(frozen=True)
class HttpResponse:
    """Only the response information needed by the bounded collector."""

    status_code: int
    headers: Mapping[str, str]
    body: object | None
    elapsed_ms: float


@dataclass(frozen=True)
class LogObservation:
    """Request-correlated, sanitized runtime observation."""

    available: bool = True
    provider_call_count: int | None = None
    deadline_exhausted: bool | None = None
    duration_ms: float | None = None
    security_defect: bool = False
    serialization_defect: bool = False


@dataclass(frozen=True)
class DatabaseObservation:
    """Bounded PostgreSQL metadata; no response or user content is selected."""

    record_count: int = 0
    status: str | None = None
    idempotency_finalized: bool = False
    history_count: int = 0
    history_finalized: bool = False
    history_record_id: int | None = None


@dataclass
class BoundedExecutionEvidence:
    """The only per-fixture fields allowed in final evidence."""

    case_id: str
    result_state: str | None = None
    http_success: bool = False
    public_json: bool = False
    recognized_state: bool = False
    inside_authoritative_deadline: bool = False
    provider_call_count: int | None = None
    job_summary_present_or_unavailable: bool = False
    match_reasons_present_or_unavailable: bool = False
    history_finalized: bool | None = None
    idempotency_finalized: bool | None = None
    security_defect: bool = False
    serialization_defect: bool = False
    replay: bool = False
    replay_recognized: bool = False
    replay_result: str = "not_run"
    replay_provider_call_delta: int | None = None
    duplicate_history: bool | None = None
    same_history_record: bool | None = None
    duration_ms: float = 0.0
    failure_category: str | None = None
    optional_metadata_failures: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SyntheticFixture:
    """One approved synthetic request, retained only while it is being sent."""

    case_id: str
    resume_filename: str
    resume_bytes: bytes
    job_text: str


class AnalyzeClient(Protocol):
    def analyze(
        self,
        fixture: SyntheticFixture,
        *,
        idempotency_key: str,
        request_id: str,
    ) -> HttpResponse:
        ...


class LogObserver(Protocol):
    def observe(self, request_id: str, started_at: dt.datetime) -> LogObservation:
        ...


class DatabaseVerifier(Protocol):
    def observe(self, user_id: str, idempotency_key_hash: str) -> DatabaseObservation:
        ...


def _safe_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if number < 0 or number > 10_000_000:
        return None
    return round(number, 3)


def _safe_nonnegative_int(value: object, maximum: int = 100) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if number < 0:
        return None
    return min(number, maximum)


def _header(headers: Mapping[str, str], name: str) -> str:
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value).strip()
    return ""


def _present_or_explicitly_unavailable(value: object) -> bool:
    """Return only the required boolean; never retain the narrative value."""

    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        return value
    return False


def _security_defect(body: Mapping[str, object]) -> bool:
    status = str(body.get("security_status") or "").casefold()
    if status in {"blocked", "unsafe", "critical", "high", "rejected"}:
        return True
    scan = body.get("security_scan")
    if isinstance(scan, Mapping):
        return any(
            bool(scan.get(key))
            for key in ("blocked", "sensitive_data_detected", "output_leakage_detected")
        )
    return False


def _public_semantics(body: object) -> tuple[object, ...] | None:
    if not isinstance(body, Mapping):
        return None
    state = body.get("analysis_status")
    if state not in SUPPORTED_STATES:
        return None
    return (
        state,
        _present_or_explicitly_unavailable(body.get("job_summary")),
        _present_or_explicitly_unavailable(body.get("match_reason")),
        bool(body.get("saved_to_history")),
        body.get("application_id") is not None,
    )


def _provider_call_count(body: Mapping[str, object]) -> int | None:
    completion = body.get("model_completion")
    if not isinstance(completion, Mapping):
        return None
    primary = _safe_nonnegative_int(completion.get("primary_attempt_count"), 2)
    repair = _safe_nonnegative_int(completion.get("repair_attempt_count"), 1)
    if primary is None or repair is None:
        return None
    return min(MAX_PROVIDER_CALLS, primary + repair)


def _completion_bool(body: Mapping[str, object], key: str) -> bool | None:
    completion = body.get("model_completion")
    if not isinstance(completion, Mapping) or key not in completion:
        return None
    return bool(completion.get(key))


def _response_evidence(
    case_id: str,
    response: HttpResponse,
    observation: LogObservation | None,
) -> BoundedExecutionEvidence:
    evidence = BoundedExecutionEvidence(
        case_id=case_id,
        http_success=response.status_code == 200,
        public_json=isinstance(response.body, Mapping),
        serialization_defect=response.status_code == 200 and not isinstance(response.body, Mapping),
    )
    body = response.body if isinstance(response.body, Mapping) else None
    if body is not None:
        state = body.get("analysis_status")
        evidence.result_state = state if state in SUPPORTED_STATES else None
        evidence.recognized_state = evidence.result_state is not None
        evidence.job_summary_present_or_unavailable = _present_or_explicitly_unavailable(
            body.get("job_summary")
        )
        evidence.match_reasons_present_or_unavailable = _present_or_explicitly_unavailable(
            body.get("match_reason")
        )
        evidence.provider_call_count = _provider_call_count(body)
        evidence.history_finalized = _completion_bool(body, "history_finalized")
        evidence.idempotency_finalized = _completion_bool(body, "idempotency_finalized")
        evidence.security_defect = _security_defect(body)
        evidence.serialization_defect = False

    duration = response.elapsed_ms
    if observation is not None:
        if observation.duration_ms is not None:
            duration = observation.duration_ms
        if observation.security_defect:
            evidence.security_defect = True
        if observation.serialization_defect:
            evidence.serialization_defect = True
        if observation.deadline_exhausted is not None:
            evidence.inside_authoritative_deadline = (
                not observation.deadline_exhausted and duration <= ANALYZE_SAFETY_DEADLINE_MS
            )
        else:
            evidence.inside_authoritative_deadline = duration <= ANALYZE_SAFETY_DEADLINE_MS
    else:
        evidence.inside_authoritative_deadline = duration <= ANALYZE_SAFETY_DEADLINE_MS
    evidence.duration_ms = round(max(0.0, duration), 3)
    return evidence


def hash_idempotency_key(key: str) -> str:
    """Hash the caller-owned key for bounded PostgreSQL lookup only."""

    return hashlib.sha256(IDEMPOTENCY_KEY_DOMAIN + key.encode("ascii")).hexdigest()


def generate_candidate_idempotency_key() -> str:
    """Generate a safe key without ever exposing it in evidence or logs."""

    return f"pja-evidence-{secrets.token_hex(18)}"


def _request_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


class BoundedEvidenceCollector:
    """Collect one first execution and one completed replay safely."""

    def __init__(
        self,
        client: AnalyzeClient,
        *,
        log_observer: LogObserver | None = None,
        database_verifier: DatabaseVerifier | None = None,
        key_factory: Callable[[], str] = generate_candidate_idempotency_key,
        request_id_factory: Callable[[str], str] = _request_id,
    ) -> None:
        self.client = client
        self.log_observer = log_observer
        self.database_verifier = database_verifier
        self.key_factory = key_factory
        self.request_id_factory = request_id_factory

    def _observe_logs(
        self,
        request_id: str,
        started_at: dt.datetime,
        evidence: BoundedExecutionEvidence,
        *,
        label: str,
    ) -> LogObservation | None:
        if self.log_observer is None:
            evidence.optional_metadata_failures.append(f"{label}_log_metadata_missing")
            return None
        try:
            observation = self.log_observer.observe(request_id, started_at)
            if not observation.available:
                raise OptionalMetadataUnavailable(f"{label}_log_metadata_missing")
            return observation
        except Exception:
            evidence.optional_metadata_failures.append(f"{label}_log_metadata_unavailable")
            LOGGER.warning("candidate_optional_metadata_unavailable category=%s", label)
            return None

    def _observe_database(
        self,
        user_id: str,
        key_hash: str,
        evidence: BoundedExecutionEvidence,
        *,
        label: str,
    ) -> DatabaseObservation | None:
        if self.database_verifier is None:
            evidence.optional_metadata_failures.append(f"{label}_database_metadata_missing")
            return None
        try:
            return self.database_verifier.observe(user_id, key_hash)
        except Exception:
            evidence.optional_metadata_failures.append(f"{label}_database_metadata_unavailable")
            LOGGER.warning("candidate_optional_metadata_unavailable category=%s", label)
            return None

    def collect(self, fixture: SyntheticFixture, *, user_id: str) -> BoundedExecutionEvidence:
        # The key is deliberately created before the first request.  It is
        # never read back from PostgreSQL and never included in evidence.
        key = self.key_factory()
        if not isinstance(key, str) or len(key) < 8:
            raise CollectorFailure("caller_owned_idempotency_key_invalid")
        key_hash = hash_idempotency_key(key)
        first_request_id = self.request_id_factory("candidate-first")
        first_started_at = dt.datetime.now(dt.timezone.utc)
        try:
            first_response = self.client.analyze(
                fixture,
                idempotency_key=key,
                request_id=first_request_id,
            )
        except Exception:
            evidence = BoundedExecutionEvidence(
                case_id=fixture.case_id,
                failure_category="first_request_transport_failure",
            )
            LOGGER.warning("candidate_request_failed category=first_request_transport_failure")
            return evidence

        evidence = _response_evidence(fixture.case_id, first_response, None)
        first_observation = self._observe_logs(
            first_request_id,
            first_started_at,
            evidence,
            label="first",
        )
        if first_observation is not None:
            optional_failures = list(evidence.optional_metadata_failures)
            evidence = _response_evidence(fixture.case_id, first_response, first_observation)
            evidence.optional_metadata_failures.extend(optional_failures)
        # The public model completion is the primary bounded call count.  A
        # request-correlated log count is only a cross-check, never a body read.
        if first_observation is not None and first_observation.provider_call_count is not None:
            if evidence.provider_call_count is None:
                evidence.provider_call_count = first_observation.provider_call_count
            elif evidence.provider_call_count != first_observation.provider_call_count:
                evidence.failure_category = "provider_call_observation_mismatch"
        first_database = self._observe_database(
            user_id,
            key_hash,
            evidence,
            label="first",
        )
        if first_database is not None:
            evidence.history_finalized = bool(
                evidence.history_finalized is True
                and first_database.history_finalized
                and first_database.history_count == 1
            )
            evidence.idempotency_finalized = bool(
                evidence.idempotency_finalized is True
                and first_database.idempotency_finalized
            )
            if first_database.record_count != 1:
                evidence.failure_category = evidence.failure_category or "idempotency_record_count_invalid"

        replay_request_id = self.request_id_factory("candidate-replay")
        replay_started_at = dt.datetime.now(dt.timezone.utc)
        try:
            replay_response = self.client.analyze(
                fixture,
                idempotency_key=key,
                request_id=replay_request_id,
            )
            evidence.replay = True
        except Exception:
            evidence.failure_category = evidence.failure_category or "replay_transport_failure"
            LOGGER.warning("candidate_request_failed category=replay_transport_failure")
            return evidence

        replay_observation = self._observe_logs(
            replay_request_id,
            replay_started_at,
            evidence,
            label="replay",
        )
        if replay_observation is not None:
            # A unique caller request id lets this be a direct bounded delta:
            # replay had zero request-correlated Provider-start events.
            evidence.replay_provider_call_delta = replay_observation.provider_call_count
        replay_body = replay_response.body
        replay_semantics = _public_semantics(replay_body)
        first_semantics = _public_semantics(first_response.body)
        evidence.replay_recognized = (
            replay_response.status_code == 200
            and _header(replay_response.headers, "Idempotency-Replayed").casefold() == "true"
        )
        evidence.replay_result = (
            "completed"
            if evidence.replay_recognized
            and replay_semantics is not None
            and replay_semantics == first_semantics
            else "not_completed"
        )
        replay_body_map = replay_body if isinstance(replay_body, Mapping) else None
        if replay_response.status_code == 200 and replay_body_map is None:
            evidence.serialization_defect = True
        if _security_defect(replay_body_map or {}):
            evidence.security_defect = True

        replay_database = self._observe_database(
            user_id,
            key_hash,
            evidence,
            label="replay",
        )
        if first_database is not None and replay_database is not None:
            evidence.duplicate_history = replay_database.history_count != 1
            evidence.same_history_record = (
                first_database.history_record_id is not None
                and first_database.history_record_id == replay_database.history_record_id
            )
            if replay_database.record_count != 1:
                evidence.duplicate_history = True
            if replay_database.status != "completed" or not replay_database.idempotency_finalized:
                evidence.replay_result = "not_completed"

        if evidence.replay_provider_call_delta not in (None, 0):
            evidence.failure_category = evidence.failure_category or "replay_provider_call_nonzero"
        if evidence.replay_result != "completed":
            evidence.failure_category = evidence.failure_category or "completed_replay_not_proven"
        if evidence.duplicate_history is True:
            evidence.failure_category = evidence.failure_category or "duplicate_history_observed"
        return evidence


def _docx_fixture_bytes() -> bytes:
    """Build a deterministic, minimal DOCX without reading a local resume."""

    paragraphs = (
        "Synthetic candidate backend engineer.",
        "Built FastAPI services with PostgreSQL, Redis, Docker, and REST APIs.",
    )
    body = "".join(
        f"<w:p><w:r><w:t>{html.escape(paragraph)}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    ).encode("utf-8")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    ).encode("utf-8")
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", relationships)
        package.writestr("word/document.xml", document)
    return buffer.getvalue()


def make_synthetic_fixture() -> SyntheticFixture:
    return SyntheticFixture(
        case_id="pragmatic-provider-evidence-completion-1",
        resume_filename="synthetic-provider-evidence.docx",
        resume_bytes=_docx_fixture_bytes(),
        job_text=(
            "Synthetic Platform Engineer role. Required: Python, FastAPI, PostgreSQL, "
            "Redis, Docker, and REST APIs."
        ),
    )


def _multipart_body(fixture: SyntheticFixture, boundary: str) -> bytes:
    fields = (
        ("job_text", fixture.job_text.encode("utf-8"), None),
        ("save_to_history", b"true", None),
        ("use_knowledge_base", b"false", None),
        ("use_project_knowledge", b"false", None),
        ("project_knowledge_top_k", b"0", None),
        ("rag_mode", b"off", None),
        (
            "resume",
            fixture.resume_bytes,
            f'filename="{fixture.resume_filename}"; type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"',
        ),
    )
    chunks: list[bytes] = []
    delimiter = f"--{boundary}".encode("ascii")
    for name, value, file_spec in fields:
        chunks.append(delimiter + b"\r\n")
        if file_spec is None:
            chunks.append(f'Content-Disposition: form-data; name="{name}"'.encode("ascii"))
        else:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"; {file_spec}'.encode("ascii")
            )
            chunks.append(b"Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        chunks.append(b"\r\n\r\n")
        chunks.append(value)
        chunks.append(b"\r\n")
    chunks.append(delimiter + b"--\r\n")
    return b"".join(chunks)


class ProductionHttpClient:
    """Minimal authenticated client that discards bodies after bounded parsing."""

    def __init__(self, base_url: str, trusted_origin: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.trusted_origin = trusted_origin.rstrip("/")
        self.cookies = CookieJar()
        tls = ssl.create_default_context()
        tls.check_hostname = False
        tls.verify_mode = ssl.CERT_NONE
        self.opener = build_opener(HTTPCookieProcessor(self.cookies), HTTPSHandler(context=tls))
        self.csrf_token = ""

    def _json_request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        request_headers = {"User-Agent": "PJA-production-candidate-evidence/1"}
        if content_type:
            request_headers["Content-Type"] = content_type
        if headers:
            request_headers.update(headers)
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers=request_headers,
        )
        started = time.perf_counter()
        try:
            response = self.opener.open(request, timeout=190)
            status = int(response.status)
            raw = response.read()
            response_headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in {"idempotency-replayed", "x-request-id"}
            }
        except HTTPError as error:
            status = int(error.code)
            raw = error.read()
            response_headers = {}
        except (URLError, TimeoutError, OSError) as exc:
            raise CollectorFailure("http_transport_failure") from exc
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        parsed: object | None = None
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = None
        del raw
        return HttpResponse(status, response_headers, parsed, elapsed_ms)

    def login(self, email: str, password: str) -> None:
        body = json.dumps({"email": email, "password": password}, separators=(",", ":")).encode()
        response = self._json_request(
            "/api/auth/login",
            method="POST",
            body=body,
            content_type="application/json",
        )
        if response.status_code != 200 or not isinstance(response.body, Mapping):
            raise CollectorFailure("synthetic_operator_login_failed")
        csrf = response.body.get("csrf_token")
        if not isinstance(csrf, str) or not csrf:
            raise CollectorFailure("synthetic_operator_csrf_missing")
        self.csrf_token = csrf

    def logout(self) -> None:
        if not self.csrf_token:
            return
        self._json_request(
            "/api/auth/logout",
            method="POST",
            headers={"Origin": self.trusted_origin, "X-CSRF-Token": self.csrf_token},
        )
        self.csrf_token = ""

    def analyze(
        self,
        fixture: SyntheticFixture,
        *,
        idempotency_key: str,
        request_id: str,
    ) -> HttpResponse:
        boundary = f"pja_candidate_{secrets.token_hex(12)}"
        body = _multipart_body(fixture, boundary)
        return self._json_request(
            "/api/analyze",
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            headers={
                "Origin": self.trusted_origin,
                "X-CSRF-Token": self.csrf_token,
                "Idempotency-Key": idempotency_key,
                "X-Request-ID": request_id,
            },
        )

    def health_snapshot(self) -> dict[str, object]:
        health = self._json_request("/api/health")
        ready = self._json_request("/api/ready")
        health_body = health.body if isinstance(health.body, Mapping) else {}
        ready_body = ready.body if isinstance(ready.body, Mapping) else {}
        return {
            "health_http_200": health.status_code == 200,
            "ready_http_200": ready.status_code == 200,
            "status_ok": health_body.get("status") == "ok",
            "ready": ready_body.get("ready") is True,
            "version": health_body.get("version"),
        }


class DockerLogObserver:
    """Stream only request-correlated safe log metadata from one container."""

    def __init__(self, container_name: str) -> None:
        self.container_name = container_name

    def observe(self, request_id: str, started_at: dt.datetime) -> LogObservation:
        command = [
            "docker",
            "logs",
            "--since",
            started_at.isoformat(),
            self.container_name,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            raise OptionalMetadataUnavailable("docker_logs_unavailable") from exc
        provider_calls = 0
        deadline_exhausted: bool | None = None
        duration_ms: float | None = None
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                try:
                    event = json.loads(raw_line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, Mapping) or event.get("request_id") != request_id:
                    continue
                message = str(event.get("message") or "")
                if message.startswith("DeepSeek call started"):
                    provider_calls = min(MAX_PROVIDER_CALLS, provider_calls + 1)
                if message.startswith("Analyze timing complete"):
                    duration_match = _bounded_search(r"total_analyze_duration_ms=([0-9.]+)", message)
                    deadline_match = _bounded_search(r"deadline_exhausted=(True|False)", message)
                    duration_ms = _safe_float(duration_match)
                    if deadline_match:
                        deadline_exhausted = deadline_match == "True"
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            process.kill()
            raise OptionalMetadataUnavailable("docker_logs_read_failed") from exc
        return LogObservation(
            available=process.returncode == 0,
            provider_call_count=provider_calls,
            deadline_exhausted=deadline_exhausted,
            duration_ms=duration_ms,
        )


def _bounded_search(pattern: str, value: str) -> str:
    import re

    match = re.search(pattern, value)
    return match.group(1) if match else ""


_DATABASE_PROBE = r'''
import json
import sys
from sqlalchemy import text
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.session import session_factory

payload = json.load(sys.stdin)
db = session_factory()()
try:
    action = payload.get("action")
    uid = payload.get("user_id")
    if action == "create_operator":
        user = AuthService(db, load_v2_settings()).create_user(
            payload["email"], payload["password"], payload["display_name"], "user"
        )
        db.commit()
        print(json.dumps({"ok": True, "user_id": str(user.id)}))
    elif action == "schema":
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        print(json.dumps({"ok": True, "revision": str(revision)}))
    elif action == "observe":
        records = db.execute(text(
            "SELECT status, history_record_id FROM analyze_idempotency_records "
            "WHERE user_id = :uid AND operation = 'analyze:v1' "
            "AND idempotency_key_hash = :key_hash"
        ), {"uid": uid, "key_hash": payload["key_hash"]}).mappings().all()
        history_count = db.execute(text(
            "SELECT COUNT(*) FROM application_records WHERE owner_user_id = :uid"
        ), {"uid": uid}).scalar_one()
        completed = len(records) == 1 and records[0]["status"] == "completed"
        history_id = records[0]["history_record_id"] if len(records) == 1 else None
        print(json.dumps({
            "ok": True,
            "record_count": len(records),
            "status": records[0]["status"] if len(records) == 1 else None,
            "idempotency_finalized": completed and history_id is not None,
            "history_count": int(history_count),
            "history_finalized": int(history_count) == 1 and history_id is not None,
            "history_record_id": int(history_id) if history_id is not None else None,
        }))
    elif action == "cleanup":
        exact_user = db.execute(text(
            "SELECT COUNT(*) FROM users WHERE id = :uid "
            "AND normalized_email = :email AND role = 'user'"
        ), {"uid": uid, "email": payload["email"]}).scalar_one()
        if int(exact_user) != 1:
            raise RuntimeError("synthetic_operator_identity_mismatch")
        counts = {}
        for table in (
            "application_records",
            "analysis_step_metrics",
            "analysis_metrics",
            "analyze_idempotency_records",
            "audit_events",
        ):
            if table == "audit_events":
                clause = "user_id = :uid"
            elif table == "application_records":
                clause = "owner_user_id = :uid"
            elif table in ("analysis_step_metrics", "analysis_metrics"):
                clause = "owner_user_id = :uid"
            else:
                clause = "user_id = :uid"
            counts[table] = int(db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {clause}"
            ), {"uid": uid}).scalar_one())
        db.execute(text("DELETE FROM application_records WHERE owner_user_id = :uid"), {"uid": uid})
        db.execute(text("DELETE FROM analysis_step_metrics WHERE owner_user_id = :uid"), {"uid": uid})
        db.execute(text("DELETE FROM analysis_metrics WHERE owner_user_id = :uid"), {"uid": uid})
        db.execute(text("DELETE FROM analyze_idempotency_records WHERE user_id = :uid"), {"uid": uid})
        db.execute(text("DELETE FROM audit_events WHERE user_id = :uid"), {"uid": uid})
        deleted_user = db.execute(text(
            "DELETE FROM users WHERE id = :uid AND normalized_email = :email AND role = 'user'"
        ), {"uid": uid, "email": payload["email"]}).rowcount
        db.commit()
        remaining = {}
        for table, column in (
            ("application_records", "owner_user_id"),
            ("analysis_step_metrics", "owner_user_id"),
            ("analysis_metrics", "owner_user_id"),
            ("analyze_idempotency_records", "user_id"),
        ):
            remaining[table] = int(db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = :uid"
            ), {"uid": uid}).scalar_one())
        remaining["users"] = int(db.execute(text(
            "SELECT COUNT(*) FROM users WHERE id = :uid"
        ), {"uid": uid}).scalar_one())
        print(json.dumps({"ok": deleted_user == 1, "before": counts, "remaining": remaining}))
    else:
        raise RuntimeError("unknown_probe_action")
except Exception as exc:
    db.rollback()
    print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
finally:
    db.close()
'''


class DockerPostgresVerifier:
    """Run bounded SQL inside the deployed backend without exposing secrets."""

    def __init__(self, backend_container: str) -> None:
        self.backend_container = backend_container

    def _run(self, payload: Mapping[str, object]) -> dict[str, object]:
        try:
            result = subprocess.run(
                ["docker", "exec", "-i", self.backend_container, "python", "-c", _DATABASE_PROBE],
                input=json.dumps(payload, separators=(",", ":")),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OptionalMetadataUnavailable("database_probe_failed") from exc
        if result.returncode != 0:
            raise OptionalMetadataUnavailable("database_probe_failed")
        try:
            value = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, TypeError, ValueError) as exc:
            raise OptionalMetadataUnavailable("database_probe_invalid") from exc
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise OptionalMetadataUnavailable("database_probe_rejected")
        return value

    def create_operator(self, email: str, password: str) -> str:
        value = self._run({
            "action": "create_operator",
            "email": email,
            "password": password,
            "display_name": "Synthetic Evidence Operator",
        })
        user_id = value.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise CollectorFailure("synthetic_operator_creation_failed")
        return user_id

    def observe(self, user_id: str, idempotency_key_hash: str) -> DatabaseObservation:
        value = self._run({"action": "observe", "user_id": user_id, "key_hash": idempotency_key_hash})
        return DatabaseObservation(
            record_count=int(value.get("record_count") or 0),
            status=value.get("status") if isinstance(value.get("status"), str) else None,
            idempotency_finalized=bool(value.get("idempotency_finalized")),
            history_count=int(value.get("history_count") or 0),
            history_finalized=bool(value.get("history_finalized")),
            history_record_id=(
                int(value["history_record_id"])
                if value.get("history_record_id") is not None
                else None
            ),
        )

    def schema_revision(self) -> str:
        value = self._run({"action": "schema"})
        revision = value.get("revision")
        if not isinstance(revision, str):
            raise CollectorFailure("schema_revision_unavailable")
        return revision

    def cleanup_operator(self, user_id: str, email: str) -> dict[str, object]:
        return self._run({"action": "cleanup", "user_id": user_id, "email": email})


@dataclass(frozen=True)
class RuntimeSnapshot:
    image_digest: str
    revision: str
    version: str
    health: str
    restart_count: int
    oom_killed: bool


class DockerRuntimeProbe:
    """Read only selected container state, never the full environment."""

    _INSPECT_TEMPLATE = (
        "{{.Image}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}|"
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|"
        "{{index .Config.Labels \"org.opencontainers.image.revision\"}}|"
        "{{index .Config.Labels \"org.opencontainers.image.version\"}}"
    )

    def __init__(self, services: Mapping[str, str]) -> None:
        self.services = dict(services)

    def service(self, logical_name: str) -> RuntimeSnapshot:
        name = self.services[logical_name]
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", self._INSPECT_TEMPLATE, name],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CollectorFailure("runtime_inspection_failed") from exc
        if result.returncode != 0:
            raise CollectorFailure("runtime_inspection_failed")
        values = result.stdout.strip().split("|", 6)
        if len(values) != 7:
            raise CollectorFailure("runtime_inspection_invalid")
        try:
            restart_count = int(values[2])
        except ValueError as exc:
            raise CollectorFailure("runtime_inspection_invalid") from exc
        return RuntimeSnapshot(
            image_digest=values[0],
            health=values[4],
            restart_count=restart_count,
            oom_killed=values[3].casefold() == "true",
            revision=values[5],
            version=values[6],
        )

    def selected_backend_environment(self, backend_name: str) -> dict[str, str]:
        command = (
            "printf '%s\\n' \"$ANALYSIS_JD_NORMALIZATION_MODE\" "
            "\"$JD_NORMALIZATION_EXPECTED_POLICY_VERSION\" "
            "\"$JD_NORMALIZATION_EXPECTED_DICTIONARY_VERSION\""
        )
        try:
            result = subprocess.run(
                ["docker", "exec", backend_name, "sh", "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CollectorFailure("normalization_configuration_unavailable") from exc
        if result.returncode != 0:
            raise CollectorFailure("normalization_configuration_unavailable")
        values = result.stdout.strip().splitlines()
        if len(values) != 3:
            raise CollectorFailure("normalization_configuration_invalid")
        return {"mode": values[0], "policy": values[1], "dictionary": values[2]}


def verify_current_candidate(
    runtime: DockerRuntimeProbe,
    database: DockerPostgresVerifier,
    client: ProductionHttpClient,
) -> dict[str, object]:
    expected = {
        "backend": EXPECTED_BACKEND_DIGEST,
        "worker": EXPECTED_BACKEND_DIGEST,
        "outbox": EXPECTED_BACKEND_DIGEST,
        "frontend": EXPECTED_FRONTEND_DIGEST,
        "edge": EXPECTED_FRONTEND_DIGEST,
        "java": EXPECTED_JAVA_DIGEST,
    }
    snapshots: dict[str, object] = {}
    for service, digest in expected.items():
        snapshot = runtime.service(service)
        snapshots[service] = asdict(snapshot)
        if (
            snapshot.image_digest != digest
            or snapshot.revision != EXPECTED_SOURCE_REVISION
            and service != "java"
            or snapshot.version != EXPECTED_PUBLIC_VERSION
            and service != "java"
            or snapshot.health != "healthy"
            or snapshot.restart_count != 0
            or snapshot.oom_killed
        ):
            raise CollectorFailure("production_candidate_changed_or_unhealthy")
    configuration = runtime.selected_backend_environment(runtime.services["backend"])
    if configuration != {
        "mode": EXPECTED_JD_MODE,
        "policy": EXPECTED_JD_POLICY,
        "dictionary": EXPECTED_SKILL_DICTIONARY,
    }:
        raise CollectorFailure("normalization_baseline_changed")
    schema = database.schema_revision()
    if schema != EXPECTED_ALEMBIC_REVISION:
        raise CollectorFailure("alembic_baseline_changed")
    health = client.health_snapshot()
    if health != {
        "health_http_200": True,
        "ready_http_200": True,
        "status_ok": True,
        "ready": True,
        "version": EXPECTED_PUBLIC_VERSION,
    }:
        raise CollectorFailure("public_health_changed_or_unhealthy")
    return {
        "source_revision": EXPECTED_SOURCE_REVISION,
        "backend_digest": EXPECTED_BACKEND_DIGEST,
        "frontend_digest": EXPECTED_FRONTEND_DIGEST,
        "java_digest": EXPECTED_JAVA_DIGEST,
        "public_version": EXPECTED_PUBLIC_VERSION,
        "alembic_current_head": schema,
        "jd_normalization_mode": configuration["mode"],
        "jd_normalization_policy": configuration["policy"],
        "skill_dictionary": configuration["dictionary"],
        "services": snapshots,
        "health": health,
    }


def _write_bounded(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _cleanup_summary(value: Mapping[str, object]) -> dict[str, object]:
    remaining = value.get("remaining")
    if not isinstance(remaining, Mapping):
        return {"status": "failed", "zero_synthetic_rows": False}
    zero_rows = all(int(item or 0) == 0 for item in remaining.values())
    return {
        "status": "passed" if value.get("ok") is True and zero_rows else "failed",
        "zero_synthetic_rows": zero_rows,
        "remaining_row_counts": {str(key): int(item or 0) for key, item in remaining.items()},
    }


def run_production(
    *,
    output_path: Path,
    base_url: str,
    trusted_origin: str,
    backend_container: str,
    java_container: str,
    operator_email: str | None = None,
    operator_password: str | None = None,
) -> dict[str, object]:
    """Run exactly one first request plus its one completed replay."""

    database = DockerPostgresVerifier(backend_container)
    client = ProductionHttpClient(base_url, trusted_origin)
    runtime = DockerRuntimeProbe({
        "backend": backend_container,
        "worker": "personal-job-agent-v2-worker-1",
        "outbox": "personal-job-agent-v2-outbox-dispatcher-1",
        "frontend": "personal-job-agent-v2-frontend-1",
        "edge": "personal-job-agent-v2-edge-1",
        "java": java_container,
    })
    result: dict[str, object] = {
        "supplemental_execution_count": 0,
        "production_candidate_current": False,
        "cleanup": {"status": "not_run", "zero_synthetic_rows": False},
    }
    user_id: str | None = None
    email = operator_email or f"pja-evidence-{uuid.uuid4().hex[:20]}@example.com"
    password = operator_password or secrets.token_urlsafe(32)
    try:
        result["production_baseline"] = verify_current_candidate(runtime, database, client)
        result["production_candidate_current"] = True
        user_id = database.create_operator(email, password)
        client.login(email, password)
        fixture = make_synthetic_fixture()
        evidence = BoundedEvidenceCollector(
            client,
            log_observer=DockerLogObserver(backend_container),
            database_verifier=database,
        ).collect(fixture, user_id=user_id)
        result["supplemental_execution_count"] = 1
        result["supplemental_evidence"] = asdict(evidence)
    except CollectorFailure as exc:
        result["failure_category"] = exc.category
    except Exception:
        result["failure_category"] = "collector_unexpected_failure"
    finally:
        try:
            client.logout()
        except Exception:
            result["logout_failure"] = True
        if user_id is not None:
            try:
                result["cleanup"] = _cleanup_summary(database.cleanup_operator(user_id, email))
            except Exception:
                result["cleanup"] = {"status": "failed", "zero_synthetic_rows": False}
        password = ""
        email = ""
        _write_bounded(output_path, result)
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="https://127.0.0.1:8080")
    parser.add_argument("--trusted-origin", default="https://101.34.61.52:8080")
    parser.add_argument("--backend-container", default="personal-job-agent-v2-backend-1")
    parser.add_argument("--java-container", default="pja-java-normalization-java-normalization-1")
    parser.add_argument("--operator-email")
    parser.add_argument("--operator-password-stdin", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    password = None
    if args.operator_password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            _write_bounded(args.output, {"failure_category": "operator_password_missing"})
            return 2
    result = run_production(
        output_path=args.output,
        base_url=args.base_url,
        trusted_origin=args.trusted_origin,
        backend_container=args.backend_container,
        java_container=args.java_container,
        operator_email=args.operator_email,
        operator_password=password,
    )
    return 0 if result.get("production_candidate_current") and result.get("cleanup", {}).get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
