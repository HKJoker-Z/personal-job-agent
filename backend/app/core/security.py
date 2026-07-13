"""Small, auditable primitives for password, opaque token, and fingerprint handling."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from email_validator import EmailNotValidError, validate_email
from pwdlib import PasswordHash


PASSWORD_HASH = PasswordHash.recommended()
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024


def normalize_email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise ValueError("A valid email address is required.") from exc


def validate_password(value: str) -> str:
    if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH} characters."
        )
    return value


def hash_password(value: str) -> str:
    return PASSWORD_HASH.hash(validate_password(value))


def verify_password(value: str, encoded: str) -> bool:
    try:
        return PASSWORD_HASH.verify(value, encoded)
    except Exception:
        return False


def random_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def tokens_match(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(token_hash(value), expected_hash)


def keyed_fingerprint(value: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def masked_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"
