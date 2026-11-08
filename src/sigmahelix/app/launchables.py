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
import re
import shlex
import shutil
import stat
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .paths import projects_dir
from .security import confine_to_root

#: How many run links a single project may contribute.
MAX_PER_PROJECT = 4

#: Build output folders that hold the artefact, not the sources.
_BUILD_DIRS = ("dist", "release", "target/release", "out", "build/bin")

#: Never descend into these while looking for an interface.
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "site-packages",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".cache",
        ".idea",
        ".vscode",
        "build",
        "target",
        "obj",
        "_archive",
        "_archive_pre_merge",
    }
)


@dataclass(frozen=True)
class Launchable:
    """Something the user can start with one click."""

    project: str
    kind: str
    label: str
    path: Path
    command: tuple[str, ...]
    requires: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "project": self.project,
            "kind": self.kind,
            "label": self.label,
            "path": str(self.path),
            "command": " ".join(self.command),
            "requires": list(self.requires),
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
    return _html_entrypoints(project)


def _walk(project: Path, max_depth: int = 3) -> Iterator[Path]:
    """Files under ``project`` to a bounded depth, skipping junk folders."""
    for current, dirs, files in os.walk(project):
        depth = len(Path(current).relative_to(project).parts)
        if depth >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = sorted(
                d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")
            )
        for name in sorted(files):
            yield Path(current) / name


def _python(project: Path) -> str:
    """The interpreter a project should run with: its venv if it has one."""
    for candidate in (project / ".venv/bin/python", project / "venv/bin/python"):
        if candidate.is_file():
            return str(candidate)
    return "python3"


#: A subfolder carrying these is a separate project, not this project's UI.
_NESTED_MARKERS = (
    ".git",
    "pyproject.toml",
    "package.json",
    "setup.py",
    "Cargo.toml",
    "go.mod",
)


def _is_nested_project(project: Path, path: Path) -> bool:
    """True when ``path`` lives inside another project vendored in this one."""
    parts = path.relative_to(project).parts[:-1]
    for index in range(1, len(parts) + 1):
        folder = project.joinpath(*parts[:index])
        if any((folder / marker).exists() for marker in _NESTED_MARKERS):
            return True
    return False


def _html_entrypoints(project: Path) -> list[Launchable]:
    """Every real HTML page that can be opened as a dashboard."""
    found: list[tuple[tuple[int, int, str], Launchable]] = []
    for path in _walk(project):
        if path.name not in ("index.html", "home.html"):
            continue
        rel = _rel(project, path)
        if "templates" in Path(rel).parts:
            continue  # a Jinja template, not a page you can open
        if _is_nested_project(project, path):
            continue  # a vendored copy of another project
        rank = (rel.count("/"), 0 if path.name == "index.html" else 1, rel)
        found.append(
            (
                rank,
                Launchable(
                    project=project.name,
                    kind="dashboard",
                    label=rel,
                    path=path,
                    command=("xdg-open", str(path)),
                ),
            )
        )
    found.sort(key=lambda item: item[0])
    return [item[1] for item in found[:1]]


#: Python imports that mean "this script opens a window": (marker, module).
_GUI_IMPORTS = (
    ("import tkinter", "tkinter"),
    ("from tkinter", "tkinter"),
    ("import PyQt5", "PyQt5"),
    ("import PyQt6", "PyQt6"),
    ("from PyQt5", "PyQt5"),
    ("from PyQt6", "PyQt6"),
    ("import PySide2", "PySide2"),
    ("import PySide6", "PySide6"),
    ("from PySide2", "PySide2"),
    ("from PySide6", "PySide6"),
    ("import webview", "webview"),
    ("import kivy", "kivy"),
)


#: Entry-point names that are tests or throwaway examples, never the app.
_SKIP_ENTRY = re.compile(r"(^test_|_test\.py$|smoke|conftest|example|sample)", re.I)


def _entry_candidates(project: Path, names: set[str], depth: int = 3) -> list[Path]:
    """Named entry-point files, shallowest first, ignoring tests and copies."""
    found = [
        path
        for path in _walk(project, max_depth=depth)
        if path.name in names
        and not _SKIP_ENTRY.search(path.name)
        and not _is_nested_project(project, path)
    ]
    return sorted(found, key=lambda p: (len(p.relative_to(project).parts), str(p)))


def _python_desktop(project: Path) -> list[Launchable]:
    """A desktop app entry point: a script that opens a real window."""
    names = {"desktop.py", "main.py", "app.py", "gui.py", "run.py", "__main__.py"}
    for path in _entry_candidates(project, names):
        text = _read_head(path, limit=200_000)
        module = next((m for marker, m in _GUI_IMPORTS if marker in text), None)
        if module is not None:
            rel = _rel(project, path)
            return [
                Launchable(
                    project=project.name,
                    kind="desktop",
                    label=f"python {rel}",
                    path=path,
                    command=(_python(project), str(path)),
                    requires=(module,),
                )
            ]
    return []


def _read_head(path: Path, limit: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _streamlit(project: Path) -> list[Launchable]:
    """A Streamlit app is a real dashboard; run it with the project's python."""
    for path in _walk(project, max_depth=2):
        if path.suffix != ".py" or _is_nested_project(project, path):
            continue
        if _SKIP_ENTRY.search(path.name):
            continue
        head = _read_head(path)
        if re.search(r"^\s*(?:import|from)\s+streamlit\b", head, re.MULTILINE):
            rel = _rel(project, path)
            return [
                Launchable(
                    project=project.name,
                    kind="web",
                    label=f"streamlit {rel}",
                    path=path,
                    command=(
                        _python(project),
                        "-m",
                        "streamlit",
                        "run",
                        str(path),
                        "--server.headless=true",
                        "--server.address=127.0.0.1",
                    ),
                    requires=("streamlit",),
                )
            ]
    return []


def _fastapi(project: Path) -> list[Launchable]:
    names = {"main.py", "app.py", "server.py", "api.py"}
    for path in _entry_candidates(project, names):
        head = _read_head(path, limit=60_000)
        if "FastAPI(" not in head or not re.search(
            r"^\s*\w+\s*=\s*FastAPI\(", head, re.M
        ):
            continue
        module = str(path.relative_to(project)).removesuffix(".py").replace("/", ".")
        return [
            Launchable(
                project=project.name,
                kind="web",
                label=f"uvicorn {module}",
                path=path,
                command=(
                    _python(project),
                    "-m",
                    "uvicorn",
                    f"{module}:app",
                    "--reload",
                    "--host",
                    "127.0.0.1",
                ),
                requires=("fastapi", "uvicorn"),
            )
        ]
    return []


def _flask(project: Path) -> list[Launchable]:
    names = {"app.py", "main.py", "server.py"}
    for path in _entry_candidates(project, names):
        head = _read_head(path, limit=60_000)
        if "Flask(" in head and re.search(r"^\s*\w+\s*=\s*Flask\(", head, re.M):
            rel = _rel(project, path)
            return [
                Launchable(
                    project=project.name,
                    kind="web",
                    label=f"flask {rel}",
                    path=path,
                    command=(_python(project), str(path)),
                    requires=("flask",),
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
                command=(_python(project), str(candidate), "runserver"),
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
    _python_desktop,
    _node_script,
    _streamlit,
    _fastapi,
    _flask,
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


def index_html(project: Path) -> Path | None:
    """The page a project opens as its interface, if it has one."""
    pages = _html_entrypoints(project)
    return pages[0].path if pages else None


#: Terminal emulators we can hand a dev server to, best first.
_TERMINALS = (
    "x-terminal-emulator",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "xterm",
)


def _terminal_argv(command: list[str], cwd: Path) -> list[str] | None:
    """Wrap a command so it runs visibly in a terminal window."""
    inner = (
        f"cd {shlex.quote(str(cwd))} && "
        f"{shlex.join(command)}; echo; echo '[finished] press Enter to close'; read -r"
    )
    for name in _TERMINALS:
        path = shutil.which(name)
        if not path:
            continue
        if name == "gnome-terminal":
            return [path, "--", "bash", "-lc", inner]
        return [path, "-e", "bash", "-lc", inner]
    return None


def _preflight(command: list[str], requires: tuple[str, ...] = ()) -> str | None:
    """Why a command cannot run here, before we open a window on a lie."""
    if len(command) >= 3 and command[1] == "-m":
        requires = (command[2], *requires)
    for module in dict.fromkeys(requires):
        try:
            probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [command[0], "-c", f"import {module}"],
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode != 0:
            return (
                f"{module} is not installed for {Path(command[0]).name} — "
                "install the project requirements first"
            )
    if command[0] == "npm" and not shutil.which("npm"):
        return "npm is not installed"
    if command[0] == "docker" and not shutil.which("docker"):
        return "docker is not installed"
    return None


def launch(item: Launchable, terminal: bool | None = None) -> tuple[bool, str]:
    """Start one launchable, confined to the projects directory.

    Web and service kinds open in a terminal so the server log is visible;
    packaged apps open detached. ``terminal`` overrides that choice.
    """
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

    problem = _preflight(command, item.requires)
    if problem:
        return False, problem

    want_terminal = item.kind in ("web", "service") if terminal is None else terminal
    argv = _terminal_argv(command, project_root) if want_terminal else None
    if want_terminal and argv is None:
        want_terminal = False

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
            argv or command,
            cwd=str(project_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL if argv is None else None,
            stderr=subprocess.DEVNULL if argv is None else None,
            start_new_session=True,
        )
    except FileNotFoundError:
        return False, f"{command[0]} is not installed"
    except OSError as exc:
        return False, str(exc)
    where = "in a terminal" if argv else "detached"
    return True, f"started {item.label} from {item.project} ({where})"
