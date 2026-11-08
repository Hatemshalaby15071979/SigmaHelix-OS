"""Tenant-scoped SQLite repositories for the durable domain records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Generic, TypeVar
from uuid import UUID

from ..models import (
    Approval,
    ApprovalStatus,
    Event,
    Evidence,
    Note,
    Project,
    QuestionStatus,
    RiskLevel,
    Task,
    TaskQuestion,
    TaskStatus,
)
from .database import Database

T = TypeVar("T")


class RepositoryOperationError(RuntimeError):
    """Raised when an operation would violate a record's lifecycle policy."""


@dataclass(frozen=True, slots=True)
class _Codec(Generic[T]):
    table: str
    columns: tuple[str, ...]
    encode: Callable[[T], dict[str, object]]
    decode: Callable[[sqlite3.Row], T]
    order_by: str
    soft_delete: bool = False
    mutable: bool = True
    read_table: str | None = None
    insert_related: Callable[[sqlite3.Connection, T], None] | None = None
    allocates_display_id: bool = False


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value is not None else None


def _task_encode(record: Task) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "title": record.title,
        "description": record.description,
        "status": record.status.value,
        "project_id": str(record.project_id) if record.project_id else None,
        "due_at": _time(record.due_at),
        "created_at": _time(record.created_at),
        "updated_at": _time(record.updated_at),
        "pinned": int(record.pinned),
        "display_id": record.display_id,
        "recurrence": record.recurrence,
    }


def _task_decode(row: sqlite3.Row) -> Task:
    return Task(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        title=row["title"],
        description=row["description"],
        status=TaskStatus(row["status"]),
        project_id=_uuid(row["project_id"]),
        due_at=_parse_time(row["due_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        pinned=bool(row["pinned"]),
        display_id=int(row["display_id"]),
        recurrence=row["recurrence"],
    )


def _note_encode(record: Note) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "content": record.content,
        "project_id": str(record.project_id) if record.project_id else None,
        "created_at": _time(record.created_at),
        "updated_at": _time(record.updated_at),
        "pinned": int(record.pinned),
        "display_id": record.display_id,
    }


def _note_decode(row: sqlite3.Row) -> Note:
    return Note(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        content=row["content"],
        project_id=_uuid(row["project_id"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        pinned=bool(row["pinned"]),
        display_id=int(row["display_id"]),
    )


def _project_encode(record: Project) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "name": record.name,
        "root_path": str(record.root_path),
        "created_at": _time(record.created_at),
        "updated_at": _time(record.updated_at),
        "last_scanned_at": _time(record.last_scanned_at),
    }


def _project_decode(row: sqlite3.Row) -> Project:
    return Project(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        name=row["name"],
        root_path=Path(row["root_path"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_scanned_at=_parse_time(row["last_scanned_at"]),
    )


def _event_encode(record: Event) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "event_type": record.event_type,
        "payload_json": json.dumps(
            record.payload, sort_keys=True, separators=(",", ":")
        ),
        "occurred_at": _time(record.occurred_at),
    }


def _event_decode(row: sqlite3.Row) -> Event:
    return Event(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        event_type=row["event_type"],
        payload=json.loads(row["payload_json"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
    )


def _approval_encode(record: Approval) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "action": record.action,
        "risk": record.risk.value,
        "payload_sha256": record.payload_sha256,
        "status": record.status.value,
        "created_at": _time(record.created_at),
        "expires_at": _time(record.expires_at),
        "decided_at": _time(record.decided_at),
        "decided_by": record.decided_by,
    }


def _approval_decode(row: sqlite3.Row) -> Approval:
    return Approval(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        action=row["action"],
        risk=RiskLevel(row["risk"]),
        payload_sha256=row["payload_sha256"],
        status=ApprovalStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
        decided_at=_parse_time(row["decided_at"]),
        decided_by=row["decided_by"],
    )


def _evidence_encode(record: Evidence) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "source_type": record.source_type,
        "source_ref": record.source_ref,
        "claim": record.claim,
        "project_id": str(record.project_id) if record.project_id else None,
        "metric": record.metric,
        "artifact_sha256": record.artifact_sha256,
        "verified_by": record.verified_by,
        "confidence": record.confidence,
        "captured_at": _time(record.captured_at),
        "last_seen": _time(record.last_seen),
    }


def _evidence_decode(row: sqlite3.Row) -> Evidence:
    return Evidence(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        claim=row["claim"],
        project_id=_uuid(row["project_id"]),
        metric=row["metric"],
        artifact_sha256=row["artifact_sha256"],
        verified_by=row["verified_by"],
        confidence=row["confidence"],
        tags=tuple(json.loads(row["tags_json"])),
        captured_at=datetime.fromisoformat(row["captured_at"]),
        last_seen=_parse_time(row["last_seen"]),
    )


class SqliteRepository(Generic[T]):
    """Typed record access; SQL identifiers come only from local codec metadata."""

    def __init__(self, database: Database, codec: _Codec[T]) -> None:
        self.database = database
        self.codec = codec

    def create(self, record: T) -> T:
        values = self.codec.encode(record)
        columns = self.codec.columns
        if set(values) != set(columns):
            raise RepositoryOperationError(
                "repository codec fields do not match record"
            )
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {self.codec.table} ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        with self.database.transaction() as connection:
            if self.codec.allocates_display_id and values.get("display_id") == 0:
                values["display_id"] = self._next_display_id(
                    connection, str(values["tenant_id"])
                )
                record = replace(record, display_id=values["display_id"])  # type: ignore[type-var]
            connection.execute(sql, tuple(values[column] for column in columns))
            if self.codec.insert_related is not None:
                self.codec.insert_related(connection, record)
        return record

    def _next_display_id(self, connection: sqlite3.Connection, tenant_id: str) -> int:
        """Allocate the next human-facing number inside the write transaction.

        Numbers are never reused, including for soft-deleted records, so an
        "ID 7" the user saw yesterday always refers to the same record.
        """
        row = connection.execute(
            f"SELECT COALESCE(MAX(display_id), 0) + 1 FROM {self.codec.table} "
            "WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return int(row[0])

    def get(self, record_id: UUID, tenant_id: str = "local") -> T | None:
        sql = f"SELECT * FROM {self.codec.read_table or self.codec.table} WHERE id = ? AND tenant_id = ?"
        if self.codec.soft_delete:
            sql += " AND deleted_at IS NULL"
        with self.database.connection() as connection:
            row = connection.execute(sql, (str(record_id), tenant_id)).fetchone()
        return self.codec.decode(row) if row is not None else None

    def list_all(self, tenant_id: str = "local") -> list[T]:
        sql = f"SELECT * FROM {self.codec.read_table or self.codec.table} WHERE tenant_id = ?"
        if self.codec.soft_delete:
            sql += " AND deleted_at IS NULL"
        sql += f" ORDER BY {self.codec.order_by}"
        with self.database.connection() as connection:
            rows = connection.execute(sql, (tenant_id,)).fetchall()
        return [self.codec.decode(row) for row in rows]

    def update(self, record: T) -> T:
        if not self.codec.mutable:
            raise RepositoryOperationError(
                f"{self.codec.table} records are append-only"
            )
        values = self.codec.encode(record)
        record_id = values.pop("id")
        tenant_id = values.pop("tenant_id")
        assignments = ", ".join(f"{column} = ?" for column in values)
        sql = (
            f"UPDATE {self.codec.table} SET {assignments} "
            "WHERE id = ? AND tenant_id = ?"
        )
        if self.codec.soft_delete:
            sql += " AND deleted_at IS NULL"
        with self.database.transaction() as connection:
            cursor = connection.execute(sql, (*values.values(), record_id, tenant_id))
            if cursor.rowcount != 1:
                raise KeyError(f"{self.codec.table} record was not found")
        return record

    def delete(self, record_id: UUID, tenant_id: str = "local") -> bool:
        if not self.codec.soft_delete:
            raise RepositoryOperationError(
                f"{self.codec.table} records cannot be deleted"
            )
        deleted_at = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE {self.codec.table} SET deleted_at = ? "
                "WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL",
                (deleted_at, str(record_id), tenant_id),
            )
        return cursor.rowcount == 1


class TaskRepository(SqliteRepository[Task]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "tasks",
                (
                    "id",
                    "tenant_id",
                    "title",
                    "description",
                    "status",
                    "project_id",
                    "due_at",
                    "created_at",
                    "updated_at",
                    "pinned",
                    "display_id",
                    "recurrence",
                ),
                _task_encode,
                _task_decode,
                "pinned DESC, display_id, id",
                soft_delete=True,
                allocates_display_id=True,
            ),
        )


def _question_encode(record: TaskQuestion) -> dict[str, object]:
    return {
        "id": str(record.id),
        "tenant_id": record.tenant_id,
        "task_id": str(record.task_id),
        "question": record.question,
        "answer": record.answer,
        "evidence": record.evidence,
        "status": record.status.value,
        "created_at": _time(record.created_at),
        "updated_at": _time(record.updated_at),
        "answered_at": _time(record.answered_at),
        "display_id": record.display_id,
    }


def _question_decode(row: sqlite3.Row) -> TaskQuestion:
    return TaskQuestion(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        task_id=UUID(row["task_id"]),
        question=row["question"],
        answer=row["answer"],
        evidence=row["evidence"],
        status=QuestionStatus(row["status"]),
        created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_time(row["updated_at"]),  # type: ignore[arg-type]
        answered_at=_parse_time(row["answered_at"]),
        display_id=row["display_id"],
    )


class TaskQuestionRepository(SqliteRepository[TaskQuestion]):
    """Questions attached to a task; answered ones carry their evidence."""

    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "task_questions",
                (
                    "id",
                    "tenant_id",
                    "task_id",
                    "question",
                    "answer",
                    "evidence",
                    "status",
                    "created_at",
                    "updated_at",
                    "answered_at",
                    "display_id",
                ),
                _question_encode,
                _question_decode,
                "display_id, id",
                soft_delete=True,
                allocates_display_id=True,
            ),
        )

    def list_for_task(
        self, task_id: UUID, tenant_id: str = "local"
    ) -> list[TaskQuestion]:
        """Every question of one task, in the order it was written."""
        sql = (
            "SELECT * FROM task_questions "
            "WHERE tenant_id = ? AND task_id = ? AND deleted_at IS NULL "
            "ORDER BY display_id, id"
        )
        with self.database.connection() as connection:
            rows = connection.execute(sql, (tenant_id, str(task_id))).fetchall()
        return [self.codec.decode(row) for row in rows]

    def delete_for_task(self, task_id: UUID, tenant_id: str = "local") -> int:
        """Soft-delete every question of a task. Returns how many were closed."""
        stamp = datetime.now(UTC).isoformat()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE task_questions SET deleted_at = ? "
                "WHERE tenant_id = ? AND task_id = ? AND deleted_at IS NULL",
                (stamp, tenant_id, str(task_id)),
            )
        return cursor.rowcount


class NoteRepository(SqliteRepository[Note]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "notes",
                (
                    "id",
                    "tenant_id",
                    "content",
                    "project_id",
                    "created_at",
                    "updated_at",
                    "pinned",
                    "display_id",
                ),
                _note_encode,
                _note_decode,
                "pinned DESC, display_id, id",
                soft_delete=True,
                allocates_display_id=True,
            ),
        )


class ProjectRepository(SqliteRepository[Project]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "projects",
                (
                    "id",
                    "tenant_id",
                    "name",
                    "root_path",
                    "created_at",
                    "updated_at",
                    "last_scanned_at",
                ),
                _project_encode,
                _project_decode,
                "name, id",
                soft_delete=True,
            ),
        )


class EventRepository(SqliteRepository[Event]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "events",
                ("id", "tenant_id", "event_type", "payload_json", "occurred_at"),
                _event_encode,
                _event_decode,
                "occurred_at, id",
                mutable=False,
            ),
        )


class ApprovalRepository(SqliteRepository[Approval]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "approvals",
                (
                    "id",
                    "tenant_id",
                    "action",
                    "risk",
                    "payload_sha256",
                    "status",
                    "created_at",
                    "expires_at",
                    "decided_at",
                    "decided_by",
                ),
                _approval_encode,
                _approval_decode,
                "created_at, id",
            ),
        )


def _insert_evidence_tags(connection: sqlite3.Connection, record: Evidence) -> None:
    connection.executemany(
        "INSERT INTO evidence_tags (tenant_id, evidence_id, tag) VALUES (?, ?, ?)",
        ((record.tenant_id, str(record.id), tag) for tag in record.tags),
    )


class EvidenceRepository(SqliteRepository[Evidence]):
    def __init__(self, database: Database) -> None:
        super().__init__(
            database,
            _Codec(
                "evidence",
                (
                    "id",
                    "tenant_id",
                    "source_type",
                    "source_ref",
                    "claim",
                    "project_id",
                    "metric",
                    "artifact_sha256",
                    "verified_by",
                    "confidence",
                    "captured_at",
                    "last_seen",
                ),
                _evidence_encode,
                _evidence_decode,
                "captured_at, id",
                mutable=False,
                read_table="evidence_records",
                insert_related=_insert_evidence_tags,
            ),
        )
