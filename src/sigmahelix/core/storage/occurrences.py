"""Transactional recurrence materialization into durable task occurrences."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from ..models import Task, TaskOccurrence, TaskSeries, TaskStatus
from ..recurrence import RecurrenceFrequency, RecurrenceRule, occurrences
from .audit import AuditLog
from .database import Database
from .repositories import TaskRepository


class OccurrenceError(RuntimeError):
    """Raised when a recurrence series cannot be safely materialized."""


Clock = Callable[[], datetime]


def _rule_to_json(rule: RecurrenceRule) -> str:
    return json.dumps(
        {
            "frequency": rule.frequency.value,
            "anchor": rule.anchor.isoformat(),
            "interval": rule.interval,
            "weekdays": list(rule.weekdays),
            "day_of_month": rule.day_of_month,
            "count": rule.count,
            "end_date": rule.end_date.isoformat() if rule.end_date else None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _rule_from_json(value: str) -> RecurrenceRule:
    document: dict[str, Any] = json.loads(value)
    return RecurrenceRule(
        frequency=RecurrenceFrequency(document["frequency"]),
        anchor=date.fromisoformat(document["anchor"]),
        interval=document["interval"],
        weekdays=tuple(document["weekdays"]),
        day_of_month=document["day_of_month"],
        count=document["count"],
        end_date=date.fromisoformat(document["end_date"])
        if document["end_date"]
        else None,
    )


def _series_from_row(row) -> TaskSeries:
    return TaskSeries(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        title=row["title"],
        description=row["description"],
        project_id=UUID(row["project_id"]) if row["project_id"] else None,
        rule=_rule_from_json(row["rule_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        active=bool(row["active"]),
        last_materialized_through=date.fromisoformat(row["last_materialized_through"])
        if row["last_materialized_through"]
        else None,
    )


class OccurrenceService:
    """Create recurring task series, materialize tasks, and complete one date."""

    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tasks = TaskRepository(database)
        self._audit = AuditLog(database)

    def create_series(self, series: TaskSeries) -> TaskSeries:
        """Persist one recurring definition without creating a template task."""
        if not isinstance(series, TaskSeries):
            raise ValueError("series must be a TaskSeries")
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO task_series (id, tenant_id, title, description, project_id, "
                "rule_json, created_at, active, last_materialized_through) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(series.id),
                    series.tenant_id,
                    series.title,
                    series.description,
                    str(series.project_id) if series.project_id else None,
                    _rule_to_json(series.rule),
                    series.created_at.isoformat(),
                    int(series.active),
                    series.last_materialized_through.isoformat()
                    if series.last_materialized_through
                    else None,
                ),
            )
        return series

    def get_series(
        self, series_id: UUID, tenant_id: str = "local"
    ) -> TaskSeries | None:
        """Return a tenant-scoped recurring definition, if it exists."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM task_series WHERE id = ? AND tenant_id = ?",
                (str(series_id), tenant_id),
            ).fetchone()
        return _series_from_row(row) if row is not None else None

    def set_active(
        self, series_id: UUID, active: bool, tenant_id: str = "local"
    ) -> TaskSeries:
        """Pause or resume future materialization without changing occurrences."""
        if not isinstance(active, bool):
            raise ValueError("active must be a boolean")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE task_series SET active = ? WHERE id = ? AND tenant_id = ?",
                (int(active), str(series_id), tenant_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("task series was not found")
        result = self.get_series(series_id, tenant_id)
        if result is None:
            raise KeyError("task series was not found")
        return result

    def materialize(
        self,
        series_id: UUID,
        through: date,
        tenant_id: str = "local",
        limit: int = 1000,
    ) -> list[Task]:
        """Create missing tasks up to a date, atomically with their receipts.

        A full batch advances only to its last generated date. Call again with the
        same `through` date to continue without dropping later occurrences.
        """
        if not isinstance(series_id, UUID):
            raise ValueError("series_id must be a UUID")
        if not isinstance(through, date) or isinstance(through, datetime):
            raise ValueError("through must be a date")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM task_series WHERE id = ? AND tenant_id = ?",
                (str(series_id), tenant_id),
            ).fetchone()
            if row is None:
                raise KeyError("task series was not found")
            series = _series_from_row(row)
            if not series.active:
                return []
            rule = series.rule
            previous_cursor = series.last_materialized_through
            generated = occurrences(
                rule,
                through,
                after=previous_cursor,
                limit=limit,
            )
            now = self._clock()
            if (
                not isinstance(now, datetime)
                or now.tzinfo is None
                or now.utcoffset() is None
            ):
                raise OccurrenceError("clock must return a timezone-aware datetime")
            now = now.astimezone(UTC)
            created: list[Task] = []
            for scheduled_for in generated:
                task_id = uuid5(
                    NAMESPACE_URL,
                    f"sigmahelix:series:{series.id}:occurrence:{scheduled_for.isoformat()}",
                )
                task = Task(
                    title=series.title,
                    id=task_id,
                    description=series.description,
                    status=TaskStatus.TODO,
                    project_id=series.project_id,
                    due_at=datetime.combine(scheduled_for, time.min, UTC),
                    created_at=now,
                    updated_at=now,
                    tenant_id=series.tenant_id,
                )
                occurrence_id = uuid5(
                    NAMESPACE_URL,
                    f"sigmahelix:series-occurrence:{series.id}:{scheduled_for.isoformat()}",
                )
                connection.execute(
                    "INSERT INTO tasks (id, tenant_id, title, description, status, project_id, "
                    "due_at, created_at, updated_at, deleted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        str(task.id),
                        task.tenant_id,
                        task.title,
                        task.description,
                        task.status.value,
                        str(task.project_id) if task.project_id else None,
                        task.due_at.isoformat() if task.due_at else None,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ),
                )
                connection.execute(
                    "INSERT INTO task_occurrences (id, tenant_id, series_id, task_id, "
                    "scheduled_for, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(occurrence_id),
                        series.tenant_id,
                        str(series.id),
                        str(task.id),
                        scheduled_for.isoformat(),
                        now.isoformat(),
                    ),
                )
                payload = {
                    "series_id": str(series.id),
                    "task_id": str(task.id),
                    "scheduled_for": scheduled_for.isoformat(),
                }
                self._append_event(
                    connection,
                    series.tenant_id,
                    "task.occurrence.materialized",
                    payload,
                    now,
                )
                self._audit.append_in_transaction(
                    connection,
                    "task.occurrence.materialized",
                    "task_occurrence",
                    str(occurrence_id),
                    payload,
                    tenant_id=series.tenant_id,
                    occurred_at=now,
                )
                created.append(task)

            if generated and len(generated) == limit:
                cursor = generated[-1]
            elif previous_cursor is None or through > previous_cursor:
                cursor = through
            else:
                cursor = previous_cursor
            connection.execute(
                "UPDATE task_series SET last_materialized_through = ? "
                "WHERE id = ? AND tenant_id = ?",
                (cursor.isoformat(), str(series.id), series.tenant_id),
            )
            return created

    def complete_occurrence(
        self,
        series_id: UUID,
        scheduled_for: date,
        tenant_id: str = "local",
    ) -> Task:
        """Complete one generated task while leaving its series active."""
        if not isinstance(scheduled_for, date) or isinstance(scheduled_for, datetime):
            raise ValueError("scheduled_for must be a date")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT o.task_id, t.status FROM task_occurrences AS o JOIN tasks AS t "
                "ON t.id = o.task_id AND t.tenant_id = o.tenant_id "
                "WHERE o.series_id = ? AND o.tenant_id = ? AND o.scheduled_for = ? "
                "AND t.deleted_at IS NULL",
                (str(series_id), tenant_id, scheduled_for.isoformat()),
            ).fetchone()
            if row is None:
                raise KeyError("task occurrence was not found")
            if row["status"] == TaskStatus.CANCELLED.value:
                raise OccurrenceError("cancelled occurrence cannot be completed")
            task_id = row["task_id"]
            if row["status"] != TaskStatus.DONE.value:
                now = self._clock()
                if (
                    not isinstance(now, datetime)
                    or now.tzinfo is None
                    or now.utcoffset() is None
                ):
                    raise OccurrenceError("clock must return a timezone-aware datetime")
                now = now.astimezone(UTC)
                connection.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                    (TaskStatus.DONE.value, now.isoformat(), task_id, tenant_id),
                )
                payload = {
                    "series_id": str(series_id),
                    "task_id": task_id,
                    "scheduled_for": scheduled_for.isoformat(),
                }
                self._append_event(
                    connection,
                    tenant_id,
                    "task.occurrence.completed",
                    payload,
                    now,
                )
                self._audit.append_in_transaction(
                    connection,
                    "task.occurrence.completed",
                    "task_occurrence",
                    f"{series_id}:{scheduled_for.isoformat()}",
                    payload,
                    tenant_id=tenant_id,
                    occurred_at=now,
                )
        task = self._tasks.get(UUID(task_id), tenant_id)
        if task is None:
            raise OccurrenceError("completed occurrence task disappeared")
        return task

    def list_occurrences(
        self, series_id: UUID, tenant_id: str = "local"
    ) -> list[TaskOccurrence]:
        """Return generated occurrences in calendar order."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT scheduled_for, task_id FROM task_occurrences "
                "WHERE series_id = ? AND tenant_id = ? ORDER BY scheduled_for",
                (str(series_id), tenant_id),
            ).fetchall()
        result: list[TaskOccurrence] = []
        for row in rows:
            task = self._tasks.get(UUID(row["task_id"]), tenant_id)
            if task is not None:
                result.append(
                    TaskOccurrence(
                        series_id,
                        date.fromisoformat(row["scheduled_for"]),
                        task,
                    )
                )
        return result

    @staticmethod
    def _append_event(
        connection,
        tenant_id: str,
        event_type: str,
        payload: dict[str, str],
        now: datetime,
    ) -> None:
        connection.execute(
            "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(
                    uuid5(
                        NAMESPACE_URL,
                        f"sigmahelix:{tenant_id}:{event_type}:{payload['series_id']}:{payload.get('scheduled_for')}:{payload.get('task_id')}",
                    )
                ),
                tenant_id,
                event_type,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                now.isoformat(),
            ),
        )
