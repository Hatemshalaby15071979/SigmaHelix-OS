"""The cloud loop: truncation is retried, raw JSON is never shown, and a
claim without a tool result is never presented as done.

All tests run against a fake model — no network, no real projects.
"""

from __future__ import annotations

import json

import pytest

from sigmahelix.app import agent as agent_module


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
        "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
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


class ScriptedCloud:
    """A fake cloud backend with truncation control and budget capture."""

    def __init__(self, agent, replies, truncate_first=False):
        self.agent = agent
        self.replies = list(replies)
        self.truncate_first = truncate_first
        self.calls: list[dict] = []

    def __call__(self, messages, max_tokens=None):
        index = min(len(self.calls), len(self.replies) - 1)
        self.calls.append({"max_tokens": max_tokens})
        payload = self.replies[index]
        if self.truncate_first and len(self.calls) == 1:
            self.agent.last_trace["truncated"] = True
            self.agent.last_trace["finish_reason"] = "length"
            return payload, None
        self.agent.last_trace["truncated"] = False
        self.agent.last_trace["finish_reason"] = "stop"
        return payload, None


def test_truncated_tool_call_is_retried_and_never_echoed(cloud_agent, workspace):
    """A half-written tool call is retried with a bigger budget, and the
    partial JSON never reaches the user."""
    partial = '{"action":"file_operations","content":"{\\"operation\\":\\"create'
    complete = json.dumps(
        {
            "action": "file_operations",
            "content": json.dumps(
                {
                    "operation": "create",
                    "path": "demo/notes.txt",
                    "content": "hello",
                }
            ),
            "reply": "",
        }
    )
    final = json.dumps(
        {
            "action": "final",
            "content": "",
            "reply": "Done — created demo/notes.txt.",
            "evidence": ["file_operations:demo/notes.txt"],
        }
    )
    fake = ScriptedCloud(cloud_agent, [partial, complete, final], truncate_first=True)
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent.process_command("create a notes file in demo")

    # retried once, then completed, then finished
    assert len(fake.calls) == 3
    # the file was really created
    assert (workspace / "demo" / "notes.txt").read_text() == "hello"
    # the raw partial JSON was never shown
    assert '{"action"' not in reply
    assert "created" in reply.lower()


def test_truncated_heavy_action_gets_the_heavy_budget(cloud_agent):
    """file_operations/edit_file/run_command/audit_repo retries use 8192."""
    partial = '{"action":"file_operations","content":"{\\"operation'
    final = json.dumps(
        {"action": "final", "content": "", "reply": "Nothing was executed."}
    )
    fake = ScriptedCloud(cloud_agent, [partial, final], truncate_first=True)
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    cloud_agent.process_command("write a big file")

    assert fake.calls[1]["max_tokens"] == 8192


def test_double_truncation_reports_instead_of_guessing(cloud_agent):
    partial = '{"action":"file_operations","content":"{\\"operation'
    fake = ScriptedCloud(cloud_agent, [partial, partial], truncate_first=True)

    # every call is "truncated"
    def always_truncated(messages, max_tokens=None):
        fake.calls.append({"max_tokens": max_tokens})
        cloud_agent.last_trace["truncated"] = True
        return partial, None

    cloud_agent._cloud_chat = always_truncated  # type: ignore[method-assign]

    reply = cloud_agent.process_command("write a big file")

    assert "cut off" in reply
    assert '{"action"' not in reply


def test_malformed_tool_call_is_never_echoed(cloud_agent):
    """Action-looking text that does not parse is an error, not a reply."""
    broken = '{"action": "file_operations", "content": "not valid json at all'
    final = json.dumps(
        {"action": "final", "content": "", "reply": "I could not build the call."}
    )
    fake = ScriptedCloud(cloud_agent, [broken, broken, final])
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent.process_command("create a file")

    assert "malformed" in reply
    assert '{"action"' not in reply


def test_unverified_claim_is_blocked(cloud_agent):
    """'Fixed it, tests pass' with zero tool calls gets one correction round,
    then a visible unverified-claim flag."""
    final = json.dumps(
        {
            "action": "final",
            "content": "",
            "reply": "Fixed the demo project, tests pass.",
        }
    )
    fake = ScriptedCloud(cloud_agent, [final, final])
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent.process_command("fix the demo project")

    # one correction round, then the flagged answer
    assert len(fake.calls) == 2
    assert "unverified claim" in reply


def test_verified_claim_passes_cleanly(cloud_agent, workspace):
    replies = [
        json.dumps(
            {"action": "run_tests", "content": "demo", "reply": "", "plan": "prove it"}
        ),
        json.dumps(
            {
                "action": "final",
                "content": "",
                "reply": "Tests pass for demo.",
                "evidence": ["run_tests:exit=0"],
            }
        ),
    ]
    fake = ScriptedCloud(cloud_agent, replies)
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent._agent_loop(
        cloud_agent._build_messages("verify the demo suite"), "verify the demo suite"
    )

    assert "unverified claim" not in reply
    steps = cloud_agent.last_trace.get("steps") or []
    assert steps[0]["action"] == "run_tests"
    assert steps[0]["plan"] == "prove it"
    assert cloud_agent.last_trace.get("evidence") == ["run_tests:exit=0"]


def test_steps_are_recorded_with_plan_and_args(cloud_agent, workspace):
    replies = [
        json.dumps(
            {
                "action": "audit_repo",
                "content": "demo",
                "reply": "",
                "plan": "see what the project is missing",
            }
        ),
        json.dumps(
            {"action": "final", "content": "", "reply": "demo has tests and a readme."}
        ),
    ]
    fake = ScriptedCloud(cloud_agent, replies)
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    cloud_agent._agent_loop(cloud_agent._build_messages("inspect demo"), "inspect demo")

    steps = cloud_agent.last_trace.get("steps") or []
    assert len(steps) == 1
    step = steps[0]
    assert step["seq"] == 1
    assert step["action"] == "audit_repo"
    assert step["plan"] == "see what the project is missing"
    assert step["args"] == "demo"
    assert step["ok"] is True
    assert "summary" in step
    assert step["duration_ms"] >= 0
    assert cloud_agent.last_trace.get("plans") == ["see what the project is missing"]
    assert cloud_agent.last_trace.get("truncated") is False
    assert cloud_agent.last_trace.get("finish_reason") == "stop"


def test_final_with_empty_reply_labels_tool_output_not_answer(cloud_agent, workspace):
    """A final step with no reply must not pass the raw tool observation off as
    the model's answer, and must not store it as the model's own words."""
    tool_call = json.dumps(
        {
            "action": "file_operations",
            "content": json.dumps(
                {"operation": "create", "path": "demo/probe.txt", "content": "hi"}
            ),
            "reply": "",
        }
    )
    final_empty = json.dumps({"action": "final", "content": "", "reply": ""})
    fake = ScriptedCloud(cloud_agent, [tool_call, final_empty])
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent.process_command("create a probe file in demo")

    assert "could not produce an answer" in reply.lower()
    assert "last tool result" in reply.lower()
    # The observation is labelled, not presented as the model's own answer.
    assert cloud_agent.history[-1] == (
        "assistant",
        "I could not produce an answer this turn (no reply).",
    )
    assert "Created" not in cloud_agent.history[-1][1]


def test_step_exhaustion_labels_tool_output_and_never_stores_it(cloud_agent, workspace):
    """When the step budget runs out, the last observation is labelled as a tool
    result, never returned bare or remembered as the model's reply."""
    tool_call = json.dumps(
        {
            "action": "file_operations",
            "content": json.dumps(
                {"operation": "create", "path": "demo/loop.txt", "content": "x"}
            ),
            "reply": "",
        }
    )
    fake = ScriptedCloud(cloud_agent, [tool_call])  # repeats for every step
    cloud_agent._cloud_chat = fake  # type: ignore[method-assign]

    reply = cloud_agent.process_command("keep going forever")

    assert "ran out of steps" in reply.lower()
    assert "last tool result" in reply.lower()
    assert cloud_agent.history[-1] == (
        "assistant",
        "I ran out of steps before reaching an answer.",
    )
