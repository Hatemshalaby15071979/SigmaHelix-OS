import subprocess
import sys
from datetime import UTC, datetime

from sigmahelix.core.storage import (
    AuditLog,
    Database,
    ProjectScanBatch,
    ProjectScanner,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def _git(path, *args):
    subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(path, index):
    path.mkdir()
    _git(path, "init", "--quiet", "--initial-branch=main")
    (path / "README.md").write_text(f"Project {index}\n", encoding="utf-8")
    (path / "pyproject.toml").write_text("[project]\nname='sample'\n", encoding="utf-8")
    (path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    _git(path, "add", "README.md", "pyproject.toml", "main.py")
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=SigmaHelix Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_scans_twelve_repositories_with_git_manifest_entrypoint_and_health(tmp_path):
    roots = []
    for index in range(12):
        root = tmp_path / f"project-{index:02d}"
        _make_repo(root, index)
        roots.append(root)

    database = Database((tmp_path / "sigmahelix.db").resolve())
    database.initialize()
    scanner = ProjectScanner(database, clock=lambda: NOW)
    batch = scanner.scan(roots)

    assert len(batch.scans) == 12
    assert batch.duration_seconds < 2.0
    assert all(scan.git_branch == "main" for scan in batch.scans)
    assert all(scan.git_commit for scan in batch.scans)
    assert all(scan.git_dirty is False for scan in batch.scans)
    assert all(scan.manifests == ("pyproject.toml",) for scan in batch.scans)
    assert all(scan.entrypoints == ("main.py",) for scan in batch.scans)
    assert all(scan.health == "ok" for scan in batch.scans)


def test_scan_is_read_only_until_persisted_then_latest_snapshot_is_tenant_scoped(
    tmp_path,
):
    root = tmp_path / "sample"
    _make_repo(root, 1)
    database = Database((tmp_path / "persist.db").resolve())
    database.initialize()
    scanner = ProjectScanner(database, clock=lambda: NOW)

    batch = scanner.scan([root], tenant_id="tenant-a")
    with database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0

    recorded = scanner.record(batch, tenant_id="tenant-a")[0]
    latest = scanner.latest(recorded.id, tenant_id="tenant-a")
    assert latest == recorded
    assert latest.health_score == 100
    assert scanner.latest(recorded.id, tenant_id="tenant-b") is None
    with database.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM project_scan_snapshots"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'project.scanned'"
            ).fetchone()[0]
            == 1
        )
    assert AuditLog(database).verify().valid


def test_dirty_state_and_health_findings_are_deterministic(tmp_path):
    repo = tmp_path / "dirty"
    _make_repo(repo, 2)
    (repo / "main.py").write_text("print('changed')\n", encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    database = Database((tmp_path / "state.db").resolve())
    database.initialize()

    scans = ProjectScanner(database, clock=lambda: NOW).scan([repo, empty]).scans
    dirty_scan = next(scan for scan in scans if scan.root_path == repo)
    empty_scan = next(scan for scan in scans if scan.root_path == empty)
    assert dirty_scan.git_dirty is True
    assert dirty_scan.git_change_count == 1
    assert empty_scan.health == "needs_attention"
    assert {
        "missing_readme",
        "no_recognized_manifest",
        "no_detected_entrypoint",
    } <= set(empty_scan.findings)


def test_windows_artifacts_are_explicitly_unsupported_on_linux_and_persisted(tmp_path):
    root = tmp_path / "windows-output"
    root.mkdir()
    (root / "setup.exe").write_bytes(b"test artifact")
    database = Database((tmp_path / "artifacts.db").resolve())
    database.initialize()
    scanner = ProjectScanner(database, clock=lambda: NOW)

    scan = scanner.scan([root]).scans[0]
    artifact = scan.artifacts[0]
    if sys.platform.startswith("linux"):
        assert artifact.platform == "windows"
        assert artifact.status == "unsupported"
        assert "unsupported on Linux" in artifact.reason
    saved = scanner.record(ProjectScanBatch((scan,), 0.0))[0]
    assert scanner.latest(saved.id).artifacts == scan.artifacts


def test_health_scores_are_deterministic_and_new_projects_compare_scan_batches(
    tmp_path,
):
    healthy = tmp_path / "healthy"
    _make_repo(healthy, 5)
    empty = tmp_path / "empty"
    empty.mkdir()
    added = tmp_path / "added"
    _make_repo(added, 6)
    database = Database((tmp_path / "score.db").resolve())
    database.initialize()
    scanner = ProjectScanner(database, clock=lambda: NOW)

    first = scanner.scan([healthy, empty])
    assert {scan.name: scan.health_score for scan in first.scans} == {
        "healthy": 100,
        "empty": 40,
    }
    assert scanner.new_since_last_scan(first) == first.scans
    scanner.record(first)

    second = scanner.scan([healthy, empty, added])
    assert [scan.name for scan in scanner.new_since_last_scan(second)] == ["added"]
    scanner.record(second)
    third = scanner.scan([healthy, empty, added])
    assert scanner.new_since_last_scan(third) == ()
