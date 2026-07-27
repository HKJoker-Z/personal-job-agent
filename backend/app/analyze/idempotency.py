"""PostgreSQL-backed idempotency state machine for synchronous Analyze."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.db.models import (
    AnalyzeIdempotencyRecord,
    ApplicationRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    ensure_utc,
    utc_now,
)
from app.db.session import session_factory
from database import (
    clean_text,
    default_ats_analysis,
    default_scoring_breakdown,
    safe_float,
    safe_int,
    serialize_analysis_metadata,
    serialize_json,
    serialize_list,
)


OPERATION = "analyze:v1"
FINGERPRINT_VERSION = "analyze-request-fingerprint:v1"
KEY_HASH_DOMAIN = b"personal-job-agent:analyze:idempotency-key:v1\x00"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
TERMINAL_STATUSES = ("completed", "failed", "indeterminate")
MAX_RESPONSE_BYTES = 512 * 1024


class IdempotencyError(RuntimeError):
    def __init__(self, code: str, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class Claim:
    record_id: UUID
    attempt_token: UUID | None
    replay_status: int | None = None
    replay_body: dict[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_body is not None


def validate_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not KEY_PATTERN.fullmatch(value):
        raise IdempotencyError(
            "IDEMPOTENCY_KEY_INVALID",
            "Idempotency-Key must be 8-128 safe ASCII characters.",
        )
    return value


def hash_key(value: str) -> str:
    return hashlib.sha256(KEY_HASH_DOMAIN + value.encode("ascii")).hexdigest()


def _normalized_text(value: str | None) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def _text_hash(value: str | None) -> str:
    return hashlib.sha256(_normalized_text(value).encode("utf-8")).hexdigest()


def project_knowledge_version(db: Any, enabled: bool) -> dict[str, Any] | None:
    if not enabled:
        return None
    documents = db.scalars(
        select(KnowledgeDocument).order_by(KnowledgeDocument.id.asc())
    ).all()
    digest = hashlib.sha256()
    ids: list[int] = []
    for document in documents:
        ids.append(document.id)
        digest.update(f"document:{document.id}\x00".encode())
        chunks = db.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.chunk_index.asc())
        ).all()
        for chunk in chunks:
            digest.update(f"{chunk.chunk_index}\x00".encode())
            digest.update(_normalized_text(chunk.content).encode("utf-8"))
            digest.update(b"\x00")
    return {"document_ids": ids, "content_hash": digest.hexdigest()}


def request_fingerprint(
    *,
    resume_version_id: str | None,
    resume_text: str,
    job_text: str,
    job_url: str | None,
    rag_enabled: bool,
    rag_top_k: int,
    project_knowledge: dict[str, Any] | None,
    save_to_history: bool,
    model: str,
    security_policy_version: str,
) -> str:
    canonical = {
        "analysis_contract_version": "compact-analysis:v2.0.3",
        "job": {
            "acquired_text_hash": _text_hash(job_text),
            "normalized_url": _normalized_text(job_url) or None,
        },
        "model": model,
        "project_knowledge": project_knowledge,
        "rag": {"enabled": rag_enabled, "top_k": int(rag_top_k)},
        "resume": {
            "normalized_text_hash": _text_hash(resume_text),
            "version_id": resume_version_id or None,
        },
        "save_to_history": bool(save_to_history),
        "security_policy_version": security_policy_version,
        "version": FINGERPRINT_VERSION,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AnalyzeIdempotencyService:
    def __init__(self) -> None:
        self._factory = session_factory()
        self.lease_seconds = max(
            5, min(300, int(os.getenv("ANALYZE_IDEMPOTENCY_LEASE_SECONDS", "180")))
        )
        self.retention_hours = max(
            1, min(168, int(os.getenv("ANALYZE_IDEMPOTENCY_RETENTION_HOURS", "24")))
        )

    def _lease(self):
        return utc_now() + timedelta(seconds=self.lease_seconds)

    def _expiry(self):
        return utc_now() + timedelta(hours=self.retention_hours)

    def cleanup(self, batch_size: int = 100) -> int:
        batch_size = max(1, min(500, batch_size))
        now = utc_now()
        db = self._factory()
        try:
            stale = db.scalars(
                select(AnalyzeIdempotencyRecord)
                .where(
                    AnalyzeIdempotencyRecord.status == "processing",
                    AnalyzeIdempotencyRecord.lease_expires_at <= now,
                )
                .order_by(AnalyzeIdempotencyRecord.lease_expires_at.asc())
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
            for record in stale:
                if record.provider_started_at is not None:
                    record.status = "indeterminate"
                    record.error_code = "IDEMPOTENCY_OUTCOME_UNKNOWN"
                    record.completed_at = now
                elif ensure_utc(record.expires_at) <= now:
                    record.status = "failed"
                    record.error_code = "IDEMPOTENCY_PERSISTENCE_FAILED"
                    record.completed_at = now
            expired_ids = list(
                db.scalars(
                    select(AnalyzeIdempotencyRecord.id)
                    .where(
                        AnalyzeIdempotencyRecord.status.in_(TERMINAL_STATUSES),
                        AnalyzeIdempotencyRecord.expires_at <= now,
                    )
                    .order_by(AnalyzeIdempotencyRecord.expires_at.asc())
                    .limit(batch_size)
                )
            )
            if expired_ids:
                db.execute(
                    delete(AnalyzeIdempotencyRecord).where(
                        AnalyzeIdempotencyRecord.id.in_(expired_ids)
                    )
                )
            db.commit()
            return len(expired_ids)
        except SQLAlchemyError:
            db.rollback()
            return 0
        finally:
            db.close()

    def claim(
        self,
        *,
        user_id: UUID,
        key_hash: str,
        fingerprint: str,
        request_id: str,
    ) -> Claim:
        self.cleanup()
        now = utc_now()
        token = uuid4()
        record = AnalyzeIdempotencyRecord(
            user_id=user_id,
            operation=OPERATION,
            idempotency_key_hash=key_hash,
            request_fingerprint=fingerprint,
            status="processing",
            request_id=request_id,
            attempt_token=token,
            lease_expires_at=self._lease(),
            attempt_count=1,
            expires_at=self._expiry(),
        )
        db = self._factory()
        try:
            db.add(record)
            db.commit()
            return Claim(record.id, token)
        except IntegrityError:
            db.rollback()
        except SQLAlchemyError as exc:
            db.rollback()
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                "The idempotency record could not be persisted.",
            ) from exc

        try:
            existing = db.scalar(
                select(AnalyzeIdempotencyRecord)
                .where(
                    AnalyzeIdempotencyRecord.user_id == user_id,
                    AnalyzeIdempotencyRecord.operation == OPERATION,
                    AnalyzeIdempotencyRecord.idempotency_key_hash == key_hash,
                )
                .with_for_update()
            )
            if existing is None:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The idempotency record could not be loaded.",
                )
            if existing.request_fingerprint != fingerprint:
                raise IdempotencyError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "This Idempotency-Key was already used for a different Analyze request.",
                )
            if existing.status == "completed":
                body = existing.response_body
                if not isinstance(body, dict) or existing.response_status is None:
                    raise IdempotencyError(
                        "IDEMPOTENCY_PERSISTENCE_FAILED",
                        "The stored Analyze response is unavailable.",
                    )
                return Claim(existing.id, None, existing.response_status, body)
            if existing.status == "indeterminate" or (
                existing.status == "processing"
                and ensure_utc(existing.lease_expires_at) <= now
                and existing.provider_started_at is not None
            ):
                existing.status = "indeterminate"
                existing.error_code = "IDEMPOTENCY_OUTCOME_UNKNOWN"
                existing.completed_at = existing.completed_at or now
                db.commit()
                raise IdempotencyError(
                    "IDEMPOTENCY_OUTCOME_UNKNOWN",
                    "The provider outcome is unknown; automatic execution is blocked.",
                )
            if existing.status == "processing" and ensure_utc(existing.lease_expires_at) > now:
                retry_after = max(
                    1,
                    min(
                        30,
                        int((ensure_utc(existing.lease_expires_at) - now).total_seconds()) + 1,
                    ),
                )
                raise IdempotencyError(
                    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    "An Analyze request with this key is still processing.",
                    retry_after=retry_after,
                )
            existing.status = "processing"
            existing.attempt_token = token
            existing.request_id = request_id
            existing.provider_started_at = None
            existing.lease_expires_at = self._lease()
            existing.attempt_count += 1
            existing.error_code = None
            existing.completed_at = None
            existing.expires_at = self._expiry()
            db.commit()
            return Claim(existing.id, token)
        except IdempotencyError:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                "The idempotency record could not be persisted.",
            ) from exc
        finally:
            db.close()

    def provider_started(self, claim: Claim) -> None:
        if claim.attempt_token is None:
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED", "The provider attempt is no longer current."
            )
        db = self._factory()
        try:
            changed = db.execute(
                update(AnalyzeIdempotencyRecord)
                .where(
                    AnalyzeIdempotencyRecord.id == claim.record_id,
                    AnalyzeIdempotencyRecord.status == "processing",
                    AnalyzeIdempotencyRecord.attempt_token == claim.attempt_token,
                )
                .values(provider_started_at=utc_now(), lease_expires_at=self._lease())
            ).rowcount
            if changed != 1:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The provider attempt is no longer current.",
                )
            db.commit()
        except IdempotencyError:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                "The provider boundary could not be persisted.",
            ) from exc
        finally:
            db.close()

    def fail_unfinalized(self, claim: Claim, error_code: str) -> None:
        if claim.attempt_token is None:
            return
        db = self._factory()
        try:
            record = db.scalar(
                select(AnalyzeIdempotencyRecord)
                .where(
                    AnalyzeIdempotencyRecord.id == claim.record_id,
                    AnalyzeIdempotencyRecord.attempt_token == claim.attempt_token,
                    AnalyzeIdempotencyRecord.status == "processing",
                )
                .with_for_update()
            )
            if record is None:
                db.rollback()
                return
            record.status = "indeterminate" if record.provider_started_at else "failed"
            record.error_code = (
                "IDEMPOTENCY_OUTCOME_UNKNOWN" if record.provider_started_at else error_code[:80]
            )
            record.completed_at = utc_now()
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        finally:
            db.close()

    def finalize(
        self,
        claim: Claim,
        response: dict[str, Any],
        *,
        save_to_history: bool,
        user_id: UUID,
        job_url: str | None,
        resume_filename: str | None,
    ) -> tuple[dict[str, Any], int | None]:
        if claim.attempt_token is None:
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED", "The Analyze attempt cannot be finalized."
            )
        body = dict(response)
        db = self._factory()
        try:
            record = db.scalar(
                select(AnalyzeIdempotencyRecord)
                .where(AnalyzeIdempotencyRecord.id == claim.record_id)
                .with_for_update()
            )
            if (
                record is None
                or record.status != "processing"
                or record.attempt_token != claim.attempt_token
            ):
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "A stale Analyze attempt cannot finalize this request.",
                )
            history_id = None
            if save_to_history:
                history = self._history_record(
                    body, user_id=user_id, job_url=job_url, resume_filename=resume_filename
                )
                db.add(history)
                db.flush()
                history_id = history.id
            body["application_id"] = history_id
            body["saved_to_history"] = bool(save_to_history)
            encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_RESPONSE_BYTES:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The normalized Analyze response is too large to store safely.",
                )
            record.response_status = 200
            record.response_body = body
            record.history_record_id = history_id
            record.status = "completed"
            record.completed_at = utc_now()
            record.error_code = None
            db.commit()
            return body, history_id
        except IdempotencyError:
            db.rollback()
            raise
        except SQLAlchemyError as exc:
            db.rollback()
            raise IdempotencyError(
                "IDEMPOTENCY_PERSISTENCE_FAILED",
                "Analyze finalization could not be committed.",
            ) from exc
        finally:
            db.close()

    @staticmethod
    def _history_record(
        result: dict[str, Any],
        *,
        user_id: UUID,
        job_url: str | None,
        resume_filename: str | None,
    ) -> ApplicationRecord:
        now = utc_now()
        return ApplicationRecord(
            owner_user_id=user_id,
            created_at=now,
            updated_at=now,
            company_name=clean_text(result.get("company_name"), "Unknown Company"),
            job_title=clean_text(result.get("job_title"), "Unknown Position"),
            job_url=job_url or None,
            resume_filename=resume_filename or None,
            application_status="Saved",
            match_score=int(result.get("match_score", 0)),
            match_reason=clean_text(result.get("match_reason")),
            job_summary=clean_text(result.get("job_summary")),
            matched_skills=serialize_list(result.get("matched_skills")),
            missing_skills=serialize_list(result.get("missing_skills")),
            resume_suggestions=serialize_list(result.get("resume_suggestions")),
            cover_letter=clean_text(result.get("cover_letter")),
            scoring_breakdown=serialize_json(
                result.get("scoring_breakdown"), default_scoring_breakdown()
            ),
            ats_analysis=serialize_json(result.get("ats_analysis"), default_ats_analysis()),
            upgraded_resume_bullets=serialize_json(result.get("upgraded_resume_bullets"), []),
            rag_mode=clean_text(result.get("rag_mode")),
            rag_sources=serialize_json(result.get("rag_sources"), []),
            workflow_id=clean_text(result.get("workflow_id")) or None,
            workflow_steps=serialize_json(result.get("workflow_steps"), []),
            workflow_duration_ms=safe_float(result.get("workflow_duration_ms"), None),
            workflow_duration_us=safe_int(result.get("workflow_duration_us"), None),
            next_action=serialize_json(result.get("next_action"), {}),
            next_action_decision=clean_text(result.get("next_action_decision"), "pending"),
            next_action_decision_notes=clean_text(result.get("next_action_decision_notes")) or None,
            next_action_decided_at=None,
            security_scan=serialize_json(result.get("security_scan"), {}),
            security_status=clean_text(result.get("security_status"), "not_available"),
            security_policy_version=clean_text(result.get("security_policy_version")) or None,
            notes=serialize_analysis_metadata(result),
        )


class AnalyzeIdempotencyFailureMiddleware(BaseHTTPMiddleware):
    """Close claimed attempts when a handled route failure prevents finalization."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        claim = getattr(request.state, "analyze_idempotency_claim", None)
        service = getattr(request.state, "analyze_idempotency_service", None)
        finalized = bool(getattr(request.state, "analyze_idempotency_finalized", False))
        if claim is not None and service is not None and not finalized and response.status_code >= 400:
            service.fail_unfinalized(
                claim,
                str(getattr(request.state, "error_code", "IDEMPOTENCY_PERSISTENCE_FAILED")),
            )
        return response
