"""Input validation and preparation for the Analyze workflow."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, NoReturn

from docx import Document
from fastapi import HTTPException, Request, UploadFile
from pypdf import PdfReader

from agent_workflow import AgentWorkflow, WorkflowContext
from analysis_fallback import normalize_analysis_text, structure_aware_truncate
from app.jobs.acquisition import SafeJobUrlFetcher, UnsafeJobUrl
from config import AppConfig


logger = logging.getLogger("personal-job-agent")
FailureHandler = Callable[..., NoReturn]


@dataclass
class PreparedAnalyzeInput:
    context: WorkflowContext
    resume_version_id: str
    warnings: list[str]


def analyze_error_detail(
    message: str,
    error_code: str,
    error_stage: str,
    *,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "message": message,
        "error_code": error_code,
        "error_stage": error_stage,
        "details": details or {},
    }


def _input_error(
    status_code: int,
    message: str,
    error_code: str,
    error_stage: str,
    *,
    field_name: str | None = None,
) -> HTTPException:
    details = {"field": field_name} if field_name else None
    return HTTPException(
        status_code=status_code,
        detail=analyze_error_detail(
            message,
            error_code,
            error_stage,
            details=details,
        ),
    )


def clamp_rag_top_k(value: int) -> int:
    return max(1, min(10, int(value)))


def resolve_rag_mode(use_knowledge_base: bool, rag_mode: str | None) -> str:
    if not use_knowledge_base:
        return "off"

    clean_mode = ("" if rag_mode is None else str(rag_mode)).strip().lower()
    if not clean_mode or clean_mode == "all":
        return "project"
    if clean_mode in {"project", "off"}:
        return clean_mode

    raise HTTPException(status_code=400, detail="rag_mode must be either 'project' or 'off'.")


def _extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_docx_text(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs).strip()


async def _extract_uploaded_resume(resume: UploadFile, config: AppConfig) -> str:
    filename = (resume.filename or "").lower()
    file_bytes = await resume.read()

    if not file_bytes:
        logger.warning("Resume parsing failed error_type=EmptyUpload")
        raise HTTPException(status_code=400, detail="Uploaded resume file is empty.")
    if len(file_bytes) > config.max_upload_size_bytes:
        logger.warning("Resume parsing failed error_type=FileTooLarge")
        raise HTTPException(
            status_code=400,
            detail=(
                "Resume file is too large. Maximum size is "
                f"{config.max_upload_size_mb} MB."
            ),
        )

    try:
        if filename.endswith(".pdf"):
            text = _extract_pdf_text(file_bytes)
        elif filename.endswith(".docx"):
            text = _extract_docx_text(file_bytes)
        else:
            logger.warning("Resume parsing failed error_type=UnsupportedFileType")
            raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Resume parsing failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail="Failed to parse resume. Please upload a valid PDF or DOCX file.",
        ) from exc

    text = normalize_analysis_text(text)
    if not text:
        logger.warning("Resume parsing failed error_type=NoExtractedText")
        raise HTTPException(status_code=400, detail="Could not extract text from the resume.")
    return text


def _load_stored_resume(request: Request, resume_version_id: str) -> str:
    from uuid import UUID

    from app.core.config import load_v2_settings
    from app.resumes.service import ResumeConflict, ResumeNotFound, ResumeService

    current_user = getattr(request.state, "v2_user", None)
    current_db = getattr(request.state, "v2_db", None)
    if current_user is None or current_db is None:
        raise _input_error(
            401,
            "Authentication required.",
            "AUTHENTICATION_REQUIRED",
            "authentication",
        )
    try:
        version_id = UUID(resume_version_id)
    except ValueError as exc:
        raise _input_error(
            400,
            "Resume Version ID is invalid.",
            "RESUME_SOURCE_INVALID",
            "parse_resume",
            field_name="resume_version_id",
        ) from exc
    try:
        return ResumeService(
            current_db, current_user.id, load_v2_settings()
        ).analysis_text(version_id)
    except ResumeNotFound as exc:
        raise _input_error(
            404,
            "Resume Version not found.",
            "RESUME_NOT_FOUND",
            "parse_resume",
        ) from exc
    except ResumeConflict as exc:
        raise _input_error(
            400,
            "Resume Version has no analyzable content.",
            "RESUME_PARSING_FAILED",
            "parse_resume",
        ) from exc


def _fetch_job_text(job_url: str) -> str:
    try:
        return SafeJobUrlFetcher().fetch(job_url).description
    except UnsafeJobUrl as exc:
        logger.warning("JD fetch failed error_type=UnsafeOrUnavailableUrl")
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch job URL safely. Please paste the job description instead.",
        ) from exc


def _validate_resume_source(
    resume: UploadFile | None,
    resume_version_id: str | None,
    config: AppConfig,
) -> tuple[str, str | None]:
    clean_resume_version_id = (resume_version_id or "").strip()
    if (resume is None) == (not clean_resume_version_id):
        logger.warning("Analyze request rejected error_type=MissingResume")
        raise _input_error(
            400,
            "Provide exactly one resume source: an upload or resume_version_id.",
            "RESUME_SOURCE_INVALID",
            "validate_input",
            field_name="resume",
        )

    resume_filename = (resume.filename or "") if resume else ""
    if resume is not None and not resume_filename.lower().endswith((".pdf", ".docx")):
        logger.warning("Analyze request rejected error_type=UnsupportedResumeType")
        raise _input_error(
            400,
            "Resume must be a PDF or DOCX file.",
            "RESUME_SOURCE_INVALID",
            "validate_input",
            field_name="resume",
        )

    upload_size = getattr(resume, "size", None)
    if isinstance(upload_size, int) and upload_size > config.max_upload_size_bytes:
        logger.warning("Analyze request rejected error_type=ResumeTooLarge")
        raise _input_error(
            400,
            f"Resume file is too large. Maximum size is {config.max_upload_size_mb} MB.",
            "RESUME_SOURCE_INVALID",
            "validate_input",
            field_name="resume",
        )

    display_name = resume_filename or (
        "Stored Resume Version" if clean_resume_version_id else None
    )
    return clean_resume_version_id, display_name


def _validate_job_source(
    job_text: str | None,
    job_url: str | None,
) -> tuple[str, str]:
    clean_job_text = (job_text or "").strip()
    clean_job_url = (job_url or "").strip()
    if sum(bool(value) for value in (clean_job_text, clean_job_url)) != 1:
        logger.warning("Analyze request rejected error_type=MissingJobInput")
        raise _input_error(
            400,
            "Provide exactly one job source: job description text or job URL.",
            "JOB_SOURCE_INVALID",
            "validate_input",
            field_name="job",
        )
    return clean_job_text, clean_job_url


def _validate_input(
    *,
    resume: UploadFile | None,
    resume_version_id: str | None,
    job_text: str | None,
    job_url: str | None,
    use_knowledge_base: bool,
    use_project_knowledge: bool | None,
    rag_top_k: int,
    project_knowledge_top_k: int | None,
    rag_mode: str | None,
    workflow: AgentWorkflow,
    context: WorkflowContext,
    config: AppConfig,
    failure_handler: FailureHandler,
) -> tuple[str, str]:
    workflow.start_step("validate_input", "Validate Input")
    try:
        clean_resume_version_id, resume_filename = _validate_resume_source(
            resume, resume_version_id, config
        )
        clean_job_text, clean_job_url = _validate_job_source(job_text, job_url)

        effective_use_project_knowledge = (
            use_knowledge_base
            if use_project_knowledge is None
            else use_project_knowledge
        )
        context.resume_filename = resume_filename
        context.job_url = clean_job_url or None
        context.source_type = "text" if clean_job_text else "url"
        context.rag_mode = resolve_rag_mode(effective_use_project_knowledge, rag_mode)
        context.rag_top_k = clamp_rag_top_k(
            project_knowledge_top_k
            if project_knowledge_top_k is not None
            else rag_top_k
        )
        workflow.complete_step(
            "validate_input",
            f"Input accepted. RAG mode: {context.rag_mode}; top_k: {context.rag_top_k}.",
        )
        return clean_resume_version_id, clean_job_text
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="validate_input",
            message="Input validation failed.",
            error_code="REQUEST_VALIDATION_FAILED",
            exc=exc,
        )


async def _parse_resume(
    resume_version_id: str,
    *,
    request: Request,
    resume: UploadFile | None,
    warnings: list[str],
    workflow: AgentWorkflow,
    context: WorkflowContext,
    config: AppConfig,
    failure_handler: FailureHandler,
) -> None:
    workflow.start_step("parse_resume", "Parse Resume")
    try:
        if resume_version_id:
            resume_text = _load_stored_resume(request, resume_version_id)
            context.source_type = "saved_resume_version"
        else:
            assert resume is not None
            resume_text = await _extract_uploaded_resume(resume, config)
        resume_text, resume_was_truncated = structure_aware_truncate(
            resume_text, config.analysis_resume_max_chars
        )
        if not resume_text.strip():
            raise _input_error(
                400,
                "Resume text is required for analysis.",
                "RESUME_PARSING_FAILED",
                "parse_resume",
            )
        context.resume_text = resume_text
        logger.info("Resume parsing succeeded characters=%s", len(resume_text))
        if resume_was_truncated:
            logger.info(
                "Resume text truncated characters=%s",
                config.analysis_resume_max_chars,
            )
            workflow.add_warning()
            warnings.append(
                "Resume input exceeded "
                f"{config.analysis_resume_max_chars} characters and was shortened by section."
            )
        workflow.complete_step(
            "parse_resume",
            f"Resume text extracted successfully from {context.resume_filename or 'uploaded file'}.",
        )
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="parse_resume",
            message="Resume parsing failed.",
            error_code="RESUME_PARSING_FAILED",
            exc=exc,
        )


def _acquire_job_description(
    *,
    clean_job_text: str,
    warnings: list[str],
    workflow: AgentWorkflow,
    context: WorkflowContext,
    config: AppConfig,
    failure_handler: FailureHandler,
) -> None:
    workflow.start_step("acquire_job_description", "Acquire Job Description")
    try:
        if clean_job_text:
            job_description = clean_job_text
            source_message = "Used pasted job description text."
            logger.info("JD text received characters=%s", len(job_description))
        else:
            job_description = _fetch_job_text(context.job_url or "")
            source_message = "Fetched job description from the provided URL."
            logger.info("JD fetch succeeded characters=%s", len(job_description))

        job_description, jd_was_truncated = structure_aware_truncate(
            job_description, config.analysis_job_description_max_chars
        )
        if not job_description.strip():
            raise _input_error(
                400,
                "Job Description text is required for analysis.",
                "JOB_DESCRIPTION_ACQUISITION_FAILED",
                "acquire_job_description",
            )
        context.job_text = job_description
        if jd_was_truncated:
            logger.info(
                "JD text truncated characters=%s",
                config.analysis_job_description_max_chars,
            )
            workflow.add_warning()
            warnings.append(
                "Job Description exceeded "
                f"{config.analysis_job_description_max_chars} characters and was shortened by section."
            )
        workflow.complete_step("acquire_job_description", source_message)
    except Exception as exc:
        failure_handler(
            workflow,
            context,
            step_key="acquire_job_description",
            message="Could not acquire job description.",
            error_code="JOB_DESCRIPTION_ACQUISITION_FAILED",
            exc=exc,
        )


async def prepare_analyze_input(
    *,
    request: Request,
    resume: UploadFile | None,
    resume_version_id: str | None,
    job_text: str | None,
    job_url: str | None,
    use_knowledge_base: bool,
    use_project_knowledge: bool | None,
    rag_top_k: int,
    project_knowledge_top_k: int | None,
    rag_mode: str | None,
    workflow: AgentWorkflow,
    config: AppConfig,
    failure_handler: FailureHandler,
) -> PreparedAnalyzeInput:
    context = WorkflowContext(workflow_id=workflow.workflow_id)
    warnings: list[str] = []
    clean_resume_version_id, clean_job_text = _validate_input(
        resume=resume,
        resume_version_id=resume_version_id,
        job_text=job_text,
        job_url=job_url,
        use_knowledge_base=use_knowledge_base,
        use_project_knowledge=use_project_knowledge,
        rag_top_k=rag_top_k,
        project_knowledge_top_k=project_knowledge_top_k,
        rag_mode=rag_mode,
        workflow=workflow,
        context=context,
        config=config,
        failure_handler=failure_handler,
    )
    await _parse_resume(
        clean_resume_version_id,
        request=request,
        resume=resume,
        warnings=warnings,
        workflow=workflow,
        context=context,
        config=config,
        failure_handler=failure_handler,
    )
    _acquire_job_description(
        clean_job_text=clean_job_text,
        warnings=warnings,
        workflow=workflow,
        context=context,
        config=config,
        failure_handler=failure_handler,
    )
    return PreparedAnalyzeInput(
        context=context,
        resume_version_id=clean_resume_version_id,
        warnings=warnings,
    )
