"""Tolerant, bounded contract handling for resume analysis model output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, model_validator


MODEL_OUTPUT_TRUNCATED = "MODEL_OUTPUT_TRUNCATED"
MODEL_OUTPUT_INVALID_JSON = "MODEL_OUTPUT_INVALID_JSON"
MODEL_OUTPUT_SCHEMA_INVALID = "MODEL_OUTPUT_SCHEMA_INVALID"
MODEL_OUTPUT_EMPTY = "MODEL_OUTPUT_EMPTY"
MODEL_OUTPUT_RESOURCE_LIMIT = "MODEL_OUTPUT_RESOURCE_LIMIT"
MODEL_OUTPUT_TOO_LARGE = "MODEL_OUTPUT_TOO_LARGE"
MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"

MODEL_ERROR_MESSAGES = {
    MODEL_OUTPUT_TRUNCATED: "The model response reached its output limit before completion.",
    MODEL_OUTPUT_INVALID_JSON: "The model returned an incomplete or invalid structured response.",
    MODEL_OUTPUT_SCHEMA_INVALID: "The model response did not contain a usable analysis.",
    MODEL_OUTPUT_EMPTY: "The model returned an empty response.",
    MODEL_OUTPUT_RESOURCE_LIMIT: "The model provider stopped before a usable response was available.",
    MODEL_OUTPUT_TOO_LARGE: "The model response exceeded the safe structured-output limit.",
    MODEL_PROVIDER_ERROR: "The model provider request failed safely.",
}

TRUNCATED_FINISH_REASONS = {"length", "max_tokens", "max_output_tokens", "token_limit"}
RESOURCE_FINISH_REASONS = {"insufficient_system_resource", "resource_exhausted"}
TRAILING_COMMA = re.compile(r",\s*([}\]])")
MAX_PROVIDER_CONTENT_CHARS = 32_000
MAX_PROVIDER_METADATA_TOKENS = 1_000_000
MAX_PROVIDER_METADATA_LATENCY_MS = 300_000
SAFE_RETRY_REASONS = {
    "connect_timeout",
    "read_timeout",
    "write_timeout",
    "pool_timeout",
    "http_429",
    "http_5xx",
    "resource_limit",
    "empty_content",
    "finish_length",
}
SAFE_PARSE_OUTCOMES = {"canonical", "local_format_repair", "format_repair_call", "invalid", "empty"}
SAFE_RESULT_STATES = {"complete", "repaired", "partial", "fallback"}
SAFE_TIMEOUT_CATEGORIES = {
    "connect_timeout",
    "read_timeout",
    "write_timeout",
    "pool_timeout",
}
SAFE_DEADLINE_BUCKETS = {"gt_60s", "31_60s", "11_30s", "1_10s", "exhausted"}

# The active Provider contract is deliberately shallow.  The fields below are
# the only fields the prompt asks DeepSeek to generate.  The older compact
# skill/dimension/evidence fields remain accepted as bounded compatibility
# input for already-created fixtures and operator experiments, but they are
# not authoritative in the active Analyze path.
PROVIDER_FIELD_ALIASES = {
    "job_summary": ("jobSummary", "summary"),
    "match_reasons": ("matchReasons", "reasons", "match_reason", "matchReason"),
    "recommendations": ("suggestions", "next_steps", "nextSteps"),
    "resume_improvements": ("resumeImprovements", "resume_suggestions", "improvements"),
}
PROVIDER_CANONICAL_FIELDS = tuple(PROVIDER_FIELD_ALIASES)

OPTIONAL_PROVIDER_NARRATIVE_FIELDS = ("job_summary", "match_reason")
REQUIRED_ANALYSIS_FIELDS = (
    "matched_skills",
    "missing_skills",
    "unknown_skills",
    "concise_recommendations",
)
TOP_LEVEL_FIELD_ALIASES = {
    "matched_skills": ("matchedSkills", "matches"),
    "missing_skills": ("missingSkills", "gaps"),
    "unknown_skills": ("unknownSkills", "unknowns"),
    "concise_dimension_assessments": (
        "dimension_assessments", "dimensionAssessments", "assessments", "dimensions"
    ),
    "evidence_references": ("evidenceReferences", "evidence_mapping", "evidenceMapping"),
    "unsupported_claim_candidates": (
        "unsupportedCandidates", "unsupported_claims"
    ),
    "concise_recommendations": (
        "recommendations", "suggestions", "next_steps", "nextSteps"
    ),
}
CANONICAL_ANALYSIS_FIELDS = tuple(TOP_LEVEL_FIELD_ALIASES)

DIMENSION_FIELD_ALIASES = {
    "skills_match": ("skillsMatch", "skills"),
    "project_experience": ("projectExperience", "projects"),
    "education": (),
    "work_experience": ("workExperience", "experience"),
    "keyword_match": ("keywordMatch", "keywords"),
}
DIMENSION_VALUE_ALIASES = {
    "score": ("rating", "percentage"),
    "assessment": ("summary", "reason", "comment"),
    "evidence_ids": ("evidenceIds", "evidence", "references"),
}
EVIDENCE_REFERENCE_ALIASES = {
    "skill": ("name", "requirement"),
    "evidence_ids": ("evidenceIds", "evidence", "references"),
}

SALVAGE_WARNING_MESSAGES = {
    "missing_required_field_defaulted": "A missing required model field was filled with a safe default.",
    "missing_optional_field_defaulted": "A missing optional model field was filled with a safe default.",
    "null_field_defaulted": "A null model field was replaced with a safe default.",
    "field_alias_normalized": "An equivalent model field alias was normalized.",
    "scalar_to_list": "A scalar string was normalized to a single-item list.",
    "numeric_string_normalized": "A numeric string was normalized to a bounded number.",
    "score_clamped": "An out-of-range score was clamped to the supported range.",
    "invalid_field_defaulted": "An invalid field was replaced with a safe default.",
    "invalid_list_item_removed": "An invalid list item was removed while valid items were preserved.",
    "list_truncated": "A list was bounded to the supported item limit.",
    "unknown_top_level_field_ignored": "An unknown top-level field was ignored safely.",
    "unknown_nested_field_ignored": "An unknown nested field was ignored safely.",
    "evidence_mapping_normalized": "A supported evidence mapping shape was normalized.",
}


class ModelOutputError(RuntimeError):
    """A classified provider or model-output failure with safe metadata only."""

    def __init__(self, error_code: str, *, metadata: dict[str, Any] | None = None) -> None:
        self.error_code = error_code
        self.safe_message = MODEL_ERROR_MESSAGES[error_code]
        self.metadata = safe_model_metadata(metadata) if metadata is not None else {}
        super().__init__(self.safe_message)


@dataclass(frozen=True)
class ProviderAnalysisResponse:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedModelJson:
    data: dict[str, Any]
    normalized: bool = False
    warnings: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SalvagedCompactAnalysis:
    """Deterministic field-level normalization before Pydantic validation.

    The minimum safe acceptance contract is deliberately semantic rather than a
    field count: at least one bounded narrative or legacy judgment must survive
    normalization. Backend-owned scoring, evidence reconciliation, Job Summary,
    and Match Reasons are then completed or derived from validated local data.
    """

    data: dict[str, Any]
    action_codes: tuple[str, ...] = ()
    rejected_field_count: int = 0
    accepted_field_count: int = 0


ConciseSkill = Annotated[str, Field(max_length=80)]
ConciseAssessment = Annotated[str, Field(max_length=240)]
ConciseRecommendation = Annotated[str, Field(max_length=180)]
ConciseClaim = Annotated[str, Field(max_length=240)]
EvidenceId = Annotated[str, Field(max_length=80)]


SKILL_CASE = {
    "api": "API", "aws": "AWS", "ci/cd": "CI/CD", "css": "CSS", "docker": "Docker",
    "docx": "DOCX", "fastapi": "FastAPI", "gcp": "GCP", "html": "HTML", "javascript": "JavaScript",
    "kubernetes": "Kubernetes", "llm": "LLM", "mysql": "MySQL", "node.js": "Node.js",
    "pdf": "PDF", "postgresql": "PostgreSQL", "python": "Python", "rag": "RAG", "react": "React",
    "redis": "Redis", "rest": "REST", "sql": "SQL", "typescript": "TypeScript",
}


def _field_keys(field_name: str, aliases: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return (field_name, *aliases[field_name])


def _canonical_alias(key: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    return next(
        (
            field_name
            for field_name, field_aliases in aliases.items()
            if key == field_name or key in field_aliases
        ),
        None,
    )


def _clean_text(value: Any, maximum: int) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    text = " ".join(str(value).replace("\x00", "").split()).strip()
    return text[:maximum]


def _canonical_dimension_name(value: Any) -> str | None:
    normalized = _clean_text(value, 80).casefold().replace(" ", "_")
    for field_name in DIMENSION_FIELD_ALIASES:
        for alias in _field_keys(field_name, DIMENSION_FIELD_ALIASES):
            # Match the legacy list normalizer's effective aliases.  Its
            # casefolding made camelCase aliases unreachable in this shape.
            if alias == alias.casefold().replace(" ", "_") and normalized == alias:
                return field_name
    return None


def _normalize_skill(value: Any) -> str:
    text = _clean_text(value, 80).strip(" ,;|\t")
    return SKILL_CASE.get(text.casefold(), text)


def _dedupe_skills(values: Any, maximum: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        text = _normalize_skill(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= maximum:
            break
    return result


def _score(value: Any) -> int:
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        value = match.group(0) if match else 0
    try:
        number = round(float(value or 0))
    except (TypeError, ValueError, OverflowError):
        number = 0
    return max(0, min(100, number))


def _salvage_score(value: Any, *, actions: list[str], rejected: list[int]) -> int:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return 0
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if not match:
            _note_action(actions, "invalid_field_defaulted")
            rejected[0] += 1
            return 0
        _note_action(actions, "numeric_string_normalized")
        parsed = float(match.group(0))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = float(value)
    else:
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return 0
    bounded = _score(parsed)
    if bounded != parsed:
        _note_action(actions, "score_clamped")
    return bounded


def _note_action(actions: list[str], code: str) -> None:
    if code not in actions:
        actions.append(code)


def _clean_salvage_string(
    value: Any,
    *,
    maximum: int,
    actions: list[str],
) -> str | None:
    if not isinstance(value, str):
        return None
    clean = _clean_text(value, maximum)
    if len(value) > maximum:
        _note_action(actions, "text_truncated")
    return clean


def _salvage_string_list(
    value: Any,
    *,
    maximum_items: int,
    maximum_length: int,
    reject_empty_scalar: bool = False,
    actions: list[str],
    rejected: list[int],
) -> list[str]:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return []
    if isinstance(value, str):
        _note_action(actions, "scalar_to_list")
        clean = _clean_salvage_string(
            value,
            maximum=maximum_length,
            actions=actions,
        )
        if not clean and reject_empty_scalar:
            _note_action(actions, "invalid_list_item_removed")
            rejected[0] += 1
        return [clean] if clean else []
    if not isinstance(value, list):
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return []

    result: list[str] = []
    for item in value:
        clean = _clean_salvage_string(
            item,
            maximum=maximum_length,
            actions=actions,
        )
        if clean is None or not clean:
            _note_action(actions, "invalid_list_item_removed")
            rejected[0] += 1
            continue
        result.append(clean)
        if len(result) >= maximum_items:
            if len(value) > maximum_items:
                _note_action(actions, "list_truncated")
                rejected[0] += len(value) - maximum_items
            break
    return list(dict.fromkeys(result))[:maximum_items]


def _salvage_narrative_field(
    value: Any,
    *,
    list_field: bool,
    maximum_items: int,
    maximum_length: int,
    actions: list[str],
    rejected: list[int],
) -> str | list[str]:
    """Normalize the active shallow narrative contract without rejecting peers."""
    if list_field:
        return _salvage_string_list(
            value,
            maximum_items=maximum_items,
            maximum_length=maximum_length,
            actions=actions,
            rejected=rejected,
        )
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return ""
    clean = _clean_salvage_string(value, maximum=maximum_length, actions=actions)
    if clean is None:
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return ""
    return clean


def _salvage_dimension_value(
    value: Any,
    *,
    actions: list[str],
    rejected: list[int],
) -> Any:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return {}
    if isinstance(value, str):
        return {"assessment": _clean_text(value, 240)}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"score": _score(value)}
    if not isinstance(value, dict):
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return {}

    normalized: dict[str, Any] = {}
    for key, nested in value.items():
        canonical = _canonical_alias(key, DIMENSION_VALUE_ALIASES)
        if canonical is None:
            _note_action(actions, "unknown_nested_field_ignored")
            rejected[0] += 1
            continue
        if key != canonical:
            _note_action(actions, "field_alias_normalized")
        if canonical in normalized:
            _note_action(actions, "field_alias_normalized")
            continue
        if canonical == "score":
            normalized[canonical] = _salvage_score(
                nested,
                actions=actions,
                rejected=rejected,
            )
        elif canonical == "assessment":
            if nested is None:
                _note_action(actions, "null_field_defaulted")
                normalized[canonical] = ""
            else:
                clean = _clean_salvage_string(nested, maximum=240, actions=actions)
                if clean is None:
                    _note_action(actions, "invalid_field_defaulted")
                    rejected[0] += 1
                    normalized[canonical] = ""
                else:
                    normalized[canonical] = clean
        else:
            normalized[canonical] = _salvage_string_list(
                nested,
                maximum_items=5,
                maximum_length=80,
                reject_empty_scalar=True,
                actions=actions,
                rejected=rejected,
            )
    return normalized


def _salvage_dimensions(
    value: Any,
    *,
    actions: list[str],
    rejected: list[int],
) -> dict[str, Any]:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return {}
    if isinstance(value, list):
        normalized: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                _note_action(actions, "invalid_list_item_removed")
                rejected[0] += 1
                continue
            canonical = _canonical_dimension_name(
                item.get("dimension") or item.get("name") or item.get("key")
            )
            if canonical is None:
                _note_action(actions, "invalid_list_item_removed")
                rejected[0] += 1
                continue
            _note_action(actions, "evidence_mapping_normalized")
            normalized[canonical] = _salvage_dimension_value(
                {key: nested for key, nested in item.items() if key not in {"dimension", "name", "key"}},
                actions=actions,
                rejected=rejected,
            )
        return normalized
    if not isinstance(value, dict):
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return {}
    normalized = {}
    for key, nested in value.items():
        canonical = _canonical_alias(key, DIMENSION_FIELD_ALIASES)
        if canonical is None:
            _note_action(actions, "unknown_nested_field_ignored")
            rejected[0] += 1
            continue
        if key != canonical:
            _note_action(actions, "field_alias_normalized")
        normalized[canonical] = _salvage_dimension_value(
            nested,
            actions=actions,
            rejected=rejected,
        )
    return normalized


def _salvage_evidence_references(
    value: Any,
    *,
    actions: list[str],
    rejected: list[int],
) -> list[dict[str, Any]]:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return []
    if isinstance(value, dict):
        if any(key in value for key in ("skill", "name", "requirement")):
            values: list[Any] = [value]
        else:
            _note_action(actions, "evidence_mapping_normalized")
            values = [
                {"skill": skill, "evidence_ids": evidence}
                for skill, evidence in value.items()
                if isinstance(skill, str)
            ]
    elif isinstance(value, list):
        values = value
    else:
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return []

    result: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            _note_action(actions, "invalid_list_item_removed")
            rejected[0] += 1
            continue
        normalized: dict[str, Any] = {}
        for key, nested in item.items():
            canonical = _canonical_alias(key, EVIDENCE_REFERENCE_ALIASES)
            if canonical is None:
                _note_action(actions, "unknown_nested_field_ignored")
                rejected[0] += 1
                continue
            if key != canonical:
                _note_action(actions, "field_alias_normalized")
            if canonical in normalized:
                continue
            if canonical == "skill":
                clean_source = _clean_salvage_string(
                    nested,
                    maximum=80,
                    actions=actions,
                )
                clean = _normalize_skill(clean_source) if clean_source is not None else ""
                if clean is None or not clean:
                    _note_action(actions, "invalid_list_item_removed")
                    rejected[0] += 1
                    normalized = {}
                    break
                normalized[canonical] = clean
            else:
                normalized[canonical] = _salvage_string_list(
                    nested,
                    maximum_items=5,
                    maximum_length=80,
                    reject_empty_scalar=True,
                    actions=actions,
                    rejected=rejected,
                )
        if normalized.get("skill"):
            normalized.setdefault("evidence_ids", [])
            result.append(normalized)
        if len(result) >= 12:
            if len(values) > 12:
                _note_action(actions, "list_truncated")
                rejected[0] += len(values) - 12
            break
    return result


def salvage_compact_analysis(data: dict[str, Any]) -> SalvagedCompactAnalysis:
    """Apply only named, bounded field salvage before schema validation."""
    if not isinstance(data, dict):
        return SalvagedCompactAnalysis(data={}, action_codes=("invalid_root_structure",), rejected_field_count=1)

    actions: list[str] = []
    rejected = [0]
    normalized: dict[str, Any] = {}
    known_keys = set(CANONICAL_ANALYSIS_FIELDS)
    known_keys.update(PROVIDER_CANONICAL_FIELDS)
    known_keys.update(OPTIONAL_PROVIDER_NARRATIVE_FIELDS)
    for aliases in TOP_LEVEL_FIELD_ALIASES.values():
        known_keys.update(aliases)
    for aliases in PROVIDER_FIELD_ALIASES.values():
        known_keys.update(aliases)
    for key in data:
        if key not in known_keys:
            _note_action(actions, "unknown_top_level_field_ignored")
            rejected[0] += 1

    legacy_present = any(
        key in data
        for field_name in CANONICAL_ANALYSIS_FIELDS
        if field_name != "concise_recommendations"
        for key in _field_keys(field_name, TOP_LEVEL_FIELD_ALIASES)
    )
    legacy_present = legacy_present or "concise_recommendations" in data

    # Normalize the active four-field contract first.  A legacy response is
    # allowed to remain complete for compatibility; a new response that omits
    # one of these optional narrative fields becomes partial after defaults.
    active_action_start = len(actions)
    for field_name in PROVIDER_CANONICAL_FIELDS:
        source_key = field_name if field_name in data else next(
            (alias for alias in _field_keys(field_name, PROVIDER_FIELD_ALIASES) if alias in data),
            None,
        )
        if (
            source_key is None
            and field_name == "recommendations"
            and "concise_recommendations" in data
        ):
            # This legacy name overlaps the compatibility field below and is
            # therefore handled here without making it a Pydantic alias for
            # two fields.
            source_key = "concise_recommendations"
        list_field = field_name != "job_summary"
        if source_key is None:
            if not legacy_present:
                _note_action(actions, "missing_optional_field_defaulted")
            normalized[field_name] = [] if list_field else ""
            continue
        if source_key != field_name and not legacy_present:
            _note_action(actions, "field_alias_normalized")
        normalized[field_name] = _salvage_narrative_field(
            data[source_key],
            list_field=list_field,
            maximum_items={
                "match_reasons": 5,
                "recommendations": 5,
                "resume_improvements": 4,
            }.get(field_name, 1),
            maximum_length=(
                320
                if field_name == "job_summary" and source_key == field_name
                else {
                    "job_summary": 480,
                    "match_reasons": 180,
                    "recommendations": 180,
                    "resume_improvements": 220,
                }[field_name]
            ),
            actions=actions,
            rejected=rejected,
        )
    if legacy_present:
        del actions[active_action_start:]

    if legacy_present:
        for field_name in CANONICAL_ANALYSIS_FIELDS:
            source_key = field_name if field_name in data else next(
                (alias for alias in _field_keys(field_name, TOP_LEVEL_FIELD_ALIASES) if alias in data),
                None,
            )
            if source_key is None:
                _note_action(
                    actions,
                    "missing_required_field_defaulted"
                    if field_name in REQUIRED_ANALYSIS_FIELDS
                    else "missing_optional_field_defaulted",
                )
                normalized[field_name] = {} if field_name == "concise_dimension_assessments" else []
                continue
            if source_key != field_name:
                _note_action(actions, "field_alias_normalized")
            value = data[source_key]
            if field_name in {
                "matched_skills", "missing_skills", "unknown_skills"
            }:
                skills = _salvage_string_list(
                    value,
                    maximum_items=12 if field_name != "unknown_skills" else 10,
                    maximum_length=80,
                    actions=actions,
                    rejected=rejected,
                )
                normalized[field_name] = _dedupe_skills(
                    skills,
                    12 if field_name != "unknown_skills" else 10,
                )
            elif field_name == "concise_recommendations":
                normalized[field_name] = _salvage_string_list(
                    value,
                    maximum_items=5,
                    maximum_length=180,
                    actions=actions,
                    rejected=rejected,
                )
            elif field_name == "unsupported_claim_candidates":
                normalized[field_name] = _salvage_string_list(
                    value,
                    maximum_items=5,
                    maximum_length=240,
                    actions=actions,
                    rejected=rejected,
                )
            elif field_name == "concise_dimension_assessments":
                normalized[field_name] = _salvage_dimensions(
                    value,
                    actions=actions,
                    rejected=rejected,
                )
            else:
                normalized[field_name] = _salvage_evidence_references(
                    value,
                    actions=actions,
                    rejected=rejected,
                )

    # The active prompt intentionally keeps these backend-completed fields out
    # of the requested compact model contract. Accept them only as bounded
    # compatibility fields when an operator/provider sends them anyway, so a
    # valid Provider narrative is preserved rather than silently replaced.
    for field_name in OPTIONAL_PROVIDER_NARRATIVE_FIELDS:
        if field_name not in data:
            continue
        if field_name in PROVIDER_CANONICAL_FIELDS and not legacy_present:
            if not isinstance(data[field_name], str):
                _note_action(actions, "invalid_field_defaulted")
                rejected[0] += 1
            continue
        clean = _clean_salvage_string(
            data[field_name],
            maximum=320,
            actions=actions,
        )
        if clean is None:
            _note_action(actions, "invalid_field_defaulted")
            rejected[0] += 1
            normalized[field_name] = ""
        else:
            normalized[field_name] = clean

    accepted = sum(
        1
        for value in normalized.values()
        if value not in (None, "", [], {})
    )
    return SalvagedCompactAnalysis(
        data=normalized,
        action_codes=tuple(actions),
        rejected_field_count=max(0, min(rejected[0], 100)),
        accepted_field_count=max(0, min(accepted, 32)),
    )


def salvage_warning_messages(action_codes: Any) -> list[str]:
    """Map bounded internal action categories to stable user-safe warnings."""
    messages: list[str] = []
    for code in action_codes if isinstance(action_codes, (list, tuple, set)) else []:
        if code == "text_truncated":
            message = "A model text field was bounded to the supported length."
        elif code == "invalid_root_structure":
            message = "The model response did not have a recognizable object structure."
        else:
            message = SALVAGE_WARNING_MESSAGES.get(str(code))
        if message and message not in messages:
            messages.append(message)
    return messages[:12]


def compact_has_meaningful_analysis(compact: "CompactAnalysisOutput") -> bool:
    """Minimum safe acceptance: retain useful narrative or a legacy judgment."""
    if (
        compact.job_summary.strip()
        or compact.match_reasons
        or compact.recommendations
        or compact.resume_improvements
    ):
        return True
    assessments = compact.concise_dimension_assessments
    meaningful_assessment = any(
        getattr(assessments, key).assessment or getattr(assessments, key).score > 0
        for key in ("skills_match", "project_experience", "education", "work_experience", "keyword_match")
    )
    return bool(
        compact.matched_skills
        or compact.missing_skills
        or compact.unknown_skills
        or compact.concise_recommendations
        or meaningful_assessment
    )


class CompactDimensionAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    score: int = Field(
        default=0,
        validation_alias=AliasChoices(*_field_keys("score", DIMENSION_VALUE_ALIASES)),
    )
    assessment: ConciseAssessment = Field(
        default="",
        validation_alias=AliasChoices(*_field_keys("assessment", DIMENSION_VALUE_ALIASES)),
    )
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("evidence_ids", DIMENSION_VALUE_ALIASES)),
    )


class CompactDimensionAssessments(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    skills_match: CompactDimensionAssessment = Field(
        default_factory=CompactDimensionAssessment,
        validation_alias=AliasChoices(*_field_keys("skills_match", DIMENSION_FIELD_ALIASES)),
    )
    project_experience: CompactDimensionAssessment = Field(
        default_factory=CompactDimensionAssessment,
        validation_alias=AliasChoices(*_field_keys("project_experience", DIMENSION_FIELD_ALIASES)),
    )
    education: CompactDimensionAssessment = Field(
        default_factory=CompactDimensionAssessment,
        validation_alias=AliasChoices(*_field_keys("education", DIMENSION_FIELD_ALIASES)),
    )
    work_experience: CompactDimensionAssessment = Field(
        default_factory=CompactDimensionAssessment,
        validation_alias=AliasChoices(*_field_keys("work_experience", DIMENSION_FIELD_ALIASES)),
    )
    keyword_match: CompactDimensionAssessment = Field(
        default_factory=CompactDimensionAssessment,
        validation_alias=AliasChoices(*_field_keys("keyword_match", DIMENSION_FIELD_ALIASES)),
    )


class CompactEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    skill: ConciseSkill = Field(
        default="",
        validation_alias=AliasChoices(*_field_keys("skill", EVIDENCE_REFERENCE_ALIASES)),
    )
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("evidence_ids", EVIDENCE_REFERENCE_ALIASES)),
    )


class CompactAnalysisOutput(BaseModel):
    """The active shallow contract plus bounded legacy compatibility fields."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    job_summary: Annotated[str, Field(max_length=480)] = Field(
        default="",
        validation_alias=AliasChoices(*_field_keys("job_summary", PROVIDER_FIELD_ALIASES)),
    )
    match_reasons: list[ConciseRecommendation] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("match_reasons", PROVIDER_FIELD_ALIASES)),
    )
    recommendations: list[ConciseRecommendation] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("recommendations", PROVIDER_FIELD_ALIASES)),
    )
    resume_improvements: list[Annotated[str, Field(max_length=220)]] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("resume_improvements", PROVIDER_FIELD_ALIASES)),
    )

    matched_skills: list[ConciseSkill] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("matched_skills", TOP_LEVEL_FIELD_ALIASES)),
    )
    missing_skills: list[ConciseSkill] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("missing_skills", TOP_LEVEL_FIELD_ALIASES)),
    )
    unknown_skills: list[ConciseSkill] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("unknown_skills", TOP_LEVEL_FIELD_ALIASES)),
    )
    concise_dimension_assessments: CompactDimensionAssessments = Field(
        default_factory=CompactDimensionAssessments,
        validation_alias=AliasChoices(*_field_keys("concise_dimension_assessments", TOP_LEVEL_FIELD_ALIASES)),
    )
    evidence_references: list[CompactEvidenceReference] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("evidence_references", TOP_LEVEL_FIELD_ALIASES)),
    )
    unsupported_claim_candidates: list[ConciseClaim] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("unsupported_claim_candidates", TOP_LEVEL_FIELD_ALIASES)),
    )
    concise_recommendations: list[ConciseRecommendation] = Field(
        default_factory=list,
        validation_alias=AliasChoices(*_field_keys("concise_recommendations", TOP_LEVEL_FIELD_ALIASES)),
    )

    @model_validator(mode="after")
    def require_some_analysis(self) -> "CompactAnalysisOutput":
        if not compact_has_meaningful_analysis(self):
            raise ValueError("No usable analysis fields were returned.")
        return self


def normalize_finish_reason(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in TRUNCATED_FINISH_REASONS:
        return "length"
    if text in RESOURCE_FINISH_REASONS:
        return "resource"
    if text == "stop":
        return "stop"
    if not text:
        return "unknown"
    return "other"


def safe_nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def safe_model_metadata(value: dict[str, Any]) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    try:
        latency_ms = round(
            min(max(float(value.get("latency_ms") or 0), 0), MAX_PROVIDER_METADATA_LATENCY_MS),
            3,
        )
    except (TypeError, ValueError):
        latency_ms = 0.0
    metadata = {
        "finish_reason": normalize_finish_reason(value.get("finish_reason")),
        "input_tokens": min(safe_nonnegative_int(value.get("input_tokens")), MAX_PROVIDER_METADATA_TOKENS),
        "output_tokens": min(safe_nonnegative_int(value.get("output_tokens")), MAX_PROVIDER_METADATA_TOKENS),
        "total_tokens": min(safe_nonnegative_int(value.get("total_tokens")), MAX_PROVIDER_METADATA_TOKENS),
        "response_length": min(safe_nonnegative_int(value.get("response_length")), MAX_PROVIDER_CONTENT_CHARS),
        "reached_token_limit": bool(value.get("reached_token_limit")),
        "latency_ms": latency_ms,
    }
    model_id = value.get("model_id")
    if isinstance(model_id, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}", model_id):
        metadata["model_id"] = model_id
    if "thinking_enabled" in value:
        metadata["thinking_enabled"] = bool(value.get("thinking_enabled"))
    if value.get("response_mode") == "json_object":
        metadata["response_mode"] = "json_object"
    for key, maximum in (
        ("primary_attempt_count", 2),
        ("repair_attempt_count", 1),
        ("rejected_field_count", 100),
        ("accepted_field_count", 32),
    ):
        if key in value:
            metadata[key] = min(safe_nonnegative_int(value.get(key)), maximum)
    if "empty_content" in value:
        metadata["empty_content"] = bool(value.get("empty_content"))
    retry_reason = value.get("transient_retry_reason")
    if isinstance(retry_reason, str) and retry_reason in SAFE_RETRY_REASONS:
        metadata["transient_retry_reason"] = retry_reason
    timeout_category = value.get("timeout_category")
    if isinstance(timeout_category, str) and timeout_category in SAFE_TIMEOUT_CATEGORIES:
        metadata["timeout_category"] = timeout_category
    timeout_categories = value.get("timeout_categories")
    if isinstance(timeout_categories, (list, tuple, set)):
        metadata["timeout_categories"] = [
            category
            for category in timeout_categories
            if isinstance(category, str) and category in SAFE_TIMEOUT_CATEGORIES
        ][:4]
    attempt_durations = value.get("provider_attempt_durations_ms")
    if isinstance(attempt_durations, (list, tuple)):
        bounded_durations: list[float] = []
        for duration in attempt_durations[:3]:
            try:
                bounded_durations.append(
                    round(
                        min(max(float(duration or 0), 0), MAX_PROVIDER_METADATA_LATENCY_MS),
                        3,
                    )
                )
            except (TypeError, ValueError):
                continue
        metadata["provider_attempt_durations_ms"] = bounded_durations
    for key in (
        "deadline_exhausted",
        "retry_started",
        "repair_started",
        "fallback_selected",
        "history_finalized",
        "idempotency_finalized",
        "client_disconnected",
    ):
        if key in value:
            metadata[key] = bool(value.get(key))
    remaining_bucket = value.get("remaining_deadline_bucket")
    if isinstance(remaining_bucket, str) and remaining_bucket in SAFE_DEADLINE_BUCKETS:
        metadata["remaining_deadline_bucket"] = remaining_bucket
    for key in (
        "provider_attempt_duration_ms",
        "provider_phase_duration_ms",
        "total_analyze_duration_ms",
    ):
        if key in value:
            try:
                metadata[key] = round(
                    min(max(float(value.get(key) or 0), 0), MAX_PROVIDER_METADATA_LATENCY_MS),
                    3,
                )
            except (TypeError, ValueError):
                metadata[key] = 0.0
    parse_outcome = value.get("parse_outcome")
    if isinstance(parse_outcome, str) and parse_outcome in SAFE_PARSE_OUTCOMES:
        metadata["parse_outcome"] = parse_outcome
    action_codes = value.get("salvage_action_categories")
    if isinstance(action_codes, (list, tuple, set)):
        metadata["salvage_action_categories"] = [
            str(code)[:48]
            for code in action_codes
            if isinstance(code, str) and re.fullmatch(r"[a-z0-9_:-]{1,48}", code)
        ][:12]
    result_state = value.get("result_state")
    if isinstance(result_state, str) and result_state in SAFE_RESULT_STATES:
        metadata["result_state"] = result_state
    fallback_reason = value.get("fallback_reason")
    if isinstance(fallback_reason, str) and re.fullmatch(r"[a-z0-9_:-]{1,64}", fallback_reason):
        metadata["fallback_reason"] = fallback_reason
    return metadata


def adapt_provider_completion(completion: Any, *, max_output_tokens: int, latency_ms: float) -> ProviderAnalysisResponse:
    usage = getattr(completion, "usage", None)
    output_tokens = safe_nonnegative_int(getattr(usage, "completion_tokens", 0))
    try:
        choice = completion.choices[0]
    except (AttributeError, IndexError, TypeError):
        choice = None
    raw_finish_reason = getattr(choice, "finish_reason", None) if choice is not None else None
    raw_content = getattr(getattr(choice, "message", None), "content", "")
    content = raw_content if isinstance(raw_content, str) else ""
    if len(content) > MAX_PROVIDER_CONTENT_CHARS:
        metadata = safe_model_metadata({
            "finish_reason": raw_finish_reason,
            "input_tokens": getattr(usage, "prompt_tokens", 0),
            "output_tokens": output_tokens,
            "total_tokens": getattr(usage, "total_tokens", 0),
            "response_length": len(content),
            "latency_ms": latency_ms,
        })
        raise ModelOutputError(MODEL_OUTPUT_TOO_LARGE, metadata=metadata)
    metadata = safe_model_metadata({
        "finish_reason": raw_finish_reason,
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": output_tokens,
        "total_tokens": getattr(usage, "total_tokens", 0),
        "response_length": len(content),
        "reached_token_limit": normalize_finish_reason(raw_finish_reason) == "length"
        or output_tokens >= max(int(max_output_tokens), 1),
        "latency_ms": latency_ms,
    })
    normalized_finish_reason = normalize_finish_reason(raw_finish_reason)
    if normalized_finish_reason == "length":
        raise ModelOutputError(MODEL_OUTPUT_TRUNCATED, metadata=metadata)
    if normalized_finish_reason == "resource":
        raise ModelOutputError(MODEL_OUTPUT_RESOURCE_LIMIT, metadata=metadata)
    if not content.strip():
        metadata["empty_content"] = True
        raise ModelOutputError(MODEL_OUTPUT_EMPTY, metadata=metadata)
    return ProviderAnalysisResponse(content=content, metadata=metadata)


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    while start >= 0:
        depth = 0
        quoted = False
        escaped = False
        for index in range(start, len(text)):
            character = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
                continue
            if character == '"':
                quoted = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        start = text.find("{", start + 1)
    return None


def _unwrap_analysis_object(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    expected = {
        "job_summary", "jobSummary", "summary", "match_reasons", "matchReasons", "reasons",
        "match_reason", "matchReason", "recommendations", "suggestions", "next_steps", "nextSteps",
        "resume_improvements", "resumeImprovements", "resume_suggestions", "improvements",
        "matched_skills", "matchedSkills", "matches", "missing_skills", "missingSkills", "gaps",
        "unknown_skills", "unknownSkills", "unknowns", "concise_recommendations", "recommendations",
        "suggestions", "next_steps", "nextSteps", "concise_dimension_assessments",
        "dimension_assessments", "dimensionAssessments", "assessments", "dimensions",
        "evidence_references", "evidenceReferences", "evidence_mapping", "evidenceMapping",
        "unsupported_claim_candidates", "unsupportedCandidates", "unsupported_claims",
    }
    if expected.intersection(value):
        return value, False
    for key in ("analysis", "result", "data", "output"):
        nested = value.get(key)
        if isinstance(nested, dict) and expected.intersection(nested):
            return nested, True
    return value, False


def parse_model_json_result(raw_response: str) -> ParsedModelJson:
    text = str(raw_response or "").lstrip("\ufeff").strip()
    if not text:
        raise ModelOutputError(MODEL_OUTPUT_EMPTY)
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID)
        parsed, unwrapped = _unwrap_analysis_object(parsed)
        warnings = ("A single analysis wrapper object was removed safely.",) if unwrapped else ()
        return ParsedModelJson(
            parsed,
            normalized=unwrapped,
            warnings=warnings,
            warning_codes=("wrapper_removed",) if unwrapped else (),
        )
    except json.JSONDecodeError:
        pass

    candidate = _first_balanced_object(text)
    if candidate is None:
        raise ModelOutputError(MODEL_OUTPUT_INVALID_JSON)
    repaired = TRAILING_COMMA.sub(r"\1", candidate)
    try:
        parsed = json.loads(repaired)
    except json.JSONDecodeError as exc:
        raise ModelOutputError(MODEL_OUTPUT_INVALID_JSON) from exc
    if not isinstance(parsed, dict):
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID)
    parsed, unwrapped = _unwrap_analysis_object(parsed)
    warnings = ["The model response contained wrappers or minor JSON formatting issues and was normalized locally."]
    warning_codes = ["local_format_repair"]
    if unwrapped:
        warnings.append("A single analysis wrapper object was removed safely.")
        warning_codes.append("wrapper_removed")
    if repaired != candidate:
        warnings.append("A trailing JSON comma was removed safely.")
        warning_codes.append("trailing_comma_removed")
    return ParsedModelJson(
        parsed,
        normalized=True,
        warnings=tuple(warnings),
        warning_codes=tuple(warning_codes),
    )


def parse_model_json(raw_response: str) -> dict[str, Any]:
    return parse_model_json_result(raw_response).data


def compact_analysis_warnings(data: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    missing = [
        field_name
        for field_name in PROVIDER_CANONICAL_FIELDS
        if not any(key in data for key in _field_keys(field_name, PROVIDER_FIELD_ALIASES))
        and not (field_name == "recommendations" and "concise_recommendations" in data)
    ]
    if missing:
        warnings.append("Some optional model fields were missing and safe defaults were used: " + ", ".join(missing) + ".")
    aliases = (
        *PROVIDER_FIELD_ALIASES.values(),
        *(
            TOP_LEVEL_FIELD_ALIASES[field_name]
            for field_name in CANONICAL_ANALYSIS_FIELDS
            if field_name not in {"concise_recommendations", "unsupported_claim_candidates"}
        ),
    )
    has_alias = any(alias in data for field_aliases in aliases for alias in field_aliases)
    if has_alias or "concise_recommendations" in data:
        warnings.append("Equivalent model field aliases were normalized.")
    if any(data.get(key) is None for key in data):
        warnings.append("Null model fields were replaced with safe defaults.")
    return warnings


def validate_compact_analysis(
    data: dict[str, Any] | SalvagedCompactAnalysis,
) -> CompactAnalysisOutput:
    if isinstance(data, SalvagedCompactAnalysis):
        normalized = dict(data.data)
    elif isinstance(data, dict):
        normalized = dict(salvage_compact_analysis(data).data)
    else:
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID)
    if not normalized.get("recommendations") and normalized.get("concise_recommendations"):
        normalized["recommendations"] = list(normalized["concise_recommendations"])
    if not normalized.get("concise_recommendations") and normalized.get("recommendations"):
        normalized["concise_recommendations"] = list(normalized["recommendations"])
    try:
        return CompactAnalysisOutput.model_validate(normalized)
    except ValidationError as exc:
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID) from exc
