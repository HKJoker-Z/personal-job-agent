"""Safe, exact Provider exception classification.

The OpenAI-compatible SDK intentionally has a broad exception boundary. This
module walks only exception types and explicit status fields; it never reads or
logs exception text, request bodies, headers, or credentials.
"""

from __future__ import annotations

from collections.abc import Iterator
import ssl

import httpx
import httpcore
from openai import InternalServerError, RateLimitError

from provider_deadline import (
    ProviderAttemptDeadlineExceeded,
    ProviderPhaseDeadlineExceeded,
)


CONNECT_TIMEOUT = "connect_timeout"
CONNECT_ERROR = "connect_error"
READ_TIMEOUT = "read_timeout"
READ_ERROR = "read_error"
WRITE_TIMEOUT = "write_timeout"
WRITE_ERROR = "write_error"
POOL_TIMEOUT = "pool_timeout"
REMOTE_PROTOCOL_ERROR = "remote_protocol_error"
LOCAL_PROTOCOL_ERROR = "local_protocol_error"
PROXY_ERROR = "proxy_error"
TLS_OR_CONNECT_ERROR = "tls_or_connect_error"
PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED = "provider_attempt_deadline_exhausted"
PROVIDER_PHASE_DEADLINE_EXHAUSTED = "provider_phase_deadline_exhausted"
TRANSIENT_HTTP_429 = "transient_http_429"
TRANSIENT_HTTP_5XX = "transient_http_5xx"
# Kept as a compatibility category for observations written by the previous
# implementation. New concrete exceptions use the categories above or the
# bounded ``transport_error_other`` category below.
TRANSPORT_ERROR = "transport_error"
TRANSPORT_ERROR_OTHER = "transport_error_other"
UNKNOWN_BOUNDED_PROVIDER_ERROR = "unknown_bounded_provider_error"

COMPONENT_TIMEOUT_CATEGORIES = frozenset({
    CONNECT_TIMEOUT,
    READ_TIMEOUT,
    WRITE_TIMEOUT,
    POOL_TIMEOUT,
})
PROVIDER_ERROR_CATEGORIES = frozenset({
    *COMPONENT_TIMEOUT_CATEGORIES,
    CONNECT_ERROR,
    READ_ERROR,
    WRITE_ERROR,
    REMOTE_PROTOCOL_ERROR,
    LOCAL_PROTOCOL_ERROR,
    PROXY_ERROR,
    TLS_OR_CONNECT_ERROR,
    PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED,
    PROVIDER_PHASE_DEADLINE_EXHAUSTED,
    TRANSIENT_HTTP_429,
    TRANSIENT_HTTP_5XX,
    TRANSPORT_ERROR,
    TRANSPORT_ERROR_OTHER,
    UNKNOWN_BOUNDED_PROVIDER_ERROR,
})
RETRYABLE_PROVIDER_CATEGORIES = frozenset({
    *COMPONENT_TIMEOUT_CATEGORIES,
    CONNECT_ERROR,
    READ_ERROR,
    WRITE_ERROR,
    REMOTE_PROTOCOL_ERROR,
    LOCAL_PROTOCOL_ERROR,
    PROXY_ERROR,
    TLS_OR_CONNECT_ERROR,
    PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED,
    TRANSIENT_HTTP_429,
    TRANSIENT_HTTP_5XX,
    TRANSPORT_ERROR,
    TRANSPORT_ERROR_OTHER,
})

_SAFE_EXCEPTION_CLASS_NAMES = frozenset({
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "RateLimitError",
    "InternalServerError",
    "ConnectTimeout",
    "ConnectError",
    "ReadTimeout",
    "ReadError",
    "WriteTimeout",
    "WriteError",
    "PoolTimeout",
    "RemoteProtocolError",
    "LocalProtocolError",
    "ProxyError",
    "TimeoutException",
    "TransportError",
    "NetworkError",
    "ProtocolError",
    "SSLError",
})


def _exception_chain(exc: BaseException, *, maximum: int = 8) -> Iterator[BaseException]:
    """Yield a bounded cause/context chain without inspecting exception text."""
    current: BaseException | None = exc
    seen: set[int] = set()
    for _ in range(maximum):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        cause = current.__cause__
        if cause is not None:
            current = cause
        elif not current.__suppress_context__:
            current = current.__context__
        else:
            current = None


def _status_code(value: BaseException) -> int | None:
    status_code = getattr(value, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def classify_provider_exception(exc: BaseException) -> str:
    """Return one bounded category observable at the SDK/HTTPX boundary."""
    chain = tuple(_exception_chain(exc))

    # These custom transport exceptions are deliberately checked before their
    # httpx.ReadTimeout parent so an absolute deadline cannot be mislabeled as
    # an ordinary response-read timeout.
    if any(isinstance(item, ProviderAttemptDeadlineExceeded) for item in chain):
        return PROVIDER_ATTEMPT_DEADLINE_EXHAUSTED
    if any(isinstance(item, ProviderPhaseDeadlineExceeded) for item in chain):
        return PROVIDER_PHASE_DEADLINE_EXHAUSTED

    if any(isinstance(item, httpx.ConnectTimeout) for item in chain):
        return CONNECT_TIMEOUT
    if any(isinstance(item, httpx.ReadTimeout) for item in chain):
        return READ_TIMEOUT
    if any(isinstance(item, httpx.WriteTimeout) for item in chain):
        return WRITE_TIMEOUT
    if any(isinstance(item, httpx.PoolTimeout) for item in chain):
        return POOL_TIMEOUT

    status_codes = tuple(
        status
        for item in chain
        for status in (_status_code(item),)
        if status is not None
    )
    if isinstance(exc, RateLimitError) or 429 in status_codes:
        return TRANSIENT_HTTP_429
    if isinstance(exc, InternalServerError) or any(500 <= status <= 599 for status in status_codes):
        return TRANSIENT_HTTP_5XX

    # HTTPX and HTTPcore expose phase-specific failures. Check TLS before the
    # broader connection classes because the installed clients wrap TLS
    # handshake errors as ConnectError/APIConnectionError.
    if any(isinstance(item, ssl.SSLError) for item in chain):
        return TLS_OR_CONNECT_ERROR
    if any(isinstance(item, (httpx.ProxyError, httpcore.ProxyError)) for item in chain):
        return PROXY_ERROR
    if any(isinstance(item, (httpx.RemoteProtocolError, httpcore.RemoteProtocolError)) for item in chain):
        return REMOTE_PROTOCOL_ERROR
    if any(isinstance(item, (httpx.LocalProtocolError, httpcore.LocalProtocolError)) for item in chain):
        return LOCAL_PROTOCOL_ERROR
    if any(isinstance(item, (httpx.ConnectError, httpcore.ConnectError)) for item in chain):
        return CONNECT_ERROR
    if any(isinstance(item, (httpx.ReadError, httpcore.ReadError)) for item in chain):
        return READ_ERROR
    if any(isinstance(item, (httpx.WriteError, httpcore.WriteError)) for item in chain):
        return WRITE_ERROR

    # A generic concrete network/protocol cause is bounded but does not expose
    # a reliable phase boundary. APIConnectionError itself is intentionally
    # not enough evidence: OpenAI uses it for every non-timeout exception.
    if any(
        isinstance(item, (
            httpx.TransportError,
            httpcore.NetworkError,
            httpcore.ProtocolError,
            ConnectionError,
            OSError,
        ))
        and not isinstance(item, TimeoutError)
        for item in chain
    ):
        return TRANSPORT_ERROR_OTHER

    # APITimeoutError, APIConnectionError, generic TimeoutError and generic
    # Exception values are bounded but do not expose a component boundary.
    return UNKNOWN_BOUNDED_PROVIDER_ERROR


def safe_exception_class_names(exc: BaseException, *, maximum: int = 4) -> list[str]:
    """Return only allowlisted SDK/HTTPX/TLS class names from a bounded chain."""
    names: list[str] = []
    for item in _exception_chain(exc):
        name = type(item).__name__
        if name in _SAFE_EXCEPTION_CLASS_NAMES and name not in names:
            names.append(name)
        if len(names) >= maximum:
            break
    return names


def retry_category(category: str, *, exception: BaseException | None = None) -> str | None:
    """Return the category eligible for the one application retry.

    Preserve the historical retry for a bare Python timeout while keeping its
    observability category honest: without an HTTPX boundary it is unknown,
    not a fabricated read or connect timeout. Other unknown exceptions remain
    non-retryable.
    """
    if category in RETRYABLE_PROVIDER_CATEGORIES:
        return category
    if category == UNKNOWN_BOUNDED_PROVIDER_ERROR and isinstance(exception, TimeoutError):
        return category
    return None
