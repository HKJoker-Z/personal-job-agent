"""Version 2.0.2 public API retirement boundary.

The ORM models and tables intentionally remain available for backup, restore,
rollback, and internal compatibility tests. Public requests cannot use the
retired workflows.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


REMOVED_API_PREFIXES = (
    "/api/jobs",
    "/api/applications",
    "/api/approvals",
    "/api/tasks",
    "/api/application-packages",
    "/api/application-materials",
    "/api/material-versions",
    "/api/job-rank-runs",
)


def is_removed_api(path: str, method: str) -> bool:
    if any(path == prefix or path.startswith(f"{prefix}/") for prefix in REMOVED_API_PREFIXES):
        return True
    # Existing Agent Runs remain readable and cancellable. New package-based
    # Runs, retries, and resumes are retired with the Application workflow.
    if path == "/api/agent-runs" and method == "POST":
        return True
    if path.startswith("/api/agent-runs/") and path.endswith(("/retry", "/resume")):
        return True
    return False


class FeatureRetirementMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if is_removed_api(request.url.path, request.method):
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "code": "FEATURE_REMOVED",
                        "message": "This feature is not available in Version 2.0.2.",
                    }
                },
            )
        return await call_next(request)
