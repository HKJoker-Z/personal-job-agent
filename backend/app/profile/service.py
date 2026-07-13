"""Career Profile transactions, revisions, restore, and deterministic completeness."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.db.models import ProfilePreference, ProfileRevision
from app.db.repositories.auth import AuthRepository
from app.profile.repository import RESOURCE_MODELS, ProfileRepository


class StaleProfile(RuntimeError):
    pass


class ProfileNotFound(RuntimeError):
    pass


REQUIRED_FIELDS = {
    "experiences": ("company", "role_title"),
    "educations": ("institution",),
    "projects": ("name",),
    "skills": ("name",),
    "languages": ("language", "proficiency"),
    "certifications": ("name",),
}


def _json_value(value: object) -> object:
    if isinstance(value, (UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    return value


def model_dict(value: object, *, include_private: bool = True) -> dict[str, object]:
    result: dict[str, object] = {}
    for column in inspect(value.__class__).columns:
        if not include_private and column.key in {"phone", "public_email"}:
            continue
        result[column.key] = _json_value(getattr(value, column.key))
    return result


class ProfileService:
    def __init__(self, db: Session, user_id: UUID):
        self.db = db
        self.user_id = user_id
        self.repository = ProfileRepository(db)

    def get(self) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id)
        return self._response(profile)

    def update_profile(self, values: dict[str, object], expected_revision: int) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        for field in (
            "headline",
            "professional_summary",
            "current_location",
            "phone",
            "public_email",
            "website",
            "linkedin_url",
            "github_url",
        ):
            if field in values:
                setattr(profile, field, values[field] or "")
        self._record(profile, "profile.updated")
        return self._response(profile)

    def list_items(self, resource: str) -> list[dict[str, object]]:
        profile = self.repository.get_or_create(self.user_id)
        return [model_dict(item) for item in self.repository.list_items(profile.id, resource)]

    def create_item(
        self, resource: str, values: dict[str, object], expected_revision: int
    ) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        clean = self._item_values(resource, values)
        item = RESOURCE_MODELS[resource](profile_id=profile.id, **clean)
        self.db.add(item)
        self.db.flush()
        self._record(profile, f"profile.{resource}.created")
        return model_dict(item)

    def update_item(
        self,
        resource: str,
        item_id: UUID,
        values: dict[str, object],
        expected_revision: int,
    ) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        item = self.repository.item(profile.id, resource, item_id)
        if item is None:
            raise ProfileNotFound("Profile item not found.")
        for key, value in self._item_values(resource, values, partial=True).items():
            setattr(item, key, value)
        self._record(profile, f"profile.{resource}.updated")
        return model_dict(item)

    def delete_item(self, resource: str, item_id: UUID, expected_revision: int) -> None:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        item = self.repository.item(profile.id, resource, item_id)
        if item is None:
            raise ProfileNotFound("Profile item not found.")
        self.db.delete(item)
        self.db.flush()
        self._record(profile, f"profile.{resource}.deleted")

    def get_preference(self) -> dict[str, object] | None:
        profile = self.repository.get_or_create(self.user_id)
        value = self.repository.preference(profile.id)
        return model_dict(value) if value else None

    def set_preference(self, values: dict[str, object], expected_revision: int) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        preference = self.repository.preference(profile.id)
        if preference is None:
            preference = ProfilePreference(profile_id=profile.id)
            self.db.add(preference)
        for key, value in values.items():
            setattr(preference, key, value)
        self.db.flush()
        self._record(profile, "profile.preferences.updated")
        return model_dict(preference)

    def delete_preference(self, expected_revision: int) -> None:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        preference = self.repository.preference(profile.id)
        if preference:
            self.db.delete(preference)
            self.db.flush()
        self._record(profile, "profile.preferences.deleted")

    def revisions(self) -> list[dict[str, object]]:
        profile = self.repository.get_or_create(self.user_id)
        return [
            {
                "revision": revision.revision_number,
                "change_type": revision.change_type,
                "created_at": revision.created_at,
                "created_by": str(revision.created_by),
            }
            for revision in self.repository.revisions(profile.id)
        ]

    def revision(self, number: int) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id)
        revision = self.repository.revision(profile.id, number)
        if revision is None:
            raise ProfileNotFound("Profile revision not found.")
        return {
            "revision": revision.revision_number,
            "change_type": revision.change_type,
            "created_at": revision.created_at,
            "snapshot": revision.snapshot,
        }

    def restore(self, number: int, expected_revision: int) -> dict[str, object]:
        profile = self.repository.get_or_create(self.user_id, for_update=True)
        self._expect(profile.revision, expected_revision)
        revision = self.repository.revision(profile.id, number)
        if revision is None:
            raise ProfileNotFound("Profile revision not found.")
        snapshot = revision.snapshot
        for key, value in snapshot["profile"].items():
            if key not in {"id", "user_id", "created_at", "updated_at", "revision", "completeness_score"}:
                setattr(profile, key, value)
        self.repository.clear_items(profile.id)
        self.db.flush()
        for resource, model in RESOURCE_MODELS.items():
            for item in snapshot.get(resource, []):
                values = {key: self._coerce(model, key, value) for key, value in item.items() if key not in {"created_at", "updated_at"}}
                values["profile_id"] = profile.id
                self.db.add(model(**values))
        preference = snapshot.get("preferences")
        if preference:
            values = {key: value for key, value in preference.items() if key not in {"id", "profile_id", "created_at", "updated_at"}}
            self.db.add(ProfilePreference(profile_id=profile.id, **values))
        self.db.flush()
        self._record(profile, f"profile.restored_from.{number}")
        return self._response(profile)

    def _item_values(
        self, resource: str, values: dict[str, object], partial: bool = False
    ) -> dict[str, object]:
        model_columns = {column.key for column in inspect(RESOURCE_MODELS[resource]).columns}
        clean = {
            key: value
            for key, value in values.items()
            if key in model_columns and key not in {"id", "profile_id", "created_at", "updated_at"}
        }
        if not partial:
            for field in REQUIRED_FIELDS[resource]:
                if not clean.get(field):
                    raise ValueError(f"{field} is required.")
        return clean

    def _expect(self, current: int, expected: int) -> None:
        if current != expected:
            raise StaleProfile("Profile was modified by another request.")

    def _snapshot(self, profile: object) -> dict[str, object]:
        snapshot: dict[str, object] = {"profile": model_dict(profile)}
        for resource in RESOURCE_MODELS:
            snapshot[resource] = [
                model_dict(item) for item in self.repository.list_items(profile.id, resource)
            ]
        preference = self.repository.preference(profile.id)
        snapshot["preferences"] = model_dict(preference) if preference else None
        return snapshot

    def _record(self, profile: object, change_type: str) -> None:
        self.db.flush()
        profile.revision += 1
        score, _ = self._completeness(profile)
        profile.completeness_score = score
        self.db.flush()
        self.db.add(
            ProfileRevision(
                profile_id=profile.id,
                revision_number=profile.revision,
                change_type=change_type,
                snapshot=self._snapshot(profile),
                created_by=self.user_id,
            )
        )
        AuthRepository(self.db).audit(change_type, user_id=self.user_id, resource_type="career_profile", resource_id=str(profile.id))

    def _completeness(self, profile: object) -> tuple[int, list[str]]:
        sections = {
            "basic_information": bool(profile.headline and profile.current_location),
            "professional_summary": bool(profile.professional_summary),
            "work_experience": bool(self.repository.list_items(profile.id, "experiences")),
            "education": bool(self.repository.list_items(profile.id, "educations")),
            "skills": bool(self.repository.list_items(profile.id, "skills")),
            "job_preferences": self.repository.preference(profile.id) is not None,
        }
        score = round(sum(sections.values()) * 100 / len(sections))
        return score, [key for key, complete in sections.items() if not complete]

    def _response(self, profile: object) -> dict[str, object]:
        score, missing = self._completeness(profile)
        profile.completeness_score = score
        return {**model_dict(profile), "completeness": {"score": score, "missing_sections": missing}}

    @staticmethod
    def _coerce(model: type, key: str, value: object) -> object:
        column = inspect(model).columns.get(key)
        if value is None or column is None:
            return value
        python_type = getattr(column.type, "python_type", None)
        if python_type is UUID:
            return UUID(str(value))
        if python_type is date and isinstance(value, str):
            return date.fromisoformat(value)
        if python_type is datetime and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
