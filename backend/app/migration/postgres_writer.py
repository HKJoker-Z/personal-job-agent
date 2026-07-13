"""Transactional Version 1 row migration into an Alembic-current PostgreSQL database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.security import normalize_email
from app.db.models import (
    AnalysisMetric,
    AnalysisStepMetric,
    ApplicationRecord,
    EvaluationResult,
    EvaluationRun,
    KnowledgeChunk,
    KnowledgeDocument,
    MigrationRun,
    User,
    utc_now,
)
from app.db.session import session_factory
from app.migration.sqlite_reader import SQLiteV1Reader, SourceMetadata
from app.migration.verification import aggregate_checksum
from app.readiness import ALEMBIC_HEAD


TABLE_MODELS = {
    "application_records": ApplicationRecord,
    "knowledge_documents": KnowledgeDocument,
    "knowledge_chunks": KnowledgeChunk,
    "analysis_metrics": AnalysisMetric,
    "analysis_step_metrics": AnalysisStepMetric,
    "evaluation_runs": EvaluationRun,
    "evaluation_results": EvaluationResult,
}
TABLE_ORDER = tuple(TABLE_MODELS)
JSON_TEXT_DEFAULTS = {
    "matched_skills": [],
    "missing_skills": [],
    "resume_suggestions": [],
    "scoring_breakdown": {},
    "ats_analysis": {},
    "upgraded_resume_bullets": [],
    "rag_sources": [],
    "workflow_steps": [],
    "next_action": {},
    "security_scan": {},
    "security_finding_codes": [],
    "checks_json": {},
}


class PostgreSQLV1Writer:
    def __init__(self, database_url: str):
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("Migration target must be PostgreSQL.")
        self.database_url = database_url
        self.factory = session_factory(database_url)

    def migrate(
        self,
        reader: SQLiteV1Reader,
        metadata: SourceMetadata,
        owner_email: str,
    ) -> dict[str, object]:
        db = self.factory()
        malformed_json = 0
        try:
            self._assert_revision(db)
            owner = db.scalar(select(User).where(User.normalized_email == normalize_email(owner_email)))
            if owner is None:
                raise ValueError("Migration owner user does not exist.")
            previous = db.scalar(
                select(MigrationRun).where(
                    MigrationRun.source_fingerprint == metadata.fingerprint
                )
            )
            if previous:
                return {
                    "status": "already_migrated",
                    "source_fingerprint": metadata.fingerprint,
                    "tables": previous.verification_summary,
                }
            report: dict[str, Any] = {}
            for table in TABLE_ORDER:
                if table not in metadata.tables:
                    report[table] = {"source": 0, "target": 0, "migrated": 0, "skipped": 0}
                    continue
                model = TABLE_MODELS[table]
                source_rows = list(reader.rows(table))
                ids = [row.get("id") for row in source_rows if row.get("id") is not None]
                if ids and db.scalar(select(model.id).where(model.id.in_(ids)).limit(1)) is not None:
                    raise ValueError("Target contains conflicting Version 1 primary keys.")
                migrated = 0
                for row in source_rows:
                    values, malformed = self._values(model, row, owner.id)
                    malformed_json += malformed
                    db.add(model(**values))
                    migrated += 1
                db.flush()
                self._synchronize_sequence(db, model.__tablename__)
                target_count = int(
                    db.scalar(select(text("count(*)")).select_from(model)) or 0
                )
                source_checksum = aggregate_checksum(source_rows)
                checksum_columns = [model.id]
                for name in ("run_id", "workflow_id", "created_at", "started_at"):
                    column = getattr(model, name, None)
                    if column is not None:
                        checksum_columns.append(column)
                target_rows = [
                    dict(row._mapping)
                    for row in db.execute(
                        select(*checksum_columns).order_by(model.id)
                    )
                ]
                report[table] = {
                    "source": len(source_rows),
                    "target": target_count,
                    "migrated": migrated,
                    "skipped": 0,
                    "source_checksum": source_checksum,
                    "target_checksum": aggregate_checksum(target_rows),
                }
                if target_count < len(source_rows):
                    raise RuntimeError("Migration row count verification failed.")
                if source_checksum != report[table]["target_checksum"]:
                    raise RuntimeError("Migration aggregate checksum verification failed.")
            run = MigrationRun(
                source_fingerprint=metadata.fingerprint,
                migration_version="v1-to-v2-phase1",
                started_at=utc_now(),
                completed_at=utc_now(),
                status="completed",
                row_count_summary={key: value["source"] for key, value in report.items()},
                verification_summary=report,
            )
            db.add(run)
            db.commit()
            reader.assert_unchanged()
            return {
                "status": "completed",
                "source_fingerprint": metadata.fingerprint,
                "malformed_json_normalized": malformed_json,
                "tables": report,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def verify(self, metadata: SourceMetadata) -> dict[str, object]:
        db = self.factory()
        try:
            self._assert_revision(db)
            run = db.scalar(
                select(MigrationRun).where(
                    MigrationRun.source_fingerprint == metadata.fingerprint
                )
            )
            if run is None or run.status != "completed":
                raise ValueError("No completed migration exists for this source fingerprint.")
            return {
                "status": "verified",
                "source_fingerprint": metadata.fingerprint,
                "tables": run.verification_summary,
            }
        finally:
            db.close()

    def _assert_revision(self, db: Session) -> None:
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if current != ALEMBIC_HEAD:
            raise ValueError("Target PostgreSQL is not at the required Alembic revision.")

    @staticmethod
    def _synchronize_sequence(db: Session, table_name: str) -> None:
        if table_name not in TABLE_MODELS:
            raise ValueError("Unknown migration sequence target.")
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM \"{table_name}\""
            )
        )

    @staticmethod
    def _values(model: type, source: dict[str, object], owner_id: UUID) -> tuple[dict[str, object], int]:
        mapper = inspect(model)
        values: dict[str, object] = {}
        malformed = 0
        for column in mapper.columns:
            key = column.key
            if key == "owner_user_id":
                values[key] = owner_id
                continue
            if key not in source:
                continue
            value = source[key]
            if key in JSON_TEXT_DEFAULTS and value is not None:
                try:
                    parsed = json.loads(str(value))
                    value = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
                except (TypeError, json.JSONDecodeError):
                    value = json.dumps(JSON_TEXT_DEFAULTS[key], separators=(",", ":"))
                    malformed += 1
            try:
                python_type = column.type.python_type
            except (AttributeError, NotImplementedError):
                python_type = None
            if python_type is datetime and isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
            values[key] = value
        return values, malformed
