from __future__ import annotations

import re
from typing import Any


ALLOWED_NEXT_ACTIONS = {
    "apply_now": "Apply Now",
    "improve_resume_first": "Improve Resume First",
    "upskill_first": "Upskill First",
    "save_for_later": "Save for Later",
    "skip": "Skip This Role",
}

TECHNICAL_SIGNAL_TERMS = (
    "rag",
    "retrieval augmented generation",
    "llm",
    "generative ai",
    "agent",
    "agentic ai",
    "fastapi",
    "api",
    "rest api",
    "python",
    "react",
    "sqlite",
    "sql",
    "fts5",
    "deepseek",
    "openai",
    "prompt",
    "prompt engineering",
    "ats",
    "workflow automation",
    "system integration",
    "docker",
    "kubernetes",
    "langgraph",
    "mcp",
    "vector",
    "embedding",
    "retrieval",
    "monitoring",
    "evaluation",
    "security",
)

SOFT_SKILL_TERMS = (
    "communication",
    "teamwork",
    "collaboration",
    "stakeholder",
    "leadership",
    "ownership",
    "fast paced",
)


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(100, score))


def contains_term(text: str, term: str) -> bool:
    clean_text = normalize_text(text)
    clean_term = normalize_text(term)
    if not clean_text or not clean_term:
        return False
    return f" {clean_term} " in f" {clean_text} "


def dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = normalize_text(item)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def collect_evidence_text(analysis_result: dict[str, Any]) -> str:
    chunks = []
    for source in as_list_like_dicts(analysis_result.get("rag_sources")):
        chunks.append(str(source.get("content_preview") or ""))
        chunks.append(str(source.get("relevance_reason") or ""))
    chunks.extend(as_list(analysis_result.get("matched_skills")))
    chunks.extend(as_list(as_dict(analysis_result.get("ats_analysis")).get("matched_keywords")))
    return "\n".join(chunks)


def as_list_like_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def is_supported_by_evidence(skill: str, evidence_text: str) -> bool:
    if contains_term(evidence_text, skill):
        return True

    normalized_skill = normalize_text(skill)
    if "rag" in normalized_skill or "retrieval" in normalized_skill:
        return any(
            contains_term(evidence_text, term)
            for term in (
                "RAG",
                "Retrieval-Augmented Generation",
                "document chunking",
                "SQLite FTS5 retrieval",
                "top-k evidence injection",
            )
        )
    if "llm" in normalized_skill:
        return any(
            contains_term(evidence_text, term)
            for term in ("LLM applications", "DeepSeek API", "Generative AI")
        )
    return False


def is_technical_gap(skill: str, important_keywords: list[str]) -> bool:
    normalized_skill = normalize_text(skill)
    if not normalized_skill:
        return False
    if any(term in normalized_skill for term in SOFT_SKILL_TERMS):
        return False
    if any(contains_term(skill, keyword) or contains_term(keyword, skill) for keyword in important_keywords):
        return True
    return any(term in normalized_skill for term in TECHNICAL_SIGNAL_TERMS)


def identify_critical_missing_skills(analysis_result: dict[str, Any]) -> list[str]:
    ats_analysis = as_dict(analysis_result.get("ats_analysis"))
    missing_candidates = dedupe(
        as_list(analysis_result.get("missing_skills"))
        + as_list(ats_analysis.get("missing_keywords"))
    )
    important_keywords = as_list(ats_analysis.get("important_keywords"))
    evidence_text = collect_evidence_text(analysis_result)

    critical: list[str] = []
    for skill in missing_candidates:
        if is_supported_by_evidence(skill, evidence_text):
            continue
        if is_technical_gap(skill, important_keywords):
            critical.append(skill)
    return critical[:8]


def build_recommended_tasks(
    *,
    action: str,
    analysis_result: dict[str, Any],
    critical_missing_skills: list[str],
) -> list[str]:
    tasks: list[str] = []
    resume_suggestions = as_list(analysis_result.get("resume_suggestions"))

    if action == "apply_now":
        tasks.extend(
            [
                "Review the generated cover letter.",
                "Verify that the strongest matched project evidence is reflected in the resume.",
                "Submit the application.",
            ]
        )
    elif action == "improve_resume_first":
        tasks.append("Update the resume bullets to make the strongest matched skills easier to find.")
        tasks.extend(resume_suggestions[:2])
        if critical_missing_skills:
            tasks.append(f"Address the most important gap: {critical_missing_skills[0]}.")
        tasks.append("Re-run the analysis after editing the resume.")
    elif action == "upskill_first":
        if critical_missing_skills:
            tasks.append(f"Build or document proof for: {critical_missing_skills[0]}.")
        tasks.append("Save this role and target similar positions after closing the technical gap.")
        tasks.append("Use the missing keywords as a focused learning checklist.")
    elif action == "save_for_later":
        tasks.append("Save this role for later comparison.")
        tasks.append("Review missing skills before spending time on a tailored application.")
    else:
        tasks.append("Skip this role unless there is a strong external reason to apply.")
        tasks.append("Focus on roles with stronger overlap in core requirements.")

    return dedupe(tasks)[:5]


def generate_next_action(analysis_result: dict[str, Any]) -> dict[str, Any]:
    match_score = safe_score(analysis_result.get("match_score"))
    critical_missing_skills = identify_critical_missing_skills(analysis_result)
    critical_count = len(critical_missing_skills)

    if match_score >= 85 and critical_count == 0:
        action = "apply_now"
        priority = "high"
        confidence = 0.88
        reason = "The overall match score is high and no critical job requirement is missing."
    elif match_score >= 70 or (match_score >= 65 and critical_count <= 2):
        action = "improve_resume_first"
        priority = "high" if match_score >= 75 else "medium"
        confidence = 0.76 if critical_count <= 2 else 0.68
        reason = "The role is plausible, but the resume should be improved before applying."
    elif match_score >= 55:
        action = "upskill_first"
        priority = "medium"
        confidence = 0.66
        reason = "The role has meaningful overlap, but one or more real technical gaps should be addressed first."
    elif match_score >= 40:
        action = "save_for_later"
        priority = "low"
        confidence = 0.58
        reason = "The role has limited fit now, but it may be worth saving for later comparison."
    else:
        action = "skip"
        priority = "low"
        confidence = 0.72
        reason = "The match score is low or the core requirement gap is too large."

    tasks = build_recommended_tasks(
        action=action,
        analysis_result=analysis_result,
        critical_missing_skills=critical_missing_skills,
    )
    evidence = [
        f"Overall match score: {match_score}",
        f"Critical missing skills: {critical_count}",
    ]
    if critical_missing_skills:
        evidence.append(f"Critical gaps: {', '.join(critical_missing_skills[:5])}")
    if as_list_like_dicts(analysis_result.get("rag_sources")):
        evidence.append("Project Knowledge RAG evidence was available for the analysis.")

    return {
        "action": action,
        "label": ALLOWED_NEXT_ACTIONS[action],
        "priority": priority,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "reason": reason,
        "recommended_tasks": tasks,
        "evidence": evidence[:5],
        "critical_missing_skills": critical_missing_skills,
    }
