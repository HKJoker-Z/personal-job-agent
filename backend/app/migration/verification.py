"""Content-free migration aggregate verification."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Iterable


def aggregate_checksum(rows: Iterable[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        safe_parts = tuple(
            _canonical(value)
            for value in (
                row.get("id", ""),
                row.get("run_id", ""),
                row.get("workflow_id", ""),
                row.get("created_at", row.get("started_at", "")),
            )
        )
        digest.update("\x1f".join(safe_parts).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _canonical(value: object) -> str:
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc).isoformat(timespec="seconds")
    if isinstance(value, str) and ("T" in value or " " in value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            return aware.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            return value
    return str(value)
