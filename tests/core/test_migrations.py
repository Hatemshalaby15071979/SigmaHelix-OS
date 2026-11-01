import sqlite3
from datetime import datetime, timezone

import pytest

from sigmahelix.core.models import Task
from sigmahelix.core.storage import (
    Database,
    Migration,
    MigrationDataLossError,
    MigrationError,
    MigrationRunner,
    TaskRepository,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _version(database: Database) -> int:
    with database.connection() as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _application_objects(database: Database) -> set[tuple[str, str]]:
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND type IN ('table', 'view', 'trigger', 'index')"
        ).fetchall()
    return {(row["type"], row["name"]) for row in rows}


def test_migration_runner_applies_v0_to_v8_and_rolls_back_empty_database(tmp_path):
    database = Database(tmp_path / "migrations.db")
    runner = MigrationRunner(database)

    assert runner.current_version() == 0
    assert runner.upgrade() == 8
    assert ("table", "tasks") in _application_objects(database)
    assert ("table", "audit_log") in _application_objects(database)
    assert ("table", "event_stream") in _application_objects(database)
    assert ("table", "legacy_imports") in _application_objects(database)
    assert ("table", "task_series") in _application_objects(database)
    assert ("table", "task_occurrences") in _application_objects(database)
    assert ("table", "scheduled_jobs") in _application_objects(database)
    assert ("table", "job_runs") in _application_objects(database)
    assert ("table", "missed_job_runs") in _application_objects(database)
    assert ("table", "notifications") in _application_objects(database)
    assert ("view", "evidence_records") in _application_objects(database)

    assert runner.downgrade(0) == 0
    assert _application_objects(database) == set()
    assert runner.upgrade() == 8
    assert _version(database) == 8


def test_migration_runner_refuses_downgrade_when_it_would_drop_records(tmp_path):
    database = Database(tmp_path / "migration-data.db")
    database.initialize()
    task = Task("Keep this record", created_at=NOW, updated_at=NOW)
    TaskRepository(database).create(task)
    runner = MigrationRunner(database)

    with pytest.raises(MigrationDataLossError, match="tasks contains records"):
        runner.downgrade(0)

    assert runner.current_version() == 1
    assert TaskRepository(database).get(task.id) == task


def test_migration_failure_rolls_back_all_statements_and_version(tmp_path):
    database = Database(tmp_path / "migration-failure.db")
    migration = Migration(
        version=1,
        name="intentionally_invalid",
        up_sql="CREATE TABLE partial (id TEXT); CREATE TABL broken (id TEXT);",
        down_sql="DROP TABLE partial;",
    )
    runner = MigrationRunner(database, migrations=(migration,))

    with pytest.raises(sqlite3.OperationalError, match="TABL"):
        runner.upgrade()

    assert runner.current_version() == 0
    assert _application_objects(database) == set()


def test_migration_runner_rejects_untracked_and_newer_schemas(tmp_path):
    untracked = Database(tmp_path / "untracked.db")
    with untracked.transaction() as connection:
        connection.execute("CREATE TABLE foreign_schema (id TEXT)")
    with pytest.raises(MigrationError, match="untracked schema objects"):
        MigrationRunner(untracked).upgrade()

    newer = Database(tmp_path / "newer.db")
    with newer.connection() as connection:
        connection.execute("PRAGMA user_version = 9")
    with pytest.raises(MigrationError, match="newer than supported"):
        MigrationRunner(newer).upgrade()


def test_upgrade_and_downgrade_targets_cannot_move_in_the_wrong_direction(tmp_path):
    database = Database(tmp_path / "migration-direction.db")
    runner = MigrationRunner(database)
    runner.upgrade()

    with pytest.raises(MigrationError, match="use downgrade"):
        runner.upgrade(target_version=0)
    extended_runner = MigrationRunner(
        database,
        migrations=(
            Migration(1, "v1", "", ""),
            Migration(2, "v2", "", ""),
            Migration(3, "v3", "", ""),
            Migration(4, "v4", "", ""),
            Migration(5, "v5", "", ""),
            Migration(6, "v6", "", ""),
            Migration(7, "v7", "", ""),
            Migration(8, "v8", "", ""),
            Migration(9, "v9", "", ""),
            Migration(10, "v10", "", ""),
        ),
    )
    with pytest.raises(MigrationError, match="above the current version"):
        extended_runner.downgrade(target_version=9)


def test_migration_versions_must_be_contiguous(tmp_path):
    database = Database(tmp_path / "bad-registry.db")
    migration = Migration(2, "skips_v1", "", "")

    with pytest.raises(ValueError, match="contiguous"):
        MigrationRunner(database, migrations=(migration,))


def test_migration_runner_refuses_to_remove_a_populated_audit_log(tmp_path):
    from sigmahelix.core.storage import AuditLog

    database = Database(tmp_path / "audit-migration.db")
    database.initialize()
    AuditLog(database).append("task.created", "task", "task-1", {"ok": True})

    with pytest.raises(MigrationDataLossError, match="audit_log contains records"):
        MigrationRunner(database).downgrade(1)

    assert MigrationRunner(database).current_version() == 2
