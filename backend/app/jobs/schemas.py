"""Validated Job Library request contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


JobStatus = Literal["new", "reviewed", "shortlisted", "ignored", "closed", "archived"]
SourceType = Literal["manual", "url", "pdf", "docx", "csv", "migrated"]
RequirementCategory = Literal[
    "skill", "education", "experience", "language", "certification", "location",
    "work_authorization", "responsibility", "benefit", "other",
]


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone.")
    return value.astimezone(timezone.utc) if value else None


class JobFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    location: str = Field(default="", max_length=300)
    description: str = Field(min_length=1, max_length=200_000)
    canonical_url: str | None = Field(default=None, max_length=2048)
    external_reference: str | None = Field(default=None, max_length=500)
    employment_type: str | None = Field(default=None, max_length=80)
    work_mode: str | None = Field(default=None, max_length=80)
    seniority: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=200)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, min_length=3, max_length=8)
    salary_period: str | None = Field(default=None, max_length=30)
    published_at: datetime | None = None
    application_deadline: datetime | None = None
    status: JobStatus = "new"

    _published_aware = field_validator("published_at")(_aware)
    _deadline_aware = field_validator("application_deadline")(_aware)

    @model_validator(mode="after")
    def salary_range(self) -> "JobFields":
        if self.salary_min is not None and self.salary_max is not None and self.salary_max < self.salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min.")
        return self


class JobCreate(JobFields):
    source_type: SourceType = "manual"


class ManualJobImport(JobFields):
    url: str | None = Field(default=None, max_length=2048)
    canonical_url: None = None


class UrlJobImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    url: str = Field(min_length=8, max_length=2048)


class JobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: int = Field(ge=1)
    company_name: str | None = Field(default=None, min_length=1, max_length=300)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, min_length=1, max_length=200_000)
    canonical_url: str | None = Field(default=None, max_length=2048)
    external_reference: str | None = Field(default=None, max_length=500)
    employment_type: str | None = Field(default=None, max_length=80)
    work_mode: str | None = Field(default=None, max_length=80)
    seniority: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=200)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    salary_currency: str | None = Field(default=None, max_length=8)
    salary_period: str | None = Field(default=None, max_length=30)
    published_at: datetime | None = None
    application_deadline: datetime | None = None
    status: JobStatus | None = None

    _published_aware = field_validator("published_at")(_aware)
    _deadline_aware = field_validator("application_deadline")(_aware)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class RequirementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: RequirementCategory
    requirement_type: Literal["required", "preferred", "informational", "hard_filter"]
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)
    importance: int = Field(default=3, ge=1, le=5)
    minimum_years: float | None = Field(default=None, ge=0, le=80)
    evidence_text: str | None = Field(default=None, max_length=4000)
    evidence_start: int | None = Field(default=None, ge=0)
    evidence_end: int | None = Field(default=None, ge=0)
    extraction_source: Literal["deterministic", "llm", "user"] = "user"
    confidence: float = Field(default=1, ge=0, le=1)
    verification_status: Literal["needs_review", "confirmed", "rejected"] = "needs_review"
    sort_order: int = Field(default=0, ge=0, le=10000)

    @model_validator(mode="after")
    def evidence_complete(self) -> "RequirementCreate":
        values = (self.evidence_text, self.evidence_start, self.evidence_end)
        if any(value is not None for value in values) and not all(value is not None for value in values):
            raise ValueError("Evidence text and span must be provided together.")
        if self.evidence_start is not None and self.evidence_end is not None and self.evidence_end < self.evidence_start:
            raise ValueError("Evidence span is invalid.")
        if self.extraction_source == "llm" and self.verification_status != "needs_review":
            raise ValueError("LLM requirements must start in needs_review.")
        return self


class RequirementPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: RequirementCategory | None = None
    requirement_type: Literal["required", "preferred", "informational", "hard_filter"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    importance: int | None = Field(default=None, ge=1, le=5)
    minimum_years: float | None = Field(default=None, ge=0, le=80)
    verification_status: Literal["needs_review", "confirmed", "rejected"] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class DuplicateResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm_duplicate", "not_duplicate", "dismiss"]


class JobMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_job_id: UUID
    expected_target_revision: int = Field(ge=1)
    expected_source_revision: int = Field(ge=1)
    field_selection: dict[str, Literal["target", "source"]] = Field(default_factory=dict)
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def confirmation_value(cls, value: str) -> str:
        if value != "MERGE JOBS":
            raise ValueError("confirmation must be MERGE JOBS.")
        return value


class CsvImportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    validate_only: bool = True


class RequirementExtractionResponse(BaseModel):
    requirements: list[dict[str, Any]]
    metadata: dict[str, Any]
