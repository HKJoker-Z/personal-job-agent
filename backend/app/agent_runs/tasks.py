"""Dramatiq actors; every argument is an approved safe identifier."""

from __future__ import annotations

import os
import socket
import threading

import dramatiq

from app.agent_runs.broker import broker as _broker  # noqa: F401
from app.agent_runs.definitions import validate_queue_payload
from app.agent_runs.workflow import execute_delivery
from app.agent_runs.worker import heartbeat


_active_lock = threading.Lock()
_active_tasks = 0


def current_worker_id() -> str:
    configured = os.getenv("AGENT_WORKER_ID", "").strip()
    if configured:
        return configured[:120]
    return f"{socket.gethostname()}:{os.getpid()}"[:120]


@dramatiq.actor(queue_name="agent-workflows", max_retries=0, time_limit=900_000)
def run_agent_step(
    run_id: str, step_id: str, workflow_type: str, attempt: int, correlation_id: str,
) -> None:
    payload = validate_queue_payload({
        "run_id": run_id,
        "step_id": step_id,
        "workflow_type": workflow_type,
        "attempt": attempt,
        "correlation_id": correlation_id,
    })
    global _active_tasks
    worker_id = current_worker_id()
    with _active_lock:
        _active_tasks += 1
        active = _active_tasks
    heartbeat(worker_id, "busy", active)
    try:
        execute_delivery(payload, worker_id)
    finally:
        with _active_lock:
            _active_tasks = max(_active_tasks - 1, 0)
            active = _active_tasks
        heartbeat(worker_id, "busy" if active else "ready", active)
