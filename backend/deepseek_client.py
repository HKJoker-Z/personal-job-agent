"""Client-scoped DeepSeek transport construction.

Only this module selects the DeepSeek network mode. It deliberately does not
alter process environment variables, so unrelated Backend networking keeps
its existing behavior.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx
from openai import OpenAI

from provider_deadline import DeadlineHttpxClient, ProviderDeadline


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_NETWORK_MODE_DIRECT = "direct"
DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY = "environment_proxy"


def build_deepseek_client(
    runtime_settings: Any,
    *,
    deadline: ProviderDeadline,
    kind: str,
    network_mode: str | None = None,
    client_class: Callable[..., Any] = OpenAI,
) -> tuple[Any, DeadlineHttpxClient, Any]:
    """Build one bounded OpenAI-compatible DeepSeek client.

    ``REQUEST_TIMEOUT_SECONDS`` and the shared absolute Provider deadline are
    the only timeout sources. The attempt deadline is derived from the same
    bounded budget and is never an independent unbounded timer.
    """
    timeout = deadline.call_timeout(
        configured_timeout_seconds=runtime_settings.request_timeout_seconds,
        kind=kind,
    )
    if timeout is None:
        raise RuntimeError("provider deadline has no safe call budget")

    if network_mode is None:
        network_mode = getattr(
            runtime_settings,
            "deepseek_network_mode",
            DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
        )
    if network_mode not in {
        DEEPSEEK_NETWORK_MODE_DIRECT,
        DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
    }:
        raise RuntimeError("invalid DeepSeek network mode")

    # The total attempt bound is derived from the same remaining budget used
    # for the HTTPX component timeout. The phase deadline remains authoritative
    # and is always the outer bound.
    attempt_deadline_monotonic = min(
        deadline.absolute_deadline,
        time.monotonic() + timeout.budget_seconds,
    )
    http_client = build_deepseek_http_client(
        network_mode=network_mode,
        deadline_monotonic=deadline.absolute_deadline,
        attempt_deadline_monotonic=attempt_deadline_monotonic,
        timeout=timeout.timeout,
    )
    try:
        client = client_class(
            api_key=runtime_settings.deepseek_api_key,
            base_url=DEEPSEEK_BASE_URL,
            timeout=timeout.timeout,
            max_retries=0,
            http_client=http_client,
        )
    except BaseException:
        http_client.close()
        raise
    return client, http_client, timeout


def build_deepseek_http_client(
    *,
    network_mode: str,
    deadline_monotonic: float,
    timeout: httpx.Timeout,
    attempt_deadline_monotonic: float | None = None,
    **kwargs: object,
) -> DeadlineHttpxClient:
    """Build the DeepSeek-only deadline-aware HTTPX transport.

    This small seam is also used by the disposable connectivity preflight, so
    that the preflight exercises the same client-scoped transport selection as
    the production Provider factory.
    """
    if network_mode not in {
        DEEPSEEK_NETWORK_MODE_DIRECT,
        DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
    }:
        raise ValueError("invalid DeepSeek network mode")
    return DeadlineHttpxClient(
        deadline_monotonic=deadline_monotonic,
        attempt_deadline_monotonic=attempt_deadline_monotonic,
        timeout=timeout,
        trust_env=network_mode == DEEPSEEK_NETWORK_MODE_ENVIRONMENT_PROXY,
        verify=True,
        **kwargs,
    )
