import os
import select
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from sigmahelix.core.models import Event
from sigmahelix.core.storage import Database, EventRepository


@pytest.mark.skipif(os.name != "posix", reason="SIGKILL crash test requires POSIX")
def test_sigkill_during_wal_write_recovers_committed_state_without_partial_rows(
    tmp_path: Path,
):
    database = Database(tmp_path / "crash" / "sigmahelix.db")
    database.initialize()
    committed = EventRepository(database).create(
        Event("task.created", {"task_id": "committed-before-crash"})
    )

    writer = r"""
import os, signal, sys, uuid
from pathlib import Path
from sigmahelix.core.storage import Database

database = Database(Path(sys.argv[1]))
with database.transaction() as connection:
    connection.execute("PRAGMA cache_size = 1")
    connection.execute("PRAGMA cache_spill = ON")
    for index in range(4000):
        connection.execute(
            "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
            "VALUES (?, 'local', 'crash.uncommitted', ?, '2026-11-02T12:00:00+00:00')",
            (str(uuid.uuid4()), '{"blob":"' + ('x' * 2048) + '","index":' + str(index) + '}'),
        )
    wal_size = Path(str(database.path) + "-wal").stat().st_size
    os.write(1, f"READY:{wal_size}\n".encode())
    signal.pause()
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", writer, str(database.path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 20)
        if not ready:
            stderr = process.stderr.read() if process.stderr else ""
            pytest.fail(f"writer did not reach its uncommitted WAL state: {stderr}")
        ready_line = process.stdout.readline().strip()
        assert ready_line.startswith("READY:"), ready_line
        wal_size = int(ready_line.partition(":")[2])
        assert wal_size > 32, "writer must spill uncommitted pages into the WAL"
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=10) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    recovered = Database(database.path)
    with recovered.connection() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'crash.uncommitted'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM event_stream").fetchone()[0] == 1
        )
        assert connection.execute(
            "SELECT id FROM events WHERE id = ?", (str(committed.id),)
        ).fetchone()[0] == str(committed.id)
    assert (
        not Path(str(database.path) + "-wal").exists()
        or Path(str(database.path) + "-wal").stat().st_size == 0
    )
