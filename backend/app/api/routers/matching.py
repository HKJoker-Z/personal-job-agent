"""Authenticated matching and ranking endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.api.dependencies import CurrentUser, DbSession
from app.matching.schemas import MatchRequest, RankRequest
from app.matching.service import MatchConflict, MatchNotFound, MatchingService


router = APIRouter(tags=["matching"])


def _service(db: DbSession, user: CurrentUser) -> MatchingService:
    return MatchingService(db, user.id)


def _raise(exc: Exception) -> None:
    if isinstance(exc, MatchNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, MatchConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="Matching request is invalid.") from exc


@router.post("/api/jobs/rank")
def rank_jobs(payload: RankRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).rank(payload.model_dump())
    except (MatchConflict, MatchNotFound, ValueError) as exc:
        _raise(exc)


@router.post("/api/jobs/{job_id}/match")
def match_job(job_id: UUID, payload: MatchRequest, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).run(job_id, **payload.model_dump())
    except (MatchConflict, MatchNotFound, ValueError) as exc:
        _raise(exc)


@router.get("/api/jobs/{job_id}/matches")
def match_history(job_id: UUID, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    try:
        return _service(db, user).list(job_id)
    except MatchNotFound as exc:
        _raise(exc)

@router.get("/api/jobs/{job_id}/latest-match")
def latest_match(job_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).latest(job_id)
    except MatchNotFound as exc:
        _raise(exc)


@router.get("/api/jobs/{job_id}/matches/{analysis_id}")
def get_match(job_id: UUID, analysis_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).get(job_id, analysis_id)
    except MatchNotFound as exc:
        _raise(exc)


@router.get("/api/job-rank-runs")
def rank_runs(
    db: DbSession, user: CurrentUser,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, object]]:
    return _service(db, user).rank_runs(offset, limit)


@router.get("/api/job-rank-runs/{run_id}")
def rank_run(run_id: UUID, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return _service(db, user).rank_run(run_id)
    except MatchNotFound as exc:
        _raise(exc)
