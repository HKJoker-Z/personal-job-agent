"""Authenticated administrative system status."""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUser
from app.readiness import detailed_status


router = APIRouter(tags=["system"])


@router.get("/api/admin/readiness")
def admin_readiness(user: CurrentUser) -> dict[str, object]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required.")
    return detailed_status()
