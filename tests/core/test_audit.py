import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from sigmahelix.core.storage import (
    AuditLog,
    AuditLogError,
    Database,
)


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "audit" / "sigmahelix.db")
    db.initialize()
    return db


def test_one_thousand_records_form_a_verifiable_chain(database):
    audit = AuditLog(database)
    occurred_at = datetime(2026, 11, 2, tzinfo=UTC)

    for number in range(1000):
        audit.append(
            "task.updated",
            "task",
            f"task-{number}",
            {"number": number, "state": "done"},
            occurred_at=occurred_at,
        )

    assert audit.verify().valid
    assert audit.verify().entries_checked == 1000
    entries = audit.list_entries(limit=3)
    assert [entry.sequence for entry in entries] == [998, 999, 1000]
    assert entries[-1].payload == {"number": 999, "state": "done"}


def test_chain_verification_detects_row_tampering(database):
    audit = AuditLog(database)
    first = audit.append("task.created", "task", "task-1", {"title": "First"})
    audit.append("task.updated", "task", "task-1", {"title": "Second"})
    assert audit.verify().valid

    with database.transaction() as connection:
        connection.execute("DROP TRIGGER audit_log_no_update")
        connection.execute(
            "UPDATE audit_log SET payload_json = ? WHERE sequence = ?",
            ('{"title":"forged"}', first.sequence),
        )

    result = audit.verify()
    assert not result.valid
    assert result.error_sequence == first.sequence
    assert result.reason == "record hash mismatch"


def test_append_can_share_transaction_and_rolls_back_with_domain_work(database):
    audit = AuditLog(database)
    with pytest.raises(RuntimeError, match="abort business operation"):
        with database.transaction() as connection:
            entry = audit.append_in_transaction(
                connection, "task.created", "task", "task-1", {"title": "Atomic"}
            )
            assert entry.sequence == 1
            raise RuntimeError("abort business operation")

    assert audit.verify().entries_checked == 0
    with pytest.raises(AuditLogError, match="active transaction"):
        with database.connection() as connection:
            audit.append_in_transaction(
                connection, "task.created", "task", "task-1", {"title": "No tx"}
            )


def test_concurrent_appends_are_serialized_and_verify(database):
    audit = AuditLog(database)

    def append(number):
        return audit.append(
            "task.updated", "task", f"task-{number}", {"number": number}
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(append, range(64)))

    assert sorted(entry.sequence for entry in entries) == list(range(1, 65))
    verification = audit.verify()
    assert verification.valid
    assert verification.entries_checked == 64


def test_audit_payloads_and_timestamps_are_validated(database):
    audit = AuditLog(database)

    with pytest.raises(ValueError, match="finite JSON"):
        audit.append("action", "entity", "id", {"bad": float("nan")})
    with pytest.raises(ValueError, match="timezone-aware"):
        audit.append("action", "entity", "id", {}, occurred_at=datetime(2026, 11, 2))
    with pytest.raises(ValueError, match="string keys"):
        audit.append("action", "entity", "id", {1: "bad"})
    with pytest.raises(ValueError, match="secret fields"):
        audit.append("action", "entity", "id", {"api_token": "never-store"})
    with pytest.raises(ValueError, match="secret-like values"):
        audit.append("action", "entity", "id", {"comment": "password=ordinary"})
    assert audit.verify().entries_checked == 0


def test_append_only_database_triggers_reject_edits_and_deletes(database):
    audit = AuditLog(database)
    audit.append("task.created", "task", "task-1", {"ok": True})

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("DELETE FROM audit_log")
