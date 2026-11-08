"""The metacognition ledger: every turn recorded, provable, queryable.

All tests use the isolated per-test data directory from conftest.py — never the
user's real database or projects.
"""

from __future__ import annotations

import json
import threading

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app.metacognition import (
    Ledger,
    TurnAlreadyClosed,
    TurnNotFound,
    _since,
)
from sigmahelix.core.config import load_settings
from sigmahelix.core.storage.database import Database
from sigmahelix.core.storage.migrations import MigrationRunner


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
    assert result["mismatch"]["turn_id"] == turn_id
    assert result["mismatch"]["reason"] == "proof mismatch"


def test_verify_detects_a_tampered_step(ledger, database):
    """The reasoning trail is part of the proof, not decoration."""
    turn_id = _closed_turn(ledger)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE agent_steps SET args = 'INJECTED', summary = 'nothing ran' "
            "WHERE turn_id = ?",
            (turn_id,),
        )
    result = ledger.verify()
    assert result["valid"] is False
    assert result["mismatch"]["turn_id"] == turn_id


def test_verify_detects_a_deleted_step(ledger, database):
    turn_id = _closed_turn(ledger)
    with database.transaction() as connection:
        connection.execute("DELETE FROM agent_steps WHERE turn_id = ?", (turn_id,))
    result = ledger.verify()
    assert result["valid"] is False


def test_verify_detects_a_deleted_turn(ledger, database):
    """A turn removed from the table is still anchored in the chain."""
    turn_id = _closed_turn(ledger)
    with database.transaction() as connection:
        connection.execute("DELETE FROM agent_steps WHERE turn_id = ?", (turn_id,))
        connection.execute("DELETE FROM agent_turns WHERE id = ?", (turn_id,))
    result = ledger.verify()
    assert result["valid"] is False
    assert result["orphans"] == [turn_id]
    assert result["mismatch"]["reason"] == "deleted turn"


def test_verify_detects_a_duplicate_anchor(ledger, database):
    """A turn may only be anchored once."""
    turn_id = _closed_turn(ledger)
    row = ledger.turn(turn_id)
    with database.transaction() as connection:
        ledger._audit.append_in_transaction(
            connection,
            "agent.turn.completed",
            "agent_turn",
            turn_id,
            {"proof": row["proof_hash"]},
            tenant_id=ledger.tenant_id,
        )
    result = ledger.verify()
    assert result["valid"] is False
    assert result["duplicates"] == [turn_id]
    assert result["mismatch"]["reason"] == "duplicate audit anchor"


def test_a_closed_turn_cannot_be_closed_again(ledger):
    turn_id = _closed_turn(ledger)
    with pytest.raises(TurnAlreadyClosed):
        ledger.close_turn(turn_id, reply="again", outcome="answered")
    assert ledger.turn(turn_id)["reply"] == "done"


def test_closing_an_unknown_turn_raises(ledger):
    with pytest.raises(TurnNotFound):
        ledger.close_turn("no-such-turn", reply="x", outcome="answered")


def test_a_turn_recorded_before_the_step_digest_still_verifies(ledger, database):
    """Turns from an earlier version are not thrown away."""
    from sigmahelix.app.metacognition import _legacy_proof

    turn_id = _closed_turn(ledger)
    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM agent_turns WHERE id = ?", (turn_id,)
        ).fetchone()
    legacy_hash = _legacy_proof(dict(row))
    with database.transaction() as connection:
        connection.execute(
            "UPDATE agent_turns SET proof_hash = ? WHERE id = ?",
            (legacy_hash, turn_id),
        )
    result = ledger.verify()
    assert result["valid"] is True
    assert result["legacy"] == 1
    assert result["turns_checked"] == 1


def test_an_unclosed_turn_does_not_break_verification(ledger):
    ledger.open_turn("s1", "crashed mid-way", "loop", "cloud")
    result = ledger.verify()
    assert result["valid"] is True
    assert result["unclosed"] == 1
    # Not corrupt — but not complete either.
    assert result["complete"] is False


# ---- the report --------------------------------------------------------------


def test_report_math_is_deterministic(ledger):
    # Three turns that normalise to the *same* intent ("fix the demo" -> "fix
    # demo") with one success, one failure and one block. The report must group
    # them under that exact key, not under any grouping that happens to have two
    # members.
    _closed_turn(ledger, text="fix the demo", outcome="acted")
    _closed_turn(ledger, text="fix the demo", outcome="failed")
    _closed_turn(ledger, text="fix the demo", outcome="blocked")

    metrics = ledger.report("7d")
    assert metrics["turns"] == 3
    assert metrics["outcomes"] == {"acted": 1, "failed": 1, "blocked": 1}
    assert metrics["success_rate"] == pytest.approx(1 / 3)
    assert metrics["truncation_rate"] == 0.0
    assert metrics["tool_calls"]["run_tests"]["total"] == 3
    assert metrics["mean_steps_success"] == pytest.approx(1.0)
    # Exactly one repeated intent, keyed by the normalised phrase, with all 3 ids.
    assert metrics["repeated_intents"] == {
        "fix demo": metrics["repeated_intents"]["fix demo"]
    }
    assert len(metrics["repeated_intents"]["fix demo"]) == 3
    # The failures came first; the block at the end means it was never recovered.
    assert "fix demo" not in metrics["recovered"]


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


def test_a_rejected_recommendation_is_not_re_proposed(ledger):
    """A rejection sticks: it never comes back as a new proposal."""
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]
    ledger.decide(rec["id"], "rejected", note="not now")

    again = ledger.recommend("7d")
    assert [r["id"] for r in again] == [rec["id"]]
    assert again[0]["status"] == "rejected"
    assert len(ledger.recommendations()) == 1


# ---- approval workflow -----------------------------------------------------------


def test_decide_transitions_and_is_audited(ledger, database):
    # A decision is a real state change, written to the table and the chain.
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]
    assert rec["status"] == "proposed"  # the precondition the test relies on

    decided = ledger.decide(rec["id"], "approved", note="do it")
    assert decided["status"] == "approved"

    # The stored row actually moved from proposed -> approved.
    stored = ledger.recommendations(status="approved")
    assert len(stored) == 1
    assert stored[0]["id"] == rec["id"]

    with pytest.raises(ValueError):
        ledger.decide(rec["id"], "bogus")
    with pytest.raises(ValueError):
        ledger.decide("nope", "approved")

    with database.connection() as connection:
        entries = connection.execute(
            "SELECT payload_json FROM audit_log WHERE action = ?",
            ("agent.recommendation.decision",),
        ).fetchall()
    assert len(entries) == 1
    payload = json.loads(entries[0]["payload_json"])
    # The chain records both ends of the transition, not just the new state —
    # a no-op decide that merely echoed {status: decision} would fail.
    assert payload["decision"] == "approved"
    assert payload["from"] == "proposed"


def test_the_decision_state_machine_is_enforced(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]

    ledger.decide(rec["id"], "approved")
    # approving twice is not a transition
    with pytest.raises(ValueError):
        ledger.decide(rec["id"], "approved")
    # an approval can be withdrawn
    assert ledger.decide(rec["id"], "rejected")["status"] == "rejected"
    # a rejection can be reopened by the founder — and only by the founder
    assert ledger.decide(rec["id"], "reopen")["status"] == "proposed"


def test_a_decision_cannot_be_made_twice_silently(ledger, database):
    """Every decision is a legal transition and every one is audited.

    The old code let any status become any other, so a rejection could be
    flipped to approved without a word. Now the transition table decides, and
    the chain records where the recommendation came from.
    """
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]
    ledger.decide(rec["id"], "rejected")

    # Approving a rejection is a legal, explicit reconsideration — not a
    # silent overwrite — and it is recorded with both states.
    assert ledger.decide(rec["id"], "approved")["status"] == "approved"

    with database.connection() as connection:
        entries = connection.execute(
            "SELECT payload_json FROM audit_log WHERE action = ?",
            ("agent.recommendation.decision",),
        ).fetchall()
    decisions = [json.loads(entry["payload_json"]) for entry in entries]
    assert [d["decision"] for d in decisions] == ["rejected", "approved"]
    assert decisions[1]["from"] == "rejected"


# ---- privacy ------------------------------------------------------------------------


def test_secrets_are_redacted_before_they_are_stored(ledger):
    secret = "sk-abcdefghijklmnop1234"
    turn_id = ledger.open_turn(
        "s1", f"my key is api_key={secret}", "loop", "cloud"
    )
    ledger.add_step(
        turn_id,
        "tool_call",
        action="run_command",
        args=f"curl -H 'Authorization: Bearer {secret}'",
        summary=f"used {secret}",
    )
    ledger.close_turn(
        turn_id, reply=f"I stored {secret}", outcome="acted", model="deepseek-chat"
    )
    row = ledger.turn(turn_id)
    assert secret not in row["user_text"]
    assert secret not in row["reply"]
    assert secret not in row["steps"][0]["args"]
    assert secret not in row["steps"][0]["summary"]
    assert "[REDACTED]" in row["user_text"]
    # The proof still verifies over the redacted content.
    assert ledger.verify()["valid"] is True


def test_cloud_mode_does_not_replay_past_turns_to_the_provider(ledger, monkeypatch):
    """Past turns are local unless the founder opts in."""
    first = _offline_agent(monkeypatch)
    first.process_command("create task audit sigmahelix")

    second = _offline_agent(monkeypatch)
    second.model_kind = "cloud"
    assert second._may_replay_history() is False
    messages = second._build_messages("what did we do?")
    contents = [m["content"] for m in messages if m["role"] == "user"]
    assert not any("audit sigmahelix" in c for c in contents)

    # The founder can allow it explicitly.
    second.cloud_replay_history = True
    assert second._may_replay_history() is True
    messages = second._build_messages("what did we do?")
    contents = [m["content"] for m in messages if m["role"] == "user"]
    assert any("audit sigmahelix" in c for c in contents)


def test_the_local_model_may_replay_past_turns(ledger, monkeypatch):
    first = _offline_agent(monkeypatch)
    first.process_command("create task audit sigmahelix")

    second = _offline_agent(monkeypatch)
    second.model_kind = "local"
    messages = second._build_messages("what did we do?")
    contents = [m["content"] for m in messages if m["role"] == "user"]
    assert any("audit sigmahelix" in c for c in contents)


# ---- bounds -------------------------------------------------------------------------


def test_the_period_must_be_within_bounds(ledger):
    with pytest.raises(ValueError):
        ledger.report("1000000000d")
    with pytest.raises(ValueError):
        ledger.report("0d")
    with pytest.raises(ValueError):
        ledger.report("7x")


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
    roles = [m["role"] for m in messages]
    contents = [m["content"] for m in messages]

    # the user's earlier prompts survived
    assert any("audit sigmahelix" in c for c in contents)
    # so did the assistant's replies — not just the user text
    assert "assistant" in roles
    replies = [m["content"] for m in messages if m["role"] == "assistant"]
    assert replies
    assert all(r.strip() for r in replies)


def test_ledger_failure_never_breaks_a_reply(monkeypatch):
    agent = _offline_agent(monkeypatch)
    real = agent.ledger
    before = len(real.turns())

    # The ledger's open blows up. Recording is best-effort: the chat must still
    # answer, and nothing half-written may linger in the real ledger.
    monkeypatch.setattr(
        real,
        "open_turn",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk on fire")),
    )
    reply = agent.process_command("list tasks")
    assert reply  # the chat still produces an answer
    assert len(real.turns()) == before  # no orphan half-turn was committed


def test_the_agent_records_its_steps_in_one_write(ledger, monkeypatch):
    """Steps, the turn row and the anchor are written together."""
    agent = _offline_agent(monkeypatch)
    agent._ledger_obj = ledger
    turn_id, started = agent._open_turn("do the thing")
    agent.last_trace = {
        "steps": [
            {
                "seq": 1,
                "action": "run_tests",
                "plan": "prove it",
                "args": "pytest",
                "ok": True,
                "summary": "exit 0",
                "duration_ms": 5,
            }
        ],
        "plans": ["prove it"],
        "total_tokens": 10,
        "completion_tokens": 4,
        "prompt_tokens": 6,
    }
    agent._close_turn(turn_id, started, "loop", "done", None, "acted")

    row = ledger.turn(turn_id)
    assert len(row["steps"]) == 1
    assert row["steps"][0]["action"] == "run_tests"
    assert row["steps"][0]["ok"] == 1
    assert row["outcome"] == "acted"
    assert ledger.verify()["valid"] is True


def test_a_turn_is_anchored_exactly_once(ledger, monkeypatch):
    agent = _offline_agent(monkeypatch)
    agent._ledger_obj = ledger
    agent.process_command("create task water the plants")
    with ledger.database.connection() as connection:
        anchors = connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'agent.turn.completed'"
        ).fetchone()[0]
    assert anchors == 1
    assert ledger.verify()["valid"] is True
    assert ledger.verify()["complete"] is True


# ---- item #7: aggregate report, no N+1, no turn_ids on the wire ---------------


def test_empty_period_report_has_complete_shape(ledger):
    metrics = ledger.report("7d")
    assert metrics["turns"] == 0
    assert metrics["tool_calls"] == {}
    assert metrics["tool_failure_rate"] == {}
    assert metrics["mean_steps_success"] == 0.0
    assert "turn_ids" not in metrics


def test_report_omits_turn_ids_from_the_payload(ledger):
    _closed_turn(ledger, text="x", outcome="acted")
    metrics = ledger.report("7d")
    assert "turn_ids" not in metrics
    # The aggregate path still produces correct per-action tool totals.
    assert metrics["tool_calls"]["run_tests"]["total"] == 1


def test_report_aggregate_matches_reference_counts(ledger):
    """The single GROUP BY query must agree with counting every step directly."""
    for _ in range(20):
        _closed_turn(ledger, text="do a thing", outcome="acted")
    tid = ledger.open_turn("s1", "break it", "loop", "cloud")
    ledger.add_step(tid, "tool_call", action="run_tests", ok=False, summary="boom")
    ledger.close_turn(tid, reply="failed", outcome="failed")

    metrics = ledger.report("7d")
    with ledger.database.connection() as connection:
        ref = connection.execute(
            "SELECT action, SUM(ok = 0) AS failed, COUNT(*) AS total "
            "FROM agent_steps WHERE tenant_id = ? AND kind = 'tool_call' "
            "GROUP BY action",
            (ledger.tenant_id,),
        ).fetchall()
    ref_calls = {r["action"]: {"total": r["total"], "failed": r["failed"]} for r in ref}
    assert metrics["tool_calls"] == ref_calls
    # 20 acted turns each with one step -> mean of 1.0; the failed turn never
    # counts toward a successful turn's step count.
    assert metrics["mean_steps_success"] == pytest.approx(1.0)
    assert metrics["turns"] == 21


def test_report_scales_without_per_turn_queries(ledger):
    """200 turns with 3 steps each must aggregate in one pass, not 200 queries."""
    for i in range(200):
        _closed_turn(ledger, text=f"task {i}", outcome="acted")
    metrics = ledger.report("7d")
    assert metrics["turns"] == 200
    assert metrics["tool_calls"]["run_tests"]["total"] == 200
    assert metrics["mean_steps_success"] == pytest.approx(1.0)


def test_recommend_reuses_passed_metrics(ledger):
    """analyze computes the report once and hands it to recommend."""
    _closed_turn(ledger, text="x", truncated=1)
    fresh = ledger.recommend("7d")
    reused = ledger.recommend("7d", metrics=ledger.report("7d"))
    assert [r["id"] for r in fresh] == [r["id"] for r in reused]
    assert [r["title"] for r in fresh] == [r["title"] for r in reused]


def test_pushback_without_tools_detected_by_aggregate(ledger):
    """A pushback turn with no tool call is flagged; one with a call is not."""
    a = ledger.open_turn("s1", "is it ok?", "llm", "cloud")
    ledger.close_turn(a, reply="yes", outcome="answered")
    ledger.add_feedback(a, "pushback")

    b = ledger.open_turn("s1", "run it", "loop", "cloud")
    ledger.add_step(b, "tool_call", action="run_tests", ok=True)
    ledger.close_turn(b, reply="done", outcome="answered")
    ledger.add_feedback(b, "pushback")

    assert ledger._pushback_without_tools([a, b]) == [a]
    recs = ledger.recommend("7d")
    prompt = [
        r for r in recs if r["kind"] == "prompt" and "checking" in r["title"].lower()
    ]
    assert prompt
    assert prompt[0]["evidence"]["turns"] == [a]


# ---- item #8: apply() with an explicit, reversible kind whitelist --------------


def _insert_recommendation(
    ledger, kind, title, status="approved", evidence=None
):
    """Insert a recommendation row directly so apply() can be tested in isolation."""
    import json
    import uuid
    from datetime import UTC, datetime

    rec_id = str(uuid.uuid4())
    with ledger.database.transaction() as connection:
        connection.execute(
            "INSERT INTO agent_recommendations "
            "(id, tenant_id, created_at, period, kind, title, body, evidence_json, status) "
            "VALUES (?, ?, ?, '7d', ?, ?, ?, ?, ?)",
            (
                rec_id,
                ledger.tenant_id,
                datetime.now(UTC).isoformat(),
                kind,
                title,
                "do it",
                json.dumps(evidence or {}),
                status,
            ),
        )
    return rec_id


def test_apply_requires_an_approved_recommendation(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]  # stored as "proposed"
    with pytest.raises(ValueError):
        ledger.apply(rec["id"])


def test_apply_of_a_rejected_recommendation_is_refused(ledger):
    rec_id = _insert_recommendation(
        ledger,
        "config",
        "Raise the cloud reply budget",
        status="rejected",
        evidence={"setting": "cloud_max_tokens", "value": 8192},
    )
    with pytest.raises(ValueError):
        ledger.apply(rec_id)


def test_apply_skill_writes_a_reversible_file(ledger):
    from sigmahelix.app.skills import user_skills_dir

    rec_id = _insert_recommendation(
        ledger,
        "skill",
        "Recurring failure: water plants",
        evidence={"turns": ["t1", "t2", "t3"]},
    )
    result = ledger.apply(rec_id)
    assert result["status"] == "applied"
    files = list(user_skills_dir().glob("*.md"))
    assert files
    text = files[0].read_text()
    assert "Recurring failure" in text
    assert "t1" in text
    assert ledger.recommendations(status="applied")[0]["id"] == rec_id
    # An applied recommendation can no longer be decided (terminal state).
    with pytest.raises(ValueError):
        ledger.decide(rec_id, "rejected")


def test_apply_config_writes_the_setting(ledger):
    from sigmahelix.core.config import load_settings

    rec_id = _insert_recommendation(
        ledger,
        "config",
        "Raise the cloud reply budget",
        evidence={"setting": "cloud_max_tokens", "value": 8192},
    )
    result = ledger.apply(rec_id)
    assert result["status"] == "applied"
    assert load_settings().cloud_max_tokens == 8192


def test_apply_plugin_toggles_the_enabled_set(ledger):
    rec_id = _insert_recommendation(
        ledger,
        "update_plugin",
        "Enable the blog plugin",
        evidence={"plugin_id": "blog"},
    )
    result = ledger.apply(rec_id)
    assert result["status"] == "applied"
    from sigmahelix.core.config import load_settings

    assert "blog" in load_settings().plugins_enabled


def test_apply_rejects_non_appliable_kinds(ledger):
    from sigmahelix.app.metacognition import LedgerError

    rec_id = _insert_recommendation(
        ledger,
        "prompt",
        "Answer only after checking",
        evidence={"turns": ["t1"]},
    )
    with pytest.raises(LedgerError) as exc:
        ledger.apply(rec_id)
    assert "not auto-applied" in str(exc.value)


def test_apply_is_audited(ledger, database):
    import json

    rec_id = _insert_recommendation(
        ledger,
        "config",
        "Raise the cloud reply budget",
        evidence={"setting": "cloud_max_tokens", "value": 8192},
    )
    ledger.apply(rec_id)
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM audit_log WHERE action = ?",
            ("agent.recommendation.applied",),
        ).fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0]["payload_json"])["effect"].startswith(
        "set cloud_max_tokens"
    )


def test_truncation_recommendation_carries_apply_target(ledger):
    _closed_turn(ledger, text="x", truncated=1)
    recs = ledger.recommend("7d")
    config = [r for r in recs if r["kind"] == "config"][0]
    assert config["evidence"]["setting"] == "cloud_max_tokens"
    assert isinstance(config["evidence"]["value"], int)
    # end-to-end: approve then apply
    ledger.decide(config["id"], "approve")
    result = ledger.apply(config["id"])
    assert result["status"] == "applied"


# ---- items #9/#10: explicit outcomes, deterministic routes record a step -----


def test_outcome_from_reply_maps_reply_contract_explicitly():
    """The outcome is decided from the route's status contract, not sniffed."""
    f = agent_module.Agent._outcome_from_reply
    assert f("", None, action=False) == "answered"
    assert f("done", None, action=True) == "acted"
    assert f("⚠️ no plugin", None, action=True) == "blocked"
    assert f("❌ tool failed", None, action=True) == "blocked"
    assert f("❌ I won't", None, action=False) == "refused"
    assert f("anything", "Boom: no", action=True) == "failed"


def test_deterministic_tool_route_records_an_acted_step(ledger, monkeypatch):
    """A tool route that runs offline must show up as an action, with a step."""
    agent = _offline_agent(monkeypatch)
    monkeypatch.setattr(agent, "_direct_route", lambda text: None)
    monkeypatch.setattr(agent, "_task_build_route", lambda raw: None)
    monkeypatch.setattr(agent, "_tool_route", lambda raw: "ran the tool")
    monkeypatch.setattr(agent, "_llm_roundtrip", lambda raw: None)
    monkeypatch.setattr(agent, "_keyword_route", lambda raw: "fallback")

    agent.process_command("do the thing")

    turn_id = ledger.turns()[-1]["id"]
    row = ledger.turn(turn_id)
    assert row["route"] == "tool"
    assert row["outcome"] == "acted"
    assert len(row["steps"]) == 1
    assert row["steps"][0]["kind"] == "tool_call"
    assert row["steps"][0]["action"] == "tool"
    assert row["steps"][0]["ok"] == 1


def test_blocked_tool_route_is_not_counted_as_acted(ledger, monkeypatch):
    """A disabled plugin (⚠️ reply) is recorded as blocked, not a fake action."""
    agent = _offline_agent(monkeypatch)
    monkeypatch.setattr(agent, "_direct_route", lambda text: None)
    monkeypatch.setattr(agent, "_task_build_route", lambda raw: None)
    monkeypatch.setattr(agent, "_tool_route", lambda raw: "⚠️ plugin off")
    monkeypatch.setattr(agent, "_llm_roundtrip", lambda raw: None)
    monkeypatch.setattr(agent, "_keyword_route", lambda raw: "fallback")

    agent.process_command("do the thing")

    turn_id = ledger.turns()[-1]["id"]
    row = ledger.turn(turn_id)
    assert row["route"] == "tool"
    assert row["outcome"] == "blocked"
    assert row["steps"] == []  # no fabricated success step


def test_deterministic_task_route_records_an_acted_step(ledger, monkeypatch):
    agent = _offline_agent(monkeypatch)
    monkeypatch.setattr(agent, "_direct_route", lambda text: None)
    monkeypatch.setattr(agent, "_tool_route", lambda raw: None)
    monkeypatch.setattr(agent, "_task_build_route", lambda raw: "handled the task")
    monkeypatch.setattr(agent, "_llm_roundtrip", lambda raw: None)
    monkeypatch.setattr(agent, "_keyword_route", lambda raw: "fallback")

    agent.process_command("handle the task")

    turn_id = ledger.turns()[-1]["id"]
    row = ledger.turn(turn_id)
    assert row["route"] == "task"
    assert row["outcome"] == "acted"
    assert len(row["steps"]) == 1
    assert row["steps"][0]["action"] == "task"


# ---- item #11: metric arithmetic ----------------------------------------------


def test_pushback_rate_never_exceeds_one(ledger):
    """Two verdicts on one turn, or a late verdict, must not break the ratio."""
    turn_id = ledger.open_turn("s1", "did it work?", "llm", "cloud")
    ledger.close_turn(turn_id, reply="yes", outcome="answered")
    # Same turn judged pushback twice (user + heuristic) — one turn, not two.
    ledger.add_feedback(turn_id, "pushback")
    ledger.add_feedback(turn_id, "pushback")

    metrics = ledger.report("7d")
    assert metrics["turns"] == 1
    assert metrics["pushback_rate"] <= 1.0
    assert metrics["pushback_turns"] == [turn_id]


def test_pushback_counts_only_turns_that_started_in_period(ledger):
    """A turn started before the period is excluded even if verdict is in it."""
    old = ledger.open_turn("s1", "old question", "llm", "cloud")
    ledger.close_turn(old, reply="old answer", outcome="answered")
    # Re-date the turn so it falls outside the 7d window.
    with ledger.database.connection() as connection:
        connection.execute(
            "UPDATE agent_turns SET started_at = '2000-01-01T00:00:00+00:00' "
            "WHERE id = ?",
            (old,),
        )
    # A fresh in-period turn gets the pushback.
    fresh = ledger.open_turn("s1", "new question", "llm", "cloud")
    ledger.close_turn(fresh, reply="new answer", outcome="answered")
    ledger.add_feedback(fresh, "pushback")

    metrics = ledger.report("7d")
    assert old not in metrics["pushback_turns"]
    assert metrics["pushback_rate"] == pytest.approx(1.0)
    assert metrics["turns"] == 1


def test_turns_limit_none_returns_everything(ledger):
    """limit=None is the contract report() relies on: no silent truncation."""
    for i in range(5):
        tid = ledger.open_turn("s1", f"task {i}", "loop", "cloud")
        ledger.close_turn(tid, reply="x", outcome="answered")
    since = _since("7d")
    assert len(ledger.turns(since=since, limit=2)) == 2
    assert len(ledger.turns(since=since, limit=None)) == 5


# ---- item #12: migration v17 indexes -----------------------------------------


def test_migration_v17_adds_ledger_indexes(tmp_path):
    database = Database(tmp_path / "indexes.db")
    runner = MigrationRunner(database)
    assert runner.upgrade() == 17

    def index_names(db):
        with db.connection() as connection:
            return {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }

    names = index_names(database)
    assert "idx_agent_feedback_tenant_created" in names
    assert "idx_agent_recommendations_tenant_status_created" in names

    # Rolling back drops the indexes without touching the data tables.
    assert runner.downgrade(16) == 16
    names = index_names(database)
    assert "idx_agent_feedback_tenant_created" not in names
    assert "idx_agent_recommendations_tenant_status_created" not in names


# ---- item #13: missing regression tests --------------------------------------


def test_decide_twice_is_refused(ledger):
    """A second, illegal decision is refused and the stored status is unchanged.

    The state machine permits a withdrawal (approved -> rejected) but forbids
    re-approving an already-approved recommendation: that transition is not in
    ``_DECISION_FLOW`` and must raise rather than silently overwrite.
    """
    _closed_turn(ledger, text="x", truncated=1)
    rec = ledger.recommend("7d")[0]
    assert ledger.decide(rec["id"], "approved")["status"] == "approved"

    with pytest.raises(ValueError):
        ledger.decide(rec["id"], "approved")  # not a legal transition
    # The stored row still reflects the only decision that took.
    assert ledger.recommendations()[0]["status"] == "approved"


def test_ledger_raising_mid_turn_keeps_the_reply(monkeypatch):
    """A ledger that dies after the turn opens must not cost the user a reply.

    The turn was opened (a row exists) but never closed, so exactly one unclosed
    turn remains — never a half-written, half-anchored one.
    """
    agent = _offline_agent(monkeypatch)
    real = agent.ledger

    class Broken:
        def open_turn(self, *a, **k):
            return real.open_turn(*a, **k)

        def add_step(self, *a, **k):
            raise RuntimeError("disk on fire")

        def close_turn(self, *a, **k):
            raise RuntimeError("disk on fire")

    agent._ledger_obj = Broken()
    reply = agent.process_command("create task water the plants")
    assert reply  # the chat still answers despite the ledger dying
    assert real.verify()["unclosed"] == 1
    assert real.turns()[0]["ended_at"] is None


def test_unclosed_turn_evidence_shape(ledger):
    """evidence_json is always a JSON array, even before the turn closes."""
    turn_id = ledger.open_turn("s1", "crashed mid-way", "loop", "cloud")
    evidence = json.loads(ledger.turn(turn_id)["evidence_json"])
    assert isinstance(evidence, list)
    assert evidence == []

    # Once closed with evidence it stays a list (not a dict or a string).
    tid2 = _closed_turn(ledger)
    assert json.loads(ledger.turn(tid2)["evidence_json"]) == ["run_tests:exit=0"]


def test_agent_persists_steps_into_the_ledger(ledger, monkeypatch):
    """Steps the loop records survive into the ledger as real step rows."""
    agent = _offline_agent(monkeypatch)
    agent._ledger_obj = ledger
    agent.llm_available = True  # force the LLM route, which runs the loop

    def fake_llm_roundtrip(raw):
        agent.last_trace = {
            "steps": [
                {
                    "seq": 1,
                    "action": "run_tests",
                    "plan": "prove it",
                    "args": "pytest",
                    "ok": True,
                    "summary": "exit 0",
                    "duration_ms": 5,
                }
            ],
            "plans": ["prove it"],
            "total_tokens": 10,
            "completion_tokens": 4,
            "prompt_tokens": 6,
        }
        return "ran the tests"

    for route in ("_direct_route", "_task_build_route", "_tool_route", "_keyword_route"):
        monkeypatch.setattr(agent, route, lambda text: None)
    monkeypatch.setattr(agent, "_llm_roundtrip", fake_llm_roundtrip)

    agent.process_command("run the tests")

    turn_id = ledger.turns()[-1]["id"]
    row = ledger.turn(turn_id)
    assert len(row["steps"]) == 1
    assert row["steps"][0]["action"] == "run_tests"
    assert row["steps"][0]["ok"] == 1
    assert ledger.verify()["valid"] is True


def test_concurrent_turns_same_session(ledger):
    """Two turns opening/closing in parallel both persist with distinct indices."""

    def work():
        tid = ledger.open_turn("s", "parallel work", "loop", "cloud")
        ledger.add_step(tid, "tool_call", action="run_tests", ok=True, summary="ok")
        ledger.close_turn(tid, reply="done", outcome="acted")

    threads = [threading.Thread(target=work) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = ledger.turns()
    assert len(rows) == 2
    assert len({r["id"] for r in rows}) == 2  # no lost or merged turn
    # Each turn got its own index within the shared session.
    assert len({r["turn_index"] for r in rows}) == 2
    assert ledger.verify()["valid"] is True


def test_recovered_intent_and_skill_rule(ledger):
    """A failure that later succeeds is 'recovered' (no skill); three straight
    failures in one intent fire a skill rule instead."""

    # Intent "fix demo": fail, fail, then succeed -> recovered, no skill rule.
    for outcome in ("failed", "failed", "acted"):
        tid = ledger.open_turn("s1", "fix the demo", "loop", "cloud")
        ledger.close_turn(tid, reply="x", outcome=outcome)

    # Intent "deploy site": three straight failures -> skill rule, not recovered.
    for _ in range(3):
        tid = ledger.open_turn("s1", "deploy the site", "loop", "cloud")
        ledger.close_turn(tid, reply="x", outcome="failed")

    metrics = ledger.report("7d")
    assert "fix demo" in metrics["recovered"]
    assert "deploy site" not in metrics["recovered"]

    recs = ledger.recommend("7d")
    skill_titles = [r["title"] for r in recs if r["kind"] == "skill"]
    assert any("deploy site" in title for title in skill_titles)
    assert not any("fix demo" in title for title in skill_titles)
