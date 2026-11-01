from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import pytest

from sigmahelix.core.models import TaskSeries, TaskStatus
from sigmahelix.core.recurrence import RecurrenceFrequency, RecurrenceRule
from sigmahelix.core.storage import (
    AuditLog,
    Database,
    EventBus,
    OccurrenceService,
    TaskRepository,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
START = date(2026, 11, 2)


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "occurrences" / "sigmahelix.db")
    db.initialize()
    return db


def _series(count=4, active=True):
    return TaskSeries(
        title="Review weekly plan",
        description="Recurring plan review",
        rule=RecurrenceRule(
            RecurrenceFrequency.DAILY,
            START,
            count=count,
        ),
        created_at=NOW,
        active=active,
    )


def test_completing_one_occurrence_keeps_series_active_and_materializes_next(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=3))
    first_batch = service.materialize(series.id, START)
    assert len(first_batch) == 1
    completed = service.complete_occurrence(series.id, START)
    assert completed.status == TaskStatus.DONE
    assert service.get_series(series.id).active

    second_batch = service.materialize(series.id, date(2026, 11, 3))

    assert len(second_batch) == 1
    assert second_batch[0].status == TaskStatus.TODO
    assert service.get_series(series.id).active
    assert [item.task.status for item in service.list_occurrences(series.id)] == [
        TaskStatus.DONE,
        TaskStatus.TODO,
    ]
    assert AuditLog(database).verify().entries_checked == 3
    assert [item.event.event_type for item in EventBus(database).replay()] == [
        "task.occurrence.materialized",
        "task.occurrence.completed",
        "task.occurrence.materialized",
    ]


def test_materialization_is_idempotent_and_count_limits_the_series(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=2))

    first = service.materialize(series.id, date(2026, 11, 10))
    repeated = service.materialize(series.id, date(2026, 11, 10))

    assert len(first) == 2
    assert repeated == []
    assert len(TaskRepository(database).list_all()) == 2
    assert len(service.list_occurrences(series.id)) == 2


def test_full_batches_resume_from_last_occurrence_without_dropping_dates(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=5))

    first = service.materialize(series.id, date(2026, 11, 6), limit=2)
    second = service.materialize(series.id, date(2026, 11, 6), limit=2)
    third = service.materialize(series.id, date(2026, 11, 6), limit=2)

    assert [task.due_at.date() for task in first + second + third] == [
        date(2026, 11, day) for day in range(2, 7)
    ]
    assert service.materialize(series.id, date(2026, 11, 6), limit=2) == []


def test_concurrent_materializers_create_each_occurrence_once(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=3))

    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = list(
            pool.map(
                lambda _: service.materialize(series.id, date(2026, 11, 4)),
                range(8),
            )
        )

    assert sum(map(len, batches)) == 3
    assert len(service.list_occurrences(series.id)) == 3
    assert AuditLog(database).verify().entries_checked == 3


def test_paused_series_does_not_materialize_and_existing_tasks_remain(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=3))
    first = service.materialize(series.id, START)
    service.set_active(series.id, False)

    assert service.materialize(series.id, date(2026, 11, 4)) == []
    assert service.get_series(series.id).active is False
    assert TaskRepository(database).get(first[0].id).status == TaskStatus.TODO


def test_completion_is_idempotent_and_unknown_occurrences_are_rejected(database):
    service = OccurrenceService(database, clock=lambda: NOW)
    series = service.create_series(_series(count=1))
    materialized = service.materialize(series.id, START)[0]

    first = service.complete_occurrence(series.id, START)
    second = service.complete_occurrence(series.id, START)
    assert first == second
    assert AuditLog(database).verify().entries_checked == 2

    with pytest.raises(KeyError, match="occurrence was not found"):
        service.complete_occurrence(series.id, date(2026, 11, 3))
    with pytest.raises(KeyError, match="series was not found"):
        service.materialize(materialized.id, date(2026, 11, 3))
