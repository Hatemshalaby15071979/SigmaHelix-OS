"""Snooze, dismiss, and reschedule transitions for inbox alarms."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .audit import AuditLog
from .database import Database
from .notifications import NotificationService
from .scheduler import Scheduler

_DELIVERY_JOB = "notification.alarm.deliver"


class AlarmError(RuntimeError):
    """Raised when an alarm state transition is invalid."""


@dataclass(frozen=True, slots=True)
class AlarmState:
    """Current action state for one inbox notification."""

    notification_id: UUID
    tenant_id: str
    state: str
    due_at: datetime | None
    scheduled_job_id: UUID | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AlarmAction:
    """Immutable history of one snooze, dismiss, or reschedule action."""

    id: UUID
    notification_id: UUID
    tenant_id: str
    action: str
    from_state: str
    to_state: str
    due_at: datetime | None
    created_at: datetime


def _aware(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{label} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _state_from_row(row: sqlite3.Row) -> AlarmState:
    return AlarmState(
        UUID(row["notification_id"]),
        row["tenant_id"],
        row["state"],
        datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
        UUID(row["scheduled_job_id"]) if row["scheduled_job_id"] else None,
        datetime.fromisoformat(row["updated_at"]),
    )


class AlarmService:
    """Manage durable alarm state and schedule future notification delivery."""

    def __init__(
        self,
        database: Database,
        scheduler: Scheduler,
        notifications: NotificationService,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if scheduler.database.path.resolve() != database.path.resolve():
            raise ValueError("scheduler and alarm service must share a database")
        self.database = database
        self.scheduler = scheduler
        self.notifications = notifications
        self._clock = clock or (lambda: datetime.now(UTC))
        self._audit = AuditLog(database)
        self.scheduler.register_handler(_DELIVERY_JOB, self._deliver_scheduled)

    def get_state(
        self, notification_id: UUID, tenant_id: str = "local"
    ) -> AlarmState | None:
        if not isinstance(notification_id, UUID):
            raise ValueError("notification_id must be a UUID")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM notification_alarm_states "
                "WHERE notification_id = ? AND tenant_id = ?",
                (str(notification_id), tenant_id),
            ).fetchone()
        return _state_from_row(row) if row is not None else None

    def snooze(
        self,
        notification_id: UUID,
        until: datetime,
        tenant_id: str = "local",
    ) -> AlarmState:
        return self._transition(notification_id, "snooze", until, tenant_id)

    def reschedule(
        self,
        notification_id: UUID,
        until: datetime,
        tenant_id: str = "local",
    ) -> AlarmState:
        return self._transition(notification_id, "reschedule", until, tenant_id)

    def dismiss(self, notification_id: UUID, tenant_id: str = "local") -> AlarmState:
        return self._transition(notification_id, "dismiss", None, tenant_id)

    def _transition(
        self,
        notification_id: UUID,
        action: str,
        due_at: datetime | None,
        tenant_id: str,
    ) -> AlarmState:
        if not isinstance(notification_id, UUID):
            raise ValueError("notification_id must be a UUID")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        now = _aware(self._clock(), "clock")
        scheduled_at = _aware(due_at, "until") if due_at is not None else None
        if action != "dismiss" and scheduled_at is None:
            raise ValueError("snooze and reschedule require a due time")
        if scheduled_at is not None and scheduled_at <= now:
            raise ValueError("snooze and reschedule time must be in the future")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT s.*, n.title, n.body FROM notification_alarm_states s "
                "JOIN notifications n ON n.id = s.notification_id AND n.tenant_id = s.tenant_id "
                "WHERE s.notification_id = ? AND s.tenant_id = ?",
                (str(notification_id), tenant_id),
            ).fetchone()
            if row is None:
                raise AlarmError("notification alarm does not exist")
            previous = _state_from_row(row)
            if previous.state == "dismissed":
                raise AlarmError("dismissed alarms cannot transition")

            action_id = uuid4()
            next_state = "dismissed" if action == "dismiss" else f"{action}d"
            next_job_id: UUID | None = None
            if previous.scheduled_job_id is not None:
                connection.execute(
                    "UPDATE scheduled_jobs SET enabled = 0 WHERE id = ? AND tenant_id = ?",
                    (str(previous.scheduled_job_id), tenant_id),
                )
            if scheduled_at is not None:
                next_job_id = uuid4()
                payload: Mapping[str, Any] = {
                    "notification_id": str(notification_id),
                    "tenant_id": tenant_id,
                    "title": row["title"],
                    "body": row["body"],
                    "dedupe_key": f"alarm:{notification_id}:{action_id}",
                }
                connection.execute(
                    "INSERT INTO scheduled_jobs "
                    "(id, tenant_id, job_type, payload_json, next_run_at, interval_seconds, enabled, created_at, last_run_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL, 1, ?, NULL)",
                    (
                        str(next_job_id),
                        tenant_id,
                        _DELIVERY_JOB,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        scheduled_at.isoformat(),
                        now.isoformat(),
                    ),
                )
            connection.execute(
                "UPDATE notification_alarm_states SET state = ?, due_at = ?, "
                "scheduled_job_id = ?, updated_at = ? "
                "WHERE notification_id = ? AND tenant_id = ?",
                (
                    next_state,
                    scheduled_at.isoformat() if scheduled_at else None,
                    str(next_job_id) if next_job_id else None,
                    now.isoformat(),
                    str(notification_id),
                    tenant_id,
                ),
            )
            connection.execute(
                "INSERT INTO notification_actions "
                "(id, tenant_id, notification_id, action, from_state, to_state, due_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(action_id),
                    tenant_id,
                    str(notification_id),
                    action,
                    previous.state,
                    next_state,
                    scheduled_at.isoformat() if scheduled_at else None,
                    now.isoformat(),
                ),
            )
            event_type = f"notification.alarm.{action}"
            payload = {
                "notification_id": str(notification_id),
                "action_id": str(action_id),
                "state": next_state,
                "due_at": scheduled_at.isoformat() if scheduled_at else "",
            }
            connection.execute(
                "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(uuid5(NAMESPACE_URL, f"sigmahelix:{event_type}:{action_id}")),
                    tenant_id,
                    event_type,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    now.isoformat(),
                ),
            )
            self._audit.append_in_transaction(
                connection,
                event_type,
                "notification",
                str(notification_id),
                payload,
                tenant_id=tenant_id,
                occurred_at=now,
            )
            updated = connection.execute(
                "SELECT * FROM notification_alarm_states "
                "WHERE notification_id = ? AND tenant_id = ?",
                (str(notification_id), tenant_id),
            ).fetchone()
        return _state_from_row(updated)

    def list_actions(
        self, notification_id: UUID, tenant_id: str = "local"
    ) -> list[AlarmAction]:
        if not isinstance(notification_id, UUID):
            raise ValueError("notification_id must be a UUID")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM notification_actions WHERE notification_id = ? "
                "AND tenant_id = ? ORDER BY rowid",
                (str(notification_id), tenant_id),
            ).fetchall()
        return [
            AlarmAction(
                UUID(row["id"]),
                UUID(row["notification_id"]),
                row["tenant_id"],
                row["action"],
                row["from_state"],
                row["to_state"],
                datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def _deliver_scheduled(self, payload: Mapping[str, Any]) -> None:
        """Create a new inbox item for a snoozed or rescheduled alarm."""
        try:
            self.notifications.deliver(
                str(payload["title"]),
                str(payload["body"]),
                tenant_id=str(payload["tenant_id"]),
                dedupe_key=str(payload["dedupe_key"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AlarmError("scheduled notification payload is invalid") from exc
