"""Validated request contracts for matching and ranking."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DIMENSIONS = (
    "required_skills",
    "experience",
    "projects",
    "education",
    "location_and_authorization",
    "languages",
    "seniority",
    "preferences",
)

DEFAULT_WEIGHTS = {
    "required_skills": 30.0,
    "experience": 20.0,
    "projects": 15.0,
    "education": 10.0,
    "location_and_authorization": 10.0,
    "languages": 5.0,
    "seniority": 5.0,
    "preferences": 5.0,
}


def validate_weights(value: dict[str, float] | None) -> dict[str, float] | None:
    if value is None:
        return None
    if set(value) != set(DIMENSIONS):
        raise ValueError("weight_config must contain exactly the supported dimensions.")
    if any(weight < 0 or weight > 100 for weight in value.values()):
        raise ValueError("Matching weights must be between 0 and 100.")
    if abs(sum(value.values()) - 100) > 0.001:
        raise ValueError("Matching weights must total 100.")
    return {key: float(value[key]) for key in DIMENSIONS}


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_revision: int | None = Field(default=None, ge=1)
    resume_version_id: UUID | None = None
    weight_config: dict[str, float] | None = None
    force_new: bool = False

    _weights = field_validator("weight_config")(validate_weights)


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    filters: dict[str, str | bool | None] = Field(default_factory=dict)
    profile_revision: int | None = Field(default=None, ge=1)
    resume_version_id: UUID | None = None
    weight_config: dict[str, float] | None = None
    deadline_factor: float = Field(default=3, ge=0, le=10)
    user_priority_factor: float = Field(default=2, ge=0, le=10)
    preparation_effort_factor: float = Field(default=2, ge=0, le=10)

    _weights = field_validator("weight_config")(validate_weights)

    @model_validator(mode="after")
    def source(self) -> "RankRequest":
        if not self.job_ids and not self.filters:
            raise ValueError("Provide job_ids or Job Library filters.")
        allowed = {"query", "company", "title", "location", "status", "employment_type", "work_mode"}
        if set(self.filters) - allowed:
            raise ValueError("Ranking filter contains unsupported fields.")
        return self


class ExplanationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: Literal["concise", "detailed"] = "concise"
