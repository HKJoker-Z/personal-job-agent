"""Authenticated Job Library, import, requirement, duplicate, and merge API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import load_v2_settings
from app.jobs.acquisition import UnsafeJobUrl
from app.jobs.import_service import JobImportService, MAX_CSV_BYTES
from app.jobs.schemas import (
    DuplicateResolution,
    JobCreate,
    JobMergeRequest,
    JobPatch,
    ManualJobImport,
    RequirementCreate,
    RequirementPatch,
    RevisionRequest,
    UrlJobImport,
)
from app.jobs.service import JobConflict, JobNotFound, JobService
from app.storage.validation import UnsafeUpload


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _service(db: DbSession, user: CurrentUser) -> JobService:
    return JobService(db, user.id)


def _imports(db: DbSession, user: CurrentUser) -> JobImportService:
    return JobImportService(db, user.id, load_v2_settings())


def _raise(exc: Exception) -> None:
    if isinstance(exc, JobNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, JobConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, UnsafeJobUrl):
        raise HTTPException(status_code=400, detail="Job URL could not be imported safely.") from exc
    raise HTTPException(status_code=400, detail=str(exc) if len(str(exc)) < 240 else "Job request is invalid.") from exc


@router.post("/import/manual", status_code=status.HTTP_201_CREATED)
def import_manual(payload: ManualJobImport, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _imports(db, user).manual(payload.model_dump(exclude={"canonical_url"}))
    except (ValueError, JobConflict) as exc:
        _raise(exc)


@router.post("/import/url", status_code=status.HTTP_201_CREATED)
def import_url(payload: UrlJobImport, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _imports(db, user).url(payload.url)
    except (UnsafeJobUrl, ValueError, JobConflict) as exc:
        _raise(exc)


@router.post("/import/file", status_code=status.HTTP_201_CREATED)
async def import_file(db: DbSession, user: CurrentUser, file: UploadFile = File(...)) -> dict[str, object]:
    settings = load_v2_settings()
    try:
        data = await file.read(settings.max_stored_file_size_bytes + 1)
        return _imports(db, user).file(file.filename or "job", file.content_type or "", data)
    except (UnsafeUpload, ValueError, JobConflict) as exc:
        _raise(exc)


@router.get("/import/csv/template")
def csv_template(_user: CurrentUser) -> Response:
    return Response(
        JobImportService.template(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="job-import-template.csv"', "X-Content-Type-Options": "nosniff"},
    )


@router.post("/import/csv")
async def import_csv(
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
    validate_only: bool = Query(default=True),
) -> dict[str, object]:
    try:
        data = await file.read(MAX_CSV_BYTES + 1)
        return _imports(db, user).csv(data, validate_only)
    except ValueError as exc:
        _raise(exc)


@router.get("")
def list_jobs(
    db: DbSession,
    user: CurrentUser,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=25, ge=1, le=100),
    query: str | None = Query(default=None, max_length=300),
    company: str | None = Query(default=None, max_length=300),
    title: str | None = Query(default=None, max_length=300),
    location: str | None = Query(default=None, max_length=300),
    status_filter: str | None = Query(default=None, alias="status", max_length=30),
    employment_type: str | None = Query(default=None, max_length=80),
    work_mode: str | None = Query(default=None, max_length=80),
    source_type: str | None = Query(default=None, max_length=30),
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    deadline_before: datetime | None = None,
    deadline_after: datetime | None = None,
    archived: bool | None = False,
    sort: str = Query(default="-created_at", max_length=40),
) -> dict[str, object]:
    filters = {
        "query": query, "company": company.casefold() if company else None,
        "title": title.casefold() if title else None, "location": location.casefold() if location else None,
        "status": status_filter, "employment_type": employment_type, "work_mode": work_mode,
        "source_type": source_type, "created_after": created_after, "created_before": created_before,
        "deadline_before": deadline_before, "deadline_after": deadline_after, "archived": archived,
    }
    try:
        return _service(db, user).list(filters, offset, limit, sort)
    except ValueError as exc:
        _raise(exc)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).create(payload.model_dump())
    except (ValueError, JobConflict) as exc:
        _raise(exc)


@router.get("/{job_id}")
def get_job(job_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).get(job_id)
    except JobNotFound as exc:
        _raise(exc)


@router.patch("/{job_id}")
def patch_job(job_id: UUID, payload: JobPatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).update(job_id, payload.model_dump(exclude_unset=True))
    except (JobNotFound, JobConflict, ValueError) as exc:
        _raise(exc)


@router.delete("/{job_id}")
@router.post("/{job_id}/archive")
def archive_job(job_id: UUID, payload: RevisionRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).archive(job_id, payload.expected_revision)
    except (JobNotFound, JobConflict) as exc:
        _raise(exc)


@router.post("/{job_id}/restore")
def restore_job(job_id: UUID, payload: RevisionRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).restore(job_id, payload.expected_revision)
    except (JobNotFound, JobConflict) as exc:
        _raise(exc)


@router.get("/{job_id}/sources")
def job_sources(job_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).sources(job_id)
    except JobNotFound as exc:
        _raise(exc)


@router.get("/{job_id}/requirements")
def job_requirements(job_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).requirements(job_id)
    except JobNotFound as exc:
        _raise(exc)


@router.post("/{job_id}/requirements", status_code=status.HTTP_201_CREATED)
def add_requirement(job_id: UUID, payload: RequirementCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).add_requirement(job_id, payload.model_dump())
    except (JobNotFound, ValueError) as exc:
        _raise(exc)


@router.patch("/{job_id}/requirements/{requirement_id}")
def patch_requirement(job_id: UUID, requirement_id: UUID, payload: RequirementPatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).update_requirement(job_id, requirement_id, payload.model_dump(exclude_unset=True))
    except (JobNotFound, ValueError) as exc:
        _raise(exc)


@router.delete("/{job_id}/requirements/{requirement_id}")
def delete_requirement(job_id: UUID, requirement_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    try:
        _service(db, user).delete_requirement(job_id, requirement_id)
        return {"deleted": True}
    except JobNotFound as exc:
        _raise(exc)


@router.post("/{job_id}/extract-requirements")
def extract_requirements(job_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).extract_requirements(job_id)
    except (JobNotFound, ValueError) as exc:
        _raise(exc)


@router.get("/{job_id}/duplicates")
def duplicates(job_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).duplicates(job_id)
    except JobNotFound as exc:
        _raise(exc)


@router.post("/{job_id}/duplicates/{candidate_id}/resolve")
def resolve_duplicate(job_id: UUID, candidate_id: UUID, payload: DuplicateResolution, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).resolve_duplicate(job_id, candidate_id, payload.action)
    except (JobNotFound, JobConflict) as exc:
        _raise(exc)


@router.post("/{target_job_id}/merge")
def merge_jobs(target_job_id: UUID, payload: JobMergeRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).merge(
            target_job_id, payload.source_job_id, payload.expected_target_revision,
            payload.expected_source_revision, payload.field_selection,
        )
    except (JobNotFound, JobConflict, ValueError) as exc:
        _raise(exc)
