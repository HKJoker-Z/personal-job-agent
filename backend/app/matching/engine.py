"""Pure deterministic matching engine. LLM output never enters numeric scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.matching.normalization import SYNONYM_MAP_VERSION, normalize_term, term_relation
from app.matching.schemas import DEFAULT_WEIGHTS, DIMENSIONS


SCORING_VERSION = "deterministic-v1"


@dataclass(frozen=True)
class Fact:
    source_type: str
    source_id: str | None
    value: str
    source_revision: int
    years: float | None = None


DIMENSION_CATEGORIES = {
    "required_skills": {"skill", "certification"},
    "experience": {"experience", "responsibility"},
    "projects": {"responsibility"},
    "education": {"education"},
    "location_and_authorization": {"location", "work_authorization"},
    "languages": {"language"},
    "seniority": {"experience"},
    "preferences": set(),
}


def _confirmed(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if item.get("verification_status") == "confirmed"]


def profile_facts(snapshot: dict[str, Any], revision: int) -> dict[str, list[Fact]]:
    facts: dict[str, list[Fact]] = {key: [] for key in DIMENSIONS}
    seen: set[tuple[str, str, str | None]] = set()

    def add(dimension: str, source: str, item: dict[str, Any], values: list[object], years: float | None = None) -> None:
        source_id = str(item.get("id")) if item.get("id") else None
        for raw in values:
            value = str(raw or "").strip()
            key = (dimension, normalize_term(value), source_id)
            if value and key not in seen:
                seen.add(key)
                facts[dimension].append(Fact(source, source_id, value, revision, years))

    for item in _confirmed(list(snapshot.get("skills") or [])):
        add("required_skills", "profile_skill", item, [item.get("name")], item.get("years_experience"))
    for item in _confirmed(list(snapshot.get("experiences") or [])):
        add("experience", "profile_experience", item, [item.get("role_title"), item.get("description")])
        add("required_skills", "profile_experience", item, list(item.get("skills") or []))
        add("seniority", "profile_experience", item, [item.get("role_title")])
    for item in _confirmed(list(snapshot.get("projects") or [])):
        add("projects", "profile_project", item, [item.get("name"), item.get("role"), item.get("description")])
        add("required_skills", "profile_project", item, list(item.get("technologies") or []))
    for item in _confirmed(list(snapshot.get("educations") or [])):
        add("education", "profile_education", item, [item.get("degree"), item.get("field_of_study"), item.get("institution")])
    for item in _confirmed(list(snapshot.get("languages") or [])):
        add("languages", "profile_language", item, [item.get("language"), f"{item.get('language', '')} {item.get('proficiency', '')}"])
    for item in _confirmed(list(snapshot.get("certifications") or [])):
        add("required_skills", "profile_certification", item, [item.get("name")])
    profile = dict(snapshot.get("profile") or {})
    add("location_and_authorization", "profile_preference", profile, [profile.get("current_location")])
    preference = dict(snapshot.get("preferences") or {})
    if preference:
        add("location_and_authorization", "profile_preference", preference, [preference.get("work_authorization"), *(preference.get("target_locations") or [])])
        add("preferences", "profile_preference", preference, [*(preference.get("target_roles") or []), *(preference.get("employment_types") or []), *(preference.get("work_modes") or [])])
    return facts


def _dimension_for(requirement: dict[str, Any], job: dict[str, Any]) -> str:
    category = str(requirement.get("category") or "other")
    if category == "skill" or category == "certification":
        return "required_skills"
    if category == "education":
        return "education"
    if category in {"location", "work_authorization"}:
        return "location_and_authorization"
    if category == "language":
        return "languages"
    if category == "experience":
        name = normalize_term(str(requirement.get("name") or ""))
        if any(word in name for word in ("senior", "junior", "lead", "principal", "staff")):
            return "seniority"
        return "experience"
    if category == "responsibility":
        return "projects"
    return "preferences"


def _best(required: str, candidates: list[Fact]) -> tuple[str, float, Fact | None]:
    values = [(term_relation(required, fact.value), fact) for fact in candidates]
    if not values:
        return "missing", 0.0, None
    (relation, contribution), fact = max(values, key=lambda item: item[0][1])
    return relation, contribution, fact


def _hard_result(requirement: dict[str, Any], relation: str, candidates: list[Fact], fact: Fact | None) -> str:
    if relation in {"exact", "synonym"}:
        minimum = requirement.get("minimum_years")
        if minimum is not None and fact is not None:
            if fact.years is None:
                return "unknown"
            return "passed" if fact.years >= float(minimum) else "failed"
        return "passed"
    if relation == "related":
        return "warning"
    # Absence is unknown. An explicit but contradictory fact is a failure for
    # mandatory identity-like requirements such as location/language/auth.
    category = requirement.get("category")
    if candidates and category in {"location", "work_authorization", "language", "certification"}:
        return "failed"
    return "unknown"


def score_match(
    profile_snapshot: dict[str, Any],
    profile_revision: int,
    job: dict[str, Any],
    requirements: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = dict(weights or DEFAULT_WEIGHTS)
    facts = profile_facts(profile_snapshot, profile_revision)
    dimension_rows: dict[str, list[tuple[float, str]]] = {key: [] for key in DIMENSIONS}
    evidence: list[dict[str, Any]] = []
    hard_statuses: list[str] = []

    for requirement in requirements:
        if requirement.get("verification_status") == "rejected":
            continue
        dimension = _dimension_for(requirement, job)
        required = str(requirement.get("name") or requirement.get("description") or "").strip()
        if requirement.get("verification_status") != "confirmed":
            evidence.append({
                "dimension": dimension, "requirement_id": requirement.get("id"),
                "source_type": "job_requirement", "source_id": None, "source_revision": None,
                "evidence_kind": "unknown", "evidence_summary": "Requirement awaits user confirmation.",
                "contribution": 0.0, "confidence": float(requirement.get("confidence") or 0.5),
                "verification_status": "needs_review",
            })
            continue
        relation, contribution, fact = _best(required, facts[dimension])
        minimum = requirement.get("minimum_years")
        if minimum is not None and fact and fact.years is not None and fact.years < float(minimum):
            contribution = min(contribution, max(0.0, fact.years / float(minimum)))
            relation = "related" if contribution else "missing"
        dimension_rows[dimension].append((contribution, relation))
        is_hard = requirement.get("requirement_type") == "hard_filter" or requirement.get("category") in {
            "work_authorization", "location", "language", "certification"
        } or (requirement.get("category") == "experience" and minimum is not None)
        hard = _hard_result(requirement, relation, facts[dimension], fact) if is_hard else None
        if hard:
            hard_statuses.append(hard)
        evidence.append({
            "dimension": dimension,
            "requirement_id": requirement.get("id"),
            "source_type": fact.source_type if fact else "job_requirement",
            "source_id": fact.source_id if fact else None,
            "source_revision": fact.source_revision if fact else None,
            "evidence_kind": "hard_filter" if is_hard else ({"exact": "matched", "synonym": "matched", "related": "partial"}.get(relation, "missing")),
            "evidence_summary": (
                f"{relation} evidence from {fact.source_type}." if fact
                else "No confirmed profile evidence; this is not treated as a confirmed negative."
            ),
            "contribution": round(contribution, 4),
            "confidence": 1.0,
            "verification_status": "confirmed",
            "hard_filter_result": hard,
        })

    # Preferences are deterministic comparisons against saved Job fields.
    preference_targets = [str(job.get(key) or "") for key in ("title", "location", "employment_type", "work_mode")]
    if facts["preferences"] and any(preference_targets):
        contributions = [_best(target, facts["preferences"])[1] for target in preference_targets if target]
        dimension_rows["preferences"].append((max(contributions or [0]), "preference"))

    dimensions: list[dict[str, Any]] = []
    for order, dimension in enumerate(DIMENSIONS):
        rows = dimension_rows[dimension]
        if rows:
            raw = sum(row[0] for row in rows) / len(rows)
            status = "matched" if raw >= 0.85 else "partial" if raw > 0 else "missing"
            explanation = f"{len(rows)} confirmed requirement(s) evaluated with deterministic evidence."
        else:
            raw = 0.5
            status = "unknown"
            explanation = "No confirmed requirement is available; unknown is not treated as unmet."
        weighted = raw * float(weights[dimension])
        dimensions.append({
            "dimension": dimension, "raw_score": round(raw, 4),
            "weighted_score": round(weighted, 4), "max_score": float(weights[dimension]),
            "explanation": explanation, "status": status, "sort_order": order,
        })

    overall = round(min(100.0, max(0.0, sum(item["weighted_score"] for item in dimensions))), 2)
    if "failed" in hard_statuses:
        hard_filter = "failed"
    elif "warning" in hard_statuses:
        hard_filter = "warning"
    elif "unknown" in hard_statuses or not hard_statuses:
        hard_filter = "unknown"
    else:
        hard_filter = "passed"
    if hard_filter == "failed":
        recommendation = "not_recommended"
    elif overall >= 80 and hard_filter == "passed":
        recommendation = "high_priority"
    elif overall >= 65:
        recommendation = "worth_applying"
    elif overall >= 45:
        recommendation = "apply_with_preparation"
    elif overall >= 25:
        recommendation = "low_priority"
    else:
        recommendation = "not_recommended"
    missing = sum(1 for item in evidence if item["evidence_kind"] in {"missing", "unknown"})
    preparation = "high" if missing >= 4 else "medium" if missing >= 2 else "low"
    return {
        "scoring_version": SCORING_VERSION,
        "synonym_map_version": SYNONYM_MAP_VERSION,
        "weight_config": weights,
        "overall_score": overall,
        "hard_filter_status": hard_filter,
        "recommendation": recommendation,
        "preparation_effort": preparation,
        "dimensions": dimensions,
        "evidence": evidence,
    }
