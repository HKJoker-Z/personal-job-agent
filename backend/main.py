"""Compatibility entry point for Uvicorn and existing imports."""

from legacy_application import *  # noqa: F401,F403
from legacy_application import app as legacy_app

from app.application import extend_application


app = extend_application(legacy_app)
