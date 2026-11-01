"""Transactional, versioned SQLite migrations with guarded rollback."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .database import Database
from .schema import SCHEMA_V1


class MigrationError(RuntimeError):
    """Raised when the database cannot be safely migrated."""


class MigrationDataLossError(MigrationError):
    """Raised when a downgrade would discard persisted domain records."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    up_sql: str
    down_sql: str
    rollback_requires_empty: tuple[str, ...] = ()


DROP_V1 = """
DROP VIEW IF EXISTS evidence_records;
DROP TRIGGER IF EXISTS evidence_tags_no_delete;
DROP TRIGGER IF EXISTS evidence_tags_no_update;
DROP TRIGGER IF EXISTS evidence_no_delete;
DROP TRIGGER IF EXISTS evidence_no_update;
DROP TRIGGER IF EXISTS events_no_delete;
DROP TRIGGER IF EXISTS events_no_update;
DROP TABLE IF EXISTS evidence_tags;
DROP TABLE IF EXISTS evidence;
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS approvals;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS projects;
"""

CORE_MIGRATIONS = (
    Migration(
        version=1,
        name="durable_core_v1",
        up_sql=SCHEMA_V1,
        down_sql=DROP_V1,
        rollback_requires_empty=(
            "projects",
            "tasks",
            "notes",
            "events",
            "approvals",
            "evidence",
            "evidence_tags",
        ),
    ),
)


class MigrationRunner:
    """Applies ordered migrations and only downgrades empty schemas."""

    def __init__(
        self,
        database: Database,
        migrations: Iterable[Migration] = CORE_MIGRATIONS,
    ) -> None:
        self.database = database
        self.migrations = tuple(sorted(migrations, key=lambda item: item.version))
        versions = [migration.version for migration in self.migrations]
        if any(
            isinstance(version, bool) or not isinstance(version, int)
            for version in versions
        ):
            raise ValueError("migration versions must be integers")
        if versions != list(range(1, len(versions) + 1)):
            raise ValueError("migration versions must be unique and contiguous from 1")
        if any(
            not isinstance(migration.name, str) or not migration.name.strip()
            for migration in self.migrations
        ):
            raise ValueError("migration names must be non-empty strings")

    @property
    def latest_version(self) -> int:
        return self.migrations[-1].version if self.migrations else 0

    def current_version(self) -> int:
        with self.database.connection() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def upgrade(self, target_version: int | None = None) -> int:
        target = self.latest_version if target_version is None else target_version
        self._validate_target(target)
        while True:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = int(
                        connection.execute("PRAGMA user_version").fetchone()[0]
                    )
                    if current > self.latest_version:
                        raise MigrationError(
                            f"database version {current} is newer than supported "
                            f"version {self.latest_version}"
                        )
                    if current > target:
                        raise MigrationError(
                            "upgrade target is below the current version; "
                            "use downgrade() explicitly"
                        )
                    if current == target:
                        connection.rollback()
                        return current
                    migration = self._migration(current + 1)
                    if current == 0:
                        self._require_empty_database(connection)
                    self._execute_script(connection, migration.up_sql)
                    connection.execute(f"PRAGMA user_version = {migration.version}")
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def downgrade(self, target_version: int = 0) -> int:
        self._validate_target(target_version)
        while True:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    current = int(
                        connection.execute("PRAGMA user_version").fetchone()[0]
                    )
                    if current > self.latest_version:
                        raise MigrationError(
                            f"database version {current} is newer than supported "
                            f"version {self.latest_version}"
                        )
                    if current < target_version:
                        raise MigrationError(
                            "downgrade target is above the current version"
                        )
                    if current == target_version:
                        connection.rollback()
                        return current
                    migration = self._migration(current)
                    self._require_empty_tables(
                        connection, migration.rollback_requires_empty
                    )
                    self._execute_script(connection, migration.down_sql)
                    connection.execute(f"PRAGMA user_version = {current - 1}")
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def _validate_target(self, target: int) -> None:
        if isinstance(target, bool) or not isinstance(target, int):
            raise ValueError("target migration version must be an integer")
        if target < 0 or target > self.latest_version:
            raise ValueError(
                f"target version must be between 0 and {self.latest_version}"
            )

    def _migration(self, version: int) -> Migration:
        for migration in self.migrations:
            if migration.version == version:
                return migration
        raise MigrationError(f"migration version {version} is not registered")

    @staticmethod
    def _require_empty_database(connection: sqlite3.Connection) -> None:
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' "
            "AND type IN ('table', 'view', 'trigger', 'index')"
        ).fetchall()
        if objects:
            names = sorted(f"{row[0]}:{row[1]}" for row in objects)
            raise MigrationError(
                "version 0 database contains untracked schema objects: "
                + ", ".join(names)
            )

    @staticmethod
    def _require_empty_tables(
        connection: sqlite3.Connection, table_names: tuple[str, ...]
    ) -> None:
        for table_name in table_names:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", table_name):
                raise MigrationError("rollback table name is not a safe identifier")
            row = connection.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()
            if row is not None:
                raise MigrationDataLossError(
                    f"cannot roll back while {table_name} contains records"
                )

    @staticmethod
    def _execute_script(connection: sqlite3.Connection, script: str) -> None:
        statement = ""
        for character in script:
            statement += character
            if character == ";" and sqlite3.complete_statement(statement):
                if statement.strip():
                    connection.execute(statement)
                statement = ""
        if statement.strip():
            raise MigrationError("migration script ends with an incomplete statement")
