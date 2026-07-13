"""Explainable exact and near-duplicate Job detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID


TOKEN_RE = re.compile(r"[\w+#.-]+", re.UNICODE)


@dataclass(frozen=True)
class DuplicateAssessment:
    match_type: str
    score: float
    reasons: tuple[str, ...]


def canonical_pair(left: UUID, right: UUID) -> tuple[UUID, UUID]:
    if left == right:
        raise ValueError("A Job cannot be compared with itself.")
    return tuple(sorted((left, right), key=str))  # type: ignore[return-value]


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in TOKEN_RE.findall(value) if len(item) > 1}


def token_similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def assess_duplicate(left: object, right: object, threshold: float = 0.78) -> DuplicateAssessment | None:
    reasons: list[str] = []
    if getattr(left, "canonical_url", None) and getattr(left, "canonical_url") == getattr(right, "canonical_url", None):
        reasons.append("same_url")
    if getattr(left, "description_text_hash") == getattr(right, "description_text_hash"):
        reasons.append("same_description_hash")
    if getattr(left, "deduplication_key") == getattr(right, "deduplication_key"):
        reasons.append("same_deduplication_key")
    if reasons:
        return DuplicateAssessment("exact", 1.0, tuple(reasons))

    company = getattr(left, "normalized_company_name") == getattr(right, "normalized_company_name")
    title = getattr(left, "normalized_title") == getattr(right, "normalized_title")
    location = getattr(left, "normalized_location") == getattr(right, "normalized_location")
    if company:
        reasons.append("same_company")
    if title:
        reasons.append("same_title")
    if location:
        reasons.append("same_location")
    text_score = token_similarity(getattr(left, "description"), getattr(right, "description"))
    if text_score >= threshold:
        reasons.append("high_text_similarity")
    score = round(0.25 * company + 0.25 * title + 0.10 * location + 0.40 * text_score, 6)
    if company and title and score >= 0.62:
        return DuplicateAssessment("near", score, tuple(reasons))
    return None
