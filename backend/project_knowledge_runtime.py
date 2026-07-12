"""Runtime path and seed initialization helpers for writable Project Knowledge."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from config import AppConfig, load_config


PROJECT_KNOWLEDGE_LOGICAL_NAME = "PROJECT_KNOWLEDGE.md"


def get_project_knowledge_path(config: AppConfig | None = None) -> Path:
    return (config or load_config(validate_production=False)).project_knowledge_path


def get_project_knowledge_seed_path(config: AppConfig | None = None) -> Path:
    return (config or load_config(validate_production=False)).project_knowledge_seed_path


def initialize_project_knowledge(config: AppConfig | None = None) -> bool:
    """Seed the writable file once, using an atomic replacement without overwriting user data."""
    settings = config or load_config(validate_production=False)
    target = settings.project_knowledge_path
    if target.is_file():
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    seed = settings.project_knowledge_seed_path
    if not seed.is_file() or seed.resolve(strict=False) == target.resolve(strict=False):
        return False
    temporary = target.with_name(f".{target.name}.seed.tmp")
    try:
        with seed.open("rb") as source, temporary.open("xb") as destination:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    except FileExistsError:
        return target.is_file()
    finally:
        if temporary.exists():
            temporary.unlink()
    return target.is_file()
