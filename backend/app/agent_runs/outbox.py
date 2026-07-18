"""Transactional Outbox dispatcher with Redis outage recovery and dead letters."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.agent_runs.definitions import validate_queue_payload
from app.agent_runs.service import AgentRunService
from app.db.models import AgentOutboxEvent, AgentRun, AgentStep, DeadLetterRecord, utc_now
from app.db.session import session_factory


def dispatch_batch(dispatcher_id: str, limit: int = 50) -> int:
    factory = session_factory()
    db = factory()
    try:
        now = utc_now()
        rows = db.scalars(select(AgentOutboxEvent).where(
            AgentOutboxEvent.status.in_(("pending", "failed")),
            AgentOutboxEvent.available_at <= now,
        ).order_by(AgentOutboxEvent.created_at).limit(limit).with_for_update(skip_locked=True)).all()
        ids = [row.id for row in rows]
        for row in rows:
            row.status = "publishing"
            row.locked_by = dispatcher_id[:120]
            row.locked_at = now
            row.attempt += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    published = 0
    for event_id in ids:
        attempt_db = factory()
        try:
            event = attempt_db.scalar(select(AgentOutboxEvent).where(
                AgentOutboxEvent.id == event_id,
            ).with_for_update())
            if event is None or event.status != "publishing":
                attempt_db.rollback()
                continue
            payload = validate_queue_payload(dict(event.payload))
            from app.agent_runs.tasks import run_agent_step

            run_agent_step.send(
                payload["run_id"], payload["step_id"], payload["workflow_type"],
                payload["attempt"], payload["correlation_id"],
            )
            event.status = "published"
            event.published_at = utc_now()
            event.locked_by = None
            event.locked_at = None
            event.safe_error_code = None
            attempt_db.commit()
            published += 1
        except Exception:
            attempt_db.rollback()
            _record_publish_failure(factory, event_id)
        finally:
            attempt_db.close()
    return published


def _record_publish_failure(factory: object, event_id: UUID) -> None:
    db = factory()
    try:
        event = db.scalar(select(AgentOutboxEvent).where(AgentOutboxEvent.id == event_id).with_for_update())
        if event is None:
            return
        event.locked_by = None
        event.locked_at = None
        event.safe_error_code = "redis_unavailable"
        if event.attempt >= event.max_attempts:
            event.status = "dead_letter"
            run = db.scalar(select(AgentRun).where(AgentRun.id == event.run_id).with_for_update())
            if run is not None:
                service = AgentRunService(db)
                if run.status == "queued":
                    service._transition_run(run, "running", "run.dispatch_started", "Queue dispatch recovery started.")
                if run.status == "running":
                    service._transition_run(run, "failed", "run.dispatch_failed", "Queue dispatch retry limit was exhausted.")
                if run.status in {"failed", "retry_scheduled"}:
                    service._transition_run(run, "dead_letter", "run.dead_letter", "Queue dispatch moved the Run to dead letter.")
                db.add(DeadLetterRecord(
                    owner_user_id=run.owner_user_id,
                    run_id=run.id,
                    step_id=event.step_id,
                    outbox_event_id=event.id,
                    reason_code="redis_publish_exhausted",
                    safe_error_summary="Redis queue publication failed after the configured retry limit.",
                    attempts=event.attempt,
                    safe_payload=dict(event.payload),
                ))
        else:
            event.status = "failed"
            delay = min(300, (2 ** min(event.attempt, 6)) + (int(event.id.hex[:2], 16) % 5))
            event.available_at = utc_now() + timedelta(seconds=delay)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def recover_stale_publications(stale_seconds: int = 300) -> int:
    db = session_factory()()
    try:
        cutoff = utc_now() - timedelta(seconds=stale_seconds)
        rows = db.scalars(select(AgentOutboxEvent).where(
            AgentOutboxEvent.status == "publishing",
            AgentOutboxEvent.locked_at < cutoff,
        ).with_for_update(skip_locked=True)).all()
        for row in rows:
            row.status = "failed"
            row.available_at = utc_now()
            row.locked_by = None
            row.locked_at = None
            row.safe_error_code = "dispatcher_interrupted"
        db.commit()
        return len(rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def recover_orphaned_deliveries(stale_seconds: int = 30) -> int:
    """Re-publish PostgreSQL-owned work after Redis loses transient queue state.

    Duplicate delivery is safe because the Worker claim is protected by row locks,
    the delivery attempt, and an execution lease.
    """
    db = session_factory()()
    try:
        cutoff = utc_now() - timedelta(seconds=stale_seconds)
        rows = db.scalars(select(AgentOutboxEvent).where(
            AgentOutboxEvent.status == "published",
            AgentOutboxEvent.published_at < cutoff,
            AgentOutboxEvent.step_id.in_(select(AgentStep.id).where(
                AgentStep.status.in_(("queued", "retry_scheduled")),
                AgentStep.scheduled_at <= utc_now(),
            )),
        ).with_for_update(skip_locked=True)).all()
        for row in rows:
            row.status = "pending"
            row.available_at = utc_now()
            row.published_at = None
            row.safe_error_code = "queue_delivery_recovered"
        db.commit()
        return len(rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_dispatcher(dispatcher_id: str, stop: object, interval_seconds: float = 1.0) -> None:
    while not stop.is_set():
        try:
            recover_stale_publications()
            recover_orphaned_deliveries()
            dispatch_batch(dispatcher_id)
        except Exception:
            pass
        stop.wait(interval_seconds)
