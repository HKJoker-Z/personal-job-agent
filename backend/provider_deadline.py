"""Bounded monotonic deadlines for the synchronous Provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time

import httpx


# The external candidate client contract is 180 seconds.  Keep a small margin
# for ASGI response delivery and the reverse proxy without changing that
# external contract.
ANALYZE_EXTERNAL_CLIENT_TIMEOUT_SECONDS = 180.0
ANALYZE_CLIENT_SAFETY_MARGIN_SECONDS = 5.0
ANALYZE_TOTAL_SAFETY_DEADLINE_SECONDS = (
    ANALYZE_EXTERNAL_CLIENT_TIMEOUT_SECONDS - ANALYZE_CLIENT_SAFETY_MARGIN_SECONDS
)

# Local parsing, deterministic fallback, final security processing, the
# History/idempotency transaction, and JSON serialization are intentionally
# reserved before another Provider call is started.
PROVIDER_FALLBACK_FINALIZATION_RESERVE_SECONDS = 30.0
PROVIDER_RETRY_RESERVE_SECONDS = 0.25
PROVIDER_REPAIR_RESERVE_SECONDS = 5.0
PROVIDER_MIN_CALL_BUDGET_SECONDS = 1.0

# These are the component defaults used when a configured attempt has enough
# remaining budget.  The actual values are always capped by the remaining
# monotonic deadline and the configured REQUEST_TIMEOUT_SECONDS.
PROVIDER_CONNECT_TIMEOUT_SECONDS = 5.0
PROVIDER_WRITE_TIMEOUT_SECONDS = 10.0
PROVIDER_POOL_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ProviderAttemptTimeout:
    """One request timeout derived from one absolute Provider deadline."""

    timeout: httpx.Timeout
    budget_seconds: float
    remaining_seconds: float
    remaining_bucket: str


class ProviderDeadline:
    """An absolute monotonic deadline shared by primary and repair calls."""

    def __init__(
        self,
        absolute_deadline: float,
        *,
        finalization_reserve_seconds: float = PROVIDER_FALLBACK_FINALIZATION_RESERVE_SECONDS,
        retry_reserve_seconds: float = PROVIDER_RETRY_RESERVE_SECONDS,
        repair_reserve_seconds: float = PROVIDER_REPAIR_RESERVE_SECONDS,
        minimum_call_budget_seconds: float = PROVIDER_MIN_CALL_BUDGET_SECONDS,
    ) -> None:
        self.absolute_deadline = float(absolute_deadline)
        self.finalization_reserve_seconds = max(0.0, float(finalization_reserve_seconds))
        self.retry_reserve_seconds = max(0.0, float(retry_reserve_seconds))
        self.repair_reserve_seconds = max(0.0, float(repair_reserve_seconds))
        self.minimum_call_budget_seconds = max(0.1, float(minimum_call_budget_seconds))

    @classmethod
    def for_phase(
        cls,
        *,
        phase_started_monotonic: float,
        configured_deadline_seconds: float,
        request_safety_deadline: float | None = None,
    ) -> "ProviderDeadline":
        phase_deadline = float(phase_started_monotonic) + max(
            0.0, float(configured_deadline_seconds)
        )
        if request_safety_deadline is not None:
            phase_deadline = min(
                phase_deadline,
                float(request_safety_deadline) - PROVIDER_FALLBACK_FINALIZATION_RESERVE_SECONDS,
            )
        return cls(phase_deadline)

    def remaining_seconds(self, now: float | None = None) -> float:
        return self.absolute_deadline - (time.monotonic() if now is None else float(now))

    def expired(self, now: float | None = None) -> bool:
        return self.remaining_seconds(now) <= 0.0

    def remaining_bucket(self, now: float | None = None) -> str:
        remaining = self.remaining_seconds(now)
        if remaining <= 0.0:
            return "exhausted"
        if remaining <= 10.0:
            return "1_10s"
        if remaining <= 30.0:
            return "11_30s"
        if remaining <= 60.0:
            return "31_60s"
        return "gt_60s"

    def _continuation_reserve(self, kind: str) -> float:
        if kind == "retry":
            return self.retry_reserve_seconds
        if kind == "repair":
            return self.repair_reserve_seconds
        return 0.0

    def call_timeout(
        self,
        *,
        configured_timeout_seconds: float,
        kind: str = "primary",
        now: float | None = None,
    ) -> ProviderAttemptTimeout | None:
        """Return a bounded component timeout, or None when a call is unsafe."""
        remaining = self.remaining_seconds(now)
        available = (
            remaining
            - self.finalization_reserve_seconds
            - self._continuation_reserve(kind)
        )
        budget = min(max(0.0, float(configured_timeout_seconds)), available)
        if budget < self.minimum_call_budget_seconds:
            return None
        timeout = httpx.Timeout(
            connect=min(PROVIDER_CONNECT_TIMEOUT_SECONDS, budget),
            read=budget,
            write=min(PROVIDER_WRITE_TIMEOUT_SECONDS, budget),
            pool=min(PROVIDER_POOL_TIMEOUT_SECONDS, budget),
        )
        return ProviderAttemptTimeout(
            timeout=timeout,
            budget_seconds=round(budget, 3),
            remaining_seconds=round(remaining, 3),
            remaining_bucket=self.remaining_bucket(now),
        )

    def can_start(self, *, configured_timeout_seconds: float, kind: str = "primary") -> bool:
        return self.call_timeout(
            configured_timeout_seconds=configured_timeout_seconds,
            kind=kind,
        ) is not None


class _DeadlineSyncByteStream(httpx.SyncByteStream):
    """Stop a response body whose chunks outlive the absolute deadline."""

    def __init__(
        self,
        stream: httpx.SyncByteStream,
        deadline_monotonic: float,
        request: httpx.Request,
    ) -> None:
        self._stream = stream
        self._deadline_monotonic = deadline_monotonic
        self._request = request

    def _read_next(self, iterator: object) -> tuple[str, object]:
        """Read one transport chunk without allowing a blocking read past deadline."""
        outcome: list[tuple[str, object]] = []
        completed = threading.Event()

        def read_chunk() -> None:
            try:
                outcome.append(("chunk", next(iterator)))  # type: ignore[arg-type]
            except StopIteration:
                outcome.append(("stop", None))
            except BaseException as exc:
                outcome.append(("error", exc))
            finally:
                completed.set()

        worker = threading.Thread(target=read_chunk, daemon=True)
        worker.start()
        remaining = max(0.0, self._deadline_monotonic - time.monotonic())
        if not completed.wait(remaining):
            self.close()
            completed.wait(0.2)
            raise httpx.ReadTimeout(
                "Provider response deadline exhausted",
                request=self._request,
            )
        kind, value = outcome[0]
        if kind == "error":
            raise value  # type: ignore[misc]
        return kind, value

    def __iter__(self):
        iterator = iter(self._stream)
        while True:
            if time.monotonic() >= self._deadline_monotonic:
                self.close()
                raise httpx.ReadTimeout(
                    "Provider response deadline exhausted",
                    request=self._request,
                )
            kind, chunk = self._read_next(iterator)
            if kind == "stop":
                return
            yield chunk  # type: ignore[misc]

    def close(self) -> None:
        self._stream.close()


class DeadlineHttpxClient(httpx.Client):
    """HTTPX client with per-phase timeouts and a hard total response bound.

    The OpenAI-compatible SDK accepts a synchronous ``httpx.Client``.  HTTPX
    read timeouts are per read operation, so a server that emits small chunks
    repeatedly could otherwise keep a response alive past the application
    deadline.  This wrapper forces the non-streaming SDK path through a
    deadline-aware byte stream while retaining HTTPX's normal environment
    proxy behavior (``trust_env=True`` by default).
    """

    def __init__(self, *, deadline_monotonic: float, **kwargs: object) -> None:
        self._deadline_monotonic = float(deadline_monotonic)
        super().__init__(**kwargs)

    def _send_until_deadline(
        self,
        operation: object,
        *,
        request: httpx.Request,
    ) -> httpx.Response:
        """Run one blocking transport operation and close this call's client on expiry."""
        outcome: list[tuple[str, object]] = []
        completed = threading.Event()
        cancelled = threading.Event()

        def send_request() -> None:
            try:
                response = operation()  # type: ignore[operator]
                if cancelled.is_set():
                    response.close()
                else:
                    outcome.append(("response", response))
            except BaseException as exc:
                outcome.append(("error", exc))
            finally:
                completed.set()

        worker = threading.Thread(target=send_request, daemon=True)
        worker.start()
        remaining = max(0.0, self._deadline_monotonic - time.monotonic())
        if not completed.wait(remaining):
            cancelled.set()
            try:
                self.close()
            except Exception:
                pass
            completed.wait(0.2)
            raise httpx.ReadTimeout(
                "Provider request deadline exhausted",
                request=request,
            )
        kind, value = outcome[0]
        if kind == "error":
            raise value  # type: ignore[misc]
        return value  # type: ignore[return-value]

    def send(
        self,
        request: httpx.Request,
        *,
        stream: bool = False,
        auth: object = httpx.USE_CLIENT_DEFAULT,
        follow_redirects: object = httpx.USE_CLIENT_DEFAULT,
    ) -> httpx.Response:
        if time.monotonic() >= self._deadline_monotonic:
            raise httpx.ReadTimeout(
                "Provider request deadline exhausted",
                request=request,
            )
        timeout_extensions = request.extensions.get("timeout")
        if isinstance(timeout_extensions, dict):
            remaining = max(0.0, self._deadline_monotonic - time.monotonic())
            request.extensions["timeout"] = {
                key: min(max(float(value), 0.0), remaining)
                for key, value in timeout_extensions.items()
            }
        response = self._send_until_deadline(
            lambda: super(DeadlineHttpxClient, self).send(
                request,
                stream=True,
                auth=auth,
                follow_redirects=follow_redirects,
            ),
            request=request,
        )
        response.stream = _DeadlineSyncByteStream(
            response.stream,
            self._deadline_monotonic,
            request,
        )
        if not stream:
            try:
                response.read()
            except BaseException:
                response.close()
                raise
        return response
