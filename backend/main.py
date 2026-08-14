"""ASGI entry point for the single application factory."""

from app.application import create_application
# Keep the small set of existing module-level compatibility exports explicit
# while callers migrate away from the transitional legacy module.
from legacy_application import (
    health_check,
    project_knowledge_status_data,
    write_project_knowledge_file,
)


app = create_application()
