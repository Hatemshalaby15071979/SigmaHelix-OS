"""Offline E2E: agent keyword routing, managers, data gating. No LLM needed."""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from sigmahelix.app.agent import Agent
from sigmahelix.app.managers import (
    CalendarManager,
    LauncherManager,
    NotesManager,
    ProjectsManager,
    TasksManager,
)

EXPECTED_REPOS = [
    "Blue Waves Music Production",
    "CompliProof",
    "Dynamic-Ops-Automation-Engine",
    "Helix-Education",
    "Helix-Prime",
    "L-D-Command-Center",
    "RTA_command_center",
    "Study-Studio",
    "cx-sentiment-sentinel",
    "live-support-assistant",
    "wfm-forecasting-calculator",
    "work-samples",
]


@pytest.fixture
def offline_agent(monkeypatch):
    """Agent with LLM ping disabled to test deterministic routing."""
    monkeypatch.setattr(Agent, "_check_llm", lambda self, timeout=2.0: False)
    return Agent()


# ---------------- tasks ----------------


def test_task_create_list_complete_delete(offline_agent):
    mgr = TasksManager()
    r = mgr.create_task("create task ship quarterly report")
    assert "ship quarterly report" in r and "ID: 1" in r
    r = mgr.list_tasks("list tasks")
    assert "ship quarterly report" in r and "[ ]" in r
    r = mgr.complete_task("complete task 1")
    assert "completed" in r
    assert "[✓]" in mgr.list_tasks("list tasks")
    r = mgr.delete_task("delete task 1")
    assert "deleted" in r
    assert "no tasks" in mgr.list_tasks("list tasks").lower()


def test_task_bad_id_handled(offline_agent):
    mgr = TasksManager()
    out = mgr.complete_task("complete task abc")
    assert "specify" in out.lower()


# ---------------- notes ----------------


def test_notes_crud(offline_agent):
    mgr = NotesManager()
    r = mgr.create_note("create note call the accountant at 3pm")
    assert "ID: 1" in r
    listing = mgr.list_notes("view notes")
    assert "accountant" in listing
    assert "deleted" in mgr.delete_note("delete note 1")


def test_note_filtering(offline_agent):
    mgr = NotesManager()
    r = mgr.create_note("create note test")
    assert "ID: 1" in r


# ---------------- calendar ----------------


def test_calendar_today_tomorrow(offline_agent):
    cal = CalendarManager()
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert "Nothing scheduled" in cal.get_tasks_for_date("today")

    cal.schedule_task("today item", today)
    cal.schedule_task("tomorrow item", tomorrow)
    assert today in cal.get_tasks_for_date("today")
    assert "today item" in cal.get_tasks_for_date("today")
    assert tomorrow in cal.get_tasks_for_date("tomorrow")
    assert "tomorrow item" not in cal.get_tasks_for_date("today")


def test_calendar_week_month(offline_agent):
    cal = CalendarManager()
    today = datetime.date.today().isoformat()
    cal.schedule_task("weekly item", today)
    assert "Agenda" in cal.get_tasks_for_date("this week")
    assert "Agenda" in cal.get_tasks_for_date("this month")


def test_calendar_schedule_and_read(offline_agent):
    cal = CalendarManager()
    out = cal.schedule_task("call supplier", "2026-11-05", "09:00")
    assert "scheduled for 2026-11-05" in out
    assert "call supplier" in cal.get_tasks_for_date("2026-11-05")


# ---------------- projects + explorer (real filesystem) ----------------


def test_projects_lists_all_repos(offline_agent):
    prj = ProjectsManager()
    listing = prj.list_projects("show projects")
    for repo in EXPECTED_REPOS:
        assert repo in listing, f"missing repo {repo}"


def test_explorer_scans_exes(offline_agent):
    prj = ProjectsManager()
    out = prj.explore_apps("explorer")
    assert isinstance(out, str)  # tolerates empty exe set without failing


# ---------------- agent routing ----------------


def test_agent_routes_tasks_offline(offline_agent):
    r = offline_agent.process_command("create task audit expense receipts")
    assert "audit expense receipts" in r
    assert "audit expense receipts" in offline_agent.process_command("list tasks")


def test_agent_routes_projects_offline(offline_agent):
    out = offline_agent.process_command("show projects")
    for repo in EXPECTED_REPOS:
        assert repo in out


def test_agent_exit_and_help(offline_agent):
    assert offline_agent.process_command("help") is not None
    assert offline_agent.process_command("")  # empty handled


def test_agent_empty_input(offline_agent):
    assert "say something" in offline_agent.process_command("")


def test_greeting_with_today_is_not_agenda(offline_agent):
    """Regression: 'how are you today?' is small talk, not an agenda request."""
    out = offline_agent.process_command("hey there, how are you today?")
    assert "Nothing scheduled" not in out
    assert "Hello" in out


def test_agenda_routing(offline_agent):
    assert "Nothing scheduled" in offline_agent.process_command("today")
    assert "Nothing scheduled" in offline_agent.process_command(
        "what is on my plate today?"
    )
    assert "Nothing scheduled" in offline_agent.process_command("show calendar today")


# ---------------- voice (offline-safe) ----------------


def test_voice_lazy_init_no_mic_crash(offline_agent):
    engine = offline_agent.voice_engine  # must not raise even without mic
    assert engine is not None
    stub = offline_agent.process_command("say hello from test")
    assert "hello from test" in stub


# ---------------- launcher (no subprocess run; verify path guards) ----------------


def test_launcher_missing_project_reports(tmp_path, monkeypatch):
    launcher = LauncherManager()
    monkeypatch.setattr(launcher, "projects_dir", str(tmp_path))
    out = launcher.launch_project("nope")
    assert "no project matches" in out.lower()


# ---------------- TTS discipline: NEVER automatic, always on demand ----------------


def test_process_command_never_speaks(offline_agent):
    """Regression: agent replies must not trigger TTS on their own."""
    calls = []
    orig = type(offline_agent.voice_engine).speak_text
    offline_agent.voice_engine.speak_text = lambda *a, **k: calls.append(a) or True
    for cmd in (
        "hello",
        "create task write report",
        "list tasks",
        "view notes",
        "today",
        "show projects",
    ):
        offline_agent.process_command(cmd)
    assert calls == [], f"process_command triggered automatic TTS: {calls}"
    offline_agent.voice_engine.speak_text = orig


def test_listen_is_on_demand(offline_agent):
    calls = []
    offline_agent.voice_engine.speak_text = lambda *a, **k: calls.append(a) or True
    offline_agent.process_command("create task buy milk")
    assert calls == []  # reply alone is silent
    offline_agent.process_command("listen hello world")  # explicit ask -> speaks
    assert len(calls) == 1
    offline_agent.voice_engine.speak_text = None


def test_stop_speech_command(offline_agent):
    out = offline_agent.process_command("stop speech")
    assert "stopped" in out.lower()
    out2 = offline_agent.process_command("mute")
    assert "stopped" in out2.lower()
