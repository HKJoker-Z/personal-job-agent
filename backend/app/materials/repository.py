"""Ownership-scoped persistence for Packages, Materials, evidence, and reviews."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApplicationMaterial,
    ApplicationMaterialVersion,
    ApplicationPackage,
    MaterialEvidenceLink,
    MaterialReview,
)


class MaterialRepository:
    def __init__(self, db: Session):
        self.db = db

    def package(self, owner_id: UUID, package_id: UUID, *, for_update: bool = False) -> ApplicationPackage | None:
        statement = select(ApplicationPackage).where(
            ApplicationPackage.id == package_id, ApplicationPackage.owner_user_id == owner_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def packages(self, owner_id: UUID, application_id: UUID) -> list[ApplicationPackage]:
        return list(self.db.scalars(select(ApplicationPackage).where(
            ApplicationPackage.owner_user_id == owner_id,
            ApplicationPackage.application_id == application_id,
        ).order_by(ApplicationPackage.created_at.desc())))

    def materials(self, owner_id: UUID, package_id: UUID) -> list[ApplicationMaterial]:
        return list(self.db.scalars(select(ApplicationMaterial).where(
            ApplicationMaterial.owner_user_id == owner_id,
            ApplicationMaterial.package_id == package_id,
        ).order_by(ApplicationMaterial.created_at, ApplicationMaterial.id)))

    def material(self, owner_id: UUID, material_id: UUID, *, for_update: bool = False) -> ApplicationMaterial | None:
        statement = select(ApplicationMaterial).where(
            ApplicationMaterial.id == material_id, ApplicationMaterial.owner_user_id == owner_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def reusable_material(self, owner_id: UUID, package_id: UUID, material_type: str) -> ApplicationMaterial | None:
        return self.db.scalar(select(ApplicationMaterial).where(
            ApplicationMaterial.owner_user_id == owner_id,
            ApplicationMaterial.package_id == package_id,
            ApplicationMaterial.material_type == material_type,
            ApplicationMaterial.status != "archived",
        ).order_by(ApplicationMaterial.created_at.desc()).limit(1))

    def version(self, owner_id: UUID, version_id: UUID) -> ApplicationMaterialVersion | None:
        return self.db.scalar(select(ApplicationMaterialVersion).join(
            ApplicationMaterial, ApplicationMaterial.id == ApplicationMaterialVersion.material_id,
        ).where(
            ApplicationMaterialVersion.id == version_id,
            ApplicationMaterial.owner_user_id == owner_id,
        ))

    def versions(self, owner_id: UUID, material_id: UUID) -> list[ApplicationMaterialVersion]:
        return list(self.db.scalars(select(ApplicationMaterialVersion).join(
            ApplicationMaterial, ApplicationMaterial.id == ApplicationMaterialVersion.material_id,
        ).where(
            ApplicationMaterial.owner_user_id == owner_id,
            ApplicationMaterialVersion.material_id == material_id,
        ).order_by(ApplicationMaterialVersion.version_number.desc())))

    def next_version(self, material_id: UUID) -> int:
        return int(self.db.scalar(select(func.max(ApplicationMaterialVersion.version_number)).where(
            ApplicationMaterialVersion.material_id == material_id,
        )) or 0) + 1

    def evidence(self, owner_id: UUID, version_id: UUID) -> list[MaterialEvidenceLink]:
        return list(self.db.scalars(select(MaterialEvidenceLink).join(
            ApplicationMaterialVersion,
            ApplicationMaterialVersion.id == MaterialEvidenceLink.material_version_id,
        ).join(ApplicationMaterial, ApplicationMaterial.id == ApplicationMaterialVersion.material_id).where(
            ApplicationMaterial.owner_user_id == owner_id,
            MaterialEvidenceLink.material_version_id == version_id,
        ).order_by(MaterialEvidenceLink.claim_key)))

    def evidence_link(
        self, owner_id: UUID, version_id: UUID, evidence_id: UUID, *, for_update: bool = False,
    ) -> MaterialEvidenceLink | None:
        statement = select(MaterialEvidenceLink).join(
            ApplicationMaterialVersion,
            ApplicationMaterialVersion.id == MaterialEvidenceLink.material_version_id,
        ).join(ApplicationMaterial, ApplicationMaterial.id == ApplicationMaterialVersion.material_id).where(
            ApplicationMaterial.owner_user_id == owner_id,
            MaterialEvidenceLink.material_version_id == version_id,
            MaterialEvidenceLink.id == evidence_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def reviews(self, owner_id: UUID, version_id: UUID) -> list[MaterialReview]:
        return list(self.db.scalars(select(MaterialReview).join(
            ApplicationMaterialVersion, ApplicationMaterialVersion.id == MaterialReview.material_version_id,
        ).join(ApplicationMaterial, ApplicationMaterial.id == ApplicationMaterialVersion.material_id).where(
            ApplicationMaterial.owner_user_id == owner_id,
            MaterialReview.material_version_id == version_id,
        ).order_by(MaterialReview.created_at)))
