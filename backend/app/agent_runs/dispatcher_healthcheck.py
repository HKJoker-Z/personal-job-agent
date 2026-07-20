"""Check dispatcher heartbeat plus its private PostgreSQL and Redis dependencies."""

from __future__ import annotations

import os
import time
from pathlib import Path

from redis import Redis
from sqlalchemy import text

from app.core.config import load_v2_settings
from app.db.engine import build_engine


def main() -> int:
    heartbeat = Path(os.getenv("OUTBOX_HEARTBEAT_FILE", "/tmp/outbox-dispatcher.heartbeat"))
    if not heartbeat.is_file() or time.time() - heartbeat.stat().st_mtime > 30:
        return 1
    settings = load_v2_settings()
    try:
        with build_engine(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        try:
            return 0 if client.ping() is True else 1
        finally:
            client.close()
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
