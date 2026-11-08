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
    (legacy) → ``<checkout>/../cloned_repos`` when that exists → a discovered
    ``cloned_repos`` folder (for installed binaries that have no checkout
    sibling) → ``~/projects``.
    """
    override = os.environ.get("SIGMAHELIX_PROJECTS_DIR") or os.environ.get(
        "COMPANY_OS_PROJECTS_DIR"
    )
    if override:
        return _expand(override)
    global _PROJECTS_DIR_CACHE
    if _PROJECTS_DIR_CACHE is not None:
        return _PROJECTS_DIR_CACHE
    root = checkout_root()
    if root is not None:
        sibling = root.parent / "cloned_repos"
        if sibling.is_dir():
            _PROJECTS_DIR_CACHE = sibling
            return sibling
    discovered = _discover_cloned_repos()
    if discovered is not None:
        _PROJECTS_DIR_CACHE = discovered
        return discovered
    fallback = Path.home() / "projects"
    _PROJECTS_DIR_CACHE = fallback
    return fallback


#: Resolved projects dir is cached so a (possibly slow) discovery runs once.
_PROJECTS_DIR_CACHE: Path | None = None


def _discover_cloned_repos() -> Path | None:
    """Find a ``cloned_repos`` directory when there is no checkout sibling.

    When SigmaHelix is installed away from its source (e.g. into
    ``~/.local/share``), the sibling trick cannot locate the user's projects.
    We then search a bounded set of roots — the home directory and mounted
    volumes — for a folder literally named ``cloned_repos``.
    """
    roots: list[tuple[Path, int]] = [(Path.home(), 1)]
    for mount in ("/run/media", "/media", "/mnt"):
        mount_path = Path(mount)
        if not mount_path.is_dir():
            continue
        try:
            for child in sorted(mount_path.iterdir()):
                if child.is_dir():
                    roots.append((child, 3))
        except OSError:
            continue
    for root, depth in roots:
        found = _find_dir_named(root, "cloned_repos", depth)
        if found is not None:
            return found
    return None


def _find_dir_named(root: Path, name: str, max_depth: int) -> Path | None:
    """Return the first directory named ``name`` within ``max_depth`` of ``root``."""
    if max_depth < 0 or not root.is_dir():
        return None
    try:
        children = sorted(
            child
            for child in root.iterdir()
            if child.is_dir() and not child.is_symlink()
        )
    except OSError:
        return None
    for child in children:
        if child.name == name:
            return child
    if max_depth == 0:
        return None
    for child in children:
        found = _find_dir_named(child, name, max_depth - 1)
        if found is not None:
            return found
    return None
