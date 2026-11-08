"""Tommy's metacognition ledger.

Every turn Tommy takes is written to ``agent_turns`` with its steps in
``agent_steps``; each completed turn's content hash is anchored in the existing
hash-chained ``audit_log``, so a report is provable, not just plausible.

The report and the recommendations are computed by SQL and deterministic rules
only. No model call invents a metric, and no recommendation applies itself —
the founder approves or rejects, and only whitelisted reversible actions may be
applied at all.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from ..core.storage.audit import AuditLog
from ..core.storage.database import Database

DEFAULT_TENANT = "local"

_PERIOD = re.compile(r"^(\d+)([dhw])$")

# Words dropped when two user messages are compared as "the same intent".
_INTENT_STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "with",
        "it",
        "is",
        "are",
        "was",
        "please",
        "tommy",
        "my",
        "me",
        "i",
        "do",
        "does",
        "did",
        "can",
        "could",
        "you",
        "your",
        "its",
        "this",
        "that",
    }
)

_PROOF_FIELDS = (
    "id",
    "tenant_id",
    "session_id",
    "turn_index",
    "started_at",
    "ended_at",
    "user_text",
    "route",
    "model_mode",
    "provider",
    "model",
    "plan",
    "reply",
    "outcome",
    "error",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "duration_ms",
    "truncated",
    "evidence_json",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(record: dict[str, Any]) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()


def _proof(record: dict[str, Any]) -> str:
    """SHA-256 over the canonical turn record (proof field excluded)."""
    return hashlib.sha256(
        _canonical({k: record.get(k) for k in _PROOF_FIELDS})
    ).hexdigest()


def _since(period: str) -> str:
    match = _PERIOD.match((period or "7d").strip().lower())
    if not match:
        raise ValueError("period must look like 7d, 24h or 2w")
    amount, unit = int(match.group(1)), match.group(2)
    delta = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "w": timedelta(weeks=amount),
    }[unit]
    return (datetime.now(UTC) - delta).isoformat()


def _normalize_intent(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return " ".join(w for w in words if w not in _INTENT_STOP_WORDS)


class Ledger:
    """Write and query the agent ledger. All access is tenant-scoped."""

    def __init__(self, database: Database, tenant_id: str = DEFAULT_TENANT) -> None:
        self.database = database
        self.tenant_id = tenant_id
        self._audit = AuditLog(database)

    # ---- writing ---------------------------------------------------------
    def open_turn(
        self, session_id: str, user_text: str, route: str, model_mode: str
    ) -> str:
        """Start a turn row and return its id."""
        turn_id = str(uuid.uuid4())
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(turn_index) + 1, 0) FROM agent_turns "
                "WHERE tenant_id = ? AND session_id = ?",
                (self.tenant_id, session_id),
            ).fetchone()
            record = {
                "id": turn_id,
                "tenant_id": self.tenant_id,
                "session_id": session_id,
                "turn_index": int(row[0]),
                "started_at": _now(),
                "ended_at": None,
                "user_text": user_text,
                "route": route,
                "model_mode": model_mode,
                "provider": None,
                "model": None,
                "plan": "",
                "reply": "",
                "outcome": "unknown",
                "error": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "duration_ms": 0,
                "truncated": 0,
                "evidence_json": "{}",
            }
            connection.execute(
                "INSERT INTO agent_turns ("
                "id, tenant_id, session_id, turn_index, started_at, user_text, "
                "route, model_mode, proof_hash"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    self.tenant_id,
                    session_id,
                    record["turn_index"],
                    record["started_at"],
                    user_text,
                    route,
                    model_mode,
                    _proof(record),
                ),
            )
        return turn_id

    def add_step(
        self,
        turn_id: str,
        kind: str,
        action: str = "",
        plan: str = "",
        args: str = "",
        summary: str = "",
        ok: bool = True,
        duration_ms: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append one step to a turn."""
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(seq) + 1, 1) FROM agent_steps "
                "WHERE tenant_id = ? AND turn_id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            connection.execute(
                "INSERT INTO agent_steps ("
                "id, tenant_id, turn_id, seq, kind, action, plan, args, "
                "summary, ok, duration_ms, payload_json, occurred_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.tenant_id,
                    turn_id,
                    int(row[0]),
                    kind,
                    action,
                    plan,
                    args,
                    summary,
                    1 if ok else 0,
                    duration_ms,
                    json.dumps(payload or {}),
                    _now(),
                ),
            )

    def close_turn(
        self,
        turn_id: str,
        *,
        reply: str,
        outcome: str,
        route: str | None = None,
        error: str | None = None,
        plan: str = "",
        provider: str | None = None,
        model: str | None = None,
        tokens: tuple[int, int, int] = (0, 0, 0),
        duration_ms: int = 0,
        truncated: bool = False,
        evidence: list[str] | None = None,
    ) -> None:
        """Finish a turn, recompute its content proof, and anchor the proof in
        the hash-chained audit log."""
        ended_at = _now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown turn {turn_id!r}")
            record = dict(row)
            record.update(
                {
                    "ended_at": ended_at,
                    "reply": reply,
                    "outcome": outcome,
                    "route": route or record["route"],
                    "error": error,
                    "plan": plan,
                    "provider": provider,
                    "model": model,
                    "prompt_tokens": tokens[0],
                    "completion_tokens": tokens[1],
                    "total_tokens": tokens[2],
                    "duration_ms": duration_ms,
                    "truncated": 1 if truncated else 0,
                    "evidence_json": json.dumps(evidence or []),
                }
            )
            proof = _proof(record)
            connection.execute(
                "UPDATE agent_turns SET ended_at = ?, reply = ?, outcome = ?, "
                "route = ?, error = ?, plan = ?, provider = ?, model = ?, "
                "prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, "
                "duration_ms = ?, truncated = ?, evidence_json = ?, proof_hash = ? "
                "WHERE tenant_id = ? AND id = ?",
                (
                    ended_at,
                    reply,
                    outcome,
                    record["route"],
                    error,
                    plan,
                    provider,
                    model,
                    tokens[0],
                    tokens[1],
                    tokens[2],
                    duration_ms,
                    1 if truncated else 0,
                    record["evidence_json"],
                    proof,
                    self.tenant_id,
                    turn_id,
                ),
            )
            steps = connection.execute(
                "SELECT COUNT(*) FROM agent_steps WHERE tenant_id = ? AND turn_id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()[0]
        # Anchor the proof in the global chain AFTER the row is final.
        self._audit.append(
            "agent.turn.completed",
            "agent_turn",
            turn_id,
            {
                "session": record["session_id"],
                "turn": record["turn_index"],
                "route": record["route"],
                "outcome": outcome,
                "model": model or "",
                # "tokens" would trip the audit log's secret-key guard; the
                # value is a spend counter, not a credential.
                "spend": tokens[2],
                "steps": int(steps),
                "proof": proof,
            },
            tenant_id=self.tenant_id,
        )

    # ---- reading ---------------------------------------------------------
    def turn(self, turn_id: str) -> dict[str, Any]:
        """One turn with its steps, oldest step first."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown turn {turn_id!r}")
            steps = connection.execute(
                "SELECT * FROM agent_steps WHERE tenant_id = ? AND turn_id = ? "
                "ORDER BY seq",
                (self.tenant_id, turn_id),
            ).fetchall()
        record = dict(row)
        record["steps"] = [dict(step) for step in steps]
        return record

    def turns(self, since: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Turns oldest-first, optionally since an ISO timestamp."""
        with self.database.connection() as connection:
            if since:
                rows = connection.execute(
                    "SELECT * FROM agent_turns WHERE tenant_id = ? AND started_at >= ? "
                    "ORDER BY started_at, turn_index LIMIT ?",
                    (self.tenant_id, since, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM agent_turns WHERE tenant_id = ? "
                    "ORDER BY started_at DESC, turn_index DESC LIMIT ?",
                    (self.tenant_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
        return [dict(row) for row in rows]

    def recent_conversation(self, limit: int = 12) -> list[tuple[str, str]]:
        """The last turns as (role, content) pairs for the model's context."""
        pairs: list[tuple[str, str]] = []
        for row in self.turns(limit=limit):
            if row["reply"]:  # skip turns that never produced a reply
                pairs.append(("user", row["user_text"][:4000]))
                pairs.append(("assistant", row["reply"][:4000]))
        return pairs[-limit * 2 :]

    def add_feedback(
        self, turn_id: str, verdict: str, reason: str = "", source: str = "user"
    ) -> None:
        """Record the founder's judgement of a turn."""
        if verdict not in ("good", "pushback"):
            raise ValueError("verdict must be 'good' or 'pushback'")
        with self.database.transaction() as connection:
            exists = connection.execute(
                "SELECT 1 FROM agent_turns WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            if exists is None:
                raise ValueError(f"unknown turn {turn_id!r}")
            connection.execute(
                "INSERT INTO agent_feedback ("
                "id, tenant_id, turn_id, verdict, reason, source, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.tenant_id,
                    turn_id,
                    verdict,
                    reason,
                    source,
                    _now(),
                ),
            )
        self._audit.append(
            "agent.feedback",
            "agent_turn",
            turn_id,
            {"verdict": verdict, "source": source},
            tenant_id=self.tenant_id,
        )

    # ---- the report ------------------------------------------------------
    def report(self, period: str = "7d") -> dict[str, Any]:
        """Deterministic metrics for a period. Every number is SQL-derived."""
        since = _since(period)
        turns = self.turns(since=since, limit=100000)
        turn_ids = [row["id"] for row in turns]
        total = len(turns)

        outcomes: dict[str, int] = {}
        for row in turns:
            outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
        succeeded = outcomes.get("answered", 0) + outcomes.get("acted", 0)
        truncated = sum(int(row["truncated"]) for row in turns)

        tool_calls: dict[str, dict[str, int]] = {}
        steps_per_success: list[int] = []
        with self.database.connection() as connection:
            for row in turns:
                steps = connection.execute(
                    "SELECT action, ok, kind FROM agent_steps "
                    "WHERE tenant_id = ? AND turn_id = ? AND kind = 'tool_call'",
                    (self.tenant_id, row["id"]),
                ).fetchall()
                if row["outcome"] in ("answered", "acted"):
                    steps_per_success.append(len(steps))
                for step in steps:
                    bucket = tool_calls.setdefault(
                        step["action"], {"total": 0, "failed": 0}
                    )
                    bucket["total"] += 1
                    bucket["failed"] += 0 if step["ok"] else 1
            feedback = connection.execute(
                "SELECT turn_id, verdict FROM agent_feedback WHERE tenant_id = ? "
                "AND created_at >= ?",
                (self.tenant_id, since),
            ).fetchall()

        pushback = sum(1 for f in feedback if f["verdict"] == "pushback")
        tokens_by_outcome: dict[str, list[int]] = {}
        for row in turns:
            tokens_by_outcome.setdefault(row["outcome"], []).append(
                int(row["total_tokens"])
            )

        intents: dict[str, list[dict[str, Any]]] = {}
        for row in turns:
            key = _normalize_intent(row["user_text"])
            if key:
                intents.setdefault(key, []).append(row)
        repeated = {
            key: [r["id"] for r in rows]
            for key, rows in intents.items()
            if len(rows) >= 2
            and any(r["outcome"] not in ("answered", "acted") for r in rows)
        }
        recovered = {
            key: ids
            for key, ids in repeated.items()
            if rows_succeeded_later(intents[key])
        }

        return {
            "period": period,
            "since": since,
            "turns": total,
            "outcomes": outcomes,
            "success_rate": (succeeded / total) if total else 0.0,
            "truncation_rate": (truncated / total) if total else 0.0,
            "tool_calls": tool_calls,
            "tool_failure_rate": {
                action: b["failed"] / b["total"]
                for action, b in tool_calls.items()
                if b["total"]
            },
            "pushback_rate": (pushback / total) if total else 0.0,
            "pushback_turns": [
                f["turn_id"] for f in feedback if f["verdict"] == "pushback"
            ],
            "mean_steps_success": (
                sum(steps_per_success) / len(steps_per_success)
                if steps_per_success
                else 0.0
            ),
            "tokens_per_outcome": {
                outcome: sum(values) / len(values)
                for outcome, values in tokens_by_outcome.items()
                if values
            },
            "repeated_intents": repeated,
            "recovered": recovered,
            "turn_ids": turn_ids,
        }

    # ---- recommendations ---------------------------------------------------
    def recommend(self, period: str = "7d") -> list[dict[str, Any]]:
        """Deterministic recommendation rules. Each cites the turns behind it."""
        metrics = self.report(period)
        rules: list[dict[str, Any]] = []

        if metrics["truncation_rate"] > 0:
            rules.append(
                {
                    "kind": "config",
                    "title": "Raise the cloud reply budget",
                    "body": (
                        f"{metrics['truncation_rate']:.0%} of turns in {period} were cut "
                        "off by the token limit. Raise cloud_max_tokens in settings."
                    ),
                    "evidence": {
                        "turns": metrics["turn_ids"],
                        "metric": "truncation_rate",
                    },
                }
            )

        for action, rate in metrics["tool_failure_rate"].items():
            bucket = metrics["tool_calls"].get(action, {})
            if rate >= 0.5 and bucket.get("total", 0) >= 2:
                rules.append(
                    {
                        "kind": "tool",
                        "title": f"Fix the failing tool: {action}",
                        "body": (
                            f"{action} failed {bucket['failed']} of {bucket['total']} "
                            f"calls in {period}. Fix the tool before anything else."
                        ),
                        "evidence": {
                            "turns": metrics["turn_ids"],
                            "metric": f"tool_failure_rate:{action}",
                        },
                    }
                )

        # Pushback on turns that used no tool call at all -> the model answered
        # from thin air instead of checking.
        no_tool_pushback: list[str] = []
        with self.database.connection() as connection:
            for turn_id in metrics["pushback_turns"]:
                count = connection.execute(
                    "SELECT COUNT(*) FROM agent_steps WHERE tenant_id = ? "
                    "AND turn_id = ? AND kind = 'tool_call'",
                    (self.tenant_id, turn_id),
                ).fetchone()[0]
                if count == 0:
                    no_tool_pushback.append(turn_id)
        if no_tool_pushback:
            rules.append(
                {
                    "kind": "prompt",
                    "title": "Answer only after checking",
                    "body": (
                        f"{len(no_tool_pushback)} pushed-back turn(s) used no tool at "
                        "all. Strengthen the rule: answer only after a tool call or an "
                        "explicit 'I don't know'."
                    ),
                    "evidence": {
                        "turns": no_tool_pushback,
                        "metric": "pushback_no_tool",
                    },
                }
            )

        for intent, ids in metrics["repeated_intents"].items():
            if len(ids) >= 3 and intent not in metrics["recovered"]:
                rules.append(
                    {
                        "kind": "skill",
                        "title": f"Recurring failure: {intent[:60]}",
                        "body": (
                            f"The same request appeared {len(ids)} times in {period} "
                            "without ever succeeding. Consider a skill or plugin for it."
                        ),
                        "evidence": {"turns": ids, "metric": "repeated_intents"},
                    }
                )

        if metrics["turns"] >= 50 and metrics["mean_steps_success"] > 8:
            rules.append(
                {
                    "kind": "prompt",
                    "title": "Plans are too vague",
                    "body": (
                        f"Successful turns averaged {metrics['mean_steps_success']:.1f} "
                        "steps. Sharpen the plan-first rule in the work loop."
                    ),
                    "evidence": {
                        "turns": metrics["turn_ids"],
                        "metric": "mean_steps_success",
                    },
                }
            )

        # Persist new recommendations; keep one open row per kind+title.
        now = _now()
        stored: list[dict[str, Any]] = []
        with self.database.transaction() as connection:
            for rule in rules:
                existing = connection.execute(
                    "SELECT id, status FROM agent_recommendations WHERE tenant_id = ? "
                    "AND kind = ? AND title = ? AND status IN ('proposed', 'approved')",
                    (self.tenant_id, rule["kind"], rule["title"]),
                ).fetchone()
                if existing is not None:
                    stored.append(
                        {**rule, "id": existing["id"], "status": existing["status"]}
                    )
                    continue
                rec_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO agent_recommendations ("
                    "id, tenant_id, created_at, period, kind, title, body, evidence_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        rec_id,
                        self.tenant_id,
                        now,
                        period,
                        rule["kind"],
                        rule["title"],
                        rule["body"],
                        json.dumps(rule["evidence"]),
                    ),
                )
                stored.append({**rule, "id": rec_id, "status": "proposed"})
        return stored

    def recommendations(self, status: str | None = None) -> list[dict[str, Any]]:
        """Stored recommendations, newest first."""
        with self.database.connection() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM agent_recommendations WHERE tenant_id = ? AND status = ? "
                    "ORDER BY created_at DESC",
                    (self.tenant_id, status),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM agent_recommendations WHERE tenant_id = ? "
                    "ORDER BY created_at DESC",
                    (self.tenant_id,),
                ).fetchall()
        return [dict(row) for row in rows]

    def decide(self, rec_id: str, decision: str, note: str = "") -> dict[str, Any]:
        """The founder approves or rejects a recommendation. Never self-applied."""
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM agent_recommendations WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, rec_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown recommendation {rec_id!r}")
            if row["status"] not in ("proposed", "approved", "rejected"):
                raise ValueError(f"recommendation already {row['status']}")
            connection.execute(
                "UPDATE agent_recommendations SET status = ?, decided_at = ?, "
                "decision_note = ? WHERE tenant_id = ? AND id = ?",
                (decision, _now(), note, self.tenant_id, rec_id),
            )
        self._audit.append(
            "agent.recommendation.decision",
            "agent_recommendation",
            rec_id,
            {"decision": decision},
            tenant_id=self.tenant_id,
        )
        return {"id": rec_id, "status": decision}

    # ---- proof -----------------------------------------------------------
    def verify(self) -> dict[str, Any]:
        """Verify the audit chain, then recompute every closed turn's proof."""
        chain = self._audit.verify()
        checked = 0
        unclosed = 0
        mismatch: dict[str, str] | None = None
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ?", (self.tenant_id,)
            ).fetchall()
        audit_entries = {
            entry.entity_id: entry
            for entry in self._audit.list_entries(
                tenant_id=self.tenant_id, limit=100000
            )
            if entry.action == "agent.turn.completed"
        }
        for row in rows:
            if row["ended_at"] is None:
                unclosed += 1
                continue
            checked += 1
            entry = audit_entries.get(row["id"])
            expected = _proof(dict(row))
            if (
                expected != row["proof_hash"]
                or entry is None
                or entry.payload.get("proof") != row["proof_hash"]
            ):
                mismatch = {"turn_id": row["id"]}
                break
        return {
            "chain_valid": chain.valid,
            "entries_checked": chain.entries_checked,
            "turns_checked": checked,
            "unclosed": unclosed,
            "valid": chain.valid and mismatch is None,
            "mismatch": mismatch,
        }


def rows_succeeded_later(rows: list[dict[str, Any]]) -> bool:
    """True when an intent failed first and later succeeded."""
    seen_failure = False
    for row in rows:
        ok = row["outcome"] in ("answered", "acted")
        if not ok:
            seen_failure = True
        elif seen_failure:
            return True
    return False
