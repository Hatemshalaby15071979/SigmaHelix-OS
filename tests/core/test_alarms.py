from datetime import UTC, datetime, timedelta

import pytest

from sigmahelix.core.storage import (
    AlarmError,
    AlarmService,
    AuditLog,
    Database,
    NotificationService,
    Scheduler,
)


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now


def test_snooze_reschedule_dismiss_state_machine_and_due_delivery(tmp_path):
    database = Database((tmp_path / "alarms.db").resolve())
    database.initialize()
    clock = FakeClock()
    scheduler = Scheduler(database, clock)
    notifications = NotificationService(database, clock, native_sender=None)
    alarms = AlarmService(database, scheduler, notifications, clock)
    item = notifications.deliver("Review", "Check the release", dedupe_key="original")

    snoozed_at = NOW + timedelta(minutes=10)
    snoozed = alarms.snooze(item.id, snoozed_at)
    assert snoozed.state == "snoozed"
    assert snoozed.due_at == snoozed_at
    assert scheduler.run_due() == []

    clock.now = snoozed_at
    first_delivery = scheduler.run_due()
    assert len(first_delivery) == 1
    assert first_delivery[0].status == "succeeded"
    assert len(notifications.list_inbox()) == 2
    assert alarms.get_state(item.id).state == "snoozed"

    rescheduled_at = snoozed_at + timedelta(minutes=20)
    rescheduled = alarms.reschedule(item.id, rescheduled_at)
    assert rescheduled.state == "rescheduled"
    assert rescheduled.due_at == rescheduled_at
    assert scheduler.get_job(snoozed.scheduled_job_id).enabled is False

    dismissed = alarms.dismiss(item.id)
    assert dismissed.state == "dismissed"
    assert dismissed.due_at is None
    assert dismissed.scheduled_job_id is None
    assert scheduler.get_job(rescheduled.scheduled_job_id).enabled is False
    assert len(alarms.list_actions(item.id)) == 3
    assert [action.action for action in alarms.list_actions(item.id)] == [
        "snooze",
        "reschedule",
        "dismiss",
    ]

    clock.now = rescheduled_at + timedelta(minutes=1)
    assert scheduler.run_due() == []
    with pytest.raises(AlarmError, match="dismissed alarms"):
        alarms.snooze(item.id, clock.now + timedelta(minutes=1))
    assert AuditLog(database).verify().valid


def test_alarm_actions_require_future_times_and_respect_tenant_scope(tmp_path):
    database = Database((tmp_path / "alarm-scope.db").resolve())
    database.initialize()
    clock = FakeClock()
    scheduler = Scheduler(database, clock)
    notifications = NotificationService(database, clock, native_sender=None)
    alarms = AlarmService(database, scheduler, notifications, clock)
    item = notifications.deliver("Task", "Tenant scoped", tenant_id="tenant-a")

    assert alarms.get_state(item.id, "tenant-b") is None
    with pytest.raises(AlarmError, match="does not exist"):
        alarms.dismiss(item.id, "tenant-b")
    with pytest.raises(ValueError, match="future"):
        alarms.snooze(item.id, NOW)
