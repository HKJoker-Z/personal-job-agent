"""Bounded aggregate queries for the Version 2.0.2 dashboard."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationTask, AuditEvent, Job, JobImportRun, utc_now


class DashboardService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id

    def summary(self) -> dict[str, object]:
        now = utc_now()
        seven_days = now + timedelta(days=7)
        job_base = (Job.owner_user_id == self.owner_id, Job.archived_at.is_(None))
        application_base = (Application.owner_user_id == self.owner_id, Application.archived_at.is_(None))
        task_base = (ApplicationTask.owner_user_id == self.owner_id, ApplicationTask.archived_at.is_(None))
        stage_rows = self.db.execute(
            select(Application.current_stage, func.count()).where(*application_base).group_by(Application.current_stage)
        ).all()
        terminal = ("accepted", "rejected", "withdrawn", "closed")
        activity = list(self.db.execute(select(
            AuditEvent.event_type, AuditEvent.resource_type, AuditEvent.resource_id, AuditEvent.created_at
        ).where(AuditEvent.user_id == self.owner_id).order_by(AuditEvent.created_at.desc()).limit(20)).mappings())
        imports = list(self.db.scalars(select(JobImportRun).where(
            JobImportRun.owner_user_id == self.owner_id
        ).order_by(JobImportRun.started_at.desc()).limit(10)))
        deadlines = list(self.db.scalars(select(Job).where(
            *job_base, Job.application_deadline.is_not(None), Job.application_deadline >= now
        ).order_by(Job.application_deadline).limit(10)))
        return {
            "jobs_total": self._count(Job, *job_base),
            "jobs_new": self._count(Job, *job_base, Job.status == "new"),
            "jobs_shortlisted": self._count(Job, *job_base, Job.status == "shortlisted"),
            "applications_total": self._count(Application, *application_base),
            "applications_by_stage": {str(stage): int(count) for stage, count in stage_rows},
            "active_applications": self._count(Application, *application_base, Application.current_stage.not_in(terminal)),
            "tasks_pending": self._count(ApplicationTask, *task_base, ApplicationTask.status.in_(("pending", "in_progress"))),
            "tasks_overdue": self._count(ApplicationTask, *task_base, ApplicationTask.status.in_(("pending", "in_progress")), ApplicationTask.due_at < now),
            "tasks_due_next_7_days": self._count(ApplicationTask, *task_base, ApplicationTask.status.in_(("pending", "in_progress")), ApplicationTask.due_at >= now, ApplicationTask.due_at <= seven_days),
            "upcoming_deadlines": [{"job_id": str(item.id), "title": item.title, "company_name": item.company_name, "deadline": item.application_deadline.isoformat() if item.application_deadline else None} for item in deadlines],
            "recent_activity": [{**dict(item), "created_at": item["created_at"].isoformat()} for item in activity],
            "recent_imports": [{"id": str(item.id), "import_type": item.import_type, "status": item.status, "source_count": item.source_count, "created_count": item.created_count, "duplicate_count": item.duplicate_count, "failed_count": item.failed_count, "started_at": item.started_at.isoformat()} for item in imports],
        }

    def _count(self, model: type, *predicates: object) -> int:
        return int(self.db.scalar(select(func.count()).select_from(model).where(*predicates)) or 0)
