"""Ownership-scoped Job Library persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Job, JobDuplicateCandidate, JobRequirement, JobSource


SORTS = {
    "created_at": Job.created_at,
    "updated_at": Job.updated_at,
    "company": Job.normalized_company_name,
    "title": Job.normalized_title,
    "location": Job.normalized_location,
    "deadline": Job.application_deadline,
    "status": Job.status,
}


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, owner_id: UUID, job_id: UUID, *, include_archived: bool = False, for_update: bool = False) -> Job | None:
        statement = select(Job).where(Job.id == job_id, Job.owner_user_id == owner_id)
        if not include_archived:
            statement = statement.where(Job.archived_at.is_(None))
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def list(self, owner_id: UUID, filters: dict[str, object], offset: int, limit: int, sort: str) -> tuple[list[Job], int]:
        statement = select(Job).where(Job.owner_user_id == owner_id)
        archived = filters.get("archived")
        if archived is True:
            statement = statement.where(Job.archived_at.is_not(None))
        elif archived is not None:
            statement = statement.where(Job.archived_at.is_(None))
        else:
            statement = statement.where(Job.archived_at.is_(None))
        query = str(filters.get("query") or "").strip()
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            statement = statement.where(or_(
                Job.company_name.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
                Job.location.ilike(pattern, escape="\\"),
                Job.description.ilike(pattern, escape="\\"),
            ))
        for key, column in (
            ("company", Job.normalized_company_name), ("title", Job.normalized_title),
            ("location", Job.normalized_location), ("status", Job.status),
            ("employment_type", Job.employment_type), ("work_mode", Job.work_mode),
            ("source_type", Job.source_type),
        ):
            if filters.get(key):
                statement = statement.where(column == filters[key])
        if filters.get("created_after"):
            statement = statement.where(Job.created_at >= filters["created_after"])
        if filters.get("created_before"):
            statement = statement.where(Job.created_at <= filters["created_before"])
        if filters.get("deadline_after"):
            statement = statement.where(Job.application_deadline >= filters["deadline_after"])
        if filters.get("deadline_before"):
            statement = statement.where(Job.application_deadline <= filters["deadline_before"])
        total = int(self.db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
        descending = sort.startswith("-")
        key = sort.removeprefix("-")
        column = SORTS.get(key)
        if column is None:
            raise ValueError("Unsupported Job sort field.")
        order = desc(column) if descending else asc(column)
        values = list(self.db.scalars(statement.order_by(order, Job.id).offset(offset).limit(limit)))
        return values, total

    def exact(
        self,
        owner_id: UUID,
        canonical_url: str | None,
        digest: str,
        dedup_key: str,
        external_reference: str | None = None,
        source_type: str | None = None,
    ) -> Job | None:
        predicates = [Job.description_text_hash == digest, Job.deduplication_key == dedup_key]
        if canonical_url:
            predicates.append(Job.canonical_url == canonical_url)
        if external_reference and source_type:
            predicates.append(
                (Job.external_reference == external_reference) & (Job.source_type == source_type)
            )
        return self.db.scalar(
            select(Job).where(Job.owner_user_id == owner_id, Job.archived_at.is_(None), or_(*predicates)).limit(1)
        )

    def near_pool(self, owner_id: UUID, job_id: UUID, company: str, title: str) -> list[Job]:
        return list(self.db.scalars(
            select(Job).where(
                Job.owner_user_id == owner_id,
                Job.id != job_id,
                Job.archived_at.is_(None),
                or_(Job.normalized_company_name == company, Job.normalized_title == title),
            ).order_by(Job.created_at.desc()).limit(100)
        ))

    def sources(self, owner_id: UUID, job_id: UUID) -> list[JobSource]:
        return list(self.db.scalars(
            select(JobSource).where(JobSource.owner_user_id == owner_id, JobSource.job_id == job_id)
            .order_by(JobSource.created_at.desc())
        ))

    def requirements(self, owner_id: UUID, job_id: UUID) -> list[JobRequirement]:
        return list(self.db.scalars(
            select(JobRequirement).where(
                JobRequirement.owner_user_id == owner_id, JobRequirement.job_id == job_id
            ).order_by(JobRequirement.sort_order, JobRequirement.created_at)
        ))

    def requirement(self, owner_id: UUID, job_id: UUID, requirement_id: UUID) -> JobRequirement | None:
        return self.db.scalar(select(JobRequirement).where(
            JobRequirement.id == requirement_id,
            JobRequirement.job_id == job_id,
            JobRequirement.owner_user_id == owner_id,
        ))

    def duplicates(self, owner_id: UUID, job_id: UUID) -> list[JobDuplicateCandidate]:
        return list(self.db.scalars(select(JobDuplicateCandidate).where(
            JobDuplicateCandidate.owner_user_id == owner_id,
            or_(JobDuplicateCandidate.job_id == job_id, JobDuplicateCandidate.candidate_job_id == job_id),
        ).order_by(JobDuplicateCandidate.created_at.desc())))

    def duplicate(self, owner_id: UUID, job_id: UUID, candidate_id: UUID) -> JobDuplicateCandidate | None:
        return self.db.scalar(select(JobDuplicateCandidate).where(
            JobDuplicateCandidate.owner_user_id == owner_id,
            or_(
                (JobDuplicateCandidate.job_id == job_id) & (JobDuplicateCandidate.candidate_job_id == candidate_id),
                (JobDuplicateCandidate.job_id == candidate_id) & (JobDuplicateCandidate.candidate_job_id == job_id),
            ),
        ).with_for_update())
