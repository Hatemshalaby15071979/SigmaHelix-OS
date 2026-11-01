from threading import Event, Lock
import time

from sigmahelix.core.storage import Database, ProjectScanner, ProjectWatch


def _make_project(path):
    path.mkdir()
    (path / "README.md").write_text("watch target\n", encoding="utf-8")
    (path / "pyproject.toml").write_text(
        "[project]\nname='watch-target'\n", encoding="utf-8"
    )
    (path / "main.py").write_text("print('ready')\n", encoding="utf-8")


def test_new_project_is_detected_and_recorded_within_five_seconds(tmp_path):
    container = tmp_path / "projects"
    container.mkdir()
    database = Database((tmp_path / "watch.db").resolve())
    database.initialize()
    scanner = ProjectScanner(database)
    observed = Event()
    batches = []
    watcher = ProjectWatch(
        scanner,
        [container],
        callback=lambda batch: (batches.append(batch), observed.set()),
        poll_interval_seconds=0.05,
        debounce_seconds=0.08,
    )
    watcher.start(scan_existing=False)
    try:
        _make_project(container / "new-project")
        assert observed.wait(5.0)
        assert batches[-1].scans[0].name == "new-project"
        assert watcher.running
        with database.connection() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM project_scan_snapshots"
                ).fetchone()[0]
                == 1
            )
    finally:
        watcher.stop()
    assert not watcher.running


def test_watch_debounces_multiple_file_changes_into_one_rescan(tmp_path):
    container = tmp_path / "projects"
    project = container / "existing"
    container.mkdir()
    _make_project(project)
    database = Database((tmp_path / "debounce.db").resolve())
    database.initialize()
    callback_lock = Lock()
    batches = []
    initial = Event()
    changed = Event()

    def on_scan(batch):
        with callback_lock:
            batches.append(batch)
            if len(batches) == 1:
                initial.set()
            else:
                changed.set()

    watcher = ProjectWatch(
        ProjectScanner(database),
        [container],
        callback=on_scan,
        poll_interval_seconds=0.04,
        debounce_seconds=0.12,
    )
    watcher.start()
    try:
        assert initial.wait(2.0)
        (project / "main.py").write_text("print('change one')\n", encoding="utf-8")
        time.sleep(0.07)
        (project / "main.py").write_text("print('change two')\n", encoding="utf-8")
        assert changed.wait(2.0)
        time.sleep(0.25)
        with callback_lock:
            assert len(batches) == 2
    finally:
        watcher.stop()
