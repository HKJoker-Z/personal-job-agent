"""Application pipeline request contracts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ApplicationStage = Literal[
    "saved", "shortlisted", "preparing", "ready_to_apply", "applied", "assessment",
    "interview", "final_interview", "offer", "accepted", "rejected", "withdrawn", "closed",
]
Priority = Literal["low", "normal", "high", "urgent"]


def _utc(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Datetime values must include a timezone.")
    return value.astimezone(timezone.utc) if value else None


def _plain(value: str | None) -> str | None:
    if value is None:
        return None
    if re.search(r"<\s*/?\s*(script|iframe|object|embed|style|html|body)\b", value, re.I):
        raise ValueError("HTML and script content is not allowed.")
    return value


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    job_id: UUID
    source: str = Field(default="manual", max_length=80)
    priority: Priority = "normal"
    resume_version_id: UUID | None = None
    next_action_at: datetime | None = None
    expected_response_at: datetime | None = None
    _next_utc = field_validator("next_action_at")(_utc)
    _expected_utc = field_validator("expected_response_at")(_utc)


class ApplicationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    source: str | None = Field(default=None, max_length=80)
    priority: Priority | None = None
    next_action_at: datetime | None = None
    expected_response_at: datetime | None = None
    _next_utc = field_validator("next_action_at")(_utc)
    _expected_utc = field_validator("expected_response_at")(_utc)


class ApplicationTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    to_stage: ApplicationStage
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=4000)
    occurred_at: datetime | None = None
    _occurred_utc = field_validator("occurred_at")(_utc)
    _notes_plain = field_validator("notes")(_plain)


class ReopenApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def confirm(cls, value: str) -> str:
        if value != "REOPEN APPLICATION":
            raise ValueError("confirmation must be REOPEN APPLICATION.")
        return value


class ResumeLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resume_version_id: UUID
    expected_revision: int = Field(ge=1)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    content: str = Field(min_length=1, max_length=20_000)
    note_type: Literal["general", "recruiter", "interview", "follow_up", "outcome", "private"] = "general"
    _content_plain = field_validator("content")(_plain)


class NotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=1, max_length=20_000)
    note_type: Literal["general", "recruiter", "interview", "follow_up", "outcome", "private"] | None = None
    _content_plain = field_validator("content")(_plain)


TaskType = Literal[
    "review_job", "tailor_resume", "prepare_application", "submit_application", "follow_up",
    "assessment", "interview_preparation", "interview", "document_request", "other",
]
TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    application_id: UUID | None = None
    job_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10_000)
    task_type: TaskType = "other"
    status: TaskStatus = "pending"
    priority: Priority = "normal"
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    sort_order: int = Field(default=0, ge=0, le=10000)
    _due_utc = field_validator("due_at")(_utc)
    _reminder_utc = field_validator("reminder_at")(_utc)
    _description_plain = field_validator("description")(_plain)


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    application_id: UUID | None = None
    job_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    task_type: TaskType | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    _due_utc = field_validator("due_at")(_utc)
    _reminder_utc = field_validator("reminder_at")(_utc)
    _description_plain = field_validator("description")(_plain)


class ExpectedRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
