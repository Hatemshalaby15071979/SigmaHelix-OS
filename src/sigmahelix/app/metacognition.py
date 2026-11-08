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

from ..core.config import (
    load_settings,
    save_cloud_budget,
    save_plugin_settings,
    suggest_cloud_budget,
)
from ..core.logging import redact_text
from ..core.storage.audit import AuditLog
from ..core.storage.database import Database

DEFAULT_TENANT = "local"

#: Kinds a founder may *apply*. Every other kind is "never auto-applied" per ADR
#: 0011 and the coding brief: applying it would be a consequential side effect, so
#: the founder routes it to the coding agent as a task instead. These are the only
#: kinds that perform a real, reversible action when ``Ledger.apply`` runs.
APPLIABLE_KINDS = frozenset({"config", "skill", "delete_plugin", "update_plugin"})

_PERIOD = re.compile(r"^(\d+)([dhw])$")

#: The largest period a report may look back. Anything bigger is a typo or an
#: attempt to make the server do unbounded work.
_MAX_PERIOD = {"d": 3650, "h": 24 * 365, "w": 520}

#: The recommendation decision flow. A recommendation is decided by the founder
#: and only the founder: nothing here is ever reached by the agent itself.
_DECISION_FLOW = {
    "proposed": {"approved", "rejected"},
    "approved": {"rejected"},
    "rejected": {"approved", "proposed"},
    "applied": set(),
}

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

#: The step columns the proof commits to. A step that is edited, deleted or
#: inserted changes the digest, so the turn proof stops matching.
_STEP_DIGEST_FIELDS = (
    "seq",
    "kind",
    "action",
    "plan",
    "args",
    "summary",
    "ok",
    "duration_ms",
)


class LedgerError(RuntimeError):
    """Raised when the ledger cannot do what it was asked to do."""


class TurnNotFound(LedgerError, ValueError):
    """Raised when a turn id does not exist for this tenant."""


class TurnAlreadyClosed(LedgerError, ValueError):
    """Raised when a closed turn is closed again."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(record: Any) -> bytes:
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()


def _steps_digest(rows: list[Any]) -> str:
    """SHA-256 over the ordered steps of a turn.

    ``rows`` are ``sqlite3.Row`` objects (or dicts) in ``seq`` order. The digest
    is derived from the table, never stored, so it cannot drift from the steps
    it describes.
    """
    canonical = [[row[field] for field in _STEP_DIGEST_FIELDS] for row in rows]
    return hashlib.sha256(_canonical(canonical)).hexdigest()


def _proof(record: dict[str, Any], steps_digest: str = "") -> str:
    """SHA-256 over the canonical turn record (proof field excluded).

    The digest of the turn's steps is part of the proof, so the reasoning
    trail is provable exactly like the reply is.
    """
    fields = {k: record.get(k) for k in _PROOF_FIELDS}
    fields["steps_digest"] = steps_digest
    return hashlib.sha256(_canonical(fields)).hexdigest()


def _legacy_proof(record: dict[str, Any]) -> str:
    """The proof of a turn recorded before the step digest existed.

    Turns written by an earlier version are still verifiable, but their steps
    are not covered by the proof — the verifier reports them as legacy.
    """
    return hashlib.sha256(
        _canonical({k: record.get(k) for k in _PROOF_FIELDS})
    ).hexdigest()


def _since(period: str) -> str:
    match = _PERIOD.match((period or "7d").strip().lower())
    if not match:
        raise ValueError("period must look like 7d, 24h or 2w")
    amount, unit = int(match.group(1)), match.group(2)
    if amount < 1 or amount > _MAX_PERIOD[unit]:
        raise ValueError(f"period must be between 1 and {_MAX_PERIOD[unit]} {unit}")
    delta = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "w": timedelta(weeks=amount),
    }[unit]
    return (datetime.now(UTC) - delta).isoformat()


def _normalize_intent(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return " ".join(w for w in words if w not in _INTENT_STOP_WORDS)


def _slugify(text: str) -> str:
    """A filesystem-safe slug for a recommendation title."""
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:60]


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
                # What the founder typed may contain a credential. It is
                # redacted before it is ever written to disk.
                "user_text": redact_text(user_text),
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
                # Always a JSON array, even before the turn closes, so callers
                # never have to special-case an unclosed turn's evidence shape.
                "evidence_json": "[]",
            }
            connection.execute(
                "INSERT INTO agent_turns ("
                "id, tenant_id, session_id, turn_index, started_at, user_text, "
                "route, model_mode, evidence_json, proof_hash"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_id,
                    self.tenant_id,
                    session_id,
                    record["turn_index"],
                    record["started_at"],
                    record["user_text"],
                    route,
                    model_mode,
                    record["evidence_json"],
                    _proof(record, _steps_digest([])),
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
                    redact_text(plan),
                    redact_text(args),
                    redact_text(summary),
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
        steps: list[dict[str, Any]] | None = None,
    ) -> None:
        """Finish a turn in ONE transaction.

        The steps, the turn row, its proof and the audit anchor are written
        together. A turn is therefore never half-recorded, never unanchored and
        never committed twice: the whole turn costs one commit.
        """
        ended_at = _now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            if row is None:
                raise TurnNotFound(f"unknown turn {turn_id!r}")
            if row["ended_at"] is not None:
                raise TurnAlreadyClosed(f"turn {turn_id!r} is already closed")
            record = dict(row)
            record.update(
                {
                    "ended_at": ended_at,
                    "reply": redact_text(reply),
                    "outcome": outcome,
                    "route": route or record["route"],
                    "error": error,
                    "plan": redact_text(plan),
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
            if steps:
                self._write_steps(connection, turn_id, steps)
            step_rows = connection.execute(
                "SELECT * FROM agent_steps WHERE tenant_id = ? AND turn_id = ? "
                "ORDER BY seq",
                (self.tenant_id, turn_id),
            ).fetchall()
            # The proof commits to the steps as well as to the reply.
            proof = _proof(record, _steps_digest(step_rows))
            connection.execute(
                "UPDATE agent_turns SET ended_at = ?, reply = ?, outcome = ?, "
                "route = ?, error = ?, plan = ?, provider = ?, model = ?, "
                "prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, "
                "duration_ms = ?, truncated = ?, evidence_json = ?, proof_hash = ? "
                "WHERE tenant_id = ? AND id = ? AND ended_at IS NULL",
                (
                    ended_at,
                    record["reply"],
                    outcome,
                    record["route"],
                    error,
                    record["plan"],
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
            # Anchor the proof in the global chain in the SAME transaction, so a
            # closed turn can never exist without its anchor.
            self._audit.append_in_transaction(
                connection,
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
                    "steps": len(step_rows),
                    "proof": proof,
                },
                tenant_id=self.tenant_id,
            )

    def _write_steps(
        self,
        connection: Any,
        turn_id: str,
        steps: list[dict[str, Any]],
    ) -> None:
        """Write a turn's steps, continuing the sequence of the ones already there."""
        next_seq = connection.execute(
            "SELECT COALESCE(MAX(seq) + 1, 1) FROM agent_steps "
            "WHERE tenant_id = ? AND turn_id = ?",
            (self.tenant_id, turn_id),
        ).fetchone()[0]
        for step in steps:
            connection.execute(
                "INSERT INTO agent_steps ("
                "id, tenant_id, turn_id, seq, kind, action, plan, args, "
                "summary, ok, duration_ms, payload_json, occurred_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.tenant_id,
                    turn_id,
                    int(next_seq),
                    "tool_call",
                    str(step.get("action") or ""),
                    redact_text(str(step.get("plan") or "")),
                    redact_text(str(step.get("args") or "")),
                    redact_text(str(step.get("summary") or "")),
                    1 if step.get("ok") else 0,
                    int(step.get("duration_ms") or 0),
                    "{}",
                    _now(),
                ),
            )
            next_seq = int(next_seq) + 1

    # ---- reading ---------------------------------------------------------
    def turn(self, turn_id: str) -> dict[str, Any]:
        """One turn with its steps, oldest step first."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, turn_id),
            ).fetchone()
            if row is None:
                raise TurnNotFound(f"unknown turn {turn_id!r}")
            steps = connection.execute(
                "SELECT * FROM agent_steps WHERE tenant_id = ? AND turn_id = ? "
                "ORDER BY seq",
                (self.tenant_id, turn_id),
            ).fetchall()
        record = dict(row)
        record["steps"] = [dict(step) for step in steps]
        return record

    def turns(
        self, since: str | None = None, limit: int | None = 50
    ) -> list[dict[str, Any]]:
        """Turns oldest-first, optionally since an ISO timestamp.

        ``limit=None`` returns *every* matching turn (used by ``report`` so a
        busy period is never silently truncated to the newest ``limit`` rows).
        """
        params: list[Any] = [self.tenant_id]
        if since:
            sql = (
                "SELECT * FROM agent_turns WHERE tenant_id = ? AND started_at >= ? "
                "ORDER BY started_at, turn_index"
            )
            params.append(since)
        else:
            sql = (
                "SELECT * FROM agent_turns WHERE tenant_id = ? "
                "ORDER BY started_at DESC, turn_index DESC"
            )
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.database.connection() as connection:
            rows = connection.execute(sql, params).fetchall()
        result = [dict(row) for row in rows]
        if not since:
            result = list(reversed(result))
        return result

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
                raise TurnNotFound(f"unknown turn {turn_id!r}")
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
            # Same transaction as the row it describes.
            self._audit.append_in_transaction(
                connection,
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
        # Every turn in the period, oldest first. No sliding-window cap: a busy
        # period must not silently drop its newest turns.
        turns = self.turns(since=since, limit=None)
        total = len(turns)
        if total == 0:
            # No turns means every derived metric is zero/empty; short-circuit so
            # the aggregate query below has an empty join target.
            return {
                "period": period,
                "since": since,
                "turns": 0,
                "outcomes": {},
                "success_rate": 0.0,
                "truncation_rate": 0.0,
                "tool_calls": {},
                "tool_failure_rate": {},
                "pushback_rate": 0.0,
                "pushback_turns": [],
                "mean_steps_success": 0.0,
                "tokens_per_outcome": {},
                "repeated_intents": {},
                "recovered": {},
            }

        outcome_by_id = {row["id"]: row["outcome"] for row in turns}
        outcomes: dict[str, int] = {}
        for row in turns:
            outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
        succeeded = outcomes.get("answered", 0) + outcomes.get("acted", 0)
        truncated = sum(int(row["truncated"]) for row in turns)

        # One aggregate pass over the steps table instead of one query per turn.
        tool_calls: dict[str, dict[str, int]] = {}
        steps_per_success: dict[str, int] = {}
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT s.turn_id AS turn_id, s.action AS action, "
                "SUM(CASE WHEN s.ok = 0 THEN 1 ELSE 0 END) AS failed, "
                "COUNT(*) AS total "
                "FROM agent_steps s "
                "JOIN agent_turns t ON t.id = s.turn_id AND t.tenant_id = s.tenant_id "
                "WHERE s.tenant_id = ? AND s.kind = 'tool_call' AND t.started_at >= ? "
                "GROUP BY s.turn_id, s.action",
                (self.tenant_id, since),
            ).fetchall()
            for step in rows:
                action = step["action"]
                bucket = tool_calls.setdefault(action, {"total": 0, "failed": 0})
                bucket["total"] += int(step["total"])
                bucket["failed"] += int(step["failed"])
                tid = step["turn_id"]
                steps_per_success[tid] = steps_per_success.get(tid, 0) + int(
                    step["total"]
                )
            # Pushback is counted on turns that *started* in the period (joined
            # on started_at), not on feedback timestamps (created_at). Counting
            # feedback rows by created_at let a late verdict on an old turn — or
            # two verdicts on one turn — push the rate past 1. DISTINCT keeps one
            # entry per turn, so pushback can never exceed the period's turn count.
            pushback_rows = connection.execute(
                "SELECT DISTINCT f.turn_id AS turn_id "
                "FROM agent_feedback f "
                "JOIN agent_turns t ON t.id = f.turn_id AND t.tenant_id = f.tenant_id "
                "WHERE f.tenant_id = ? AND f.verdict = 'pushback' "
                "AND t.started_at >= ?",
                (self.tenant_id, since),
            ).fetchall()

        pushback_turns = [row["turn_id"] for row in pushback_rows]
        pushback = len(pushback_turns)

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
        success_step_counts = [
            steps_per_success.get(tid, 0)
            for tid in outcome_by_id
            if outcome_by_id[tid] in ("answered", "acted")
        ]

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
            "pushback_turns": pushback_turns,
            "mean_steps_success": (
                sum(success_step_counts) / len(success_step_counts)
                if success_step_counts
                else 0.0
            ),
            "tokens_per_outcome": {
                outcome: sum(values) / len(values)
                for outcome, values in tokens_by_outcome.items()
                if values
            },
            "repeated_intents": repeated,
            "recovered": recovered,
        }

    # ---- recommendations ---------------------------------------------------
    def _period_turn_ids(self, since: str) -> list[str]:
        """Every turn id that started since ``since``, for evidence lists."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id FROM agent_turns WHERE tenant_id = ? AND started_at >= ?",
                (self.tenant_id, since),
            ).fetchall()
        return [row["id"] for row in rows]

    def _pushback_without_tools(self, pushback_turns: list[str]) -> list[str]:
        """Pushback turns that ran no tool call — a model answering from air."""
        if not pushback_turns:
            return []
        placeholders = ",".join("?" for _ in pushback_turns)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT turn_id FROM agent_steps WHERE tenant_id = ? "
                f"AND kind = 'tool_call' AND turn_id IN ({placeholders})",
                (self.tenant_id, *pushback_turns),
            ).fetchall()
        had_tool = {row["turn_id"] for row in rows}
        return [tid for tid in pushback_turns if tid not in had_tool]

    def recommend(
        self, period: str = "7d", metrics: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Deterministic recommendation rules. Each cites the turns behind it.

        When ``metrics`` is supplied (e.g. by ``analyze``) the report is not
        recomputed — ``analyze`` already built it once.
        """
        if metrics is None:
            metrics = self.report(period)
        all_turn_ids = self._period_turn_ids(_since(period))
        rules: list[dict[str, Any]] = []

        if metrics["truncation_rate"] > 0:
            new_budget = suggest_cloud_budget(load_settings().cloud_max_tokens)
            rules.append(
                {
                    "kind": "config",
                    "title": "Raise the cloud reply budget",
                    "body": (
                        f"{metrics['truncation_rate']:.0%} of turns in {period} were cut "
                        f"off by the token limit. Raise cloud_max_tokens to {new_budget}."
                    ),
                    "evidence": {
                        "turns": all_turn_ids,
                        "metric": "truncation_rate",
                        "setting": "cloud_max_tokens",
                        "value": new_budget,
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
                            "turns": all_turn_ids,
                            "metric": f"tool_failure_rate:{action}",
                        },
                    }
                )

        # Pushback on turns that used no tool call at all -> the model answered
        # from thin air instead of checking. One aggregate query, not one per turn.
        no_tool_pushback = self._pushback_without_tools(metrics["pushback_turns"])
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
                        "turns": all_turn_ids,
                        "metric": "mean_steps_success",
                    },
                }
            )

        # Persist new recommendations; one row per (kind, title) for ever.
        # A recommendation the founder rejected is NOT re-proposed: the row
        # keeps its status and only the founder can reopen it.
        now = _now()
        stored: list[dict[str, Any]] = []
        with self.database.transaction() as connection:
            for rule in rules:
                existing = connection.execute(
                    "SELECT id, status FROM agent_recommendations WHERE tenant_id = ? "
                    "AND kind = ? AND title = ? "
                    "ORDER BY created_at DESC LIMIT 1",
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
        """The founder approves, rejects or reopens a recommendation.

        Never self-applied. The transition must be one the founder is allowed
        to make, and every decision is anchored in the audit chain.
        """
        target = {"approve": "approved", "reject": "rejected", "reopen": "proposed"}
        if decision in target:
            decision = target[decision]
        if decision not in ("approved", "rejected", "proposed"):
            raise ValueError("decision must be 'approved', 'rejected' or 'reopen'")
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM agent_recommendations WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, rec_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown recommendation {rec_id!r}")
            current = row["status"]
            if decision not in _DECISION_FLOW.get(current, set()):
                raise ValueError(
                    f"recommendation is {current}; it cannot become {decision}"
                )
            connection.execute(
                "UPDATE agent_recommendations SET status = ?, decided_at = ?, "
                "decision_note = ? WHERE tenant_id = ? AND id = ?",
                (decision, _now(), note, self.tenant_id, rec_id),
            )
            self._audit.append_in_transaction(
                connection,
                "agent.recommendation.decision",
                "agent_recommendation",
                rec_id,
                {"decision": decision, "from": current},
                tenant_id=self.tenant_id,
            )
        return {"id": rec_id, "status": decision}

    def apply(self, rec_id: str, note: str = "") -> dict[str, Any]:
        """Apply an approved recommendation. Founder-only, whitelisted, audited.

        Only ``approved`` recommendations can be applied, and only the kinds in
        :data:`APPLIABLE_KINDS` perform a real, reversible side effect. Anything
        else — ``prompt``, ``tool``, ``new_plugin`` — is "never auto-applied" per
        ADR 0011 and the coding brief: applying it would be a consequential side
        effect, so the founder routes it to the coding agent as a task instead.
        Every application is recorded in the audit chain with what it did.
        """
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT id, status, kind, title, body, evidence_json FROM "
                "agent_recommendations WHERE tenant_id = ? AND id = ?",
                (self.tenant_id, rec_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown recommendation {rec_id!r}")
            if row["status"] != "approved":
                raise ValueError(
                    f"recommendation is {row['status']}; only an approved "
                    "recommendation can be applied"
                )
            kind = row["kind"]
            if kind not in APPLIABLE_KINDS:
                raise LedgerError(
                    f"kind {kind!r} is not auto-applied; create a task for the "
                    "coding agent instead"
                )
            effect = self._apply_effect(kind, row)
            connection.execute(
                "UPDATE agent_recommendations SET status = 'applied', "
                "decided_at = ?, decision_note = ? WHERE tenant_id = ? AND id = ?",
                (_now(), note, self.tenant_id, rec_id),
            )
            self._audit.append_in_transaction(
                connection,
                "agent.recommendation.applied",
                "agent_recommendation",
                rec_id,
                {"kind": kind, "effect": effect},
                tenant_id=self.tenant_id,
            )
        return {"id": rec_id, "status": "applied", "effect": effect}

    def _apply_effect(self, kind: str, row: Any) -> str:
        """Perform the reversible side effect for an appliable kind; return a log."""
        evidence = json.loads(row["evidence_json"] or "{}")
        if kind == "skill":
            return self._apply_skill(row, evidence)
        if kind == "config":
            return self._apply_config(evidence)
        if kind in ("delete_plugin", "update_plugin"):
            return self._apply_plugin(kind, evidence)
        raise LedgerError(f"kind {kind!r} is not auto-applied")

    def _apply_skill(self, row: Any, evidence: dict[str, Any]) -> str:
        """Write the recommendation as a reversible skill file under the user dir."""
        from .skills import user_skills_dir

        directory = user_skills_dir()
        directory.mkdir(parents=True, exist_ok=True)
        slug = _slugify(row["title"]) or row["id"]
        path = directory / f"{slug}.md"
        content = f"# {row['title']}\n\n{row['body'] or ''}\n"
        turns = evidence.get("turns") or []
        if turns:
            content += (
                "\n## Evidence (turn ids)\n\n"
                + "\n".join(f"- {turn}" for turn in turns[:50])
                + "\n"
            )
        path.write_text(content, encoding="utf-8")
        return f"wrote skill file {path}"

    def _apply_config(self, evidence: dict[str, Any]) -> str:
        """Write the recommended configuration value (currently cloud_max_tokens)."""
        setting = evidence.get("setting")
        if setting != "cloud_max_tokens":
            raise LedgerError(
                f"config recommendation for {setting!r} cannot be applied"
            )
        value = evidence.get("value")
        if not isinstance(value, int) or isinstance(value, bool):
            raise LedgerError("config recommendation has no integer value")
        save_cloud_budget(value)
        return f"set {setting}={value}"

    def _apply_plugin(self, kind: str, evidence: dict[str, Any]) -> str:
        """Enable or disable a plugin id in the persisted settings."""
        plugin_id = evidence.get("plugin_id")
        if not plugin_id:
            raise LedgerError("plugin recommendation has no plugin_id")
        settings = load_settings()
        enabled = list(settings.plugins_enabled or [])
        if kind == "update_plugin":
            if plugin_id not in enabled:
                enabled.append(plugin_id)
        else:  # delete_plugin
            enabled = [item for item in enabled if item != plugin_id]
        save_plugin_settings(enabled)
        return f"{kind} {plugin_id}"

    # ---- proof -----------------------------------------------------------
    def verify(self) -> dict[str, Any]:
        """Verify the audit chain, then recompute every closed turn's proof.

        The anchors drive the check, not the table: every anchor must have a
        live closed turn, every closed turn must have exactly one anchor, and
        the proof must match the row, the anchor AND the digest of the turn's
        steps. A deleted turn, an edited step and a re-anchored turn are all
        failures.
        """
        chain = self._audit.verify()
        checked = 0
        unclosed = 0
        legacy = 0
        mismatch: dict[str, str] | None = None
        orphans: list[str] = []
        duplicates: list[str] = []

        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_turns WHERE tenant_id = ?", (self.tenant_id,)
            ).fetchall()
            step_rows = connection.execute(
                "SELECT * FROM agent_steps WHERE tenant_id = ? ORDER BY turn_id, seq",
                (self.tenant_id,),
            ).fetchall()
            anchor_rows = connection.execute(
                "SELECT entity_id, payload_json FROM audit_log "
                "WHERE tenant_id = ? AND action = 'agent.turn.completed' "
                "ORDER BY sequence",
                (self.tenant_id,),
            ).fetchall()

        steps_by_turn: dict[str, list[Any]] = {}
        for step in step_rows:
            steps_by_turn.setdefault(step["turn_id"], []).append(step)

        anchors: dict[str, list[dict[str, Any]]] = {}
        for anchor in anchor_rows:
            anchors.setdefault(anchor["entity_id"], []).append(
                json.loads(anchor["payload_json"])
            )

        for row in rows:
            if row["ended_at"] is None:
                unclosed += 1
                continue
            checked += 1
            entries = anchors.get(row["id"], [])
            if not entries:
                mismatch = {"turn_id": row["id"], "reason": "no audit anchor"}
                break
            if len(entries) > 1:
                duplicates.append(row["id"])
                mismatch = {"turn_id": row["id"], "reason": "duplicate audit anchor"}
                break
            expected = _proof(
                dict(row), _steps_digest(steps_by_turn.get(row["id"], []))
            )
            if expected != row["proof_hash"]:
                # A turn recorded before the step digest existed: still
                # verifiable, but its steps are not covered by the proof.
                if _legacy_proof(dict(row)) == row["proof_hash"]:
                    legacy += 1
                else:
                    mismatch = {"turn_id": row["id"], "reason": "proof mismatch"}
                    break
            elif entries[0].get("proof") != row["proof_hash"]:
                mismatch = {"turn_id": row["id"], "reason": "anchor mismatch"}
                break

        if mismatch is None:
            # The chain remembers a turn the table no longer has: it was deleted.
            live = {row["id"] for row in rows}
            orphans = [turn_id for turn_id in anchors if turn_id not in live]
            if orphans:
                mismatch = {"turn_id": orphans[0], "reason": "deleted turn"}

        return {
            "chain_valid": chain.valid,
            "entries_checked": chain.entries_checked,
            "turns_checked": checked,
            "unclosed": unclosed,
            "legacy": legacy,
            "complete": unclosed == 0 and not orphans and not duplicates,
            "orphans": orphans,
            "duplicates": duplicates,
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
