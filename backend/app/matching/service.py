"""Transactions and ownership rules for explainable matching and ranking."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    CareerProfile,
    Job,
    JobMatchAnalysis,
    JobMatchDimension,
    JobMatchEvidence,
    JobRankItem,
    JobRankRun,
    JobRequirement,
    ProfileRevision,
    Resume,
    ResumeVersion,
    utc_now,
)
from app.db.repositories.auth import AuthRepository
from app.jobs.repository import JobRepository
from app.matching.engine import SCORING_VERSION, score_match
from app.matching.repository import MatchingRepository
from app.matching.schemas import DEFAULT_WEIGHTS


class MatchNotFound(RuntimeError):
    pass


class MatchConflict(RuntimeError):
    pass


def _json(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _columns(value: object, excluded: set[str] | None = None) -> dict[str, object]:
    return {
        column.name: _json(getattr(value, column.name))
        for column in value.__table__.columns
        if column.name not in (excluded or set())
    }


class MatchingService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id
        self.repository = MatchingRepository(db)

    def run(
        self,
        job_id: UUID,
        profile_revision: int | None = None,
        resume_version_id: UUID | None = None,
        weight_config: dict[str, float] | None = None,
        force_new: bool = False,
    ) -> dict[str, object]:
        started = time.monotonic()
        job = self._job(job_id)
        profile, revision = self._profile_revision(profile_revision)
        resume = self._resume_version(resume_version_id) if resume_version_id else None
        weights = dict(weight_config or DEFAULT_WEIGHTS)
        fingerprint = hashlib.sha256(json.dumps({
            "job": str(job.id), "job_revision": job.revision,
            "profile": str(profile.id), "profile_revision": revision.revision_number,
            "resume": str(resume.id) if resume else None,
            "resume_version": resume.version_number if resume else None,
            "weights": weights, "scoring": SCORING_VERSION,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if not force_new:
            existing = self.repository.reusable(self.owner_id, job.id, fingerprint)
            if existing:
                return self._detail(existing, reused=True)
        requirements = list(self.db.scalars(select(JobRequirement).where(
            JobRequirement.owner_user_id == self.owner_id,
            JobRequirement.job_id == job.id,
        ).order_by(JobRequirement.sort_order, JobRequirement.id)))
        result = score_match(
            revision.snapshot,
            revision.revision_number,
            _columns(job, {"description"}),
            [_columns(item, {"description", "evidence_text", "owner_user_id"}) for item in requirements],
            weights,
        )
        analysis = JobMatchAnalysis(
            owner_user_id=self.owner_id,
            job_id=job.id,
            profile_id=profile.id,
            profile_revision=revision.revision_number,
            resume_version_id=resume.id if resume else None,
            job_revision=job.revision,
            scoring_version=result["scoring_version"],
            synonym_map_version=result["synonym_map_version"],
            input_fingerprint=fingerprint,
            weight_config=result["weight_config"],
            overall_score=result["overall_score"],
            hard_filter_status=result["hard_filter_status"],
            recommendation=result["recommendation"],
            preparation_effort=result["preparation_effort"],
            status="completed",
            completed_at=utc_now(),
            created_by_user_id=self.owner_id,
        )
        self.db.add(analysis)
        self.db.flush()
        for item in result["dimensions"]:
            self.db.add(JobMatchDimension(analysis_id=analysis.id, **item))
        for item in result["evidence"]:
            values = dict(item)
            values.pop("hard_filter_result", None)
            if values.get("requirement_id"):
                values["requirement_id"] = UUID(str(values["requirement_id"]))
            self.db.add(JobMatchEvidence(analysis_id=analysis.id, **values))
        self.db.flush()
        AuthRepository(self.db).audit(
            "job.match.completed", user_id=self.owner_id, resource_type="job_match_analysis",
            resource_id=str(analysis.id), safe_metadata={
                "scoring_version": SCORING_VERSION,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "dimension_count": len(result["dimensions"]),
                "evidence_count": len(result["evidence"]),
                "hard_filter_status": analysis.hard_filter_status,
                "overall_score": analysis.overall_score,
            },
        )
        return self._detail(analysis, reused=False)

    def list(self, job_id: UUID) -> list[dict[str, object]]:
        self._job(job_id)
        return [self._summary(item) for item in self.repository.analyses(self.owner_id, job_id)]

    def get(self, job_id: UUID, analysis_id: UUID) -> dict[str, object]:
        self._job(job_id)
        analysis = self.repository.analysis(self.owner_id, job_id, analysis_id)
        if not analysis:
            raise MatchNotFound("Match Analysis not found.")
        return self._detail(analysis)

    def latest(self, job_id: UUID) -> dict[str, object]:
        self._job(job_id)
        analysis = self.repository.latest(self.owner_id, job_id)
        if not analysis:
            raise MatchNotFound("Match Analysis not found.")
        return self._detail(analysis)

    def rank(self, values: dict[str, object]) -> dict[str, object]:
        jobs = self._rank_jobs(values.get("job_ids"), dict(values.get("filters") or {}))
        if not jobs:
            raise MatchConflict("No owned Jobs match the ranking selection.")
        analyses: list[tuple[Job, dict[str, object]]] = []
        for job in jobs:
            analysis = self.run(
                job.id, values.get("profile_revision"), values.get("resume_version_id"),
                values.get("weight_config"), False,
            )
            analyses.append((job, analysis))
        deadline_weight = float(values.get("deadline_factor") or 0)
        priority_weight = float(values.get("user_priority_factor") or 0)
        effort_weight = float(values.get("preparation_effort_factor") or 0)
        scored: list[dict[str, object]] = []
        now = datetime.now(timezone.utc)
        priority_values = {"low": -1.0, "normal": 0.0, "high": 0.5, "urgent": 1.0}
        effort_values = {"low": 1.0, "medium": 0.0, "high": -1.0}
        for job, analysis in analyses:
            deadline = job.application_deadline
            if deadline and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            days = (deadline - now).total_seconds() / 86400 if deadline else None
            deadline_value = 1.0 if days is not None and 0 <= days <= 7 else 0.5 if days is not None and days <= 30 else 0.0
            application = self.db.scalar(select(Application).where(
                Application.owner_user_id == self.owner_id,
                Application.job_id == job.id,
                Application.archived_at.is_(None),
            ))
            priority_value = priority_values.get(application.priority if application else "normal", 0.0)
            effort_value = effort_values[str(analysis["preparation_effort"])]
            hard_penalty = -25.0 if analysis["hard_filter_status"] == "failed" else -5.0 if analysis["hard_filter_status"] == "warning" else 0.0
            score = max(0.0, min(100.0, float(analysis["overall_score"]) + deadline_value * deadline_weight + priority_value * priority_weight + effort_value * effort_weight + hard_penalty))
            evidence = analysis["evidence"]
            strengths = [item["dimension"] for item in evidence if item["evidence_kind"] == "matched"][:3]
            gaps = [item["dimension"] for item in evidence if item["evidence_kind"] in {"missing", "unknown"}][:3]
            scored.append({
                "job": job, "analysis": analysis, "rank_score": round(score, 2),
                "deadline_factor": deadline_value * deadline_weight,
                "user_priority_factor": priority_value * priority_weight,
                "preparation_effort_factor": effort_value * effort_weight,
                "reason_summary": {"primary_reasons": strengths, "primary_gaps": gaps},
            })
        scored.sort(key=lambda item: (
            item["analysis"]["hard_filter_status"] == "failed",
            -float(item["rank_score"]), str(item["job"].id),
        ))
        run = JobRankRun(
            owner_user_id=self.owner_id, scoring_version=SCORING_VERSION,
            filter_config={"job_ids": [str(job.id) for job in jobs], "filters": values.get("filters") or {}},
            weight_config=values.get("weight_config") or DEFAULT_WEIGHTS,
            job_count=len(scored),
        )
        self.db.add(run)
        self.db.flush()
        for position, item in enumerate(scored, 1):
            self.db.add(JobRankItem(
                rank_run_id=run.id, job_id=item["job"].id,
                analysis_id=UUID(str(item["analysis"]["id"])), rank_position=position,
                rank_score=item["rank_score"], deadline_factor=item["deadline_factor"],
                user_priority_factor=item["user_priority_factor"],
                preparation_effort_factor=item["preparation_effort_factor"],
                reason_summary=item["reason_summary"],
            ))
        self.db.flush()
        AuthRepository(self.db).audit(
            "job.rank.completed", user_id=self.owner_id, resource_type="job_rank_run",
            resource_id=str(run.id), safe_metadata={"job_count": len(scored), "scoring_version": SCORING_VERSION},
        )
        return self.rank_run(run.id)

    def rank_runs(self, offset: int, limit: int) -> list[dict[str, object]]:
        return [_columns(item, {"owner_user_id", "filter_config"}) for item in self.repository.rank_runs(self.owner_id, offset, limit)]

    def rank_run(self, run_id: UUID) -> dict[str, object]:
        run = self.repository.rank_run(self.owner_id, run_id)
        if not run:
            raise MatchNotFound("Job Rank Run not found.")
        items = []
        for item in self.repository.rank_items(run.id):
            job = self._job(item.job_id)
            analysis = self.repository.analysis_by_id(self.owner_id, item.analysis_id)
            if not analysis:
                raise MatchNotFound("Ranked Match Analysis not found.")
            items.append({
                **_columns(item, {"rank_run_id"}),
                "job": {"id": str(job.id), "company_name": job.company_name, "title": job.title, "application_deadline": _json(job.application_deadline)},
                "overall_score": analysis.overall_score,
                "hard_filter_status": analysis.hard_filter_status,
                "recommendation": analysis.recommendation,
                "preparation_effort": analysis.preparation_effort,
            })
        return {**_columns(run, {"owner_user_id"}), "items": items}

    def _rank_jobs(self, job_ids: object, filters: dict[str, object]) -> list[Job]:
        if job_ids:
            ids = list(dict.fromkeys(UUID(str(item)) for item in job_ids))
            jobs = list(self.db.scalars(select(Job).where(
                Job.owner_user_id == self.owner_id, Job.id.in_(ids), Job.archived_at.is_(None),
            ).order_by(Job.id)))
            if len(jobs) != len(ids):
                raise MatchNotFound("One or more Jobs were not found.")
            return jobs
        clean = dict(filters)
        clean["archived"] = False
        return JobRepository(self.db).list(self.owner_id, clean, 0, 100, "created_at")[0]

    def _profile_revision(self, requested: int | None) -> tuple[CareerProfile, ProfileRevision]:
        profile = self.db.scalar(select(CareerProfile).where(CareerProfile.user_id == self.owner_id))
        if not profile:
            raise MatchConflict("Career Profile is required.")
        statement = select(ProfileRevision).where(ProfileRevision.profile_id == profile.id)
        if requested:
            statement = statement.where(ProfileRevision.revision_number == requested)
        else:
            statement = statement.order_by(ProfileRevision.revision_number.desc()).limit(1)
        revision = self.db.scalar(statement)
        if not revision:
            raise MatchConflict("A saved Profile Revision is required before matching.")
        return profile, revision

    def _job(self, job_id: UUID) -> Job:
        job = self.db.scalar(select(Job).where(
            Job.id == job_id, Job.owner_user_id == self.owner_id, Job.archived_at.is_(None),
        ))
        if not job:
            raise MatchNotFound("Job not found.")
        return job

    def _resume_version(self, version_id: UUID) -> ResumeVersion:
        version = self.db.scalar(select(ResumeVersion).join(
            Resume, Resume.id == ResumeVersion.resume_id
        ).where(
            ResumeVersion.id == version_id,
            Resume.user_id == self.owner_id,
            Resume.archived_at.is_(None),
        ))
        if not version:
            raise MatchNotFound("Resume Version not found.")
        return version

    def _summary(self, analysis: JobMatchAnalysis) -> dict[str, object]:
        return _columns(analysis, {"owner_user_id", "input_fingerprint", "weight_config"})

    def _detail(self, analysis: JobMatchAnalysis, reused: bool | None = None) -> dict[str, object]:
        result = {
            **_columns(analysis, {"owner_user_id", "input_fingerprint"}),
            "dimensions": [_columns(item) for item in self.repository.dimensions(analysis.id)],
            "evidence": [_columns(item) for item in self.repository.evidence(analysis.id)],
        }
        if reused is not None:
            result["reused"] = reused
        return result
