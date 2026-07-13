"""Ownership-scoped persistence for immutable match analyses and rank runs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    JobMatchAnalysis,
    JobMatchDimension,
    JobMatchEvidence,
    JobRankItem,
    JobRankRun,
)


class MatchingRepository:
    def __init__(self, db: Session):
        self.db = db

    def reusable(self, owner_id: UUID, job_id: UUID, fingerprint: str) -> JobMatchAnalysis | None:
        return self.db.scalar(
            select(JobMatchAnalysis).where(
                JobMatchAnalysis.owner_user_id == owner_id,
                JobMatchAnalysis.job_id == job_id,
                JobMatchAnalysis.input_fingerprint == fingerprint,
                JobMatchAnalysis.status == "completed",
            ).order_by(JobMatchAnalysis.created_at.desc()).limit(1)
        )

    def analysis(self, owner_id: UUID, job_id: UUID, analysis_id: UUID) -> JobMatchAnalysis | None:
        return self.db.scalar(select(JobMatchAnalysis).where(
            JobMatchAnalysis.id == analysis_id,
            JobMatchAnalysis.owner_user_id == owner_id,
            JobMatchAnalysis.job_id == job_id,
        ))

    def analysis_by_id(self, owner_id: UUID, analysis_id: UUID) -> JobMatchAnalysis | None:
        return self.db.scalar(select(JobMatchAnalysis).where(
            JobMatchAnalysis.id == analysis_id,
            JobMatchAnalysis.owner_user_id == owner_id,
        ))

    def analyses(self, owner_id: UUID, job_id: UUID) -> list[JobMatchAnalysis]:
        return list(self.db.scalars(select(JobMatchAnalysis).where(
            JobMatchAnalysis.owner_user_id == owner_id,
            JobMatchAnalysis.job_id == job_id,
        ).order_by(JobMatchAnalysis.created_at.desc())))

    def latest(self, owner_id: UUID, job_id: UUID) -> JobMatchAnalysis | None:
        return self.db.scalar(select(JobMatchAnalysis).where(
            JobMatchAnalysis.owner_user_id == owner_id,
            JobMatchAnalysis.job_id == job_id,
            JobMatchAnalysis.status == "completed",
        ).order_by(JobMatchAnalysis.created_at.desc()).limit(1))

    def dimensions(self, analysis_id: UUID) -> list[JobMatchDimension]:
        return list(self.db.scalars(select(JobMatchDimension).where(
            JobMatchDimension.analysis_id == analysis_id,
        ).order_by(JobMatchDimension.sort_order)))

    def evidence(self, analysis_id: UUID) -> list[JobMatchEvidence]:
        return list(self.db.scalars(select(JobMatchEvidence).where(
            JobMatchEvidence.analysis_id == analysis_id,
        ).order_by(JobMatchEvidence.dimension, JobMatchEvidence.created_at)))

    def rank_runs(self, owner_id: UUID, offset: int, limit: int) -> list[JobRankRun]:
        return list(self.db.scalars(select(JobRankRun).where(
            JobRankRun.owner_user_id == owner_id,
        ).order_by(JobRankRun.created_at.desc(), JobRankRun.id).offset(offset).limit(limit)))

    def rank_run(self, owner_id: UUID, run_id: UUID) -> JobRankRun | None:
        return self.db.scalar(select(JobRankRun).where(
            JobRankRun.id == run_id, JobRankRun.owner_user_id == owner_id,
        ))

    def rank_items(self, run_id: UUID) -> list[JobRankItem]:
        return list(self.db.scalars(select(JobRankItem).where(
            JobRankItem.rank_run_id == run_id,
        ).order_by(JobRankItem.rank_position)))
