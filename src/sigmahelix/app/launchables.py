"""Finding and starting what a project has already built.

A project only earns a run link when an artefact really exists: a packaged
binary, a desktop entry, a web entry point or a compose file. Nothing here
guesses from a README.

Every command is an argv list run with ``shell=False`` from the project root,
and the path is confined to the projects directory, so a project name can
never turn into a shell command.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import projects_dir
from .security import confine_to_root

#: How many run links a single project may contribute.
MAX_PER_PROJECT = 4

#: Build output folders that hold the artefact, not the sources.
_BUILD_DIRS = ("dist", "release", "target/release", "out", "build/bin")


@dataclass(frozen=True)
class Launchable:
    """Something the user can start with one click."""

    project: str
    kind: str
    label: str
    path: Path
    command: tuple[str, ...]

    def as_dict(self) -> dict[str, str]:
        return {
            "project": self.project,
            "kind": self.kind,
            "label": self.label,
            "path": str(self.path),
            "command": " ".join(self.command),
        }


def _rel(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return path.name


def _appimages(project: Path) -> list[Launchable]:
    found = []
    for folder in (project, *(project / name for name in _BUILD_DIRS)):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.AppImage")):
            found.append(
                Launchable(
                    project=project.name,
                    kind="appimage",
                    label=path.name,
                    path=path,
                    command=(str(path),),
                )
            )
    return found


def _executables(project: Path) -> list[Launchable]:
    found = []
    for folder in (project, *(project / name for name in _BUILD_DIRS)):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.exe")):
            found.append(
                Launchable(
                    project=project.name,
                    kind="exe",
                    label=path.name,
                    path=path,
                    command=("wine", str(path)),
                )
            )
    return found


def _desktop_entries(project: Path) -> list[Launchable]:
    found = []
    for folder in (project, project / "dist"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.desktop")):
            found.append(
                Launchable(
                    project=project.name,
                    kind="desktop",
                    label=path.stem,
                    path=path,
                    command=("gio", "launch", str(path)),
                )
            )
    return found


def _node_script(project: Path) -> list[Launchable]:
    manifest = project / "package.json"
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    scripts = data.get("scripts") or {}
    for name in ("dev", "start", "preview", "serve"):
        if name in scripts:
            return [
                Launchable(
                    project=project.name,
                    kind="web",
                    label=f"npm run {name}",
                    path=manifest,
                    command=("npm", "run", name),
                )
            ]
    return []


def _static_site(project: Path) -> list[Launchable]:
    for candidate in (project / "dist" / "index.html", project / "index.html"):
        if candidate.is_file():
            return [
                Launchable(
                    project=project.name,
                    kind="dashboard",
                    label=_rel(project, candidate),
                    path=candidate,
                    command=("xdg-open", str(candidate)),
                )
            ]
    return []


def _compose(project: Path) -> list[Launchable]:
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml"):
        candidate = project / name
        if candidate.is_file():
            return [
                Launchable(
                    project=project.name,
                    kind="service",
                    label=name,
                    path=candidate,
                    command=("docker", "compose", "up", "-d"),
                )
            ]
    return []


def _django(project: Path) -> list[Launchable]:
    candidate = project / "manage.py"
    if candidate.is_file():
        return [
            Launchable(
                project=project.name,
                kind="web",
                label="Django dev server",
                path=candidate,
                command=(sys.executable, str(candidate), "runserver"),
            )
        ]
    return []


def _dotnet(project: Path) -> list[Launchable]:
    solutions = sorted(project.glob("*.sln"))
    if solutions:
        return [
            Launchable(
                project=project.name,
                kind="desktop",
                label=solutions[0].stem,
                path=solutions[0],
                command=("dotnet", "run", "--project", str(solutions[0])),
            )
        ]
    return []


_DETECTORS = (
    _appimages,
    _executables,
    _desktop_entries,
    _node_script,
    _static_site,
    _compose,
    _django,
    _dotnet,
)


def detect_launchables(project: Path) -> list[Launchable]:
    """Every runnable artefact inside one project, best first."""
    if not project.is_dir():
        return []
    found: list[Launchable] = []
    for detector in _DETECTORS:
        try:
            found.extend(detector(project))
        except OSError:
            continue
    return found[:MAX_PER_PROJECT]


def scan_launchables(root: Path | None = None) -> dict[str, list[Launchable]]:
    """Map project name -> runnables, for every project under ``root``."""
    base = root or projects_dir()
    result: dict[str, list[Launchable]] = {}
    if not base.is_dir():
        return result
    for entry in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        items = detect_launchables(entry)
        if items:
            result[entry.name] = items
    return result


def _ensure_executable(path: Path) -> None:
    mode = path.stat().st_mode
    if not mode & stat.S_IXUSR:
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def launch(item: Launchable) -> tuple[bool, str]:
    """Start one launchable, detached, confined to the projects directory."""
    try:
        root = projects_dir()
        confine_to_root(root, str(item.path))
        project_root = confine_to_root(root, item.project)
    except ValueError as exc:
        return False, f"refused: {exc}"

    command = list(item.command)
    if item.kind == "appimage":
        try:
            _ensure_executable(item.path)
        except OSError as exc:
            return False, f"cannot make {item.label} executable: {exc}"

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(Path.home())),
        "DISPLAY": os.environ.get("DISPLAY", ""),
        "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    try:
        subprocess.Popen(  # noqa: S603 - argv list, no shell
            command,
            cwd=str(project_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        return False, f"{command[0]} is not installed"
    except OSError as exc:
        return False, str(exc)
    return True, f"started {item.label} from {item.project}"
