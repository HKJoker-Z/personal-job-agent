"""Owned task list and lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.applications.schemas import ExpectedRevision, TaskCreate, TaskPatch
from app.applications.service import ApplicationConflict, ApplicationNotFound, TaskService
from app.jobs.service import JobNotFound


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _raise(exc: Exception) -> None:
    if isinstance(exc, (ApplicationNotFound, JobNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ApplicationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_tasks(
    db: DbSession, user: CurrentUser, status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None, due_before: datetime | None = None, due_after: datetime | None = None,
    overdue: bool = False, application_id: UUID | None = None, job_id: UUID | None = None,
    task_type: str | None = None, archived: bool = False, sort: str = "due_at",
) -> list[dict[str, object]]:
    try:
        return TaskService(db, user.id).list({
            "status": status_filter, "priority": priority, "due_before": due_before, "due_after": due_after,
            "overdue": overdue, "application_id": application_id, "job_id": job_id,
            "task_type": task_type, "archived": archived,
        }, sort)
    except ValueError as exc:
        _raise(exc)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).create(payload.model_dump())
    except (ApplicationNotFound, ApplicationConflict, JobNotFound, ValueError) as exc:
        _raise(exc)


@router.get("/{task_id}")
def get_task(task_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).get(task_id)
    except ApplicationNotFound as exc:
        _raise(exc)


@router.patch("/{task_id}")
def patch_task(task_id: UUID, payload: TaskPatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).update(task_id, payload.model_dump(exclude_unset=True))
    except (ApplicationNotFound, ApplicationConflict, JobNotFound, ValueError) as exc:
        _raise(exc)


@router.delete("/{task_id}")
@router.post("/{task_id}/archive")
def archive_task(task_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).archive(task_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.post("/{task_id}/complete")
def complete_task(task_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).complete(task_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.post("/{task_id}/reopen")
def reopen_task(task_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return TaskService(db, user.id).reopen(task_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)
