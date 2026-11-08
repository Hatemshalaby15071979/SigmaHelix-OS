"""Project-directory discovery, including the installed-binary fallback."""

from __future__ import annotations

from sigmahelix.app import paths


def test_find_dir_named_finds_a_nested_cloned_repos(tmp_path):
    target = tmp_path / "Career" / "cloned_repos"
    target.mkdir(parents=True)

    assert paths._find_dir_named(tmp_path, "cloned_repos", 2) == target


def test_find_dir_named_respects_the_depth_limit(tmp_path):
    target = tmp_path / "a" / "b" / "cloned_repos"
    target.mkdir(parents=True)

    assert paths._find_dir_named(tmp_path, "cloned_repos", 1) is None
    assert paths._find_dir_named(tmp_path, "cloned_repos", 3) == target


def test_projects_dir_honours_the_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(tmp_path / "proj"))
    monkeypatch.delenv("COMPANY_OS_PROJECTS_DIR", raising=False)
    monkeypatch.setattr(paths, "_PROJECTS_DIR_CACHE", None)

    assert paths.projects_dir() == (tmp_path / "proj").resolve()


def test_projects_dir_uses_discovery_when_there_is_no_checkout(tmp_path, monkeypatch):
    discovered = tmp_path / "mnt" / "Career" / "cloned_repos"
    discovered.mkdir(parents=True)
    monkeypatch.delenv("SIGMAHELIX_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("COMPANY_OS_PROJECTS_DIR", raising=False)
    monkeypatch.setattr(paths, "_PROJECTS_DIR_CACHE", None)
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    monkeypatch.setattr(paths, "_discover_cloned_repos", lambda: discovered)

    assert paths.projects_dir() == discovered


def test_projects_dir_falls_back_to_home_projects(tmp_path, monkeypatch):
    monkeypatch.delenv("SIGMAHELIX_PROJECTS_DIR", raising=False)
    monkeypatch.delenv("COMPANY_OS_PROJECTS_DIR", raising=False)
    monkeypatch.setattr(paths, "_PROJECTS_DIR_CACHE", None)
    monkeypatch.setattr(paths, "checkout_root", lambda: None)
    monkeypatch.setattr(paths, "_discover_cloned_repos", lambda: None)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))

    assert paths.projects_dir() == tmp_path / "projects"
