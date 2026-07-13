"""Transactional Application stages, private Notes, and user-confirmed Tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.applications.repository import ApplicationRepository, TaskRepository
from app.db.models import (
    Application,
    ApplicationNote,
    ApplicationStageHistory,
    ApplicationTask,
    Job,
    utc_now,
)
from app.db.repositories.auth import AuthRepository
from app.jobs.service import JobNotFound, serialize_model
from app.resumes.repository import ResumeRepository


TRANSITIONS: dict[str, tuple[str, ...]] = {
    "saved": ("shortlisted", "preparing", "closed"),
    "shortlisted": ("preparing", "rejected", "closed"),
    "preparing": ("ready_to_apply", "withdrawn", "closed"),
    "ready_to_apply": ("applied", "withdrawn", "closed"),
    "applied": ("assessment", "interview", "rejected", "withdrawn", "closed"),
    "assessment": ("interview", "rejected", "withdrawn"),
    "interview": ("final_interview", "offer", "rejected", "withdrawn"),
    "final_interview": ("offer", "rejected", "withdrawn"),
    "offer": ("accepted", "rejected", "withdrawn"),
    "accepted": (), "rejected": (), "withdrawn": (), "closed": (),
}
TERMINAL_STAGES = {"accepted", "rejected", "withdrawn", "closed"}


class ApplicationNotFound(RuntimeError):
    pass


class ApplicationConflict(RuntimeError):
    pass


class InvalidTransition(ApplicationConflict):
    def __init__(self, current: str):
        self.current = current
        self.allowed = TRANSITIONS.get(current, ())
        super().__init__("Application stage transition is not allowed.")


def serialize_application(value: Application) -> dict[str, object]:
    return serialize_model(value, exclude={"owner_user_id"})


class ApplicationService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id
        self.repository = ApplicationRepository(db)

    def list(self, stage: str | None = None, archived: bool = False) -> list[dict[str, object]]:
        applications = self.repository.list(self.owner_id, stage, archived)
        job_ids = {item.job_id for item in applications}
        jobs = {
            job.id: job
            for job in self.db.scalars(
                select(Job).where(Job.owner_user_id == self.owner_id, Job.id.in_(job_ids))
            )
        } if job_ids else {}
        return [
            serialize_application(item) | {
                "job": {
                    "id": str(jobs[item.job_id].id),
                    "company_name": jobs[item.job_id].company_name,
                    "title": jobs[item.job_id].title,
                } if item.job_id in jobs else None
            }
            for item in applications
        ]

    def get(self, application_id: UUID) -> dict[str, object]:
        application = self._application(application_id)
        job = self.db.scalar(select(Job).where(Job.id == application.job_id, Job.owner_user_id == self.owner_id))
        return {
            **serialize_application(application),
            "job": {"id": str(job.id), "company_name": job.company_name, "title": job.title} if job else None,
            "history": self.history(application_id),
        }

    def create(self, values: dict[str, object]) -> dict[str, object]:
        job = self.db.scalar(select(Job).where(
            Job.id == values["job_id"], Job.owner_user_id == self.owner_id, Job.archived_at.is_(None)
        ))
        if not job:
            raise JobNotFound("Job not found.")
        if self.repository.active_for_job(self.owner_id, job.id):
            raise ApplicationConflict("An active Application already exists for this Job.")
        resume_id = values.get("resume_version_id")
        warning = self._resume_warning(resume_id) if resume_id else None
        application = Application(owner_user_id=self.owner_id, current_stage="saved", **values)
        self.db.add(application)
        self.db.flush()
        self.db.add(ApplicationStageHistory(
            application_id=application.id, owner_user_id=self.owner_id, from_stage="saved", to_stage="saved",
            reason="Application created", notes="", changed_by_user_id=self.owner_id,
            revision_before=0, revision_after=1,
        ))
        self._audit("application.created", application.id, {"job_id": str(job.id)})
        return {"application": serialize_application(application), "warning": warning}

    def update(self, application_id: UUID, values: dict[str, object]) -> dict[str, object]:
        expected = int(values.pop("expected_revision"))
        application = self._application(application_id, for_update=True)
        self._expect(application.revision, expected)
        for key in ("source", "priority", "next_action_at", "expected_response_at"):
            if key in values:
                setattr(application, key, values[key])
        application.revision += 1
        self._audit("application.updated", application.id, {"revision": application.revision})
        return serialize_application(application)

    def archive(self, application_id: UUID, expected_revision: int) -> dict[str, object]:
        application = self._application(application_id, for_update=True)
        self._expect(application.revision, expected_revision)
        application.archived_at = utc_now()
        application.revision += 1
        self.db.flush()
        self._audit("application.archived", application.id)
        return serialize_application(application)

    def restore(self, application_id: UUID, expected_revision: int) -> dict[str, object]:
        application = self.repository.get(self.owner_id, application_id, include_archived=True, for_update=True)
        if not application:
            raise ApplicationNotFound("Application not found.")
        self._expect(application.revision, expected_revision)
        existing = self.repository.active_for_job(self.owner_id, application.job_id)
        if existing and existing.id != application.id:
            raise ApplicationConflict("Another active Application already exists for this Job.")
        application.archived_at = None
        application.revision += 1
        self.db.flush()
        self._audit("application.restored", application.id)
        return serialize_application(application)

    def transition(self, application_id: UUID, to_stage: str, expected_revision: int, reason: str, notes: str, occurred_at: datetime | None) -> dict[str, object]:
        application = self._application(application_id, for_update=True)
        self._expect(application.revision, expected_revision)
        if to_stage not in TRANSITIONS.get(application.current_stage, ()):
            raise InvalidTransition(application.current_stage)
        before = application.revision
        previous = application.current_stage
        application.current_stage = to_stage
        application.revision += 1
        when = occurred_at or utc_now()
        if to_stage == "applied" and application.applied_at is None:
            application.applied_at = when
        if to_stage in {"accepted", "rejected", "withdrawn", "closed"}:
            application.outcome = to_stage
        self.db.add(ApplicationStageHistory(
            application_id=application.id, owner_user_id=self.owner_id,
            from_stage=previous, to_stage=to_stage, reason=reason, notes=notes,
            changed_by_user_id=self.owner_id, changed_at=when,
            revision_before=before, revision_after=application.revision,
        ))
        self._audit("application.transitioned", application.id, {"from_stage": previous, "to_stage": to_stage})
        return {"application": serialize_application(application), "allowed_next_stages": list(TRANSITIONS[to_stage])}

    def reopen(self, application_id: UUID, expected_revision: int, reason: str) -> dict[str, object]:
        application = self._application(application_id, for_update=True)
        self._expect(application.revision, expected_revision)
        if application.current_stage not in TERMINAL_STAGES:
            raise ApplicationConflict("Only a terminal Application can be reopened.")
        previous = application.current_stage
        before = application.revision
        application.current_stage = "saved"
        application.outcome = None
        application.revision += 1
        self.db.add(ApplicationStageHistory(
            application_id=application.id, owner_user_id=self.owner_id,
            from_stage=previous, to_stage="saved", reason=reason, notes="Explicit reopen",
            changed_by_user_id=self.owner_id, revision_before=before, revision_after=application.revision,
        ))
        self._audit("application.reopened", application.id, {"from_stage": previous})
        return serialize_application(application)

    def history(self, application_id: UUID) -> list[dict[str, object]]:
        self._application(application_id)
        return [serialize_model(item, exclude={"owner_user_id", "notes"}) | {"notes": item.notes} for item in self.repository.history(self.owner_id, application_id)]

    def link_resume(self, application_id: UUID, resume_version_id: UUID, expected_revision: int) -> dict[str, object]:
        application = self._application(application_id, for_update=True)
        self._expect(application.revision, expected_revision)
        warning = self._resume_warning(resume_version_id)
        application.resume_version_id = resume_version_id
        application.revision += 1
        self._audit("application.resume_linked", application.id, {"resume_version_id": str(resume_version_id)})
        return {"application": serialize_application(application), "warning": warning}

    def notes(self, application_id: UUID) -> list[dict[str, object]]:
        self._application(application_id)
        return [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.notes(self.owner_id, application_id)]

    def add_note(self, application_id: UUID, values: dict[str, object]) -> dict[str, object]:
        self._application(application_id)
        note = ApplicationNote(
            application_id=application_id, owner_user_id=self.owner_id,
            created_by_user_id=self.owner_id, **values,
        )
        self.db.add(note)
        self.db.flush()
        self._audit("application.note.created", note.id, {"application_id": str(application_id)})
        return serialize_model(note, exclude={"owner_user_id"})

    def update_note(self, application_id: UUID, note_id: UUID, values: dict[str, object]) -> dict[str, object]:
        expected = int(values.pop("expected_revision"))
        self._application(application_id)
        note = self.repository.note(self.owner_id, application_id, note_id, for_update=True)
        if not note:
            raise ApplicationNotFound("Application Note not found.")
        self._expect(note.revision, expected)
        for key in ("content", "note_type"):
            if key in values:
                setattr(note, key, values[key])
        note.revision += 1
        self._audit("application.note.updated", note.id, {"application_id": str(application_id)})
        return serialize_model(note, exclude={"owner_user_id"})

    def delete_note(self, application_id: UUID, note_id: UUID, expected_revision: int) -> None:
        self._application(application_id)
        note = self.repository.note(self.owner_id, application_id, note_id, for_update=True)
        if not note:
            raise ApplicationNotFound("Application Note not found.")
        self._expect(note.revision, expected_revision)
        note.deleted_at = utc_now()
        note.revision += 1
        self._audit("application.note.deleted", note.id, {"application_id": str(application_id)})

    def suggested_tasks(self, application_id: UUID) -> list[dict[str, object]]:
        application = self._application(application_id)
        suggestions = {
            "saved": [("Review job requirements", "review_job")],
            "shortlisted": [("Review job requirements", "review_job")],
            "preparing": [("Review job requirements", "review_job"), ("Select resume version", "tailor_resume"), ("Prepare application", "prepare_application")],
            "ready_to_apply": [("Submit application", "submit_application")],
            "applied": [("Follow up on application", "follow_up")],
            "assessment": [("Complete assessment", "assessment")],
            "interview": [("Prepare for interview", "interview_preparation")],
            "final_interview": [("Prepare for final interview", "interview_preparation")],
        }.get(application.current_stage, [])
        return [{"title": title, "task_type": task_type, "application_id": str(application.id), "job_id": str(application.job_id)} for title, task_type in suggestions]

    def _resume_warning(self, resume_version_id: object) -> str | None:
        version = ResumeRepository(self.db).owned_version(self.owner_id, UUID(str(resume_version_id)))
        if not version:
            raise ApplicationNotFound("Resume Version not found.")
        return "Linked Resume Version is a draft." if version.status != "final" else None

    def _application(self, application_id: UUID, *, for_update: bool = False) -> Application:
        value = self.repository.get(self.owner_id, application_id, for_update=for_update)
        if not value:
            raise ApplicationNotFound("Application not found.")
        return value

    @staticmethod
    def _expect(actual: int, expected: int) -> None:
        if actual != expected:
            raise ApplicationConflict("Resource revision is stale.")

    def _audit(self, event: str, resource_id: UUID, metadata: dict[str, object] | None = None) -> None:
        AuthRepository(self.db).audit(event, user_id=self.owner_id, resource_type="application", resource_id=str(resource_id), safe_metadata=metadata)


class TaskService:
    def __init__(self, db: Session, owner_id: UUID):
        self.db = db
        self.owner_id = owner_id
        self.repository = TaskRepository(db)

    def list(self, filters: dict[str, object], sort: str) -> list[dict[str, object]]:
        return [serialize_model(item, exclude={"owner_user_id"}) for item in self.repository.list(self.owner_id, filters, sort)]

    def get(self, task_id: UUID) -> dict[str, object]:
        return serialize_model(self._task(task_id), exclude={"owner_user_id"})

    def create(self, values: dict[str, object]) -> dict[str, object]:
        values = self._relationships(values)
        self._validate_reminder(values.get("reminder_at"), values.get("due_at"))
        if values.get("status") == "completed":
            values["completed_at"] = utc_now()
        task = ApplicationTask(owner_user_id=self.owner_id, **values)
        self.db.add(task)
        self.db.flush()
        self._audit("task.created", task.id)
        return serialize_model(task, exclude={"owner_user_id"})

    def update(self, task_id: UUID, values: dict[str, object]) -> dict[str, object]:
        expected = int(values.pop("expected_revision"))
        task = self._task(task_id, for_update=True)
        ApplicationService._expect(task.revision, expected)
        combined = {"application_id": task.application_id, "job_id": task.job_id} | values
        checked = self._relationships(combined)
        self._validate_reminder(checked.get("reminder_at", task.reminder_at), checked.get("due_at", task.due_at))
        for key, value in checked.items():
            if key in {"application_id", "job_id", "title", "description", "task_type", "status", "priority", "due_at", "reminder_at", "sort_order"}:
                setattr(task, key, value)
        if task.status == "completed" and task.completed_at is None:
            task.completed_at = utc_now()
        if task.status != "completed":
            task.completed_at = None
        task.revision += 1
        self._audit("task.updated", task.id)
        return serialize_model(task, exclude={"owner_user_id"})

    def complete(self, task_id: UUID, expected_revision: int) -> dict[str, object]:
        task = self._task(task_id, for_update=True)
        ApplicationService._expect(task.revision, expected_revision)
        task.status = "completed"
        task.completed_at = utc_now()
        task.revision += 1
        self._audit("task.completed", task.id)
        return serialize_model(task, exclude={"owner_user_id"})

    def reopen(self, task_id: UUID, expected_revision: int) -> dict[str, object]:
        task = self._task(task_id, for_update=True)
        ApplicationService._expect(task.revision, expected_revision)
        task.status = "pending"
        task.completed_at = None
        task.revision += 1
        self._audit("task.reopened", task.id)
        return serialize_model(task, exclude={"owner_user_id"})

    def archive(self, task_id: UUID, expected_revision: int) -> dict[str, object]:
        task = self._task(task_id, for_update=True)
        ApplicationService._expect(task.revision, expected_revision)
        task.archived_at = utc_now()
        task.revision += 1
        self._audit("task.archived", task.id)
        return serialize_model(task, exclude={"owner_user_id"})

    def _relationships(self, values: dict[str, object]) -> dict[str, object]:
        values = dict(values)
        application_id = values.get("application_id")
        job_id = values.get("job_id")
        application = None
        if application_id:
            application = ApplicationRepository(self.db).get(self.owner_id, UUID(str(application_id)))
            if not application:
                raise ApplicationNotFound("Application not found.")
            if job_id and UUID(str(job_id)) != application.job_id:
                raise ApplicationConflict("Task Job and Application do not match.")
            values["job_id"] = application.job_id
        if values.get("job_id"):
            job = self.db.scalar(select(Job).where(
                Job.id == values["job_id"], Job.owner_user_id == self.owner_id, Job.archived_at.is_(None)
            ))
            if not job:
                raise JobNotFound("Job not found.")
        return values

    @staticmethod
    def _validate_reminder(reminder: object, due: object) -> None:
        if reminder and due and reminder > due:
            raise ValueError("Task reminder cannot be later than its due date.")
        if reminder and reminder > datetime.now(timezone.utc) + timedelta(days=3650):
            raise ValueError("Task reminder is outside the supported range.")

    def _task(self, task_id: UUID, *, for_update: bool = False) -> ApplicationTask:
        task = self.repository.get(self.owner_id, task_id, for_update=for_update)
        if not task:
            raise ApplicationNotFound("Task not found.")
        return task

    def _audit(self, event: str, resource_id: UUID) -> None:
        AuthRepository(self.db).audit(event, user_id=self.owner_id, resource_type="task", resource_id=str(resource_id))
