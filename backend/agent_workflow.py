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


def duration_from_ns(duration_ns: int) -> tuple[float, int]:
    safe_duration_ns = max(int(duration_ns), 0)
    duration_us = int(round(safe_duration_ns / 1_000))
    duration_ms = round(safe_duration_ns / 1_000_000, 3)
    return duration_ms, duration_us


@dataclass
class WorkflowStep:
    key: str
    name: str
    status: str = "pending"
    message: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    duration_us: int | None = None
    _started_perf_ns: int | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "duration_us": self.duration_us,
        }


class AgentWorkflow:
    def __init__(self, workflow_id: str | None = None) -> None:
        self.workflow_id = workflow_id or str(uuid4())
        self.steps: list[WorkflowStep] = []
        self._steps_by_key: dict[str, WorkflowStep] = {}
        self.has_warnings = False
        self.has_failure = False
        self._started_perf_ns = time.perf_counter_ns()
        self._completed_perf_ns: int | None = None

    def start_step(self, key: str, name: str, message: str = "") -> WorkflowStep:
        step = WorkflowStep(
            key=key,
            name=name,
            status="running",
            message=safe_message(message),
            started_at=utc_now(),
            _started_perf_ns=time.perf_counter_ns(),
        )
        self.steps.append(step)
        self._steps_by_key[key] = step
        return step

    def complete_step(self, key: str, message: str = "") -> WorkflowStep:
        return self._finish_step(key, "completed", message)

    def skip_step(self, key: str, name: str, message: str = "") -> WorkflowStep:
        now = utc_now()
        step = WorkflowStep(
            key=key,
            name=name,
            status="skipped",
            message=safe_message(message),
            started_at=now,
            completed_at=now,
            duration_ms=0.0,
            duration_us=0,
        )
        self.steps.append(step)
        self._steps_by_key[key] = step
        return step

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
        start_perf_ns = (
            step._started_perf_ns
            if step._started_perf_ns is not None
            else time.perf_counter_ns()
        )
        end_perf_ns = time.perf_counter_ns()
        step.duration_ms, step.duration_us = duration_from_ns(end_perf_ns - start_perf_ns)
        return step

    def finish(self) -> None:
        if self._completed_perf_ns is None:
            self._completed_perf_ns = time.perf_counter_ns()

    def workflow_duration(self) -> dict[str, float | int]:
        end_perf_ns = self._completed_perf_ns or time.perf_counter_ns()
        duration_ms, duration_us = duration_from_ns(end_perf_ns - self._started_perf_ns)
        return {
            "workflow_duration_ms": duration_ms,
            "workflow_duration_us": duration_us,
        }

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
    security_filtered_rag_sources: list[dict[str, Any]] = field(default_factory=list)
    rag_sources: list[dict[str, Any]] = field(default_factory=list)
    sanitized_resume_text: str = ""
    sanitized_job_text: str = ""
    safe_prompt: str = ""
    security_scan: dict[str, Any] = field(default_factory=dict)
    security_status: str = "passed"
    llm_raw_response: str = ""
    normalized_result: dict[str, Any] = field(default_factory=dict)
    next_action: dict[str, Any] = field(default_factory=dict)
    application_id: int | None = None
    saved_to_history: bool = False
