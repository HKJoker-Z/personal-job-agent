"""Independent claim validation against owned immutable evidence sources."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from app.matching.normalization import normalize_term
from security_utils import INTERNAL_SECURITY_MARKER, scan_untrusted_text


FACT_TERMS = {
    "python", "sql", "postgresql", "javascript", "typescript", "react", "fastapi",
    "docker", "kubernetes", "aws", "azure", "gcp", "pandas", "power bi",
    "machine learning", "lead", "led", "managed", "manager", "leadership",
    "certified", "certification", "degree", "bachelor", "master", "phd",
    "authorization", "authorized", "sponsorship", "salary", "compensation",
}
NUMBER_RE = re.compile(r"(?<!\w)(?:\d{1,4}(?:[.,]\d+)?%?)(?!\w)")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
NAMED_FACT_RE = re.compile(
    r"\b(?:at|for|with|as|in)\s+([A-Z][\w&+.-]+(?:\s+[A-Z][\w&+.-]+){0,5})"
)


@dataclass(frozen=True)
class EvidenceSource:
    source_type: str
    source_id: str | None
    source_revision: int | None
    text: str


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_term(value).split() if len(token) >= 3}


def _markers(claim: str) -> set[str]:
    normalized = normalize_term(claim)
    result = set(NUMBER_RE.findall(claim))
    result.update(term for term in FACT_TERMS if term in normalized)
    result.update(re.findall(r"\b(?:19|20)\d{2}\b", claim))
    result.update(match.group(1).strip(".,") for match in NAMED_FACT_RE.finditer(claim))
    return result


def validate_claims(content: str, sources: Iterable[EvidenceSource]) -> list[dict[str, object]]:
    source_values = list(sources)
    source_blob = "\n".join(source.text for source in source_values)
    output_scan = scan_untrusted_text(content, "llm_output")
    leaked_marker = INTERNAL_SECURITY_MARKER in content
    links: list[dict[str, object]] = []
    claims = [value.strip(" -*\t") for value in SENTENCE_RE.split(content) if value.strip(" -*\t")]
    for index, claim in enumerate(claims):
        markers = _markers(claim)
        if not markers:
            status = "not_applicable"
            source = None
            confidence = 1.0
        else:
            matched_markers = {marker for marker in markers if normalize_term(marker) in normalize_term(source_blob)}
            candidates = sorted(
                source_values,
                key=lambda item: len(_tokens(claim) & _tokens(item.text)),
                reverse=True,
            )
            source = candidates[0] if candidates and (_tokens(claim) & _tokens(candidates[0].text)) else None
            if leaked_marker or output_scan.get("sensitive_data_detected"):
                status, confidence = "unsupported", 1.0
            elif matched_markers == markers and source:
                status, confidence = "supported", 1.0
            elif matched_markers:
                status, confidence = "partially_supported", 0.5
            else:
                status, confidence = "unsupported", 1.0
        links.append({
            "claim_key": f"claim-{index + 1}",
            "claim_text_hash": hashlib.sha256(claim.encode()).hexdigest(),
            "source_type": source.source_type if source else "none",
            "source_id": source.source_id if source else None,
            "source_revision": source.source_revision if source else None,
            "evidence_summary": (
                f"Validated against {source.source_type} evidence." if source
                else "No supporting confirmed evidence was identified."
            ),
            "support_status": status,
            "confidence": confidence,
        })
    return links


def validation_summary(links: list[dict[str, object]]) -> tuple[str, int, float]:
    relevant = [item for item in links if item["support_status"] != "not_applicable"]
    # Partial support still leaves an ungrounded portion of a claim and therefore
    # blocks finalization until the user edits or explicitly confirms it.
    unsupported = sum(
        item["support_status"] in {"unsupported", "partially_supported"}
        for item in relevant
    )
    supported_units = sum(
        1 if item["support_status"] in {"supported", "user_confirmed"} else 0.5
        if item["support_status"] == "partially_supported" else 0
        for item in relevant
    )
    coverage = round((supported_units / len(relevant) * 100) if relevant else 100.0, 2)
    status = "valid" if unsupported == 0 else "invalid"
    return status, unsupported, coverage
