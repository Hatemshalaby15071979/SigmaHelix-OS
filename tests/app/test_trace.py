"""The turn must report what the model thought and what it cost."""

from __future__ import annotations

import json
import urllib.request

import pytest

from sigmahelix.app import models
from sigmahelix.app.agent import Agent


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


def test_local_trace_records_thinking_and_tokens(offline_agent, monkeypatch):
    def fake_urlopen(request, timeout=0):
        return FakeResponse(
            {
                "message": {"content": "hello", "thinking": "the user greeted me"},
                "prompt_eval_count": 812,
                "eval_count": 43,
                "total_duration": 1_500_000_000,
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    offline_agent.model_name = "llama-test"
    offline_agent._ollama_chat(offline_agent._build_messages("hi"))

    trace = offline_agent.last_trace
    assert trace["provider"] == "local"
    assert trace["model"] == "llama-test"
    assert trace["thinking"] == "the user greeted me"
    assert trace["prompt_tokens"] == 812
    assert trace["completion_tokens"] == 43
    assert trace["total_tokens"] == 855
    assert trace["duration_ms"] == 1500


def test_local_trace_tolerates_a_model_without_thinking(offline_agent, monkeypatch):
    def fake_urlopen(request, timeout=0):
        return FakeResponse(
            {"message": {"content": "ok"}, "prompt_eval_count": 5, "eval_count": 1}
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    offline_agent._ollama_chat(offline_agent._build_messages("hi"))
    assert offline_agent.last_trace["thinking"] == ""
    assert offline_agent.last_trace["total_tokens"] == 6


def test_cloud_trace_records_usage_and_reasoning(offline_agent, monkeypatch):
    def fake_cloud(provider, model, key, system, timeout=30, messages=None, trace=None):
        if trace is not None:
            trace.update(
                provider=provider,
                model=model,
                thinking="weighed two options",
                prompt_tokens=1200,
                completion_tokens=80,
                total_tokens=1280,
                duration_ms=0,
            )
        return "answer", None

    monkeypatch.setattr(models, "active_cloud_providers", lambda: ["openai"])
    monkeypatch.setattr(models, "load_api_keys", lambda: {"openai": "sk-test"})
    monkeypatch.setattr(models, "default_cloud_model", lambda provider: "gpt-test")
    monkeypatch.setattr(models, "provider_for_model", lambda model: "openai")
    monkeypatch.setattr(models, "try_cloud_query", fake_cloud)

    offline_agent._cloud_chat(offline_agent._build_messages("hi"))
    trace = offline_agent.last_trace
    assert trace["provider"] == "openai"
    assert trace["thinking"] == "weighed two options"
    assert trace["total_tokens"] == 1280


def test_trace_is_cleared_on_a_new_turn(offline_agent):
    offline_agent.last_trace = {"prompt_tokens": 99, "completion_tokens": 9}
    offline_agent.process_command("help")
    assert offline_agent.last_trace == {}


def test_parse_cloud_body_extracts_usage(monkeypatch):
    body = {
        "choices": [{"message": {"content": "hi", "reasoning_content": "why"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }

    def fake_urlopen(request, timeout=0):
        return FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    trace: dict = {}
    reply, error = models.try_cloud_query(
        "openai", "gpt-test", "sk-test", "hi", trace=trace
    )
    assert reply == "hi" and error is None
    assert trace["prompt_tokens"] == 10
    assert trace["completion_tokens"] == 2
    assert trace["thinking"] == "why"
