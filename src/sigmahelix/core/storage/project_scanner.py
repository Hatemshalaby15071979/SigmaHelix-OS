"""Fast read-only project inventory and append-only persisted scan snapshots."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ..models import Project
from .audit import AuditLog
from .database import Database

_MANIFESTS = (
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "CMakeLists.txt",
    "*.sln",
)
_ENTRYPOINTS = (
    "main.py",
    "app.py",
    "manage.py",
    "__main__.py",
    "index.js",
    "index.ts",
    "index.html",
    "server.js",
    "server.ts",
    "wsgi.py",
    "asgi.py",
    "main.go",
    "main.rs",
    "Program.cs",
)
_PRUNED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "target",
    "vendor",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


class ProjectScanError(RuntimeError):
    """Raised when project inventory input or persistence is invalid."""


@dataclass(frozen=True, slots=True)
class ProjectScan:
    """One filesystem snapshot of a registered or discoverable repository."""

    id: UUID
    name: str
    root_path: Path
    scanned_at: datetime
    git_branch: str | None
    git_commit: str | None
    git_dirty: bool | None
    git_change_count: int
    manifests: tuple[str, ...]
    entrypoints: tuple[str, ...]
    findings: tuple[str, ...]
    health: str
    artifacts: tuple["ProjectArtifact", ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectArtifact:
    """A build artifact with an explicit target platform and support label."""

    path: str
    platform: str
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProjectScanBatch:
    """Deterministically ordered scan results and wall time."""

    scans: tuple[ProjectScan, ...]
    duration_seconds: float


def _utc(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC)


def _git_state(
    path: Path,
) -> tuple[str | None, str | None, bool | None, int, str | None]:
    try:
        status = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain=v1", "--branch"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.75,
        )
    except FileNotFoundError:
        return None, None, None, 0, "git_unavailable"
    except subprocess.TimeoutExpired:
        return None, None, None, 0, "git_status_timeout"
    if status.returncode != 0:
        return None, None, None, 0, "not_git_repository"

    lines = status.stdout.splitlines()
    branch_line = lines[0] if lines else ""
    branch = (
        branch_line[3:].split("...", 1)[0] if branch_line.startswith("## ") else None
    )
    changes = [line for line in lines[1:] if line and not line.startswith("## ")]
    try:
        head = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.75,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return branch, None, bool(changes), len(changes), "git_head_unavailable"
    commit = head.stdout.strip() if head.returncode == 0 else None
    finding = None if commit is not None else "git_head_unavailable"
    return branch, commit, bool(changes), len(changes), finding


def _scan_one(path: Path, tenant_id: str, scanned_at: datetime) -> ProjectScan:
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ProjectScanError(f"project root is not a directory: {resolved}")
    name = resolved.name or str(resolved)
    manifests: set[str] = set()
    entrypoints: set[str] = set()
    artifact_paths: set[str] = set()
    for current, directory_names, file_names in os.walk(resolved):
        current_path = Path(current)
        depth = len(current_path.relative_to(resolved).parts)
        directory_names[:] = sorted(
            item
            for item in directory_names
            if item not in _PRUNED_DIRS and not item.startswith(".")
        )
        if depth >= 3:
            directory_names.clear()
        relative_directory = current_path.relative_to(resolved)
        for file_name in file_names:
            relative_file = (relative_directory / file_name).as_posix()
            if file_name in _MANIFESTS or file_name.endswith(".sln"):
                manifests.add(relative_file)
            if file_name in _ENTRYPOINTS:
                entrypoints.add(relative_file)
            if Path(file_name).suffix.lower() in {
                ".exe",
                ".msi",
                ".bat",
                ".cmd",
                ".ps1",
                ".dll",
                ".appimage",
                ".deb",
                ".rpm",
                ".flatpak",
                ".desktop",
                ".jar",
            }:
                artifact_paths.add(relative_file)
    entrypoints_tuple = tuple(sorted(entrypoints)[:30])
    artifacts = tuple(_artifact_label(path) for path in sorted(artifact_paths))
    branch, commit, dirty, change_count, git_finding = _git_state(resolved)
    findings: list[str] = []
    if not any(
        (resolved / name).is_file() for name in ("README.md", "README.rst", "README")
    ):
        findings.append("missing_readme")
    if not manifests:
        findings.append("no_recognized_manifest")
    if not entrypoints:
        findings.append("no_detected_entrypoint")
    if git_finding:
        findings.append(git_finding)
    health = (
        "unavailable"
        if git_finding in {"git_unavailable", "git_status_timeout"}
        else ("needs_attention" if findings else "ok")
    )
    project_id = uuid5(NAMESPACE_URL, f"sigmahelix:project:{tenant_id}:{resolved}")
    return ProjectScan(
        project_id,
        name,
        resolved,
        scanned_at,
        branch,
        commit,
        dirty,
        change_count,
        tuple(sorted(manifests)),
        entrypoints_tuple,
        tuple(findings),
        health,
        artifacts,
    )


def _artifact_label(path: str) -> ProjectArtifact:
    suffix = Path(path).suffix.lower()
    if suffix in {".exe", ".msi", ".bat", ".cmd", ".ps1", ".dll"}:
        platform = "windows"
        supported = sys.platform.startswith("win")
    elif suffix in {".appimage", ".deb", ".rpm", ".flatpak", ".desktop"}:
        platform = "linux"
        supported = sys.platform.startswith("linux")
    else:
        platform = "java"
        supported = shutil.which("java") is not None
    if supported:
        return ProjectArtifact(
            path, platform, "supported", "target platform matches this host"
        )
    host = (
        "Windows"
        if sys.platform.startswith("win")
        else "Linux"
        if sys.platform.startswith("linux")
        else sys.platform
    )
    return ProjectArtifact(
        path,
        platform,
        "unsupported",
        f"{platform.title()} artifact is unsupported on {host}",
    )


class ProjectScanner:
    """Inspect project roots concurrently and optionally persist snapshots."""

    def __init__(
        self, database: Database, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._audit = AuditLog(database)

    def scan(self, roots: Iterable[Path], tenant_id: str = "local") -> ProjectScanBatch:
        """Read project metadata without changing the filesystem or database."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        inputs = tuple(roots)
        if len(inputs) > 1000:
            raise ValueError("scan batch cannot exceed 1000 project roots")
        paths: list[Path] = []
        for path in inputs:
            if not isinstance(path, Path) or not path.is_absolute():
                raise ValueError("project roots must be absolute Paths")
            resolved = path.resolve(strict=True)
            if not resolved.is_dir():
                raise ProjectScanError(f"project root is not a directory: {resolved}")
            paths.append(resolved)
        if len({str(path) for path in paths}) != len(paths):
            raise ValueError("project roots must not contain duplicates")
        scanned_at = _utc(self._clock)
        started = time.perf_counter()
        workers = min(16, max(1, len(paths)))
        results: list[ProjectScan] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_scan_one, path, tenant_id, scanned_at): str(path)
                for path in paths
            }
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: str(item.root_path).casefold())
        return ProjectScanBatch(tuple(results), time.perf_counter() - started)

    def record(
        self, batch: ProjectScanBatch, tenant_id: str = "local"
    ) -> tuple[ProjectScan, ...]:
        """Append scan snapshots and update each project's last-scan timestamp."""
        if not isinstance(batch, ProjectScanBatch):
            raise ValueError("batch must be a ProjectScanBatch")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        recorded: list[ProjectScan] = []
        now = _utc(self._clock)
        with self.database.transaction() as connection:
            for scan in batch.scans:
                project = Project(
                    scan.name,
                    scan.root_path,
                    id=scan.id,
                    created_at=now,
                    updated_at=now,
                    last_scanned_at=scan.scanned_at,
                    tenant_id=tenant_id,
                )
                connection.execute(
                    "INSERT INTO projects (id, tenant_id, name, root_path, created_at, updated_at, last_scanned_at, deleted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, NULL) "
                    "ON CONFLICT(tenant_id, root_path) DO UPDATE SET "
                    "name = excluded.name, updated_at = excluded.updated_at, "
                    "last_scanned_at = excluded.last_scanned_at",
                    (
                        str(project.id),
                        tenant_id,
                        project.name,
                        str(project.root_path),
                        project.created_at.isoformat(),
                        project.updated_at.isoformat(),
                        scan.scanned_at.isoformat(),
                    ),
                )
                project_row = connection.execute(
                    "SELECT id, created_at FROM projects WHERE tenant_id = ? AND root_path = ?",
                    (tenant_id, str(scan.root_path)),
                ).fetchone()
                project_id = UUID(project_row["id"])
                snapshot_id = uuid4()
                connection.execute(
                    "INSERT INTO project_scan_snapshots "
                    "(id, tenant_id, project_id, scanned_at, git_branch, git_commit, git_dirty, git_change_count, manifests_json, entrypoints_json, findings_json, health, artifacts_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(snapshot_id),
                        tenant_id,
                        str(project_id),
                        scan.scanned_at.isoformat(),
                        scan.git_branch,
                        scan.git_commit,
                        int(scan.git_dirty) if scan.git_dirty is not None else None,
                        scan.git_change_count,
                        json.dumps(scan.manifests, separators=(",", ":")),
                        json.dumps(scan.entrypoints, separators=(",", ":")),
                        json.dumps(scan.findings, separators=(",", ":")),
                        scan.health,
                        json.dumps(
                            [
                                {
                                    "path": artifact.path,
                                    "platform": artifact.platform,
                                    "status": artifact.status,
                                    "reason": artifact.reason,
                                }
                                for artifact in scan.artifacts
                            ],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
                event_type = "project.scanned"
                payload = {
                    "project_id": str(project_id),
                    "snapshot_id": str(snapshot_id),
                    "git_dirty": scan.git_dirty,
                    "health": scan.health,
                }
                connection.execute(
                    "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(uuid4()),
                        tenant_id,
                        event_type,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                        now.isoformat(),
                    ),
                )
                self._audit.append_in_transaction(
                    connection,
                    event_type,
                    "project",
                    str(project_id),
                    payload,
                    tenant_id=tenant_id,
                    occurred_at=now,
                )
                recorded.append(
                    ProjectScan(
                        project_id,
                        scan.name,
                        scan.root_path,
                        scan.scanned_at,
                        scan.git_branch,
                        scan.git_commit,
                        scan.git_dirty,
                        scan.git_change_count,
                        scan.manifests,
                        scan.entrypoints,
                        scan.findings,
                        scan.health,
                        scan.artifacts,
                    )
                )
        return tuple(recorded)

    def latest(self, project_id: UUID, tenant_id: str = "local") -> ProjectScan | None:
        """Return the latest stored snapshot for a project."""
        if not isinstance(project_id, UUID):
            raise ValueError("project_id must be a UUID")
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT s.*, p.name, p.root_path FROM project_scan_snapshots s "
                "JOIN projects p ON p.id = s.project_id AND p.tenant_id = s.tenant_id "
                "WHERE s.project_id = ? AND s.tenant_id = ? "
                "ORDER BY s.scanned_at DESC, s.rowid DESC LIMIT 1",
                (str(project_id), tenant_id),
            ).fetchone()
        if row is None:
            return None
        return ProjectScan(
            UUID(row["project_id"]),
            row["name"],
            Path(row["root_path"]),
            datetime.fromisoformat(row["scanned_at"]),
            row["git_branch"],
            row["git_commit"],
            bool(row["git_dirty"]) if row["git_dirty"] is not None else None,
            row["git_change_count"],
            tuple(json.loads(row["manifests_json"])),
            tuple(json.loads(row["entrypoints_json"])),
            tuple(json.loads(row["findings_json"])),
            row["health"],
            tuple(
                ProjectArtifact(**item) for item in json.loads(row["artifacts_json"])
            ),
        )
