"""Owned Resume, Version, import, and private file endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.api.dependencies import CurrentUser, DbSession
from app.core.config import load_v2_settings
from app.profile.service import ProfileService, StaleProfile
from app.resumes.schemas import (
    ResumeCreate,
    ResumeImportConfirmation,
    ResumeUpdate,
    ResumeVersionCreate,
)
from app.resumes.service import ResumeConflict, ResumeNotFound, ResumeService, _serialize
from app.storage.validation import UnsafeUpload, safe_display_filename


router = APIRouter(tags=["resumes"])


def _service(db: DbSession, user: CurrentUser) -> ResumeService:
    return ResumeService(db, user.id, load_v2_settings())


def _raise(exc: Exception) -> None:
    if isinstance(exc, ResumeNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (ResumeConflict, StaleProfile)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/resumes")
def list_resumes(db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    return _service(db, user).list()


@router.post("/api/resumes", status_code=status.HTTP_201_CREATED)
def create_resume(payload: ResumeCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    return _service(db, user).create(payload.model_dump())


@router.get("/api/resumes/{resume_id}")
def get_resume(resume_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).get(resume_id)
    except ResumeNotFound as exc:
        _raise(exc)


@router.patch("/api/resumes/{resume_id}")
def patch_resume(
    resume_id: UUID, payload: ResumeUpdate, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    try:
        return _service(db, user).update(resume_id, payload.model_dump(exclude_unset=True))
    except ResumeNotFound as exc:
        _raise(exc)


@router.delete("/api/resumes/{resume_id}")
def archive_resume(resume_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    try:
        _service(db, user).archive(resume_id)
        return {"archived": True}
    except ResumeNotFound as exc:
        _raise(exc)


@router.get("/api/resumes/{resume_id}/versions")
def list_versions(
    resume_id: UUID, db: DbSession, user: CurrentUser
) -> list[dict[str, object]]:
    try:
        return _service(db, user).versions(resume_id)
    except ResumeNotFound as exc:
        _raise(exc)


@router.post("/api/resumes/{resume_id}/versions", status_code=status.HTTP_201_CREATED)
def create_version(
    resume_id: UUID,
    payload: ResumeVersionCreate,
    db: DbSession,
    user: CurrentUser,
) -> dict[str, object]:
    try:
        return _service(db, user).create_version(
            resume_id,
            payload.content.model_dump(mode="json"),
            payload.parent_version_id,
            payload.change_summary,
        )
    except (ResumeNotFound, ValueError) as exc:
        _raise(exc)


@router.get("/api/resumes/{resume_id}/versions/{version_id}")
def get_version(
    resume_id: UUID, version_id: UUID, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    try:
        return _service(db, user).version(resume_id, version_id)
    except ResumeNotFound as exc:
        _raise(exc)


@router.post("/api/resumes/{resume_id}/versions/{version_id}/finalize")
def finalize_version(
    resume_id: UUID, version_id: UUID, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    try:
        return _service(db, user).finalize(resume_id, version_id)
    except (ResumeNotFound, ResumeConflict) as exc:
        _raise(exc)


@router.post("/api/resumes/{resume_id}/versions/{version_id}/set-active")
def set_active_version(
    resume_id: UUID, version_id: UUID, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    try:
        return _service(db, user).set_active(resume_id, version_id)
    except ResumeNotFound as exc:
        _raise(exc)


@router.get("/api/resumes/{resume_id}/diff")
def resume_diff(
    resume_id: UUID,
    db: DbSession,
    user: CurrentUser,
    from_version_id: UUID = Query(...),
    to_version_id: UUID = Query(...),
) -> dict[str, object]:
    try:
        return _service(db, user).diff(resume_id, from_version_id, to_version_id)
    except ResumeNotFound as exc:
        _raise(exc)


@router.post("/api/files/resume", status_code=status.HTTP_201_CREATED)
async def upload_resume_file(
    db: DbSession, user: CurrentUser, file: UploadFile = File(...)
) -> dict[str, object]:
    try:
        data = await file.read(load_v2_settings().max_stored_file_size_bytes + 1)
        asset, duplicate = _service(db, user).upload_file(
            file.filename or "resume", file.content_type or "", data
        )
        return {"file": _serialize(asset), "duplicate": duplicate}
    except (UnsafeUpload, ValueError) as exc:
        _raise(exc)


@router.get("/api/files/{file_id}/metadata")
def file_metadata(file_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _serialize(_service(db, user).file(file_id))
    except ResumeNotFound as exc:
        _raise(exc)


@router.get("/api/files/{file_id}/download")
def download_file(file_id: UUID, db: DbSession, user: CurrentUser) -> Response:
    try:
        service = _service(db, user)
        asset = service.file(file_id)
        data = service.file_path(asset).read_bytes()
        safe_name = safe_display_filename(asset.original_filename).replace('"', "")
        return Response(
            data,
            media_type=asset.media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
                "Accept-Ranges": "none",
            },
        )
    except (ResumeNotFound, OSError) as exc:
        _raise(exc)


@router.delete("/api/files/{file_id}")
def delete_file(file_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, bool]:
    try:
        _service(db, user).delete_file(file_id)
        return {"deleted": True}
    except (ResumeNotFound, ResumeConflict) as exc:
        _raise(exc)


@router.post("/api/resumes/import", status_code=status.HTTP_201_CREATED)
async def import_resume(
    db: DbSession, user: CurrentUser, file: UploadFile = File(...)
) -> dict[str, object]:
    try:
        data = await file.read(load_v2_settings().max_stored_file_size_bytes + 1)
        return _service(db, user).import_resume(
            file.filename or "resume", file.content_type or "", data
        )
    except (UnsafeUpload, ResumeConflict, ValueError) as exc:
        _raise(exc)


@router.post("/api/resumes/import/confirm")
def confirm_import(
    payload: ResumeImportConfirmation, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    service = _service(db, user)
    try:
        if payload.action == "finalize":
            return {"version": service.finalize(payload.resume_id, payload.version_id)}
        if payload.profile_revision is None:
            raise ValueError("profile_revision is required for Profile copy.")
        version = service.repository.version(payload.resume_id, payload.version_id)
        resume = service.repository.resume(user.id, payload.resume_id)
        if resume is None or version is None:
            raise ResumeNotFound("Resume Version not found.")
        profile_service = ProfileService(db, user.id)
        copied = 0
        revision = payload.profile_revision
        resource_map = {"experience": "experiences", "education": "educations", "projects": "projects", "skills": "skills", "languages": "languages", "certifications": "certifications"}
        for section in version.content_json.get("sections", []):
            resource = resource_map.get(section.get("type"))
            if not resource:
                continue
            for item in section.get("items", []):
                if item.get("verification_status") != "confirmed":
                    continue
                profile_service.create_item(resource, item, revision)
                revision += 1
                copied += 1
        return {"copied_items": copied, "profile_revision": revision}
    except (ResumeNotFound, ResumeConflict, StaleProfile, ValueError) as exc:
        _raise(exc)
