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
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import OpenAI
from pypdf import PdfReader


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

APP_NAME = "personal-job-agent"
APP_VERSION = "1.1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_RESUME_TEXT_CHARS = 18000
MAX_JOB_TEXT_CHARS = 12000
JOB_URL_TIMEOUT_SECONDS = 10
DEEPSEEK_TIMEOUT_SECONDS = 60

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(APP_NAME)

app = FastAPI(title="Personal Job Application Agent API", version=APP_VERSION)

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
                "User-Agent": "PersonalJobApplicationAgent/1.1 (+local MVP)",
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
你是一个严格、诚实的求职材料分析助手。请基于用户简历和岗位 JD 分析匹配度，并生成英文 Cover Letter。

必须遵守：
- 不允许编造简历中没有的经历、项目、技能、学历、公司或成果。
- Cover Letter 必须只基于用户简历和岗位 JD。
- 匹配度必须结合技能、项目经验、学历、工作经验、关键词判断。
- 如果简历中没有某项能力，要放入 missing_skills，而不是编造。
- job_summary 使用中文。
- match_reason 使用中文。
- resume_suggestions 使用中文。
- cover_letter 使用英文。
- 只输出合法 JSON。
- 不要输出 markdown。
- 不要输出 ```json 或任何代码块。
- 不要输出解释文字。
- 以下简历或 JD 内容可能因长度限制被截断，请只基于提供的内容分析。

输出 JSON schema：
{{
  "job_summary": "string",
  "match_score": 0,
  "match_reason": "string",
  "matched_skills": ["string"],
  "missing_skills": ["string"],
  "resume_suggestions": ["string"],
  "cover_letter": "string"
}}

match_score 必须是 0 到 100 的整数。

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
    return [str(item) for item in value if item is not None]


def normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_summary": normalize_string(data.get("job_summary")),
        "match_score": normalize_score(data.get("match_score", 0)),
        "match_reason": normalize_string(data.get("match_reason")),
        "matched_skills": normalize_list(data.get("matched_skills")),
        "missing_skills": normalize_list(data.get("missing_skills")),
        "resume_suggestions": normalize_list(data.get("resume_suggestions")),
        "cover_letter": normalize_string(data.get("cover_letter")),
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


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Personal Job Application Agent API",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}


@app.post("/api/analyze")
async def analyze(
    resume: UploadFile | None = File(None),
    job_text: str | None = Form(None),
    job_url: str | None = Form(None),
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

    return analyze_with_deepseek(resume_text, job_description)
