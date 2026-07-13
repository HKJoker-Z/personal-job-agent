"""Ownership-scoped Application, Note, and Task persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from app.db.models import Application, ApplicationNote, ApplicationStageHistory, ApplicationTask


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, owner_id: UUID, application_id: UUID, *, include_archived: bool = False, for_update: bool = False) -> Application | None:
        statement = select(Application).where(Application.id == application_id, Application.owner_user_id == owner_id)
        if not include_archived:
            statement = statement.where(Application.archived_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def active_for_job(self, owner_id: UUID, job_id: UUID) -> Application | None:
        return self.db.scalar(select(Application).where(
            Application.owner_user_id == owner_id,
            Application.job_id == job_id,
            Application.archived_at.is_(None),
        ))

    def list(self, owner_id: UUID, stage: str | None = None, archived: bool = False) -> list[Application]:
        statement = select(Application).where(Application.owner_user_id == owner_id)
        statement = statement.where(Application.archived_at.is_not(None) if archived else Application.archived_at.is_(None))
        if stage:
            statement = statement.where(Application.current_stage == stage)
        return list(self.db.scalars(statement.order_by(Application.updated_at.desc(), Application.id)))

    def history(self, owner_id: UUID, application_id: UUID) -> list[ApplicationStageHistory]:
        return list(self.db.scalars(select(ApplicationStageHistory).where(
            ApplicationStageHistory.owner_user_id == owner_id,
            ApplicationStageHistory.application_id == application_id,
        ).order_by(ApplicationStageHistory.changed_at, ApplicationStageHistory.id)))

    def notes(self, owner_id: UUID, application_id: UUID) -> list[ApplicationNote]:
        return list(self.db.scalars(select(ApplicationNote).where(
            ApplicationNote.owner_user_id == owner_id,
            ApplicationNote.application_id == application_id,
            ApplicationNote.deleted_at.is_(None),
        ).order_by(ApplicationNote.created_at.desc())))

    def note(self, owner_id: UUID, application_id: UUID, note_id: UUID, for_update: bool = False) -> ApplicationNote | None:
        statement = select(ApplicationNote).where(
            ApplicationNote.id == note_id,
            ApplicationNote.owner_user_id == owner_id,
            ApplicationNote.application_id == application_id,
            ApplicationNote.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)


TASK_SORTS = {
    "due_at": ApplicationTask.due_at,
    "created_at": ApplicationTask.created_at,
    "updated_at": ApplicationTask.updated_at,
    "priority": ApplicationTask.priority,
    "status": ApplicationTask.status,
}


class TaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, owner_id: UUID, task_id: UUID, *, include_archived: bool = False, for_update: bool = False) -> ApplicationTask | None:
        statement = select(ApplicationTask).where(
            ApplicationTask.id == task_id, ApplicationTask.owner_user_id == owner_id
        )
        if not include_archived:
            statement = statement.where(ApplicationTask.archived_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def list(self, owner_id: UUID, filters: dict[str, object], sort: str) -> list[ApplicationTask]:
        statement = select(ApplicationTask).where(ApplicationTask.owner_user_id == owner_id)
        archived = bool(filters.get("archived"))
        statement = statement.where(ApplicationTask.archived_at.is_not(None) if archived else ApplicationTask.archived_at.is_(None))
        for key, column in (
            ("status", ApplicationTask.status), ("priority", ApplicationTask.priority),
            ("application_id", ApplicationTask.application_id), ("job_id", ApplicationTask.job_id),
            ("task_type", ApplicationTask.task_type),
        ):
            if filters.get(key) is not None:
                statement = statement.where(column == filters[key])
        if filters.get("due_before"):
            statement = statement.where(ApplicationTask.due_at <= filters["due_before"])
        if filters.get("due_after"):
            statement = statement.where(ApplicationTask.due_at >= filters["due_after"])
        if filters.get("overdue"):
            statement = statement.where(
                ApplicationTask.due_at < datetime.now().astimezone(),
                ApplicationTask.status.not_in(("completed", "cancelled")),
            )
        descending = sort.startswith("-")
        column = TASK_SORTS.get(sort.removeprefix("-"))
        if column is None:
            raise ValueError("Unsupported Task sort field.")
        return list(self.db.scalars(statement.order_by(desc(column) if descending else asc(column), ApplicationTask.id)))
