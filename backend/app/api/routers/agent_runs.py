"""Authenticated Agent Run, SSE progress, and Approval APIs."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.agent_runs.schemas import AgentRunCreate, ApprovalDecisionRequest, RetryRequest, RevisionRequest
from app.agent_runs.sse import (
    ConnectionLimiterUnavailable,
    ConnectionLimitReached,
    SSEConnectionLimiter,
)
from app.agent_runs.service import (
    AgentBudgetExceeded,
    AgentConflict,
    AgentLimitExceeded,
    AgentNotFound,
    AgentRunService,
)
from app.api.dependencies import CurrentUser, DbSession
from app.core.config import load_v2_settings
from app.db.models import AgentRunEvent
from app.db.session import session_factory


router = APIRouter(tags=["agent-runs"])


def _raise(exc: Exception) -> None:
    if isinstance(exc, AgentNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AgentLimitExceeded):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, (AgentConflict, AgentBudgetExceeded)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="Agent workflow request is invalid.") from exc


@router.get("/api/agent-runs")
def list_runs(
    db: DbSession, user: CurrentUser,
    run_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, object]]:
    return AgentRunService(db, user.id).list(run_status, limit)


@router.post("/api/agent-runs", status_code=status.HTTP_202_ACCEPTED)
def create_run(
    payload: AgentRunCreate, db: DbSession, user: CurrentUser,
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    key = idempotency_header or payload.idempotency_key
    if not key or not 8 <= len(key) <= 160:
        raise HTTPException(status_code=400, detail="A valid Idempotency-Key is required.")
    try:
        value, reused = AgentRunService(db, user.id).create(payload.model_dump(), key)
        return {"run": value, "reused": reused}
    except (AgentNotFound, AgentConflict, AgentBudgetExceeded, AgentLimitExceeded) as exc:
        _raise(exc)


@router.get("/api/agent-runs/{run_id}")
def get_run(run_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).run(run_id)
    except AgentNotFound as exc:
        _raise(exc)


@router.post("/api/agent-runs/{run_id}/cancel")
def cancel_run(run_id: UUID, payload: RevisionRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).cancel(run_id, payload.expected_revision)
    except (AgentNotFound, AgentConflict) as exc:
        _raise(exc)


@router.post("/api/agent-runs/{run_id}/retry")
def retry_run(run_id: UUID, payload: RetryRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).retry(
            run_id, payload.expected_revision, payload.acknowledge_possible_cost,
        )
    except (AgentNotFound, AgentConflict) as exc:
        _raise(exc)


@router.post("/api/agent-runs/{run_id}/resume")
def resume_run(run_id: UUID, payload: RevisionRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).resume(run_id, payload.expected_revision)
    except (AgentNotFound, AgentConflict) as exc:
        _raise(exc)


@router.get("/api/agent-runs/{run_id}/steps")
def list_steps(run_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return AgentRunService(db, user.id).steps(run_id)
    except AgentNotFound as exc:
        _raise(exc)


@router.get("/api/agent-runs/{run_id}/events")
def list_events(
    run_id: UUID, db: DbSession, user: CurrentUser,
    after_id: int = Query(default=0, ge=0), limit: int = Query(default=500, ge=1, le=1000),
) -> list[dict[str, object]]:
    try:
        return AgentRunService(db, user.id).events(run_id, after_id, limit)
    except AgentNotFound as exc:
        _raise(exc)


@router.get("/api/agent-runs/{run_id}/events/stream")
def stream_events(
    run_id: UUID, db: DbSession, user: CurrentUser,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    try:
        AgentRunService(db, user.id).run(run_id)
    except AgentNotFound as exc:
        _raise(exc)
    try:
        cursor = max(int(last_event_id or "0"), 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer.") from exc
    settings = load_v2_settings()
    limiter = SSEConnectionLimiter(settings)
    try:
        limiter.acquire(user.id)
    except ConnectionLimitReached as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ConnectionLimiterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    owner_id = user.id

    async def generate():
        current = cursor
        idle = 0
        try:
            yield "retry: 2000\n\n"
            while True:
                stream_db = session_factory()()
                try:
                    events = AgentRunService(stream_db, owner_id).events(run_id, current, 100)
                    run = AgentRunService(stream_db, owner_id).run(run_id)
                    stream_db.rollback()
                finally:
                    stream_db.close()
                if events:
                    idle = 0
                    for event in events:
                        current = int(event["id"])
                        data = json.dumps(event, separators=(",", ":"), ensure_ascii=True)
                        yield f"id: {current}\nevent: {event['event_type']}\ndata: {data}\n\n"
                else:
                    idle += 1
                    if idle * 0.5 >= settings.sse_heartbeat_seconds:
                        yield f": heartbeat {current}\n\n"
                        idle = 0
                        limiter.touch(owner_id)
                    if run["status"] in {"completed", "failed", "cancelled", "dead_letter"}:
                        yield f"event: stream.complete\ndata: {{\"last_event_id\":{current}}}\n\n"
                        return
                await asyncio.sleep(0.5)
        finally:
            limiter.release(owner_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/approvals")
def list_approvals(
    db: DbSession, user: CurrentUser,
    approval_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, object]]:
    return AgentRunService(db, user.id).approvals(approval_status, limit)


@router.get("/api/approvals/{approval_id}")
def get_approval(approval_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).approval(approval_id)
    except AgentNotFound as exc:
        _raise(exc)


@router.post("/api/approvals/{approval_id}/decide")
def decide_approval(
    approval_id: UUID, payload: ApprovalDecisionRequest,
    db: DbSession, user: CurrentUser,
) -> dict[str, object]:
    try:
        return AgentRunService(db, user.id).decide_approval(
            approval_id, payload.decision, payload.expected_revision,
            payload.idempotency_key, payload.safe_reason,
        )
    except (AgentNotFound, AgentConflict) as exc:
        _raise(exc)
