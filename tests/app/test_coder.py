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


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def _scripted_cloud(agent, replies):
    """Make the cloud backend return the given JSON payloads in order."""
    calls: list[str] = []

    def fake_cloud(messages):
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
    assert any(step.startswith("edit_file") for step in steps)


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
