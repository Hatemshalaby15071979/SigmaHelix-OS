from types import SimpleNamespace
from uuid import UUID

import pytest

from sigmahelix.core.storage import (
    AuditLog,
    Database,
    EventBus,
    LegacyImportConflict,
    LegacyImportError,
    LegacySessionImporter,
    NoteRepository,
    TaskRepository,
)

SOURCE_ID = UUID("ca26eed3-03dd-4ac8-a5a1-7f73b53abdfa")


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "legacy-import" / "sigmahelix.db")
    db.initialize()
    return db


def _managers():
    return (
        SimpleNamespace(
            tasks=[
                {
                    "id": 3,
                    "name": "Review migration plan",
                    "frequency": "weekly",
                    "created": "2026-10-30",
                    "completed": False,
                },
                {
                    "id": 8,
                    "name": "Send follow-up",
                    "frequency": "daily",
                    "created": "2026-10-31",
                    "completed": True,
                },
            ]
        ),
        SimpleNamespace(
            notes=[
                {
                    "id": 2,
                    "content": "Talked through the SQLite rollout.",
                    "created": "2026-10-31",
                }
            ]
        ),
    )


def test_live_legacy_managers_import_once_with_durable_receipts(database):
    tasks, notes = _managers()
    importer = LegacySessionImporter(database)

    imported = importer.import_managers(SOURCE_ID, tasks, notes)
    repeated = importer.import_managers(SOURCE_ID, tasks, notes)

    assert imported.imported
    assert imported.task_count == 2
    assert imported.note_count == 1
    assert not repeated.imported
    assert repeated == imported.__class__(
        SOURCE_ID,
        imported.snapshot_sha256,
        2,
        1,
        False,
    )
    imported_tasks = TaskRepository(database).list_all()
    assert [task.title for task in imported_tasks] == [
        "Review migration plan",
        "Send follow-up",
    ]
    assert imported_tasks[0].description.endswith("frequency: weekly")
    assert imported_tasks[1].status.value == "done"
    assert [note.content for note in NoteRepository(database).list_all()] == [
        "Talked through the SQLite rollout."
    ]
    assert AuditLog(database).verify().entries_checked == 1
    replay = EventBus(database).replay(event_type="legacy.session.imported")
    assert len(replay) == 1
    assert replay[0].event.payload["snapshot_sha256"] == imported.snapshot_sha256


def test_same_source_id_with_changed_snapshot_is_rejected(database):
    importer = LegacySessionImporter(database)
    tasks, notes = _managers()
    importer.import_managers(SOURCE_ID, tasks, notes)
    changed = SimpleNamespace(tasks=[{**tasks.tasks[0], "name": "Changed name"}])

    with pytest.raises(LegacyImportConflict, match="different data"):
        importer.import_managers(SOURCE_ID, changed, notes)

    assert len(TaskRepository(database).list_all()) == 2
    assert len(NoteRepository(database).list_all()) == 1


def test_invalid_or_secret_bearing_snapshot_fails_before_writing(database):
    importer = LegacySessionImporter(database)
    duplicate_tasks = [
        {"id": 1, "name": "First", "created": "2026-10-31"},
        {"id": 1, "name": "Duplicate", "created": "2026-10-31"},
    ]
    with pytest.raises(LegacyImportError, match="duplicate legacy task id"):
        importer.import_snapshot(SOURCE_ID, duplicate_tasks, [])

    secret_note = [
        {
            "id": 1,
            "content": "password=never-store-this",
            "created": "2026-10-31",
        }
    ]
    with pytest.raises(LegacyImportError, match="secret-like data"):
        importer.import_snapshot(SOURCE_ID, [], secret_note)

    assert TaskRepository(database).list_all() == []
    assert NoteRepository(database).list_all() == []
    assert AuditLog(database).verify().entries_checked == 0


def test_legacy_import_marker_prevents_downgrade_that_loses_idempotence(database):
    from sigmahelix.core.storage import (
        MigrationDataLossError,
        MigrationRunner,
    )

    tasks, notes = _managers()
    LegacySessionImporter(database).import_managers(SOURCE_ID, tasks, notes)

    with pytest.raises(MigrationDataLossError, match="legacy_imports contains records"):
        MigrationRunner(database).downgrade(3)

    assert MigrationRunner(database).current_version() == 4
