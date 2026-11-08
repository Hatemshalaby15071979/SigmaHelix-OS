"""Filesystem locations used by the desktop app.

Centralises every path decision so the app can run from a source checkout, from
an installed wheel, or from a PyInstaller bundle without hardcoded directories.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "sigmahelix"
LEGACY_APP_NAME = ".company-os"


def _expand(value: str) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def data_dir() -> Path:
    """Directory for app-owned files such as the model catalog cache.

    Precedence: ``SIGMAHELIX_DATA_DIR`` → ``COMPANY_OS_DATA_DIR`` (legacy) →
    ``$XDG_DATA_HOME/sigmahelix`` → ``~/.local/share/sigmahelix``.
    """
    override = os.environ.get("SIGMAHELIX_DATA_DIR") or os.environ.get(
        "COMPANY_OS_DATA_DIR"
    )
    if override:
        return _expand(override)
    xdg = os.environ.get("XDG_DATA_HOME")
    base = _expand(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME


def legacy_data_dir() -> Path:
    """Where the pre-merge Company OS kept its JSON files, if anywhere."""
    return Path.home() / LEGACY_APP_NAME


def legacy_json_dir() -> Path:
    """Directory scanned once for pre-merge ``tasks.json`` and ``notes.json``.

    The legacy layout kept the files directly in ``~/.company-os``. When the
    data directory is overridden explicitly (tests, portable installs) only
    that directory is considered, so a developer's home directory is never
    read by accident.
    """
    if os.environ.get("SIGMAHELIX_DATA_DIR") or os.environ.get("COMPANY_OS_DATA_DIR"):
        return data_dir()
    legacy = legacy_data_dir()
    if (legacy / "tasks.json").is_file() or (legacy / "notes.json").is_file():
        return legacy
    return data_dir()


def checkout_root() -> Path | None:
    """Nearest ancestor containing ``pyproject.toml``, if this is a checkout."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def projects_dir() -> Path:
    """Directory holding the user's project folders.

    Precedence: ``SIGMAHELIX_PROJECTS_DIR`` → ``COMPANY_OS_PROJECTS_DIR``
    (legacy) → ``<checkout>/../cloned_repos`` when that exists → ``~/projects``.
    """
    override = os.environ.get("SIGMAHELIX_PROJECTS_DIR") or os.environ.get(
        "COMPANY_OS_PROJECTS_DIR"
    )
    if override:
        return _expand(override)
    root = checkout_root()
    if root is not None:
        sibling = root.parent / "cloned_repos"
        if sibling.is_dir():
            return sibling
    return Path.home() / "projects"
