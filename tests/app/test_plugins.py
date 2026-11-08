"""The plugin registry: defaults, toggles, presets, prompt and live gating.

These prove the Settings switches are real: turning a plugin off removes its
actions from the model prompt and makes the agent refuse that action instead of
silently doing it anyway.
"""

from __future__ import annotations

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app.plugins import PLUGINS, PluginRegistry
from sigmahelix.core.config import load_settings


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    return agent_module.Agent()


def test_one_persona_with_every_capability():
    registry = PluginRegistry(persist=False)
    assert registry.enabled_ids() == {p.id for p in PLUGINS}
    assert registry.is_enabled("core")
    assert registry.is_enabled("youtube")


def test_toggle_persists_to_config():
    registry = PluginRegistry(persist=True)
    assert registry.is_enabled("web")
    registry.set_enabled("web", False)
    assert not registry.is_enabled("web")
    assert "web" not in load_settings().plugins_enabled

    reloaded = PluginRegistry(persist=False)
    assert not reloaded.is_enabled("web")


def test_cannot_disable_always_on():
    registry = PluginRegistry(persist=False)
    with pytest.raises(ValueError):
        registry.set_enabled("core", False)


def test_unknown_plugin_rejected():
    registry = PluginRegistry(persist=False)
    with pytest.raises(ValueError):
        registry.set_enabled("teleport", True)
    with pytest.raises(ValueError):
        registry.apply_preset("nope")


def test_preset_applies_exact_set():
    registry = PluginRegistry(persist=False)
    registry.apply_preset("minimal")
    assert registry.enabled_ids() == {"core"}

    registry.apply_preset("coding")
    enabled = registry.enabled_ids()
    assert {"core", "projects", "files"} <= enabled
    assert "calendar" not in enabled


def test_prompt_block_lists_only_enabled_actions():
    registry = PluginRegistry(persist=False)
    registry.set_enabled("web", False)
    block = registry.prompt_block()
    assert "fetch_url" not in block
    assert "assess_projects" in block
    assert "Turned off" in block and "Web access" in block


def test_gate_blocks_disabled_action():
    registry = PluginRegistry(persist=False)
    assert registry.gate("fetch_url") is None
    registry.set_enabled("web", False)
    message = registry.gate("fetch_url")
    assert message is not None
    assert "turned off" in message.lower()
    # Unknown actions are not ours to block.
    assert registry.gate("made_up_action") is None


def test_disabling_projects_changes_agent_behaviour(offline_agent):
    agent = offline_agent
    live = agent.process_command("scan my projects")
    assert "turned off" not in live.lower()

    agent.plugins.set_enabled("projects", False)
    blocked = agent.process_command("scan my projects")
    assert "turned off" in blocked.lower()

    agent.plugins.set_enabled("projects", True)
    restored = agent.process_command("scan my projects")
    assert "turned off" not in restored.lower()


def test_disabling_web_blocks_url_reads(offline_agent):
    agent = offline_agent
    agent.plugins.set_enabled("web", False)
    out = agent.process_command("read https://example.com")
    assert "turned off" in out.lower()


def test_disabled_actions_absent_from_system_prompt(offline_agent):
    agent = offline_agent
    agent.plugins.set_enabled("documents", False)
    prompt = agent.system_prompt()
    assert "create_document" not in prompt
    assert "assess_projects" in prompt


def test_help_reflects_live_plugins(offline_agent):
    agent = offline_agent
    agent.plugins.apply_preset("minimal")
    text = agent.process_command("help")
    assert "Core persona" in text
    assert "fetch_url" not in text
    assert "Turned off:" in text

    agent.plugins.apply_preset("tommy")
    text = agent.process_command("help")
    assert "fetch_url" in text


def test_offline_keyword_routes_are_gated(offline_agent):
    """The fast keyword path must respect the registry, not bypass it."""
    agent = offline_agent
    agent.plugins.set_enabled("tasks", False)
    assert (
        "turned off"
        in agent.process_command("add a task to call the bank tomorrow").lower()
    )

    agent.plugins.set_enabled("notes", False)
    assert (
        "turned off"
        in agent.process_command("create note the client prefers email").lower()
    )

    agent.plugins.set_enabled("calendar", False)
    assert "turned off" in agent.process_command("what is on today").lower()
