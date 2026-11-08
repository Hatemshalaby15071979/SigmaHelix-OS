"""Question-driven tasks and Tommy's coding workspace.

These prove the agent can create tasks with sub-questions, add/answer/reopen
them, execute a task (answer its open questions and complete it), and build a
runnable project instead of refusing.
"""

from __future__ import annotations

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app.launchables import detect_launchables
from sigmahelix.app.managers import ProjectsManager, TasksManager


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    return agent_module.Agent()


def test_create_task_with_questions():
    mgr = TasksManager()
    out = mgr.create_task_with_questions("Ship v1", ["Does it build?", "Is it tested?"])
    assert "Ship v1" in out
    task = mgr.find(1)
    assert task["name"] == "Ship v1"
    assert [q["question"] for q in task["questions"]] == [
        "Does it build?",
        "Is it tested?",
    ]
    assert task["questions_total"] == 2
    assert task["questions_answered"] == 0
    assert task["ready"] is False


def test_add_answer_show_reopen():
    mgr = TasksManager()
    mgr.create_task_with_questions("Audit", ["Scope?"])

    assert "Question" in mgr.add_question("add question to task 1: Evidence?")
    assert len(mgr.find(1)["questions"]) == 2

    assert "answered" in mgr.answer_question(
        "answer question 1 on task 1: the whole repo"
    )
    question = next(q for q in mgr.find(1)["questions"] if q["id"] == 1)
    assert question["status"] == "answered"
    assert question["answer"] == "the whole repo"

    listing = mgr.show_questions("show questions for task 1")
    assert "Scope?" in listing and "the whole repo" in listing

    assert "reopened" in mgr.reopen_question("reopen question 1 on task 1")
    question = next(q for q in mgr.find(1)["questions"] if q["id"] == 1)
    assert question["status"] == "open"


def test_completion_blocked_until_questions_answered():
    mgr = TasksManager()
    mgr.create_task_with_questions("Gate", ["Done?"])

    blocked = mgr.complete_task("complete task 1")
    assert "unanswered" in blocked.lower()
    assert mgr.find(1)["completed"] is False

    mgr.answer_question("answer question 1 on task 1: yes")
    assert "completed" in mgr.complete_task("complete task 1").lower()
    assert mgr.find(1)["completed"] is True


def test_agent_executes_a_task_by_answering(offline_agent, monkeypatch):
    agent = offline_agent
    agent.tasks.create_task_with_questions(
        "Plan launch", ["Who is the owner?", "What is the date?"]
    )
    monkeypatch.setattr(
        agent, "_ask_text", lambda prompt, timeout=60: "answered: " + prompt[:20]
    )

    out = agent.process_command("execute task 1")
    assert "answered" in out.lower()
    task = agent.tasks.find(1)
    assert task["ready"] is True
    assert task["completed"] is True


def test_agent_deterministic_question_commands(offline_agent):
    agent = offline_agent
    agent.process_command("create task audit")
    agent.process_command("add question to task 1: Scope?")
    agent.process_command("answer question 1 on task 1: the repo")

    task = agent.tasks.find(1)
    assert task["questions"][0]["status"] == "answered"
    assert task["questions"][0]["answer"] == "the repo"


def test_create_project_scaffolds_runnable_webapp(tmp_path):
    mgr = ProjectsManager()
    projects = tmp_path / "cloned_repos"
    projects.mkdir()
    mgr.projects_dir = str(projects)

    result = mgr.create_project("Todo App")
    assert result["ok"] is True
    target = projects / "todo-app"
    for name in ("index.html", "style.css", "app.js"):
        assert (target / name).is_file()
    assert any(link.kind == "dashboard" for link in detect_launchables(target))


def test_agent_builds_instead_of_refusing(offline_agent, tmp_path):
    agent = offline_agent
    projects = tmp_path / "cloned_repos"
    projects.mkdir()
    agent.projects.projects_dir = str(projects)

    out = agent.process_command("create a todo webapp")
    assert "Built" in out
    assert (projects / "todo").is_dir()
    assert (projects / "todo" / "index.html").is_file()
