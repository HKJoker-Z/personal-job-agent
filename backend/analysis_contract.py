"""Tolerant, bounded contract handling for resume analysis model output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


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

CANONICAL_ANALYSIS_FIELDS = (
    "matched_skills",
    "missing_skills",
    "unknown_skills",
    "concise_dimension_assessments",
    "evidence_references",
    "unsupported_claim_candidates",
    "concise_recommendations",
)
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
    field count: at least one skill-state judgment, dimension assessment, or
    concise recommendation must survive bounded normalization. Backend-owned
    scoring, evidence reconciliation, Job Summary, and Match Reasons are then
    derived only from validated local data.
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


def _default_for_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (tuple, set)):
        return list(value)
    return value


def _default_for_dict(value: Any) -> Any:
    return {} if value is None else value


def _clean_text(value: Any, maximum: int) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    text = " ".join(str(value).replace("\x00", "").split()).strip()
    return text[:maximum]


def _normalize_skill(value: Any) -> str:
    text = _clean_text(value, 80).strip(" ,;|\t")
    return SKILL_CASE.get(text.casefold(), text)


def _dedupe_skills(values: Any, maximum: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in _default_for_list(values) if isinstance(_default_for_list(values), list) else []:
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
    return result


def _salvage_evidence_ids(
    value: Any,
    *,
    actions: list[str],
    rejected: list[int],
) -> list[str]:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return []
    if isinstance(value, str):
        _note_action(actions, "scalar_to_list")
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return []
    result: list[str] = []
    for item in values:
        clean = _clean_salvage_string(item, maximum=80, actions=actions)
        if clean is None or not clean:
            _note_action(actions, "invalid_list_item_removed")
            rejected[0] += 1
            continue
        result.append(clean)
        if len(result) >= 5:
            if len(values) > 5:
                _note_action(actions, "list_truncated")
                rejected[0] += len(values) - 5
            break
    return list(dict.fromkeys(result))


def _salvage_dimension_value(
    value: Any,
    *,
    actions: list[str],
    rejected: list[int],
) -> Any:
    if value is None:
        _note_action(actions, "null_field_defaulted")
        return {}
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        _note_action(actions, "invalid_field_defaulted")
        rejected[0] += 1
        return {}

    aliases = {
        "score": "score", "rating": "score", "percentage": "score",
        "assessment": "assessment", "summary": "assessment", "reason": "assessment", "comment": "assessment",
        "evidence_ids": "evidence_ids", "evidenceIds": "evidence_ids",
        "evidence": "evidence_ids", "references": "evidence_ids",
    }
    normalized: dict[str, Any] = {}
    for key, nested in value.items():
        canonical = aliases.get(key)
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
            if nested is None:
                _note_action(actions, "null_field_defaulted")
                normalized[canonical] = 0
                continue
            if isinstance(nested, str):
                match = re.search(r"-?\d+(?:\.\d+)?", nested)
                if not match:
                    _note_action(actions, "invalid_field_defaulted")
                    rejected[0] += 1
                    normalized[canonical] = 0
                    continue
                _note_action(actions, "numeric_string_normalized")
                parsed = float(match.group(0))
            elif isinstance(nested, (int, float)) and not isinstance(nested, bool):
                parsed = float(nested)
            else:
                _note_action(actions, "invalid_field_defaulted")
                rejected[0] += 1
                normalized[canonical] = 0
                continue
            bounded = max(0, min(100, round(parsed)))
            if bounded != parsed:
                _note_action(actions, "score_clamped")
            normalized[canonical] = bounded
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
            normalized[canonical] = _salvage_evidence_ids(
                nested,
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
    aliases = {
        "skills_match": "skills_match", "skillsMatch": "skills_match", "skills": "skills_match",
        "project_experience": "project_experience", "projectExperience": "project_experience", "projects": "project_experience",
        "education": "education",
        "work_experience": "work_experience", "workExperience": "work_experience", "experience": "work_experience",
        "keyword_match": "keyword_match", "keywordMatch": "keyword_match", "keywords": "keyword_match",
    }
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
            name = _clean_text(item.get("dimension") or item.get("name") or item.get("key"), 80)
            canonical = aliases.get(name.casefold().replace(" ", "_"))
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
        canonical = aliases.get(key)
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
    aliases = {
        "skill": "skill", "name": "skill", "requirement": "skill",
        "evidence_ids": "evidence_ids", "evidenceIds": "evidence_ids",
        "evidence": "evidence_ids", "references": "evidence_ids",
    }
    for item in values:
        if not isinstance(item, dict):
            _note_action(actions, "invalid_list_item_removed")
            rejected[0] += 1
            continue
        normalized: dict[str, Any] = {}
        for key, nested in item.items():
            canonical = aliases.get(key)
            if canonical is None:
                _note_action(actions, "unknown_nested_field_ignored")
                rejected[0] += 1
                continue
            if key != canonical:
                _note_action(actions, "field_alias_normalized")
            if canonical in normalized:
                continue
            if canonical == "skill":
                clean = _clean_salvage_string(nested, maximum=80, actions=actions)
                if clean is None or not clean:
                    _note_action(actions, "invalid_list_item_removed")
                    rejected[0] += 1
                    normalized = {}
                    break
                normalized[canonical] = clean
            else:
                normalized[canonical] = _salvage_evidence_ids(
                    nested,
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
    known_keys.update(OPTIONAL_PROVIDER_NARRATIVE_FIELDS)
    for aliases in TOP_LEVEL_FIELD_ALIASES.values():
        known_keys.update(aliases)
    for key in data:
        if key not in known_keys:
            _note_action(actions, "unknown_top_level_field_ignored")
            rejected[0] += 1

    for field_name in CANONICAL_ANALYSIS_FIELDS:
        source_key = field_name if field_name in data else next(
            (alias for alias in TOP_LEVEL_FIELD_ALIASES[field_name] if alias in data),
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
            normalized[field_name] = _salvage_string_list(
                value,
                maximum_items=12 if field_name != "unknown_skills" else 10,
                maximum_length=80,
                actions=actions,
                rejected=rejected,
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
    """Minimum safe acceptance: retain a judgment, not merely a JSON object."""
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

    score: int = Field(default=0, validation_alias=AliasChoices("score", "rating", "percentage"))
    assessment: ConciseAssessment = Field(
        default="", validation_alias=AliasChoices("assessment", "summary", "reason", "comment")
    )
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list, validation_alias=AliasChoices("evidence_ids", "evidenceIds", "evidence", "references")
    )

    @model_validator(mode="before")
    @classmethod
    def accept_concise_scalar(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"assessment": value}
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"score": value}
        return value

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value: Any) -> int:
        return _score(value)

    @field_validator("assessment", mode="before")
    @classmethod
    def normalize_assessment(cls, value: Any) -> str:
        return _clean_text(value, 240)

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any) -> Any:
        return _default_for_list(value)

    @field_validator("evidence_ids", mode="after")
    @classmethod
    def clean_evidence(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_clean_text(item, 80) for item in value if _clean_text(item, 80)))[:5]


def _empty_dimension() -> CompactDimensionAssessment:
    return CompactDimensionAssessment()


class CompactDimensionAssessments(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    skills_match: CompactDimensionAssessment = Field(
        default_factory=_empty_dimension, validation_alias=AliasChoices("skills_match", "skillsMatch", "skills")
    )
    project_experience: CompactDimensionAssessment = Field(
        default_factory=_empty_dimension,
        validation_alias=AliasChoices("project_experience", "projectExperience", "projects"),
    )
    education: CompactDimensionAssessment = Field(default_factory=_empty_dimension)
    work_experience: CompactDimensionAssessment = Field(
        default_factory=_empty_dimension,
        validation_alias=AliasChoices("work_experience", "workExperience", "experience"),
    )
    keyword_match: CompactDimensionAssessment = Field(
        default_factory=_empty_dimension,
        validation_alias=AliasChoices("keyword_match", "keywordMatch", "keywords"),
    )

    @model_validator(mode="before")
    @classmethod
    def accept_named_dimension_list(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        result: dict[str, Any] = {}
        aliases = {
            "skills": "skills_match", "skills_match": "skills_match",
            "projects": "project_experience", "project_experience": "project_experience",
            "education": "education", "experience": "work_experience",
            "work_experience": "work_experience", "keywords": "keyword_match",
            "keyword_match": "keyword_match",
        }
        for item in value:
            if not isinstance(item, dict):
                continue
            name = _clean_text(
                item.get("dimension") or item.get("name") or item.get("key"), 80
            ).casefold().replace(" ", "_")
            canonical = aliases.get(name)
            if canonical:
                result[canonical] = {
                    key: nested for key, nested in item.items()
                    if key not in {"dimension", "name", "key"}
                }
        return result


class CompactEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    skill: ConciseSkill = Field(default="", validation_alias=AliasChoices("skill", "name", "requirement"))
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list, validation_alias=AliasChoices("evidence_ids", "evidenceIds", "evidence", "references")
    )

    @field_validator("skill", mode="before")
    @classmethod
    def clean_skill(cls, value: Any) -> str:
        return _normalize_skill(value)

    @field_validator("evidence_ids", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any) -> Any:
        return _default_for_list(value)

    @field_validator("evidence_ids", mode="after")
    @classmethod
    def clean_evidence(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_clean_text(item, 80) for item in value if _clean_text(item, 80)))[:5]


class CompactAnalysisOutput(BaseModel):
    """The small set of judgments requested from the model."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, populate_by_name=True)

    matched_skills: list[ConciseSkill] = Field(
        default_factory=list, validation_alias=AliasChoices("matched_skills", "matchedSkills", "matches")
    )
    missing_skills: list[ConciseSkill] = Field(
        default_factory=list, validation_alias=AliasChoices("missing_skills", "missingSkills", "gaps")
    )
    unknown_skills: list[ConciseSkill] = Field(
        default_factory=list, validation_alias=AliasChoices("unknown_skills", "unknownSkills", "unknowns")
    )
    concise_dimension_assessments: CompactDimensionAssessments = Field(
        default_factory=CompactDimensionAssessments,
        validation_alias=AliasChoices(
            "concise_dimension_assessments", "dimension_assessments", "dimensionAssessments", "assessments", "dimensions"
        ),
    )
    evidence_references: list[CompactEvidenceReference] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evidence_references", "evidenceReferences", "evidence_mapping", "evidenceMapping"),
    )
    unsupported_claim_candidates: list[ConciseClaim] = Field(
        default_factory=list,
        validation_alias=AliasChoices("unsupported_claim_candidates", "unsupportedCandidates", "unsupported_claims"),
    )
    concise_recommendations: list[ConciseRecommendation] = Field(
        default_factory=list,
        validation_alias=AliasChoices("concise_recommendations", "recommendations", "suggestions", "next_steps", "nextSteps"),
    )

    @field_validator(
        "matched_skills", "missing_skills", "unknown_skills",
        "unsupported_claim_candidates", "concise_recommendations", mode="before"
    )
    @classmethod
    def list_defaults(cls, value: Any) -> Any:
        return _default_for_list(value)

    @field_validator("evidence_references", mode="before")
    @classmethod
    def evidence_list_defaults(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            if any(key in value for key in ("skill", "name", "requirement")):
                return [value]
            return [
                {"skill": skill, "evidence_ids": evidence}
                for skill, evidence in value.items()
                if isinstance(skill, str)
            ]
        return _default_for_list(value)

    @field_validator("concise_dimension_assessments", mode="before")
    @classmethod
    def object_default(cls, value: Any) -> Any:
        return _default_for_dict(value)

    @field_validator("matched_skills", mode="after")
    @classmethod
    def clean_matches(cls, value: list[str]) -> list[str]:
        return _dedupe_skills(value, 12)

    @field_validator("missing_skills", mode="after")
    @classmethod
    def clean_gaps(cls, value: list[str]) -> list[str]:
        return _dedupe_skills(value, 12)

    @field_validator("unknown_skills", mode="after")
    @classmethod
    def clean_unknowns(cls, value: list[str]) -> list[str]:
        return _dedupe_skills(value, 10)

    @field_validator("unsupported_claim_candidates", mode="after")
    @classmethod
    def clean_claims(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_clean_text(item, 240) for item in value if _clean_text(item, 240)))[:5]

    @field_validator("concise_recommendations", mode="after")
    @classmethod
    def clean_recommendations(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_clean_text(item, 180) for item in value if _clean_text(item, 180)))[:5]

    @field_validator("evidence_references", mode="after")
    @classmethod
    def dedupe_references(cls, value: list[CompactEvidenceReference]) -> list[CompactEvidenceReference]:
        result: list[CompactEvidenceReference] = []
        seen: set[str] = set()
        for item in value:
            key = item.skill.casefold()
            if item.skill and key not in seen:
                seen.add(key)
                result.append(item)
        return result[:12]

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
    aliases = {
        "matched_skills": {"matchedSkills", "matches"},
        "missing_skills": {"missingSkills", "gaps"},
        "unknown_skills": {"unknownSkills", "unknowns"},
        "concise_dimension_assessments": {"dimension_assessments", "dimensionAssessments", "assessments", "dimensions"},
        "evidence_references": {"evidenceReferences", "evidence_mapping", "evidenceMapping"},
        "concise_recommendations": {"recommendations", "suggestions", "next_steps", "nextSteps"},
    }
    warnings: list[str] = []
    core = ("matched_skills", "missing_skills", "unknown_skills", "concise_recommendations")
    missing = [key for key in core if key not in data and not aliases[key].intersection(data)]
    if missing:
        warnings.append("Some optional model fields were missing and safe defaults were used: " + ", ".join(missing) + ".")
    if any(aliases[key].intersection(data) for key in aliases):
        warnings.append("Equivalent model field aliases were normalized.")
    if any(data.get(key) is None for key in data):
        warnings.append("Null model fields were replaced with safe defaults.")
    return warnings


def validate_compact_analysis(data: dict[str, Any]) -> CompactAnalysisOutput:
    try:
        return CompactAnalysisOutput.model_validate(data)
    except ValidationError as exc:
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID) from exc
