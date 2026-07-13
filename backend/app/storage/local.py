"""Private local storage with root confinement and atomic 0600 writes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: Path):
        configured_root = root.expanduser()
        if configured_root.is_symlink():
            raise ValueError("Storage root cannot be a symlink.")
        self.root = configured_root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)

    def write(self, extension: str, data: bytes) -> tuple[str, str]:
        directory = self.root / "resumes"
        directory.mkdir(mode=0o750, exist_ok=True)
        if directory.is_symlink():
            raise ValueError("Storage directory cannot be a symlink.")
        filename = f"{uuid4().hex}{extension}"
        key = f"resumes/{filename}"
        destination = self.path(key)
        temporary = directory / f".{filename}.{uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        return key, hashlib.sha256(data).hexdigest()

    def path(self, storage_key: str) -> Path:
        pure = PurePosixPath(storage_key)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise ValueError("Storage key is invalid.")
        candidate = (self.root / Path(*pure.parts)).resolve(strict=False)
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Storage key escapes configured root.")
        current = candidate.parent
        while current != self.root.parent:
            if current.exists() and current.is_symlink():
                raise ValueError("Storage path contains a symlink.")
            if current == self.root:
                break
            current = current.parent
        return candidate

    def remove(self, storage_key: str) -> None:
        path = self.path(storage_key)
        if path.is_symlink():
            raise ValueError("Stored file cannot be a symlink.")
        path.unlink(missing_ok=True)
