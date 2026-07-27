"""Safe PostgreSQL/Alembic/storage readiness without external network calls."""

from __future__ import annotations

import os
import shutil
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from redis import Redis

from app import APP_VERSION
from app.core.config import load_v2_settings, safe_database_status
from app.db.engine import build_engine
from app.db.models import User, WorkerHeartbeat, ensure_utc, utc_now
from app.db.session import session_factory


ALEMBIC_HEAD = "20260724_06"
REQUIRED_TABLES = {
    "users",
    "user_sessions",
    "career_profiles",
    "file_assets",
    "resumes",
    "resume_versions",
    "application_records",
    "analyze_idempotency_records",
    "analysis_metrics",
    "evaluation_runs",
    "knowledge_documents",
    "knowledge_chunks",
    "job_match_analyses",
    "job_match_dimensions",
    "job_match_evidence",
    "job_rank_runs",
    "job_rank_items",
    "application_packages",
    "application_materials",
    "application_material_versions",
    "material_evidence_links",
    "material_reviews",
    "agent_runs",
    "agent_steps",
    "agent_run_events",
    "approval_requests",
    "approval_decisions",
    "agent_outbox_events",
    "user_ai_budgets",
    "ai_usage_ledger",
    "worker_heartbeats",
    "dead_letter_records",
}


def _writable(directory: Path) -> bool:
    if not directory.is_dir() or directory.is_symlink():
        return False
    probe = directory / f".readiness-{uuid4().hex}"
    try:
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        probe.unlink()
        return True
    except OSError:
        probe.unlink(missing_ok=True)
        return False


def readiness_status() -> tuple[dict[str, object], int]:
    settings = load_v2_settings()
    response: dict[str, object] = {
        "ready": False,
        "version": APP_VERSION,
        "database": "not_ready",
        "database_schema": "not_ready",
        "file_storage": "not_ready",
        "project_knowledge": "not_ready",
        "knowledge_search": "not_ready",
        "redis": "not_ready" if settings.readiness_require_redis else "not_required",
        "worker": "not_ready" if settings.readiness_require_worker else "not_required",
        "disk_space": "not_ready",
        "auth_initialized": False,
        "llm_configuration": "configured" if os.getenv("DEEPSEEK_API_KEY") else "not_configured",
        "status": "not_ready",
    }
    try:
        engine = build_engine(settings.database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            response["database"] = "ready"
            tables = set(inspect(connection).get_table_names())
            if not REQUIRED_TABLES.issubset(tables) or "alembic_version" not in tables:
                return response, 503
            current = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            if current != ALEMBIC_HEAD:
                response["database_schema"] = "revision_mismatch"
                return response, 503
            response["database_schema"] = "ready"
        response["file_storage"] = "ready" if _writable(settings.file_storage_root) else "not_ready"
        if response["file_storage"] == "ready":
            free_mb = shutil.disk_usage(settings.file_storage_root).free // (1024 * 1024)
            response["disk_space"] = "ready" if free_mb >= settings.minimum_free_disk_mb else "not_ready"
        knowledge_path = Path(
            os.getenv("PROJECT_KNOWLEDGE_PATH", "docs/PROJECT_KNOWLEDGE.md")
        ).expanduser()
        response["project_knowledge"] = "ready" if knowledge_path.is_file() else "not_ready"
        response["knowledge_search"] = "ready" if {"knowledge_documents", "knowledge_chunks"}.issubset(tables) else "not_ready"
        db = session_factory(settings.database_url)()
        try:
            response["auth_initialized"] = db.scalar(select(User.id).limit(1)) is not None
            if settings.readiness_require_worker:
                cutoff = utc_now() - timedelta(seconds=settings.worker_stale_seconds)
                workers = db.scalars(select(WorkerHeartbeat).where(
                    WorkerHeartbeat.status.in_(("ready", "busy")),
                )).all()
                if any(ensure_utc(item.last_heartbeat_at) >= cutoff for item in workers):
                    response["worker"] = "ready"
        finally:
            db.close()
        if settings.readiness_require_redis:
            redis_client = Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            try:
                if redis_client.ping() is True:
                    response["redis"] = "ready"
            finally:
                redis_client.close()
    except (OSError, SQLAlchemyError, RuntimeError, ValueError):
        return response, 503
    except Exception:
        return response, 503
    required_ready = all(
        response[key] == "ready"
        for key in (
            "database", "database_schema", "file_storage", "project_knowledge",
            "knowledge_search", "disk_space",
        )
    )
    if settings.readiness_require_redis:
        required_ready = required_ready and response["redis"] == "ready"
    if settings.readiness_require_worker:
        required_ready = required_ready and response["worker"] == "ready"
    if settings.app_env == "production" and response["llm_configuration"] != "configured":
        required_ready = False
    response["ready"] = required_ready
    response["status"] = "ready" if required_ready else "not_ready"
    return response, 200 if required_ready else 503


def detailed_status() -> dict[str, object]:
    settings = load_v2_settings()
    public, _ = readiness_status()
    return {
        **public,
        "database_configuration": safe_database_status(settings),
        "expected_schema_revision": ALEMBIC_HEAD,
    }
