"""One-time import of a live legacy TasksManager/NotesManager snapshot."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from ..logging import redact_text
from ..models import TaskStatus
from .audit import AuditLog
from .database import Database


class LegacyImportError(ValueError):
    """Raised when a legacy snapshot is malformed or unsafe to import."""


class LegacyImportConflict(LegacyImportError):
    """Raised when a source session ID is reused for different snapshot data."""


class _TaskManager(Protocol):
    tasks: Sequence[Mapping[str, Any]]


class _NoteManager(Protocol):
    notes: Sequence[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    """Counts and digest for an imported or previously imported snapshot."""

    source_id: UUID
    snapshot_sha256: str
    task_count: int
    note_count: int
    imported: bool


def _secret_check(value: str, label: str) -> None:
    if redact_text(value) != value:
        raise LegacyImportError(f"legacy {label} contains secret-like data")


def _legacy_date(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise LegacyImportError(f"legacy {label} must be a YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise LegacyImportError(f"legacy {label} must be a YYYY-MM-DD string") from exc
    if parsed.isoformat() != value:
        raise LegacyImportError(f"legacy {label} must be a YYYY-MM-DD string")
    return datetime.combine(parsed, datetime.min.time(), UTC)


def _next_display_id(connection: sqlite3.Connection, table: str, tenant_id: str) -> int:
    """Next human-facing number for a table; callers pass a fixed table name."""
    row = connection.execute(
        f"SELECT COALESCE(MAX(display_id), 0) + 1 FROM {table} WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchone()
    return int(row[0])


def _positive_id(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LegacyImportError(f"legacy {label} must be a positive integer")
    return value


def _normalize_tasks(
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)):
        raise LegacyImportError("legacy tasks must be a sequence of mappings")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, raw in enumerate(tasks):
        if not isinstance(raw, Mapping):
            raise LegacyImportError(f"legacy task {index} must be a mapping")
        if not set(raw) <= {
            "id",
            "name",
            "frequency",
            "created",
            "completed",
            "pinned",
        }:
            raise LegacyImportError(f"legacy task {index} has unsupported fields")
        legacy_id = _positive_id(raw.get("id"), f"task {index} id")
        if legacy_id in seen_ids:
            raise LegacyImportError(f"duplicate legacy task id {legacy_id}")
        seen_ids.add(legacy_id)
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise LegacyImportError(f"legacy task {legacy_id} name must be non-empty")
        _secret_check(name, f"task {legacy_id} name")
        frequency = raw.get("frequency", "daily")
        if not isinstance(frequency, str) or frequency not in {
            "daily",
            "weekly",
            "monthly",
        }:
            raise LegacyImportError(f"legacy task {legacy_id} frequency is unsupported")
        created_at = _legacy_date(raw.get("created"), f"task {legacy_id} created")
        completed = raw.get("completed", False)
        if not isinstance(completed, bool):
            raise LegacyImportError(
                f"legacy task {legacy_id} completed must be boolean"
            )
        pinned = raw.get("pinned", False)
        if not isinstance(pinned, bool):
            raise LegacyImportError(f"legacy task {legacy_id} pinned must be boolean")
        normalized.append(
            {
                "id": legacy_id,
                "name": name.strip(),
                "frequency": frequency,
                "created": created_at.date().isoformat(),
                "completed": completed,
                "pinned": pinned,
            }
        )
    return normalized


def _normalize_notes(notes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(notes, Sequence) or isinstance(notes, (str, bytes)):
        raise LegacyImportError("legacy notes must be a sequence of mappings")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for index, raw in enumerate(notes):
        if not isinstance(raw, Mapping):
            raise LegacyImportError(f"legacy note {index} must be a mapping")
        if not set(raw) <= {"id", "content", "created", "updated", "pinned"}:
            raise LegacyImportError(f"legacy note {index} has unsupported fields")
        legacy_id = _positive_id(raw.get("id"), f"note {index} id")
        if legacy_id in seen_ids:
            raise LegacyImportError(f"duplicate legacy note id {legacy_id}")
        seen_ids.add(legacy_id)
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LegacyImportError(
                f"legacy note {legacy_id} content must be non-empty"
            )
        _secret_check(content, f"note {legacy_id}")
        created_at = _legacy_date(raw.get("created"), f"note {legacy_id} created")
        pinned = raw.get("pinned", False)
        if not isinstance(pinned, bool):
            raise LegacyImportError(f"legacy note {legacy_id} pinned must be boolean")
        normalized.append(
            {
                "id": legacy_id,
                "content": content.strip(),
                "created": created_at.date().isoformat(),
                "pinned": pinned,
            }
        )
    return normalized


class LegacySessionImporter:
    """Import legacy in-memory tasks and notes once per source-session UUID."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def import_managers(
        self,
        source_id: UUID,
        task_manager: _TaskManager,
        note_manager: _NoteManager,
        tenant_id: str = "local",
    ) -> LegacyImportResult:
        """Copy manager lists while they are alive, then perform one atomic import."""
        try:
            tasks = tuple(dict(item) for item in task_manager.tasks)
            notes = tuple(dict(item) for item in note_manager.notes)
        except (AttributeError, TypeError, ValueError) as exc:
            raise LegacyImportError(
                "legacy managers must expose task and note mapping sequences"
            ) from exc
        return self.import_snapshot(source_id, tasks, notes, tenant_id)

    def import_snapshot(
        self,
        source_id: UUID,
        tasks: Sequence[Mapping[str, Any]],
        notes: Sequence[Mapping[str, Any]],
        tenant_id: str = "local",
    ) -> LegacyImportResult:
        """Validate, hash, and atomically import tasks, notes, event, and audit row."""
        if not isinstance(source_id, UUID):
            raise LegacyImportError("source_id must be a stable UUID")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise LegacyImportError("tenant_id must be a non-empty string")
        normalized_tasks = _normalize_tasks(tasks)
        normalized_notes = _normalize_notes(notes)
        snapshot_json = json.dumps(
            {
                "tasks": normalized_tasks,
                "notes": normalized_notes,
                "tenant_id": tenant_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()

        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT snapshot_sha256, task_count, note_count "
                "FROM legacy_imports WHERE source_id = ?",
                (str(source_id),),
            ).fetchone()
            if existing is not None:
                if existing["snapshot_sha256"] != snapshot_hash:
                    raise LegacyImportConflict(
                        "legacy source ID was already imported with different data"
                    )
                return LegacyImportResult(
                    source_id,
                    snapshot_hash,
                    int(existing["task_count"]),
                    int(existing["note_count"]),
                    False,
                )

            for task in normalized_tasks:
                created = _legacy_date(task["created"], "task created")
                task_uuid = uuid5(
                    NAMESPACE_URL, f"sigmahelix:legacy:{source_id}:task:{task['id']}"
                )
                display_id = _next_display_id(connection, "tasks", tenant_id)
                connection.execute(
                    "INSERT INTO tasks (id, tenant_id, title, description, status, "
                    "project_id, due_at, created_at, updated_at, pinned, display_id, "
                    "recurrence, deleted_at) "
                    "VALUES (?, ?, ?, '', ?, NULL, NULL, ?, ?, ?, ?, ?, NULL)",
                    (
                        str(task_uuid),
                        tenant_id,
                        task["name"],
                        TaskStatus.DONE.value
                        if task["completed"]
                        else TaskStatus.TODO.value,
                        created.isoformat(),
                        created.isoformat(),
                        int(task["pinned"]),
                        display_id,
                        task["frequency"],
                    ),
                )
            for note in normalized_notes:
                created = _legacy_date(note["created"], "note created")
                note_uuid = uuid5(
                    NAMESPACE_URL, f"sigmahelix:legacy:{source_id}:note:{note['id']}"
                )
                display_id = _next_display_id(connection, "notes", tenant_id)
                connection.execute(
                    "INSERT INTO notes (id, tenant_id, content, project_id, created_at, "
                    "updated_at, pinned, display_id, deleted_at) "
                    "VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL)",
                    (
                        str(note_uuid),
                        tenant_id,
                        note["content"],
                        created.isoformat(),
                        created.isoformat(),
                        int(note["pinned"]),
                        display_id,
                    ),
                )
            imported_at = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO legacy_imports (source_id, snapshot_sha256, imported_at, "
                "task_count, note_count) VALUES (?, ?, ?, ?, ?)",
                (
                    str(source_id),
                    snapshot_hash,
                    imported_at,
                    len(normalized_tasks),
                    len(normalized_notes),
                ),
            )
            event_payload = {
                "source_id": str(source_id),
                "snapshot_sha256": snapshot_hash,
                "task_count": len(normalized_tasks),
                "note_count": len(normalized_notes),
            }
            connection.execute(
                "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid5(NAMESPACE_URL, f"sigmahelix:legacy:{source_id}:event")),
                    tenant_id,
                    "legacy.session.imported",
                    json.dumps(event_payload, sort_keys=True, separators=(",", ":")),
                    imported_at,
                ),
            )
            AuditLog(self.database).append_in_transaction(
                connection,
                "legacy.session.imported",
                "legacy_session",
                str(source_id),
                event_payload,
                tenant_id=tenant_id,
                occurred_at=datetime.fromisoformat(imported_at),
            )
        return LegacyImportResult(
            source_id,
            snapshot_hash,
            len(normalized_tasks),
            len(normalized_notes),
            True,
        )
