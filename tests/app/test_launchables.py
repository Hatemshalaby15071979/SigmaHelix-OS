"""Project interfaces: detection, name resolution and honest launching.

The agent must find any project by name and start what that project actually
contains — never fall back to a hardcoded list of app names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app import launchables
from sigmahelix.app.projects import match_projects


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    return agent_module.Agent()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A fake projects dir with four different kinds of interface."""
    root = tmp_path / "cloned_repos"
    root.mkdir()

    def project(name: str) -> Path:
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        return folder

    static = project("Helix-Codex")
    (static / "marketing").mkdir(parents=True)
    (static / "index.html").write_text("<html>codex</html>")
    (static / "marketing" / "index.html").write_text("<html>mkt</html>")

    gui = project("L-D-Command-Center")
    (gui / "desktop_shell").mkdir(parents=True)
    (gui / "desktop_shell" / "app.py").write_text("import tkinter as tk\n")
    (gui / "gui_smoke.py").write_text("import tkinter as tk\n")

    stream = project("wfm-forecasting-calculator")
    (stream / "app_wfm.py").write_text("import streamlit as st\n")
    (stream / "requirements.txt").write_text("streamlit\n")

    vendored = project("CompliProof")
    (vendored / "dashboard").mkdir(parents=True)
    (vendored / "dashboard" / "home.html").write_text("<html>home</html>")
    nested = vendored / "helix-education"
    (nested / "dashboard").mkdir(parents=True)
    (nested / ".git").mkdir()
    (nested / "dashboard" / "index.html").write_text("<html>nested</html>")

    templated = project("CreateLee")
    (templated / "templates").mkdir(parents=True)
    (templated / "templates" / "index.html").write_text("<html>jinja</html>")

    monkeypatch.setattr("sigmahelix.app.projects.PROJECTS_DIR", str(root))
    monkeypatch.setattr("sigmahelix.app.paths._PROJECTS_DIR_CACHE", root)
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))
    return root


def test_match_projects_is_forgiving_but_real(workspace):
    assert match_projects("launch Helix codex app") == ["Helix-Codex"]
    assert match_projects("helix codex") == ["Helix-Codex"]
    assert match_projects("wfm") == ["wfm-forecasting-calculator"]
    assert match_projects("ld command center") == ["L-D-Command-Center"]
    assert match_projects("nonsense") == []


def test_html_prefers_the_projects_own_page(workspace):
    root = workspace / "CompliProof"
    page = launchables.index_html(root)
    assert page is not None
    assert page.name == "home.html"  # not the vendored helix-education copy


def test_templates_are_not_pages(workspace):
    assert launchables.index_html(workspace / "CreateLee") is None


def test_detects_desktop_streamlit_and_static(workspace):
    codex = launchables.detect_launchables(workspace / "Helix-Codex")
    assert codex[0].kind == "dashboard"
    assert codex[0].label == "index.html"

    gui = launchables.detect_launchables(workspace / "L-D-Command-Center")
    assert gui[0].kind == "desktop"
    assert gui[0].label == "python desktop_shell/app.py"
    assert gui[0].requires == ("tkinter",)

    stream = launchables.detect_launchables(workspace / "wfm-forecasting-calculator")
    assert stream[0].kind == "web"
    assert stream[0].command[1:3] == ("-m", "streamlit")
    assert stream[0].requires == ("streamlit",)


def test_launch_resolves_any_project_and_reports_evidence(
    workspace, offline_agent, monkeypatch
):
    started = []

    def fake_launch(item, terminal=None):
        started.append((item.project, item.label, terminal))
        return True, f"started {item.label}"

    monkeypatch.setattr(launchables, "launch", fake_launch)
    reply = offline_agent.process_command("launch Helix codex app")
    assert "Helix-Codex" in reply
    assert started and started[0][0] == "Helix-Codex"
    assert "Which app to launch" not in reply
    assert offline_agent.last_trace.get("thinking")


def test_launch_unknown_project_lists_real_names(workspace, offline_agent):
    reply = offline_agent.process_command("launch the teleporter")
    assert "couldn't match" in reply.lower()
    assert "Helix-Codex" in reply


def test_launch_ambiguous_project_asks(workspace, offline_agent, monkeypatch):
    monkeypatch.setattr(launchables, "launch", lambda item, terminal=None: (True, "ok"))
    prime = workspace / "Helix-Prime"
    prime.mkdir()
    (prime / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (prime / "index.html").write_text("<html>prime</html>")
    reply = offline_agent.process_command("launch helix")
    assert reply.startswith("Which one?")


def test_launch_without_interface_is_honest(workspace, offline_agent):
    bare = workspace / "Blue Waves Music Production"
    bare.mkdir()
    (bare / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (bare / "README.md").write_text("# music")
    reply = offline_agent.process_command("launch blue waves music")
    assert "no interface" in reply.lower()
    assert "README.md" in reply


def test_preflight_reports_missing_module(tmp_path):
    script = tmp_path / "app.py"
    script.write_text("import definitely_missing_module_xyz\n")
    item = launchables.Launchable(
        project=tmp_path.name,
        kind="desktop",
        label="python app.py",
        path=script,
        command=("python3", str(script)),
        requires=("definitely_missing_module_xyz",),
    )
    assert launchables._preflight(list(item.command), item.requires)


def test_model_preamble_never_masks_the_tool_result(
    workspace, offline_agent, monkeypatch
):
    agent = offline_agent
    agent.llm_available = True
    agent.model_kind = "local"
    monkeypatch.setattr(
        agent,
        "_ollama_chat",
        lambda messages: (
            '{"action":"launch","content":"Helix-Codex",'
            '"reply":"Launching Helix codex now."}'
        ),
    )
    monkeypatch.setattr(
        launchables, "launch", lambda item, terminal=None: (True, "started index.html")
    )
    reply = agent.process_command("launch Helix codex app")
    assert not reply.startswith("🤖")
    assert "Helix-Codex" in reply
    assert "started index.html" in reply


def test_launch_is_deterministic_before_the_model(
    workspace, offline_agent, monkeypatch
):
    """A launch request must never depend on the model's mood."""
    agent = offline_agent
    agent.llm_available = True
    agent.model_kind = "local"
    calls = []
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages: calls.append(1) or "{}")

    prime = workspace / "Helix-Prime"
    prime.mkdir()
    (prime / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (prime / "index.html").write_text("<html>prime</html>")

    reply = agent.process_command("launch helix")
    assert reply.startswith("Which one?")
    assert calls == []  # handled before any model call
