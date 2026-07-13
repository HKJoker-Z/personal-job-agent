"""Career Profile persistence, scoped to an owning user."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    CareerProfile,
    ProfileCertification,
    ProfileEducation,
    ProfileExperience,
    ProfileLanguage,
    ProfilePreference,
    ProfileProject,
    ProfileRevision,
    ProfileSkill,
)


RESOURCE_MODELS = {
    "experiences": ProfileExperience,
    "educations": ProfileEducation,
    "projects": ProfileProject,
    "skills": ProfileSkill,
    "languages": ProfileLanguage,
    "certifications": ProfileCertification,
}


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: UUID, *, for_update: bool = False) -> CareerProfile | None:
        statement = select(CareerProfile).where(CareerProfile.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def get_or_create(self, user_id: UUID, *, for_update: bool = False) -> CareerProfile:
        profile = self.get(user_id, for_update=for_update)
        if profile is None:
            profile = CareerProfile(user_id=user_id)
            self.db.add(profile)
            self.db.flush()
        return profile

    def list_items(self, profile_id: UUID, resource: str) -> list[object]:
        model = RESOURCE_MODELS[resource]
        return list(
            self.db.scalars(
                select(model)
                .where(model.profile_id == profile_id)
                .order_by(model.sort_order, model.created_at)
            )
        )

    def item(self, profile_id: UUID, resource: str, item_id: UUID) -> object | None:
        model = RESOURCE_MODELS[resource]
        return self.db.scalar(
            select(model).where(model.id == item_id, model.profile_id == profile_id)
        )

    def preference(self, profile_id: UUID) -> ProfilePreference | None:
        return self.db.scalar(
            select(ProfilePreference).where(ProfilePreference.profile_id == profile_id)
        )

    def revisions(self, profile_id: UUID) -> list[ProfileRevision]:
        return list(
            self.db.scalars(
                select(ProfileRevision)
                .where(ProfileRevision.profile_id == profile_id)
                .order_by(ProfileRevision.revision_number.desc())
            )
        )

    def revision(self, profile_id: UUID, revision_number: int) -> ProfileRevision | None:
        return self.db.scalar(
            select(ProfileRevision).where(
                ProfileRevision.profile_id == profile_id,
                ProfileRevision.revision_number == revision_number,
            )
        )

    def clear_items(self, profile_id: UUID) -> None:
        for model in RESOURCE_MODELS.values():
            self.db.execute(delete(model).where(model.profile_id == profile_id))
        self.db.execute(delete(ProfilePreference).where(ProfilePreference.profile_id == profile_id))
