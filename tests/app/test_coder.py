"""The coding agent: real commands, real tests, real edits, and the loop.

Every test runs against a sandbox project in a temporary directory — never the
user's real projects.
"""

from __future__ import annotations

import json

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app import coder


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A sandbox workspace with one small Python project."""
    root = tmp_path / "cloned_repos"
    root.mkdir()
    project = root / "demo"
    (project / "src").mkdir(parents=True)
    (project / "tests").mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (project / "README.md").write_text("# demo\n")
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (project / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 4\n"
    )
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))
    monkeypatch.setattr("sigmahelix.app.paths._PROJECTS_DIR_CACHE", root)
    return root


@pytest.fixture
def cloud_agent(workspace, monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = True
    return agent


# ---------------------------------------------------------------------------
# coder tools
# ---------------------------------------------------------------------------


def test_run_command_reports_real_output(workspace):
    result = coder.run_command(workspace, ["python3", "-c", "print('hello there')"])
    assert result.ok is True
    assert result.exit_code == 0
    assert "hello there" in result.stdout


def test_run_command_reports_failures(workspace):
    result = coder.run_command(workspace, ["python3", "-c", "raise SystemExit(3)"])
    assert result.ok is False
    assert result.exit_code == 3


def test_run_command_refuses_destructive_commands(workspace):
    result = coder.run_command(workspace, ["rm", "-rf", "/"])
    assert result.ok is False
    assert "refused" in (result.error or "")


def test_run_command_cannot_leave_the_workspace(workspace):
    result = coder.run_command(workspace, ["ls"], cwd="../../..")
    assert result.ok is False
    assert "refused" in (result.error or "")


def test_run_command_times_out(workspace):
    result = coder.run_command(
        workspace, ["python3", "-c", "import time; time.sleep(5)"], timeout=1
    )
    assert result.ok is False
    assert result.timed_out is True


def test_run_tests_detects_pytest_and_reports_failures(workspace):
    outcome = coder.run_tests(workspace, workspace / "demo")
    assert outcome["runner"] == "pytest"
    assert outcome["exit_code"] != 0
    assert any("FAILED" in line or "assert" in line for line in outcome["failures"])


def test_run_tests_passes_after_a_fix(workspace):
    (workspace / "demo" / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n"
    )
    (workspace / "demo" / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    outcome = coder.run_tests(workspace, workspace / "demo")
    assert outcome["ok"] is True, outcome["stdout"]


def test_audit_repo_reports_structure_and_gaps(workspace):
    audit = coder.audit_repo(workspace / "demo")
    assert audit["project"] == "demo"
    assert audit["readme"] == "README.md"
    assert audit["test_files"] >= 1
    assert audit["test_runner"]["runner"] == "pytest"
    assert "no CI workflow" in audit["gaps"]
    assert "no environment template (.env.example)" in audit["gaps"]


def test_edit_file_replaces_exact_text(workspace):
    outcome = coder.edit_file(
        workspace, "demo/src/calc.py", "return a + b", "return a + b + 1"
    )
    assert outcome["ok"] is True
    assert "a + b + 1" in (workspace / "demo" / "src" / "calc.py").read_text()


def test_edit_file_refuses_missing_and_ambiguous_text(workspace):
    missing = coder.edit_file(workspace, "demo/src/calc.py", "nothing here", "x")
    assert missing["ok"] is False
    assert "not found" in missing["error"]

    ambiguous = coder.edit_file(workspace, "demo/src/calc.py", "a", "b")
    assert ambiguous["ok"] is False
    assert "appears" in ambiguous["error"]


def test_find_requirements_prefers_requirements_txt(workspace):
    (workspace / "demo" / "requirements.txt").write_text("pywebview\n")
    (workspace / "demo" / "pyproject.toml").write_text("[project]\n")
    found = coder.find_requirements(workspace / "demo")
    assert found is not None
    assert found.name == "requirements.txt"


def test_install_requirements_reports_missing_manifest(workspace):
    empty = workspace / "bare"
    empty.mkdir()
    info = coder.install_project_requirements(workspace, empty)
    assert info["ok"] is False
    assert "no requirements file" in info["error"]


# ---------------------------------------------------------------------------
# agent wiring
# ---------------------------------------------------------------------------


def test_agent_dispatches_the_coding_actions(cloud_agent):
    reply = cloud_agent.process_command("audit the demo project")
    assert "AUDIT" in reply
    assert "demo" in reply

    reply = cloud_agent.process_command("run the tests for demo")
    assert "demo" in reply
    assert "pytest" in reply


def test_agent_reports_a_missing_project(cloud_agent):
    reply = cloud_agent.process_command("audit the teleporter project")
    assert "No project matches" in reply


def test_launch_remediates_missing_runtime_in_cloud(workspace, monkeypatch):
    """Cloud mode installs the missing runtime and retries the launch."""
    from sigmahelix.app.launchables import Launchable

    project = workspace / "demo"

    desktop = Launchable(
        project="demo",
        kind="desktop",
        label="python desktop.py",
        path=project / "desktop.py",
        command=("python3", "desktop.py"),
        requires=("webview",),
    )

    calls: list[str] = []

    def fake_launch(item, terminal=None):
        calls.append("launch")
        if len(calls) == 1:
            return (
                False,
                "webview is not installed for python3 — install the project requirements first",
            )
        return (True, "started python desktop.py")

    monkeypatch.setattr(
        "sigmahelix.app.launchables.detect_launchables",
        lambda p: [desktop],
    )
    monkeypatch.setattr("sigmahelix.app.launchables.launch", fake_launch)
    monkeypatch.setattr(
        "sigmahelix.app.coder.install_project_requirements",
        lambda root, proj, timeout=600: {
            "ok": True,
            "venv_py": str(project / ".venv" / "bin" / "python"),
            "req": "requirements.txt",
            "steps": [],
        },
    )

    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = False  # launch is deterministic; no model needed

    reply = agent.process_command("run the demo app")
    assert "installed requirements" in reply
    assert "started" in reply
    assert calls == ["launch", "launch"]  # failed once, retried after install


def test_agent_installs_requirements_and_runs(workspace, monkeypatch):
    """'install <project> requirements and run it' installs, then launches."""
    from sigmahelix.app.launchables import Launchable

    project = workspace / "demo"
    desktop = Launchable(
        project="demo",
        kind="desktop",
        label="python desktop.py",
        path=project / "desktop.py",
        command=("python3", "desktop.py"),
    )
    monkeypatch.setattr(
        "sigmahelix.app.launchables.detect_launchables", lambda p: [desktop]
    )
    monkeypatch.setattr(
        "sigmahelix.app.launchables.launch",
        lambda item, terminal=None: (True, "started python desktop.py"),
    )
    monkeypatch.setattr(
        "sigmahelix.app.coder.install_project_requirements",
        lambda root, proj, timeout=600: {
            "ok": True,
            "venv_py": str(project / ".venv" / "bin" / "python"),
            "req": "requirements.txt",
            "steps": [],
        },
    )

    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = False

    reply = agent.process_command(
        "install the demo project requirements and then run it"
    )
    assert "installed" in reply
    assert "started" in reply


def test_agent_installs_requirements_without_running(workspace, monkeypatch):
    monkeypatch.setattr(
        "sigmahelix.app.coder.install_project_requirements",
        lambda root, proj, timeout=600: {
            "ok": True,
            "venv_py": str(workspace / "demo" / ".venv" / "bin" / "python"),
            "req": "requirements.txt",
            "steps": [],
        },
    )
    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = False

    reply = agent.process_command("install demo requirements")
    assert "installed" in reply
    assert "started" not in reply


def test_install_route_ignores_questions(workspace, monkeypatch):
    """'how do I install packages?' must not become a project install."""
    called: list[str] = []
    monkeypatch.setattr(
        "sigmahelix.app.coder.install_project_requirements",
        lambda *a, **k: called.append("install") or {"ok": True},
    )
    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = False

    agent.process_command("how do I install python packages?")
    assert called == []


def test_install_route_asks_for_project_when_missing(workspace, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(
        "sigmahelix.app.coder.install_project_requirements",
        lambda *a, **k: called.append("install") or {"ok": True},
    )
    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    agent.llm_available = False

    reply = agent.process_command("install requirements")
    assert called == []
    assert "Which project" in reply


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def _scripted_cloud(agent, replies):
    """Make the cloud backend return the given JSON payloads in order."""
    calls: list[str] = []

    def fake_cloud(messages, max_tokens=None):
        calls.append(messages[-1]["content"][:120])
        payload = replies[min(len(calls) - 1, len(replies) - 1)]
        return payload, None

    agent._cloud_chat = fake_cloud  # type: ignore[method-assign]
    return calls


def test_loop_runs_tools_until_the_model_answers(cloud_agent, workspace):
    replies = [
        json.dumps(
            {
                "action": "audit_repo",
                "content": "demo",
                "reply": "",
            }
        ),
        json.dumps(
            {
                "action": "run_tests",
                "content": "demo",
                "reply": "",
            }
        ),
        json.dumps(
            {
                "action": "edit_file",
                "content": json.dumps(
                    {
                        "path": "demo/src/calc.py",
                        "old": "return a + b",
                        "new": "return a + b + 1",
                    }
                ),
                "reply": "",
            }
        ),
        json.dumps(
            {
                "action": "run_tests",
                "content": "demo",
                "reply": "",
            }
        ),
        json.dumps(
            {
                "action": "final",
                "content": "",
                "reply": "Fixed the calculation and the suite passes now.",
            }
        ),
    ]
    calls = _scripted_cloud(cloud_agent, replies)
    reply = cloud_agent.process_command("fix the demo project so its tests pass")

    assert "Fixed the calculation" in reply
    assert len(calls) == 5
    # the edit really happened
    assert "a + b + 1" in (workspace / "demo" / "src" / "calc.py").read_text()
    # and the loop reported its steps
    steps = cloud_agent.last_trace.get("steps") or []
    assert any(step["action"] == "edit_file" for step in steps)


def test_loop_is_off_outside_cloud_mode(cloud_agent, workspace):
    cloud_agent.model_kind = "local"
    calls = _scripted_cloud(
        cloud_agent,
        [json.dumps({"action": "audit_repo", "content": "demo", "reply": ""})],
    )
    cloud_agent.process_command("fix the demo project")
    # local mode keeps the single-shot behaviour: one model call, no loop
    assert len(calls) <= 1


def test_loop_prompt_only_exists_in_cloud_mode(cloud_agent):
    assert "WORK LOOP" in cloud_agent.system_prompt()
    cloud_agent.model_kind = "local"
    assert "WORK LOOP" not in cloud_agent.system_prompt()


def test_system_prompt_grounds_the_workspace_root(workspace):
    """The model must know its real workspace root, so it never refuses it."""
    from sigmahelix.app.paths import projects_dir

    agent = agent_module.Agent()
    prompt = agent.system_prompt()
    assert str(projects_dir()) in prompt
    assert "RESOLVE, DON'T ASK" in prompt
    assert "127.0.0.1" in prompt  # localhost is a link, not a fetch target


def test_loop_block_repeats_the_workspace_grounding(workspace):
    agent = agent_module.Agent()
    agent.model_kind = "cloud"
    block = agent.loop_block()
    assert "workspace root" in block.lower()
    assert "outside my workspace" in block
