#!/usr/bin/env python3
"""Project detection: a directory is a project only with positive evidence.

Regression test for the bug where every folder (caches, scratch dirs, empty
folders) was listed as a project.
Run: ./venv/bin/python -m pytest tests/test_projects.py -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigmahelix.app.managers import ProjectsManager
from sigmahelix.app.projects import is_project_dir, list_project_dirs

REAL_REPOS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cloned_repos",
)


def mk(path, *files):
    os.makedirs(path, exist_ok=True)
    for f in files:
        fp = os.path.join(path, f)
        os.makedirs(os.path.dirname(fp) or path, exist_ok=True)
        open(fp, "w").close()
    return path


def test_junk_and_empty_dirs_are_not_projects(tmp_path):
    assert not is_project_dir(mk(tmp_path / "empty"), "empty")
    assert not is_project_dir(mk(tmp_path / ".pytest_cache"), ".pytest_cache")
    assert not is_project_dir(mk(tmp_path / ".tmp-venv-build"), ".tmp-venv-build")
    assert not is_project_dir(mk(tmp_path / "node_modules"), "node_modules")
    assert not is_project_dir(mk(tmp_path / "venv"), "venv")
    assert not is_project_dir(mk(tmp_path / "build"), "build")
    assert not is_project_dir(mk(tmp_path / "dist"), "dist")
    # even junk names with a manifest are refused
    assert not is_project_dir(mk(tmp_path / "build", "pyproject.toml"), "build")


def test_evidence_makes_a_project(tmp_path):
    assert is_project_dir(mk(tmp_path / "gitrepo", ".git/HEAD"), "gitrepo")
    assert is_project_dir(mk(tmp_path / "pyp", "pyproject.toml"), "pyp")
    assert is_project_dir(mk(tmp_path / "node", "package.json"), "node")
    assert is_project_dir(mk(tmp_path / "rs", "Cargo.toml"), "rs")
    assert is_project_dir(mk(tmp_path / "cs", "app.csproj"), "cs")


def test_list_project_dirs_excludes_junk(tmp_path):
    mk(tmp_path / "RealOne", "pyproject.toml")
    mk(tmp_path / "RealTwo", ".git/HEAD")
    mk(tmp_path / "empty")
    mk(tmp_path / ".pytest_cache")
    mk(tmp_path / ".tmp-venv-build")
    assert list_project_dirs(str(tmp_path)) == ["RealOne", "RealTwo"]


def test_manager_listing_has_no_junk(tmp_path):
    mk(tmp_path / "RealOne", ".git/HEAD")
    mk(tmp_path / ".pytest_cache")
    mk(tmp_path / ".tmp-venv-build")
    pm = ProjectsManager()
    pm.projects_dir = str(tmp_path)
    out = pm.list_projects("show projects")
    assert "RealOne" in out
    assert ".pytest_cache" not in out
    assert ".tmp-venv-build" not in out
    assert "Available projects (1)" in out


def test_real_repo_listing_has_no_junk():
    if not os.path.isdir(REAL_REPOS):
        return
    names = list_project_dirs(REAL_REPOS)
    assert ".pytest_cache" not in names
    assert ".tmp-venv-build" not in names
    assert "__pycache__" not in names
    # every listed name must prove itself
    for n in names:
        assert is_project_dir(os.path.join(REAL_REPOS, n), n), n
