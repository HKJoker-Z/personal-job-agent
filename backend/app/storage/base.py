"""Storage provider abstraction for future local/S3/R2 implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    @abstractmethod
    def write(self, extension: str, data: bytes, namespace: str = "resumes") -> tuple[str, str]:
        """Return an opaque storage key and SHA-256 digest."""

    @abstractmethod
    def path(self, storage_key: str) -> Path:
        """Resolve an opaque storage key without permitting root escape."""

    @abstractmethod
    def remove(self, storage_key: str) -> None:
        """Physically remove one already-authorized orphan."""
