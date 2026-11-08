import shlex
import sys
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sigmahelix.core.storage import AuditLog, Database, LauncherError, LauncherService

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def launcher_service(tmp_path):
    database = Database((tmp_path / "launchers.db").resolve())
    database.initialize()
    return database, LauncherService(database, clock=lambda: NOW)


def test_preview_only_displays_known_command_and_unknown_profile_never_spawns(
    launcher_service, tmp_path, monkeypatch
):
    database, service = launcher_service
    profile = service.create_profile(
        "literal-argument",
        sys.executable,
        ("-c", "pass", "; touch should-not-exist"),
        tmp_path.resolve(),
    )
    spawn_calls = []
    monkeypatch.setattr(
        "sigmahelix.core.storage.launchers.subprocess.Popen",
        lambda *args, **kwargs: spawn_calls.append((args, kwargs)),
    )

    preview = service.preview(profile.id)
    assert preview.command == shlex.join((str(profile.executable), *profile.arguments))
    assert preview.working_directory == tmp_path.resolve()
    with pytest.raises(LauncherError, match="unknown or disabled"):
        service.launch(uuid4())
    assert spawn_calls == []
    assert service.run_history() == []


def test_explicit_launch_uses_argv_without_shell_and_persists_result(
    launcher_service, tmp_path
):
    database, service = launcher_service
    output = tmp_path / "argv.txt"
    literal = "; touch command-injection-sentinel"
    code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])"
    profile = service.create_profile(
        "safe-argv",
        sys.executable,
        ("-c", code, str(output), literal),
        tmp_path.resolve(),
    )

    preview = service.preview(profile.id)
    assert "command-injection-sentinel" in preview.command
    handle = service.launch(profile.id)
    assert handle.run.status == "running"
    assert handle.process.wait(timeout=3) == 0
    completed = service.refresh(handle)

    assert completed.status == "succeeded"
    assert completed.return_code == 0
    assert output.read_text(encoding="utf-8") == literal
    assert not (tmp_path / "command-injection-sentinel").exists()
    assert service.refresh(handle) == completed
    assert service.run_history(profile.id) == [completed]
    assert AuditLog(database).verify().valid


def test_failed_exit_disable_and_profile_scope_are_recorded(launcher_service, tmp_path):
    _database, service = launcher_service
    profile = service.create_profile(
        "fails",
        sys.executable,
        ("-c", "raise SystemExit(3)"),
        tmp_path.resolve(),
        tenant_id="tenant-a",
    )
    assert service.get_profile(profile.id, "tenant-b") is None
    with pytest.raises(LauncherError, match="unknown or disabled"):
        service.preview(profile.id, "tenant-b")

    handle = service.launch(profile.id, "tenant-a")
    assert handle.process.wait(timeout=3) == 3
    run = service.refresh(handle)
    assert run.status == "failed"
    assert run.return_code == 3
    assert service.disable_profile(profile.id, "tenant-a") is True
    assert service.disable_profile(profile.id, "tenant-a") is False
    with pytest.raises(LauncherError, match="unknown or disabled"):
        service.launch(profile.id, "tenant-a")


def test_launcher_rejects_secret_flags_and_missing_executable(
    launcher_service, tmp_path
):
    _database, service = launcher_service
    with pytest.raises(LauncherError, match="secret-like flags"):
        service.create_profile(
            "unsafe",
            sys.executable,
            ("--api-key", "secret-value"),
            tmp_path.resolve(),
        )
    with pytest.raises(LauncherError, match="could not be resolved"):
        service.create_profile(
            "missing", "/definitely/not/a/real/launcher", (), tmp_path.resolve()
        )
