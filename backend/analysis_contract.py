"""Tolerant, bounded contract handling for resume analysis model output."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


MODEL_OUTPUT_TRUNCATED = "MODEL_OUTPUT_TRUNCATED"
MODEL_OUTPUT_INVALID_JSON = "MODEL_OUTPUT_INVALID_JSON"
MODEL_OUTPUT_SCHEMA_INVALID = "MODEL_OUTPUT_SCHEMA_INVALID"
MODEL_OUTPUT_EMPTY = "MODEL_OUTPUT_EMPTY"
MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"

MODEL_ERROR_MESSAGES = {
    MODEL_OUTPUT_TRUNCATED: "The model response reached its output limit before completion.",
    MODEL_OUTPUT_INVALID_JSON: "The model returned an incomplete or invalid structured response.",
    MODEL_OUTPUT_SCHEMA_INVALID: "The model response did not contain a usable analysis.",
    MODEL_OUTPUT_EMPTY: "The model returned an empty response.",
    MODEL_PROVIDER_ERROR: "The model provider request failed safely.",
}

TRUNCATED_FINISH_REASONS = {"length", "max_tokens", "max_output_tokens", "token_limit"}
TRAILING_COMMA = re.compile(r",\s*([}\]])")


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
    text = " ".join(str(value or "").replace("\x00", "").split()).strip()
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
        assessments = self.concise_dimension_assessments
        meaningful_assessment = any(
            getattr(assessments, key).assessment
            for key in ("skills_match", "project_experience", "education", "work_experience", "keyword_match")
        )
        if not any((self.matched_skills, self.missing_skills, self.unknown_skills, self.concise_recommendations)) and not meaningful_assessment:
            raise ValueError("No usable analysis fields were returned.")
        return self


def normalize_finish_reason(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in TRUNCATED_FINISH_REASONS:
        return "length"
    if text == "stop":
        return "stop"
    if not text:
        return "unknown"
    return "other"


def safe_provider_request_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else None


def safe_nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def safe_model_metadata(value: dict[str, Any]) -> dict[str, Any]:
    try:
        latency_ms = round(max(float(value.get("latency_ms") or 0), 0), 3)
    except (TypeError, ValueError):
        latency_ms = 0.0
    metadata = {
        "finish_reason": normalize_finish_reason(value.get("finish_reason")),
        "input_tokens": safe_nonnegative_int(value.get("input_tokens")),
        "output_tokens": safe_nonnegative_int(value.get("output_tokens")),
        "total_tokens": safe_nonnegative_int(value.get("total_tokens")),
        "response_length": safe_nonnegative_int(value.get("response_length")),
        "reached_token_limit": bool(value.get("reached_token_limit")),
        "latency_ms": latency_ms,
    }
    request_id_hash = value.get("provider_request_id_hash")
    if isinstance(request_id_hash, str) and re.fullmatch(r"[a-f0-9]{16}", request_id_hash):
        metadata["provider_request_id_hash"] = request_id_hash
    return metadata


def adapt_provider_completion(completion: Any, *, max_output_tokens: int, latency_ms: float) -> ProviderAnalysisResponse:
    usage = getattr(completion, "usage", None)
    output_tokens = safe_nonnegative_int(getattr(usage, "completion_tokens", 0))
    try:
        choice = completion.choices[0]
    except (AttributeError, IndexError, TypeError):
        choice = None
    raw_finish_reason = getattr(choice, "finish_reason", None) if choice is not None else None
    content = str(getattr(getattr(choice, "message", None), "content", "") or "")
    metadata = safe_model_metadata({
        "finish_reason": raw_finish_reason,
        "input_tokens": getattr(usage, "prompt_tokens", 0),
        "output_tokens": output_tokens,
        "total_tokens": getattr(usage, "total_tokens", 0),
        "response_length": len(content),
        "reached_token_limit": output_tokens >= max(int(max_output_tokens), 1),
        "latency_ms": latency_ms,
        "provider_request_id_hash": safe_provider_request_id(getattr(completion, "id", None)),
    })
    if normalize_finish_reason(raw_finish_reason) == "length":
        raise ModelOutputError(MODEL_OUTPUT_TRUNCATED, metadata=metadata)
    if not content.strip():
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
        return ParsedModelJson(parsed, normalized=unwrapped, warnings=warnings)
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
    if unwrapped:
        warnings.append("A single analysis wrapper object was removed safely.")
    if repaired != candidate:
        warnings.append("A trailing JSON comma was removed safely.")
    return ParsedModelJson(parsed, normalized=True, warnings=tuple(warnings))


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
