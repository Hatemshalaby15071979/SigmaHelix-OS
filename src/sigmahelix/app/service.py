"""Application service: the single doorway from the UI to the durable core.

The desktop app and the console never touch SQLite directly. They call this
facade, which validates input, writes through the core repositories inside a
transaction, and appends one audit record per mutation.

Records are handed to the presentation layer as plain dictionaries keyed by a
small, stable integer ``id`` (the record's ``display_id``), because that is the
number the user sees and types ("complete task 3").
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from uuid import UUID

from ..core.config import load_settings
from ..core.models import Note, QuestionStatus, Task, TaskQuestion, TaskStatus
from ..core.storage import (
    AuditLog,
    Database,
    NoteRepository,
    TaskQuestionRepository,
    TaskRepository,
)
from ..core.storage.repositories import RepositoryOperationError

DEFAULT_TENANT = "local"

#: Tables the facade may address by display id. A closed set keeps the table
#: name out of any SQL string that could be influenced from outside.
_TABLES = frozenset({"tasks", "notes"})


def _day(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d")


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def task_to_dict(task: Task) -> dict[str, Any]:
    """Project a domain task onto the shape the UI and console expect."""
    return {
        "id": task.display_id,
        "name": task.title,
        "frequency": task.recurrence,
        "created": _day(task.created_at),
        "completed": task.status is TaskStatus.DONE,
        "pinned": task.pinned,
        "due": _day(task.due_at) if task.due_at is not None else None,
    }


def note_to_dict(note: Note) -> dict[str, Any]:
    """Project a domain note onto the shape the UI and console expect."""
    return {
        "id": note.display_id,
        "content": note.content,
        "created": _day(note.created_at),
        "updated": _stamp(note.updated_at),
        "pinned": note.pinned,
    }


def _readiness_of(questions: list[TaskQuestion]) -> dict[str, Any]:
    """How close a task is to being answerable: the completion checkpoint."""
    total = len(questions)
    answered = sum(1 for q in questions if q.status is QuestionStatus.ANSWERED)
    blocked = sum(1 for q in questions if q.status is QuestionStatus.BLOCKED)
    return {
        "questions_total": total,
        "questions_answered": answered,
        "questions_open": total - answered,
        "questions_blocked": blocked,
        "ready": total == answered,
        "readiness": 100 if total == 0 else round(answered * 100 / total),
    }


def question_to_dict(question: TaskQuestion) -> dict[str, Any]:
    """Project a task question onto the shape the UI expects."""
    return {
        "id": question.display_id,
        "question": question.question,
        "answer": question.answer,
        "evidence": question.evidence,
        "status": question.status.value,
        "answered": question.status is QuestionStatus.ANSWERED,
        "answered_at": _stamp(question.answered_at) if question.answered_at else None,
    }


class AppService:
    """Read and write user data through the durable core."""

    def __init__(
        self, database: Database | None = None, tenant_id: str = DEFAULT_TENANT
    ) -> None:
        self.database = database or Database(load_settings().database_path)
        self.database.initialize()
        self.tenant_id = tenant_id
        self._tasks = TaskRepository(self.database)
        self._notes = NoteRepository(self.database)
        self._questions = TaskQuestionRepository(self.database)
        self._audit = AuditLog(self.database)
        # Bring across anything the pre-merge JSON stores left behind. This is
        # idempotent: an already-imported snapshot is a no-op.
        self.import_legacy_json()

    # ---- shared helpers ---------------------------------------------------
    def _record_id(self, table: str, display_id: int) -> UUID | None:
        if table not in _TABLES:
            raise ValueError(f"unsupported table {table!r}")
        with self.database.connection() as connection:
            row = connection.execute(
                f"SELECT id FROM {table} WHERE tenant_id = ? AND display_id = ? "
                "AND deleted_at IS NULL",
                (self.tenant_id, display_id),
            ).fetchone()
        return UUID(row["id"]) if row is not None else None

    def _audit_write(
        self, action: str, entity: str, entity_id: str, payload: dict[str, Any]
    ) -> None:
        self._audit.append(action, entity, entity_id, payload, tenant_id=self.tenant_id)

    # ---- tasks ------------------------------------------------------------
    def _readiness(self, task_id: UUID) -> dict[str, Any]:
        return _readiness_of(self._questions.list_for_task(task_id, self.tenant_id))

    def list_tasks(self) -> list[dict[str, Any]]:
        by_task: dict[UUID, list[TaskQuestion]] = {}
        for question in self._questions.list_all(self.tenant_id):
            by_task.setdefault(question.task_id, []).append(question)
        rows = []
        for task in self._tasks.list_all(self.tenant_id):
            questions = by_task.get(task.id, [])
            record = task_to_dict(task)
            record.update(_readiness_of(questions))
            record["questions"] = [question_to_dict(q) for q in questions]
            rows.append(record)
        return rows

    def get_task(self, display_id: int) -> dict[str, Any] | None:
        record_id = self._record_id("tasks", display_id)
        if record_id is None:
            return None
        task = self._tasks.get(record_id, self.tenant_id)
        if task is None:
            return None
        questions = self._questions.list_for_task(task.id, self.tenant_id)
        record = task_to_dict(task)
        record.update(_readiness_of(questions))
        record["questions"] = [question_to_dict(q) for q in questions]
        return record

    def tasks_due_between(self, start: date, end: date) -> list[dict[str, Any]]:
        """Tasks due on or after ``start`` and before ``end``, by due time."""
        first = datetime.combine(start, time.min, UTC)
        last = datetime.combine(end, time.min, UTC)
        due = [
            task
            for task in self._tasks.list_all(self.tenant_id)
            if task.due_at is not None and first <= task.due_at < last
        ]
        due.sort(key=lambda task: (task.due_at or first, task.display_id))
        return [task_to_dict(task) for task in due]

    def create_task(
        self,
        title: str,
        recurrence: str = "none",
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        task = self._tasks.create(
            Task(
                title=title,
                recurrence=recurrence,
                due_at=due_at,
                tenant_id=self.tenant_id,
            )
        )
        self._audit_write(
            "task.created",
            "task",
            str(task.id),
            {"display_id": task.display_id, "recurrence": task.recurrence},
        )
        record = task_to_dict(task)
        record.update(self._readiness(task.id))
        return record

    def create_task_with_questions(
        self,
        title: str,
        questions: list[str],
        recurrence: str = "none",
        due_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a task and its questions in one go — the approval step.

        The user approves a proposed question set, and only then does the task
        exist. A question that is empty after trimming is dropped, not stored.
        """
        record = self.create_task(title, recurrence=recurrence, due_at=due_at)
        task_id = self._record_id("tasks", record["id"])
        if task_id is None:
            return record
        for text in questions:
            cleaned = " ".join(str(text or "").split())
            if cleaned:
                self.add_question(record["id"], cleaned)
        return self.get_task(record["id"]) or record

    def set_task_done(
        self, display_id: int, done: bool = True, force: bool = False
    ) -> dict[str, Any] | None:
        record_id = self._record_id("tasks", display_id)
        if record_id is None:
            return None
        task = self._tasks.get(record_id, self.tenant_id)
        if task is None:
            return None
        if done and not force:
            readiness = self._readiness(task.id)
            if not readiness["ready"]:
                raise RepositoryOperationError(
                    f"task {display_id} still has {readiness['questions_open']} "
                    "unanswered question(s); answer them or force the completion"
                )
        updated = replace(
            task,
            status=TaskStatus.DONE if done else TaskStatus.TODO,
            updated_at=datetime.now(UTC),
        )
        self._tasks.update(updated)
        self._audit_write(
            "task.completed" if done else "task.reopened",
            "task",
            str(task.id),
            {"display_id": task.display_id},
        )
        return task_to_dict(updated)

    def set_task_pinned(
        self, display_id: int, pinned: bool = True
    ) -> dict[str, Any] | None:
        record_id = self._record_id("tasks", display_id)
        if record_id is None:
            return None
        task = self._tasks.get(record_id, self.tenant_id)
        if task is None:
            return None
        updated = replace(task, pinned=pinned, updated_at=datetime.now(UTC))
        self._tasks.update(updated)
        self._audit_write(
            "task.pinned" if pinned else "task.unpinned",
            "task",
            str(task.id),
            {"display_id": task.display_id},
        )
        return task_to_dict(updated)

    def delete_task(self, display_id: int, force: bool = False) -> bool:
        record_id = self._record_id("tasks", display_id)
        if record_id is None:
            return False
        task = self._tasks.get(record_id, self.tenant_id)
        if task is None:
            return False
        if task.pinned and not force:
            return False
        deleted = self._tasks.delete(record_id, self.tenant_id)
        if deleted:
            self._questions.delete_for_task(record_id, self.tenant_id)
            self._audit_write(
                "task.deleted", "task", str(record_id), {"display_id": display_id}
            )
        return deleted

    # ---- task questions ---------------------------------------------------
    def questions_for(self, display_id: int) -> list[dict[str, Any]]:
        task_id = self._record_id("tasks", display_id)
        if task_id is None:
            return []
        return [
            question_to_dict(q)
            for q in self._questions.list_for_task(task_id, self.tenant_id)
        ]

    def add_question(self, display_id: int, question: str) -> dict[str, Any] | None:
        task_id = self._record_id("tasks", display_id)
        if task_id is None:
            return None
        record = self._questions.create(
            TaskQuestion(
                question=question,
                task_id=task_id,
                tenant_id=self.tenant_id,
            )
        )
        self._audit_write(
            "question.added",
            "task",
            str(task_id),
            {"display_id": display_id, "question_id": record.display_id},
        )
        return question_to_dict(record)

    def answer_question(
        self,
        display_id: int,
        question_id: int,
        answer: str,
        evidence: str = "",
    ) -> dict[str, Any] | None:
        """Record the answer to one question. This is the checkpoint."""
        task_id = self._record_id("tasks", display_id)
        if task_id is None:
            return None
        target = next(
            (
                q
                for q in self._questions.list_for_task(task_id, self.tenant_id)
                if q.display_id == question_id
            ),
            None,
        )
        if target is None:
            return None
        cleaned = answer.strip()
        if not cleaned:
            raise ValueError("an answer cannot be empty")
        now = datetime.now(UTC)
        updated = replace(
            target,
            answer=cleaned,
            evidence=evidence.strip(),
            status=QuestionStatus.ANSWERED,
            answered_at=now,
            updated_at=now,
        )
        self._questions.update(updated)
        self._audit_write(
            "question.answered",
            "task",
            str(task_id),
            {"display_id": display_id, "question_id": question_id},
        )
        return question_to_dict(updated)

    def reopen_question(
        self, display_id: int, question_id: int
    ) -> dict[str, Any] | None:
        task_id = self._record_id("tasks", display_id)
        if task_id is None:
            return None
        target = next(
            (
                q
                for q in self._questions.list_for_task(task_id, self.tenant_id)
                if q.display_id == question_id
            ),
            None,
        )
        if target is None:
            return None
        updated = replace(
            target,
            status=QuestionStatus.OPEN,
            answered_at=None,
            updated_at=datetime.now(UTC),
        )
        self._questions.update(updated)
        self._audit_write(
            "question.reopened",
            "task",
            str(task_id),
            {"display_id": display_id, "question_id": question_id},
        )
        return question_to_dict(updated)

    # ---- notes ------------------------------------------------------------
    def list_notes(self) -> list[dict[str, Any]]:
        return [note_to_dict(note) for note in self._notes.list_all(self.tenant_id)]

    def get_note(self, display_id: int) -> dict[str, Any] | None:
        record_id = self._record_id("notes", display_id)
        if record_id is None:
            return None
        note = self._notes.get(record_id, self.tenant_id)
        return note_to_dict(note) if note is not None else None

    def create_note(self, content: str) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None
        note = self._notes.create(Note(content=text, tenant_id=self.tenant_id))
        self._audit_write(
            "note.created", "note", str(note.id), {"display_id": note.display_id}
        )
        return note_to_dict(note)

    def update_note(self, display_id: int, content: str) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None
        record_id = self._record_id("notes", display_id)
        if record_id is None:
            return None
        note = self._notes.get(record_id, self.tenant_id)
        if note is None:
            return None
        updated = replace(note, content=text, updated_at=datetime.now(UTC))
        self._notes.update(updated)
        self._audit_write(
            "note.updated", "note", str(note.id), {"display_id": note.display_id}
        )
        return note_to_dict(updated)

    def set_note_pinned(
        self, display_id: int, pinned: bool = True
    ) -> dict[str, Any] | None:
        record_id = self._record_id("notes", display_id)
        if record_id is None:
            return None
        note = self._notes.get(record_id, self.tenant_id)
        if note is None:
            return None
        updated = replace(note, pinned=pinned, updated_at=datetime.now(UTC))
        self._notes.update(updated)
        self._audit_write(
            "note.pinned" if pinned else "note.unpinned",
            "note",
            str(note.id),
            {"display_id": note.display_id},
        )
        return note_to_dict(updated)

    def delete_note(self, display_id: int, force: bool = False) -> bool:
        record_id = self._record_id("notes", display_id)
        if record_id is None:
            return False
        note = self._notes.get(record_id, self.tenant_id)
        if note is None:
            return False
        if note.pinned and not force:
            return False
        deleted = self._notes.delete(record_id, self.tenant_id)
        if deleted:
            self._audit_write(
                "note.deleted", "note", str(record_id), {"display_id": display_id}
            )
        return deleted

    # ---- projects ---------------------------------------------------------
    def scan_projects(self) -> list[dict[str, Any]]:
        """Scan every proven project directory: git state, manifests, health."""
        from ..core.storage import ProjectScanner
        from .projects import project_paths

        roots = project_paths()
        if not roots:
            return []
        batch = ProjectScanner(self.database).scan(roots)
        return [
            {
                "name": scan.name,
                "path": str(scan.root_path),
                "health": scan.health,
                "score": scan.health_score,
                "branch": scan.git_branch,
                "commit": scan.git_commit,
                "dirty": bool(scan.git_dirty),
                "changes": scan.git_change_count,
                "manifests": list(scan.manifests),
                "entrypoints": list(scan.entrypoints),
                "findings": list(scan.findings),
                "artifacts": len(scan.artifacts),
            }
            for scan in batch.scans
        ]

    # ---- maintenance ------------------------------------------------------
    def import_legacy_json(self, data_dir: Path | None = None) -> dict[str, int]:
        """Import pre-merge ``tasks.json`` / ``notes.json`` exactly once.

        Returns the number of tasks and notes that were newly imported. An
        already-imported snapshot is a no-op, so this is safe to call on every
        start.
        """
        from ..core.storage import LegacyImportError, LegacySessionImporter
        from .paths import legacy_json_dir

        source = data_dir or legacy_json_dir()
        tasks = _read_json_list(source / "tasks.json")
        notes = _read_json_list(source / "notes.json")
        if not tasks and not notes:
            return {"tasks": 0, "notes": 0}
        try:
            result = LegacySessionImporter(self.database).import_snapshot(
                _legacy_source_id(tasks, notes), tasks, notes, self.tenant_id
            )
        except LegacyImportError:
            return {"tasks": 0, "notes": 0}
        return {
            "tasks": result.task_count if result.imported else 0,
            "notes": result.note_count if result.imported else 0,
        }


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _legacy_source_id(tasks: list[dict[str, Any]], notes: list[dict[str, Any]]) -> UUID:
    """A stable identity for this exact legacy snapshot."""
    import hashlib
    import json
    from uuid import NAMESPACE_URL, uuid5

    payload = json.dumps(
        {"tasks": tasks, "notes": notes}, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return uuid5(NAMESPACE_URL, f"sigmahelix:legacy-json:{digest}")


__all__ = [
    "AppService",
    "DEFAULT_TENANT",
    "RepositoryOperationError",
    "note_to_dict",
    "task_to_dict",
]
