"""Configured SQLite connections with explicit transaction handling."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class Database:
    """Owns a file-backed SQLite database and opens configured connections."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("database path must be an absolute Path")
        if str(path) == ":memory:":
            raise ValueError("the durable core requires a file-backed database")
        self.path = path

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=True,
        )
        try:
            os.chmod(self.path, 0o600)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA synchronous = FULL")
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                connection.execute("PRAGMA journal_mode = WAL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def initialize(self) -> None:
        """Upgrade the database through the registered migration sequence."""
        from .migrations import MigrationRunner

        MigrationRunner(self).upgrade()
