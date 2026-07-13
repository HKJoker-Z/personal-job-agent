"""Conservative, versioned skill normalization for deterministic matching."""

from __future__ import annotations

import re
import unicodedata


SYNONYM_MAP_VERSION = "skills-v1"

# Entries in a group are equivalent labels, not a hierarchy.
SYNONYM_GROUPS = (
    frozenset({"javascript", "js", "ecmascript"}),
    frozenset({"power bi", "powerbi"}),
    frozenset({"machine learning", "ml"}),
    frozenset({"postgresql", "postgres"}),
    frozenset({"kubernetes", "k8s"}),
    frozenset({"typescript", "ts"}),
)

# Related skills receive partial credit and are intentionally directional pairs.
RELATED_SKILLS = {
    frozenset({"postgresql", "sql"}),
    frozenset({"pandas", "python data analysis"}),
    frozenset({"python", "python data analysis"}),
    frozenset({"docker", "containerization"}),
    frozenset({"aws", "cloud computing"}),
    frozenset({"azure", "cloud computing"}),
    frozenset({"gcp", "cloud computing"}),
}


def normalize_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w+#.]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def canonical_term(value: str) -> str:
    normalized = normalize_term(value)
    for group in SYNONYM_GROUPS:
        if normalized in group:
            return sorted(group)[0]
    return normalized


def term_relation(required: str, candidate: str) -> tuple[str, float]:
    left = normalize_term(required)
    right = normalize_term(candidate)
    if not left or not right:
        return "missing", 0.0
    if left == right:
        return "exact", 1.0
    if canonical_term(left) == canonical_term(right):
        return "synonym", 0.9
    if frozenset({left, right}) in RELATED_SKILLS:
        return "related", 0.5
    # Multi-word evidence can contain a precise requirement, but broad one-token
    # overlap never upgrades an unrelated phrase to a full match.
    if len(left) >= 4 and re.search(rf"(?<!\w){re.escape(left)}(?!\w)", right):
        return "exact", 1.0
    if len(right) >= 4 and re.search(rf"(?<!\w){re.escape(right)}(?!\w)", left):
        return "related", 0.5
    return "missing", 0.0
