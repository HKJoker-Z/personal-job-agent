"""Deterministic, conservative Job normalization."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "token",
    "access_token",
    "auth",
    "authorization",
    "api_key",
    "key",
    "secret",
    "signature",
    "sig",
}
COMPANY_SUFFIXES = (" incorporated", " inc", " limited", " ltd", " corporation", " corp")


def normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_company(value: str | None) -> str:
    normalized = normalize_text(value).casefold().rstrip(".,")
    for suffix in COMPANY_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            return normalized[: -len(suffix)].rstrip(" ,.")
    return normalized


def normalize_title(value: str | None) -> str:
    # Deliberately retain seniority and employment qualifiers.
    return normalize_text(value).casefold()


def normalize_location(value: str | None) -> str:
    return normalize_text(value).casefold()


def normalize_description(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    output: list[str] = []
    for line in lines:
        if not line and (not output or not output[-1]):
            continue
        output.append(line)
    return "\n".join(output).strip()


def description_hash(description: str) -> str:
    return hashlib.sha256(normalize_description(description).encode("utf-8")).hexdigest()


def canonicalize_url(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed.")
    host = parsed.hostname.rstrip(".").casefold()
    port = parsed.port
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    clean_query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_PARAMETERS
    ]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(sorted(clean_query)), ""))


def deduplication_key(
    company: str | None, title: str | None, location: str, description: str, canonical_url: str | None
) -> str:
    parts = (
        normalize_company(company),
        normalize_title(title),
        normalize_location(location),
        description_hash(description),
        canonical_url or "",
    )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
