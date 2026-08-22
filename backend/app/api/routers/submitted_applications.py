"""Version 2.1.0 submitted Application creation endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from analysis_fallback import structure_aware_truncate
from app.analyze.input_preparation import _extract_uploaded_resume
from app.api.dependencies import CurrentUser, DbSession
from app.applications.schemas import ApplicationCreate
from app.applications.service import (
    ApplicationConflict,
    ApplicationNotFound,
    ApplicationService,
)
from config import load_config
from security_utils import prepare_resume_for_llm


router = APIRouter(prefix="/api/applications", tags=["applications"])


def _raise(exc: Exception) -> None:
    if isinstance(exc, ApplicationNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ApplicationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    if payload.job_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Company Name and Job Title are required.",
        )
    try:
        return ApplicationService(db, user.id).create(payload.model_dump())
    except (ApplicationConflict, ApplicationNotFound) as exc:
        _raise(exc)


@router.delete("/{application_id}")
def delete_application(
    application_id: UUID, db: DbSession, user: CurrentUser
) -> dict[str, object]:
    try:
        ApplicationService(db, user.id).delete(application_id)
        return {"deleted": True, "id": str(application_id)}
    except ApplicationNotFound as exc:
        _raise(exc)


@router.post("/from-analysis", status_code=status.HTTP_201_CREATED)
async def create_application_from_analysis(
    db: DbSession,
    user: CurrentUser,
    company_name: str = Form(..., min_length=1, max_length=500),
    job_title: str = Form(..., min_length=1, max_length=500),
    job_description: str = Form("", max_length=200_000),
    source_analysis_id: int | None = Form(None, ge=1),
    resume_version_id: str | None = Form(None),
    resume: UploadFile | None = File(None),
) -> dict[str, object]:
    if resume is not None and resume_version_id:
        raise HTTPException(status_code=400, detail="Provide only one Resume source.")

    resume_snapshot = None
    if resume is not None:
        config = load_config()
        parsed = await _extract_uploaded_resume(resume, config)
        parsed, _ = structure_aware_truncate(
            parsed, config.analysis_resume_max_chars
        )
        resume_snapshot, _ = prepare_resume_for_llm(parsed)

    payload = ApplicationCreate(
        company_name=company_name,
        job_title=job_title,
        job_description=job_description,
        source_analysis_id=source_analysis_id,
        resume_version_id=resume_version_id or None,
    )
    try:
        return ApplicationService(db, user.id).create_submitted(
            payload.model_dump(), resume_snapshot=resume_snapshot
        )
    except (ApplicationConflict, ApplicationNotFound) as exc:
        _raise(exc)
