"""Strict compact contract and safe provider metadata for resume analysis."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


MODEL_OUTPUT_TRUNCATED = "MODEL_OUTPUT_TRUNCATED"
MODEL_OUTPUT_INVALID_JSON = "MODEL_OUTPUT_INVALID_JSON"
MODEL_OUTPUT_SCHEMA_INVALID = "MODEL_OUTPUT_SCHEMA_INVALID"
MODEL_OUTPUT_EMPTY = "MODEL_OUTPUT_EMPTY"
MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"

MODEL_ERROR_MESSAGES = {
    MODEL_OUTPUT_TRUNCATED: (
        "The model response reached its output limit before completion. Please retry with a more focused input."
    ),
    MODEL_OUTPUT_INVALID_JSON: (
        "The model returned an incomplete or invalid structured response. Please retry."
    ),
    MODEL_OUTPUT_SCHEMA_INVALID: (
        "The model response did not match the required analysis format. Please retry."
    ),
    MODEL_OUTPUT_EMPTY: "The model returned an empty response. Please retry.",
    MODEL_PROVIDER_ERROR: "The model provider request failed safely. Please retry.",
}

TRUNCATED_FINISH_REASONS = {
    "length",
    "max_tokens",
    "max_output_tokens",
    "token_limit",
}


class ModelOutputError(RuntimeError):
    """A classified model failure that contains no model output."""

    def __init__(
        self,
        error_code: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.safe_message = MODEL_ERROR_MESSAGES[error_code]
        self.metadata = safe_model_metadata(metadata) if metadata is not None else {}
        super().__init__(self.safe_message)


@dataclass(frozen=True)
class ProviderAnalysisResponse:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


ConciseSkill = Annotated[str, Field(min_length=1, max_length=80)]
ConciseAssessment = Annotated[str, Field(min_length=1, max_length=240)]
ConciseRecommendation = Annotated[str, Field(min_length=1, max_length=180)]
ConciseClaim = Annotated[str, Field(min_length=1, max_length=240)]
EvidenceId = Annotated[str, Field(pattern=r"^(?:resume|pk:[1-9][0-9]*)$")]


class CompactDimensionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    score: int = Field(ge=0, le=100)
    assessment: ConciseAssessment
    evidence_ids: list[EvidenceId] = Field(default_factory=list, max_length=5)


class CompactDimensionAssessments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills_match: CompactDimensionAssessment
    project_experience: CompactDimensionAssessment
    education: CompactDimensionAssessment
    work_experience: CompactDimensionAssessment
    keyword_match: CompactDimensionAssessment


class CompactEvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    skill: ConciseSkill
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=5)


class CompactAnalysisOutput(BaseModel):
    """The only JSON shape the model may return for resume analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    matched_skills: list[ConciseSkill] = Field(max_length=10)
    missing_skills: list[ConciseSkill] = Field(max_length=10)
    unknown_skills: list[ConciseSkill] = Field(max_length=8)
    concise_dimension_assessments: CompactDimensionAssessments
    evidence_references: list[CompactEvidenceReference] = Field(max_length=10)
    unsupported_claim_candidates: list[ConciseClaim] = Field(max_length=5)
    concise_recommendations: list[ConciseRecommendation] = Field(max_length=5)

    @model_validator(mode="after")
    def evidence_covers_every_matched_skill(self) -> "CompactAnalysisOutput":
        matched = {item.casefold() for item in self.matched_skills}
        referenced = {item.skill.casefold() for item in self.evidence_references}
        if matched != referenced:
            raise ValueError("Every matched skill must have exactly one evidence reference entry.")
        if len(referenced) != len(self.evidence_references):
            raise ValueError("Evidence reference skills must be unique.")
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
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def safe_nonnegative_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def safe_model_metadata(value: dict[str, Any]) -> dict[str, Any]:
    finish_reason = normalize_finish_reason(value.get("finish_reason"))
    try:
        latency_ms = round(max(float(value.get("latency_ms") or 0), 0), 3)
    except (TypeError, ValueError):
        latency_ms = 0.0
    metadata = {
        "finish_reason": finish_reason,
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


def adapt_provider_completion(
    completion: Any,
    *,
    max_output_tokens: int,
    latency_ms: float,
) -> ProviderAnalysisResponse:
    usage = getattr(completion, "usage", None)
    output_tokens = safe_nonnegative_int(getattr(usage, "completion_tokens", 0))
    try:
        choice = completion.choices[0]
    except (AttributeError, IndexError, TypeError):
        choice = None
    raw_finish_reason = getattr(choice, "finish_reason", None) if choice is not None else None
    finish_reason = normalize_finish_reason(raw_finish_reason)
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
    if finish_reason == "length":
        raise ModelOutputError(MODEL_OUTPUT_TRUNCATED, metadata=metadata)
    if not content.strip():
        raise ModelOutputError(MODEL_OUTPUT_EMPTY, metadata=metadata)
    return ProviderAnalysisResponse(content=content, metadata=metadata)


def parse_model_json(raw_response: str) -> dict[str, Any]:
    if not str(raw_response or "").strip():
        raise ModelOutputError(MODEL_OUTPUT_EMPTY)
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ModelOutputError(MODEL_OUTPUT_INVALID_JSON) from exc
    if not isinstance(parsed, dict):
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID)
    return parsed


def validate_compact_analysis(data: dict[str, Any]) -> CompactAnalysisOutput:
    try:
        return CompactAnalysisOutput.model_validate(data)
    except ValidationError as exc:
        raise ModelOutputError(MODEL_OUTPUT_SCHEMA_INVALID) from exc
