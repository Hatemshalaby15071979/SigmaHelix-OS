from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock

import pytest

from sigmahelix.core.storage import Database, Scheduler, SchedulerError


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path):
    result = Database((tmp_path / "scheduler.db").resolve())
    result.initialize()
    return result


def test_one_shot_job_runs_when_due_once_and_persists_result(database):
    clock = FakeClock(NOW)
    scheduler = Scheduler(database, clock)
    calls = []
    scheduler.register_handler("notify", calls.append)
    job = scheduler.schedule("notify", {"message": "hello"}, NOW + timedelta(seconds=1))

    assert scheduler.run_due() == []
    clock.now += timedelta(seconds=1)
    runs = scheduler.run_due()
    assert len(runs) == 1
    assert calls == [{"message": "hello"}]
    assert runs[0].status == "succeeded"
    assert scheduler.get_job(job.id).enabled is False
    assert scheduler.run_due() == []
    assert scheduler.list_runs(job.id) == runs


def test_interval_job_uses_fixed_scheduled_slots(database):
    clock = FakeClock(NOW)
    scheduler = Scheduler(database, clock)
    calls = []
    scheduler.register_handler("tick", lambda payload: calls.append(payload))
    job = scheduler.schedule("tick", {}, NOW, interval_seconds=60)

    first = scheduler.run_due()
    assert first[0].scheduled_for == NOW
    clock.now += timedelta(seconds=60)
    second = scheduler.run_due()
    assert second[0].scheduled_for == NOW + timedelta(seconds=60)
    assert len(calls) == 2
    assert len(scheduler.list_runs(job.id)) == 2


def test_concurrent_scheduler_instances_claim_a_one_shot_only_once(database):
    clock = FakeClock(NOW)
    first = Scheduler(database, clock)
    second = Scheduler(database, clock)
    lock = Lock()
    calls = []

    def handler(payload):
        with lock:
            calls.append(payload)

    first.register_handler("once", handler)
    second.register_handler("once", handler)
    job = first.schedule("once", {"value": 1}, NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda scheduler: scheduler.run_due(), (first, second)))

    assert sum(map(len, results)) == 1
    assert calls == [{"value": 1}]
    assert len(first.list_runs(job.id)) == 1


def test_handler_failure_is_recorded_without_exception_message(database):
    scheduler = Scheduler(database, FakeClock(NOW))

    def fail(payload):
        raise RuntimeError("private details should not be stored")

    scheduler.register_handler("fail", fail)
    job = scheduler.schedule("fail", {}, NOW)
    run = scheduler.run_due()[0]

    assert run.status == "failed"
    assert run.error_type == "RuntimeError"
    assert scheduler.list_runs(job.id) == [run]
    with database.connection() as connection:
        assert "private details" not in str(
            connection.execute("SELECT * FROM job_runs").fetchone()
        )


def test_cancel_tenant_isolation_and_payload_validation(database):
    scheduler = Scheduler(database, FakeClock(NOW))
    job = scheduler.schedule("noop", {}, NOW, tenant_id="tenant-a")
    assert scheduler.get_job(job.id, "tenant-b") is None
    assert scheduler.cancel(job.id, "tenant-b") is False
    assert scheduler.cancel(job.id, "tenant-a") is True
    assert scheduler.run_due() == []
    with pytest.raises(SchedulerError, match="secret fields"):
        scheduler.schedule("noop", {"api_token": "hidden"}, NOW)
    with pytest.raises(SchedulerError, match="timezone-aware"):
        scheduler.schedule("noop", {}, datetime(2026, 11, 2))
    with pytest.raises(ValueError, match="interval_seconds"):
        scheduler.schedule("noop", {}, NOW, interval_seconds=0)
    with pytest.raises(SchedulerError, match="finite JSON"):
        scheduler.schedule("noop", {"value": float("nan")}, NOW)
