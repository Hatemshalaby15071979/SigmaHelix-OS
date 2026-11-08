"""Deciding what counts as a project directory on disk.

A folder is a project only with positive evidence: a VCS root or a
build/dependency manifest. Existing on disk is not evidence — caches, build
directories and scratch folders are directories too.
"""

from __future__ import annotations

import glob
import os
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
    base = root or PROJECTS_DIR
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
    base = Path(root or PROJECTS_DIR)
    return [base / name for name in list_project_dirs(str(base))]
