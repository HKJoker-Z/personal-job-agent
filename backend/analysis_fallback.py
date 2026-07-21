"""Deterministic input preparation, local matching, and scoring fallbacks."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


SECTION_PRIORITY = (
    "skills", "technical skills", "core competencies", "requirements", "qualifications",
    "work experience", "professional experience", "experience", "projects", "project experience",
    "education", "certifications", "responsibilities", "preferred qualifications",
)

SKILLS = (
    "Python", "Java", "JavaScript", "TypeScript", "React", "Vue", "Angular", "Node.js",
    "FastAPI", "Django", "Flask", "REST", "GraphQL", "SQL", "PostgreSQL", "MySQL",
    "SQLite", "MongoDB", "Redis", "Elasticsearch", "Docker", "Docker Compose", "Kubernetes",
    "AWS", "Azure", "GCP", "Linux", "Git", "GitHub Actions", "CI/CD", "Terraform",
    "Ansible", "Kafka", "RabbitMQ", "Dramatiq", "Celery", "RAG", "LLM", "DeepSeek",
    "OpenAI", "Machine Learning", "Data Analysis", "Pandas", "NumPy", "PyTorch", "TensorFlow",
    "SSE", "WebSocket", "HTML", "CSS", "Agile", "Scrum",
)

ALIASES = {
    "Node.js": ("node.js", "nodejs"),
    "PostgreSQL": ("postgresql", "postgres"),
    "Docker Compose": ("docker compose", "docker-compose"),
    "GitHub Actions": ("github actions",),
    "CI/CD": ("ci/cd", "continuous integration", "continuous delivery"),
    "RAG": ("rag", "retrieval augmented generation", "retrieval-augmented generation"),
    "LLM": ("llm", "large language model"),
    "SSE": ("sse", "server-sent events"),
    "REST": ("rest api", "restful"),
}


def normalize_analysis_text(value: str) -> str:
    text = str(value or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"</?[a-zA-Z][^>]*>", text):
        text = BeautifulSoup(text, "html.parser").get_text("\n")
    lines: list[str] = []
    blank = False
    for raw in text.splitlines():
        line = raw.replace("\t", " ")
        line = re.sub(r" {2,}", " ", line).strip()
        if not line:
            if lines and not blank:
                lines.append("")
            blank = True
            continue
        blank = False
        lines.append(line)
    return "\n".join(lines).strip()


def _heading(line: str) -> str | None:
    clean = line.lstrip("#").strip().rstrip(":").casefold()
    if not clean or len(clean) > 80:
        return None
    if clean in SECTION_PRIORITY:
        return clean
    if line.startswith("#") or (line.isupper() and len(line.split()) <= 8):
        return clean
    return None


def structure_aware_truncate(value: str, maximum: int) -> tuple[str, bool]:
    text = normalize_analysis_text(value)
    if len(text) <= maximum:
        return text, False
    sections: list[tuple[str, list[str], int]] = []
    current_name = "introduction"
    current: list[str] = []
    for index, line in enumerate(text.splitlines()):
        heading = _heading(line)
        if heading and current:
            sections.append((current_name, current, len(sections)))
            current = []
        if heading:
            current_name = heading
        current.append(line)
    if current:
        sections.append((current_name, current, len(sections)))

    def priority(section: tuple[str, list[str], int]) -> tuple[int, int]:
        name, _lines, position = section
        try:
            return SECTION_PRIORITY.index(name), position
        except ValueError:
            return len(SECTION_PRIORITY) + (0 if name == "introduction" else 1), position

    selected: list[tuple[int, str]] = []
    used = 0
    marker = "\n\n[Input safely shortened by section]\n\n"
    budget = max(maximum - len(marker), 1)
    for name, lines, position in sorted(sections, key=priority):
        block = "\n".join(lines).strip()
        if not block:
            continue
        remaining = budget - used
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining].rsplit("\n", 1)[0] or block[:remaining]
        selected.append((position, block))
        used += len(block) + 2
    result = marker.strip() + "\n\n" + "\n\n".join(block for _position, block in sorted(selected))
    return result[:maximum].strip(), True


def _contains(text: str, skill: str) -> bool:
    clean = text.casefold()
    variants = ALIASES.get(skill, (skill.casefold(),))
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term.casefold())}(?![a-z0-9])", clean) for term in variants)


def keyword_skill_states(resume_text: str, job_description: str) -> tuple[list[str], list[str]]:
    requested = [skill for skill in SKILLS if _contains(job_description, skill)]
    matched = [skill for skill in requested if _contains(resume_text, skill)]
    missing = [skill for skill in requested if skill not in matched]
    return matched[:12], missing[:12]


def deterministic_scoring(
    result: dict[str, Any], resume_text: str, job_description: str, retrieved_chunks: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    matched = list(result.get("matched_skills") or [])
    missing = list(result.get("missing_skills") or [])
    unknown = list(result.get("unknown_skills") or [])
    requested_total = len(matched) + len(missing) + len(unknown)
    ratio = len(matched) / requested_total if requested_total else 0.0
    resume_lower = resume_text.casefold()
    job_lower = job_description.casefold()
    project_present = any(term in resume_lower for term in ("project", "implemented", "built", "developed"))
    work_present = any(term in resume_lower for term in ("experience", "employment", "engineer", "developer"))
    education_required = any(term in job_lower for term in ("degree", "bachelor", "master", "education"))
    education_present = any(term in resume_lower for term in ("degree", "bachelor", "master", "university", "college"))
    project_score = round(min(100, ratio * 75 + (20 if project_present else 0) + (5 if retrieved_chunks else 0)))
    work_score = round(min(100, ratio * 75 + (25 if work_present else 0)))
    education_score = 0 if not education_required else (100 if education_present else 0)
    keyword_score = round(ratio * 100)
    previous = result.get("scoring_breakdown") if isinstance(result.get("scoring_breakdown"), dict) else {}

    def dimension(key: str, score: int, fallback_reason: str, evidence: list[str]) -> dict[str, Any]:
        current = previous.get(key) if isinstance(previous.get(key), dict) else {}
        current_reason = str(current.get("reason") or "").strip()
        reason = (
            fallback_reason
            if not current_reason or current_reason == "No validated evidence supports this dimension."
            else current_reason
        )[:240]
        return {"score": max(0, min(100, int(score))), "reason": reason, "evidence": evidence[:5]}

    matched_evidence = ["resume"] if matched else []
    return {
        "skills_match": dimension("skills_match", keyword_score, "Deterministic skill overlap between the resume and job requirements.", matched_evidence),
        "project_experience": dimension("project_experience", project_score, "Deterministic project-evidence coverage.", matched_evidence),
        "education": dimension(
            "education",
            education_score,
            "No education requirement was scored." if not education_required else "Deterministic education-requirement coverage.",
            ["resume"] if education_required and education_present else [],
        ),
        "work_experience": dimension("work_experience", work_score, "Deterministic work-experience coverage.", matched_evidence),
        "keyword_match": dimension("keyword_match", keyword_score, "Deterministic keyword overlap.", matched_evidence),
    }


def local_fallback_result(
    resume_text: str, job_description: str, retrieved_chunks: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    chunks = list(retrieved_chunks or [])
    matched, missing = keyword_skill_states(resume_text, job_description)
    if not matched and not missing:
        # A result remains useful even when the curated technical vocabulary is absent.
        missing = ["No explicit technical skill requirements were detected"]
    recommendations = []
    if missing:
        recommendations.append("Add verified evidence for the most important missing requirements.")
    if matched:
        recommendations.append("Keep matched skills near measurable experience or project evidence.")
    if not recommendations:
        recommendations.append("Tailor the summary and experience bullets to the job requirements.")
    result: dict[str, Any] = {
        "matched_skills": matched,
        "missing_skills": missing,
        "unknown_skills": [],
        "resume_suggestions": recommendations,
        "recommendations": recommendations,
        "cover_letter": "",
        "upgraded_resume_bullets": [],
        "ats_analysis": {
            "important_keywords": [*matched, *missing],
            "matched_keywords": matched,
            "missing_keywords": missing,
            "keyword_suggestions": recommendations,
        },
        "evidence_mapping": [
            {"skill": skill, "source": "resume", "evidence": []} for skill in matched
        ],
    }
    result["scoring_breakdown"] = deterministic_scoring(result, resume_text, job_description, chunks)
    return result
