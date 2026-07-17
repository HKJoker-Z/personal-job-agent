"""Dramatiq Redis Broker configured with JSON-only message encoding."""

from __future__ import annotations

from functools import lru_cache

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.encoder import JSONEncoder

from app.core.config import load_v2_settings


@lru_cache(maxsize=1)
def configure_broker() -> RedisBroker:
    settings = load_v2_settings()
    dramatiq.set_encoder(JSONEncoder())
    broker = RedisBroker(url=settings.redis_url, namespace=settings.redis_queue_namespace)
    dramatiq.set_broker(broker)
    return broker


broker = configure_broker()
