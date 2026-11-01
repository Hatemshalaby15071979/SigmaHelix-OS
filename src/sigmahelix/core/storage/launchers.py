"""Explicit launcher profiles with display-only previews and run history."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from .audit import AuditLog
from .database import Database

_SECRET_ARG = re.compile(
    r"(?:^|[-_])(password|passwd|token|secret|credential|api[-_]?key|access[-_]?key)(?:$|=|[-_])",
    re.IGNORECASE,
)
_SAFE_ENVIRONMENT = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "DBUS_SESSION_BUS_ADDRESS",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
)


class LauncherError(RuntimeError):
    """Raised when a launcher profile cannot be safely previewed or started."""


@dataclass(frozen=True, slots=True)
class LauncherProfile:
    """An immutable, explicitly registered local command."""

    id: UUID
    tenant_id: str
    name: str
    project_id: UUID | None
    executable: Path
    arguments: tuple[str, ...]
    working_directory: Path
    created_at: datetime
    enabled: bool


@dataclass(frozen=True, slots=True)
class CommandPreview:
    """A display-only command and working directory; preview never executes."""

    profile_id: UUID
    profile_name: str
    command: str
    working_directory: Path


@dataclass(frozen=True, slots=True)
class LauncherRun:
    """Persistent lifecycle summary for one explicitly started profile."""

    id: UUID
    profile_id: UUID
    profile_name: str
    tenant_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    pid: int | None
    return_code: int | None
    error_type: str | None


@dataclass(slots=True)
class LaunchHandle:
    """A started local process paired with its durable history record."""

    run: LauncherRun
    process: subprocess.Popen[bytes]


def _profile_from_row(row) -> LauncherProfile:
    return LauncherProfile(
        UUID(row["id"]),
        row["tenant_id"],
        row["name"],
        UUID(row["project_id"]) if row["project_id"] else None,
        Path(row["executable"]),
        tuple(json.loads(row["arguments_json"])),
        Path(row["working_directory"]),
        datetime.fromisoformat(row["created_at"]),
        bool(row["enabled"]),
    )


def _run_from_row(row) -> LauncherRun:
    return LauncherRun(
        UUID(row["id"]),
        UUID(row["profile_id"]),
        row["profile_name"],
        row["tenant_id"],
        datetime.fromisoformat(row["started_at"]),
        datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
        row["status"],
        row["pid"],
        row["return_code"],
        row["error_type"],
    )


class LauncherService:
    """Register, preview, and explicitly start known local command profiles."""

    def __init__(
        self, database: Database, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._audit = AuditLog(database)

    def create_profile(
        self,
        name: str,
        executable: str | Path,
        arguments: tuple[str, ...],
        working_directory: Path,
        tenant_id: str = "local",
        project_id: UUID | None = None,
    ) -> LauncherProfile:
        """Persist a validated profile without starting it."""
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if project_id is not None and not isinstance(project_id, UUID):
            raise ValueError("project_id must be a UUID or None")
        if (
            not isinstance(working_directory, Path)
            or not working_directory.is_absolute()
        ):
            raise ValueError("working_directory must be an absolute Path")
        working_directory = working_directory.resolve(strict=True)
        if not working_directory.is_dir():
            raise ValueError("working_directory must be a directory")
        if isinstance(executable, Path):
            raw_executable = str(executable)
        elif isinstance(executable, str) and executable.strip():
            raw_executable = executable
        else:
            raise ValueError("executable must be a path or command name")
        found = shutil.which(raw_executable)
        if found is None:
            raise LauncherError("executable could not be resolved")
        executable_path = Path(found).resolve(strict=True)
        if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
            raise LauncherError("executable is not an executable file")
        if not isinstance(arguments, tuple) or any(
            not isinstance(argument, str) or "\x00" in argument
            for argument in arguments
        ):
            raise ValueError("arguments must be a tuple of NUL-free strings")
        if any(_SECRET_ARG.search(argument) for argument in arguments):
            raise LauncherError("arguments must not contain secret-like flags")
        created_at = self._now()
        profile = LauncherProfile(
            uuid4(),
            tenant_id,
            name.strip(),
            project_id,
            executable_path,
            arguments,
            working_directory,
            created_at,
            True,
        )
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO launcher_profiles "
                "(id, tenant_id, name, project_id, executable, arguments_json, working_directory, created_at, enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    str(profile.id),
                    tenant_id,
                    profile.name,
                    str(project_id) if project_id else None,
                    str(executable_path),
                    json.dumps(arguments, separators=(",", ":")),
                    str(working_directory),
                    created_at.isoformat(),
                ),
            )
        return profile

    def get_profile(
        self, profile_id: UUID, tenant_id: str = "local"
    ) -> LauncherProfile | None:
        if not isinstance(profile_id, UUID):
            raise ValueError("profile_id must be a UUID")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM launcher_profiles WHERE id = ? AND tenant_id = ?",
                (str(profile_id), tenant_id),
            ).fetchone()
        return _profile_from_row(row) if row is not None else None

    def list_profiles(self, tenant_id: str = "local") -> list[LauncherProfile]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM launcher_profiles WHERE tenant_id = ? AND enabled = 1 ORDER BY name, id",
                (tenant_id,),
            ).fetchall()
        return [_profile_from_row(row) for row in rows]

    def disable_profile(self, profile_id: UUID, tenant_id: str = "local") -> bool:
        if not isinstance(profile_id, UUID):
            raise ValueError("profile_id must be a UUID")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE launcher_profiles SET enabled = 0 WHERE id = ? AND tenant_id = ? AND enabled = 1",
                (str(profile_id), tenant_id),
            )
        return cursor.rowcount == 1

    def preview(self, profile_id: UUID, tenant_id: str = "local") -> CommandPreview:
        """Build a quoted command display; this method has no process effects."""
        profile = self.get_profile(profile_id, tenant_id)
        if profile is None or not profile.enabled:
            raise LauncherError("unknown or disabled launcher profile")
        return CommandPreview(
            profile.id,
            profile.name,
            shlex.join((str(profile.executable), *profile.arguments)),
            profile.working_directory,
        )

    def launch(self, profile_id: UUID, tenant_id: str = "local") -> LaunchHandle:
        """Start exactly one registered profile with no shell interpretation."""
        profile = self.get_profile(profile_id, tenant_id)
        if profile is None or not profile.enabled:
            raise LauncherError("unknown or disabled launcher profile")
        if not profile.executable.is_file() or not os.access(
            profile.executable, os.X_OK
        ):
            raise LauncherError("registered executable is no longer available")
        if not profile.working_directory.is_dir():
            raise LauncherError("registered working directory is no longer available")
        now = self._now()
        run_id = uuid4()
        command_json = json.dumps(
            [str(profile.executable), *profile.arguments],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        command_hash = hashlib.sha256(command_json.encode("utf-8")).hexdigest()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO launcher_runs "
                "(id, tenant_id, profile_id, profile_name, executable, arguments_json, working_directory, pid, started_at, finished_at, status, return_code, error_type) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, 'running', NULL, NULL)",
                (
                    str(run_id),
                    tenant_id,
                    str(profile.id),
                    profile.name,
                    str(profile.executable),
                    json.dumps(profile.arguments, separators=(",", ":")),
                    str(profile.working_directory),
                    now.isoformat(),
                ),
            )
            self._record_event(
                connection,
                "launcher.run.started",
                run_id,
                profile,
                {"command_sha256": command_hash, "status": "running"},
                now,
            )
        environment = {
            key: value for key, value in os.environ.items() if key in _SAFE_ENVIRONMENT
        }
        try:
            process = subprocess.Popen(
                [str(profile.executable), *profile.arguments],
                cwd=profile.working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            self._finish(
                run_id, tenant_id, return_code=None, error_type=type(exc).__name__
            )
            raise LauncherError("registered launcher failed to start") from exc
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE launcher_runs SET pid = ? WHERE id = ? AND tenant_id = ? AND status = 'running'",
                (process.pid, str(run_id), tenant_id),
            )
        run = LauncherRun(
            run_id,
            profile.id,
            profile.name,
            tenant_id,
            now,
            None,
            "running",
            process.pid,
            None,
            None,
        )
        return LaunchHandle(run, process)

    def refresh(self, handle: LaunchHandle) -> LauncherRun:
        """Persist completion if a launched child has exited."""
        if not isinstance(handle, LaunchHandle):
            raise ValueError("handle must be a LaunchHandle")
        current = self.get_run(handle.run.id, handle.run.tenant_id)
        if current is None or current.status != "running":
            return current or handle.run
        return_code = handle.process.poll()
        if return_code is not None and handle.run.status == "running":
            return self._finish(
                handle.run.id,
                handle.run.tenant_id,
                return_code=return_code,
                error_type=None,
            )
        return self.get_run(handle.run.id, handle.run.tenant_id) or handle.run

    def get_run(self, run_id: UUID, tenant_id: str = "local") -> LauncherRun | None:
        if not isinstance(run_id, UUID):
            raise ValueError("run_id must be a UUID")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM launcher_runs WHERE id = ? AND tenant_id = ?",
                (str(run_id), tenant_id),
            ).fetchone()
        return _run_from_row(row) if row is not None else None

    def run_history(
        self, profile_id: UUID | None = None, tenant_id: str = "local"
    ) -> list[LauncherRun]:
        if profile_id is not None and not isinstance(profile_id, UUID):
            raise ValueError("profile_id must be a UUID or None")
        query = "SELECT * FROM launcher_runs WHERE tenant_id = ?"
        parameters: tuple[str, ...]
        if profile_id is None:
            parameters = (tenant_id,)
        else:
            query += " AND profile_id = ?"
            parameters = (tenant_id, str(profile_id))
        query += " ORDER BY started_at DESC, rowid DESC"
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_run_from_row(row) for row in rows]

    def _finish(
        self,
        run_id: UUID,
        tenant_id: str,
        return_code: int | None,
        error_type: str | None,
    ) -> LauncherRun:
        now = self._now()
        status = "succeeded" if return_code == 0 and error_type is None else "failed"
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT r.*, p.project_id FROM launcher_runs r "
                "JOIN launcher_profiles p ON p.id = r.profile_id AND p.tenant_id = r.tenant_id "
                "WHERE r.id = ? AND r.tenant_id = ?",
                (str(run_id), tenant_id),
            ).fetchone()
            if row is None:
                raise LauncherError("launcher run does not exist")
            if row["status"] != "running":
                return _run_from_row(row)
            connection.execute(
                "UPDATE launcher_runs SET finished_at = ?, status = ?, return_code = ?, error_type = ? "
                "WHERE id = ? AND tenant_id = ? AND status = 'running'",
                (
                    now.isoformat(),
                    status,
                    return_code,
                    error_type,
                    str(run_id),
                    tenant_id,
                ),
            )
            profile = LauncherProfile(
                UUID(row["profile_id"]),
                tenant_id,
                row["profile_name"],
                UUID(row["project_id"]) if row["project_id"] else None,
                Path(row["executable"]),
                tuple(json.loads(row["arguments_json"])),
                Path(row["working_directory"]),
                datetime.fromisoformat(row["started_at"]),
                True,
            )
            self._record_event(
                connection,
                "launcher.run.finished",
                run_id,
                profile,
                {
                    "status": status,
                    "return_code": return_code,
                    "error_type": error_type or "",
                },
                now,
            )
            updated = connection.execute(
                "SELECT * FROM launcher_runs WHERE id = ? AND tenant_id = ?",
                (str(run_id), tenant_id),
            ).fetchone()
        return _run_from_row(updated)

    def _record_event(
        self,
        connection,
        event_type: str,
        run_id: UUID,
        profile: LauncherProfile,
        payload: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        event_id = uuid5(NAMESPACE_URL, f"sigmahelix:{event_type}:{run_id}")
        connection.execute(
            "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(event_id),
                profile.tenant_id,
                event_type,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                occurred_at.isoformat(),
            ),
        )
        self._audit.append_in_transaction(
            connection,
            event_type,
            "launcher_run",
            str(run_id),
            payload,
            tenant_id=profile.tenant_id,
            occurred_at=occurred_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)
