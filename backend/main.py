import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from pypdf import PdfReader

from agent_workflow import AgentWorkflow, WorkflowContext
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
from evaluation_service import (
    evaluation_status,
    get_evaluation_run,
    list_evaluation_runs,
    run_evaluation_suite,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

APP_NAME = "personal-job-agent"
APP_VERSION = "1.8.1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_RESUME_TEXT_CHARS = 18000
MAX_JOB_TEXT_CHARS = 12000
PROJECT_KNOWLEDGE_RELATIVE_PATH = Path("docs") / "PROJECT_KNOWLEDGE.md"
PROJECT_KNOWLEDGE_PATH = ROOT_DIR / PROJECT_KNOWLEDGE_RELATIVE_PATH
PROJECT_KNOWLEDGE_SOURCE_PATH = "docs/PROJECT_KNOWLEDGE.md"
PROJECT_KNOWLEDGE_TITLE = "Personal Job Application Agent Project Knowledge"
PROJECT_KNOWLEDGE_CATEGORY = "Other"
PROJECT_KNOWLEDGE_MAX_UPLOAD_BYTES = 2 * 1024 * 1024
GENERIC_KNOWLEDGE_DISABLED_DETAIL = (
    "Generic knowledge base upload is disabled in v1.8. "
    "Use Project Knowledge RAG instead."
)
MAX_RESUME_UPLOAD_BYTES = 8 * 1024 * 1024
JOB_URL_TIMEOUT_SECONDS = 10
DEEPSEEK_TIMEOUT_SECONDS = 60
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
}

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title="Personal Job Application Agent API", version=APP_VERSION)
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

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://101.34.61.52:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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
    logger.error(
        "Unhandled server error path=%s error_type=%s",
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Unexpected server error. Please try again."},
    )


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_docx_text(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs).strip()


async def extract_resume_text(resume: UploadFile) -> str:
    filename = (resume.filename or "").lower()
    file_bytes = await resume.read()

    if not file_bytes:
        logger.warning("Resume parsing failed error_type=EmptyUpload")
        raise HTTPException(status_code=400, detail="Uploaded resume file is empty.")
    if len(file_bytes) > MAX_RESUME_UPLOAD_BYTES:
        logger.warning("Resume parsing failed error_type=FileTooLarge")
        raise HTTPException(status_code=400, detail="Resume file is too large. Maximum size is 8 MB.")

    try:
        if filename.endswith(".pdf"):
            text = extract_pdf_text(file_bytes)
        elif filename.endswith(".docx"):
            text = extract_docx_text(file_bytes)
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

    if not text:
        logger.warning("Resume parsing failed error_type=NoExtractedText")
        raise HTTPException(status_code=400, detail="Could not extract text from the resume.")

    return text


def fetch_job_text_from_url(job_url: str) -> str:
    if not job_url.lower().startswith(("http://", "https://")):
        logger.warning("JD fetch failed error_type=InvalidUrlScheme")
        raise HTTPException(status_code=400, detail="Job URL must start with http:// or https://.")

    try:
        response = requests.get(
            job_url,
            timeout=JOB_URL_TIMEOUT_SECONDS,
            headers={
                "User-Agent": "PersonalJobApplicationAgent/1.6 (+local MVP)",
            },
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        logger.warning("JD fetch failed error_type=Timeout")
        raise HTTPException(
            status_code=400,
            detail="Job URL request timed out. Please paste the job description instead.",
        ) from exc
    except requests.RequestException as exc:
        logger.warning("JD fetch failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch job URL. Please check the URL or paste the job description.",
        ) from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)

    if not clean_text:
        logger.warning("JD fetch failed error_type=NoReadableText")
        raise HTTPException(status_code=400, detail="Could not extract readable text from job URL.")

    return clean_text


def parse_ai_json_response(raw_response: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start == -1 or end == -1 or end <= start:
            logger.warning("AI JSON parsing failed error_type=NoJsonObject")
            raise HTTPException(
                status_code=502,
                detail="AI response was not valid JSON. Please try again.",
            )

        try:
            parsed = json.loads(raw_response[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.warning("AI JSON parsing failed error_type=%s", type(exc).__name__)
            raise HTTPException(
                status_code=502,
                detail="AI response was not valid JSON. Please try again.",
            ) from exc

    if not isinstance(parsed, dict):
        logger.warning("AI JSON parsing failed error_type=NonObjectJson")
        raise HTTPException(
            status_code=502,
            detail="AI response was not valid JSON. Please try again.",
        )

    return parsed


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
    if not isinstance(value, list):
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
        if any(
            normalized_skill == term
            or normalized_skill in term
            or term in normalized_skill
            for term in normalized_group_terms
            if term
        ):
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
    return any(
        normalized_phrase_exists(variant, retrieved_chunks_text)
        for variant in skill_synonym_variants(skill)
    )


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


def rag_source_key(source: dict[str, Any]) -> tuple[str, str, int]:
    return (
        normalize_string(source.get("document_title")).strip().lower(),
        normalize_string(source.get("category")).strip().lower(),
        normalize_int(source.get("chunk_index")),
    )


def build_default_rag_sources(retrieved_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": normalize_int(chunk.get("chunk_id")),
            "document_id": normalize_int(chunk.get("document_id")),
            "document_title": normalize_string(chunk.get("document_title")),
            "category": normalize_string(chunk.get("category")),
            "chunk_index": normalize_int(chunk.get("chunk_index")),
            "content_preview": normalize_string(chunk.get("content"))[
                :RAG_CONTENT_PREVIEW_CHARS
            ],
            "relevance_reason": "该知识库片段与当前岗位描述中的技能、项目或公司信息相关。",
        }
        for chunk in retrieved_chunks
    ]


def normalize_rag_sources(
    value: Any,
    retrieved_chunks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    retrieved_chunks = retrieved_chunks or []
    default_sources = build_default_rag_sources(retrieved_chunks)
    if not isinstance(value, list):
        return default_sources

    default_by_key = {rag_source_key(source): source for source in default_sources}
    normalized_sources: list[dict[str, Any]] = []

    for item in value:
        if not isinstance(item, dict):
            continue

        source = {
            "document_title": normalize_string(item.get("document_title")).strip(),
            "category": normalize_string(item.get("category")).strip(),
            "chunk_index": normalize_int(item.get("chunk_index")),
            "relevance_reason": normalize_string(item.get("relevance_reason")).strip(),
        }
        matching_source = default_by_key.get(rag_source_key(source))
        if matching_source:
            merged_source = {
                **matching_source,
                "relevance_reason": source["relevance_reason"]
                or matching_source["relevance_reason"],
            }
            normalized_sources.append(merged_source)

    if normalized_sources:
        return normalized_sources
    return default_sources


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

    retrieved_chunks_text = "\n".join(
        normalize_string(chunk.get("content")) for chunk in retrieved_chunks
    )
    corrected_terms: list[str] = []
    remaining_missing_skills: list[str] = []

    for skill in missing_skills:
        if rag_evidence_contains_skill(skill, retrieved_chunks_text):
            append_unique_skill(matched_skills, skill)
            append_unique_skill(corrected_terms, skill)
        else:
            remaining_missing_skills.append(skill)
    missing_skills[:] = remaining_missing_skills

    matched_keywords = ats_analysis.setdefault("matched_keywords", [])
    missing_keywords = ats_analysis.setdefault("missing_keywords", [])
    remaining_missing_keywords: list[str] = []
    for keyword in missing_keywords:
        if rag_evidence_contains_skill(keyword, retrieved_chunks_text):
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

    match_reason = normalize_string(data.get("match_reason")).strip()
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
        "job_summary": normalize_string(data.get("job_summary")),
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
    return corrected_terms


def call_deepseek_raw(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]] | None = None,
    analysis_prompt: str | None = None,
) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DeepSeek configuration failed error_type=MissingApiKey")
        raise HTTPException(
            status_code=500,
            detail="DeepSeek API key is not configured on the backend.",
        )

    client = OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=DEEPSEEK_TIMEOUT_SECONDS,
    )

    try:
        logger.info("DeepSeek call started")
        completion = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Output valid JSON only. Do not include markdown, code fences, "
                        "or explanatory text."
                    ),
                },
                {
                    "role": "user",
                    "content": analysis_prompt
                    or build_safe_analysis_prompt(
                        resume_text=resume_text,
                        job_description=job_description,
                        rag_chunks=rag_chunks or [],
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except TimeoutError as exc:
        logger.warning("DeepSeek call failed error_type=Timeout")
        raise HTTPException(
            status_code=502,
            detail="DeepSeek API request timed out. Please try again.",
        ) from exc
    except Exception as exc:
        error_type = type(exc).__name__
        logger.warning("DeepSeek call failed error_type=%s", error_type)
        if "timeout" in error_type.lower():
            detail = "DeepSeek API request timed out. Please try again."
        else:
            detail = "DeepSeek API request failed. Please try again."
        raise HTTPException(status_code=502, detail=detail) from exc

    try:
        content = completion.choices[0].message.content or ""
    except (AttributeError, IndexError) as exc:
        logger.warning("DeepSeek call failed error_type=EmptyResponse")
        raise HTTPException(
            status_code=502,
            detail="DeepSeek API response was empty. Please try again.",
        ) from exc

    logger.info("DeepSeek call succeeded")
    return content


def analyze_with_deepseek(
    resume_text: str,
    job_description: str,
    rag_chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_prompt = build_safe_analysis_prompt(
        resume_text=resume_text,
        job_description=job_description,
        rag_chunks=rag_chunks or [],
    )
    content = call_deepseek_raw(
        resume_text,
        job_description,
        rag_chunks or [],
        analysis_prompt=safe_prompt,
    )
    parsed = parse_ai_json_response(content)
    result = normalize_result(parsed, retrieved_rag_chunks=rag_chunks or [])
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


def clamp_rag_top_k(value: int) -> int:
    return max(1, min(10, int(value)))


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


def attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def project_knowledge_status_data() -> dict[str, Any]:
    exists = PROJECT_KNOWLEDGE_PATH.is_file()
    document = find_project_knowledge_document(
        title=PROJECT_KNOWLEDGE_TITLE,
        source_filename=PROJECT_KNOWLEDGE_SOURCE_PATH,
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
    if not PROJECT_KNOWLEDGE_PATH.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Project Knowledge file not found at {PROJECT_KNOWLEDGE_SOURCE_PATH}.",
        )

    try:
        raw_text = PROJECT_KNOWLEDGE_PATH.read_text(encoding="utf-8")
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

    result = rebuild_project_knowledge_document(
        title=PROJECT_KNOWLEDGE_TITLE,
        category=PROJECT_KNOWLEDGE_CATEGORY,
        source_filename=PROJECT_KNOWLEDGE_SOURCE_PATH,
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
            detail="Project Knowledge file is too large. Maximum size is 2 MB.",
        )

    try:
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Project Knowledge file must be UTF-8 encoded.",
        ) from exc


def write_project_knowledge_file(content: str) -> None:
    PROJECT_KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = PROJECT_KNOWLEDGE_PATH.with_name(".PROJECT_KNOWLEDGE.md.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, PROJECT_KNOWLEDGE_PATH)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def raise_generic_knowledge_disabled() -> None:
    raise HTTPException(status_code=410, detail=GENERIC_KNOWLEDGE_DISABLED_DETAIL)


def resolve_rag_mode(use_knowledge_base: bool, rag_mode: str | None) -> str:
    if not use_knowledge_base:
        return "off"

    clean_mode = normalize_string(rag_mode).strip().lower()
    if not clean_mode:
        return "project"
    if clean_mode == "all":
        return "project"
    if clean_mode in {"project", "off"}:
        return clean_mode

    raise HTTPException(status_code=400, detail="rag_mode must be either 'project' or 'off'.")


REMAINING_WORKFLOW_STEPS = (
    ("scan_untrusted_input", "Scan Untrusted Input"),
    ("retrieve_project_evidence", "Retrieve Project Knowledge"),
    ("scan_project_evidence", "Scan Project Evidence"),
    ("build_safe_prompt", "Build Safe Prompt"),
    ("run_llm_analysis", "Run LLM Analysis"),
    ("scan_llm_output", "Scan LLM Output"),
    ("validate_structured_output", "Validate Structured Output"),
    ("reconcile_evidence", "Reconcile Evidence"),
    ("recommend_next_action", "Recommend Next Action"),
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


def raise_security_blocked(
    workflow: AgentWorkflow,
    context: WorkflowContext,
    *,
    status_code: int = 422,
    message: str = "Sensitive credential-like content was detected. Remove secrets before analysis.",
    error_code: str = "CREDENTIAL_LIKE_CONTENT_DETECTED",
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
) -> None:
    workflow.fail_step(step_key, message)
    record_analysis_observation(
        workflow,
        context,
        outcome="failed",
        error_code=error_code,
        error_stage=step_key,
    )
    if isinstance(exc, HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": message,
                "workflow_id": context.workflow_id,
                "error_code": error_code,
            },
        ) from exc
    raise exc


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Personal Job Application Agent API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}


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
            detail="Live LLM evaluation is not supported in Version 1.8.",
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
    return {"items": items}


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


@app.get("/api/applications")
def get_applications(
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    clean_status = validate_application_status(status, required=False)
    clean_search = (search or "").strip() or None
    items, total = list_application_records(
        status=clean_status,
        search=clean_search,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/api/applications/{application_id}")
def get_application(application_id: int) -> dict[str, Any]:
    return get_existing_application_record(application_id)


@app.get("/api/applications/{application_id}/cover-letter.docx")
def export_cover_letter_docx(application_id: int) -> StreamingResponse:
    record = get_existing_application_record(application_id)
    buffer = build_cover_letter_docx(record)
    filename = build_export_filename("cover-letter", record, "docx")
    logger.info("Cover letter export generated application_id=%s", application_id)
    return StreamingResponse(
        buffer,
        media_type=DOCX_MEDIA_TYPE,
        headers=attachment_headers(filename),
    )


@app.head("/api/applications/{application_id}/cover-letter.docx")
def head_cover_letter_docx(application_id: int) -> Response:
    record = get_existing_application_record(application_id)
    filename = build_export_filename("cover-letter", record, "docx")
    return Response(media_type=DOCX_MEDIA_TYPE, headers=attachment_headers(filename))


@app.get("/api/applications/{application_id}/report.pdf")
def export_analysis_report_pdf(application_id: int) -> StreamingResponse:
    record = get_existing_application_record(application_id)
    buffer = build_analysis_report_pdf(record)
    filename = build_export_filename("analysis-report", record, "pdf")
    logger.info("Analysis report export generated application_id=%s", application_id)
    return StreamingResponse(
        buffer,
        media_type=PDF_MEDIA_TYPE,
        headers=attachment_headers(filename),
    )


@app.head("/api/applications/{application_id}/report.pdf")
def head_analysis_report_pdf(application_id: int) -> Response:
    record = get_existing_application_record(application_id)
    filename = build_export_filename("analysis-report", record, "pdf")
    return Response(media_type=PDF_MEDIA_TYPE, headers=attachment_headers(filename))


@app.patch("/api/applications/{application_id}")
def patch_application(application_id: int, payload: ApplicationUpdate) -> dict[str, Any]:
    clean_status = validate_application_status(payload.application_status, required=True)
    notes_provided = field_was_provided(payload, "notes")
    updated_record = update_application_record(
        application_id,
        application_status=clean_status,
        notes=payload.notes,
        update_notes=notes_provided,
    )

    if updated_record is None:
        raise HTTPException(status_code=404, detail="Application record not found.")

    return updated_record


@app.patch("/api/applications/{application_id}/next-action")
def patch_next_action_decision(
    application_id: int,
    payload: NextActionDecisionUpdate,
) -> dict[str, Any]:
    decision = validate_next_action_decision(payload.decision)
    updated_record = update_next_action_decision(
        application_id,
        decision=decision,
        notes=payload.notes,
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


@app.delete("/api/applications/{application_id}")
def delete_application(application_id: int) -> dict[str, Any]:
    deleted = delete_application_record(application_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application record not found.")
    return {"deleted": True, "id": application_id}


@app.post("/api/analyze")
async def analyze(
    resume: UploadFile | None = File(None),
    job_text: str | None = Form(None),
    job_url: str | None = Form(None),
    save_to_history: bool = Form(True),
    use_knowledge_base: bool = Form(True),
    rag_top_k: int = Form(5),
    rag_mode: str | None = Form(None),
) -> dict[str, Any]:
    logger.info("Received analysis request")
    workflow = AgentWorkflow()
    context = WorkflowContext(workflow_id=workflow.workflow_id)

    workflow.start_step("validate_input", "Validate Input")
    try:
        if resume is None:
            logger.warning("Analyze request rejected error_type=MissingResume")
            raise HTTPException(status_code=400, detail="Please upload a PDF or DOCX resume.")

        resume_filename = resume.filename or ""
        clean_resume_filename = resume_filename.lower()
        if not clean_resume_filename.endswith((".pdf", ".docx")):
            logger.warning("Analyze request rejected error_type=UnsupportedResumeType")
            raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file.")

        upload_size = getattr(resume, "size", None)
        if isinstance(upload_size, int) and upload_size > MAX_RESUME_UPLOAD_BYTES:
            logger.warning("Analyze request rejected error_type=ResumeTooLarge")
            raise HTTPException(
                status_code=400,
                detail="Resume file is too large. Maximum size is 8 MB.",
            )

        clean_job_text = (job_text or "").strip()
        clean_job_url = (job_url or "").strip()
        if not clean_job_text and not clean_job_url:
            logger.warning("Analyze request rejected error_type=MissingJobInput")
            raise HTTPException(
                status_code=400,
                detail="Please provide either job description text or a job URL.",
            )

        context.resume_filename = resume_filename or None
        context.job_url = clean_job_url or None
        context.source_type = "text" if clean_job_text else "url"
        context.rag_mode = resolve_rag_mode(use_knowledge_base, rag_mode)
        context.rag_top_k = clamp_rag_top_k(rag_top_k)
        workflow.complete_step(
            "validate_input",
            f"Input accepted. RAG mode: {context.rag_mode}; top_k: {context.rag_top_k}.",
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="validate_input",
            message="Input validation failed.",
            error_code="INPUT_VALIDATION_FAILED",
            exc=exc,
        )

    workflow.start_step("parse_resume", "Parse Resume")
    try:
        resume_text = await extract_resume_text(resume)
        resume_text, resume_was_truncated = truncate_text(resume_text, MAX_RESUME_TEXT_CHARS)
        context.resume_text = resume_text
        logger.info("Resume parsing succeeded characters=%s", len(resume_text))
        if resume_was_truncated:
            logger.info("Resume text truncated characters=%s", MAX_RESUME_TEXT_CHARS)
        workflow.complete_step(
            "parse_resume",
            f"Resume text extracted successfully from {context.resume_filename or 'uploaded file'}.",
        )
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="parse_resume",
            message="Resume parsing failed.",
            error_code="RESUME_PARSING_FAILED",
            exc=exc,
        )

    workflow.start_step("acquire_job_description", "Acquire Job Description")
    try:
        if clean_job_text:
            job_description = clean_job_text
            source_message = "Used pasted job description text."
            logger.info("JD text received characters=%s", len(job_description))
        else:
            job_description = fetch_job_text_from_url(clean_job_url)
            source_message = "Fetched job description from the provided URL."
            logger.info("JD fetch succeeded characters=%s", len(job_description))

        job_description, jd_was_truncated = truncate_text(job_description, MAX_JOB_TEXT_CHARS)
        context.job_text = job_description
        if jd_was_truncated:
            logger.info("JD text truncated characters=%s", MAX_JOB_TEXT_CHARS)
        workflow.complete_step("acquire_job_description", source_message)
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="acquire_job_description",
            message="Could not acquire job description.",
            error_code="JOB_DESCRIPTION_ACQUISITION_FAILED",
            exc=exc,
        )

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

    logger.info(
        "Analyze RAG settings rag_mode=%s use_knowledge_base=%s rag_top_k=%s",
        context.rag_mode,
        use_knowledge_base,
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
                    error_code="PROJECT_KNOWLEDGE_CREDENTIAL_LIKE_CONTENT_DETECTED",
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
    try:
        context.llm_raw_response = call_deepseek_raw(
            context.sanitized_resume_text,
            context.sanitized_job_text,
            context.retrieved_chunks,
            analysis_prompt=context.safe_prompt,
        )
        workflow.complete_step("run_llm_analysis", "DeepSeek returned a JSON response.")
    except Exception as exc:
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="run_llm_analysis",
            message="LLM analysis failed.",
            error_code="LLM_ANALYSIS_FAILED",
            exc=exc,
        )

    workflow.start_step("scan_llm_output", "Scan LLM Output")
    try:
        sanitized_output, output_scan, marker_leaked = scan_llm_output(context.llm_raw_response)
        context.security_scan = merge_security_scans(context.security_scan, output_scan)
        if output_scan.get("findings"):
            workflow.add_warning()
        if marker_leaked:
            workflow.fail_step(
                "scan_llm_output",
                "LLM output security scanning detected internal instruction leakage.",
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
                error_code="LLM_OUTPUT_SECURITY_VALIDATION_FAILED",
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

    workflow.start_step("validate_structured_output", "Validate Structured Output")
    try:
        parsed = parse_ai_json_response(context.llm_raw_response)
        result = normalize_result(
            parsed,
            retrieved_rag_chunks=context.retrieved_chunks,
            apply_rag_corrections=False,
        )
        context.json_parse_success = True
        workflow.complete_step(
            "validate_structured_output",
            "LLM JSON parsed and normalized successfully.",
        )
    except Exception as exc:
        context.json_parse_success = False
        fail_analysis_and_raise(
            workflow,
            context,
            step_key="validate_structured_output",
            message="Structured output validation failed.",
            error_code="STRUCTURED_OUTPUT_VALIDATION_FAILED",
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
        if not result["used_knowledge_base"]:
            result["rag_sources"] = []
        if context.security_filtered_rag_sources:
            result["rag_sources"] = [
                *(result.get("rag_sources") or []),
                *context.security_filtered_rag_sources,
            ]
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

    if save_to_history:
        workflow.start_step("save_application", "Save Application")
        try:
            result["workflow_id"] = context.workflow_id
            result["workflow_steps"] = workflow.to_list()
            context.application_id = insert_application_record(
                result,
                job_url=context.job_url,
                resume_filename=context.resume_filename,
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
                error_code="APPLICATION_SAVE_FAILED",
                exc=exc,
            )
    else:
        workflow.skip_step(
            "save_application",
            "Save Application",
            "Save to history was disabled for this analysis.",
        )

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

    if context.application_id is not None:
        update_application_workflow_steps(
            context.application_id,
            workflow_steps=result["workflow_steps"],
            workflow_duration_ms=result["workflow_duration_ms"],
            workflow_duration_us=result["workflow_duration_us"],
        )

    record_analysis_observation(
        workflow,
        context,
        outcome=workflow.status(),
        result=result,
    )

    return result
