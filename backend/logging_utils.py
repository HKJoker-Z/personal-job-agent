"""Privacy-aware structured logging and request correlation utilities."""

from __future__ import annotations

import json
import logging
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
request_id_context: ContextVar[str] = ContextVar("request_id", default="")


def safe_request_id(candidate: str | None) -> str:
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return str(uuid4())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", "") or request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in (
            "workflow_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "error_code",
            "error_stage",
        ):
            value = getattr(record, field, None)
            if value not in (None, ""):
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    allowed_fields = {
        key: value
        for key, value in fields.items()
        if key
        in {
            "request_id",
            "workflow_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "error_code",
            "error_stage",
        }
    }
    logger.log(level, message, extra=allowed_fields)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, logger: logging.Logger):
        super().__init__(app)
        self.logger = logger

    async def dispatch(self, request: Request, call_next: Any):
        request_id = safe_request_id(request.headers.get("X-Request-ID"))
        token = request_id_context.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter_ns()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_ms = round(max(0, time.perf_counter_ns() - started) / 1_000_000, 3)
            route = getattr(request.scope.get("route"), "path", request.url.path)
            try:
                log_event(
                    self.logger,
                    logging.INFO if status_code < 500 else logging.ERROR,
                    "http_request_completed",
                    request_id=request_id,
                    workflow_id=getattr(request.state, "workflow_id", ""),
                    method=request.method,
                    route=route,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    error_code=getattr(request.state, "error_code", ""),
                    error_stage=getattr(request.state, "error_stage", ""),
                )
            except Exception:
                pass
            request_id_context.reset(token)
