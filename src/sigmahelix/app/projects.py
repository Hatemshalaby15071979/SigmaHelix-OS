"""Deciding what counts as a project directory on disk.

A folder is a project only with positive evidence: a VCS root or a
build/dependency manifest. Existing on disk is not evidence — caches, build
directories and scratch folders are directories too.
"""

from __future__ import annotations

import difflib
import glob
import os
import re
from pathlib import Path

from .paths import projects_dir

_PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "CMakeLists.txt",
    "Makefile",
    "deno.json",
    "bun.lockb",
    "mix.exs",
    "pubspec.yaml",
)
_PROJECT_GLOBS = ("*.csproj", "*.sln", "*.uproject", "*.xcodeproj", "*.cabal")

#: Never a project, whatever it contains.
JUNK_DIRS = frozenset(
    {
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "build",
        "dist",
        "target",
        "out",
        "bin",
        "obj",
        "site-packages",
        ".git",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        ".tmp-venv-build",
        ".idea",
        ".vscode",
    }
)

PROJECTS_DIR = str(projects_dir())


def is_project_dir(path: str | os.PathLike[str], name: str | None = None) -> bool:
    """True only when a directory proves it is a project."""
    label = name or os.path.basename(os.path.normpath(str(path)))
    if not label or label.startswith(".") or label.lower() in JUNK_DIRS:
        return False
    if not os.path.isdir(path):
        return False
    if any(os.path.exists(os.path.join(path, marker)) for marker in _PROJECT_MARKERS):
        return True
    return any(glob.glob(os.path.join(path, pattern)) for pattern in _PROJECT_GLOBS)


def list_project_dirs(root: str | None = None) -> list[str]:
    """Names of proven projects under ``root``, sorted, junk excluded."""
    base = str(root) if root else str(projects_dir())
    if not os.path.isdir(base):
        return []
    names = [
        entry
        for entry in os.listdir(base)
        if is_project_dir(os.path.join(base, entry), entry)
    ]
    return sorted(names, key=str.lower)


def project_paths(root: str | None = None) -> list[Path]:
    """Absolute paths of proven projects under ``root``."""
    base = Path(root) if root else projects_dir()
    return [base / name for name in list_project_dirs(str(base))]


#: Words that describe the request, not the project.
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "app",
        "application",
        "dashboard",
        "project",
        "repo",
        "repository",
        "website",
        "webapp",
        "web",
        "site",
        "ui",
        "please",
        "for",
        "me",
        "my",
        "up",
        "now",
    }
)


def _normalise(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def match_projects(query: str, root: str | None = None) -> list[str]:
    """Rank real project names against a free-text query, best first.

    Matching is deliberately forgiving — the user types "launch Helix codex app"
    and means ``Helix-Codex``. It never invents a name: only names that exist in
    the projects directory come back.
    """
    names = list_project_dirs(root)
    if not names:
        return []
    words = query.lower().replace("-", " ").replace("_", " ").split()
    words = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    cleaned = " ".join(words)
    needle = _normalise(cleaned)
    if not needle:
        return []

    normalised = {name: _normalise(name) for name in names}

    exact = [name for name, norm in normalised.items() if norm == needle]
    if exact:
        return sorted(exact)

    contained = [
        name
        for name, norm in normalised.items()
        if len(norm) >= 3 and (needle in norm or norm in needle)
    ]
    if contained:
        return sorted(
            contained, key=lambda n: (abs(len(normalised[n]) - len(needle)), n)
        )

    # Token overlap: "blue waves music" -> Blue Waves Music Production.
    tokens = {w for w in words if len(w) > 2}
    scored: list[tuple[int, str]] = []
    for name in normalised:
        name_tokens = {
            part for part in re.split(r"[^a-z0-9]+", name.lower()) if len(part) > 2
        }
        hits = len(tokens & name_tokens)
        if hits:
            scored.append((hits, name))
    if scored:
        best = max(hits for hits, _ in scored)
        return sorted(name for hits, name in scored if hits == best)

    close = difflib.get_close_matches(
        needle, list(normalised.values()), n=3, cutoff=0.6
    )
    return [name for name, norm in normalised.items() if norm in close]
