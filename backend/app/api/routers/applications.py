"""Application pipeline, Stage History, Notes, and resume-link endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.applications.schemas import (
    ApplicationCreate, ApplicationPatch, ApplicationTransition, ExpectedRevision,
    NoteCreate, NotePatch, ReopenApplication, ResumeLink,
)
from app.applications.service import (
    ApplicationConflict, ApplicationNotFound, ApplicationService, InvalidTransition,
)
from app.jobs.service import JobNotFound


router = APIRouter(prefix="/api/applications", tags=["applications"])


def _service(db: DbSession, user: CurrentUser) -> ApplicationService:
    return ApplicationService(db, user.id)


def _raise(exc: Exception) -> None:
    if isinstance(exc, (ApplicationNotFound, JobNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, InvalidTransition):
        raise HTTPException(status_code=409, detail={"message": str(exc), "current_stage": exc.current, "allowed_next_stages": list(exc.allowed)}) from exc
    if isinstance(exc, ApplicationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_applications(db: DbSession, user: CurrentUser, stage_filter: str | None = Query(default=None, alias="stage"), archived: bool = False) -> list[dict[str, object]]:
    return _service(db, user).list(stage_filter, archived)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).create(payload.model_dump())
    except (ApplicationConflict, ApplicationNotFound, JobNotFound) as exc:
        _raise(exc)


@router.get("/{application_id:uuid}")
def get_application(application_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).get(application_id)
    except ApplicationNotFound as exc:
        _raise(exc)


@router.patch("/{application_id:uuid}")
def patch_application(application_id: UUID, payload: ApplicationPatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).update(application_id, payload.model_dump(exclude_unset=True))
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.delete("/{application_id:uuid}")
@router.post("/{application_id:uuid}/archive")
def archive_application(application_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).archive(application_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.api_route("/{application_id}", methods=["GET", "PATCH", "DELETE", "POST"])
def invalid_application_id(application_id: str) -> None:
    raise HTTPException(status_code=404, detail="Application not found.")


@router.post("/{application_id:uuid}/restore")
def restore_application(application_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).restore(application_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.post("/{application_id:uuid}/transition")
def transition(application_id: UUID, payload: ApplicationTransition, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).transition(
            application_id, payload.to_stage, payload.expected_revision, payload.reason,
            payload.notes, payload.occurred_at,
        )
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.post("/{application_id:uuid}/reopen")
def reopen(application_id: UUID, payload: ReopenApplication, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).reopen(application_id, payload.expected_revision, payload.reason)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.get("/{application_id:uuid}/history")
def history(application_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).history(application_id)
    except ApplicationNotFound as exc:
        _raise(exc)


@router.post("/{application_id:uuid}/resume")
def link_resume(application_id: UUID, payload: ResumeLink, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).link_resume(application_id, payload.resume_version_id, payload.expected_revision)
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.get("/{application_id:uuid}/notes")
def notes(application_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).notes(application_id)
    except ApplicationNotFound as exc:
        _raise(exc)


@router.post("/{application_id:uuid}/notes", status_code=status.HTTP_201_CREATED)
def add_note(application_id: UUID, payload: NoteCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).add_note(application_id, payload.model_dump())
    except ApplicationNotFound as exc:
        _raise(exc)


@router.patch("/{application_id:uuid}/notes/{note_id:uuid}")
def patch_note(application_id: UUID, note_id: UUID, payload: NotePatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).update_note(application_id, note_id, payload.model_dump(exclude_unset=True))
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.delete("/{application_id:uuid}/notes/{note_id:uuid}")
def delete_note(application_id: UUID, note_id: UUID, payload: ExpectedRevision, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    try:
        _service(db, user).delete_note(application_id, note_id, payload.expected_revision)
        return {"deleted": True}
    except (ApplicationNotFound, ApplicationConflict) as exc:
        _raise(exc)


@router.get("/{application_id:uuid}/suggested-tasks")
def suggested_tasks(application_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).suggested_tasks(application_id)
    except ApplicationNotFound as exc:
        _raise(exc)
