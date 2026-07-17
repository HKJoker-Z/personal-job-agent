"""Strict Agent Run and Step state machines."""

from __future__ import annotations


class IllegalTransition(RuntimeError):
    pass


RUN_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"waiting_for_approval", "completed", "failed", "retry_scheduled", "cancelled"},
    "waiting_for_approval": {"queued", "cancelled", "failed"},
    "retry_scheduled": {"queued", "cancelled", "dead_letter"},
    "failed": {"queued", "dead_letter", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "dead_letter": set(),
}

STEP_TRANSITIONS = {
    "pending": {"queued", "skipped", "cancelled", "waiting_for_approval"},
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "cancelled", "retry_scheduled", "waiting_for_approval"},
    "waiting_for_approval": {"queued", "completed", "failed", "cancelled"},
    "retry_scheduled": {"queued", "cancelled", "failed"},
    "failed": {"queued", "cancelled"},
    "completed": set(),
    "skipped": set(),
    "cancelled": set(),
}


def require_run_transition(current: str, target: str) -> None:
    if target == current or target not in RUN_TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"Agent Run cannot transition from {current} to {target}.")


def require_step_transition(current: str, target: str) -> None:
    if target == current or target not in STEP_TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"Agent Step cannot transition from {current} to {target}.")
