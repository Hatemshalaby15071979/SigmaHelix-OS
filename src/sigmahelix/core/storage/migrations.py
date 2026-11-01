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
    Migration(
        version=9,
        name="notification_alarm_state_v9",
        up_sql="""
CREATE TABLE notification_alarm_states (
    notification_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    state TEXT NOT NULL CHECK(state IN ('pending', 'snoozed', 'rescheduled', 'dismissed')),
    due_at TEXT,
    scheduled_job_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (notification_id),
    UNIQUE (tenant_id, notification_id),
    FOREIGN KEY (tenant_id, notification_id) REFERENCES notifications(tenant_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, scheduled_job_id) REFERENCES scheduled_jobs(tenant_id, id) ON DELETE RESTRICT,
    CHECK ((state IN ('snoozed', 'rescheduled') AND due_at IS NOT NULL AND scheduled_job_id IS NOT NULL)
        OR (state IN ('pending', 'dismissed') AND due_at IS NULL AND scheduled_job_id IS NULL))
);
CREATE UNIQUE INDEX idx_notifications_tenant_id ON notifications(tenant_id, id);
CREATE TABLE notification_actions (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    notification_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('snooze', 'dismiss', 'reschedule')),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    due_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (tenant_id, notification_id) REFERENCES notifications(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_notification_actions_history
    ON notification_actions(tenant_id, notification_id, created_at, id);
INSERT INTO notification_alarm_states
    (notification_id, tenant_id, state, due_at, scheduled_job_id, updated_at)
    SELECT id, tenant_id, 'pending', NULL, NULL, created_at FROM notifications;
CREATE TRIGGER notification_alarm_state_transition
BEFORE UPDATE ON notification_alarm_states
WHEN OLD.state = 'dismissed'
  OR (OLD.state = 'pending' AND NEW.state NOT IN ('snoozed', 'rescheduled', 'dismissed'))
  OR (OLD.state IN ('snoozed', 'rescheduled') AND NEW.state NOT IN ('snoozed', 'rescheduled', 'dismissed'))
  OR NEW.notification_id != OLD.notification_id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.updated_at < OLD.updated_at
  OR (NEW.state = OLD.state AND NEW.updated_at = OLD.updated_at)
  OR NEW.state NOT IN ('pending', 'snoozed', 'rescheduled', 'dismissed')
  OR (NEW.state IN ('snoozed', 'rescheduled') AND (NEW.due_at IS NULL OR NEW.scheduled_job_id IS NULL))
  OR (NEW.state IN ('pending', 'dismissed') AND (NEW.due_at IS NOT NULL OR NEW.scheduled_job_id IS NOT NULL))
BEGIN
    SELECT RAISE(ABORT, 'notification alarm transition is invalid');
END;
CREATE TRIGGER notification_actions_no_update
BEFORE UPDATE ON notification_actions BEGIN
    SELECT RAISE(ABORT, 'notification actions are append-only');
END;
CREATE TRIGGER notification_actions_no_delete
BEFORE DELETE ON notification_actions BEGIN
    SELECT RAISE(ABORT, 'notification actions are append-only');
END;
CREATE TRIGGER notification_alarm_states_no_delete
BEFORE DELETE ON notification_alarm_states BEGIN
    SELECT RAISE(ABORT, 'notification alarm states are retained');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS notification_alarm_states_no_delete;
DROP TRIGGER IF EXISTS notification_actions_no_delete;
DROP TRIGGER IF EXISTS notification_actions_no_update;
DROP TRIGGER IF EXISTS notification_alarm_state_transition;
DROP TABLE IF EXISTS notification_actions;
DROP TABLE IF EXISTS notification_alarm_states;
DROP INDEX IF EXISTS idx_notifications_tenant_id;
""",
        rollback_requires_empty=("notification_actions", "notification_alarm_states"),
    ),
    Migration(
        version=10,
        name="project_scan_snapshots_v10",
        up_sql="""
CREATE TABLE project_scan_snapshots (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    project_id TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    git_branch TEXT,
    git_commit TEXT,
    git_dirty INTEGER CHECK(git_dirty IS NULL OR git_dirty IN (0, 1)),
    git_change_count INTEGER NOT NULL CHECK(git_change_count >= 0),
    manifests_json TEXT NOT NULL CHECK(json_valid(manifests_json)),
    entrypoints_json TEXT NOT NULL CHECK(json_valid(entrypoints_json)),
    findings_json TEXT NOT NULL CHECK(json_valid(findings_json)),
    health TEXT NOT NULL CHECK(health IN ('ok', 'needs_attention', 'unavailable')),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_project_scans_latest
    ON project_scan_snapshots(tenant_id, project_id, scanned_at DESC, id);
CREATE TRIGGER project_scan_snapshots_no_update
BEFORE UPDATE ON project_scan_snapshots BEGIN
    SELECT RAISE(ABORT, 'project scan snapshots are append-only');
END;
CREATE TRIGGER project_scan_snapshots_no_delete
BEFORE DELETE ON project_scan_snapshots BEGIN
    SELECT RAISE(ABORT, 'project scan snapshots are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS project_scan_snapshots_no_delete;
DROP TRIGGER IF EXISTS project_scan_snapshots_no_update;
DROP TABLE IF EXISTS project_scan_snapshots;
""",
        rollback_requires_empty=("project_scan_snapshots",),
    ),
    Migration(
        version=11,
        name="launcher_profiles_and_run_history_v11",
        up_sql="""
CREATE TABLE launcher_profiles (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    project_id TEXT,
    executable TEXT NOT NULL CHECK(length(trim(executable)) > 0),
    arguments_json TEXT NOT NULL CHECK(json_valid(arguments_json)),
    working_directory TEXT NOT NULL CHECK(length(trim(working_directory)) > 0),
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, name),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_launcher_profiles_enabled
    ON launcher_profiles(tenant_id, enabled, name);
CREATE TABLE launcher_runs (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    profile_id TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    executable TEXT NOT NULL,
    arguments_json TEXT NOT NULL CHECK(json_valid(arguments_json)),
    working_directory TEXT NOT NULL,
    pid INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'succeeded', 'failed')),
    return_code INTEGER,
    error_type TEXT,
    FOREIGN KEY (tenant_id, profile_id) REFERENCES launcher_profiles(tenant_id, id) ON DELETE RESTRICT
);
CREATE INDEX idx_launcher_runs_history
    ON launcher_runs(tenant_id, profile_id, started_at DESC);
CREATE TRIGGER launcher_profiles_disable_only
BEFORE UPDATE ON launcher_profiles
WHEN OLD.enabled != 1
  OR NEW.enabled != 0
  OR NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.name != OLD.name
  OR NEW.project_id IS NOT OLD.project_id
  OR NEW.executable != OLD.executable
  OR NEW.arguments_json != OLD.arguments_json
  OR NEW.working_directory != OLD.working_directory
  OR NEW.created_at != OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'launcher profiles are immutable except disable');
END;
CREATE TRIGGER launcher_profiles_no_delete
BEFORE DELETE ON launcher_profiles BEGIN
    SELECT RAISE(ABORT, 'launcher profiles are retained');
END;
CREATE TRIGGER launcher_runs_update_transition
BEFORE UPDATE ON launcher_runs
WHEN OLD.status != 'running'
  OR NEW.status NOT IN ('running', 'succeeded', 'failed')
  OR NEW.id != OLD.id
  OR NEW.tenant_id != OLD.tenant_id
  OR NEW.profile_id != OLD.profile_id
  OR NEW.profile_name != OLD.profile_name
  OR NEW.executable != OLD.executable
  OR NEW.arguments_json != OLD.arguments_json
  OR NEW.working_directory != OLD.working_directory
  OR NEW.started_at != OLD.started_at
  OR (OLD.pid IS NOT NULL AND NEW.pid IS NOT OLD.pid)
  OR (NEW.status = 'running' AND NEW.finished_at IS NOT NULL)
  OR (NEW.status != 'running' AND NEW.finished_at IS NULL)
BEGIN
    SELECT RAISE(ABORT, 'launcher run transition is invalid');
END;
CREATE TRIGGER launcher_runs_no_delete
BEFORE DELETE ON launcher_runs BEGIN
    SELECT RAISE(ABORT, 'launcher runs are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS launcher_runs_no_delete;
DROP TRIGGER IF EXISTS launcher_runs_update_transition;
DROP TRIGGER IF EXISTS launcher_profiles_no_delete;
DROP TRIGGER IF EXISTS launcher_profiles_disable_only;
DROP TABLE IF EXISTS launcher_runs;
DROP TABLE IF EXISTS launcher_profiles;
""",
        rollback_requires_empty=("launcher_runs", "launcher_profiles"),
    ),
    Migration(
        version=12,
        name="project_artifact_platform_labels_v12",
        up_sql="""
ALTER TABLE project_scan_snapshots
    ADD COLUMN artifacts_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(artifacts_json));
""",
        down_sql="""
ALTER TABLE project_scan_snapshots DROP COLUMN artifacts_json;
""",
        rollback_requires_empty=("project_scan_snapshots",),
    ),
    Migration(
        version=13,
        name="project_health_scores_and_scan_batches_v13",
        up_sql="""
CREATE TABLE project_scan_batches (
    id TEXT NOT NULL PRIMARY KEY,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    scanned_at TEXT NOT NULL,
    project_count INTEGER NOT NULL CHECK(project_count >= 0),
    UNIQUE (tenant_id, id)
);
CREATE INDEX idx_project_scan_batches_latest
    ON project_scan_batches(tenant_id, scanned_at DESC);
DROP TRIGGER IF EXISTS project_scan_snapshots_no_update;
ALTER TABLE project_scan_snapshots ADD COLUMN batch_id TEXT;
ALTER TABLE project_scan_snapshots ADD COLUMN health_score INTEGER NOT NULL DEFAULT 0 CHECK(health_score BETWEEN 0 AND 100);
UPDATE project_scan_snapshots SET health_score = CASE health
    WHEN 'ok' THEN 100 WHEN 'needs_attention' THEN 50 ELSE 0 END;
INSERT INTO project_scan_batches (id, tenant_id, scanned_at, project_count)
    SELECT MIN(id), tenant_id, scanned_at, COUNT(*)
    FROM project_scan_snapshots GROUP BY tenant_id, scanned_at;
UPDATE project_scan_snapshots
SET batch_id = (
    SELECT b.id FROM project_scan_batches b
    WHERE b.tenant_id = project_scan_snapshots.tenant_id
      AND b.scanned_at = project_scan_snapshots.scanned_at
);
CREATE TRIGGER project_scan_snapshots_no_update
BEFORE UPDATE ON project_scan_snapshots BEGIN
    SELECT RAISE(ABORT, 'project scan snapshots are append-only');
END;
CREATE TRIGGER project_scan_batches_no_update
BEFORE UPDATE ON project_scan_batches BEGIN
    SELECT RAISE(ABORT, 'project scan batches are append-only');
END;
CREATE TRIGGER project_scan_batches_no_delete
BEFORE DELETE ON project_scan_batches BEGIN
    SELECT RAISE(ABORT, 'project scan batches are append-only');
END;
""",
        down_sql="""
DROP TRIGGER IF EXISTS project_scan_batches_no_delete;
DROP TRIGGER IF EXISTS project_scan_batches_no_update;
DROP TRIGGER IF EXISTS project_scan_snapshots_no_update;
ALTER TABLE project_scan_snapshots DROP COLUMN health_score;
ALTER TABLE project_scan_snapshots DROP COLUMN batch_id;
DROP TABLE IF EXISTS project_scan_batches;
CREATE TRIGGER project_scan_snapshots_no_update
BEFORE UPDATE ON project_scan_snapshots BEGIN
    SELECT RAISE(ABORT, 'project scan snapshots are append-only');
END;
""",
        rollback_requires_empty=("project_scan_batches", "project_scan_snapshots"),
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
