"""Select one effective JD before RAG, prompting, or provider execution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.analyze.execution import (
    ExecutionBinding,
    LOCAL_NORMALIZATION_CONTRACT_VERSION,
    execution_fingerprint,
)
from app.analyze.normalization_client import (
    JavaNormalizationClient,
    NormalizationClientError,
)
from app.analyze.normalization_shadow import observe_shadow_normalization
from config import JavaNormalizationConfig
from security_utils import scan_and_sanitize_untrusted_text


@dataclass(frozen=True)
class EffectiveNormalization:
    text: str
    source: str
    policy_version: str
    dictionary_version: str | None
    java_attempted: bool
    java_outcome: str
    fallback: bool
    duration_ms: float
    authoritative_second_scan_outcome: str
    accepted_security_scan: dict[str, Any] = field(default_factory=dict)

    def execution_binding(self, stable_request_fingerprint: str) -> ExecutionBinding:
        return execution_fingerprint(
            stable_request_fingerprint=stable_request_fingerprint,
            effective_normalization_source=self.source,
            effective_job_text=self.text,
            normalization_policy_version=self.policy_version,
            skill_dictionary_version=self.dictionary_version,
        )


def _duration_ms(started: int) -> float:
    return round(max(0, time.perf_counter_ns() - started) / 1_000_000, 3)


def _emit(
    logger: logging.Logger,
    *,
    request_id: str,
    mode: str,
    result: EffectiveNormalization,
) -> None:
    try:
        logger.info(
            "jd_normalization_execution_observation",
            extra={
                "request_id": request_id,
                "normalization_mode": mode,
                "normalization_source": result.source,
                "java_attempted": result.java_attempted,
                "normalization_outcome": result.java_outcome,
                "fallback": result.fallback,
                "duration_ms": result.duration_ms,
                "normalization_policy_version": result.policy_version,
                "skill_dictionary_version": result.dictionary_version,
                "authoritative_second_scan_outcome": (
                    result.authoritative_second_scan_outcome
                ),
            },
        )
    except Exception:
        pass


def _local_result(
    local_text: str,
    *,
    source: str,
    java_attempted: bool,
    java_outcome: str,
    duration_ms: float,
    second_scan_outcome: str,
) -> EffectiveNormalization:
    return EffectiveNormalization(
        text=local_text,
        source=source,
        policy_version=LOCAL_NORMALIZATION_CONTRACT_VERSION,
        dictionary_version=None,
        java_attempted=java_attempted,
        java_outcome=java_outcome,
        fallback=source == "fallback_local",
        duration_ms=duration_ms,
        authoritative_second_scan_outcome=second_scan_outcome,
    )


async def select_effective_normalization(
    *,
    client: JavaNormalizationClient | None,
    config: JavaNormalizationConfig,
    local_sanitized_job_text: str,
    request_id: str,
    logger: logging.Logger,
    stable_request_fingerprint: str | None = None,
) -> EffectiveNormalization:
    """Make at most one Java attempt, then return one immutable effective choice."""

    if config.mode == "local":
        result = _local_result(
            local_sanitized_job_text,
            source="local",
            java_attempted=False,
            java_outcome="not_attempted",
            duration_ms=0.0,
            second_scan_outcome="not_applicable",
        )
        _emit(logger, request_id=request_id, mode=config.mode, result=result)
        return result

    if config.mode == "shadow":
        if stable_request_fingerprint is None:
            raise ValueError("Shadow normalization requires the stable request fingerprint.")
        observation = await observe_shadow_normalization(
            client=client,
            config=config,
            input_fingerprint=stable_request_fingerprint,
            sanitized_job_text=local_sanitized_job_text,
            request_id=request_id,
            logger=logger,
        )
        return _local_result(
            local_sanitized_job_text,
            source="local",
            java_attempted=observation is not None,
            java_outcome=(
                observation.outcome if observation is not None else "not_sampled"
            ),
            duration_ms=observation.duration_ms if observation is not None else 0.0,
            second_scan_outcome=(
                "observation_only"
                if observation is not None and observation.outcome == "success"
                else "not_authoritative"
            ),
        )

    if config.mode != "java":
        raise ValueError("Unsupported JD normalization mode.")

    started = time.perf_counter_ns()
    try:
        if client is None:
            raise NormalizationClientError("unavailable")
        normalized = await client.normalize(local_sanitized_job_text, request_id)
        try:
            effective_text, second_scan = scan_and_sanitize_untrusted_text(
                normalized.normalized_text,
                "job_description",
            )
        except Exception:
            result = _local_result(
                local_sanitized_job_text,
                source="fallback_local",
                java_attempted=True,
                java_outcome="second_scan_error",
                duration_ms=_duration_ms(started),
                second_scan_outcome="error",
            )
        else:
            if second_scan.get("blocked") or not effective_text.strip():
                result = _local_result(
                    local_sanitized_job_text,
                    source="fallback_local",
                    java_attempted=True,
                    java_outcome="second_scan_rejected",
                    duration_ms=_duration_ms(started),
                    second_scan_outcome="rejected",
                )
            else:
                result = EffectiveNormalization(
                    text=effective_text,
                    source="java",
                    policy_version=normalized.normalization_policy_version,
                    dictionary_version=normalized.skill_dictionary_version,
                    java_attempted=True,
                    java_outcome="success",
                    fallback=False,
                    duration_ms=_duration_ms(started),
                    authoritative_second_scan_outcome="accepted",
                    accepted_security_scan=second_scan,
                )
    except NormalizationClientError as exc:
        result = _local_result(
            local_sanitized_job_text,
            source="fallback_local",
            java_attempted=True,
            java_outcome=exc.outcome,
            duration_ms=_duration_ms(started),
            second_scan_outcome="not_available",
        )
    except Exception:
        result = _local_result(
            local_sanitized_job_text,
            source="fallback_local",
            java_attempted=True,
            java_outcome="unavailable",
            duration_ms=_duration_ms(started),
            second_scan_outcome="not_available",
        )
    _emit(logger, request_id=request_id, mode=config.mode, result=result)
    return result
