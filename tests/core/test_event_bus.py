from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from sigmahelix.core.models import Event
from sigmahelix.core.storage import (
    Database,
    EventBus,
    EventDispatchError,
    EventRepository,
)


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "events" / "sigmahelix.db")
    db.initialize()
    return db


def test_publish_persists_then_notifies_matching_subscribers(database):
    bus = EventBus(database)
    received = []
    other_tenant = []
    bus.subscribe(received.append, event_type="task.created")
    bus.subscribe(other_tenant.append, tenant_id="tenant-b")
    event = Event("task.created", {"task_id": "task-1"})

    envelope = bus.publish(event)

    assert envelope.sequence == 1
    assert envelope.event == event
    assert received == [envelope]
    assert other_tenant == []
    with database.connection() as connection:
        row = connection.execute(
            "SELECT e.id, s.sequence FROM events e JOIN event_stream s "
            "ON s.event_id = e.id WHERE e.id = ?",
            (str(event.id),),
        ).fetchone()
    assert row["sequence"] == envelope.sequence


def test_replay_resumes_after_cursor_across_bus_instances(database):
    publisher = EventBus(database)
    events = [
        Event("task.created", {"number": 1}),
        Event("note.created", {"number": 2}),
        Event("task.updated", {"number": 3}),
        Event("task.completed", {"number": 4}),
    ]
    envelopes = [publisher.publish(event) for event in events]

    restarted = EventBus(database)
    replayed = restarted.replay(after_sequence=1, limit=2)
    assert [item.sequence for item in replayed] == [2, 3]
    assert [item.event for item in replayed] == events[1:3]
    tasks = restarted.replay(event_type="task.completed")
    assert [(item.sequence, item.event) for item in tasks] == [(4, events[3])]
    assert envelopes[-1].sequence == 4


def test_repository_insert_is_streamed_and_transaction_rollback_is_atomic(database):
    repository = EventRepository(database)
    event = Event("task.created", {"task_id": "direct"})
    repository.create(event)
    assert EventBus(database).replay()[0].event == event

    aborted = Event("task.created", {"task_id": "rolled-back"})
    with pytest.raises(RuntimeError, match="rollback"):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(aborted.id),
                    aborted.tenant_id,
                    aborted.event_type,
                    '{"task_id":"rolled-back"}',
                    aborted.occurred_at.isoformat(),
                ),
            )
            raise RuntimeError("rollback")
    assert [item.event.id for item in EventBus(database).replay()] == [event.id]


def test_subscriber_failures_are_reported_after_persist_and_replay(database):
    bus = EventBus(database)
    bus.subscribe(lambda _: (_ for _ in ()).throw(RuntimeError("subscriber offline")))
    event = Event("task.created", {"task_id": "durable"})

    with pytest.raises(
        EventDispatchError, match="persisted, but 1 subscriber"
    ) as error:
        bus.publish(event)

    assert error.value.envelope.event == event
    assert [item.event for item in bus.replay()] == [event]


def test_unsubscribe_and_tenant_scoped_replay(database):
    bus = EventBus(database)
    received = []
    token = bus.subscribe(received.append, tenant_id="tenant-a")
    first = Event("task.created", {}, tenant_id="tenant-a")
    second = Event("task.created", {}, tenant_id="tenant-b")

    bus.publish(first)
    assert bus.unsubscribe(token)
    assert not bus.unsubscribe(token)
    bus.publish(second)

    assert [item.event for item in received] == [first]
    assert [item.event for item in bus.replay(tenant_id="tenant-b")] == [second]
    assert bus.replay(tenant_id="tenant-a", after_sequence=1) == []


def test_bus_rejects_secret_like_payloads_and_invalid_replay_cursors(database):
    bus = EventBus(database)
    with pytest.raises(ValueError, match="secret-like data"):
        bus.publish(Event("credential.used", {"api_token": "never-store"}))
    with pytest.raises(ValueError, match="secret-like data"):
        bus.publish(Event("credential.used", {"comment": "password=never-store"}))
    for cursor in (-1, True, "1"):
        with pytest.raises(ValueError, match="after_sequence"):
            bus.replay(after_sequence=cursor)
    assert bus.replay() == []


def test_concurrent_publishers_receive_unique_replay_cursors(database):
    bus = EventBus(database)

    def publish(number):
        return bus.publish(Event("task.updated", {"number": number}))

    with ThreadPoolExecutor(max_workers=8) as pool:
        envelopes = list(pool.map(publish, range(40)))

    assert sorted(item.sequence for item in envelopes) == list(range(1, 41))
    replayed = EventBus(database).replay(limit=50)
    assert [item.sequence for item in replayed] == list(range(1, 41))


def test_event_stream_rejects_edits_and_deletes(database):
    event = Event("task.created", {"task_id": "immutable"})
    EventRepository(database).create(event)

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("DELETE FROM event_stream")
