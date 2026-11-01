import hashlib
import json
import sqlite3

import pytest

from sigmahelix.core.models import Event, Task
from sigmahelix.core.storage import (
    AuditLog,
    BackupError,
    Database,
    DatabaseBackup,
    EventRepository,
    TaskRepository,
)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_export_and_restore_round_trip_byte_identically(tmp_path):
    source = Database(tmp_path / "source" / "sigmahelix.db")
    source.initialize()
    task = Task("Durable task")
    TaskRepository(source).create(task)
    EventRepository(source).create(Event("task.created", {"id": str(task.id)}))
    AuditLog(source).append("task.created", "task", str(task.id), {"ok": True})

    backup_path = tmp_path / "exports" / "snapshot.db"
    restored_path = tmp_path / "restore" / "sigmahelix.db"
    service = DatabaseBackup()
    manifest = service.export(source, backup_path)
    restored_manifest = service.restore(backup_path, restored_path)

    assert manifest == restored_manifest
    assert manifest.size_bytes == backup_path.stat().st_size
    assert manifest.database_sha256 == _digest(backup_path) == _digest(restored_path)
    assert manifest.schema_version == 9
    assert restored_path.stat().st_mode & 0o777 == 0o600
    assert DatabaseBackup.manifest_path(backup_path).stat().st_mode & 0o777 == 0o600

    restored = Database(restored_path)
    assert TaskRepository(restored).get(task.id) == task
    assert AuditLog(restored).verify().valid
    with restored.connection() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute("SELECT COUNT(*) FROM event_stream").fetchone()[0] == 1
        )


def test_restore_refuses_checksum_tampering_and_leaves_no_destination(tmp_path):
    source = Database(tmp_path / "original.db")
    source.initialize()
    backup = tmp_path / "snapshot.db"
    service = DatabaseBackup()
    service.export(source, backup)
    backup.write_bytes(backup.read_bytes() + b"tamper")
    destination = tmp_path / "restored.db"

    with pytest.raises(BackupError, match="size does not match"):
        service.restore(backup, destination)

    assert not destination.exists()


def test_export_and_restore_refuse_to_overwrite_files(tmp_path):
    source = Database(tmp_path / "original.db")
    source.initialize()
    backup_path = tmp_path / "backup.db"
    service = DatabaseBackup()
    service.export(source, backup_path)

    with pytest.raises(FileExistsError):
        service.export(source, backup_path)
    with pytest.raises(FileExistsError):
        service.restore(backup_path, tmp_path / "original.db")


def test_restore_rejects_missing_or_invalid_manifest(tmp_path):
    backup = tmp_path / "backup.db"
    destination = tmp_path / "restored.db"
    backup.write_bytes(b"not sqlite")
    service = DatabaseBackup()

    with pytest.raises(BackupError, match="manifest is missing"):
        service.restore(backup, destination)

    DatabaseBackup.manifest_path(backup).write_text("{}", encoding="utf-8")
    with pytest.raises(BackupError, match="manifest is invalid"):
        service.restore(backup, destination)


def test_restore_rejects_a_checksum_valid_non_database(tmp_path):
    backup = tmp_path / "fake.db"
    backup.write_bytes(b"not sqlite")
    DatabaseBackup.manifest_path(backup).write_text(
        json.dumps(
            {
                "format": "sigmahelix-sqlite-backup-v1",
                "created_at": "2026-11-02T00:00:00+00:00",
                "database_sha256": _digest(backup),
                "size_bytes": backup.stat().st_size,
                "schema_version": 9,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(BackupError, match="not a readable SQLite database"):
        DatabaseBackup().restore(backup, tmp_path / "restored.db")


def test_restore_rejects_database_with_unknown_sigmahelix_schema(tmp_path):
    backup = tmp_path / "broken.db"
    connection = sqlite3.connect(backup)
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
    connection.execute("PRAGMA user_version = 9")
    connection.commit()
    connection.close()
    DatabaseBackup.manifest_path(backup).write_text(
        json.dumps(
            {
                "format": "sigmahelix-sqlite-backup-v1",
                "created_at": "2026-11-02T00:00:00+00:00",
                "database_sha256": _digest(backup),
                "size_bytes": backup.stat().st_size,
                "schema_version": 9,
            }
        ),
        encoding="utf-8",
    )

    # A checksum-valid SQLite database without the version's required tables is rejected.
    with pytest.raises(BackupError, match="missing required tables"):
        DatabaseBackup().restore(backup, tmp_path / "restored.db")
