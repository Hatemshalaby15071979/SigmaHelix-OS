"""The metacognition ledger: every turn recorded, provable, queryable.

All tests use the isolated per-test data directory from conftest.py — never the
user's real database or projects.
"""

from __future__ import annotations

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app.metacognition import Ledger
from sigmahelix.core.config import load_settings
from sigmahelix.core.storage.database import Database


@pytest.fixture
def database():
    db = Database(load_settings().database_path)
    db.initialize()
    return db


@pytest.fixture
def ledger(database):
    return Ledger(database)


def _offline_agent(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    return agent_module.Agent()


def _closed_turn(ledger, text="fix the demo", outcome="acted", truncated=0):
    turn_id = ledger.open_turn("s1", text, "loop", "cloud")
    ledger.add_step(
        turn_id,
        "tool_call",
        action="run_tests",
        plan="prove it",
        args="demo",
        summary="pytest exit 0",
        ok=True,
        duration_ms=12,
    )
    ledger.close_turn(
        turn_id,
        reply="done",
        outcome=outcome,
        route="loop",
        model="deepseek-chat",
        tokens=(100, 50, 150),
        duration_ms=900,
        truncated=bool(truncated),
        evidence=["run_tests:exit=0"],
    )
    return turn_id


# ---- writing / reading -----------------------------------------------------


def test_turn_and_steps_round_trip(ledger):
    turn_id = _closed_turn(ledger)
    row = ledger.turn(turn_id)
    assert row["user_text"] == "fix the demo"
    assert row["outcome"] == "acted"
    assert row["route"] == "loop"
    assert row["model"] == "deepseek-chat"
    assert row["total_tokens"] == 150
    assert row["proof_hash"] and len(row["proof_hash"]) == 64
    steps = row["steps"]
    assert len(steps) == 1
    assert steps[0]["action"] == "run_tests"
    assert steps[0]["plan"] == "prove it"
    assert steps[0]["ok"] == 1


def test_close_turn_anchors_the_proof_in_the_audit_chain(ledger):
    _closed_turn(ledger)
    result = ledger.verify()
    assert result["valid"] is True
    assert result["chain_valid"] is True
    assert result["turns_checked"] == 1


def test_verify_detects_a_tampered_turn(ledger, database):
    turn_id = _closed_turn(ledger)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE agent_turns SET reply = 'lied' WHERE id = ?", (turn_id,)
        )
    result = ledger.verify()
    assert result["valid"] is False
    assert result["mismatch"] == {"turn_id": turn_id}


def test_unclosed_turns_do_not_break_verification(ledger):
    ledger.open_turn("s1", "crashed mid-way", "loop", "cloud")
    result = ledger.verify()
    assert result["valid"] is True
    assert result["unclosed"] == 1


# ---- the report --------------------------------------------------------------


def test_report_math_is_deterministic(ledger):
    _closed_turn(ledger, text="fix the demo", outcome="acted")
    _closed_turn(ledger, text="fix the demo", outcome="failed")
    tid = ledger.open_turn("s1", "fix the demo again", "loop", "cloud")
    ledger.close_turn(tid, reply="⚠️ blocked", outcome="blocked", tokens=(1, 1, 2))

    metrics = ledger.report("7d")
    assert metrics["turns"] == 3
    assert metrics["outcomes"] == {"acted": 1, "failed": 1, "blocked": 1}
    assert metrics["success_rate"] == pytest.approx(1 / 3)
    assert metrics["truncation_rate"] == 0.0
    assert metrics["tool_calls"]["run_tests"]["total"] == 2
    assert metrics["mean_steps_success"] == pytest.approx(1.0)
    # "fix the demo" normalises to the same intent as "fix the demo again"
    assert any(len(ids) >= 2 for ids in metrics["repeated_intents"].values())


def test_report_counts_truncation_and_pushback(ledger):
    _closed_turn(ledger, text="a", outcome="answered", truncated=1)
    _closed_turn(ledger, text="b", outcome="answered")
    turn_id = _closed_turn(ledger, text="c", outcome="answered")
    ledger.add_feedback(turn_id, "pushback", reason="invented a repo read")

    metrics = ledger.report("7d")
    assert metrics["truncation_rate"] == pytest.approx(1 / 3)
    assert metrics["pushback_rate"] == pytest.approx(1 / 3)
    assert metrics["pushback_turns"] == [turn_id]


# ---- recommendations -----------------------------------------------------------


def test_truncation_recommends_a_config_change(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    recs = ledger.recommend("7d")
    config = [r for r in recs if r["kind"] == "config"]
    assert config and "budget" in config[0]["title"].lower()
    assert config[0]["evidence"]["turns"]


def test_pushback_without_tools_recommends_a_prompt_fix(ledger):
    turn_id = ledger.open_turn("s1", "is the repo ok?", "llm", "cloud")
    ledger.close_turn(turn_id, reply="yes it is fine", outcome="answered")
    ledger.add_feedback(turn_id, "pushback")

    recs = ledger.recommend("7d")
    prompt = [
        r for r in recs if r["kind"] == "prompt" and "checking" in r["title"].lower()
    ]
    assert prompt
    assert prompt[0]["evidence"]["turns"] == [turn_id]


def test_failing_tool_recommends_a_tool_fix(ledger):
    for _ in range(2):
        turn_id = ledger.open_turn("s1", "run it", "loop", "cloud")
        ledger.add_step(
            turn_id, "tool_call", action="run_tests", ok=False, summary="boom"
        )
        ledger.close_turn(turn_id, reply="failed", outcome="failed")

    recs = ledger.recommend("7d")
    tool = [r for r in recs if r["kind"] == "tool"]
    assert tool and tool[0]["title"].endswith("run_tests")


def test_recommendations_are_stored_once_and_survive_recompute(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    first = ledger.recommend("7d")
    second = ledger.recommend("7d")
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert ledger.recommendations(status="proposed")


# ---- approval workflow -----------------------------------------------------------


def test_decide_transitions_and_is_audited(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]
    decided = ledger.decide(rec["id"], "approved", note="do it")
    assert decided["status"] == "approved"
    with pytest.raises(ValueError):
        ledger.decide(rec["id"], "bogus")
    with pytest.raises(ValueError):
        ledger.decide("nope", "approved")


# ---- agent integration -------------------------------------------------------


def test_process_command_records_the_turn(ledger, monkeypatch):
    agent = _offline_agent(monkeypatch)
    reply = agent.process_command("create task water the plants")
    assert "task" in reply.lower()
    rows = ledger.turns()
    assert len(rows) == 1
    assert rows[0]["route"] in ("direct", "task", "tool", "keyword")
    assert rows[0]["outcome"] in ("answered", "acted")
    assert rows[0]["reply"] == reply
    assert rows[0]["ended_at"] is not None


def test_conversation_survives_a_restart(ledger, monkeypatch):
    first = _offline_agent(monkeypatch)
    first.process_command("create task audit sigmahelix")
    first.process_command("list tasks")

    # a brand-new agent (new session, empty in-memory history) sees the past
    second = _offline_agent(monkeypatch)
    assert second.history == []
    messages = second._build_messages("what did we do?")
    contents = [m["content"] for m in messages if m["role"] == "user"]
    assert any("audit sigmahelix" in c for c in contents)


def test_ledger_failure_never_breaks_a_reply(monkeypatch):
    agent = _offline_agent(monkeypatch)

    class Broken:
        def open_turn(self, *a, **k):
            raise RuntimeError("disk on fire")

    agent._ledger_obj = Broken()
    reply = agent.process_command("list tasks")
    assert "task" in reply.lower() or "no tasks" in reply.lower()
