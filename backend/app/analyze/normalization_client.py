"""Bounded internal client for shadow or authoritative Java JD normalization."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from config import JavaNormalizationConfig
from logging_utils import REQUEST_ID_PATTERN


NORMALIZE_PATH = "/api/v1/job-descriptions/normalize"
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TOP_LEVEL_FIELDS = {
    "normalized_text",
    "content_hash",
    "normalization_policy_version",
    "skill_dictionary_version",
    "required_skills",
    "preferred_skills",
    "mentioned_skills",
    "metadata",
}
METADATA_FIELDS = {"title", "company", "location", "canonical_url"}
MAX_NORMALIZED_CODE_POINTS = 100_000
MAX_REQUEST_BYTES = 512 * 1024
MAX_SKILLS = 256
MAX_SKILL_NAME_CODE_POINTS = 200
MAX_METADATA_CODE_POINTS = 200
MAX_CANONICAL_URL_ASCII_LENGTH = 2_048


class NormalizationClientError(RuntimeError):
    """A stable normalization outcome that intentionally contains no remote detail."""

    def __init__(self, outcome: str):
        super().__init__(outcome)
        self.outcome = outcome


@dataclass(frozen=True)
class NormalizedSkill:
    id: str
    name: str


@dataclass(frozen=True)
class NormalizedJobDescription:
    normalized_text: str
    content_hash: str
    normalization_policy_version: str
    skill_dictionary_version: str
    required_skills: tuple[NormalizedSkill, ...]
    preferred_skills: tuple[NormalizedSkill, ...]
    mentioned_skills: tuple[NormalizedSkill, ...]
    metadata: dict[str, str | None]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def _bounded_string(
    value: Any,
    *,
    maximum: int,
    allow_none: bool = False,
) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise NormalizationClientError("invalid_schema")
    return value


def _skill_list(value: Any, seen: set[str]) -> tuple[NormalizedSkill, ...]:
    if not isinstance(value, list):
        raise NormalizationClientError("invalid_schema")
    output: list[NormalizedSkill] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "name"}:
            raise NormalizationClientError("invalid_schema")
        skill_id = item.get("id")
        name = item.get("name")
        if (
            not isinstance(skill_id, str)
            or not SKILL_ID_PATTERN.fullmatch(skill_id)
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > MAX_SKILL_NAME_CODE_POINTS
            or skill_id in seen
        ):
            raise NormalizationClientError("invalid_schema")
        seen.add(skill_id)
        output.append(NormalizedSkill(id=skill_id, name=name))
    return tuple(output)


def _metadata(value: Any) -> dict[str, str | None]:
    if not isinstance(value, dict) or set(value) != METADATA_FIELDS:
        raise NormalizationClientError("invalid_schema")
    output: dict[str, str | None] = {}
    for field in ("title", "company", "location"):
        output[field] = _bounded_string(
            value.get(field),
            maximum=MAX_METADATA_CODE_POINTS,
            allow_none=True,
        )
    canonical_url = _bounded_string(
        value.get("canonical_url"),
        maximum=MAX_CANONICAL_URL_ASCII_LENGTH,
        allow_none=True,
    )
    if canonical_url is not None:
        parsed = urlsplit(canonical_url)
        if (
            not canonical_url.isascii()
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise NormalizationClientError("invalid_schema")
    output["canonical_url"] = canonical_url
    return output


def validate_normalization_response(
    value: Any,
    config: JavaNormalizationConfig,
) -> NormalizedJobDescription:
    if not isinstance(value, dict) or set(value) != TOP_LEVEL_FIELDS:
        raise NormalizationClientError("invalid_schema")

    normalized_text = _bounded_string(
        value.get("normalized_text"),
        maximum=MAX_NORMALIZED_CODE_POINTS,
    )
    assert normalized_text is not None
    content_hash = value.get("content_hash")
    if not isinstance(content_hash, str) or not HASH_PATTERN.fullmatch(content_hash):
        raise NormalizationClientError("hash_mismatch")
    recomputed = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    if recomputed != content_hash:
        raise NormalizationClientError("hash_mismatch")

    policy_version = value.get("normalization_policy_version")
    if policy_version != config.expected_policy_version:
        raise NormalizationClientError("policy_mismatch")
    dictionary_version = value.get("skill_dictionary_version")
    if dictionary_version != config.expected_dictionary_version:
        raise NormalizationClientError("dictionary_mismatch")

    seen: set[str] = set()
    required = _skill_list(value.get("required_skills"), seen)
    preferred = _skill_list(value.get("preferred_skills"), seen)
    mentioned = _skill_list(value.get("mentioned_skills"), seen)
    if len(seen) > MAX_SKILLS:
        raise NormalizationClientError("invalid_schema")

    return NormalizedJobDescription(
        normalized_text=normalized_text,
        content_hash=content_hash,
        normalization_policy_version=policy_version,
        skill_dictionary_version=dictionary_version,
        required_skills=required,
        preferred_skills=preferred,
        mentioned_skills=mentioned,
        metadata=_metadata(value.get("metadata")),
    )


def _http_outcome(status_code: int) -> str:
    if status_code == 401:
        return "unauthorized"
    if 400 <= status_code < 500:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    return "client_error"


class JavaNormalizationClient:
    """One-attempt, no-proxy, no-redirect client with a bounded response."""

    def __init__(
        self,
        config: JavaNormalizationConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if (
            config.mode not in {"shadow", "java"}
            or not config.base_url
            or not config.api_key
        ):
            raise ValueError(
                "Java normalization client requires validated shadow or java configuration."
            )
        self._config = config
        timeout = httpx.Timeout(
            connect=config.connect_timeout_ms / 1000,
            read=config.response_timeout_ms / 1000,
            write=config.response_timeout_ms / 1000,
            pool=config.connect_timeout_ms / 1000,
        )
        limits = httpx.Limits(
            max_connections=config.pool_max_connections,
            max_keepalive_connections=config.pool_max_keepalive_connections,
        )
        effective_transport = transport or httpx.AsyncHTTPTransport(
            retries=0,
            limits=limits,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
            trust_env=False,
            transport=effective_transport,
        )
        self._endpoint = f"{config.base_url}{NORMALIZE_PATH}"

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def aclose(self) -> None:
        await self._client.aclose()

    async def normalize(
        self,
        raw_text: str,
        request_id: str,
    ) -> NormalizedJobDescription:
        if not REQUEST_ID_PATTERN.fullmatch(request_id):
            raise NormalizationClientError("request_id_mismatch")
        if (
            not isinstance(raw_text, str)
            or not raw_text.strip()
            or len(raw_text) > MAX_NORMALIZED_CODE_POINTS
        ):
            raise NormalizationClientError("client_error")
        body = json.dumps(
            {"raw_text": raw_text},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise NormalizationClientError("client_error")
        request = httpx.Request(
            "POST",
            self._endpoint,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            content=body,
        )
        try:
            async with asyncio.timeout(self._config.total_timeout_ms / 1000):
                response = await self._client.send(
                    request,
                    stream=True,
                    follow_redirects=False,
                )
                try:
                    if response.status_code != 200:
                        raise NormalizationClientError(
                            _http_outcome(response.status_code)
                        )
                    content_type = response.headers.get("Content-Type", "")
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    if media_type != "application/json" and not media_type.endswith(
                        "+json"
                    ):
                        raise NormalizationClientError("invalid_schema")
                    response_request_id = response.headers.get("X-Request-ID")
                    if (
                        response_request_id is None
                        or not REQUEST_ID_PATTERN.fullmatch(response_request_id)
                        or response_request_id != request_id
                    ):
                        raise NormalizationClientError("request_id_mismatch")
                    declared_length = response.headers.get("Content-Length")
                    if declared_length is not None:
                        try:
                            parsed_length = int(declared_length)
                            if parsed_length < 0:
                                raise NormalizationClientError("invalid_schema")
                            if parsed_length > self._config.max_response_bytes:
                                raise NormalizationClientError("oversized_response")
                        except ValueError as exc:
                            raise NormalizationClientError("invalid_schema") from exc

                    collected = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(collected) + len(chunk) > self._config.max_response_bytes:
                            raise NormalizationClientError("oversized_response")
                        collected.extend(chunk)
                    try:
                        payload = json.loads(
                            bytes(collected),
                            object_pairs_hook=_unique_object,
                        )
                    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                        raise NormalizationClientError("invalid_json") from exc
                    return validate_normalization_response(payload, self._config)
                finally:
                    await response.aclose()
        except NormalizationClientError:
            raise
        except asyncio.TimeoutError as exc:
            raise NormalizationClientError("total_timeout") from exc
        except httpx.ConnectTimeout as exc:
            raise NormalizationClientError("connect_timeout") from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            raise NormalizationClientError("response_timeout") from exc
        except (
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.ProtocolError,
            httpx.PoolTimeout,
        ) as exc:
            raise NormalizationClientError("unavailable") from exc
        except httpx.HTTPError as exc:
            raise NormalizationClientError("unavailable") from exc
