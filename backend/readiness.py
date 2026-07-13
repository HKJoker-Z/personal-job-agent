"""Lightweight local readiness checks; never calls the external LLM."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import APP_VERSION, AppConfig, ConfigError, load_config
from database import assert_safe_test_database
from project_knowledge_runtime import PROJECT_KNOWLEDGE_LOGICAL_NAME, initialize_project_knowledge


REQUIRED_TABLES = {
    "application_records",
    "knowledge_documents",
    "knowledge_chunks",
    "analysis_metrics",
    "analysis_step_metrics",
    "evaluation_runs",
    "evaluation_results",
}


def _directory_is_writable(directory: Path) -> bool:
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / f".readiness-write-test-{uuid4().hex}"
    try:
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        probe.unlink()
        return True
    except OSError:
        if probe.exists():
            probe.unlink()
        return False


def readiness_status(config: AppConfig | None = None) -> tuple[dict[str, Any], int]:
    if os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL"):
        from app.readiness import readiness_status as v2_readiness_status

        return v2_readiness_status()
    try:
        settings = config or load_config(validate_production=False)
    except ConfigError:
        return _failure("configuration"), 503

    response: dict[str, Any] = {
        "ready": False,
        "version": APP_VERSION,
        "database": "not_ready",
        "database_schema": "not_ready",
        "project_knowledge_file": "not_ready",
        "project_knowledge_index": "not_ready",
        "llm_configuration": "configured" if settings.deepseek_api_key else "not_configured",
        "status": "not_ready",
    }
    try:
        assert_safe_test_database(settings.database_path, settings.app_env)
        if not _directory_is_writable(settings.database_path.parent):
            return response, 503
        connection = sqlite3.connect(f"{settings.database_path.as_uri()}?mode=rw", uri=True)
        try:
            table_rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {str(row[0]) for row in table_rows}
            response["database"] = "ready"
            if not REQUIRED_TABLES.issubset(tables):
                return response, 503
            response["database_schema"] = "ready"
            initialized = initialize_project_knowledge(settings)
            if not initialized:
                return response, 503
            response["project_knowledge_file"] = "ready"
            indexed = connection.execute(
                """
                SELECT 1 FROM knowledge_documents
                WHERE source_filename IN (?, ?)
                LIMIT 1
                """,
                (PROJECT_KNOWLEDGE_LOGICAL_NAME, "docs/PROJECT_KNOWLEDGE.md"),
            ).fetchone()
            response["project_knowledge_index"] = "ready" if indexed else "degraded"
        finally:
            connection.close()
    except (OSError, sqlite3.Error, RuntimeError):
        return response, 503

    if settings.app_env == "production" and not settings.deepseek_api_key:
        return response, 503
    response["ready"] = True
    response["status"] = (
        "ready" if response["project_knowledge_index"] == "ready" else "ready_with_warnings"
    )
    return response, 200


def _failure(component: str) -> dict[str, Any]:
    return {
        "ready": False,
        "version": APP_VERSION,
        "database": "not_ready",
        "database_schema": "not_ready",
        "project_knowledge_file": "not_ready",
        "project_knowledge_index": "not_ready",
        "llm_configuration": "not_configured" if component == "configuration" else "unknown",
        "status": "not_ready",
    }
