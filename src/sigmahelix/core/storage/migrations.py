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
    Migration(
        version=2,
        name="hash_chained_audit_log_v2",
        up_sql="""
CREATE TABLE audit_log (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    action TEXT NOT NULL CHECK(length(trim(action)) > 0),
    entity_type TEXT NOT NULL CHECK(length(trim(entity_type)) > 0),
    entity_id TEXT NOT NULL CHECK(length(trim(entity_id)) > 0),
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    previous_hash TEXT NOT NULL CHECK(length(previous_hash) = 64 AND previous_hash NOT GLOB '*[^0-9a-f]*'),
    record_hash TEXT NOT NULL CHECK(length(record_hash) = 64 AND record_hash NOT GLOB '*[^0-9a-f]*')
);
CREATE INDEX idx_audit_log_tenant_sequence ON audit_log(tenant_id, sequence);
CREATE TRIGGER audit_log_no_update
BEFORE UPDATE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'audit log is append-only');
END;
CREATE TRIGGER audit_log_no_delete
BEFORE DELETE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'audit log is append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS audit_log_no_delete;
DROP TRIGGER IF EXISTS audit_log_no_update;
DROP TABLE IF EXISTS audit_log;
""",
        rollback_requires_empty=("audit_log",),
    ),
    Migration(
        version=3,
        name="persistent_event_stream_v3",
        up_sql="""
CREATE TABLE event_stream (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    FOREIGN KEY (tenant_id, event_id) REFERENCES events(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_event_stream_tenant_sequence ON event_stream(tenant_id, sequence);
INSERT INTO event_stream (event_id, tenant_id)
    SELECT id, tenant_id FROM events ORDER BY occurred_at, id;
CREATE TRIGGER events_add_to_stream
AFTER INSERT ON events BEGIN
    INSERT INTO event_stream (event_id, tenant_id) VALUES (NEW.id, NEW.tenant_id);
END;
CREATE TRIGGER event_stream_no_update
BEFORE UPDATE ON event_stream BEGIN
    SELECT RAISE(ABORT, 'event stream is append-only');
END;
CREATE TRIGGER event_stream_no_delete
BEFORE DELETE ON event_stream BEGIN
    SELECT RAISE(ABORT, 'event stream is append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS events_add_to_stream;
DROP TRIGGER IF EXISTS event_stream_no_delete;
DROP TRIGGER IF EXISTS event_stream_no_update;
DROP TABLE IF EXISTS event_stream;
""",
    ),
    Migration(
        version=4,
        name="legacy_session_import_ledger_v4",
        up_sql="""
CREATE TABLE legacy_imports (
    source_id TEXT PRIMARY KEY CHECK(length(trim(source_id)) > 0),
    snapshot_sha256 TEXT NOT NULL CHECK(length(snapshot_sha256) = 64 AND snapshot_sha256 NOT GLOB '*[^0-9a-f]*'),
    imported_at TEXT NOT NULL,
    task_count INTEGER NOT NULL CHECK(task_count >= 0),
    note_count INTEGER NOT NULL CHECK(note_count >= 0)
);
CREATE TRIGGER legacy_imports_no_update
BEFORE UPDATE ON legacy_imports BEGIN
    SELECT RAISE(ABORT, 'legacy import ledger is append-only');
END;
CREATE TRIGGER legacy_imports_no_delete
BEFORE DELETE ON legacy_imports BEGIN
    SELECT RAISE(ABORT, 'legacy import ledger is append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS legacy_imports_no_delete;
DROP TRIGGER IF EXISTS legacy_imports_no_update;
DROP TABLE IF EXISTS legacy_imports;
""",
        rollback_requires_empty=("legacy_imports",),
    ),
    Migration(
        version=5,
        name="recurring_task_occurrences_v5",
        up_sql="""
CREATE TABLE task_series (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    description TEXT NOT NULL DEFAULT '',
    project_id TEXT,
    rule_json TEXT NOT NULL CHECK(json_valid(rule_json)),
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    last_materialized_through TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_task_series_tenant_active ON task_series(tenant_id, active, id);
CREATE TABLE task_occurrences (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    series_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, series_id, scheduled_for),
    UNIQUE (tenant_id, task_id),
    FOREIGN KEY (tenant_id, series_id) REFERENCES task_series(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_task_occurrences_tenant_series_date
    ON task_occurrences(tenant_id, series_id, scheduled_for);
CREATE TRIGGER task_occurrences_no_update
BEFORE UPDATE ON task_occurrences BEGIN
    SELECT RAISE(ABORT, 'task occurrences are append-only');
END;
CREATE TRIGGER task_occurrences_no_delete
BEFORE DELETE ON task_occurrences BEGIN
    SELECT RAISE(ABORT, 'task occurrences are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS task_occurrences_no_delete;
DROP TRIGGER IF EXISTS task_occurrences_no_update;
DROP TABLE IF EXISTS task_occurrences;
DROP TABLE IF EXISTS task_series;
""",
        rollback_requires_empty=("task_occurrences", "task_series"),
    ),
    Migration(
        version=6,
        name="persisted_scheduler_jobs_v6",
        up_sql="""
CREATE TABLE scheduled_jobs (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    job_type TEXT NOT NULL CHECK(length(trim(job_type)) > 0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    next_run_at TEXT NOT NULL,
    interval_seconds INTEGER CHECK(interval_seconds IS NULL OR interval_seconds > 0),
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id)
);
CREATE INDEX idx_scheduled_jobs_due
    ON scheduled_jobs(enabled, next_run_at, tenant_id);
CREATE TABLE job_runs (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    job_id TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
    error_type TEXT,
    UNIQUE (tenant_id, job_id, scheduled_for),
    FOREIGN KEY (tenant_id, job_id) REFERENCES scheduled_jobs(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_job_runs_tenant_status
    ON job_runs(tenant_id, status, started_at);
CREATE TRIGGER job_runs_update_transition
BEFORE UPDATE ON job_runs
WHEN OLD.status != 'running'
  OR NEW.status NOT IN ('succeeded', 'failed')
  OR NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.job_id != OLD.job_id
  OR NEW.scheduled_for != OLD.scheduled_for
  OR NEW.started_at != OLD.started_at
BEGIN
    SELECT RAISE(ABORT, 'job run transition is invalid');
END;
CREATE TRIGGER job_runs_no_delete
BEFORE DELETE ON job_runs BEGIN
    SELECT RAISE(ABORT, 'job runs are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS job_runs_no_delete;
DROP TRIGGER IF EXISTS job_runs_update_transition;
DROP TABLE IF EXISTS job_runs;
DROP TABLE IF EXISTS scheduled_jobs;
""",
        rollback_requires_empty=("job_runs", "scheduled_jobs"),
    ),
    Migration(
        version=7,
        name="missed_scheduler_run_recovery_v7",
        up_sql="""
CREATE TABLE missed_job_runs (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    job_id TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(reason IN ('overdue', 'interrupted')),
    state TEXT NOT NULL CHECK(state IN ('pending', 'acknowledged')),
    acknowledged_at TEXT,
    UNIQUE (tenant_id, job_id, scheduled_for),
    FOREIGN KEY (tenant_id, job_id) REFERENCES scheduled_jobs(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_missed_job_runs_pending
    ON missed_job_runs(tenant_id, state, detected_at);
CREATE TRIGGER missed_job_runs_state_transition
BEFORE UPDATE ON missed_job_runs
WHEN OLD.state != 'pending'
  OR NEW.state != 'acknowledged'
  OR NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.job_id != OLD.job_id
  OR NEW.scheduled_for != OLD.scheduled_for
  OR NEW.detected_at != OLD.detected_at
  OR NEW.reason != OLD.reason
  OR NEW.acknowledged_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'missed job run transition is invalid');
END;
CREATE TRIGGER missed_job_runs_no_delete
BEFORE DELETE ON missed_job_runs BEGIN
    SELECT RAISE(ABORT, 'missed job runs are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS missed_job_runs_no_delete;
DROP TRIGGER IF EXISTS missed_job_runs_state_transition;
DROP TABLE IF EXISTS missed_job_runs;
""",
        rollback_requires_empty=("missed_job_runs",),
    ),
    Migration(
        version=8,
        name="notification_inbox_v8",
        up_sql="""
CREATE TABLE notifications (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    dedupe_key TEXT NOT NULL CHECK(length(trim(dedupe_key)) > 0),
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    native_status TEXT NOT NULL CHECK(native_status IN ('pending', 'delivered', 'unavailable', 'failed')),
    UNIQUE (tenant_id, dedupe_key)
);
CREATE INDEX idx_notifications_inbox
    ON notifications(tenant_id, read_at, created_at DESC);
CREATE TRIGGER notifications_state_transition
BEFORE UPDATE ON notifications
WHEN NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.dedupe_key != OLD.dedupe_key
  OR NEW.title != OLD.title
  OR NEW.body != OLD.body
  OR NEW.created_at != OLD.created_at
  OR (NEW.native_status != OLD.native_status
      AND (OLD.native_status != 'pending' OR NEW.native_status NOT IN ('delivered', 'unavailable', 'failed')))
  OR (NEW.read_at IS NOT OLD.read_at AND (OLD.read_at IS NOT NULL OR NEW.read_at IS NULL))
BEGIN
    SELECT RAISE(ABORT, 'notification state transition is invalid');
END;
CREATE TRIGGER notifications_no_delete
BEFORE DELETE ON notifications BEGIN
    SELECT RAISE(ABORT, 'notifications are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS notifications_no_delete;
DROP TRIGGER IF EXISTS notifications_state_transition;
DROP TABLE IF EXISTS notifications;
""",
        rollback_requires_empty=("notifications",),
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
