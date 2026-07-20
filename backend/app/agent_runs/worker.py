"""Graceful Worker supervisor with Outbox dispatch, recovery, and heartbeat."""

from __future__ import annotations

import hashlib
import os
import signal
import socket
import subprocess
import sys
import threading
from datetime import timedelta

from sqlalchemy import select

from app import APP_VERSION
from app.agent_runs.outbox import run_dispatcher
from app.agent_runs.service import AgentRunService
from app.core.config import load_v2_settings
from app.db.models import AgentRun, AgentStep, WorkerHeartbeat, ensure_utc, utc_now
from app.db.session import session_factory


def _worker_id() -> str:
    return (os.getenv("AGENT_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}")[:120]


def embedded_dispatcher_enabled() -> bool:
    return os.getenv("OUTBOX_DISPATCH_IN_WORKER", "true").strip().lower() in {"1", "true", "yes", "on"}


def heartbeat(worker_id: str, status: str, active_tasks: int = 0) -> None:
    settings = load_v2_settings()
    db = session_factory()()
    try:
        value = db.get(WorkerHeartbeat, worker_id)
        if value is None:
            value = WorkerHeartbeat(
                worker_id=worker_id,
                hostname_hash=hashlib.sha256(socket.gethostname().encode()).hexdigest(),
                process_id=os.getpid(),
                status=status,
                concurrency=settings.worker_concurrency,
                active_tasks=active_tasks,
                worker_version=APP_VERSION,
            )
            db.add(value)
        else:
            value.status = status
            value.active_tasks = active_tasks
            value.last_heartbeat_at = utc_now()
            if status == "stopped":
                value.shutdown_at = utc_now()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def pulse(worker_id: str) -> None:
    """Refresh liveness without overwriting busy/active state from Actor processes."""
    db = session_factory()()
    try:
        value = db.get(WorkerHeartbeat, worker_id)
        if value is not None and value.status in {"ready", "busy"}:
            value.last_heartbeat_at = utc_now()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def recover_expired_steps() -> int:
    db = session_factory()()
    recovered = 0
    try:
        rows = db.execute(select(AgentRun.id, AgentRun.owner_user_id, AgentRun.revision).join(
            AgentStep, AgentStep.run_id == AgentRun.id,
        ).where(
            AgentRun.status == "running",
            AgentStep.status == "running",
            AgentStep.lease_expires_at < utc_now(),
        )).all()
        db.close()
        for run_id, owner_id, revision in rows:
            value_db = session_factory()()
            try:
                AgentRunService(value_db, owner_id).resume(run_id, revision)
                value_db.commit()
                recovered += 1
            except Exception:
                value_db.rollback()
            finally:
                value_db.close()
        return recovered
    finally:
        if db.is_active:
            db.close()


def _maintenance(worker_id: str, stop: threading.Event) -> None:
    settings = load_v2_settings()
    while not stop.is_set():
        pulse(worker_id)
        try:
            recover_expired_steps()
        except Exception:
            pass
        stop.wait(settings.worker_heartbeat_seconds)


def main() -> int:
    settings = load_v2_settings()
    worker_id = _worker_id()
    os.environ["AGENT_WORKER_ID"] = worker_id
    stop = threading.Event()
    heartbeat(worker_id, "starting")
    process = subprocess.Popen([
        sys.executable, "-m", "dramatiq", "app.agent_runs.tasks",
        "--processes", "1", "--threads", str(settings.worker_concurrency),
    ])
    heartbeat(worker_id, "ready")
    dispatcher = (
        threading.Thread(target=run_dispatcher, args=(worker_id, stop), daemon=True)
        if embedded_dispatcher_enabled()
        else None
    )
    maintainer = threading.Thread(target=_maintenance, args=(worker_id, stop), daemon=True)
    if dispatcher is not None:
        dispatcher.start()
    maintainer.start()

    def shutdown(_signum: int, _frame: object) -> None:
        heartbeat(worker_id, "stopping")
        stop.set()
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        return process.wait()
    finally:
        stop.set()
        if dispatcher is not None:
            dispatcher.join(timeout=5)
        maintainer.join(timeout=5)
        if process.poll() is None:
            process.kill()
        heartbeat(worker_id, "stopped")


if __name__ == "__main__":
    raise SystemExit(main())
