"""Shared test-only helpers for isolated SQLite integration and unit tests."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from database import assert_safe_test_database, init_db


_MISSING = object()


@contextmanager
def temporary_test_database() -> Iterator[Path]:
    """Create, migrate, and remove a database without changing the application database."""
    previous_env = {
        "APP_ENV": os.environ.get("APP_ENV", _MISSING),
        "APP_DATABASE_PATH": os.environ.get("APP_DATABASE_PATH", _MISSING),
    }
    with tempfile.TemporaryDirectory(prefix="personal-job-agent-test-") as temporary_directory:
        database_path = Path(temporary_directory) / "app.db"
        os.environ["APP_ENV"] = "test"
        os.environ["APP_DATABASE_PATH"] = str(database_path)
        try:
            assert_safe_test_database(database_path, "test")
            init_db()
            yield database_path
        finally:
            for name, original_value in previous_env.items():
                if original_value is _MISSING:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = str(original_value)
