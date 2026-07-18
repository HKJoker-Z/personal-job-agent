"""Cross-process SSE connection accounting using Redis in production."""

from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from uuid import UUID

from redis import Redis

from app.core.config import V2Settings


class ConnectionLimitReached(RuntimeError):
    pass


class ConnectionLimiterUnavailable(RuntimeError):
    pass


_local_lock = threading.Lock()
_local_connections: dict[UUID, int] = defaultdict(int)


class SSEConnectionLimiter:
    def __init__(self, settings: V2Settings):
        self.settings = settings
        self.use_redis = settings.readiness_require_redis
        self.ttl_seconds = max(settings.sse_heartbeat_seconds * 4, 60)

    def _key(self, owner_id: UUID) -> str:
        digest = hashlib.sha256(str(owner_id).encode()).hexdigest()
        return f"{self.settings.redis_queue_namespace}:sse:{digest}"

    def _client(self) -> Redis:
        return Redis.from_url(
            self.settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )

    def acquire(self, owner_id: UUID) -> None:
        if not self.use_redis:
            with _local_lock:
                if _local_connections[owner_id] >= self.settings.sse_max_connections_per_user:
                    raise ConnectionLimitReached("SSE connection limit reached.")
                _local_connections[owner_id] += 1
            return
        client = self._client()
        key = self._key(owner_id)
        try:
            count = int(client.incr(key))
            client.expire(key, self.ttl_seconds)
            if count > self.settings.sse_max_connections_per_user:
                client.eval(
                    "local n=redis.call('decr',KEYS[1]); if n<=0 then redis.call('del',KEYS[1]) end; return n",
                    1,
                    key,
                )
                raise ConnectionLimitReached("SSE connection limit reached.")
        except ConnectionLimitReached:
            raise
        except Exception as exc:
            raise ConnectionLimiterUnavailable("SSE coordination is unavailable.") from exc
        finally:
            client.close()

    def touch(self, owner_id: UUID) -> None:
        if not self.use_redis:
            return
        client = self._client()
        try:
            client.expire(self._key(owner_id), self.ttl_seconds)
        except Exception:
            pass
        finally:
            client.close()

    def release(self, owner_id: UUID) -> None:
        if not self.use_redis:
            with _local_lock:
                _local_connections[owner_id] = max(_local_connections[owner_id] - 1, 0)
            return
        client = self._client()
        try:
            client.eval(
                "local n=redis.call('decr',KEYS[1]); if n<=0 then redis.call('del',KEYS[1]) end; return n",
                1,
                self._key(owner_id),
            )
        except Exception:
            pass
        finally:
            client.close()
