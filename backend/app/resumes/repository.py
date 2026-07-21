"""Owned Resume and private file persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import FileAsset, Resume, ResumeVersion


class ResumeRepository:
    def __init__(self, db: Session):
        self.db = db

    def resumes(self, user_id: UUID) -> list[Resume]:
        return list(
            self.db.scalars(
                select(Resume)
                .where(Resume.user_id == user_id, Resume.archived_at.is_(None))
                .order_by(Resume.is_primary.desc(), Resume.updated_at.desc(), Resume.created_at.desc())
            )
        )

    def primary(self, user_id: UUID) -> Resume | None:
        return self.db.scalar(
            select(Resume).where(
                Resume.user_id == user_id,
                Resume.is_primary.is_(True),
                Resume.archived_at.is_(None),
            )
        )

    def active_for_update(self, user_id: UUID) -> list[Resume]:
        return list(
            self.db.scalars(
                select(Resume)
                .where(Resume.user_id == user_id, Resume.archived_at.is_(None))
                .order_by(Resume.updated_at.desc(), Resume.created_at.desc())
                .with_for_update()
            )
        )

    def resume(self, user_id: UUID, resume_id: UUID, include_archived: bool = False) -> Resume | None:
        statement = select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        if not include_archived:
            statement = statement.where(Resume.archived_at.is_(None))
        return self.db.scalar(statement)

    def resume_for_update(self, user_id: UUID, resume_id: UUID) -> Resume | None:
        return self.db.scalar(
            select(Resume)
            .where(
                Resume.id == resume_id,
                Resume.user_id == user_id,
                Resume.archived_at.is_(None),
            )
            .with_for_update()
        )

    def versions(self, resume_id: UUID) -> list[ResumeVersion]:
        return list(
            self.db.scalars(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == resume_id)
                .order_by(ResumeVersion.version_number.desc())
            )
        )

    def version(self, resume_id: UUID, version_id: UUID) -> ResumeVersion | None:
        return self.db.scalar(
            select(ResumeVersion).where(
                ResumeVersion.id == version_id,
                ResumeVersion.resume_id == resume_id,
            )
        )

    def owned_version(self, user_id: UUID, version_id: UUID) -> ResumeVersion | None:
        return self.db.scalar(
            select(ResumeVersion)
            .join(Resume, Resume.id == ResumeVersion.resume_id)
            .where(ResumeVersion.id == version_id, Resume.user_id == user_id, Resume.archived_at.is_(None))
        )

    def next_version_number(self, resume_id: UUID) -> int:
        current = self.db.scalar(
            select(func.max(ResumeVersion.version_number)).where(ResumeVersion.resume_id == resume_id)
        )
        return int(current or 0) + 1

    def file(self, user_id: UUID, file_id: UUID, include_deleted: bool = False) -> FileAsset | None:
        statement = select(FileAsset).where(FileAsset.id == file_id, FileAsset.user_id == user_id)
        if not include_deleted:
            statement = statement.where(FileAsset.deleted_at.is_(None))
        return self.db.scalar(statement)

    def duplicate_file(self, user_id: UUID, digest: str) -> FileAsset | None:
        return self.db.scalar(
            select(FileAsset).where(
                FileAsset.user_id == user_id,
                FileAsset.sha256 == digest,
                FileAsset.deleted_at.is_(None),
            )
        )

    def file_is_referenced(self, file_id: UUID) -> bool:
        return self.db.scalar(
            select(ResumeVersion.id).where(ResumeVersion.source_file_id == file_id).limit(1)
        ) is not None
