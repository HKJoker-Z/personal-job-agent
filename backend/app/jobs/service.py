"""Job Library business rules, ownership, audit, deduplication, and merge."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Application,
    ApplicationTask,
    Job,
    JobDuplicateCandidate,
    JobMergeHistory,
    JobRequirement,
    JobSource,
    utc_now,
)
from app.db.repositories.auth import AuthRepository
from app.jobs.deduplication import assess_duplicate, canonical_pair
from app.jobs.extraction import deterministic_requirements, llm_requirements, RequirementInvoker
from app.jobs.normalization import (
    canonicalize_url,
    deduplication_key,
    description_hash,
    normalize_company,
    normalize_description,
    normalize_location,
    normalize_text,
    normalize_title,
)
from app.jobs.repository import JobRepository


class JobNotFound(RuntimeError):
    pass


class JobConflict(RuntimeError):
    pass


def _value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_job(job: Job, *, detail: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "id": str(job.id), "company_name": job.company_name, "title": job.title,
        "location": job.location, "canonical_url": job.canonical_url,
        "employment_type": job.employment_type, "work_mode": job.work_mode,
        "seniority": job.seniority, "department": job.department,
        "salary_min": job.salary_min, "salary_max": job.salary_max,
        "salary_currency": job.salary_currency, "salary_period": job.salary_period,
        "published_at": _value(job.published_at), "application_deadline": _value(job.application_deadline),
        "source_type": job.source_type, "status": job.status, "revision": job.revision,
        "created_at": _value(job.created_at), "updated_at": _value(job.updated_at),
        "archived_at": _value(job.archived_at),
        "description_summary": job.description[:280] + ("…" if len(job.description) > 280 else ""),
    }
    if detail:
        result.update({
            "description": job.description,
            "normalized_company_name": job.normalized_company_name,
            "normalized_title": job.normalized_title,
            "normalized_location": job.normalized_location,
            "external_reference": job.external_reference,
        })
    return result


def serialize_model(value: object, *, exclude: set[str] | None = None) -> dict[str, object]:
    excluded = exclude or set()
    return {
        column.name: _value(getattr(value, column.name))
        for column in value.__table__.columns
        if column.name not in excluded
    }


class JobService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id
        self.repository = JobRepository(db)

    def list(self, filters: dict[str, object], offset: int, limit: int, sort: str) -> dict[str, object]:
        values, total = self.repository.list(self.owner_id, filters, offset, limit, sort)
        return {"items": [serialize_job(item) for item in values], "offset": offset, "limit": limit, "total": total}

    def get(self, job_id: UUID) -> dict[str, object]:
        job = self._job(job_id)
        application = self.db.scalar(select(Application).where(
            Application.owner_user_id == self.owner_id,
            Application.job_id == job.id,
            Application.archived_at.is_(None),
        ))
        return {
            **serialize_job(job, detail=True),
            "sources": [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.sources(self.owner_id, job.id)],
            "requirements": [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.requirements(self.owner_id, job.id)],
            "duplicate_candidates": [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.duplicates(self.owner_id, job.id)],
            "linked_application_id": str(application.id) if application else None,
        }

    def create(self, values: dict[str, object], source: dict[str, object] | None = None) -> dict[str, object]:
        clean = self._normalized(values)
        existing = self.repository.exact(
            self.owner_id,
            clean.get("canonical_url"),
            str(clean["description_text_hash"]),
            str(clean["deduplication_key"]),
            str(clean["external_reference"]) if clean.get("external_reference") else None,
            str(clean["source_type"]),
        )
        if existing:
            source_values = source or {"source_type": clean["source_type"]}
            self.db.add(JobSource(job_id=existing.id, owner_user_id=self.owner_id, **source_values))
            self._audit("job.source.added_to_existing", existing.id, {"source_type": source_values.get("source_type")})
            return {"result": "existing", "job": serialize_job(existing, detail=True), "duplicate_candidate": None}
        job = Job(owner_user_id=self.owner_id, **clean)
        self.db.add(job)
        self.db.flush()
        source_values = source or {"source_type": clean["source_type"]}
        self.db.add(JobSource(job_id=job.id, owner_user_id=self.owner_id, **source_values))
        self.db.flush()
        for index, item in enumerate(deterministic_requirements(job.description)):
            self._add_requirement_model(job, item, index)
        candidate = self._record_near_duplicate(job)
        self._audit("job.created", job.id, {"source_type": job.source_type, "near_duplicate": bool(candidate)})
        return {
            "result": "duplicate_candidate" if candidate else "created",
            "job": serialize_job(job, detail=True),
            "duplicate_candidate": serialize_model(candidate, exclude={"owner_user_id"}) if candidate else None,
        }

    def update(self, job_id: UUID, values: dict[str, object]) -> dict[str, object]:
        expected = int(values.pop("expected_revision"))
        job = self._job(job_id, for_update=True)
        self._expect(job.revision, expected)
        mutable = {
            "company_name", "title", "location", "description", "canonical_url", "external_reference",
            "employment_type", "work_mode", "seniority", "department", "salary_min", "salary_max",
            "salary_currency", "salary_period", "published_at", "application_deadline", "status",
        }
        for key, value in values.items():
            if key in mutable:
                setattr(job, key, value)
        normalized = self._normalized({key: getattr(job, key) for key in mutable} | {"source_type": job.source_type})
        for key in (
            "company_name", "normalized_company_name", "title", "normalized_title", "location",
            "normalized_location", "description", "description_text_hash", "canonical_url",
            "deduplication_key",
        ):
            setattr(job, key, normalized[key])
        self._validate_salary(job.salary_min, job.salary_max)
        job.revision += 1
        self._audit("job.updated", job.id, {"revision": job.revision})
        return serialize_job(job, detail=True)

    def archive(self, job_id: UUID, expected_revision: int) -> dict[str, object]:
        job = self._job(job_id, for_update=True)
        self._expect(job.revision, expected_revision)
        job.archived_at = utc_now()
        job.status = "archived"
        job.revision += 1
        self._audit("job.archived", job.id)
        return serialize_job(job, detail=True)

    def restore(self, job_id: UUID, expected_revision: int) -> dict[str, object]:
        job = self.repository.get(self.owner_id, job_id, include_archived=True, for_update=True)
        if not job:
            raise JobNotFound("Job not found.")
        self._expect(job.revision, expected_revision)
        job.archived_at = None
        job.status = "reviewed"
        job.revision += 1
        self._audit("job.restored", job.id)
        return serialize_job(job, detail=True)

    def sources(self, job_id: UUID) -> list[dict[str, object]]:
        self._job(job_id)
        return [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.sources(self.owner_id, job_id)]

    def requirements(self, job_id: UUID) -> list[dict[str, object]]:
        self._job(job_id)
        return [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.requirements(self.owner_id, job_id)]

    def add_requirement(self, job_id: UUID, values: dict[str, object]) -> dict[str, object]:
        job = self._job(job_id, for_update=True)
        requirement = self._add_requirement_model(job, values, int(values.get("sort_order") or 0))
        self._audit("job.requirement.created", requirement.id, {"job_id": str(job.id)})
        return serialize_model(requirement, exclude={"owner_user_id"})

    def update_requirement(self, job_id: UUID, requirement_id: UUID, values: dict[str, object]) -> dict[str, object]:
        self._job(job_id, for_update=True)
        requirement = self.repository.requirement(self.owner_id, job_id, requirement_id)
        if not requirement:
            raise JobNotFound("Job Requirement not found.")
        for key, value in values.items():
            setattr(requirement, key, value)
        if "name" in values:
            requirement.normalized_name = normalize_text(str(values["name"])).casefold()
        self._audit("job.requirement.updated", requirement.id, {"job_id": str(job_id)})
        return serialize_model(requirement, exclude={"owner_user_id"})

    def delete_requirement(self, job_id: UUID, requirement_id: UUID) -> None:
        self._job(job_id, for_update=True)
        requirement = self.repository.requirement(self.owner_id, job_id, requirement_id)
        if not requirement:
            raise JobNotFound("Job Requirement not found.")
        self.db.delete(requirement)
        self._audit("job.requirement.deleted", requirement_id, {"job_id": str(job_id)})

    def extract_requirements(self, job_id: UUID, invoker: RequirementInvoker | None = None) -> dict[str, object]:
        job = self._job(job_id, for_update=True)
        items, metadata = llm_requirements(job.description, invoker)
        created = [serialize_model(self._add_requirement_model(job, item, index), exclude={"owner_user_id"}) for index, item in enumerate(items)]
        self._audit("job.requirements.llm_extracted", job.id, metadata)
        return {"requirements": created, "metadata": metadata}

    def duplicates(self, job_id: UUID) -> list[dict[str, object]]:
        self._job(job_id)
        return [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.duplicates(self.owner_id, job_id)]

    def resolve_duplicate(self, job_id: UUID, candidate_id: UUID, action: str) -> dict[str, object]:
        self._job(job_id)
        self._job(candidate_id)
        duplicate = self.repository.duplicate(self.owner_id, job_id, candidate_id)
        if not duplicate:
            raise JobNotFound("Duplicate candidate not found.")
        duplicate.status = {"confirm_duplicate": "confirmed_duplicate", "not_duplicate": "not_duplicate", "dismiss": "dismissed"}[action]
        duplicate.resolved_at = utc_now()
        duplicate.resolved_by_user_id = self.owner_id
        self._audit("job.duplicate.resolved", duplicate.id, {"action": action})
        return serialize_model(duplicate, exclude={"owner_user_id"})

    def merge(self, target_id: UUID, source_id: UUID, expected_target: int, expected_source: int, selections: dict[str, str]) -> dict[str, object]:
        if target_id == source_id:
            raise JobConflict("Source and target Job must differ.")
        ordered = sorted((target_id, source_id), key=str)
        locked = list(self.db.scalars(select(Job).where(
            Job.owner_user_id == self.owner_id, Job.id.in_(ordered)
        ).order_by(Job.id).with_for_update()))
        by_id = {item.id: item for item in locked}
        target, source = by_id.get(target_id), by_id.get(source_id)
        if not target or not source or target.archived_at or source.archived_at:
            raise JobNotFound("Job not found.")
        self._expect(target.revision, expected_target)
        self._expect(source.revision, expected_source)
        target_application = self.db.scalar(select(Application).where(
            Application.owner_user_id == self.owner_id, Application.job_id == target.id,
            Application.archived_at.is_(None),
        ))
        source_application = self.db.scalar(select(Application).where(
            Application.owner_user_id == self.owner_id, Application.job_id == source.id,
            Application.archived_at.is_(None),
        ))
        if target_application and source_application:
            raise JobConflict("Both Jobs have active Applications; resolve them before merging.")
        allowed_fields = {
            "company_name", "title", "location", "description", "canonical_url", "external_reference",
            "employment_type", "work_mode", "seniority", "department", "salary_min", "salary_max",
            "salary_currency", "salary_period", "published_at", "application_deadline",
        }
        for field, selected in selections.items():
            if field not in allowed_fields:
                raise JobConflict("Merge field selection contains an unsupported field.")
            if selected == "source":
                setattr(target, field, getattr(source, field))
        normalized = self._normalized({field: getattr(target, field) for field in allowed_fields} | {"source_type": target.source_type})
        for key in ("normalized_company_name", "normalized_title", "normalized_location", "description_text_hash", "deduplication_key"):
            setattr(target, key, normalized[key])
        self.db.execute(update(JobSource).where(
            JobSource.owner_user_id == self.owner_id, JobSource.job_id == source.id
        ).values(job_id=target.id))
        self.db.execute(update(JobRequirement).where(
            JobRequirement.owner_user_id == self.owner_id, JobRequirement.job_id == source.id
        ).values(job_id=target.id))
        self.db.execute(update(ApplicationTask).where(
            ApplicationTask.owner_user_id == self.owner_id, ApplicationTask.job_id == source.id
        ).values(job_id=target.id))
        if source_application:
            source_application.job_id = target.id
        target.revision += 1
        source.revision += 1
        source.archived_at = utc_now()
        source.status = "archived"
        history = JobMergeHistory(
            owner_user_id=self.owner_id, target_job_id=target.id, source_job_id=source.id,
            field_selection=selections,
            summary={"sources_moved": True, "requirements_moved": True, "application_moved": bool(source_application)},
            merged_by_user_id=self.owner_id,
        )
        self.db.add(history)
        self._audit("job.merged", target.id, {"source_job_id": str(source.id), "merge_history_id": str(history.id)})
        return {"target": serialize_job(target, detail=True), "source": serialize_job(source, detail=True), "merge": serialize_model(history, exclude={"owner_user_id"})}

    def _normalized(self, values: dict[str, object]) -> dict[str, object]:
        company = normalize_text(str(values.get("company_name") or ""))
        title = normalize_text(str(values.get("title") or ""))
        location = normalize_text(str(values.get("location") or ""))
        description = normalize_description(str(values.get("description") or ""))
        if not description:
            raise ValueError("Job description is required.")
        canonical_url = canonicalize_url(str(values["canonical_url"])) if values.get("canonical_url") else None
        self._validate_salary(values.get("salary_min"), values.get("salary_max"))
        return {
            **values,
            "company_name": company or None,
            "normalized_company_name": normalize_company(company),
            "title": title or None,
            "normalized_title": normalize_title(title),
            "location": location,
            "normalized_location": normalize_location(location),
            "description": description,
            "description_text_hash": description_hash(description),
            "canonical_url": canonical_url,
            "deduplication_key": deduplication_key(company, title, location, description, canonical_url),
        }

    def _record_near_duplicate(self, job: Job) -> JobDuplicateCandidate | None:
        best: tuple[object, Job] | None = None
        for candidate in self.repository.near_pool(
            self.owner_id, job.id, job.normalized_company_name, job.normalized_title
        ):
            assessment = assess_duplicate(job, candidate)
            if assessment and assessment.match_type == "near" and (best is None or assessment.score > best[0].score):
                best = (assessment, candidate)
        if not best:
            return None
        assessment, candidate = best
        left, right = canonical_pair(job.id, candidate.id)
        value = JobDuplicateCandidate(
            owner_user_id=self.owner_id, job_id=left, candidate_job_id=right,
            match_type=assessment.match_type, similarity_score=assessment.score,
            reason_codes=list(assessment.reasons), status="pending",
        )
        self.db.add(value)
        self.db.flush()
        return value

    def _add_requirement_model(self, job: Job, values: dict[str, object], sort_order: int) -> JobRequirement:
        evidence = values.get("evidence_text")
        start, end = values.get("evidence_start"), values.get("evidence_end")
        if evidence is not None:
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end > len(job.description) or end < start or job.description[start:end] != evidence:
                raise ValueError("Requirement evidence must exactly match the current Job Description.")
        source = str(values.get("extraction_source") or "user")
        status = str(values.get("verification_status") or "needs_review")
        if source == "llm" and status != "needs_review":
            raise ValueError("LLM requirements must be reviewed before confirmation.")
        requirement = JobRequirement(
            job_id=job.id, owner_user_id=self.owner_id,
            category=str(values.get("category") or "other"),
            requirement_type=str(values.get("requirement_type") or "informational"),
            name=normalize_text(str(values.get("name") or evidence or "Requirement"))[:300],
            normalized_name=normalize_text(str(values.get("name") or evidence or "Requirement")).casefold()[:300],
            description=str(values.get("description") or "")[:4000],
            importance=int(values.get("importance") or 3), minimum_years=values.get("minimum_years"),
            evidence_text=evidence, evidence_start=start, evidence_end=end,
            extraction_source=source, confidence=float(values.get("confidence", 0.5)),
            verification_status=status, sort_order=int(values.get("sort_order", sort_order)),
        )
        self.db.add(requirement)
        self.db.flush()
        return requirement

    def _job(self, job_id: UUID, *, for_update: bool = False) -> Job:
        job = self.repository.get(self.owner_id, job_id, for_update=for_update)
        if not job:
            raise JobNotFound("Job not found.")
        return job

    @staticmethod
    def _expect(actual: int, expected: int) -> None:
        if actual != expected:
            raise JobConflict("Job revision is stale.")

    @staticmethod
    def _validate_salary(minimum: object, maximum: object) -> None:
        if minimum is not None and int(minimum) < 0 or maximum is not None and int(maximum) < 0:
            raise ValueError("Salary values cannot be negative.")
        if minimum is not None and maximum is not None and int(maximum) < int(minimum):
            raise ValueError("salary_max must be greater than or equal to salary_min.")

    def _audit(self, event: str, resource_id: UUID, metadata: dict[str, object] | None = None) -> None:
        AuthRepository(self.db).audit(event, user_id=self.owner_id, resource_type="job", resource_id=str(resource_id), safe_metadata=metadata)
