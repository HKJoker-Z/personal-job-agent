"""Standalone supervisor for the PostgreSQL transactional Outbox."""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path

from app.agent_runs.outbox import dispatch_batch, recover_orphaned_deliveries, recover_stale_publications


def main() -> int:
    dispatcher_id = (os.getenv("AGENT_DISPATCHER_ID", "outbox-primary").strip() or "outbox-primary")[:120]
    heartbeat = Path(os.getenv("OUTBOX_HEARTBEAT_FILE", "/tmp/outbox-dispatcher.heartbeat"))
    stop = threading.Event()

    def shutdown(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stop.is_set():
        try:
            recover_stale_publications()
            recover_orphaned_deliveries()
            dispatch_batch(dispatcher_id)
            heartbeat.touch(mode=0o600, exist_ok=True)
        except Exception:
            # The next bounded loop retries; readiness fails if heartbeats stop.
            pass
        stop.wait(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
