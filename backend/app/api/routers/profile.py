"""Owned Career Profile CRUD and immutable revision history."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status

from app.api.dependencies import CurrentUser, DbSession
from app.profile.schemas import ProfileItemPayload, ProfilePreferencePayload, ProfileUpdate
from app.profile.service import ProfileNotFound, ProfileService, StaleProfile


router = APIRouter(prefix="/api/profile", tags=["career-profile"])
ResourceName = Literal[
    "experiences", "educations", "projects", "skills", "languages", "certifications"
]


def _expected(if_match: str | None) -> int:
    if not if_match:
        raise HTTPException(status_code=428, detail="If-Match profile revision is required.")
    value = if_match.strip().removeprefix("W/").strip('"')
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="If-Match must be a profile revision integer.") from exc


def _raise(exc: Exception) -> None:
    if isinstance(exc, StaleProfile):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ProfileNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def get_profile(db: DbSession, user: CurrentUser) -> dict[str, object]:
    return ProfileService(db, user.id).get()


@router.put("")
def put_profile(payload: ProfileUpdate, db: DbSession, user: CurrentUser) -> dict[str, object]:
    values = payload.model_dump(exclude={"revision"}, mode="json")
    try:
        return ProfileService(db, user.id).update_profile(values, payload.revision)
    except (StaleProfile, ValueError) as exc:
        _raise(exc)


@router.get("/preferences")
def get_preferences(db: DbSession, user: CurrentUser) -> dict[str, object] | None:
    return ProfileService(db, user.id).get_preference()


@router.put("/preferences")
def put_preferences(
    payload: ProfilePreferencePayload,
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, object]:
    try:
        return ProfileService(db, user.id).set_preference(
            payload.model_dump(mode="json"), _expected(if_match)
        )
    except (StaleProfile, ValueError) as exc:
        _raise(exc)


@router.delete("/preferences")
def delete_preferences(
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, bool]:
    try:
        ProfileService(db, user.id).delete_preference(_expected(if_match))
        return {"deleted": True}
    except (StaleProfile, ValueError) as exc:
        _raise(exc)


@router.get("/revisions")
def get_revisions(db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    return ProfileService(db, user.id).revisions()


@router.get("/revisions/{revision}")
def get_revision(revision: int, db: DbSession, user: CurrentUser) -> dict[str, object]:
    try:
        return ProfileService(db, user.id).revision(revision)
    except ProfileNotFound as exc:
        _raise(exc)


@router.post("/revisions/{revision}/restore")
def restore_revision(
    revision: int,
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, object]:
    try:
        return ProfileService(db, user.id).restore(revision, _expected(if_match))
    except (ProfileNotFound, StaleProfile, ValueError) as exc:
        _raise(exc)


@router.get("/{resource}")
def list_items(resource: ResourceName, db: DbSession, user: CurrentUser) -> list[dict[str, object]]:
    return ProfileService(db, user.id).list_items(resource)


@router.post("/{resource}", status_code=status.HTTP_201_CREATED)
def create_item(
    resource: ResourceName,
    payload: ProfileItemPayload,
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, object]:
    try:
        return ProfileService(db, user.id).create_item(
            resource, payload.model_dump(mode="json"), _expected(if_match)
        )
    except (StaleProfile, ValueError) as exc:
        _raise(exc)


@router.patch("/{resource}/{item_id}")
def patch_item(
    resource: ResourceName,
    item_id: UUID,
    payload: ProfileItemPayload,
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, object]:
    try:
        return ProfileService(db, user.id).update_item(
            resource,
            item_id,
            payload.model_dump(exclude_unset=True, mode="json"),
            _expected(if_match),
        )
    except (ProfileNotFound, StaleProfile, ValueError) as exc:
        _raise(exc)


@router.delete("/{resource}/{item_id}")
def delete_item(
    resource: ResourceName,
    item_id: UUID,
    db: DbSession,
    user: CurrentUser,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, bool]:
    try:
        ProfileService(db, user.id).delete_item(resource, item_id, _expected(if_match))
        return {"deleted": True}
    except (ProfileNotFound, StaleProfile, ValueError) as exc:
        _raise(exc)
