"""Deterministic, observation-only Java normalization orchestration."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from app.analyze.normalization_client import (
    JavaNormalizationClient,
    NormalizationClientError,
)
from config import JavaNormalizationConfig
from security_utils import scan_untrusted_text


SAMPLE_DOMAIN = b"personal-job-agent:jd-normalization-shadow-sampling:v1\x00"


@dataclass(frozen=True)
class ShadowObservation:
    sampled: bool
    outcome: str
    duration_ms: float
    text_hash_equal: bool | None = None
    security_finding_count: int | None = None
    policy_version: str | None = None
    dictionary_version: str | None = None


def deterministic_shadow_sample(input_fingerprint: str, sample_rate: float) -> bool:
    if sample_rate <= 0:
        return False
    if sample_rate >= 1:
        return True
    if len(input_fingerprint) != 64:
        raise ValueError("Analyze input fingerprint must be a SHA-256 value.")
    try:
        fingerprint_bytes = bytes.fromhex(input_fingerprint)
    except ValueError as exc:
        raise ValueError("Analyze input fingerprint must be a SHA-256 value.") from exc
    value = int.from_bytes(
        hashlib.sha256(SAMPLE_DOMAIN + fingerprint_bytes).digest()[:8],
        "big",
    )
    threshold = int(sample_rate * (1 << 64))
    return value < threshold


def _emit(
    logger: logging.Logger,
    request_id: str,
    observation: ShadowObservation,
) -> None:
    fields: dict[str, object] = {
        "request_id": request_id,
        "normalization_mode": "shadow",
        "normalization_source": "local",
        "java_attempted": True,
        "sampled": observation.sampled,
        "normalization_outcome": observation.outcome,
        "fallback": False,
        "duration_ms": observation.duration_ms,
        "authoritative_second_scan_outcome": (
            "observation_only"
            if observation.outcome == "success"
            else "not_authoritative"
        ),
    }
    optional = {
        "text_hash_equal": observation.text_hash_equal,
        "security_finding_count": observation.security_finding_count,
        "normalization_policy_version": observation.policy_version,
        "skill_dictionary_version": observation.dictionary_version,
    }
    fields.update({key: value for key, value in optional.items() if value is not None})
    logger.info("jd_normalization_shadow_observation", extra=fields)


async def observe_shadow_normalization(
    *,
    client: JavaNormalizationClient | None,
    config: JavaNormalizationConfig,
    input_fingerprint: str,
    sanitized_job_text: str,
    request_id: str,
    logger: logging.Logger,
) -> ShadowObservation | None:
    if not deterministic_shadow_sample(input_fingerprint, config.shadow_sample_rate):
        return None

    started = time.perf_counter_ns()
    try:
        if client is None:
            raise NormalizationClientError("unavailable")
        normalized = await client.normalize(sanitized_job_text, request_id)
        observation_scan = scan_untrusted_text(
            normalized.normalized_text,
            "job_description",
        )
        local_hash = hashlib.sha256(sanitized_job_text.encode("utf-8")).hexdigest()
        observation = ShadowObservation(
            sampled=True,
            outcome="success",
            duration_ms=round(
                max(0, time.perf_counter_ns() - started) / 1_000_000,
                3,
            ),
            text_hash_equal=local_hash == normalized.content_hash,
            security_finding_count=min(
                len(observation_scan.get("findings") or []),
                256,
            ),
            policy_version=normalized.normalization_policy_version,
            dictionary_version=normalized.skill_dictionary_version,
        )
    except NormalizationClientError as exc:
        observation = ShadowObservation(
            sampled=True,
            outcome=exc.outcome,
            duration_ms=round(
                max(0, time.perf_counter_ns() - started) / 1_000_000,
                3,
            ),
        )
    except Exception:
        observation = ShadowObservation(
            sampled=True,
            outcome="unavailable",
            duration_ms=round(
                max(0, time.perf_counter_ns() - started) / 1_000_000,
                3,
            ),
        )
    try:
        _emit(logger, request_id, observation)
    except Exception:
        pass
    return observation
