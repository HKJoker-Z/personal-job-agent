"""Container-local Redis, database, and Worker heartbeat healthcheck."""

from __future__ import annotations

import os
from datetime import timedelta

from redis import Redis

from app.core.config import load_v2_settings
from app.db.models import WorkerHeartbeat, ensure_utc, utc_now
from app.db.session import session_factory


def main() -> int:
    settings = load_v2_settings()
    worker_id = os.getenv("AGENT_WORKER_ID", "").strip()[:120]
    if not worker_id:
        return 1
    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        if client.ping() is not True:
            return 1
    except Exception:
        return 1
    finally:
        client.close()
    db = session_factory()()
    try:
        heartbeat = db.get(WorkerHeartbeat, worker_id)
        if heartbeat is None or heartbeat.status not in {"ready", "busy"}:
            return 1
        cutoff = utc_now() - timedelta(seconds=settings.worker_stale_seconds)
        return 0 if ensure_utc(heartbeat.last_heartbeat_at) >= cutoff else 1
    except Exception:
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
