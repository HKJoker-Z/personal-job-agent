import json
import os
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pypdf import PdfReader


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
MAX_TEXT_CHARS = 18000

app = FastAPI(title="Personal Job Application Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://101.34.61.52:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        raise HTTPException(status_code=400, detail="Uploaded resume file is empty.")

    try:
        if filename.endswith(".pdf"):
            text = extract_pdf_text(file_bytes)
        elif filename.endswith(".docx"):
            text = extract_docx_text(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Resume must be a PDF or DOCX file.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {exc}") from exc

    if not text:
        raise HTTPException(status_code=400, detail="Could not extract text from the resume.")

    return text


def fetch_job_text_from_url(job_url: str) -> str:
    try:
        response = requests.get(
            job_url,
            timeout=12,
            headers={
                "User-Agent": "PersonalJobApplicationAgent/0.1 (+local MVP)",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch job URL: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        element.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    clean_text = "\n".join(lines)

    if not clean_text:
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
- 只输出合法 JSON，不要输出 markdown，不要输出解释文字。

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
{resume_text[:MAX_TEXT_CHARS]}

岗位 JD：
{job_description[:MAX_TEXT_CHARS]}
""".strip()


def normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_summary": str(data.get("job_summary", "")),
        "match_score": int(data.get("match_score", 0)),
        "match_reason": str(data.get("match_reason", "")),
        "matched_skills": list(data.get("matched_skills") or []),
        "missing_skills": list(data.get("missing_skills") or []),
        "resume_suggestions": list(data.get("resume_suggestions") or []),
        "cover_letter": str(data.get("cover_letter", "")),
    }


def analyze_with_deepseek(resume_text: str, job_description: str) -> dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="DEEPSEEK_API_KEY is not configured. Please add it to the project root .env file.",
        )

    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)

    try:
        completion = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You output strict JSON only. Do not include markdown or extra text.",
                },
                {"role": "user", "content": build_prompt(resume_text, job_description)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek API request failed: {exc}") from exc

    content = completion.choices[0].message.content or ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail="DeepSeek returned invalid JSON. Please try again.",
        ) from exc

    try:
        result = normalize_result(parsed)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek JSON shape is invalid: {exc}") from exc

    result["match_score"] = max(0, min(100, result["match_score"]))
    return result


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    resume: UploadFile = File(...),
    job_text: str | None = Form(None),
    job_url: str | None = Form(None),
) -> dict[str, Any]:
    resume_text = await extract_resume_text(resume)

    clean_job_text = (job_text or "").strip()
    clean_job_url = (job_url or "").strip()

    if clean_job_text:
        job_description = clean_job_text
    elif clean_job_url:
        job_description = fetch_job_text_from_url(clean_job_url)
    else:
        raise HTTPException(status_code=400, detail="Please provide either job_text or job_url.")

    return analyze_with_deepseek(resume_text, job_description)
