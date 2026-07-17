"""Application composition for the Version 2 transitional architecture."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import agent_runs, applications, auth, dashboard, jobs, matching, materials, profile, resumes, system, tasks
from app.auth.middleware import V2SecurityMiddleware
from app.core.config import load_v2_settings


def extend_application(app: FastAPI) -> FastAPI:
    settings = load_v2_settings()
    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(resumes.router)
    # Static /api/jobs/rank must be registered before the legacy /api/jobs/{job_id} route.
    app.include_router(matching.router)
    app.include_router(jobs.router)
    app.include_router(applications.router)
    app.include_router(materials.router)
    app.include_router(agent_runs.router)
    app.include_router(tasks.router)
    app.include_router(dashboard.router)
    app.include_router(system.router)
    app.add_middleware(V2SecurityMiddleware, settings=settings)
    return app


def create_application() -> FastAPI:
    from legacy_application import app as legacy_app

    return extend_application(legacy_app)
