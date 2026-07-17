"""Lazy SQLAlchemy engine construction; importing this module never connects."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import load_v2_settings


@lru_cache(maxsize=4)
def build_engine(database_url: str | None = None) -> Engine:
    settings = load_v2_settings()
    url = database_url or settings.database_url
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if url == "sqlite+pysqlite:///:memory:":
        kwargs.update(
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    elif url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": settings.database_connect_timeout_seconds}
    else:
        kwargs["connect_args"] = {"connect_timeout": settings.database_connect_timeout_seconds}
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
        kwargs["pool_timeout"] = settings.database_connect_timeout_seconds
    return create_engine(url, **kwargs)


def dispose_engines() -> None:
    build_engine.cache_clear()
