"""Synchronous persistent publish/subscribe and cursor-based event replay."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from ..logging import redact_text
from ..models import Event
from .database import Database
from .repositories import EventRepository

EventCallback = Callable[["EventEnvelope"], None]
_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|private.?key|api.?key|access.?key|authorization",
    re.IGNORECASE,
)


def _contains_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            not isinstance(key, str)
            or _SENSITIVE_KEY.search(key) is not None
            or _contains_secret(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(child) for child in value)
    return isinstance(value, str) and redact_text(value) != value


class EventBusError(RuntimeError):
    """Raised when event dispatch fails after a durable publish."""


class EventDispatchError(EventBusError):
    """Reports subscriber failures after the event has already been persisted."""

    def __init__(self, envelope: EventEnvelope, failures: tuple[Exception, ...]):
        self.envelope = envelope
        self.failures = failures
        super().__init__(
            f"event {envelope.sequence} persisted, but {len(failures)} subscriber(s) failed"
        )


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """A persisted event paired with its stable per-database sequence cursor."""

    sequence: int
    event: Event


@dataclass(frozen=True, slots=True)
class _Subscription:
    tenant_id: str
    event_type: str | None
    callback: EventCallback


class EventBus:
    """Persist events before delivering them to matching in-process subscribers."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._events = EventRepository(database)
        self._lock = RLock()
        self._subscriptions: dict[UUID, _Subscription] = {}

    def subscribe(
        self,
        callback: EventCallback,
        tenant_id: str = "local",
        event_type: str | None = None,
    ) -> UUID:
        """Register a callback filtered by tenant and optionally by event type."""
        if not callable(callback):
            raise ValueError("callback must be callable")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if event_type is not None and (
            not isinstance(event_type, str) or not event_type.strip()
        ):
            raise ValueError("event_type must be a non-empty string or None")
        token = uuid4()
        with self._lock:
            self._subscriptions[token] = _Subscription(tenant_id, event_type, callback)
        return token

    def unsubscribe(self, token: UUID) -> bool:
        """Remove a subscription; return false if it was already removed."""
        if not isinstance(token, UUID):
            raise ValueError("subscription token must be a UUID")
        with self._lock:
            return self._subscriptions.pop(token, None) is not None

    def publish(self, event: Event) -> EventEnvelope:
        """Persist first, dispatch to matching subscribers, then return its cursor.

        If callbacks fail, the event remains durable and `EventDispatchError`
        carries the envelope for later replay. Callers should not publish it again.
        """
        if not isinstance(event, Event):
            raise ValueError("event must be an Event")
        if _contains_secret(event.payload):
            raise ValueError("event payload must not contain secret-like data")
        self._events.create(event)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT sequence FROM event_stream WHERE event_id = ? AND tenant_id = ?",
                (str(event.id), event.tenant_id),
            ).fetchone()
        if row is None:
            raise EventBusError("persisted event has no event stream sequence")
        envelope = EventEnvelope(int(row["sequence"]), event)
        with self._lock:
            subscribers = tuple(self._subscriptions.values())
        failures: list[Exception] = []
        for subscription in subscribers:
            if subscription.tenant_id != event.tenant_id:
                continue
            if subscription.event_type not in (None, event.event_type):
                continue
            try:
                subscription.callback(envelope)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise EventDispatchError(envelope, tuple(failures))
        return envelope

    def replay(
        self,
        after_sequence: int = 0,
        tenant_id: str = "local",
        event_type: str | None = None,
        limit: int = 1000,
    ) -> list[EventEnvelope]:
        """Return matching persisted events after a sequence cursor, oldest first."""
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int):
            raise ValueError("after_sequence must be an integer")
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if event_type is not None and (
            not isinstance(event_type, str) or not event_type.strip()
        ):
            raise ValueError("event_type must be a non-empty string or None")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        sql = (
            "SELECT s.sequence, e.id, e.tenant_id, e.event_type, e.payload_json, e.occurred_at "
            "FROM event_stream AS s JOIN events AS e "
            "ON e.id = s.event_id AND e.tenant_id = s.tenant_id "
            "WHERE s.tenant_id = ? AND s.sequence > ?"
        )
        parameters: list[object] = [tenant_id, after_sequence]
        if event_type is not None:
            sql += " AND e.event_type = ?"
            parameters.append(event_type)
        sql += " ORDER BY s.sequence LIMIT ?"
        parameters.append(limit)
        with self.database.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [
            EventEnvelope(
                int(row["sequence"]),
                Event(
                    event_type=row["event_type"],
                    payload=json.loads(row["payload_json"]),
                    id=UUID(row["id"]),
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                    tenant_id=row["tenant_id"],
                ),
            )
            for row in rows
        ]
