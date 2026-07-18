"""Validated API contracts for Agent Runs and approval decisions."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    workflow_type: Literal["generate_application_package"] = "generate_application_package"
    package_id: UUID | None = None
    application_id: UUID | None = None
    job_id: UUID | None = None
    resume_version_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    force_new: bool = False
    force_confirmation: str | None = None

    @model_validator(mode="after")
    def validate_refs(self) -> "AgentRunCreate":
        if self.package_id is None:
            raise ValueError("package_id is required for generate_application_package.")
        if self.force_new and self.force_confirmation != "FORCE NEW":
            raise ValueError("force_confirmation must be FORCE NEW.")
        return self


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class RetryRequest(RevisionRequest):
    acknowledge_possible_cost: bool = False


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Literal["approve", "reject"]
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    safe_reason: str = Field(default="", max_length=500)
