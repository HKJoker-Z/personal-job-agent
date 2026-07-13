"""Resume request and structured content schemas."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ResumeSection(BaseModel):
    type: Literal["experience", "education", "projects", "skills", "languages", "certifications", "custom"]
    title: str = Field(default="", max_length=200)
    items: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class ResumeContent(BaseModel):
    schema_version: Literal[1] = 1
    header: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=12000)
    sections: list[ResumeSection] = Field(default_factory=list, max_length=50)


class ResumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    language: str = Field(default="en", min_length=2, max_length=20)
    target_role: str = Field(default="", max_length=240)


class ResumeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    language: str | None = Field(default=None, min_length=2, max_length=20)
    target_role: str | None = Field(default=None, max_length=240)


class ResumeVersionCreate(BaseModel):
    parent_version_id: UUID | None = None
    content: ResumeContent
    change_summary: str = Field(default="", max_length=500)


class ResumeImportConfirmation(BaseModel):
    resume_id: UUID
    version_id: UUID
    action: Literal["finalize", "copy_confirmed_to_profile"]
    profile_revision: int | None = Field(default=None, ge=1)
