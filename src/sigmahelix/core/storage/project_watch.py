"""Debounced polling watch for project additions and metadata changes."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from .project_scanner import ProjectScanBatch, ProjectScanner, _PRUNED_DIRS

ScanCallback = Callable[[ProjectScanBatch], None]


class ProjectWatchError(RuntimeError):
    """Raised for invalid watch configuration or lifecycle calls."""


def _signature(root: Path, max_entries: int = 20_000) -> str:
    digest = hashlib.sha256()
    count = 0
    for current, directory_names, file_names in os.walk(root):
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in _PRUNED_DIRS and not name.startswith(".")
        )
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        if depth >= 3:
            directory_names.clear()
        for name in sorted(file_names):
            path = current_path / name
            try:
                metadata = path.stat(follow_symlinks=False)
            except OSError:
                continue
            digest.update(
                f"{path.relative_to(root).as_posix()}\0{metadata.st_mtime_ns}\0{metadata.st_size}\n".encode()
            )
            count += 1
            if count >= max_entries:
                digest.update(b"entry-limit-reached")
                return digest.hexdigest()
    return digest.hexdigest()


class ProjectWatch:
    """Watch project containers and perform debounced full rescans.

    The watcher monitors a container whose immediate visible directories are
    projects. It polls bounded file metadata signatures and never reads or
    writes project contents. `start()` records an initial snapshot by default;
    later changes are debounced before another scan is persisted.
    """

    def __init__(
        self,
        scanner: ProjectScanner,
        containers: Iterable[Path],
        callback: ScanCallback | None = None,
        poll_interval_seconds: float = 1.0,
        debounce_seconds: float = 0.3,
        tenant_id: str = "local",
    ) -> None:
        if (
            not isinstance(poll_interval_seconds, (int, float))
            or not 0.01 <= poll_interval_seconds <= 60
        ):
            raise ValueError("poll_interval_seconds must be between 0.01 and 60")
        if (
            not isinstance(debounce_seconds, (int, float))
            or not 0.01 <= debounce_seconds <= 30
        ):
            raise ValueError("debounce_seconds must be between 0.01 and 30")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        paths = tuple(containers)
        if not paths or any(
            not isinstance(path, Path) or not path.is_absolute() for path in paths
        ):
            raise ValueError("containers must be non-empty absolute Paths")
        normalized = tuple(path.resolve(strict=True) for path in paths)
        if any(not path.is_dir() for path in normalized):
            raise ValueError("every watch container must be a directory")
        if len(set(normalized)) != len(normalized):
            raise ValueError("watch containers must be unique")
        self.scanner = scanner
        self.containers = normalized
        self.callback = callback
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.debounce_seconds = float(debounce_seconds)
        self.tenant_id = tenant_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._snapshot: dict[Path, str] = {}
        self._last_batch: ProjectScanBatch | None = None
        self._last_error: str | None = None
        self._error_count = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_batch(self) -> ProjectScanBatch | None:
        with self._lock:
            return self._last_batch

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def error_count(self) -> int:
        with self._lock:
            return self._error_count

    def start(self, scan_existing: bool = True) -> None:
        """Capture current state, optionally scan it, then start polling."""
        if self.running:
            raise ProjectWatchError("watcher is already running")
        self._stop.clear()
        projects = self._projects()
        self._snapshot = {path: _signature(path) for path in projects}
        if scan_existing and projects:
            self._scan_and_publish(projects)
        self._thread = threading.Thread(
            target=self._run,
            name="sigmahelix-project-watch",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the polling thread and wait briefly for an active scan."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                raise ProjectWatchError("watcher did not stop before the timeout")
            self._thread = None

    def _projects(self) -> tuple[Path, ...]:
        found: set[Path] = set()
        for container in self.containers:
            try:
                found.update(
                    path.resolve(strict=True)
                    for path in container.iterdir()
                    if not path.name.startswith(".") and path.is_dir()
                )
            except OSError as exc:
                self._record_error(type(exc).__name__)
        return tuple(sorted(found, key=lambda item: str(item).casefold()))

    def _scan_and_publish(self, projects: tuple[Path, ...]) -> None:
        try:
            batch = self.scanner.scan(projects, tenant_id=self.tenant_id)
            self.scanner.record(batch, tenant_id=self.tenant_id)
            with self._lock:
                self._last_batch = batch
                self._last_error = None
            if self.callback is not None:
                self.callback(batch)
        except Exception as exc:
            self._record_error(type(exc).__name__)

    def _record_error(self, error_type: str) -> None:
        with self._lock:
            self._last_error = error_type
            self._error_count += 1

    def _run(self) -> None:
        changed_at: float | None = None
        while not self._stop.wait(self.poll_interval_seconds):
            projects = self._projects()
            snapshot = {path: _signature(path) for path in projects}
            if snapshot != self._snapshot:
                self._snapshot = snapshot
                changed_at = time.monotonic()
            if (
                changed_at is not None
                and time.monotonic() - changed_at >= self.debounce_seconds
            ):
                self._scan_and_publish(projects)
                self._snapshot = {path: _signature(path) for path in self._projects()}
                changed_at = None
