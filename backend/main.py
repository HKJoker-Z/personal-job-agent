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
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from pypdf import PdfReader

from database import (
    ALLOWED_APPLICATION_STATUSES,
    DB_PATH,
    delete_application_record,
    get_application_record,
    init_db,
    insert_application_record,
    list_application_records,
    update_application_record,
)
from export_utils import (
    build_analysis_report_pdf,
    build_cover_letter_docx,
    build_export_filename,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

APP_NAME = "personal-job-agent"
APP_VERSION = "1.4"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_RESUME_TEXT_CHARS = 18000
MAX_JOB_TEXT_CHARS = 12000
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

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title="Personal Job Application Agent API", version=APP_VERSION)
init_db()
logger.info("SQLite database initialized path=%s", DB_PATH)


class ApplicationUpdate(BaseModel):
    application_status: str | None = None
    notes: str | None = None

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
                "User-Agent": "PersonalJobApplicationAgent/1.4 (+local MVP)",
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


def build_prompt(resume_text: str, job_description: str) -> str:
    return f"""
你是一个严格、诚实、可解释的 Resume-JD Matching Agent。请基于用户简历和岗位 JD 分析匹配度、ATS 关键词覆盖，并生成英文 Cover Letter。

必须遵守：
- 不允许编造简历中没有的经历、项目、技能、学历、公司或成果。
- Cover Letter 必须只基于用户简历和岗位 JD。
- upgraded_resume_bullets 只能改写简历已有内容，original 必须来自简历原文或可直接对应的已有 bullet，不能新增不存在的经历。
- ATS keyword suggestions 只能建议用户在确实有真实经历的情况下加入相关关键词，不能建议用户编造技能或经历。
- scoring_breakdown 的 evidence 必须来自简历或 JD 中能支持判断的内容。
- 每个 scoring_breakdown 维度的 score 必须是 0 到 100 的整数。
- 匹配度必须结合技能、项目经验、学历、工作经验、关键词判断。
- 如果简历中没有某项能力，要放入 missing_skills，而不是编造。
- important_keywords 必须来自 JD。
- matched_keywords 是简历中已经覆盖的 JD 关键词。
- missing_keywords 是 JD 中重要但简历中缺失的关键词。
- job_summary、match_reason、resume_suggestions、keyword_suggestions、reason 使用中文。
- cover_letter 使用英文。
- company_name 使用 JD 中识别到的公司名；无法识别时使用 "Unknown Company"。
- job_title 使用 JD 中识别到的岗位名；无法识别时使用 "Unknown Position"。
- 只输出合法 JSON。
- 不要输出 markdown。
- 不要输出 ```json 或任何代码块。
- 不要输出解释文字。
- 以下简历或 JD 内容可能因长度限制被截断，请只基于提供的内容分析。
- 你返回的 match_score 仅作为参考，后端会用 scoring_breakdown 按固定权重重新计算最终 match_score。

输出 JSON schema：
{{
  "company_name": "string",
  "job_title": "string",
  "job_summary": "string",
  "match_score": 0,
  "match_reason": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "resume_suggestions": ["string"],
  "cover_letter": "string",
  "scoring_breakdown": {{
    "skills_match": {{
      "score": 0,
      "reason": "string",
      "evidence": ["string"]
    }},
    "project_experience": {{
      "score": 0,
      "reason": "string",
      "evidence": ["string"]
    }},
    "education": {{
      "score": 0,
      "reason": "string",
      "evidence": ["string"]
    }},
    "work_experience": {{
      "score": 0,
      "reason": "string",
      "evidence": ["string"]
    }},
    "keyword_match": {{
      "score": 0,
      "reason": "string",
      "evidence": ["string"]
    }}
  }},
  "ats_analysis": {{
    "important_keywords": ["string"],
    "matched_keywords": ["string"],
    "missing_keywords": ["string"],
    "keyword_suggestions": ["string"]
  }},
  "upgraded_resume_bullets": [
    {{
      "original": "string",
      "improved": "string",
      "reason": "string"
    }}
  ]
}}

match_score 必须是 0 到 100 的整数。
scoring_breakdown 权重参考：
- skills_match: 35%
- project_experience: 25%
- education: 15%
- work_experience: 15%
- keyword_match: 10%

用户简历：
{resume_text}

岗位 JD：
{job_description}
""".strip()


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


def normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


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


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    scoring_breakdown = normalize_scoring_breakdown(data.get("scoring_breakdown"))
    matched_skills = normalize_list(data.get("matched_skills"))
    missing_skills = normalize_list(data.get("missing_skills"))
    match_reason = normalize_string(data.get("match_reason")).strip()
    weighted_reason = build_match_reason_fallback(scoring_breakdown, matched_skills, missing_skills)
    if match_reason:
        match_reason = f"{match_reason}\n{weighted_reason}"
    else:
        match_reason = weighted_reason

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
        "ats_analysis": normalize_ats_analysis(data.get("ats_analysis")),
        "upgraded_resume_bullets": normalize_upgraded_resume_bullets(
            data.get("upgraded_resume_bullets")
        ),
    }


def analyze_with_deepseek(resume_text: str, job_description: str) -> dict[str, Any]:
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
                {"role": "user", "content": build_prompt(resume_text, job_description)},
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

    parsed = parse_ai_json_response(content)
    result = normalize_result(parsed)

    logger.info("DeepSeek call succeeded")
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
) -> dict[str, Any]:
    logger.info("Received analysis request")

    if resume is None:
        logger.warning("Analyze request rejected error_type=MissingResume")
        raise HTTPException(status_code=400, detail="Please upload a PDF or DOCX resume.")

    clean_job_text = (job_text or "").strip()
    clean_job_url = (job_url or "").strip()

    if not clean_job_text and not clean_job_url:
        logger.warning("Analyze request rejected error_type=MissingJobInput")
        raise HTTPException(
            status_code=400,
            detail="Please provide either job description text or a job URL.",
        )

    resume_text = await extract_resume_text(resume)
    logger.info("Resume parsing succeeded characters=%s", len(resume_text))

    if clean_job_text:
        job_description = clean_job_text
        logger.info("JD text received characters=%s", len(job_description))
    elif clean_job_url:
        job_description = fetch_job_text_from_url(clean_job_url)
        logger.info("JD fetch succeeded characters=%s", len(job_description))

    resume_text, resume_was_truncated = truncate_text(resume_text, MAX_RESUME_TEXT_CHARS)
    job_description, jd_was_truncated = truncate_text(job_description, MAX_JOB_TEXT_CHARS)

    if resume_was_truncated:
        logger.info("Resume text truncated characters=%s", MAX_RESUME_TEXT_CHARS)
    if jd_was_truncated:
        logger.info("JD text truncated characters=%s", MAX_JOB_TEXT_CHARS)

    result = analyze_with_deepseek(resume_text, job_description)
    application_id: int | None = None
    saved_to_history = False

    if save_to_history:
        application_id = insert_application_record(
            result,
            job_url=clean_job_url or None,
            resume_filename=resume.filename or None,
        )
        saved_to_history = True
        logger.info("Analysis saved to history application_id=%s", application_id)

    return {
        **result,
        "application_id": application_id,
        "saved_to_history": saved_to_history,
    }
