"""Versioned Analyze execution identity for effective JD normalization."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


EXECUTION_CONTRACT_VERSION = "analyze-execution-v1"
LOCAL_NORMALIZATION_CONTRACT_VERSION = "fastapi-local-jd-v1"
EXECUTION_FINGERPRINT_DOMAIN = (
    b"personal-job-agent:analyze:execution-fingerprint:v1\x00"
)
EFFECTIVE_NORMALIZATION_SOURCES = ("local", "java", "fallback_local")
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExecutionBinding:
    """Exact normalization identity selected before downstream Analyze work."""

    fingerprint: bytes
    contract_version: str
    normalization_source: str
    normalization_policy_version: str
    skill_dictionary_version: str | None

    def __post_init__(self) -> None:
        if len(self.fingerprint) != 32:
            raise ValueError("Execution fingerprint must contain exactly 32 bytes.")
        if self.contract_version != EXECUTION_CONTRACT_VERSION:
            raise ValueError("Execution contract version is unsupported.")
        if self.normalization_source not in EFFECTIVE_NORMALIZATION_SOURCES:
            raise ValueError("Effective normalization source is unsupported.")
        if not self.normalization_policy_version.strip():
            raise ValueError("Normalization policy version must be nonblank.")
        if self.normalization_source == "java":
            if not self.skill_dictionary_version or not self.skill_dictionary_version.strip():
                raise ValueError("Java execution requires a skill dictionary version.")
        elif self.skill_dictionary_version is not None:
            raise ValueError("Local execution does not use a skill dictionary version.")


def execution_fingerprint(
    *,
    stable_request_fingerprint: str,
    effective_normalization_source: str,
    effective_job_text: str,
    normalization_policy_version: str,
    skill_dictionary_version: str | None,
) -> ExecutionBinding:
    """Return the domain-separated SHA-256 binding for one effective execution."""

    if not SHA256_HEX_PATTERN.fullmatch(stable_request_fingerprint):
        raise ValueError("Stable request fingerprint must be a SHA-256 value.")
    if effective_normalization_source not in EFFECTIVE_NORMALIZATION_SOURCES:
        raise ValueError("Effective normalization source is unsupported.")
    if not isinstance(effective_job_text, str) or not effective_job_text.strip():
        raise ValueError("Effective Job Description text must be nonblank.")
    if not isinstance(normalization_policy_version, str) or not normalization_policy_version.strip():
        raise ValueError("Normalization policy version must be nonblank.")
    if effective_normalization_source == "java":
        if not isinstance(skill_dictionary_version, str) or not skill_dictionary_version.strip():
            raise ValueError("Java execution requires a skill dictionary version.")
    elif skill_dictionary_version is not None:
        raise ValueError("Local execution does not use a skill dictionary version.")

    canonical = {
        "effective_job_text_sha256": hashlib.sha256(
            effective_job_text.encode("utf-8")
        ).hexdigest(),
        "effective_normalization_source": effective_normalization_source,
        "execution_contract_version": EXECUTION_CONTRACT_VERSION,
        "normalization_policy_version": normalization_policy_version,
        "skill_dictionary_version": skill_dictionary_version,
        "stable_request_fingerprint": stable_request_fingerprint,
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(EXECUTION_FINGERPRINT_DOMAIN + encoded).digest()
    return ExecutionBinding(
        fingerprint=digest,
        contract_version=EXECUTION_CONTRACT_VERSION,
        normalization_source=effective_normalization_source,
        normalization_policy_version=normalization_policy_version,
        skill_dictionary_version=skill_dictionary_version,
    )
