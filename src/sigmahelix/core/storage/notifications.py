"""Durable in-app notifications with an optional Linux desktop adapter."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from ..logging import redact_text
from .database import Database

NativeSender = Callable[[str, str], bool | None]
_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|private.?key|api.?key|access.?key|authorization",
    re.IGNORECASE,
)


class NotificationError(RuntimeError):
    """Raised when notification data cannot be stored safely."""


@dataclass(frozen=True, slots=True)
class Notification:
    """One durable inbox item and its optional desktop delivery result."""

    id: UUID
    tenant_id: str
    dedupe_key: str
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None
    native_status: str


def _send_notify_send(title: str, body: str) -> bool | None:
    executable = shutil.which("notify-send")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--", title, body],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _row_to_notification(row) -> Notification:
    return Notification(
        UUID(row["id"]),
        row["tenant_id"],
        row["dedupe_key"],
        row["title"],
        row["body"],
        datetime.fromisoformat(row["created_at"]),
        datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
        row["native_status"],
    )


class NotificationService:
    """Persist every notification first, then try an optional desktop alert."""

    def __init__(
        self,
        database: Database,
        clock: Callable[[], datetime] | None = None,
        native_sender: NativeSender | None = _send_notify_send,
    ) -> None:
        self.database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._native_sender = native_sender

    def deliver(
        self,
        title: str,
        body: str,
        tenant_id: str = "local",
        dedupe_key: str | None = None,
    ) -> Notification:
        """Store an inbox item and attempt native delivery at most once."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title must be a non-empty string")
        if not isinstance(body, str):
            raise ValueError("body must be a string")
        if _SENSITIVE_KEY.search(title) or _SENSITIVE_KEY.search(body):
            raise NotificationError("notification text must not contain secret fields")
        if redact_text(title) != title or redact_text(body) != body:
            raise NotificationError(
                "notification text must not contain secret-like values"
            )
        key = dedupe_key or str(uuid4())
        if not isinstance(key, str) or not key.strip():
            raise ValueError("dedupe_key must be a non-empty string")
        now = self._clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(UTC)
        identifier = uuid4()
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO notifications "
                "(id, tenant_id, dedupe_key, title, body, created_at, read_at, native_status) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, 'pending')",
                (
                    str(identifier),
                    tenant_id,
                    key,
                    title.strip(),
                    body,
                    now.isoformat(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM notifications WHERE tenant_id = ? AND dedupe_key = ?",
                (tenant_id, key),
            ).fetchone()
        if row is None:
            raise NotificationError("notification was not persisted")
        if cursor.rowcount != 1:
            return _row_to_notification(row)

        status = "unavailable"
        if self._native_sender is not None:
            try:
                sent = self._native_sender(title.strip(), body)
                status = (
                    "delivered"
                    if sent is True
                    else "unavailable"
                    if sent is None
                    else "failed"
                )
            except Exception:
                status = "failed"
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE notifications SET native_status = ? WHERE id = ? AND tenant_id = ?",
                (status, str(identifier), tenant_id),
            )
            final_row = connection.execute(
                "SELECT * FROM notifications WHERE id = ? AND tenant_id = ?",
                (str(identifier), tenant_id),
            ).fetchone()
        return _row_to_notification(final_row)

    def list_inbox(
        self, tenant_id: str = "local", unread_only: bool = False
    ) -> list[Notification]:
        """Return inbox items, newest first, with optional unread filtering."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        query = "SELECT * FROM notifications WHERE tenant_id = ?"
        parameters: tuple[str, ...] = (tenant_id,)
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC, id"
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_notification(row) for row in rows]

    def mark_read(self, notification_id: UUID, tenant_id: str = "local") -> bool:
        """Mark one inbox item read while retaining its delivery history."""
        if not isinstance(notification_id, UUID):
            raise ValueError("notification_id must be a UUID")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        now = self._clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise ValueError("clock must return a timezone-aware datetime")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE notifications SET read_at = ? "
                "WHERE id = ? AND tenant_id = ? AND read_at IS NULL",
                (now.astimezone(UTC).isoformat(), str(notification_id), tenant_id),
            )
        return cursor.rowcount == 1
