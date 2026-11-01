from datetime import UTC, datetime

import pytest

from sigmahelix.core.storage import (
    Database,
    NotificationError,
    NotificationService,
)


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_notification_uses_native_delivery_and_keeps_in_app_copy(tmp_path):
    database = Database((tmp_path / "notifications.db").resolve())
    database.initialize()
    sent = []
    service = NotificationService(
        database,
        clock=lambda: NOW,
        native_sender=lambda title, body: sent.append((title, body)) or True,
    )

    item = service.deliver("Task due", "Review the release", dedupe_key="task-42")

    assert item.native_status == "delivered"
    assert sent == [("Task due", "Review the release")]
    assert service.list_inbox(unread_only=True) == [item]
    assert service.mark_read(item.id) is True
    assert service.mark_read(item.id) is False
    assert service.list_inbox(unread_only=True) == []
    assert service.list_inbox()[0].read_at == NOW


@pytest.mark.parametrize(
    ("sender_result", "expected_status"),
    [(None, "unavailable"), (False, "failed")],
)
def test_in_app_fallback_persists_when_native_delivery_fails(
    tmp_path, sender_result, expected_status
):
    database = Database((tmp_path / "fallback.db").resolve())
    database.initialize()
    service = NotificationService(
        database, clock=lambda: NOW, native_sender=lambda title, body: sender_result
    )

    item = service.deliver("Reminder", "The inbox remains available")

    assert item.native_status == expected_status
    assert service.list_inbox() == [item]


def test_notification_deduplication_does_not_repeat_native_delivery(tmp_path):
    database = Database((tmp_path / "dedupe.db").resolve())
    database.initialize()
    calls = []
    service = NotificationService(
        database,
        clock=lambda: NOW,
        native_sender=lambda title, body: calls.append((title, body)) or True,
    )

    first = service.deliver("Task", "Due", dedupe_key="task-slot-1")
    second = service.deliver("Task", "Due", dedupe_key="task-slot-1")

    assert first == second
    assert len(service.list_inbox()) == 1
    assert calls == [("Task", "Due")]


def test_notifications_reject_secret_like_text_and_tenant_reads_are_scoped(tmp_path):
    database = Database((tmp_path / "privacy.db").resolve())
    database.initialize()
    service = NotificationService(database, native_sender=None)

    with pytest.raises(NotificationError, match="secret fields"):
        service.deliver("Access token", "value")
    item = service.deliver("Task", "Private tenant", tenant_id="tenant-a")
    assert service.list_inbox("tenant-b") == []
    assert service.mark_read(item.id, "tenant-b") is False
