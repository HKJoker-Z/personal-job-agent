"""Bounded aggregates for the simplified Version 2.0.1 workspace."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentRun, ApplicationRecord, AuditEvent, Resume, ResumeVersion


class DashboardService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id

    def summary(self) -> dict[str, object]:
        activity = list(self.db.execute(select(
            AuditEvent.event_type, AuditEvent.resource_type, AuditEvent.resource_id, AuditEvent.created_at
        ).where(AuditEvent.user_id == self.owner_id).order_by(AuditEvent.created_at.desc()).limit(20)).mappings())
        active_run_statuses = ("queued", "running", "waiting_for_approval", "retry_scheduled")
        return {
            "resumes_total": self._count(Resume, Resume.user_id == self.owner_id, Resume.archived_at.is_(None)),
            "resume_versions_total": int(self.db.scalar(select(func.count()).select_from(ResumeVersion).join(Resume, Resume.id == ResumeVersion.resume_id).where(Resume.user_id == self.owner_id)) or 0),
            "history_total": self._count(ApplicationRecord, ApplicationRecord.owner_user_id == self.owner_id),
            "agent_runs_total": self._count(AgentRun, AgentRun.owner_user_id == self.owner_id),
            "agent_runs_active": self._count(AgentRun, AgentRun.owner_user_id == self.owner_id, AgentRun.status.in_(active_run_statuses)),
            "recent_activity": [{**dict(item), "created_at": item["created_at"].isoformat()} for item in activity],
        }

    def _count(self, model: type, *predicates: object) -> int:
        return int(self.db.scalar(select(func.count()).select_from(model).where(*predicates)) or 0)
