"""Application composition for the Version 2 transitional architecture."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import agent_runs, auth, dashboard, profile, resumes, system
from app.auth.middleware import V2SecurityMiddleware
from app.core.config import load_v2_settings
from app.feature_retirement import FeatureRetirementMiddleware


def extend_application(app: FastAPI) -> FastAPI:
    settings = load_v2_settings()
    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(resumes.router)
    app.include_router(agent_runs.router)
    app.include_router(dashboard.router)
    app.include_router(system.router)
    # Security remains outermost: unauthenticated requests still fail closed,
    # and authenticated retired endpoints receive the uniform 410 response.
    app.add_middleware(FeatureRetirementMiddleware)
    app.add_middleware(V2SecurityMiddleware, settings=settings)
    return app


def create_application() -> FastAPI:
    from legacy_application import app as legacy_app

    return extend_application(legacy_app)
