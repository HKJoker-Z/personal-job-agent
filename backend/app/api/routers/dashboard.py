"""Current-user job-search dashboard."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.dashboard.service import DashboardService


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(db: DbSession, user: CurrentUser) -> dict[str, object]:
    return DashboardService(db, user.id).summary()
