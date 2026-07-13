"""Strict read-only inspection of known Version 1 SQLite schemas."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


CORE_TABLE = "application_records"
KNOWN_TABLES = {
    "application_records",
    "knowledge_documents",
    "knowledge_chunks",
    "analysis_metrics",
    "analysis_step_metrics",
    "evaluation_runs",
    "evaluation_results",
}
IGNORED_TABLE_PREFIXES = ("knowledge_chunks_fts", "sqlite_")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceMetadata:
    path: Path
    size: int
    mtime_ns: int
    fingerprint: str
    tables: tuple[str, ...]
    row_counts: dict[str, int]


class SQLiteV1Reader:
    def __init__(self, source: Path):
        self.path = source.expanduser().resolve(strict=True)
        if not self.path.is_file() or self.path.is_symlink():
            raise ValueError("Source SQLite path must be a regular non-symlink file.")
        self._initial_hash = sha256_file(self.path)
        stat = self.path.stat()
        self._initial_size = stat.st_size
        self._initial_mtime_ns = stat.st_mtime_ns

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def inspect(self) -> SourceMetadata:
        with self.connect() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ValueError("Source SQLite integrity_check failed.")
            all_tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            business_tables = {
                table
                for table in all_tables
                if not table.startswith(IGNORED_TABLE_PREFIXES)
            }
            unknown = business_tables - KNOWN_TABLES
            if unknown:
                raise ValueError("Source SQLite contains an unknown business schema.")
            if CORE_TABLE not in business_tables:
                raise ValueError("Source SQLite is missing the required application_records table.")
            counts = {
                table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in sorted(business_tables)
            }
        return SourceMetadata(
            path=self.path,
            size=self._initial_size,
            mtime_ns=self._initial_mtime_ns,
            fingerprint=self._initial_hash,
            tables=tuple(sorted(business_tables)),
            row_counts=counts,
        )

    def rows(self, table: str, batch_size: int = 500) -> Iterator[dict[str, object]]:
        if table not in KNOWN_TABLES:
            raise ValueError("Unknown migration table requested.")
        with self.connect() as connection:
            cursor = connection.execute(f'SELECT * FROM "{table}" ORDER BY id')
            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    yield dict(row)

    def assert_unchanged(self) -> None:
        stat = self.path.stat()
        if (
            stat.st_size != self._initial_size
            or stat.st_mtime_ns != self._initial_mtime_ns
            or sha256_file(self.path) != self._initial_hash
        ):
            raise RuntimeError("Source SQLite changed during migration.")
