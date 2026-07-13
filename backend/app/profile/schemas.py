"""Validated Career Profile request schemas."""

from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


VerificationStatus = Literal["draft", "needs_review", "confirmed"]


def _url(value: str) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must use http or https.")
    return value


class ProfileUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    revision: int = Field(ge=1)
    headline: str = Field(default="", max_length=240)
    professional_summary: str = Field(default="", max_length=8000)
    current_location: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=80)
    public_email: EmailStr | None = None
    website: str = Field(default="", max_length=500)
    linkedin_url: str = Field(default="", max_length=500)
    github_url: str = Field(default="", max_length=500)

    _validate_website = field_validator("website", "linkedin_url", "github_url")(_url)


class ProfileItemPayload(BaseModel):
    model_config = {"extra": "forbid"}
    company: str | None = Field(default=None, max_length=240)
    role_title: str | None = Field(default=None, max_length=240)
    location: str = Field(default="", max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str = Field(default="", max_length=8000)
    achievements: list[str] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=100)
    source_type: str = Field(default="manual", max_length=30)
    institution: str | None = Field(default=None, max_length=240)
    degree: str = Field(default="", max_length=200)
    field_of_study: str = Field(default="", max_length=200)
    grade: str = Field(default="", max_length=120)
    name: str | None = Field(default=None, max_length=240)
    role: str = Field(default="", max_length=200)
    technologies: list[str] = Field(default_factory=list, max_length=100)
    metrics: list[str] = Field(default_factory=list, max_length=50)
    project_url: str = Field(default="", max_length=500)
    repository_url: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=120)
    proficiency: str = Field(default="", max_length=80)
    years_experience: float | None = Field(default=None, ge=0, le=100)
    last_used_at: date | None = None
    language: str | None = Field(default=None, max_length=120)
    issuer: str = Field(default="", max_length=240)
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str = Field(default="", max_length=200)
    credential_url: str = Field(default="", max_length=500)
    verification_status: VerificationStatus = "draft"
    sort_order: int = Field(default=0, ge=0, le=100000)

    _validate_urls = field_validator("project_url", "repository_url", "credential_url")(_url)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProfileItemPayload":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date.")
        if self.is_current and self.end_date is not None:
            raise ValueError("A current experience cannot have an end_date.")
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date cannot be before issue_date.")
        return self


class ProfilePreferencePayload(BaseModel):
    model_config = {"extra": "forbid"}
    target_roles: list[str] = Field(default_factory=list, max_length=50)
    target_locations: list[str] = Field(default_factory=list, max_length=50)
    employment_types: list[str] = Field(default_factory=list, max_length=20)
    work_modes: list[str] = Field(default_factory=list, max_length=20)
    minimum_salary: int | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="", max_length=8)
    salary_period: Literal["hourly", "monthly", "annual"] = "annual"
    work_authorization: str = Field(default="", max_length=240)
    sponsorship_required: bool | None = None
    willing_to_relocate: bool | None = None
    excluded_role_keywords: list[str] = Field(default_factory=list, max_length=100)
