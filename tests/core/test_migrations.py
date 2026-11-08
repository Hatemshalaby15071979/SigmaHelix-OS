import sqlite3
from datetime import UTC, datetime

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
from sigmahelix.core.storage.migrations import CORE_MIGRATIONS

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


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


def test_migration_runner_applies_every_migration_and_rolls_back_empty_database(
    tmp_path,
):
    database = Database(tmp_path / "migrations.db")
    runner = MigrationRunner(database)

    assert runner.current_version() == 0
    assert runner.upgrade() == runner.latest_version
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
    assert ("table", "notification_alarm_states") in _application_objects(database)
    assert ("table", "notification_actions") in _application_objects(database)
    assert ("table", "project_scan_snapshots") in _application_objects(database)
    assert ("table", "launcher_profiles") in _application_objects(database)
    assert ("table", "launcher_runs") in _application_objects(database)
    assert ("table", "project_scan_batches") in _application_objects(database)
    with database.connection() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(project_scan_snapshots)")
        }
    assert "artifacts_json" in columns
    assert ("view", "evidence_records") in _application_objects(database)

    assert runner.downgrade(0) == 0
    assert _application_objects(database) == set()
    assert runner.upgrade() == runner.latest_version
    assert _version(database) == runner.latest_version


def test_migration_runner_refuses_downgrade_when_it_would_drop_records(tmp_path):
    database = Database(tmp_path / "migration-data.db")
    database.initialize()
    task = TaskRepository(database).create(
        Task("Keep this record", created_at=NOW, updated_at=NOW)
    )
    runner = MigrationRunner(database)

    with pytest.raises(MigrationDataLossError, match="tasks contains records"):
        runner.downgrade(0)

    assert runner.current_version() == runner.latest_version
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
        connection.execute(
            f"PRAGMA user_version = {MigrationRunner(newer).latest_version + 1}"
        )
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
            *CORE_MIGRATIONS,
            Migration(MigrationRunner(database).latest_version + 1, "next", "", ""),
        ),
    )
    with pytest.raises(MigrationError, match="above the current version"):
        extended_runner.downgrade(target_version=runner.latest_version + 1)


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

    # A blocked downgrade must not partially roll back the schema.
    assert MigrationRunner(database).current_version() == (
        MigrationRunner(database).latest_version
    )


def test_alarm_migration_backfills_existing_notifications(tmp_path):
    database = Database(tmp_path / "alarm-backfill.db")
    runner = MigrationRunner(database)
    runner.upgrade(target_version=8)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO notifications "
            "(id, tenant_id, dedupe_key, title, body, created_at, read_at, native_status) "
            "VALUES ('notification-1', 'local', 'existing', 'Existing', '', ?, NULL, 'unavailable')",
            (NOW.isoformat(),),
        )

    assert runner.upgrade() == runner.latest_version
    with database.connection() as connection:
        row = connection.execute(
            "SELECT state FROM notification_alarm_states WHERE notification_id = ?",
            ("notification-1",),
        ).fetchone()
    assert row["state"] == "pending"


def test_health_migration_backfills_old_snapshots_and_batch_membership(tmp_path):
    database = Database(tmp_path / "scan-backfill.db")
    runner = MigrationRunner(database)
    runner.upgrade(target_version=12)
    project_id = "project-existing"
    snapshot_id = "snapshot-existing"
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO projects "
            "(id, tenant_id, name, root_path, created_at, updated_at, last_scanned_at, deleted_at) "
            "VALUES (?, 'local', 'Existing', ?, ?, ?, ?, NULL)",
            (
                project_id,
                str((tmp_path / "existing").resolve()),
                NOW.isoformat(),
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO project_scan_snapshots "
            "(id, tenant_id, project_id, scanned_at, git_branch, git_commit, git_dirty, git_change_count, manifests_json, entrypoints_json, findings_json, health, artifacts_json) "
            "VALUES (?, 'local', ?, ?, NULL, NULL, NULL, 0, '[]', '[]', '[\"missing_readme\"]', 'needs_attention', '[]')",
            (snapshot_id, project_id, NOW.isoformat()),
        )

    assert runner.upgrade() == runner.latest_version
    with database.connection() as connection:
        snapshot = connection.execute(
            "SELECT batch_id, health_score FROM project_scan_snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        batch_count = connection.execute(
            "SELECT COUNT(*) FROM project_scan_batches"
        ).fetchone()[0]
    assert snapshot["batch_id"]
    assert snapshot["health_score"] == 50
    assert batch_count == 1


def test_metacognition_ledger_migration_creates_and_drops_its_tables(tmp_path):
    from sigmahelix.core.storage.backup import _REQUIRED_TABLES

    database = Database(tmp_path / "ledger.db")
    runner = MigrationRunner(database)
    assert runner.upgrade() == 16

    objects = _application_objects(database)
    for table in (
        "agent_turns",
        "agent_steps",
        "agent_feedback",
        "agent_recommendations",
    ):
        assert ("table", table) in objects
        assert table in _REQUIRED_TABLES[16]
        assert table in _REQUIRED_TABLES[runner.latest_version]

    # an empty ledger downgrades cleanly
    assert runner.downgrade(15) == 15
    objects = _application_objects(database)
    assert ("table", "agent_turns") not in objects
    assert ("table", "agent_steps") not in objects
    assert ("table", "task_questions") in objects
