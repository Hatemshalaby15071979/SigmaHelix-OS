"""Consistent SQLite export, checksummed manifests, and byte-identical restore."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .database import Database
from .migrations import MigrationRunner

_FORMAT = "sigmahelix-sqlite-backup-v1"
_REQUIRED_TABLES = {
    1: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
    },
    2: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
    },
    3: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
    },
    4: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
    },
    5: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
    },
    6: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
    },
    7: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
        "missed_job_runs",
    },
    8: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
        "missed_job_runs",
        "notifications",
    },
    9: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
        "missed_job_runs",
        "notifications",
        "notification_alarm_states",
        "notification_actions",
    },
    10: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
        "missed_job_runs",
        "notifications",
        "notification_alarm_states",
        "notification_actions",
        "project_scan_snapshots",
    },
    11: {
        "projects",
        "tasks",
        "notes",
        "events",
        "approvals",
        "evidence",
        "evidence_tags",
        "audit_log",
        "event_stream",
        "legacy_imports",
        "task_series",
        "task_occurrences",
        "scheduled_jobs",
        "job_runs",
        "missed_job_runs",
        "notifications",
        "notification_alarm_states",
        "notification_actions",
        "project_scan_snapshots",
        "launcher_profiles",
        "launcher_runs",
    },
}


class BackupError(RuntimeError):
    """Raised when a database export or restore fails validation."""


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """Integrity metadata stored beside a SQLite snapshot."""

    format: str
    created_at: str
    database_sha256: str
    size_bytes: int
    schema_version: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_absolute(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError(f"{label} must be an absolute Path")
    return path


def _manifest_path(database_path: Path) -> Path:
    return database_path.with_name(database_path.name + ".manifest.json")


def _validate_database(path: Path) -> int:
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5.0)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise BackupError(f"SQLite integrity check failed: {integrity}")
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise BackupError("SQLite foreign-key check failed")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise BackupError("backup is not a readable SQLite database") from exc
    if version < 1 or version > MigrationRunner(Database(path)).latest_version:
        raise BackupError(f"unsupported SigmaHelix schema version {version}")
    if version not in _REQUIRED_TABLES or not _REQUIRED_TABLES[version] <= tables:
        raise BackupError(f"schema version {version} is missing required tables")
    return version


class DatabaseBackup:
    """Create consistent, private SQLite snapshots and validate safe restores."""

    @staticmethod
    def manifest_path(database_path: Path) -> Path:
        """Return the required sidecar path for an exported database."""
        return _manifest_path(_require_absolute(database_path, "database path"))

    def export(self, source: Database, destination: Path) -> BackupManifest:
        """Snapshot a live database through SQLite backup API and write a manifest."""
        destination = _require_absolute(destination, "backup destination")
        if source.path.resolve(strict=False) == destination.resolve(strict=False):
            raise ValueError("backup destination must differ from the source database")
        if not source.path.is_file():
            raise FileNotFoundError(source.path)
        manifest_path = _manifest_path(destination)
        if destination.exists() or manifest_path.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        os.chmod(temp_dir, 0o700)
        temp_database = temp_dir / destination.name
        temp_manifest = temp_dir / "manifest.json"
        try:
            _validate_database(source.path)
            with source.connection() as source_connection:
                schema_version = int(
                    source_connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if (
                    schema_version < 1
                    or schema_version > MigrationRunner(source).latest_version
                ):
                    raise BackupError(
                        f"unsupported SigmaHelix schema version {schema_version}"
                    )
                target_connection = sqlite3.connect(temp_database)
                try:
                    source_connection.backup(target_connection)
                    integrity = target_connection.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()[0]
                    if integrity != "ok":
                        raise BackupError(
                            f"SQLite snapshot integrity failed: {integrity}"
                        )
                    target_connection.commit()
                finally:
                    target_connection.close()
            if _validate_database(temp_database) != schema_version:
                raise BackupError("snapshot schema version changed during export")
            os.chmod(temp_database, 0o600)
            _fsync_file(temp_database)
            manifest = BackupManifest(
                format=_FORMAT,
                created_at=datetime.now(UTC).isoformat(),
                database_sha256=_sha256(temp_database),
                size_bytes=temp_database.stat().st_size,
                schema_version=schema_version,
            )
            with temp_manifest.open("x", encoding="utf-8") as stream:
                json.dump(
                    asdict(manifest), stream, sort_keys=True, separators=(",", ":")
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_manifest, 0o600)
            os.link(temp_database, destination)
            try:
                os.link(temp_manifest, manifest_path)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
            _fsync_directory(destination.parent)
            return manifest
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def restore(self, source: Path, destination: Path) -> BackupManifest:
        """Verify the snapshot and atomically install a byte-identical new DB file."""
        source = _require_absolute(source, "backup source")
        destination = _require_absolute(destination, "restore destination")
        if source.resolve(strict=False) == destination.resolve(strict=False):
            raise ValueError("restore destination must differ from the backup source")
        if not source.is_file():
            raise FileNotFoundError(source)
        manifest_path = _manifest_path(source)
        if not manifest_path.is_file():
            raise BackupError("backup manifest is missing")
        if destination.exists():
            raise FileExistsError(destination)
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = BackupManifest(**raw_manifest)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BackupError("backup manifest is invalid") from exc
        if manifest.format != _FORMAT:
            raise BackupError("unsupported backup manifest format")
        if source.stat().st_size != manifest.size_bytes:
            raise BackupError("backup size does not match its manifest")
        if _sha256(source) != manifest.database_sha256:
            raise BackupError("backup checksum does not match its manifest")
        schema_version = _validate_database(source)
        if schema_version != manifest.schema_version:
            raise BackupError("backup schema version does not match its manifest")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        os.chmod(temp_dir, 0o700)
        temp_database = temp_dir / destination.name
        try:
            shutil.copyfile(source, temp_database)
            os.chmod(temp_database, 0o600)
            _fsync_file(temp_database)
            if _sha256(temp_database) != manifest.database_sha256:
                raise BackupError("restored database copy failed checksum verification")
            _validate_database(temp_database)
            os.link(temp_database, destination)
            _fsync_directory(destination.parent)
            return manifest
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
