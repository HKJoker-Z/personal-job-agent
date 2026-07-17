"""Versioned workflow definition and queue payload allow-list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


WORKFLOW_TYPE = "generate_application_package"


@dataclass(frozen=True)
class StepDefinition:
    key: str
    uses_model: bool = False


APPLICATION_PACKAGE_STEPS = (
    StepDefinition("validate_request"),
    StepDefinition("snapshot_profile"),
    StepDefinition("snapshot_job"),
    StepDefinition("load_resume"),
    StepDefinition("run_or_reuse_match"),
    StepDefinition("select_grounded_evidence"),
    StepDefinition("generate_tailored_resume", True),
    StepDefinition("validate_tailored_resume"),
    StepDefinition("request_resume_approval"),
    StepDefinition("wait_resume_approval"),
    StepDefinition("generate_cover_letter", True),
    StepDefinition("validate_cover_letter"),
    StepDefinition("request_cover_letter_approval"),
    StepDefinition("wait_cover_letter_approval"),
    StepDefinition("generate_application_answers", True),
    StepDefinition("validate_application_answers"),
    StepDefinition("build_package_summary"),
    StepDefinition("request_package_approval"),
    StepDefinition("wait_package_approval"),
    StepDefinition("finalize_run"),
)

STEP_BY_KEY = {item.key: item for item in APPLICATION_PACKAGE_STEPS}
APPROVAL_REQUEST_STEPS = {
    "request_resume_approval": ("wait_resume_approval", "resume_draft"),
    "request_cover_letter_approval": ("wait_cover_letter_approval", "cover_letter_draft"),
    "request_package_approval": ("wait_package_approval", "application_package"),
}
MODEL_STEPS = {item.key for item in APPLICATION_PACKAGE_STEPS if item.uses_model}

QUEUE_PAYLOAD_KEYS = {"run_id", "step_id", "workflow_type", "attempt", "correlation_id"}


def validate_queue_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reject any queue payload containing business text, credentials, or unknown fields."""
    if set(payload) != QUEUE_PAYLOAD_KEYS:
        raise ValueError("Queue payload must contain only the approved safe identifiers.")
    normalized = {
        "run_id": str(payload["run_id"]),
        "step_id": str(payload["step_id"]),
        "workflow_type": str(payload["workflow_type"]),
        "attempt": int(payload["attempt"]),
        "correlation_id": str(payload["correlation_id"]),
    }
    if normalized["workflow_type"] != WORKFLOW_TYPE or normalized["attempt"] < 0:
        raise ValueError("Queue payload has an invalid workflow type or attempt.")
    for key in ("run_id", "step_id", "correlation_id"):
        value = normalized[key]
        if not value or len(value) > 64:
            raise ValueError("Queue identifier is invalid.")
    return normalized
