"""Application factory and composition for the transitional architecture."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.routers import agent_runs, auth, dashboard, profile, resumes, system
from app.analyze.idempotency import AnalyzeIdempotencyFailureMiddleware
from app.auth.middleware import V2SecurityMiddleware
from app.core.config import load_v2_settings
from app.feature_retirement import FeatureRetirementMiddleware
from logging_utils import RequestLoggingMiddleware


def _remove_inner_request_logging(app: FastAPI) -> None:
    """Move the legacy logger outside Version 2 security during composition."""
    app.user_middleware = [
        middleware
        for middleware in app.user_middleware
        if middleware.cls is not RequestLoggingMiddleware
    ]


def _compose_application(app: FastAPI) -> FastAPI:
    settings = load_v2_settings()
    _remove_inner_request_logging(app)
    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(resumes.router)
    app.include_router(agent_runs.router)
    app.include_router(dashboard.router)
    app.include_router(system.router)
    # Security remains outside feature routing so unauthenticated requests fail
    # closed. Correlation is added last so it wraps every security outcome.
    app.add_middleware(AnalyzeIdempotencyFailureMiddleware)
    app.add_middleware(FeatureRetirementMiddleware)
    app.add_middleware(V2SecurityMiddleware, settings=settings)
    app.add_middleware(
        RequestLoggingMiddleware,
        logger=logging.getLogger("personal-job-agent"),
    )
    return app


def extend_application(app: FastAPI) -> FastAPI:
    """Compose the legacy app for compatibility callers and test harnesses."""
    return _compose_application(app)


def create_application() -> FastAPI:
    """Build the ASGI application used by Uvicorn and production containers."""
    from legacy_application import app as legacy_app

    return _compose_application(legacy_app)
