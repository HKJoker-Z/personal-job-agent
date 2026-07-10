from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


WORKFLOW_STATUSES = {"completed", "completed_with_warnings", "failed"}
STEP_STATUSES = {"pending", "running", "completed", "skipped", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_message(message: Any) -> str:
    text = str(message or "").strip()
    text = " ".join(text.split())
    return text[:240]


@dataclass
class WorkflowStep:
    key: str
    name: str
    status: str = "pending"
    message: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    _start_perf: float | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
        }


class AgentWorkflow:
    def __init__(self, workflow_id: str | None = None) -> None:
        self.workflow_id = workflow_id or str(uuid4())
        self.steps: list[WorkflowStep] = []
        self._steps_by_key: dict[str, WorkflowStep] = {}
        self.has_warnings = False
        self.has_failure = False

    def start_step(self, key: str, name: str, message: str = "") -> WorkflowStep:
        step = WorkflowStep(
            key=key,
            name=name,
            status="running",
            message=safe_message(message),
            started_at=utc_now(),
            _start_perf=time.perf_counter(),
        )
        self.steps.append(step)
        self._steps_by_key[key] = step
        return step

    def complete_step(self, key: str, message: str = "") -> WorkflowStep:
        return self._finish_step(key, "completed", message)

    def skip_step(self, key: str, name: str, message: str = "") -> WorkflowStep:
        step = self.start_step(key, name, message)
        return self._finish_step(step.key, "skipped", message)

    def fail_step(self, key: str, message: str = "") -> WorkflowStep:
        self.has_failure = True
        return self._finish_step(key, "failed", message)

    def add_warning(self) -> None:
        self.has_warnings = True

    def _finish_step(self, key: str, status: str, message: str = "") -> WorkflowStep:
        if status not in STEP_STATUSES:
            raise ValueError(f"Unsupported workflow step status: {status}")

        step = self._steps_by_key[key]
        step.status = status
        step.message = safe_message(message or step.message)
        step.completed_at = utc_now()
        start_perf = step._start_perf if step._start_perf is not None else time.perf_counter()
        step.duration_ms = max(0, int((time.perf_counter() - start_perf) * 1000))
        return step

    def status(self) -> str:
        if self.has_failure or any(step.status == "failed" for step in self.steps):
            return "failed"
        if self.has_warnings:
            return "completed_with_warnings"
        return "completed"

    def to_list(self) -> list[dict[str, Any]]:
        return [step.to_dict() for step in self.steps]


@dataclass
class WorkflowContext:
    workflow_id: str
    resume_filename: str | None = None
    resume_text: str = ""
    job_text: str = ""
    job_url: str | None = None
    rag_mode: str = "project"
    rag_top_k: int = 5
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    rag_sources: list[dict[str, Any]] = field(default_factory=list)
    llm_raw_response: str = ""
    normalized_result: dict[str, Any] = field(default_factory=dict)
    next_action: dict[str, Any] = field(default_factory=dict)
    application_id: int | None = None
    saved_to_history: bool = False
