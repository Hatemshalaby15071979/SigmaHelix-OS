"""Skills must reach every model, local or cloud, on every turn.

The failure this file guards against: skills are discovered and stored but the
prompt that actually reaches the model never contains them. So the tests look
at the payload on the wire, not at the library in isolation.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from sigmahelix.app import models
from sigmahelix.app.agent import Agent
from sigmahelix.app.skills import SkillError, SkillLibrary, parse_skill

EXPECTED = {
    "hatem-specific",
    "i-have-adhd",
    "frontend-webapp",
    "ui-interaction-design",
    "devops-engineering",
    "prompt-engineering",
}


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(Agent, "_check_llm", lambda self, timeout=2.0: False)
    return Agent()


# --------------------------------------------------------------------------
# discovery and composition
# --------------------------------------------------------------------------
def test_discovers_every_shipped_skill():
    library = SkillLibrary()
    names = {skill.name for skill in library.skills(refresh=True)}
    assert names >= EXPECTED, f"missing: {EXPECTED - names}"


def test_personal_skills_load_first():
    library = SkillLibrary()
    sources = [skill.source for skill in library.skills(refresh=True)]
    assert sources[0] == "personal"
    assert sources.index("personal") < sources.index("builtin")


def test_composition_contains_every_skill_and_token():
    library = SkillLibrary()
    composition = library.compose("BASE PROMPT")
    assert composition.prompt.startswith("BASE PROMPT")
    assert not composition.truncated
    for skill in library.skills():
        assert skill.name in composition.prompt
        assert skill.token in composition.prompt


def test_tokens_are_stable_and_distinct():
    library = SkillLibrary()
    tokens = [skill.token for skill in library.skills(refresh=True)]
    assert len(tokens) == len(set(tokens))
    again = [skill.token for skill in SkillLibrary().skills(refresh=True)]
    assert tokens == again


def test_budget_truncation_is_reported_not_hidden(tmp_path):
    (tmp_path / "big.md").write_text(
        "---\nname: big\ndescription: big\n---\n" + ("x" * 5000),
        encoding="utf-8",
    )
    library = SkillLibrary(roots={"user": tmp_path}, budget=1000)
    composition = library.compose("base")
    assert "big" in composition.truncated
    assert "big" not in composition.prompt


def test_user_skill_overrides_builtin(tmp_path):
    (tmp_path / "devops-engineering.md").write_text(
        "---\nname: devops-engineering\ndescription: mine\n---\nmine wins",
        encoding="utf-8",
    )
    library = SkillLibrary(roots={"user": tmp_path})
    skill = library.get("devops-engineering")
    assert skill is not None and skill.body == "mine wins"


def test_bad_frontmatter_is_reported_not_fatal(tmp_path):
    (tmp_path / "broken.md").write_text("no frontmatter here", encoding="utf-8")
    (tmp_path / "good.md").write_text(
        "---\nname: good\ndescription: fine\n---\nbody", encoding="utf-8"
    )
    library = SkillLibrary(roots={"user": tmp_path})
    names = [skill.name for skill in library.skills(refresh=True)]
    assert names == ["good"]
    assert any("broken.md" in error for error in library.errors)


def test_parse_skill_rejects_empty_body(tmp_path):
    with pytest.raises(SkillError):
        parse_skill("---\nname: x\n---\n", tmp_path / "x.md", "user", 30)


# --------------------------------------------------------------------------
# the payload on the wire
# --------------------------------------------------------------------------
def test_local_payload_carries_every_skill(offline_agent, monkeypatch):
    captured: dict = {}

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data)
        return FakeResponse({"message": {"content": "ok"}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    offline_agent.model_name = "test-model"
    offline_agent._ollama_chat(offline_agent._build_messages("hi"))

    system = captured["body"]["messages"][0]
    assert system["role"] == "system"
    for skill in offline_agent.skills.skills():
        assert skill.token in system["content"], f"{skill.name} missing from payload"
    assert "You are Tommy" in system["content"]


def test_cloud_payload_carries_every_skill(offline_agent, monkeypatch):
    captured: dict = {}

    def fake_cloud(
        provider,
        model,
        key,
        system,
        timeout=30,
        messages=None,
        trace=None,
        max_tokens=4096,
    ):
        captured["messages"] = messages
        return "ok", None

    monkeypatch.setattr(models, "active_cloud_providers", lambda: ["openai"])
    monkeypatch.setattr(models, "load_api_keys", lambda: {"openai": "sk-test"})
    monkeypatch.setattr(models, "default_cloud_model", lambda provider: "gpt-test")
    monkeypatch.setattr(models, "provider_for_model", lambda model: "openai")
    monkeypatch.setattr(models, "try_cloud_query", fake_cloud)

    messages = offline_agent._build_messages("hello")
    reply, error = offline_agent._cloud_chat(messages)

    assert reply == "ok" and error is None
    system = captured["messages"][0]["content"]
    for skill in offline_agent.skills.skills():
        assert skill.token in system, f"{skill.name} missing from cloud payload"


def test_switching_provider_does_not_change_the_system_prompt(offline_agent):
    """The persona and skills are provider-independent; the work loop is not.

    Cloud mode runs a multi-step tool loop, so only cloud gets the loop
    contract — everything else about the prompt stays identical.
    """
    prompt_local = offline_agent.system_prompt()
    offline_agent.model_kind = "cloud"
    offline_agent.cloud_provider = "openai"
    prompt_cloud = offline_agent.system_prompt()
    assert "WORK LOOP" not in prompt_local
    assert "WORK LOOP" in prompt_cloud
    assert prompt_cloud.replace(offline_agent.loop_block(), "").strip() == (
        prompt_local.strip()
    )


def test_enabled_capabilities_join_the_prompt(offline_agent):
    before = offline_agent.system_prompt()
    offline_agent.injected_skills["web_search"] = {"description": "search the web"}
    after = offline_agent.system_prompt()
    assert "ENABLED CAPABILITIES" in after
    assert "web_search" in after
    assert len(after) > len(before)


def test_reload_skills_picks_up_a_new_file(offline_agent, tmp_path, monkeypatch):
    from sigmahelix.app import skills as skills_module

    monkeypatch.setattr(skills_module, "user_skills_dir", lambda: tmp_path)
    (tmp_path / "extra.md").write_text(
        "---\nname: extra\ndescription: added later\n---\nnew rule",
        encoding="utf-8",
    )
    offline_agent.skills.roots["user"] = tmp_path
    assert offline_agent.reload_skills() >= len(EXPECTED) + 1
    assert "new rule" in offline_agent.system_prompt()
