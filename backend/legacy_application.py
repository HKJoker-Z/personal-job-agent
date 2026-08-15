import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from agent_workflow import AgentWorkflow, WorkflowContext
from analysis_contract import (
    MODEL_OUTPUT_EMPTY,
    MODEL_OUTPUT_RESOURCE_LIMIT,
    MODEL_OUTPUT_TRUNCATED,
    MODEL_PROVIDER_ERROR,
    CompactAnalysisOutput,
    ModelOutputError,
    ProviderAnalysisResponse,
    OPTIONAL_PROVIDER_NARRATIVE_FIELDS,
    adapt_provider_completion,
    compact_analysis_warnings,
    parse_model_json,
    parse_model_json_result,
    salvage_compact_analysis,
    salvage_warning_messages,
    safe_model_metadata,
    validate_compact_analysis,
)
from analysis_fallback import (
    deterministic_job_summary,
    deterministic_match_reasons,
    deterministic_scoring,
    keyword_skill_states,
    local_fallback_result,
)
from app.api.errors import (
    analyze_error_response,
    analyze_exception_response,
    is_analyze_request,
    request_id_for,
)
from app.analyze.idempotency import (
    AnalyzeIdempotencyService,
    IdempotencyError,
    hash_key as hash_idempotency_key,
    project_knowledge_version,
    request_fingerprint as analyze_request_fingerprint,
    validate_key as validate_idempotency_key,
)
from app.analyze.input_preparation import (
    analyze_error_detail,
    clamp_rag_top_k,
    prepare_analyze_input,
)
from app.analyze.normalization_client import JavaNormalizationClient
from app.analyze.normalization_runtime import select_effective_normalization
from app.materials.grounding import EvidenceSource, validate_claims, validation_summary
from config import APP_VERSION, load_config
from database import (
    ALLOWED_APPLICATION_STATUSES,
    ALLOWED_KNOWLEDGE_CATEGORIES,
    ALLOWED_NEXT_ACTION_DECISIONS,
    create_knowledge_document,
    delete_application_record,
    delete_knowledge_document,
    find_project_knowledge_document,
    get_application_record,
    get_knowledge_document,
    init_db,
    insert_application_record,
    list_application_records,
    list_knowledge_documents,
    rebuild_project_knowledge_document,
    search_knowledge_chunks,
    update_application_record,
    update_application_workflow_steps,
    update_next_action_decision,
)
from data_management_service import (
    DataManagementError,
    authorize_destructive_request,
    data_management_status,
    delete_evaluation_data,
    delete_monitoring_data,
    delete_trace,
    preview_evaluation_deletion,
    preview_monitoring_deletion,
)
from export_utils import (
    build_analysis_report_pdf,
    build_cover_letter_docx,
    build_export_filename,
)
from knowledge_utils import (
    build_text_chunks,
    clean_knowledge_text,
    extract_knowledge_file_text,
    validate_knowledge_filename,
)
from recommendation_engine import generate_next_action
from safe_prompt import build_safe_analysis_prompt
from security_utils import (
    POLICY_VERSION as SECURITY_POLICY_VERSION,
    empty_security_scan,
    merge_security_scans,
    normalized_security_scan,
    prepare_resume_for_llm,
    scan_and_sanitize_untrusted_text,
    scan_llm_output,
    scan_project_chunks,
    security_status_from_scan,
)
from monitoring_service import (
    build_analysis_metric,
    get_overview as get_monitoring_overview,
    get_rag_metrics,
    get_recommendation_metrics,
    get_security_metrics,
    get_trace_detail,
    get_workflow_step_performance,
    list_traces,
    monitoring_status,
    persist_analysis_metrics_best_effort,
)
from provider_deadline import (
    ANALYZE_TOTAL_SAFETY_DEADLINE_SECONDS,
    DeadlineHttpxClient,
    ProviderAttemptTimeout,
    ProviderDeadline,
)
from evaluation_service import (
    evaluation_status,
    get_evaluation_run,
    list_evaluation_runs,
    run_evaluation_suite,
)
from logging_utils import RequestLoggingMiddleware, configure_logging
from project_knowledge_runtime import (
    PROJECT_KNOWLEDGE_LOGICAL_NAME,
    get_project_knowledge_path,
    initialize_project_knowledge,
)
from readiness import readiness_status

ROOT_DIR = Path(__file__).resolve().parents[1]
if (os.getenv("APP_ENV", "development").strip().lower() or "development") == "development":
    load_dotenv(ROOT_DIR / ".env")
settings = load_config()

APP_NAME = "personal-job-agent"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = settings.deepseek_model
MAX_PROVIDER_CALLS_PER_ANALYZE = 3
MAX_PRIMARY_PROVIDER_CALLS = MAX_PROVIDER_CALLS_PER_ANALYZE - 1
PROJECT_KNOWLEDGE_SOURCE_PATH = PROJECT_KNOWLEDGE_LOGICAL_NAME
LEGACY_PROJECT_KNOWLEDGE_SOURCE_PATH = "docs/PROJECT_KNOWLEDGE.md"
PROJECT_KNOWLEDGE_TITLE = "Personal Job Agent Project Knowledge"
PROJECT_KNOWLEDGE_CATEGORY = "Other"
PROJECT_KNOWLEDGE_MAX_UPLOAD_BYTES = settings.max_upload_size_bytes
GENERIC_KNOWLEDGE_DISABLED_DETAIL = (
    "Generic knowledge base upload is disabled for this release. "
    "Use Project Knowledge RAG instead."
)
JOB_URL_TIMEOUT_SECONDS = 10
SCORING_DIMENSIONS = (
    "skills_match",
    "project_experience",
    "education",
    "work_experience",
    "keyword_match",
)
SCORING_DIMENSION_LABELS = {
    "skills_match": "Skills Match",
    "project_experience": "Project Experience",
    "education": "Education",
    "work_experience": "Work Experience",
    "keyword_match": "Keyword Match",
}
SCORING_WEIGHTS = {
    "skills_match": 0.35,
    "project_experience": 0.25,
    "education": 0.15,
    "work_experience": 0.15,
    "keyword_match": 0.10,
}
ATS_ANALYSIS_FIELDS = (
    "important_keywords",
    "matched_keywords",
    "missing_keywords",
    "keyword_suggestions",
)
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"
RAG_CONTENT_PREVIEW_CHARS = 320
AI_RETRIEVAL_TERMS = (
    "RAG",
    "Retrieval-Augmented Generation",
    "retrieval augmented generation",
    "LLM",
    "LLM applications",
    "Generative AI",
    "Agentic AI",
    "workflow automation",
    "API development",
    "system integration",
    "FastAPI",
    "SQLite",
    "prompt engineering",
    "responsible AI",
    "data leakage prevention",
    "evidence-based generation",
)
SKILL_SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    "RAG": (
        "RAG",
        "Retrieval-Augmented Generation",
        "retrieval augmented generation",
        "retrieval-augmented",
        "top-k evidence injection",
        "top k evidence injection",
        "document chunking",
        "chunking",
        "SQLite FTS5 retrieval",
        "FTS5 retrieval",
        "retrieval pipeline",
        "project-centered RAG",
        "Project Knowledge RAG",
    ),
    "LLM applications": (
        "LLM applications",
        "LLM application",
        "DeepSeek API",
        "DeepSeek API integration",
        "LLM API integration",
        "AI application",
        "Generative AI",
    ),
    "workflow automation": (
        "workflow automation",
        "job application workflow",
        "export workflow",
        "application tracking",
        "cover letter generation",
        "resume parsing",
        "JD analysis",
    ),
    "API development": (
        "API development",
        "FastAPI",
        "FastAPI API development",
        "REST API",
        "CRUD API",
        "project knowledge rebuild/search/status/upload",
    ),
    "system integration": (
        "system integration",
        "frontend/backend integration",
        "frontend backend integration",
        "React",
        "FastAPI",
        "SQLite",
        "DeepSeek API",
        "file parsing",
        "document export",
    ),
    "responsible AI": (
        "responsible AI",
        "data minimization",
        "not fabricate",
        "anti-fabrication",
        "evidence-based generation",
        "grounded",
    ),
    "data leakage prevention": (
        "data leakage prevention",
        "top-k chunks",
        "top k chunks",
        "not save resume_text",
        "full resume_text is not saved",
        ".env ignored",
        "safe logging",
    ),
    "PostgreSQL": ("PostgreSQL", "Postgres", "PostgreSQL 16"),
    "Redis": ("Redis", "Redis 7", "message broker", "queue broker"),
    "Dramatiq": ("Dramatiq", "background worker", "worker queue"),
    "FastAPI": ("FastAPI", "Python API", "REST API"),
    "React": ("React", "React frontend", "frontend"),
    "Docker Compose": ("Docker Compose", "Compose", "container orchestration"),
    "SSE": ("SSE", "Server-Sent Events", "live progress"),
    "CI/CD": ("CI/CD", "GitHub Actions", "continuous integration", "continuous delivery"),
}

configure_logging(settings.log_level)
logger = logging.getLogger(APP_NAME)


@asynccontextmanager
async def application_lifespan(application: FastAPI):
    normalization_client: JavaNormalizationClient | None = None
    if settings.jd_normalization.mode in {"shadow", "java"}:
        normalization_client = JavaNormalizationClient(settings.jd_normalization)
        application.state.jd_normalization_client = normalization_client
    try:
        yield
    finally:
        if normalization_client is not None:
            await normalization_client.aclose()
            application.state.jd_normalization_client = None


app = FastAPI(
    title="Personal Job Agent API",
    version=APP_VERSION,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
    debug=False,
    lifespan=application_lifespan,
)
initialize_project_knowledge(settings)
init_db()
logger.info("SQLite database initialized")


class ApplicationUpdate(BaseModel):
    application_status: str | None = None
    notes: str | None = None


class NextActionDecisionUpdate(BaseModel):
    decision: str
    notes: str | None = None


class EvaluationRunRequest(BaseModel):
    suite_name: str = "default"
    mode: str = "offline"


class MonitoringDataManagementRequest(BaseModel):
    mode: str
    date_from: str | None = None
    date_to: str | None = None
    outcomes: list[str] = []
    security_statuses: list[str] = []
    risk_levels: list[str] = []
    confirmation: str | None = None


class TraceDeletionRequest(BaseModel):
    confirmation: str
    notes: str | None = None


class EvaluationDataManagementRequest(BaseModel):
    mode: str
    date_from: str | None = None
    date_to: str | None = None
    statuses: list[str] = []
    confirmation: str | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Idempotency-Replayed", "X-Request-ID"],
)
if settings.app_env == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
app.add_middleware(RequestLoggingMiddleware, logger=logger)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if is_analyze_request(request):
        logger.warning(
            "Request failed path=%s status_code=%s error_type=HTTPException",
            request.url.path,
            exc.status_code,
        )
        return analyze_exception_response(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        )
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    request.state.error_code = detail.get("error_code", "HTTP_ERROR")
    request.state.error_stage = detail.get("error_stage", "")
    logger.warning(
        "Request failed path=%s status_code=%s error_type=HTTPException",
        request.url.path,
        exc.status_code,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    if is_analyze_request(request):
        logger.warning(
            "Request validation failed path=%s error_type=%s",
            request.url.path,
            type(exc).__name__,
        )
        return analyze_error_response(
            request,
            status_code=400,
            code="REQUEST_VALIDATION_FAILED",
            message="Invalid request. Please check the uploaded file and form fields.",
            error_stage="request_validation",
        )
    request.state.error_code = "REQUEST_VALIDATION_FAILED"
    logger.warning(
        "Request validation failed path=%s error_type=%s",
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": "Invalid request. Please check the uploaded file and form fields."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if is_analyze_request(request):
        logger.error(
            "Unhandled server error path=%s error_type=%s",
            request.url.path,
            type(exc).__name__,
        )
        return analyze_error_response(
            request,
            status_code=500,
            code="UNEXPECTED_SERVER_ERROR",
            message="Unexpected server error. Please try again.",
        )
    request.state.error_code = "UNEXPECTED_SERVER_ERROR"
    logger.error(
        "Unhandled server error path=%s error_type=%s",
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected server error. Please try again."},
    )


def parse_ai_json_response(raw_response: str) -> dict[str, Any]:
    return parse_model_json(raw_response)


def normalize_score(value: Any) -> int:
    try:
        if isinstance(value, str):
            match = re.search(r"-?\d+", value)
            score = int(match.group(0)) if match else 0
        else:
            score = int(value)
    except (TypeError, ValueError):
        score = 0

    return max(0, min(100, score))


def normalize_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def normalize_skill_text(text: Any) -> str:
    normalized = normalize_string(text).lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9+#]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalized_phrase_exists(needle: str, haystack: str) -> bool:
    clean_needle = normalize_skill_text(needle)
    clean_haystack = normalize_skill_text(haystack)
    if not clean_needle or not clean_haystack:
        return False
    return f" {clean_needle} " in f" {clean_haystack} "


def skill_synonym_variants(skill: str) -> list[str]:
    variants = [skill]
    normalized_skill = normalize_skill_text(skill)
    for group_name, group_variants in SKILL_SYNONYM_GROUPS.items():
        normalized_group_terms = [normalize_skill_text(item) for item in (group_name, *group_variants)]
        # Synonym expansion is deliberately exact. A generic term such as
        # "Python" or "worker" must not inherit evidence for the more specific
        # "Python API" or "background worker" synonym.
        if normalized_skill in {term for term in normalized_group_terms if term}:
            variants.extend(group_variants)

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = normalize_skill_text(variant)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(variant)
    return deduped


def rag_evidence_contains_skill(skill: str, retrieved_chunks_text: str) -> bool:
    heading = normalize_skill_text(chunk_heading(retrieved_chunks_text))
    if heading.startswith(("known limitations", "future roadmap", "removed features")):
        return False
    negation_terms = {"not", "no", "never", "without", "lack", "lacks", "missing", "future", "planned"}
    for segment in re.split(r"[.;\n]+", normalize_string(retrieved_chunks_text)):
        segment_tokens = normalize_skill_text(segment).split()
        if not segment_tokens:
            continue
        for variant in skill_synonym_variants(skill):
            variant_tokens = normalize_skill_text(variant).split()
            if not variant_tokens or len(variant_tokens) > len(segment_tokens):
                continue
            for index in range(len(segment_tokens) - len(variant_tokens) + 1):
                if segment_tokens[index:index + len(variant_tokens)] != variant_tokens:
                    continue
                context = segment_tokens[max(0, index - 3):index + len(variant_tokens) + 3]
                if not negation_terms.intersection(context):
                    return True
    return False


def append_unique_skill(items: list[str], skill: str) -> None:
    normalized_existing = {normalize_skill_text(item) for item in items}
    if normalize_skill_text(skill) not in normalized_existing:
        items.append(skill)


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_named_field(value: Any, fallback: str) -> str:
    text = normalize_string(value).strip()
    return text or fallback


def default_scoring_breakdown() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "score": 0,
            "reason": "",
            "evidence": [],
        }
        for key in SCORING_DIMENSIONS
    }


def normalize_scoring_dimension(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}

    return {
        "score": normalize_score(value.get("score", 0)),
        "reason": normalize_string(value.get("reason")),
        "evidence": normalize_list(value.get("evidence")),
    }


def normalize_scoring_breakdown(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        value = {}

    normalized = default_scoring_breakdown()
    for key in SCORING_DIMENSIONS:
        normalized[key] = normalize_scoring_dimension(value.get(key))
    return normalized


def calculate_weighted_match_score(scoring_breakdown: dict[str, dict[str, Any]]) -> int:
    weighted_score = 0.0
    for key, weight in SCORING_WEIGHTS.items():
        section = scoring_breakdown.get(key, {})
        weighted_score += normalize_score(section.get("score", 0)) * weight
    return normalize_score(round(weighted_score))


def normalize_ats_analysis(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}

    return {key: normalize_list(value.get(key)) for key in ATS_ANALYSIS_FIELDS}


def normalize_upgraded_resume_bullets(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    bullets: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        original = normalize_string(item.get("original")).strip()
        improved = normalize_string(item.get("improved")).strip()
        reason = normalize_string(item.get("reason")).strip()
        if not original:
            continue

        bullets.append(
            {
                "original": original,
                "improved": improved,
                "reason": reason,
            }
        )

    return bullets


def chunk_heading(content: Any) -> str:
    for line in normalize_string(content).splitlines():
        clean = line.strip()
        if clean.startswith("#"):
            return clean.lstrip("#").strip()[:160] or "Project Knowledge"
    return "Project Knowledge"


def build_default_rag_sources(
    retrieved_chunks: list[dict[str, Any]],
    matched_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    matched_skills = matched_skills or []
    return [
        {
            "document": PROJECT_KNOWLEDGE_SOURCE_PATH,
            "section": chunk_heading(chunk.get("content")),
            "chunk_id": normalize_int(chunk.get("chunk_id")),
            "relevance_score": round(float(chunk.get("score") or 0), 4),
            "supported_skills": [
                skill for skill in matched_skills
                if rag_evidence_contains_skill(skill, normalize_string(chunk.get("content")))
            ],
        }
        for chunk in retrieved_chunks
    ]


def normalize_rag_sources(
    value: Any,
    retrieved_chunks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    # Source metadata comes exclusively from the trusted retrieval layer. The
    # model cannot add paths, chunk ids, scores, or content to the response.
    del value
    return build_default_rag_sources(retrieved_chunks or [])


def apply_rag_supported_skill_corrections(
    *,
    matched_skills: list[str],
    missing_skills: list[str],
    ats_analysis: dict[str, list[str]],
    scoring_breakdown: dict[str, dict[str, Any]],
    retrieved_chunks: list[dict[str, Any]],
) -> list[str]:
    if not retrieved_chunks:
        return []

    corrected_terms: list[str] = []
    remaining_missing_skills: list[str] = []

    for skill in missing_skills:
        if any(
            rag_evidence_contains_skill(skill, normalize_string(chunk.get("content")))
            for chunk in retrieved_chunks
        ):
            append_unique_skill(matched_skills, skill)
            append_unique_skill(corrected_terms, skill)
        else:
            remaining_missing_skills.append(skill)
    missing_skills[:] = remaining_missing_skills

    matched_keywords = ats_analysis.setdefault("matched_keywords", [])
    missing_keywords = ats_analysis.setdefault("missing_keywords", [])
    remaining_missing_keywords: list[str] = []
    for keyword in missing_keywords:
        if any(
            rag_evidence_contains_skill(keyword, normalize_string(chunk.get("content")))
            for chunk in retrieved_chunks
        ):
            append_unique_skill(matched_keywords, keyword)
            append_unique_skill(corrected_terms, keyword)
        else:
            remaining_missing_keywords.append(keyword)
    missing_keywords[:] = remaining_missing_keywords

    if not corrected_terms:
        return []

    evidence_note = (
        "Project Knowledge RAG evidence supports: "
        f"{', '.join(corrected_terms[:8])}."
    )
    for key, minimum_score in (
        ("skills_match", 70),
        ("project_experience", 65),
        ("keyword_match", 70),
    ):
        section = scoring_breakdown.get(key)
        if not isinstance(section, dict):
            continue
        section["score"] = max(normalize_score(section.get("score")), minimum_score)
        evidence = section.setdefault("evidence", [])
        if isinstance(evidence, list):
            append_unique_skill(evidence, evidence_note)

    return corrected_terms


def build_match_reason_fallback(
    scoring_breakdown: dict[str, dict[str, Any]],
    matched_skills: list[str],
    missing_skills: list[str],
) -> str:
    strong_dimensions = [
        SCORING_DIMENSION_LABELS[key]
        for key in SCORING_DIMENSIONS
        if normalize_score(scoring_breakdown[key].get("score")) >= 70
    ]
    weak_dimensions = [
        SCORING_DIMENSION_LABELS[key]
        for key in SCORING_DIMENSIONS
        if normalize_score(scoring_breakdown[key].get("score")) < 60
    ]

    parts: list[str] = []
    if strong_dimensions:
        parts.append(f"主要匹配点：{', '.join(strong_dimensions)}。")
    elif matched_skills:
        parts.append(f"主要匹配点：简历覆盖了 {', '.join(matched_skills[:5])}。")
    else:
        parts.append("主要匹配点：当前简历与岗位 JD 的明确重合信息较少。")

    if weak_dimensions:
        parts.append(f"主要短板：{', '.join(weak_dimensions)} 仍需补强。")
    elif missing_skills:
        parts.append(f"主要短板：JD 提到的 {', '.join(missing_skills[:5])} 在简历中不够明显。")
    else:
        parts.append("主要短板：暂无明显短板，但仍建议按 JD 关键词优化表达。")

    return "".join(parts)


def normalize_result(
    data: dict[str, Any],
    *,
    retrieved_rag_chunks: list[dict[str, Any]] | None = None,
    apply_rag_corrections: bool = True,
) -> dict[str, Any]:
    retrieved_rag_chunks = retrieved_rag_chunks or []
    scoring_breakdown = normalize_scoring_breakdown(data.get("scoring_breakdown"))
    matched_skills = normalize_list(data.get("matched_skills"))
    missing_skills = normalize_list(data.get("missing_skills"))
    ats_analysis = normalize_ats_analysis(data.get("ats_analysis"))
    upgraded_resume_bullets = normalize_upgraded_resume_bullets(
        data.get("upgraded_resume_bullets")
    )
    rag_sources = normalize_rag_sources(
        data.get("rag_sources"),
        retrieved_rag_chunks,
    )
    rag_corrected_terms: list[str] = []
    if apply_rag_corrections:
        rag_corrected_terms = apply_rag_supported_skill_corrections(
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            ats_analysis=ats_analysis,
            scoring_breakdown=scoring_breakdown,
            retrieved_chunks=retrieved_rag_chunks,
        )

    raw_match_reason = data.get("match_reason")
    match_reason = raw_match_reason.strip() if isinstance(raw_match_reason, str) else ""
    weighted_reason = build_match_reason_fallback(scoring_breakdown, matched_skills, missing_skills)
    if match_reason:
        match_reason = f"{match_reason}\n{weighted_reason}"
    else:
        match_reason = weighted_reason
    if rag_corrected_terms:
        match_reason = (
            f"{match_reason}\n"
            "Project Knowledge RAG evidence also supports: "
            f"{', '.join(rag_corrected_terms[:8])}."
        )

    return {
        "company_name": normalize_named_field(data.get("company_name"), "Unknown Company"),
        "job_title": normalize_named_field(data.get("job_title"), "Unknown Position"),
        "job_summary": (
            data.get("job_summary").strip()
            if isinstance(data.get("job_summary"), str)
            else ""
        )[:320],
        "match_score": calculate_weighted_match_score(scoring_breakdown),
        "match_reason": match_reason,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "resume_suggestions": normalize_list(data.get("resume_suggestions")),
        "cover_letter": normalize_string(data.get("cover_letter")),
        "scoring_breakdown": scoring_breakdown,
        "ats_analysis": ats_analysis,
        "upgraded_resume_bullets": upgraded_resume_bullets,
        "rag_sources": rag_sources,
    }


def ensure_deterministic_narratives(result: dict[str, Any], job_description: str) -> None:
    """Fill the two public narrative fields from validated local facts only."""
    summary = result.get("job_summary")
    if not isinstance(summary, str) or not summary.strip():
        result["job_summary"] = deterministic_job_summary(job_description)
    else:
        result["job_summary"] = summary.strip()[:320]

    match_reason = result.get("match_reason")
    if not isinstance(match_reason, str) or not match_reason.strip():
        result["match_reason"] = deterministic_match_reasons(
            result.get("scoring_breakdown") if isinstance(result.get("scoring_breakdown"), dict) else {},
            normalize_list(result.get("matched_skills")),
            normalize_list(result.get("missing_skills")),
        )
    else:
        result["match_reason"] = match_reason.strip()[:320]


def compact_analysis_to_result(
    analysis: CompactAnalysisOutput,
    *,
    resume_text: str | None = None,
    job_description: str | None = None,
) -> dict[str, Any]:
    """Convert the Provider contract into the stable frontend contract.

    In the active path, skill states are derived from the sanitized Resume/JD
    and the Provider supplies only bounded narrative material.  Omitting the
    context preserves the older conversion behavior for compatibility tests and
    previously recorded fixtures.
    """
    compact = analysis.model_dump()
    dimensions = compact.get("concise_dimension_assessments") or {}
    scoring_breakdown = {
        key: {
            "score": value["score"],
            "reason": value["assessment"],
            "evidence": list(value["evidence_ids"]),
        }
        for key, value in dimensions.items()
        if isinstance(value, dict)
    }
    if resume_text is not None and job_description is not None:
        matched_skills, missing_skills = keyword_skill_states(resume_text, job_description)
        unknown_skills: list[str] = []
    else:
        matched_skills = list(compact.get("matched_skills") or [])
        missing_skills = list(compact.get("missing_skills") or [])
        unknown_skills = list(compact.get("unknown_skills") or [])

    recommendations = list(
        compact.get("recommendations")
        or compact.get("concise_recommendations")
        or []
    )
    resume_improvements = list(compact.get("resume_improvements") or [])
    provider_match_reasons = list(compact.get("match_reasons") or [])
    provider_match_reason = " ".join(provider_match_reasons).strip()
    provider_summary = compact.get("job_summary") or ""
    resume_suggestions = list(dict.fromkeys([*recommendations, *resume_improvements]))
    result = normalize_result(
        {
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "resume_suggestions": resume_suggestions,
            "job_summary": provider_summary,
            "match_reason": provider_match_reason,
            "scoring_breakdown": scoring_breakdown,
            "ats_analysis": {
                "important_keywords": [*matched_skills, *missing_skills, *unknown_skills],
                "matched_keywords": matched_skills,
                "missing_keywords": [*missing_skills, *unknown_skills],
                "keyword_suggestions": recommendations,
            },
            "cover_letter": "",
            "upgraded_resume_bullets": [],
        },
        retrieved_rag_chunks=[],
        apply_rag_corrections=False,
    )
    result["unknown_skills"] = unknown_skills
    result["recommendations"] = recommendations
    result["resume_suggestions"] = resume_suggestions
    if resume_text is not None and job_description is not None:
        if not normalize_string(result.get("job_summary")).strip():
            result["job_summary"] = deterministic_job_summary(job_description)
        if not normalize_string(result.get("match_reason")).strip():
            result["match_reason"] = deterministic_match_reasons(
                scoring_breakdown,
                matched_skills,
                missing_skills,
            )
    result["_model_evidence_references"] = compact.get("evidence_references") or []
    result["_unsupported_claim_candidates"] = compact.get("unsupported_claim_candidates") or []
    return result


def coordinate_skill_states(result: dict[str, Any]) -> None:
    """Ensure a skill appears in exactly one final state, preferring matched."""
    matched = normalize_list(result.get("matched_skills"))
    matched_keys = {normalize_skill_text(item) for item in matched}
    missing = [
        item for item in normalize_list(result.get("missing_skills"))
        if normalize_skill_text(item) not in matched_keys
    ]
    missing_keys = {normalize_skill_text(item) for item in missing}
    unknown = [
        item for item in normalize_list(result.get("unknown_skills"))
        if normalize_skill_text(item) not in matched_keys
        and normalize_skill_text(item) not in missing_keys
    ]
    result["matched_skills"] = matched
    result["missing_skills"] = missing
    result["unknown_skills"] = unknown


def validate_model_evidence_references(
    result: dict[str, Any],
    *,
    resume_text: str,
    retrieved_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Accept only current-request IDs whose text actually supports the skill."""
    chunks_by_id = {
        normalize_int(chunk.get("chunk_id")): chunk
        for chunk in retrieved_chunks
        if normalize_int(chunk.get("chunk_id")) > 0
    }
    references = result.pop("_model_evidence_references", [])
    reference_by_skill = {
        normalize_skill_text(item.get("skill")): item
        for item in references
        if isinstance(item, dict)
    }
    valid_matched: list[str] = []
    mapping: list[dict[str, Any]] = []
    rejected_ids: list[str] = []
    rejected_skills: list[str] = []

    for skill in normalize_list(result.get("matched_skills")):
        reference = reference_by_skill.get(normalize_skill_text(skill), {})
        valid_ids: list[str] = []
        for evidence_id in normalize_list(reference.get("evidence_ids")):
            if evidence_id == "resume":
                if rag_evidence_contains_skill(skill, resume_text):
                    valid_ids.append(evidence_id)
                else:
                    rejected_ids.append(evidence_id)
                continue
            if not evidence_id.startswith("pk:"):
                rejected_ids.append(evidence_id)
                continue
            chunk_id = normalize_int(evidence_id.removeprefix("pk:"))
            chunk = chunks_by_id.get(chunk_id)
            if chunk and rag_evidence_contains_skill(skill, normalize_string(chunk.get("content"))):
                valid_ids.append(evidence_id)
            else:
                rejected_ids.append(evidence_id)

        # Evidence references are helpful but optional. The backend can retain
        # a model match only when the request's own resume or retrieved chunks
        # independently contain that skill.
        if not valid_ids and rag_evidence_contains_skill(skill, resume_text):
            valid_ids.append("resume")
        if not valid_ids:
            for chunk_id, chunk in chunks_by_id.items():
                if rag_evidence_contains_skill(skill, normalize_string(chunk.get("content"))):
                    valid_ids.append(f"pk:{chunk_id}")

        if not valid_ids:
            append_unique_skill(result.setdefault("unknown_skills", []), skill)
            rejected_skills.append(skill)
            continue

        valid_matched.append(skill)
        project_ids = [item.removeprefix("pk:") for item in valid_ids if item.startswith("pk:")]
        mapping.append({
            "skill": skill,
            "source": "resume" if "resume" in valid_ids else "project_knowledge",
            "evidence": [f"project-knowledge-chunk:{item}" for item in project_ids],
        })

    result["matched_skills"] = valid_matched
    result["evidence_mapping"] = mapping
    allowed_dimension_ids = {"resume", *(f"pk:{item}" for item in chunks_by_id)}
    for section in (result.get("scoring_breakdown") or {}).values():
        if not isinstance(section, dict):
            continue
        safe_evidence: list[str] = []
        for evidence_id in normalize_list(section.get("evidence")):
            if evidence_id not in allowed_dimension_ids:
                rejected_ids.append(evidence_id)
                continue
            safe_evidence.append(
                evidence_id if evidence_id == "resume"
                else f"project-knowledge-chunk:{evidence_id.removeprefix('pk:')}"
            )
        section["evidence"] = safe_evidence
        if not safe_evidence:
            section["score"] = 0
            section["reason"] = "No validated evidence supports this dimension."

    coordinate_skill_states(result)
    validation = {
        "status": "passed" if not rejected_ids else "completed_with_rejections",
        "rejected_reference_count": len(rejected_ids),
        "rejected_evidence_ids": sorted(set(rejected_ids))[:10],
        "rejected_skills": rejected_skills[:10],
    }
    result["evidence_reference_validation"] = validation
    return validation


def reconcile_result_with_rag_evidence(
    result: dict[str, Any],
    retrieved_rag_chunks: list[dict[str, Any]],
) -> list[str]:
    scoring_breakdown = result.get("scoring_breakdown")
    ats_analysis = result.get("ats_analysis")
    matched_skills = result.get("matched_skills")
    missing_skills = result.get("missing_skills")
    if not isinstance(scoring_breakdown, dict):
        scoring_breakdown = default_scoring_breakdown()
        result["scoring_breakdown"] = scoring_breakdown
    if not isinstance(ats_analysis, dict):
        ats_analysis = normalize_ats_analysis({})
        result["ats_analysis"] = ats_analysis
    if not isinstance(matched_skills, list):
        matched_skills = []
        result["matched_skills"] = matched_skills
    if not isinstance(missing_skills, list):
        missing_skills = []
        result["missing_skills"] = missing_skills

    corrected_terms = apply_rag_supported_skill_corrections(
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        ats_analysis=ats_analysis,
        scoring_breakdown=scoring_breakdown,
        retrieved_chunks=retrieved_rag_chunks,
    )
    if corrected_terms:
        result["match_reason"] = (
            f"{normalize_string(result.get('match_reason')).strip()}\n"
            "Project Knowledge RAG evidence also supports: "
            f"{', '.join(corrected_terms[:8])}."
        ).strip()
        result["match_score"] = calculate_weighted_match_score(scoring_breakdown)
    coordinate_skill_states(result)
    return corrected_terms


def build_evidence_mapping(
    matched_skills: list[str],
    resume_text: str,
    retrieved_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for skill in matched_skills:
        resume_supported = rag_evidence_contains_skill(skill, resume_text)
        chunk_ids = [
            normalize_int(chunk.get("chunk_id"))
            for chunk in retrieved_chunks
            if rag_evidence_contains_skill(skill, normalize_string(chunk.get("content")))
        ]
        if resume_supported:
            source = "resume"
        elif chunk_ids:
            source = "project_knowledge"
        else:
            source = "unknown"
        mapping.append({
            "skill": skill,
            "source": source,
            "evidence": [f"project-knowledge-chunk:{chunk_id}" for chunk_id in chunk_ids],
        })
    return mapping


def enforce_analysis_grounding(
    result: dict[str, Any],
    resume_text: str,
    retrieved_chunks: list[dict[str, Any]],
) -> None:
    mapping = build_evidence_mapping(
        result.get("matched_skills") or [], resume_text, retrieved_chunks
    )
    unsupported_skills = {
        item["skill"] for item in mapping if item["source"] == "unknown"
    }
    if unsupported_skills:
        result["matched_skills"] = [
            skill for skill in result.get("matched_skills") or []
            if skill not in unsupported_skills
        ]
        for skill in sorted(unsupported_skills):
            append_unique_skill(result.setdefault("missing_skills", []), skill)
        mapping = [item for item in mapping if item["source"] != "unknown"]
    result["evidence_mapping"] = mapping

    evidence_sources = [EvidenceSource("resume", None, None, resume_text)]
    evidence_sources.extend(
        EvidenceSource(
            "project_knowledge",
            str(chunk.get("chunk_id") or ""),
            None,
            normalize_string(chunk.get("content")),
        )
        for chunk in retrieved_chunks
    )
    unsupported_candidates = normalize_list(result.pop("_unsupported_claim_candidates", []))
    generated_claim_text = "\n".join([
        normalize_string(result.get("cover_letter")),
        *[
            normalize_string(item.get("improved"))
            for item in result.get("upgraded_resume_bullets") or []
            if isinstance(item, dict)
        ],
        *unsupported_candidates,
    ])
    claim_links = validate_claims(generated_claim_text, evidence_sources)
    validation_status, unsupported_count, coverage = validation_summary(claim_links)
    result["claim_validation"] = {
        "status": validation_status,
        "unsupported_claim_count": unsupported_count,
        "evidence_coverage": coverage,
        "claims": [
            {
                "claim_key": item["claim_key"],
                "claim_text_hash": item["claim_text_hash"],
                "source": item["source_type"],
                "source_id": item["source_id"],
                "support_status": item["support_status"],
            }
            for item in claim_links
        ],
    }
    if unsupported_count:
        # Unsupported candidates are dropped without blocking the reliable
        # match analysis. Generated application material remains empty unless
        # it has evidence.
        result["cover_letter"] = ""
        result["upgraded_resume_bullets"] = []
        result["claim_validation"]["warning"] = (
            "Unsupported candidate claims were removed from the result."
        )


def sanitize_provider_narratives(
    result: dict[str, Any],
    *,
    resume_text: str,
    job_description: str,
    retrieved_chunks: list[dict[str, Any]],
) -> int:
    """Remove only unsupported narrative sentences while retaining safe peers."""
    sources = [
        EvidenceSource("resume", None, None, resume_text),
        EvidenceSource("job_description", None, None, job_description),
    ]
    sources.extend(
        EvidenceSource(
            "project_knowledge",
            str(chunk.get("chunk_id") or "") or None,
            None,
            normalize_string(chunk.get("content")),
        )
        for chunk in retrieved_chunks
    )

    def clean_text(value: Any) -> tuple[str, int]:
        if not isinstance(value, str) or not value.strip():
            return "", 0
        kept: list[str] = []
        removed = 0
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", value):
            sentence = sentence.strip()
            if not sentence:
                continue
            links = validate_claims(sentence, sources)
            if any(item.get("support_status") in {"unsupported", "partially_supported"} for item in links):
                removed += 1
                continue
            kept.append(sentence)
        return " ".join(kept)[:480], removed

    def clean_list(value: Any) -> tuple[list[str], int]:
        if not isinstance(value, list):
            return [], 0
        kept: list[str] = []
        removed = 0
        for item in value:
            clean, count = clean_text(item)
            removed += count
            if clean:
                kept.append(clean)
        return list(dict.fromkeys(kept)), removed

    removed_total = 0
    summary, removed = clean_text(result.get("job_summary"))
    removed_total += removed
    if isinstance(result.get("job_summary"), str):
        result["job_summary"] = summary
    reason, removed = clean_text(result.get("match_reason"))
    removed_total += removed
    if isinstance(result.get("match_reason"), str):
        result["match_reason"] = reason
    for field_name in ("recommendations", "resume_suggestions"):
        cleaned, removed = clean_list(result.get(field_name))
        removed_total += removed
        if isinstance(result.get(field_name), list):
            result[field_name] = cleaned
    return removed_total


def provider_retry_reason(exc: Exception | ModelOutputError) -> str | None:
    """Return a fixed retry category without inspecting or logging exception text."""
    cause = getattr(exc, "__cause__", None)
    timeout_source = cause if isinstance(cause, httpx.TimeoutException) else exc
    if isinstance(timeout_source, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(timeout_source, httpx.WriteTimeout):
        return "write_timeout"
    if isinstance(timeout_source, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(timeout_source, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, APITimeoutError):
        return "read_timeout"
    if isinstance(exc, APIConnectionError):
        return "connect_timeout"
    if isinstance(exc, RateLimitError):
        return "http_429"
    if isinstance(exc, InternalServerError):
        return "http_5xx"
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return "http_429"
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return "http_5xx"
    if isinstance(exc, TimeoutError):
        return "read_timeout"
    if isinstance(exc, ConnectionError):
        return "connect_timeout"
    if isinstance(exc, ModelOutputError):
        return {
            MODEL_OUTPUT_EMPTY: "empty_content",
            MODEL_OUTPUT_TRUNCATED: "finish_length",
            MODEL_OUTPUT_RESOURCE_LIMIT: "resource_limit",
        }.get(exc.error_code)
    return None


def provider_request_options(runtime_settings: Any, *, max_tokens: int) -> dict[str, Any]:
    """Build the bounded, JSON-mode request shared by primary and repair calls."""
    options: dict[str, Any] = {
        "model": runtime_settings.deepseek_model,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "extra_body": {
            "thinking": {
                "type": "enabled" if runtime_settings.deepseek_thinking_enabled else "disabled"
            }
        },
    }
    # DeepSeek documents thinking as independent from sampling controls. Keep
    # the legacy deterministic temperature only for the default disabled path.
    if not runtime_settings.deepseek_thinking_enabled:
        options["temperature"] = 0.2
    return options


def _provider_metadata_base(runtime_settings: Any, *, attempt_count: int = 0) -> dict[str, Any]:
    return {
        "model_id": runtime_settings.deepseek_model,
        "thinking_enabled": runtime_settings.deepseek_thinking_enabled,
        "response_mode": "json_object",
        "primary_attempt_count": attempt_count,
        "repair_attempt_count": 0,
    }


def _provider_observation_metadata(
    metadata: dict[str, Any],
    *,
    deadline: ProviderDeadline,
    phase_started: float,
    attempt_durations_ms: list[float],
    timeout_categories: list[str],
    retry_started: bool = False,
    repair_started: bool = False,
    deadline_exhausted: bool | None = None,
    fallback_selected: bool = False,
    attempt_count: int | None = None,
) -> dict[str, Any]:
    """Merge only bounded Provider timing categories into safe metadata."""
    categories = list(dict.fromkeys(timeout_categories))[:4]
    return safe_model_metadata({
        **metadata,
        "provider_attempt_durations_ms": attempt_durations_ms[:3],
        "provider_attempt_duration_ms": attempt_durations_ms[-1] if attempt_durations_ms else 0.0,
        "timeout_categories": categories,
        "timeout_category": categories[-1] if categories else None,
        "retry_started": retry_started,
        "repair_started": repair_started,
        "deadline_exhausted": deadline.expired() if deadline_exhausted is None else deadline_exhausted,
        "remaining_deadline_bucket": deadline.remaining_bucket(),
        "fallback_selected": fallback_selected,
        "provider_phase_duration_ms": round((time.monotonic() - phase_started) * 1000, 3),
        "primary_attempt_count": attempt_count
        if attempt_count is not None
        else metadata.get("primary_attempt_count", 0),
    })


def _provider_deadline_error(
    runtime_settings: Any,
    *,
    deadline: ProviderDeadline,
    phase_started: float,
    metadata: dict[str, Any] | None = None,
    attempt_durations_ms: list[float] | None = None,
    timeout_categories: list[str] | None = None,
    retry_started: bool = False,
    repair_started: bool = False,
    attempt_count: int = 0,
) -> ModelOutputError:
    observation = _provider_observation_metadata(
        {
            **_provider_metadata_base(runtime_settings, attempt_count=attempt_count),
            **(metadata or {}),
            "primary_attempt_count": attempt_count,
            "result_state": "fallback",
            "fallback_reason": "provider_deadline_exhausted",
            "deadline_exhausted": True,
        },
        deadline=deadline,
        phase_started=phase_started,
        attempt_durations_ms=attempt_durations_ms or [],
        timeout_categories=timeout_categories or [],
        retry_started=retry_started,
        repair_started=repair_started,
        deadline_exhausted=True,
        fallback_selected=True,
    )
    return ModelOutputError(MODEL_PROVIDER_ERROR, metadata=observation)


def _build_provider_client(
    runtime_settings: Any,
    *,
    deadline: ProviderDeadline,
    attempt_timeout: ProviderAttemptTimeout,
) -> tuple[OpenAI, DeadlineHttpxClient]:
    http_client = DeadlineHttpxClient(
        deadline_monotonic=deadline.absolute_deadline,
        timeout=attempt_timeout.timeout,
    )
    try:
        client = OpenAI(
            api_key=runtime_settings.deepseek_api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=attempt_timeout.timeout,
            max_retries=0,
            http_client=http_client,
        )
    except BaseException:
        http_client.close()
        raise
    return client, http_client


def _close_provider_clients(client: Any, http_client: DeadlineHttpxClient) -> None:
    try:
        close = getattr(client, "close", None)
        if callable(close):
            close()
    finally:
        http_client.close()


def _public_model_completion(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: metadata.get(key)
        for key in (
            "finish_reason",
            "response_length",
            "reached_token_limit",
            "latency_ms",
            "model_id",
            "thinking_enabled",
            "response_mode",
            "primary_attempt_count",
            "repair_attempt_count",
            "empty_content",
            "transient_retry_reason",
            "parse_outcome",
            "salvage_action_categories",
            "rejected_field_count",
            "accepted_field_count",
            "timeout_category",
            "timeout_categories",
            "provider_attempt_durations_ms",
            "provider_attempt_duration_ms",
            "remaining_deadline_bucket",
            "deadline_exhausted",
            "retry_started",
            "repair_started",
            "fallback_selected",
            "history_finalized",
            "idempotency_finalized",
            "client_disconnected",
            "result_state",
            "fallback_reason",
        )
        if key in metadata
    }


async def _request_client_disconnected(request: Request) -> bool:
    """Best-effort safe disconnect check at async boundaries."""
    try:
        return bool(await request.is_disconnected())
    except Exception:
        return False


def call_deepseek_raw(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]] | None = None,
    analysis_prompt: str | None = None,
    usage_out: dict[str, Any] | None = None,
    deadline_monotonic: float | None = None,
) -> ProviderAnalysisResponse:
    """Run at most two bounded primary calls, with one stable transient retry."""
    runtime_settings = load_config(validate_production=False)
    base_metadata = _provider_metadata_base(runtime_settings)
    phase_started = time.monotonic()
    if runtime_settings.mock_provider_enabled:
        if runtime_settings.app_env == "production":
            raise HTTPException(status_code=500, detail="Mock provider is unavailable in production.")
        content = json.dumps({
            "job_summary": "A concise comparison of the supplied resume and role.",
            "match_reasons": ["Use only the supplied resume and role evidence."],
            "recommendations": ["Keep verified project evidence prominent."],
            "resume_improvements": [],
        })
        metadata = safe_model_metadata({
            **base_metadata,
            "finish_reason": "stop",
            "response_length": len(content),
            "latency_ms": 0,
            "primary_attempt_count": 1,
            "provider_attempt_durations_ms": [0.0],
            "retry_started": False,
            "repair_started": False,
            "remaining_deadline_bucket": "gt_60s",
        })
        if usage_out is not None:
            usage_out.update(metadata)
        return ProviderAnalysisResponse(content=content, metadata=metadata)
    if not runtime_settings.deepseek_api_key:
        logger.error("DeepSeek configuration failed error_type=MissingApiKey")
        raise HTTPException(
            status_code=500,
            detail="DeepSeek API key is not configured on the backend.",
        )

    prompt = analysis_prompt or build_safe_analysis_prompt(
        resume_text=resume_text,
        job_description=job_description,
        rag_chunks=rag_chunks or [],
    )
    deadline = ProviderDeadline(
        deadline_monotonic
        or (time.monotonic() + runtime_settings.provider_overall_deadline_seconds)
    )
    retry_reason: str | None = None
    last_error: ModelOutputError | None = None
    attempt_durations_ms: list[float] = []
    timeout_categories: list[str] = []
    retry_started = False
    for attempt in range(1, MAX_PRIMARY_PROVIDER_CALLS + 1):
        attempt_timeout = deadline.call_timeout(
            configured_timeout_seconds=runtime_settings.request_timeout_seconds,
            kind="primary" if attempt == 1 else "retry",
        )
        if attempt_timeout is None:
            if last_error is not None:
                raise _provider_deadline_error(
                    runtime_settings,
                    deadline=deadline,
                    phase_started=phase_started,
                    metadata=last_error.metadata,
                    attempt_durations_ms=attempt_durations_ms,
                    timeout_categories=timeout_categories,
                    retry_started=retry_started,
                    attempt_count=attempt - 1,
                ) from last_error
            raise _provider_deadline_error(
                runtime_settings,
                deadline=deadline,
                phase_started=phase_started,
                attempt_count=attempt - 1,
            )
        if attempt > 1:
            retry_started = True
        http_client: DeadlineHttpxClient | None = None
        client: Any | None = None
        max_tokens = (
            runtime_settings.model_length_retry_output_tokens
            if retry_reason == "finish_length"
            else runtime_settings.model_max_output_tokens
        )
        metadata_seed = {
            **base_metadata,
            "primary_attempt_count": attempt,
            "transient_retry_reason": retry_reason,
            "remaining_deadline_bucket": attempt_timeout.remaining_bucket,
        }
        started = time.monotonic()
        attempt_duration_recorded = False
        try:
            client, http_client = _build_provider_client(
                runtime_settings,
                deadline=deadline,
                attempt_timeout=attempt_timeout,
            )
            logger.info(
                "DeepSeek call started attempt=%s model=%s thinking_enabled=%s response_mode=json_object max_tokens=%s timeout_contract=connect_read_write_pool",
                attempt,
                runtime_settings.deepseek_model,
                runtime_settings.deepseek_thinking_enabled,
                max_tokens,
            )
            options = provider_request_options(runtime_settings, max_tokens=max_tokens)
            completion = client.chat.completions.create(
                **options,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return JSON only. The final content must be exactly one JSON object. "
                            "Do not include Markdown fences or prose outside the object."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            response = adapt_provider_completion(
                completion,
                max_output_tokens=max_tokens,
                latency_ms=round((time.monotonic() - started) * 1000, 3),
            )
            attempt_duration_ms = round((time.monotonic() - started) * 1000, 3)
            attempt_durations_ms.append(attempt_duration_ms)
            attempt_duration_recorded = True
            if deadline.expired():
                raise _provider_deadline_error(
                    runtime_settings,
                    deadline=deadline,
                    phase_started=phase_started,
                    metadata=response.metadata,
                    attempt_durations_ms=attempt_durations_ms,
                    timeout_categories=timeout_categories,
                    retry_started=retry_started,
                    attempt_count=attempt,
                )
            metadata = safe_model_metadata({
                **response.metadata,
                **metadata_seed,
                "primary_attempt_count": attempt,
            })
            metadata = _provider_observation_metadata(
                metadata,
                deadline=deadline,
                phase_started=phase_started,
                attempt_durations_ms=attempt_durations_ms,
                timeout_categories=timeout_categories,
                retry_started=retry_started,
                attempt_count=attempt,
            )
            response = ProviderAnalysisResponse(content=response.content, metadata=metadata)
            if usage_out is not None:
                usage_out.update(metadata)
            logger.info(
                "DeepSeek call succeeded attempt=%s finish_reason=%s output_tokens=%s response_length=%s latency_ms=%s",
                attempt,
                metadata.get("finish_reason"),
                metadata.get("output_tokens"),
                metadata.get("response_length"),
                metadata.get("latency_ms"),
            )
            return response
        except Exception as exc:
            model_error = exc if isinstance(exc, ModelOutputError) else None
            reason = provider_retry_reason(exc)
            attempt_duration_ms = round((time.monotonic() - started) * 1000, 3)
            if not attempt_duration_recorded:
                attempt_durations_ms.append(attempt_duration_ms)
            if reason in {"connect_timeout", "read_timeout", "write_timeout", "pool_timeout"}:
                timeout_categories.append(reason)
            metadata_values = {
                **(model_error.metadata if model_error is not None else {}),
                **metadata_seed,
                "primary_attempt_count": attempt,
            }
            if model_error is None:
                metadata_values["latency_ms"] = attempt_duration_ms
            else:
                metadata_values["empty_content"] = model_error.error_code == MODEL_OUTPUT_EMPTY
            metadata = safe_model_metadata(metadata_values)
            metadata = _provider_observation_metadata(
                metadata,
                deadline=deadline,
                phase_started=phase_started,
                attempt_durations_ms=attempt_durations_ms,
                timeout_categories=timeout_categories,
                retry_started=retry_started,
                deadline_exhausted=deadline.expired(),
                attempt_count=attempt,
            )
            error_code = model_error.error_code if model_error is not None else MODEL_PROVIDER_ERROR
            last_error = ModelOutputError(error_code, metadata=metadata)
            if usage_out is not None:
                usage_out.update(metadata)
            if model_error is not None:
                logger.warning(
                    "DeepSeek output rejected attempt=%s error_code=%s finish_reason=%s output_tokens=%s latency_ms=%s",
                    attempt,
                    error_code,
                    metadata.get("finish_reason"),
                    metadata.get("output_tokens"),
                    metadata.get("latency_ms"),
                )
            else:
                logger.warning(
                    "DeepSeek call failed attempt=%s error_code=%s retry_category=%s latency_ms=%s",
                    attempt,
                    error_code,
                    reason or "provider_call_failed",
                    attempt_duration_ms,
                )
            if deadline.expired():
                break
            if not reason or attempt >= MAX_PRIMARY_PROVIDER_CALLS:
                raise last_error from exc
            retry_reason = reason

        finally:
            if client is not None and http_client is not None:
                _close_provider_clients(client, http_client)

        retry_timeout = deadline.call_timeout(
            configured_timeout_seconds=runtime_settings.request_timeout_seconds,
            kind="retry",
        )
        if retry_timeout is None:
            break
        backoff = min(
            runtime_settings.provider_retry_backoff_seconds,
            max(0.0, deadline.remaining_seconds()),
        )
        if backoff > 0:
            time.sleep(backoff)

    if last_error is not None:
        if deadline.call_timeout(
            configured_timeout_seconds=runtime_settings.request_timeout_seconds,
            kind="retry",
        ) is None:
            raise _provider_deadline_error(
                runtime_settings,
                deadline=deadline,
                phase_started=phase_started,
                metadata=last_error.metadata,
                attempt_durations_ms=attempt_durations_ms,
                timeout_categories=timeout_categories,
                retry_started=retry_started,
                attempt_count=min(MAX_PRIMARY_PROVIDER_CALLS, len(attempt_durations_ms)),
            ) from last_error
        raise last_error
    raise _provider_deadline_error(
        runtime_settings,
        deadline=deadline,
        phase_started=phase_started,
        attempt_count=min(MAX_PRIMARY_PROVIDER_CALLS, len(attempt_durations_ms)),
    )


def call_deepseek_repair(
    raw_response: str,
    *,
    usage_out: dict[str, Any] | None = None,
    deadline_monotonic: float | None = None,
) -> ProviderAnalysisResponse:
    """Make the single allowed, bounded format-only repair request."""
    runtime_settings = load_config(validate_production=False)
    phase_started = time.monotonic()
    if not runtime_settings.deepseek_api_key:
        raise ModelOutputError(MODEL_PROVIDER_ERROR)
    deadline = ProviderDeadline(
        deadline_monotonic
        or (time.monotonic() + runtime_settings.provider_overall_deadline_seconds)
    )
    attempt_timeout = deadline.call_timeout(
        configured_timeout_seconds=runtime_settings.request_timeout_seconds,
        kind="repair",
    )
    if attempt_timeout is None:
        raise _provider_deadline_error(
            runtime_settings,
            deadline=deadline,
            phase_started=phase_started,
            metadata={"repair_attempt_count": 0, "repair_started": False},
            repair_started=False,
        )
    repair_tokens = runtime_settings.model_repair_output_tokens
    repair_prompt = (
        "Convert the model text below into one concise JSON object. Preserve only explicit analysis; "
        "do not add facts. Use only job_summary, match_reasons, recommendations, and "
        "resume_improvements. The Backend owns skills, evidence, and scores. The final content must be exactly one JSON object; "
        "do not use Markdown fences or prose outside it.\n\n"
        + str(raw_response or "")[:12_000]
    )
    started = time.monotonic()
    attempt_durations_ms: list[float] = []
    timeout_categories: list[str] = []
    client: Any | None = None
    http_client: DeadlineHttpxClient | None = None
    try:
        client, http_client = _build_provider_client(
            runtime_settings,
            deadline=deadline,
            attempt_timeout=attempt_timeout,
        )
        options = provider_request_options(runtime_settings, max_tokens=repair_tokens)
        completion = client.chat.completions.create(
            **options,
            messages=[
                {"role": "system", "content": "Return JSON only. Repair format; never redo the analysis."},
                {"role": "user", "content": repair_prompt},
            ],
        )
    except Exception as exc:
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        attempt_durations_ms.append(latency_ms)
        reason = provider_retry_reason(exc)
        if reason in {"connect_timeout", "read_timeout", "write_timeout", "pool_timeout"}:
            timeout_categories.append(reason)
        metadata = safe_model_metadata({
            **_provider_metadata_base(runtime_settings),
            "repair_attempt_count": 1,
            "latency_ms": latency_ms,
            "repair_started": True,
            "timeout_category": reason,
        })
        metadata = _provider_observation_metadata(
            metadata,
            deadline=deadline,
            phase_started=phase_started,
            attempt_durations_ms=attempt_durations_ms,
            timeout_categories=timeout_categories,
            repair_started=True,
            deadline_exhausted=deadline.expired(),
        )
        if usage_out is not None:
            usage_out.update(metadata)
        if deadline.expired():
            raise _provider_deadline_error(
                runtime_settings,
                deadline=deadline,
                phase_started=phase_started,
                metadata=metadata,
                attempt_durations_ms=attempt_durations_ms,
                timeout_categories=timeout_categories,
                repair_started=True,
            ) from exc
        raise ModelOutputError(MODEL_PROVIDER_ERROR, metadata=metadata) from exc
    finally:
        if client is not None and http_client is not None:
            _close_provider_clients(client, http_client)
    try:
        response = adapt_provider_completion(
            completion,
            max_output_tokens=repair_tokens,
            latency_ms=round((time.monotonic() - started) * 1000, 3),
        )
        attempt_durations_ms.append(round((time.monotonic() - started) * 1000, 3))
    except ModelOutputError as exc:
        if not attempt_durations_ms:
            attempt_durations_ms.append(round((time.monotonic() - started) * 1000, 3))
        if deadline.expired() or exc.metadata.get("deadline_exhausted"):
            raise _provider_deadline_error(
                runtime_settings,
                deadline=deadline,
                phase_started=phase_started,
                metadata=exc.metadata,
                attempt_durations_ms=attempt_durations_ms,
                timeout_categories=timeout_categories,
                repair_started=True,
            ) from exc
        metadata = safe_model_metadata({
            **exc.metadata,
            **_provider_metadata_base(runtime_settings),
            "repair_attempt_count": 1,
            "repair_started": True,
        })
        metadata = _provider_observation_metadata(
            metadata,
            deadline=deadline,
            phase_started=phase_started,
            attempt_durations_ms=attempt_durations_ms,
            timeout_categories=timeout_categories,
            repair_started=True,
            deadline_exhausted=deadline.expired(),
        )
        if usage_out is not None:
            usage_out.update(metadata)
        raise ModelOutputError(exc.error_code, metadata=metadata) from exc
    if deadline.expired():
        raise _provider_deadline_error(
            runtime_settings,
            deadline=deadline,
            phase_started=phase_started,
            metadata=response.metadata,
            attempt_durations_ms=attempt_durations_ms,
            timeout_categories=timeout_categories,
            repair_started=True,
        )
    metadata = _provider_observation_metadata(
        safe_model_metadata({
            **response.metadata,
            **_provider_metadata_base(runtime_settings),
            "repair_attempt_count": 1,
            "repair_started": True,
        }),
        deadline=deadline,
        phase_started=phase_started,
        attempt_durations_ms=attempt_durations_ms,
        timeout_categories=timeout_categories,
        repair_started=True,
    )
    response = ProviderAnalysisResponse(content=response.content, metadata=metadata)
    if usage_out is not None:
        usage_out.update(response.metadata)
    return response


def model_response_to_result(
    raw_response: str,
    *,
    repairer: Any | None = None,
    metadata_out: dict[str, Any] | None = None,
    resume_text: str | None = None,
    job_description: str | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    """Parse locally first, then perform at most one model format repair."""
    try:
        parsed_result = parse_model_json_result(raw_response)
        salvaged = salvage_compact_analysis(parsed_result.data)
        compact = validate_compact_analysis(salvaged)
        warnings = list(parsed_result.warnings)
        warnings.extend(compact_analysis_warnings(parsed_result.data))
        warnings.extend(salvage_warning_messages(salvaged.action_codes))
        if metadata_out is not None:
            metadata_out.update({
                "parse_outcome": "local_format_repair" if parsed_result.normalized else "canonical",
                "salvage_action_categories": list(salvaged.action_codes),
                "rejected_field_count": salvaged.rejected_field_count,
                "accepted_field_count": salvaged.accepted_field_count,
            })
        if salvaged.action_codes:
            status = "partial"
        elif parsed_result.normalized:
            status = "repaired"
        else:
            status = "complete"
        result = compact_analysis_to_result(
            compact,
            resume_text=resume_text,
            job_description=job_description,
        )
        for field_name in OPTIONAL_PROVIDER_NARRATIVE_FIELDS:
            if isinstance(salvaged.data.get(field_name), str) and salvaged.data[field_name]:
                result[field_name] = salvaged.data[field_name]
        return result, status, list(dict.fromkeys(warnings))
    except (ModelOutputError, ValidationError, ValueError):
        pass

    if repairer is None:
        repairer = call_deepseek_repair
    # Exactly one format-only retry is allowed per analysis.
    repaired_response = repairer(raw_response)
    repaired_text = (
        repaired_response.content
        if isinstance(repaired_response, ProviderAnalysisResponse)
        else str(repaired_response or "")
    )
    parsed_result = parse_model_json_result(repaired_text)
    salvaged = salvage_compact_analysis(parsed_result.data)
    compact = validate_compact_analysis(salvaged)
    warnings = ["The model response was automatically normalized by one format-only repair call."]
    warnings.extend(parsed_result.warnings)
    warnings.extend(compact_analysis_warnings(parsed_result.data))
    warnings.extend(salvage_warning_messages(salvaged.action_codes))
    if metadata_out is not None:
        metadata_out.update({
            "parse_outcome": "format_repair_call",
            "salvage_action_categories": list(salvaged.action_codes),
            "rejected_field_count": salvaged.rejected_field_count,
            "accepted_field_count": salvaged.accepted_field_count,
            "repair_attempt_count": 1,
        })
    status = "partial" if salvaged.action_codes else "repaired"
    result = compact_analysis_to_result(
        compact,
        resume_text=resume_text,
        job_description=job_description,
    )
    for field_name in OPTIONAL_PROVIDER_NARRATIVE_FIELDS:
        if isinstance(salvaged.data.get(field_name), str) and salvaged.data[field_name]:
            result[field_name] = salvaged.data[field_name]
    return result, status, list(dict.fromkeys(warnings))


def analyze_with_deepseek(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    provider_phase_started = time.monotonic()
    provider_deadline = ProviderDeadline.for_phase(
        phase_started_monotonic=provider_phase_started,
        configured_deadline_seconds=load_config(
            validate_production=False
        ).provider_overall_deadline_seconds,
    )
    safe_prompt = build_safe_analysis_prompt(
        resume_text=resume_text,
        job_description=job_description,
        rag_chunks=rag_chunks or [],
    )
    provider_response = call_deepseek_raw(
        resume_text,
        job_description,
        rag_chunks or [],
        analysis_prompt=safe_prompt,
        deadline_monotonic=provider_deadline.absolute_deadline,
    )
    result, status, warnings = model_response_to_result(
        provider_response.content,
        repairer=lambda raw_response: call_deepseek_repair(
            raw_response,
            deadline_monotonic=provider_deadline.absolute_deadline,
        ),
        resume_text=resume_text,
        job_description=job_description,
    )
    validate_model_evidence_references(
        result,
        resume_text=resume_text,
        retrieved_chunks=rag_chunks or [],
    )
    reconcile_result_with_rag_evidence(result, rag_chunks or [])
    enforce_analysis_grounding(result, resume_text, rag_chunks or [])
    result["used_knowledge_base"] = bool(rag_chunks)
    result["retrieval_count"] = len(rag_chunks or [])
    result["rag_sources"] = build_default_rag_sources(
        rag_chunks or [], result.get("matched_skills") or []
    )
    result["scoring_breakdown"] = deterministic_scoring(
        result, resume_text, job_description, rag_chunks or []
    )
    result["match_score"] = calculate_weighted_match_score(result["scoring_breakdown"])
    ensure_deterministic_narratives(result, job_description)
    result["analysis_status"] = status
    result["analysis_warnings"] = warnings
    return result


def validate_application_status(value: str | None, *, required: bool) -> str | None:
    status = (value or "").strip()
    if status == "All" and not required:
        return None

    if not status:
        if required:
            raise HTTPException(status_code=400, detail="application_status is required.")
        return None

    if status not in ALLOWED_APPLICATION_STATUSES:
        allowed = ", ".join(ALLOWED_APPLICATION_STATUSES)
        raise HTTPException(
            status_code=400,
            detail=f"application_status must be one of: {allowed}.",
        )

    return status


def validate_next_action_decision(value: str | None) -> str:
    decision = (value or "").strip()
    if decision not in ALLOWED_NEXT_ACTION_DECISIONS:
        allowed = ", ".join(ALLOWED_NEXT_ACTION_DECISIONS)
        raise HTTPException(status_code=400, detail=f"decision must be one of: {allowed}.")
    return decision


def validate_knowledge_category(value: str | None, *, required: bool) -> str | None:
    category = (value or "").strip()
    if not category:
        if required:
            raise HTTPException(status_code=400, detail="category is required.")
        return None

    if category not in ALLOWED_KNOWLEDGE_CATEGORIES:
        allowed = ", ".join(ALLOWED_KNOWLEDGE_CATEGORIES)
        raise HTTPException(status_code=400, detail=f"category must be one of: {allowed}.")

    return category


def extract_retrieval_keywords(text: str) -> list[str]:
    stopwords = {
        "and",
        "are",
        "for",
        "the",
        "with",
        "you",
        "our",
        "will",
        "this",
        "that",
        "from",
        "have",
        "has",
        "your",
        "job",
        "role",
        "team",
        "work",
        "experience",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{2,}", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [
        token
        for token, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:30]
    ]


def extract_ai_retrieval_terms(text: str) -> list[str]:
    normalized_text = normalize_skill_text(text)
    terms: list[str] = []
    for term in AI_RETRIEVAL_TERMS:
        if normalized_phrase_exists(term, normalized_text):
            terms.append(term)

    for group_name, variants in SKILL_SYNONYM_GROUPS.items():
        if any(normalized_phrase_exists(variant, normalized_text) for variant in variants):
            terms.append(group_name)
            terms.extend(variants)

    if normalized_phrase_exists("RAG", normalized_text):
        terms.append("Retrieval-Augmented Generation")
    if normalized_phrase_exists("Retrieval-Augmented Generation", normalized_text):
        terms.append("RAG")
    if normalized_phrase_exists("LLM applications", normalized_text):
        terms.extend(["DeepSeek API", "LLM application", "LLM API integration"])
    if normalized_phrase_exists("workflow automation", normalized_text):
        terms.extend(["job application workflow automation", "export workflow automation"])

    for acronym in ("RAG", "LLM", "API", "ATS", "AI"):
        if normalized_phrase_exists(acronym, normalized_text):
            terms.append(acronym)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = normalize_skill_text(term)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped


def build_knowledge_retrieval_query(job_description: str, resume_text: str) -> str:
    keywords = extract_retrieval_keywords(job_description)
    ai_terms = extract_ai_retrieval_terms(job_description)
    query_parts = [
        " ".join(ai_terms),
        job_description[:2500],
        " ".join(keywords),
        resume_text[:1200],
    ]
    return "\n".join(part for part in query_parts if part.strip())


def field_was_provided(model: BaseModel, field_name: str) -> bool:
    fields_set = getattr(model, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(model, "__fields_set__", set())
    return field_name in fields_set


def get_existing_application_record(application_id: int) -> dict[str, Any]:
    record = get_application_record(application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application record not found.")
    return record


def get_owned_history_record(application_id: int, request: Request) -> dict[str, Any]:
    user = getattr(request.state, "v2_user", None)
    record = get_application_record(
        application_id,
        owner_user_id=getattr(user, "id", None),
        include_unowned=getattr(user, "role", "") == "admin",
    )
    if record is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return record


def attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def project_knowledge_status_data() -> dict[str, Any]:
    knowledge_path = get_project_knowledge_path()
    exists = knowledge_path.is_file()
    document = find_project_knowledge_document(
        title=PROJECT_KNOWLEDGE_TITLE,
        source_filename=PROJECT_KNOWLEDGE_SOURCE_PATH,
    )
    if document is None:
        document = find_project_knowledge_document(
            title=PROJECT_KNOWLEDGE_TITLE,
            source_filename=LEGACY_PROJECT_KNOWLEDGE_SOURCE_PATH,
        )

    if not exists:
        return {
            "exists": False,
            "path": PROJECT_KNOWLEDGE_SOURCE_PATH,
            "indexed": False,
            "document_id": None,
            "chunk_count": 0,
        }

    chunk_count = normalize_int(document.get("chunk_count")) if document else 0
    return {
        "exists": True,
        "path": PROJECT_KNOWLEDGE_SOURCE_PATH,
        "indexed": bool(document and chunk_count > 0),
        "document_id": normalize_int(document.get("id")) if document else None,
        "chunk_count": chunk_count,
        "updated_at": document.get("updated_at") if document else None,
    }


def rebuild_project_knowledge_index() -> dict[str, Any]:
    knowledge_path = get_project_knowledge_path()
    if not knowledge_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Project Knowledge file not found at {PROJECT_KNOWLEDGE_SOURCE_PATH}.",
        )

    try:
        raw_text = knowledge_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Project Knowledge file must be UTF-8 encoded.",
        ) from exc
    except OSError as exc:
        logger.warning("Project Knowledge read failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Failed to read Project Knowledge file.",
        ) from exc

    content = clean_knowledge_text(raw_text)
    chunks = build_text_chunks(content)
    if not chunks:
        raise HTTPException(status_code=400, detail="Project Knowledge content is empty.")

    existing = project_knowledge_status_data()
    database_source = (
        LEGACY_PROJECT_KNOWLEDGE_SOURCE_PATH
        if existing.get("document_id")
        and find_project_knowledge_document(
            title=PROJECT_KNOWLEDGE_TITLE,
            source_filename=LEGACY_PROJECT_KNOWLEDGE_SOURCE_PATH,
        )
        else PROJECT_KNOWLEDGE_SOURCE_PATH
    )
    result = rebuild_project_knowledge_document(
        title=PROJECT_KNOWLEDGE_TITLE,
        category=PROJECT_KNOWLEDGE_CATEGORY,
        source_filename=database_source,
        content=content,
        chunks=chunks,
    )
    logger.info(
        "Project Knowledge index rebuilt document_id=%s chunk_count=%s",
        result["id"],
        result["chunk_count"],
    )
    return {
        "rebuilt": True,
        "document_id": result["id"],
        "chunk_count": result["chunk_count"],
        "source_path": PROJECT_KNOWLEDGE_SOURCE_PATH,
    }


def ensure_project_knowledge_indexed() -> dict[str, Any] | None:
    status = project_knowledge_status_data()
    if not status["exists"]:
        logger.info("Project Knowledge RAG skipped reason=MissingSourceFile")
        return None

    if status["indexed"]:
        return status

    try:
        rebuild_project_knowledge_index()
    except HTTPException as exc:
        logger.warning(
            "Project Knowledge auto rebuild failed status_code=%s",
            exc.status_code,
        )
        return None

    rebuilt_status = project_knowledge_status_data()
    return rebuilt_status if rebuilt_status["indexed"] else None


def search_project_knowledge(query: str, top_k: int) -> tuple[list[dict[str, Any]], str]:
    status = ensure_project_knowledge_indexed()
    if not status or not status.get("document_id"):
        return [], "none"

    return search_knowledge_chunks(
        query,
        clamp_rag_top_k(top_k),
        document_id=normalize_int(status["document_id"]),
    )


def validate_project_knowledge_upload_name(filename: str) -> None:
    clean_name = Path(filename or "").name.lower()
    if not clean_name.endswith((".md", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Only .md and .txt Project Knowledge files are supported.",
        )


def decode_project_knowledge_upload(file_bytes: bytes) -> str:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded Project Knowledge file is empty.")

    if len(file_bytes) > PROJECT_KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Project Knowledge file is too large. Maximum size is {settings.max_upload_size_mb} MB.",
        )

    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Project Knowledge file must be UTF-8 encoded.",
        ) from exc


def write_project_knowledge_file(content: str) -> None:
    knowledge_path = get_project_knowledge_path()
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = knowledge_path.with_name(".PROJECT_KNOWLEDGE.md.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, knowledge_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def raise_generic_knowledge_disabled() -> None:
    raise HTTPException(status_code=410, detail=GENERIC_KNOWLEDGE_DISABLED_DETAIL)


REMAINING_WORKFLOW_STEPS = (
    ("scan_untrusted_input", "Scan Untrusted Input"),
    ("retrieve_project_evidence", "Retrieve Project Knowledge"),
    ("scan_project_evidence", "Scan Project Evidence"),
    ("build_safe_prompt", "Build Safe Prompt"),
    ("run_llm_analysis", "Run LLM Analysis"),
    ("scan_llm_output", "Scan LLM Output"),
    ("parse_model_json", "Parse Model JSON"),
    ("validate_structured_output", "Validate Structured Output"),
    ("validate_evidence_references", "Validate Evidence References"),
    ("reconcile_evidence", "Reconcile Evidence"),
    ("recommend_next_action", "Recommend Next Action"),
    ("final_output_scan", "Final Output Security Scan"),
    ("save_application", "Save Application"),
    ("finalize_result", "Finalize Result"),
)


def skip_workflow_steps_after(
    workflow: AgentWorkflow,
    *,
    after_key: str,
    message: str,
) -> None:
    should_skip = False
    for key, name in REMAINING_WORKFLOW_STEPS:
        if key == after_key:
            should_skip = True
            continue
        if should_skip:
            workflow.skip_step(key, name, message)


def idempotency_http_exception(exc: IdempotencyError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    status_code = 503 if exc.code == "IDEMPOTENCY_PERSISTENCE_FAILED" else 409
    if exc.code == "IDEMPOTENCY_KEY_INVALID":
        status_code = 400
    return HTTPException(
        status_code=status_code,
        detail=analyze_error_detail(
            str(exc),
            exc.code,
            "idempotency",
            details={"retryable": exc.code in {
                "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                "IDEMPOTENCY_PERSISTENCE_FAILED",
            }},
        ),
        headers=headers,
    )


def raise_security_blocked(
    workflow: AgentWorkflow,
    context: WorkflowContext,
    *,
    status_code: int = 422,
    message: str = "Sensitive credential-like content was detected. Remove secrets before analysis.",
    error_code: str = "INPUT_SECURITY_BLOCKED",
    error_stage: str = "scan_untrusted_input",
) -> None:
    context.security_scan = normalized_security_scan(context.security_scan or empty_security_scan())
    context.security_status = "blocked"
    record_analysis_observation(
        workflow,
        context,
        outcome="blocked",
        error_code=error_code,
        error_stage=error_stage,
    )
    duration = workflow.workflow_duration()
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": message,
            "workflow_id": context.workflow_id,
            "security_status": "blocked",
            "error_code": error_code,
            "security_scan": normalized_security_scan(context.security_scan),
            "workflow_status": workflow.status(),
            "workflow_steps": workflow.to_list(),
            "workflow_duration_ms": duration["workflow_duration_ms"],
            "workflow_duration_us": duration["workflow_duration_us"],
        },
    )


def record_analysis_observation(
    workflow: AgentWorkflow,
    context: WorkflowContext,
    *,
    outcome: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_stage: str | None = None,
) -> None:
    workflow.finish()
    workflow_duration = workflow.workflow_duration()
    steps = workflow.to_list()
    result = result or {}
    security_scan = normalized_security_scan(
        result.get("security_scan") or context.security_scan or empty_security_scan()
    )
    security_status = (
        result.get("security_status")
        or context.security_status
        or security_status_from_scan(security_scan)
    )
    rag_sources = result.get("rag_sources")
    rag_source_count = len(rag_sources) if isinstance(rag_sources, list) else len(context.rag_sources)
    next_action = result.get("next_action") or context.next_action or {}
    next_action_code = next_action.get("action") if isinstance(next_action, dict) else None
    metric = build_analysis_metric(
        workflow_id=context.workflow_id,
        workflow_status=workflow.status(),
        workflow_duration_ms=workflow_duration["workflow_duration_ms"],
        workflow_duration_us=workflow_duration["workflow_duration_us"],
        workflow_steps=steps,
        outcome=outcome,
        rag_mode=context.rag_mode,
        rag_source_count=rag_source_count,
        rag_reconciliation_count=context.rag_reconciliation_count,
        security_scan=security_scan,
        security_status=security_status,
        json_parse_success=context.json_parse_success,
        saved_to_history=context.saved_to_history,
        application_id=context.application_id,
        next_action=next_action_code,
        error_code=error_code,
        error_stage=error_stage,
        source_type=context.source_type,
        provider_observation=context.model_metadata,
    )
    persist_analysis_metrics_best_effort(metric, steps)


def fail_analysis_and_raise(
    workflow: AgentWorkflow,
    context: WorkflowContext,
    *,
    step_key: str,
    message: str,
    error_code: str,
    exc: Exception,
    status_code: int = 500,
) -> None:
    http_detail = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) else {}
    effective_error_code = (
        exc.error_code
        if isinstance(exc, ModelOutputError)
        else str(http_detail.get("error_code") or error_code)
    )
    effective_message = (
        exc.safe_message
        if isinstance(exc, ModelOutputError)
        else str(http_detail.get("message") or message)
    )
    workflow.fail_step(step_key, effective_message)
    record_analysis_observation(
        workflow,
        context,
        outcome="failed",
        error_code=effective_error_code,
        error_stage=step_key,
    )
    if isinstance(exc, ModelOutputError):
        metadata = safe_model_metadata(exc.metadata or context.model_metadata)
        context.model_metadata = metadata
        raise HTTPException(
            status_code=502,
            detail={
                "message": exc.safe_message,
                "workflow_id": context.workflow_id,
                "error_code": effective_error_code,
                "error_stage": step_key,
                "model_metadata": {
                    key: metadata.get(key)
                    for key in (
                        "finish_reason",
                        "input_tokens",
                        "output_tokens",
                        "total_tokens",
                        "response_length",
                        "reached_token_limit",
                        "latency_ms",
                    )
                },
                "rag_diagnostics": {
                    "retrieval_succeeded": bool(context.rag_mode == "project"),
                    "retrieval_count": len(context.retrieved_chunks),
                },
            },
        ) from exc
    if isinstance(exc, HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else effective_message
        details = http_detail.get("details")
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": message,
                "workflow_id": context.workflow_id,
                "error_code": effective_error_code,
                "error_stage": step_key,
                "details": details if isinstance(details, dict) else {},
            },
        ) from exc
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": effective_message,
            "workflow_id": context.workflow_id,
            "error_code": effective_error_code,
            "error_stage": step_key,
            "details": {},
        },
    ) from exc


@app.get("/")
def root() -> dict[str, str]:
    response = {
        "message": "Personal Job Agent API",
        "version": APP_VERSION,
        "health": "/api/health",
    }
    if settings.enable_api_docs:
        response["docs"] = "/docs"
    return response


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}


@app.get("/api/ready")
def readiness_check() -> JSONResponse:
    payload, status_code = readiness_status()
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/security/policy")
def get_security_policy() -> dict[str, Any]:
    return {
        "version": SECURITY_POLICY_VERSION,
        "prompt_injection_detection": True,
        "secret_detection": True,
        "pii_redaction": True,
        "output_leakage_scan": True,
        "limitations": [
            "Pattern-based detection may produce false positives or false negatives.",
            "The system cannot guarantee complete prompt injection prevention.",
        ],
    }


@app.get("/api/monitoring/status")
def get_monitoring_status() -> dict[str, Any]:
    return monitoring_status()


def request_client_host(request: Request) -> str | None:
    return request.client.host if request.client else None


def model_payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # Pydantic v2
    return model.dict()  # Pydantic v1


def raise_data_management_error(exc: DataManagementError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"message": exc.message, "error_code": exc.error_code},
    ) from exc


@app.get("/api/monitoring/data-management/status")
def get_data_management_status(request: Request) -> dict[str, Any]:
    return data_management_status(request_client_host(request))


@app.post("/api/monitoring/data/preview")
def post_monitoring_data_preview(
    payload: MonitoringDataManagementRequest,
    request: Request,
    admin_token: str | None = Header(default=None, alias="X-Monitoring-Admin-Token"),
) -> dict[str, Any]:
    try:
        authorize_destructive_request(admin_token, request_client_host(request))
        return preview_monitoring_deletion(model_payload(payload))
    except DataManagementError as exc:
        raise_data_management_error(exc)


@app.delete("/api/monitoring/data")
def delete_monitoring_data_endpoint(
    payload: MonitoringDataManagementRequest,
    request: Request,
    admin_token: str | None = Header(default=None, alias="X-Monitoring-Admin-Token"),
) -> dict[str, Any]:
    try:
        authorize_destructive_request(admin_token, request_client_host(request))
        return delete_monitoring_data(model_payload(payload))
    except DataManagementError as exc:
        raise_data_management_error(exc)


@app.get("/api/monitoring/overview")
def get_monitoring_overview_endpoint(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return get_monitoring_overview(days)


@app.get("/api/monitoring/workflow-steps")
def get_monitoring_workflow_steps(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return get_workflow_step_performance(days)


@app.get("/api/monitoring/rag")
def get_monitoring_rag(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return get_rag_metrics(days)


@app.get("/api/monitoring/security")
def get_monitoring_security(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return get_security_metrics(days)


@app.get("/api/monitoring/recommendations")
def get_monitoring_recommendations(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    return get_recommendation_metrics(days)


@app.get("/api/monitoring/traces")
def get_monitoring_traces(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    outcome: str | None = Query(None),
    security_status: str | None = Query(None),
    risk_level: str | None = Query(None),
) -> dict[str, Any]:
    return list_traces(
        days=days,
        limit=limit,
        offset=offset,
        outcome=outcome,
        security_status=security_status,
        risk_level=risk_level,
    )


@app.get("/api/monitoring/traces/{workflow_id}")
def get_monitoring_trace_detail(workflow_id: str) -> dict[str, Any]:
    trace = get_trace_detail(workflow_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Workflow trace not found.")
    return trace


@app.delete("/api/monitoring/traces/{workflow_id}")
def delete_monitoring_trace_endpoint(
    workflow_id: str,
    payload: TraceDeletionRequest,
    request: Request,
    admin_token: str | None = Header(default=None, alias="X-Monitoring-Admin-Token"),
) -> dict[str, Any]:
    try:
        authorize_destructive_request(admin_token, request_client_host(request))
        return delete_trace(workflow_id, model_payload(payload))
    except DataManagementError as exc:
        raise_data_management_error(exc)


@app.get("/api/evaluations/status")
def get_evaluations_status() -> dict[str, Any]:
    return evaluation_status()


@app.post("/api/evaluations/data/preview")
def post_evaluation_data_preview(
    payload: EvaluationDataManagementRequest,
    request: Request,
    admin_token: str | None = Header(default=None, alias="X-Monitoring-Admin-Token"),
) -> dict[str, Any]:
    try:
        authorize_destructive_request(admin_token, request_client_host(request))
        return preview_evaluation_deletion(model_payload(payload))
    except DataManagementError as exc:
        raise_data_management_error(exc)


@app.delete("/api/evaluations/data")
def delete_evaluation_data_endpoint(
    payload: EvaluationDataManagementRequest,
    request: Request,
    admin_token: str | None = Header(default=None, alias="X-Monitoring-Admin-Token"),
) -> dict[str, Any]:
    try:
        authorize_destructive_request(admin_token, request_client_host(request))
        return delete_evaluation_data(model_payload(payload))
    except DataManagementError as exc:
        raise_data_management_error(exc)


@app.post("/api/evaluations/run")
def post_evaluation_run(payload: EvaluationRunRequest) -> dict[str, Any]:
    if payload.mode != "offline":
        raise HTTPException(
            status_code=400,
            detail="Live LLM evaluation is not supported in Version 1.9.",
        )
    try:
        return run_evaluation_suite(payload.suite_name, payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/evaluations/runs")
def get_evaluation_runs_endpoint(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    return list_evaluation_runs(limit=limit, offset=offset)


@app.get("/api/evaluations/runs/{run_id}")
def get_evaluation_run_endpoint(run_id: str) -> dict[str, Any]:
    run = get_evaluation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return run


@app.get("/api/project-knowledge/status")
def get_project_knowledge_status() -> dict[str, Any]:
    return project_knowledge_status_data()


@app.post("/api/project-knowledge/rebuild")
def post_project_knowledge_rebuild() -> dict[str, Any]:
    return rebuild_project_knowledge_index()


@app.get("/api/project-knowledge/search")
def get_project_knowledge_search(
    query: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=10),
) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise HTTPException(status_code=400, detail="query is required.")

    items, retrieval_method = search_project_knowledge(clean_query, clamp_rag_top_k(top_k))
    logger.info(
        "Project Knowledge search completed result_count=%s retrieval_method=%s",
        len(items),
        retrieval_method,
    )
    return {"items": items, "retrieval_method": retrieval_method}


@app.post("/api/project-knowledge/upload")
async def post_project_knowledge_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    validate_project_knowledge_upload_name(file.filename or "")
    file_bytes = await file.read(PROJECT_KNOWLEDGE_MAX_UPLOAD_BYTES + 1)
    content = clean_knowledge_text(decode_project_knowledge_upload(file_bytes))
    if not content:
        raise HTTPException(status_code=400, detail="Project Knowledge content is empty.")

    write_project_knowledge_file(content)
    rebuild_result = rebuild_project_knowledge_index()
    return {
        "uploaded": True,
        "source_path": PROJECT_KNOWLEDGE_SOURCE_PATH,
        "document_id": rebuild_result["document_id"],
        "chunk_count": rebuild_result["chunk_count"],
        "message": "Project knowledge file uploaded and indexed successfully.",
    }


@app.get("/api/knowledge/documents")
def get_knowledge_documents(
    category: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
) -> dict[str, Any]:
    raise_generic_knowledge_disabled()


@app.post("/api/knowledge/documents")
async def post_knowledge_document(
    title: str | None = Form(None),
    category: str | None = Form(None),
    content_text: str | None = Form(None),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    raise_generic_knowledge_disabled()


@app.get("/api/knowledge/documents/{document_id}")
def get_knowledge_document_detail(document_id: int) -> dict[str, Any]:
    raise_generic_knowledge_disabled()


@app.delete("/api/knowledge/documents/{document_id}")
def delete_knowledge_document_endpoint(document_id: int) -> dict[str, Any]:
    raise_generic_knowledge_disabled()


@app.get("/api/knowledge/search")
def search_knowledge(
    query: str | None = Query(None),
    top_k: int = Query(5),
) -> dict[str, Any]:
    raise_generic_knowledge_disabled()


@app.get("/api/history")
@app.get("/api/applications")
def get_applications(
    request: Request,
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    stage: str | None = Query(None),
    archived: bool = Query(False),
) -> Any:
    current_user = getattr(request.state, "v2_user", None)
    if request.url.path == "/api/history":
        clean_status = validate_application_status(status, required=False)
        clean_search = (search or "").strip() or None
        items, total = list_application_records(
            status=clean_status,
            search=clean_search,
            limit=limit,
            offset=offset,
            owner_user_id=getattr(current_user, "id", None),
            include_unowned=getattr(current_user, "role", "") == "admin",
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    legacy_query = any(key in request.query_params for key in ("status", "search", "limit", "offset"))
    if not legacy_query:
        from app.applications.service import ApplicationService

        current_user = getattr(request.state, "v2_user", None)
        current_db = getattr(request.state, "v2_db", None)
        if current_user is None or current_db is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        return ApplicationService(current_db, current_user.id).list(stage, archived)
    clean_status = validate_application_status(status, required=False)
    clean_search = (search or "").strip() or None
    items, total = list_application_records(
        status=clean_status,
        search=clean_search,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/history/{application_id}")
@app.get("/api/applications/{application_id}")
def get_application(application_id: str, request: Request) -> dict[str, Any]:
    from uuid import UUID

    try:
        version_2_id = UUID(application_id)
    except ValueError:
        try:
            legacy_id = int(application_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Application not found.") from exc
        if request.url.path.startswith("/api/history/"):
            return get_owned_history_record(legacy_id, request)
        return get_existing_application_record(legacy_id)
    from app.applications.service import ApplicationNotFound, ApplicationService

    current_user = getattr(request.state, "v2_user", None)
    current_db = getattr(request.state, "v2_db", None)
    if current_user is None or current_db is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return ApplicationService(current_db, current_user.id).get(version_2_id)
    except ApplicationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/history/{application_id}/cover-letter.docx")
@app.get("/api/applications/{application_id}/cover-letter.docx")
def export_cover_letter_docx(application_id: int, request: Request) -> StreamingResponse:
    record = get_owned_history_record(application_id, request) if request.url.path.startswith("/api/history/") else get_existing_application_record(application_id)
    buffer = build_cover_letter_docx(record)
    filename = build_export_filename("cover-letter", record, "docx")
    logger.info("Cover letter export generated application_id=%s", application_id)
    return StreamingResponse(
        buffer,
        media_type=DOCX_MEDIA_TYPE,
        headers=attachment_headers(filename),
    )


@app.head("/api/history/{application_id}/cover-letter.docx")
@app.head("/api/applications/{application_id}/cover-letter.docx")
def head_cover_letter_docx(application_id: int, request: Request) -> Response:
    record = get_owned_history_record(application_id, request) if request.url.path.startswith("/api/history/") else get_existing_application_record(application_id)
    filename = build_export_filename("cover-letter", record, "docx")
    return Response(media_type=DOCX_MEDIA_TYPE, headers=attachment_headers(filename))


@app.get("/api/history/{application_id}/report.pdf")
@app.get("/api/applications/{application_id}/report.pdf")
def export_analysis_report_pdf(application_id: int, request: Request) -> StreamingResponse:
    record = get_owned_history_record(application_id, request) if request.url.path.startswith("/api/history/") else get_existing_application_record(application_id)
    buffer = build_analysis_report_pdf(record)
    filename = build_export_filename("analysis-report", record, "pdf")
    logger.info("Analysis report export generated application_id=%s", application_id)
    return StreamingResponse(
        buffer,
        media_type=PDF_MEDIA_TYPE,
        headers=attachment_headers(filename),
    )


@app.head("/api/history/{application_id}/report.pdf")
@app.head("/api/applications/{application_id}/report.pdf")
def head_analysis_report_pdf(application_id: int, request: Request) -> Response:
    record = get_owned_history_record(application_id, request) if request.url.path.startswith("/api/history/") else get_existing_application_record(application_id)
    filename = build_export_filename("analysis-report", record, "pdf")
    return Response(media_type=PDF_MEDIA_TYPE, headers=attachment_headers(filename))


@app.patch("/api/history/{application_id}")
@app.patch("/api/applications/{application_id}")
async def patch_application(application_id: str, request: Request) -> dict[str, Any]:
    from uuid import UUID

    raw_payload = await request.json()
    try:
        version_2_id = UUID(application_id)
    except ValueError:
        try:
            legacy_id = int(application_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Application not found.") from exc
        try:
            payload = ApplicationUpdate.model_validate(raw_payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="Application update is invalid.") from exc
        clean_status = validate_application_status(payload.application_status, required=True)
        notes_provided = field_was_provided(payload, "notes")
        updated_record = update_application_record(
            legacy_id,
            application_status=clean_status,
            notes=payload.notes,
            update_notes=notes_provided,
            owner_user_id=getattr(getattr(request.state, "v2_user", None), "id", None) if request.url.path.startswith("/api/history/") else None,
            include_unowned=getattr(getattr(request.state, "v2_user", None), "role", "") == "admin" if request.url.path.startswith("/api/history/") else False,
        )

        if updated_record is None:
            raise HTTPException(status_code=404, detail="Application record not found.")
        return updated_record

    from app.applications.schemas import ApplicationPatch
    from app.applications.service import ApplicationConflict, ApplicationNotFound, ApplicationService

    current_user = getattr(request.state, "v2_user", None)
    current_db = getattr(request.state, "v2_db", None)
    if current_user is None or current_db is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        payload = ApplicationPatch.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Application update is invalid.") from exc
    try:
        return ApplicationService(current_db, current_user.id).update(
            version_2_id, payload.model_dump(exclude_unset=True)
        )
    except ApplicationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApplicationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/history/{application_id}/next-action")
@app.patch("/api/applications/{application_id}/next-action")
def patch_next_action_decision(
    application_id: int,
    payload: NextActionDecisionUpdate,
    request: Request,
) -> dict[str, Any]:
    decision = validate_next_action_decision(payload.decision)
    updated_record = update_next_action_decision(
        application_id,
        decision=decision,
        notes=payload.notes,
        owner_user_id=getattr(getattr(request.state, "v2_user", None), "id", None) if request.url.path.startswith("/api/history/") else None,
        include_unowned=getattr(getattr(request.state, "v2_user", None), "role", "") == "admin" if request.url.path.startswith("/api/history/") else False,
    )
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Application record not found.")

    return {
        "application_id": application_id,
        "next_action": updated_record.get("next_action") or {},
        "decision": updated_record.get("next_action_decision") or "pending",
        "notes": updated_record.get("next_action_decision_notes") or "",
        "decided_at": updated_record.get("next_action_decided_at"),
    }


@app.delete("/api/history/{application_id}")
@app.delete("/api/applications/{application_id}")
async def delete_application(application_id: str, request: Request) -> dict[str, Any]:
    from uuid import UUID

    try:
        version_2_id = UUID(application_id)
    except ValueError:
        try:
            legacy_id = int(application_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Application not found.") from exc
        deleted = delete_application_record(
            legacy_id,
            owner_user_id=getattr(getattr(request.state, "v2_user", None), "id", None) if request.url.path.startswith("/api/history/") else None,
            include_unowned=getattr(getattr(request.state, "v2_user", None), "role", "") == "admin" if request.url.path.startswith("/api/history/") else False,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Application record not found.")
        return {"deleted": True, "id": legacy_id}

    from app.applications.schemas import ExpectedRevision
    from app.applications.service import ApplicationConflict, ApplicationNotFound, ApplicationService

    current_user = getattr(request.state, "v2_user", None)
    current_db = getattr(request.state, "v2_db", None)
    if current_user is None or current_db is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        payload = ExpectedRevision.model_validate(await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Application archive request is invalid.") from exc
    try:
        return ApplicationService(current_db, current_user.id).archive(
            version_2_id, payload.expected_revision
        )
    except ApplicationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApplicationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _provider_deadline_exhausted(provider_budget: ProviderDeadline, exc: Exception) -> bool:
    metadata = exc.metadata if isinstance(exc, ModelOutputError) else {}
    return bool(provider_budget.expired() or metadata.get("deadline_exhausted"))


def _select_provider_fallback(
    context: WorkflowContext,
    analysis_warnings: list[str],
    *,
    metadata: dict[str, Any],
    fallback_reason: str,
    deadline_exhausted: bool,
) -> dict[str, Any]:
    context.model_metadata = safe_model_metadata({
        **metadata,
        "result_state": "fallback",
        "fallback_reason": fallback_reason,
        "deadline_exhausted": deadline_exhausted,
        "fallback_selected": True,
    })
    analysis_warnings.append(
        "AI response could not be fully parsed. A local fallback analysis is shown."
    )
    return local_fallback_result(
        context.sanitized_resume_text,
        context.sanitized_job_text,
        context.retrieved_chunks,
    )


@app.post("/api/analyze")
async def analyze(
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    resume: UploadFile | None = File(None),
    job_text: str | None = Form(None),
    job_url: str | None = Form(None),
    save_to_history: bool = Form(True),
    use_knowledge_base: bool = Form(True),
    use_project_knowledge: bool | None = Form(None),
    rag_top_k: int = Form(5),
    project_knowledge_top_k: int | None = Form(None),
    rag_mode: str | None = Form(None),
    resume_version_id: str | None = Form(None),
) -> dict[str, Any]:
    logger.info("Received analysis request")
    analysis_started_monotonic = time.monotonic()
    analysis_safety_deadline = (
        analysis_started_monotonic + ANALYZE_TOTAL_SAFETY_DEADLINE_SECONDS
    )
    try:
        clean_idempotency_key = validate_idempotency_key(idempotency_key)
    except IdempotencyError as exc:
        raise idempotency_http_exception(exc) from exc
    idempotency_service: AnalyzeIdempotencyService | None = None
    idempotency_claim = None
    fingerprint: str | None = None
    execution_binding = None
    workflow = AgentWorkflow()
    request.state.workflow_id = workflow.workflow_id

    prepared_input = await prepare_analyze_input(
        request=request,
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
        config=settings,
        failure_handler=fail_analysis_and_raise,
    )
    context = prepared_input.context
    clean_resume_version_id = prepared_input.resume_version_id
    input_warnings = prepared_input.warnings

    if clean_idempotency_key:
        current_user = getattr(request.state, "v2_user", None)
        current_db = getattr(request.state, "v2_db", None)
        if current_user is None or current_db is None:
            raise HTTPException(
                status_code=401,
                detail=analyze_error_detail(
                    "Authentication required.",
                    "AUTHENTICATION_REQUIRED",
                    "authentication",
                ),
            )
        knowledge_version = project_knowledge_version(
            current_db, context.rag_mode == "project"
        )
        fingerprint = analyze_request_fingerprint(
            resume_version_id=clean_resume_version_id or None,
            resume_text=context.resume_text,
            job_text=context.job_text,
            job_url=context.job_url,
            rag_enabled=context.rag_mode == "project",
            rag_top_k=context.rag_top_k,
            project_knowledge=knowledge_version,
            save_to_history=save_to_history,
            model=DEEPSEEK_MODEL,
            security_policy_version=SECURITY_POLICY_VERSION,
        )
        idempotency_service = AnalyzeIdempotencyService()
        try:
            idempotency_claim = idempotency_service.claim(
                user_id=current_user.id,
                key_hash=hash_idempotency_key(clean_idempotency_key),
                fingerprint=fingerprint,
                request_id=request_id_for(request),
            )
        except IdempotencyError as exc:
            raise idempotency_http_exception(exc) from exc
        if idempotency_claim.is_replay:
            return JSONResponse(
                status_code=idempotency_claim.replay_status or 200,
                content=idempotency_claim.replay_body,
                headers={
                    "Idempotency-Replayed": "true",
                    "X-Request-ID": request_id_for(request),
                },
            )
        request.state.analyze_idempotency_service = idempotency_service
        request.state.analyze_idempotency_claim = idempotency_claim

    workflow.start_step("scan_untrusted_input", "Scan Untrusted Input")
    try:
        sanitized_resume_text, resume_scan = prepare_resume_for_llm(context.resume_text)
        sanitized_job_text, job_scan = scan_and_sanitize_untrusted_text(
            context.job_text,
            "job_description",
        )
        context.sanitized_resume_text = sanitized_resume_text
        context.sanitized_job_text = sanitized_job_text
        context.security_scan = merge_security_scans(resume_scan, job_scan)
        if context.security_scan.get("blocked"):
            workflow.fail_step(
                "scan_untrusted_input",
                "Sensitive credential-like content was detected before LLM invocation.",
            )
            skip_workflow_steps_after(
                workflow,
                after_key="scan_untrusted_input",
                message="Skipped because security scanning blocked the request.",
            )
            raise_security_blocked(workflow, context)
        if context.security_scan.get("prompt_injection_detected"):
            workflow.add_warning()
        workflow.complete_step(
            "scan_untrusted_input",
            "Untrusted resume and job description were scanned and prepared for analysis.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="scan_untrusted_input",
            message="Security scanning failed.",
            error_code="UNTRUSTED_INPUT_SCAN_FAILED",
            exc=exc,
        )

    if settings.jd_normalization.mode == "shadow" and fingerprint is None:
        current_db = getattr(request.state, "v2_db", None)
        knowledge_version = project_knowledge_version(
            current_db,
            context.rag_mode == "project",
        )
        fingerprint = analyze_request_fingerprint(
            resume_version_id=clean_resume_version_id or None,
            resume_text=context.resume_text,
            job_text=context.job_text,
            job_url=context.job_url,
            rag_enabled=context.rag_mode == "project",
            rag_top_k=context.rag_top_k,
            project_knowledge=knowledge_version,
            save_to_history=save_to_history,
            model=DEEPSEEK_MODEL,
            security_policy_version=SECURITY_POLICY_VERSION,
        )

    try:
        effective_normalization = await select_effective_normalization(
            client=getattr(
                request.app.state,
                "jd_normalization_client",
                None,
            ),
            config=settings.jd_normalization,
            local_sanitized_job_text=context.sanitized_job_text,
            request_id=request_id_for(request),
            logger=logger,
            stable_request_fingerprint=fingerprint,
        )
        context.sanitized_job_text = effective_normalization.text
        if effective_normalization.accepted_security_scan:
            context.security_scan = merge_security_scans(
                context.security_scan,
                effective_normalization.accepted_security_scan,
            )
            if effective_normalization.accepted_security_scan.get(
                "prompt_injection_detected"
            ):
                workflow.add_warning()
        if idempotency_service is not None and idempotency_claim is not None:
            if fingerprint is None:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The Analyze execution binding is unavailable.",
                )
            execution_binding = effective_normalization.execution_binding(
                fingerprint
            )
            idempotency_service.bind_execution(
                idempotency_claim,
                execution_binding,
            )
    except IdempotencyError as exc:
        raise idempotency_http_exception(exc) from exc
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="scan_untrusted_input",
            message="Job Description normalization failed safely.",
            error_code="JD_NORMALIZATION_FAILED",
            exc=exc,
        )

    logger.info(
        "Analyze RAG settings rag_mode=%s use_knowledge_base=%s rag_top_k=%s",
        context.rag_mode,
        context.rag_mode == "project",
        context.rag_top_k,
    )
    if context.rag_mode == "off":
        workflow.skip_step(
            "retrieve_project_evidence",
            "Retrieve Project Knowledge",
            "Project Knowledge RAG is off for this analysis.",
        )
    else:
        workflow.start_step("retrieve_project_evidence", "Retrieve Project Knowledge")
        try:
            retrieval_query = build_knowledge_retrieval_query(
                context.sanitized_job_text,
                context.sanitized_resume_text,
            )
            rag_chunks, retrieval_method = search_project_knowledge(
                retrieval_query,
                context.rag_top_k,
            )
            context.retrieved_chunks = rag_chunks
            context.rag_sources = build_default_rag_sources(rag_chunks)
            if not rag_chunks:
                workflow.add_warning()
            workflow.complete_step(
                "retrieve_project_evidence",
                (
                    f"Retrieved {len(rag_chunks)} Project Knowledge source(s) "
                    f"using {retrieval_method}."
                ),
            )
        except Exception as exc:
            fail_analysis_and_raise(
                workflow,
                context,
                step_key="retrieve_project_evidence",
                message="Project Knowledge retrieval failed.",
                error_code="PROJECT_KNOWLEDGE_RETRIEVAL_FAILED",
                exc=exc,
            )
        logger.info(
            "Project Knowledge retrieval completed result_count=%s retrieval_method=%s chunk_ids=%s titles=%s",
            len(context.retrieved_chunks),
            retrieval_method if context.retrieved_chunks else "none",
            [chunk.get("chunk_id") for chunk in context.retrieved_chunks],
            [chunk.get("document_title") for chunk in context.retrieved_chunks],
        )

    if context.rag_mode == "off":
        workflow.skip_step(
            "scan_project_evidence",
            "Scan Project Evidence",
            "Project Knowledge RAG is off for this analysis.",
        )
    else:
        workflow.start_step("scan_project_evidence", "Scan Project Evidence")
        try:
            sanitized_chunks, project_scan, filtered_sources = scan_project_chunks(
                context.retrieved_chunks
            )
            context.retrieved_chunks = sanitized_chunks
            context.security_filtered_rag_sources = filtered_sources
            context.rag_sources = build_default_rag_sources(sanitized_chunks)
            if filtered_sources:
                context.rag_sources.extend(filtered_sources)
            context.security_scan = merge_security_scans(context.security_scan, project_scan)
            if project_scan.get("prompt_injection_detected"):
                workflow.add_warning()
            if context.security_scan.get("blocked"):
                workflow.fail_step(
                    "scan_project_evidence",
                    "Sensitive credential-like content was detected in Project Knowledge evidence.",
                )
                skip_workflow_steps_after(
                    workflow,
                    after_key="scan_project_evidence",
                    message="Skipped because security scanning blocked the request.",
                )
                raise_security_blocked(
                    workflow,
                    context,
                    error_code="INPUT_SECURITY_BLOCKED",
                    error_stage="scan_project_evidence",
                )
            workflow.complete_step(
                "scan_project_evidence",
                (
                    f"Scanned {len(context.retrieved_chunks)} Project Knowledge source(s); "
                    f"filtered {len(filtered_sources)} source(s)."
                ),
            )
        except HTTPException:
            raise
        except Exception as exc:
            fail_analysis_and_raise(
                workflow,
                context,
                step_key="scan_project_evidence",
                message="Project evidence security scan failed.",
                error_code="PROJECT_EVIDENCE_SCAN_FAILED",
                exc=exc,
            )

    workflow.start_step("build_safe_prompt", "Build Safe Prompt")
    try:
        context.safe_prompt = build_safe_analysis_prompt(
            resume_text=context.sanitized_resume_text,
            job_description=context.sanitized_job_text,
            rag_chunks=context.retrieved_chunks,
        )
        workflow.complete_step(
            "build_safe_prompt",
            "Safe prompt built with isolated untrusted data sections.",
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="build_safe_prompt",
            message="Safe prompt construction failed.",
            error_code="SAFE_PROMPT_BUILD_FAILED",
            exc=exc,
        )

    workflow.start_step("run_llm_analysis", "Run LLM Analysis")
    analysis_status = "complete"
    analysis_warnings: list[str] = list(input_warnings)
    provider_phase_started_monotonic = time.monotonic()
    runtime_settings = load_config(validate_production=False)
    provider_budget = ProviderDeadline.for_phase(
        phase_started_monotonic=provider_phase_started_monotonic,
        configured_deadline_seconds=runtime_settings.provider_overall_deadline_seconds,
        request_safety_deadline=analysis_safety_deadline,
    )
    provider_deadline = provider_budget.absolute_deadline
    client_disconnected = await _request_client_disconnected(request)
    try:
        if client_disconnected:
            raise ModelOutputError(
                MODEL_PROVIDER_ERROR,
                metadata=safe_model_metadata({
                    **_provider_metadata_base(runtime_settings),
                    "client_disconnected": True,
                    "fallback_reason": "client_disconnected",
                    "deadline_exhausted": False,
                    "fallback_selected": True,
                    "remaining_deadline_bucket": provider_budget.remaining_bucket(),
                    "provider_phase_duration_ms": 0.0,
                }),
            )
        if idempotency_service is not None and idempotency_claim is not None:
            if execution_binding is None:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The Analyze execution binding is unavailable.",
                )
            idempotency_service.provider_started(
                idempotency_claim,
                execution_binding,
            )
        provider_response = call_deepseek_raw(
            context.sanitized_resume_text,
            context.sanitized_job_text,
            context.retrieved_chunks,
            analysis_prompt=context.safe_prompt,
            usage_out=context.model_metadata,
            deadline_monotonic=provider_deadline,
        )
        context.llm_raw_response = provider_response.content
        context.model_metadata = dict(provider_response.metadata)
        workflow.complete_step(
            "run_llm_analysis",
            "Provider returned a complete response with safe completion metadata.",
        )
    except IdempotencyError as exc:
        raise idempotency_http_exception(exc) from exc
    except Exception as exc:
        workflow.add_warning()
        error_metadata = exc.metadata if isinstance(exc, ModelOutputError) else {}
        provider_deadline_exhausted = _provider_deadline_exhausted(provider_budget, exc)
        fallback_reason = (
            "client_disconnected"
            if error_metadata.get("client_disconnected")
            else (
                "provider_deadline_exhausted"
                if provider_deadline_exhausted
                else "provider_call_failed"
            )
        )
        analysis_status = "fallback"
        result = _select_provider_fallback(
            context,
            analysis_warnings,
            metadata={
                **error_metadata,
                "model_id": DEEPSEEK_MODEL,
                "thinking_enabled": settings.deepseek_thinking_enabled,
                "response_mode": "json_object",
            },
            fallback_reason=fallback_reason,
            deadline_exhausted=provider_deadline_exhausted,
        )
        workflow.complete_step(
            "run_llm_analysis",
            "Provider was unavailable; continuing with deterministic local analysis.",
        )
        logger.warning(
            "DeepSeek analysis unavailable; local fallback selected fallback_category=%s",
            context.model_metadata.get("fallback_reason") or "provider_call_failed",
        )

    if analysis_status != "fallback":
        workflow.start_step("scan_llm_output", "Scan LLM Output")
        try:
            sanitized_output, output_scan, marker_leaked = scan_llm_output(context.llm_raw_response)
            context.security_scan = merge_security_scans(context.security_scan, output_scan)
            if output_scan.get("findings"):
                workflow.add_warning()
            if marker_leaked or output_scan.get("sensitive_data_detected") or output_scan.get("blocked"):
                workflow.fail_step(
                    "scan_llm_output",
                    "LLM output security scanning detected a blocking security finding.",
                )
                skip_workflow_steps_after(
                    workflow,
                    after_key="scan_llm_output",
                    message="Skipped because LLM output security scanning blocked the response.",
                )
                raise_security_blocked(
                    workflow,
                    context,
                    status_code=502,
                    message="LLM output failed security validation. Please try again.",
                    error_code="OUTPUT_SECURITY_BLOCKED",
                    error_stage="scan_llm_output",
                )
            context.llm_raw_response = sanitized_output
            workflow.complete_step(
                "scan_llm_output",
                "LLM output was scanned for credential and internal marker leakage.",
            )
        except HTTPException:
            raise
        except Exception as exc:
            fail_analysis_and_raise(
                workflow,
                context,
                step_key="scan_llm_output",
                message="LLM output security scanning failed.",
                error_code="LLM_OUTPUT_SCAN_FAILED",
                exc=exc,
            )
    else:
        workflow.skip_step(
            "scan_llm_output", "Scan LLM Output", "No provider output was available to scan."
        )

    workflow.start_step("parse_model_json", "Parse Model JSON")
    if analysis_status != "fallback":
        try:
            parse_metadata: dict[str, Any] = {}

            def repairer(raw_response: str) -> ProviderAnalysisResponse:
                if idempotency_service is not None and idempotency_claim is not None:
                    if execution_binding is None:
                        raise IdempotencyError(
                            "IDEMPOTENCY_PERSISTENCE_FAILED",
                            "The Analyze execution binding is unavailable.",
                        )
                    idempotency_service.provider_started(
                        idempotency_claim,
                        execution_binding,
                    )
                repair_metadata: dict[str, Any] = {}
                try:
                    repaired = call_deepseek_repair(
                        raw_response,
                        usage_out=repair_metadata,
                        deadline_monotonic=provider_deadline,
                    )
                finally:
                    context.model_metadata = safe_model_metadata({
                        **context.model_metadata,
                        **repair_metadata,
                    })
                repaired_content = (
                    repaired.content
                    if isinstance(repaired, ProviderAnalysisResponse)
                    else str(repaired or "")
                )
                sanitized_repair, repair_scan, repair_marker = scan_llm_output(repaired_content)
                context.security_scan = merge_security_scans(context.security_scan, repair_scan)
                if repair_marker or repair_scan.get("sensitive_data_detected") or repair_scan.get("blocked"):
                    workflow.fail_step(
                        "parse_model_json",
                        "Format repair output failed the blocking security boundary.",
                    )
                    skip_workflow_steps_after(
                        workflow,
                        after_key="parse_model_json",
                        message="Skipped because the format repair output was blocked by security scanning.",
                    )
                    raise_security_blocked(
                        workflow,
                        context,
                        status_code=502,
                        message="LLM output failed security validation. Please try again.",
                        error_code="OUTPUT_SECURITY_BLOCKED",
                        error_stage="scan_llm_output",
                    )
                return ProviderAnalysisResponse(
                    content=sanitized_repair,
                    metadata=(
                        repaired.metadata
                        if isinstance(repaired, ProviderAnalysisResponse)
                        else {}
                    ),
                )
            result, analysis_status, parsed_warnings = model_response_to_result(
                context.llm_raw_response,
                repairer=repairer,
                metadata_out=parse_metadata,
                resume_text=context.sanitized_resume_text,
                job_description=context.sanitized_job_text,
            )
            removed_narratives = sanitize_provider_narratives(
                result,
                resume_text=context.sanitized_resume_text,
                job_description=context.sanitized_job_text,
                retrieved_chunks=context.retrieved_chunks,
            )
            if removed_narratives:
                parsed_warnings.append(
                    "Unsupported narrative claims were removed while preserving the safe analysis."
                )
                if analysis_status == "complete":
                    analysis_status = "partial"
            context.model_metadata = safe_model_metadata({
                **context.model_metadata,
                **parse_metadata,
                "result_state": analysis_status,
            })
            analysis_warnings.extend(parsed_warnings)
            context.json_parse_success = True
            if analysis_status != "complete":
                workflow.add_warning()
            workflow.complete_step(
                "parse_model_json",
                "Model output was parsed with bounded normalization.",
            )
            workflow.start_step("validate_structured_output", "Validate Structured Output")
            workflow.complete_step(
                "validate_structured_output",
                "Usable analysis fields passed the tolerant compact Schema.",
            )
        except IdempotencyError as exc:
            raise idempotency_http_exception(exc) from exc
        except HTTPException:
            raise
        except Exception as exc:
            context.json_parse_success = False
            workflow.add_warning()
            analysis_status = "fallback"
            parse_deadline_exhausted = _provider_deadline_exhausted(provider_budget, exc)
            result = _select_provider_fallback(
                context,
                analysis_warnings,
                metadata=context.model_metadata,
                fallback_reason=(
                    "provider_deadline_exhausted"
                    if parse_deadline_exhausted
                    else "minimum_safe_contract_failed"
                ),
                deadline_exhausted=parse_deadline_exhausted,
            )
            workflow.complete_step(
                "parse_model_json",
                "Model parsing and the one allowed repair were unusable; local fallback selected.",
            )
            workflow.start_step("validate_structured_output", "Validate Structured Output")
            workflow.complete_step(
                "validate_structured_output",
                "Deterministic fallback output has the stable analysis structure.",
            )
            logger.warning(
                "DeepSeek response fallback selected fallback_category=%s",
                context.model_metadata.get("fallback_reason") or "minimum_safe_contract_failed",
            )
    else:
        context.json_parse_success = False
        workflow.complete_step(
            "parse_model_json",
            "Provider output was unavailable; local fallback required no JSON parsing.",
        )
        workflow.start_step("validate_structured_output", "Validate Structured Output")
        workflow.complete_step(
            "validate_structured_output", "Deterministic fallback output has the stable analysis structure."
        )

    if provider_budget.expired() and analysis_status != "fallback":
        analysis_status = "fallback"
        workflow.add_warning()
        result = _select_provider_fallback(
            context,
            analysis_warnings,
            metadata=context.model_metadata,
            fallback_reason="provider_deadline_exhausted",
            deadline_exhausted=True,
        )

    context.model_metadata = safe_model_metadata({
        **context.model_metadata,
        "provider_phase_duration_ms": round(
            (time.monotonic() - provider_phase_started_monotonic) * 1000,
            3,
        ),
        "deadline_exhausted": bool(
            context.model_metadata.get("deadline_exhausted") or provider_budget.expired()
        ),
        "fallback_selected": analysis_status == "fallback",
        "result_state": analysis_status,
        "remaining_deadline_bucket": provider_budget.remaining_bucket(),
    })
    provider_phase_completed_monotonic = time.monotonic()

    workflow.start_step("validate_evidence_references", "Validate Evidence References")
    try:
        evidence_validation = validate_model_evidence_references(
            result,
            resume_text=context.sanitized_resume_text,
            retrieved_chunks=context.retrieved_chunks,
        )
        if evidence_validation["rejected_reference_count"]:
            workflow.add_warning()
            analysis_warnings.append(
                "Unknown or unsupported evidence references were ignored without blocking the analysis."
            )
            if analysis_status == "complete":
                analysis_status = "partial"
        workflow.complete_step(
            "validate_evidence_references",
            (
                "Validated model evidence IDs against the current request; rejected "
                f"{evidence_validation['rejected_reference_count']} reference(s)."
            ),
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="validate_evidence_references",
            message="Evidence reference validation failed safely.",
            error_code="EVIDENCE_REFERENCE_VALIDATION_FAILED",
            exc=exc,
        )

    workflow.start_step("reconcile_evidence", "Reconcile Evidence")
    try:
        corrected_terms = reconcile_result_with_rag_evidence(result, context.retrieved_chunks)
        context.rag_reconciliation_count = len(corrected_terms)
        result["rag_mode"] = context.rag_mode
        result["used_knowledge_base"] = bool(
            context.rag_mode == "project" and context.retrieved_chunks
        )
        result["retrieval_count"] = len(context.retrieved_chunks)
        enforce_analysis_grounding(
            result,
            context.sanitized_resume_text,
            context.retrieved_chunks,
        )
        result["scoring_breakdown"] = deterministic_scoring(
            result,
            context.sanitized_resume_text,
            context.sanitized_job_text,
            context.retrieved_chunks,
        )
        result["match_score"] = calculate_weighted_match_score(result["scoring_breakdown"])
        ensure_deterministic_narratives(result, context.sanitized_job_text)
        result["rag_sources"] = build_default_rag_sources(
            context.retrieved_chunks,
            result.get("matched_skills") or [],
        )
        if not result["used_knowledge_base"]:
            result["rag_sources"] = []
        if (result.get("claim_validation") or {}).get("unsupported_claim_count"):
            workflow.add_warning()
            analysis_warnings.append(
                "Unsupported candidate claims were removed without blocking the reliable result."
            )
            if analysis_status == "complete":
                analysis_status = "partial"
        result["analysis_status"] = analysis_status
        # Evidence cleanup and deterministic grounding can change a provider
        # result from complete to partial after JSON parsing. Keep the
        # structured observation aligned with the final public state.
        context.model_metadata = safe_model_metadata({
            **context.model_metadata,
            "result_state": analysis_status,
        })
        result["analysis_warnings"] = list(dict.fromkeys(analysis_warnings))
        result["recommendations"] = normalize_list(
            result.get("recommendations") or result.get("resume_suggestions")
        )
        result["resume_suggestions"] = list(result["recommendations"])
        result.setdefault("unknown_skills", [])
        result.setdefault("cover_letter", "")
        result.setdefault("upgraded_resume_bullets", [])
        result.setdefault("ats_analysis", {})
        result.setdefault("evidence_mapping", [])
        workflow.complete_step(
            "reconcile_evidence",
            (
                f"Reconciled Project Knowledge evidence; corrected {len(corrected_terms)} "
                "RAG-supported term(s)."
            ),
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="reconcile_evidence",
            message="Evidence reconciliation failed.",
            error_code="EVIDENCE_RECONCILIATION_FAILED",
            exc=exc,
        )

    workflow.start_step("recommend_next_action", "Recommend Next Action")
    try:
        context.next_action = generate_next_action(result)
        result["next_action"] = context.next_action
        result["next_action_decision"] = "pending"
        workflow.complete_step(
            "recommend_next_action",
            f"Recommended next action: {context.next_action.get('label', 'No Recommendation')}.",
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="recommend_next_action",
            message="Next-action recommendation failed.",
            error_code="NEXT_ACTION_RECOMMENDATION_FAILED",
            exc=exc,
        )

    context.security_scan = normalized_security_scan(context.security_scan or empty_security_scan())
    context.security_status = security_status_from_scan(context.security_scan)
    result["security_scan"] = context.security_scan
    result["security_status"] = context.security_status
    result["security_policy_version"] = SECURITY_POLICY_VERSION

    workflow.start_step("final_output_scan", "Final Output Security Scan")
    try:
        serialized_result = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
        _sanitized_final, final_scan, final_marker = scan_llm_output(serialized_result)
        context.security_scan = merge_security_scans(context.security_scan, final_scan)
        if final_marker or final_scan.get("sensitive_data_detected") or final_scan.get("blocked"):
            workflow.fail_step(
                "final_output_scan",
                "Final serialized analysis failed the blocking security boundary.",
            )
            skip_workflow_steps_after(
                workflow,
                after_key="final_output_scan",
                message="Skipped because final output security scanning blocked the response.",
            )
            raise_security_blocked(
                workflow,
                context,
                status_code=502,
                message="The analysis result failed final security validation. Please try again.",
                error_code="OUTPUT_SECURITY_BLOCKED",
                error_stage="final_output_scan",
            )
        context.security_scan = normalized_security_scan(context.security_scan)
        context.security_status = security_status_from_scan(context.security_scan)
        result["security_scan"] = context.security_scan
        result["security_status"] = context.security_status
        workflow.complete_step(
            "final_output_scan",
            "Final serialized analysis passed output security scanning.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="final_output_scan",
            message="Final output security scanning failed.",
            error_code="FINAL_OUTPUT_SCAN_FAILED",
            exc=exc,
        )

    if save_to_history:
        workflow.start_step("save_application", "Save Application")
        if idempotency_claim is not None:
            result["workflow_id"] = context.workflow_id
            result["workflow_steps"] = workflow.to_list()
            workflow.complete_step(
                "save_application",
                "History and the idempotency result will be committed atomically.",
            )
        else:
            try:
                result["workflow_id"] = context.workflow_id
                result["workflow_steps"] = workflow.to_list()
                context.application_id = insert_application_record(
                    result,
                    job_url=context.job_url,
                    resume_filename=context.resume_filename,
                    owner_user_id=getattr(getattr(request.state, "v2_user", None), "id", None),
                )
                context.saved_to_history = True
                workflow.complete_step(
                    "save_application",
                    f"Application record saved with ID {context.application_id}.",
                )
                logger.info("Analysis saved to history application_id=%s", context.application_id)
            except Exception as exc:
                fail_analysis_and_raise(
                    workflow,
                    context,
                    step_key="save_application",
                    message="Could not save application record.",
                    error_code="ANALYZE_PERSISTENCE_FAILED",
                    exc=exc,
                    status_code=503,
                )
    else:
        workflow.skip_step(
            "save_application",
            "Save Application",
            "Save to history was disabled for this analysis.",
        )

    client_disconnected = client_disconnected or await _request_client_disconnected(request)
    history_finalized = (
        (not save_to_history)
        or context.application_id is not None
        or (idempotency_service is not None and idempotency_claim is not None)
    )
    idempotency_finalized = bool(
        idempotency_service is not None and idempotency_claim is not None
    )
    context.model_metadata = safe_model_metadata({
        **context.model_metadata,
        "history_finalized": history_finalized,
        "idempotency_finalized": idempotency_finalized,
        "client_disconnected": client_disconnected,
        "provider_phase_duration_ms": round(
            (provider_phase_completed_monotonic - provider_phase_started_monotonic) * 1000,
            3,
        ),
        "total_analyze_duration_ms": round(
            (time.monotonic() - analysis_started_monotonic) * 1000,
            3,
        ),
        "fallback_selected": analysis_status == "fallback",
        "result_state": analysis_status,
    })

    workflow.start_step("finalize_result", "Finalize Result")
    try:
        result["workflow_id"] = context.workflow_id
        result["workflow_status"] = workflow.status()
        result["application_id"] = context.application_id
        result["saved_to_history"] = context.saved_to_history
        result["next_action_decision"] = result.get("next_action_decision") or "pending"
        result["next_action"] = result.get("next_action") or {}
        result["rag_sources"] = result.get("rag_sources") or []
        result["security_scan"] = normalized_security_scan(
            result.get("security_scan") or context.security_scan
        )
        result["security_status"] = result.get("security_status") or context.security_status
        result["security_policy_version"] = SECURITY_POLICY_VERSION
        result["model_usage"] = {
            key: normalize_int(context.model_metadata.get(key))
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        result["model_completion"] = _public_model_completion(context.model_metadata)
        workflow.complete_step(
            "finalize_result",
            "Final API response prepared with workflow audit trail.",
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="finalize_result",
            message="Final API response preparation failed.",
            error_code="FINAL_RESULT_PREPARATION_FAILED",
            exc=exc,
        )

    workflow.finish()
    workflow_duration = workflow.workflow_duration()
    result["workflow_status"] = workflow.status()
    result["workflow_duration_ms"] = workflow_duration["workflow_duration_ms"]
    result["workflow_duration_us"] = workflow_duration["workflow_duration_us"]
    result["workflow_steps"] = workflow.to_list()

    if idempotency_service is not None and idempotency_claim is not None:
        current_user = getattr(request.state, "v2_user", None)
        try:
            if execution_binding is None:
                raise IdempotencyError(
                    "IDEMPOTENCY_PERSISTENCE_FAILED",
                    "The Analyze execution binding is unavailable.",
                )
            result, history_id = idempotency_service.finalize(
                idempotency_claim,
                result,
                execution_binding=execution_binding,
                save_to_history=save_to_history,
                user_id=current_user.id,
                job_url=context.job_url,
                resume_filename=context.resume_filename,
            )
        except IdempotencyError as exc:
            raise idempotency_http_exception(exc) from exc
        context.application_id = history_id
        context.saved_to_history = save_to_history
        request.state.analyze_idempotency_finalized = True
    elif context.application_id is not None:
        update_application_workflow_steps(
            context.application_id,
            workflow_steps=result["workflow_steps"],
            workflow_duration_ms=result["workflow_duration_ms"],
            workflow_duration_us=result["workflow_duration_us"],
        )

    logger.info(
        "Analyze timing complete total_analyze_duration_ms=%s provider_phase_duration_ms=%s deadline_exhausted=%s retry_started=%s repair_started=%s fallback_selected=%s history_finalized=%s idempotency_finalized=%s client_disconnected=%s result_state=%s",
        context.model_metadata.get("total_analyze_duration_ms"),
        context.model_metadata.get("provider_phase_duration_ms"),
        context.model_metadata.get("deadline_exhausted", False),
        context.model_metadata.get("retry_started", False),
        context.model_metadata.get("repair_started", False),
        context.model_metadata.get("fallback_selected", False),
        history_finalized,
        idempotency_finalized,
        client_disconnected,
        result.get("analysis_status") or analysis_status,
    )

    record_analysis_observation(
        workflow,
        context,
        outcome=workflow.status(),
        result=result,
    )

    return result
