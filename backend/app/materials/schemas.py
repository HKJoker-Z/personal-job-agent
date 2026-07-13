"""Validated contracts for Package and Material review operations."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _plain(value: str) -> str:
    if re.search(r"<\s*/?\s*(script|iframe|object|embed|style|html|body)\b", value, re.I):
        raise ValueError("HTML and script content is not allowed.")
    return value


class PackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_resume_version_id: UUID
    match_analysis_id: UUID
    title: str = Field(min_length=1, max_length=240)
    _title_plain = field_validator("title")(_plain)


class PackagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    _title_plain = field_validator("title")(_plain)


class PackageRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class PackageApprove(PackageRevision):
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def confirm(cls, value: str) -> str:
        if value != "APPROVE PACKAGE":
            raise ValueError("confirmation must be APPROVE PACKAGE.")
        return value


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force_new: bool = False


class AnswerQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    question: str = Field(min_length=1, max_length=2000)
    _question_plain = field_validator("question")(_plain)


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[AnswerQuestion] = Field(min_length=1, max_length=20)


class MaterialEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_active_version_id: UUID
    content_text: str = Field(default="", max_length=50_000)
    content_json: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = Field(default="User edit", max_length=500)
    _text_plain = field_validator("content_text")(_plain)


class MaterialReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["request_changes", "approve", "reject"]
    notes: str = Field(default="", max_length=10_000)
    _notes_plain = field_validator("notes")(_plain)


class MaterialFinalize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def confirm(cls, value: str) -> str:
        if value != "FINALIZE MATERIAL":
            raise ValueError("confirmation must be FINALIZE MATERIAL.")
        return value


class EvidenceConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def confirm(cls, value: str) -> str:
        if value != "CONFIRM CLAIM":
            raise ValueError("confirmation must be CONFIRM CLAIM.")
        return value
