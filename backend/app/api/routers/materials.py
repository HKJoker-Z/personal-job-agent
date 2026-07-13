"""Application Package and evidence-grounded Material endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DbSession
from app.materials.schemas import (
    AnswerRequest,
    EvidenceConfirmation,
    GenerateRequest,
    MaterialEdit,
    MaterialFinalize,
    MaterialReviewRequest,
    PackageApprove,
    PackageCreate,
    PackagePatch,
    PackageRevision,
)
from app.materials.generator import MaterialGenerationError, MaterialGenerationTimeout
from app.materials.service import MaterialConflict, MaterialNotFound, MaterialService


router = APIRouter(tags=["application-materials"])


def _service(db: DbSession, user: CurrentUser) -> MaterialService:
    return MaterialService(db, user.id)


def _raise(exc: Exception) -> None:
    if isinstance(exc, MaterialNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MaterialConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, MaterialGenerationTimeout):
        raise HTTPException(status_code=504, detail="Application Material generation timed out.") from exc
    if isinstance(exc, MaterialGenerationError):
        raise HTTPException(status_code=502, detail="Application Material generation failed security validation.") from exc
    raise HTTPException(status_code=400, detail="Application Material request is invalid.") from exc


@router.post("/api/applications/{application_id}/packages", status_code=status.HTTP_201_CREATED)
def create_package(application_id: UUID, payload: PackageCreate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).create_package(application_id, payload.model_dump())
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.get("/api/applications/{application_id}/packages")
def list_packages(application_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).packages(application_id)
    except MaterialNotFound as exc:
        _raise(exc)


@router.get("/api/application-packages/{package_id}")
def get_package(package_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).package(package_id)
    except MaterialNotFound as exc:
        _raise(exc)


@router.patch("/api/application-packages/{package_id}")
def patch_package(package_id: UUID, payload: PackagePatch, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).update_package(package_id, payload.expected_revision, payload.title)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/application-packages/{package_id}/archive")
def archive_package(package_id: UUID, payload: PackageRevision, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).archive_package(package_id, payload.expected_revision)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/application-packages/{package_id}/approve")
def approve_package(package_id: UUID, payload: PackageApprove, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).approve_package(package_id, payload.expected_revision)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/application-packages/{package_id}/generate-resume")
def generate_resume(package_id: UUID, payload: GenerateRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).generate_resume(package_id, payload.force_new)
    except (MaterialNotFound, MaterialConflict, MaterialGenerationError) as exc:
        _raise(exc)


@router.post("/api/application-packages/{package_id}/generate-cover-letter")
def generate_cover_letter(package_id: UUID, payload: GenerateRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).generate_cover_letter(package_id, payload.force_new)
    except (MaterialNotFound, MaterialConflict, MaterialGenerationError) as exc:
        _raise(exc)


@router.post("/api/application-packages/{package_id}/answers")
def generate_answers(package_id: UUID, payload: AnswerRequest, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).generate_answers(package_id, payload.model_dump()["questions"])
    except (MaterialNotFound, MaterialConflict, MaterialGenerationError) as exc:
        _raise(exc)


@router.get("/api/application-materials/{material_id}")
def get_material(material_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).material(material_id)
    except MaterialNotFound as exc:
        _raise(exc)


@router.get("/api/application-materials/{material_id}/versions")
def material_versions(material_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).versions(material_id)
    except MaterialNotFound as exc:
        _raise(exc)


@router.post("/api/application-materials/{material_id}/versions", status_code=status.HTTP_201_CREATED)
def edit_material(material_id: UUID, payload: MaterialEdit, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).edit(
            material_id, payload.expected_active_version_id, payload.content_json,
            payload.content_text, payload.change_summary,
        )
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/material-versions/{version_id}/validate")
def validate_material(version_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).validate(version_id)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.get("/api/material-versions/{version_id}/evidence")
def material_evidence(version_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).evidence(version_id)
    except MaterialNotFound as exc:
        _raise(exc)


@router.post("/api/material-versions/{version_id}/evidence/{evidence_id}/confirm")
def confirm_material_evidence(
    version_id: UUID, evidence_id: UUID, _payload: EvidenceConfirmation,
    db: DbSession, user: CurrentUser,
) -> dict[str, object]:
    try:
        return _service(db, user).confirm_evidence(version_id, evidence_id)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/material-versions/{version_id}/review")
def review_material(version_id: UUID, payload: MaterialReviewRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).review(version_id, payload.decision, payload.notes)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)


@router.post("/api/material-versions/{version_id}/finalize")
def finalize_material(version_id: UUID, _payload: MaterialFinalize, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).finalize(version_id)
    except (MaterialNotFound, MaterialConflict) as exc:
        _raise(exc)
