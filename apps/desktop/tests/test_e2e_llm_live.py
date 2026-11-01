"""LIVE LLM E2E: real Ollama chat round-trip tests.

Run manually:  pytest tests/test_e2e_llm_live.py -v
These are skipped automatically when the server or a model is missing.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from agent import OLLAMA_HOSTS, OLLAMA_MODEL

import agent as agent_mod


def _server_up() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_HOSTS[0]}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _models() -> list:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOSTS[0]}/api/tags", timeout=2) as r:
            return [m["name"] for m in json.loads(r.read())["models"]]
    except Exception:
        return []


SERVER_UP = _server_up()

requires_ollama = pytest.mark.skipif(
    not SERVER_UP or OLLAMA_MODEL not in _models(),
    reason=f"Ollama/{OLLAMA_MODEL} not reachable at {OLLAMA_HOSTS}")


@pytest.fixture
def live_agent():
    a = agent_mod.Agent()
    assert a.llm_available, "Agent did not detect live Ollama"
    return a


@requires_ollama
def test_llm_natural_greeting(live_agent):
    """User speaks naturally; agent asks LLM; reply must look human."""
    out = live_agent.process_command("hey there, how are you today?")
    assert isinstance(out, str) and len(out) > 5
    assert "🤖" in out, f"expected LLM reply path, got: {out!r}"


@requires_ollama
def test_llm_intent_create_task(live_agent):
    """Natural 'I need to ship X' must become a real task row."""
    out = live_agent.process_command("remind me to prepare the QBR deck for Friday")
    tasks = live_agent.tasks.list_tasks("list")
    assert "prepare the QBR deck" in tasks.lower() or "qbr deck" in out.lower(), \
        f"LLM intent parse failed. reply={out!r}\ntasks={tasks!r}"


@requires_ollama
def test_llm_intent_schedule(live_agent):
    out = live_agent.process_command("what is on my plate today?")
    assert "2026" in out or "task" in out.lower() or "🤖" in out


@requires_ollama
def test_llm_intent_note(live_agent):
    live_agent.process_command("write a note: client prefers email over calls")
    notes = live_agent.notes.list_notes("view")
    assert "client prefers email" in notes.lower()


@requires_ollama
def test_llm_exceptions_dont_crash(live_agent):
    out = live_agent.process_command("क�fjdkls 73829 random garbage 💩")
    assert isinstance(out, str)  # survived garbage gracefully
