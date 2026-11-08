# ADR 0011 — Record every turn in a hash-proven ledger and derive recommendations from it

- **Status:** accepted
- **Date:** 2026-11-08

## Context

Tommy's turns were not durable. Chat history lived in RAM (last 8 turns, each cut
to 400 characters) and vanished on restart, so the model could truthfully say "I
don't have the transcript" and could contradict its own earlier claims. There was
also no way to see *how* a turn reached its answer: the loop recorded a flat list
of step strings that no surface rendered, and cloud replies were capped at 500
tokens, which truncated tool calls mid-JSON and leaked raw
`{"action": ...}` text to the user.

That combination made the agent unauditable and made self-improvement impossible:
there was no record to analyse, no metric to act on, and no evidence behind any
claim about its own performance.

## Decision

1. **One ledger, four tables** (migration v16): `agent_turns`, `agent_steps`,
   `agent_feedback`, `agent_recommendations`. `Agent.process_command` opens a turn
   and closes it in `finally`, so failures are recorded too.
2. **Proof, not a second chain.** Each closed turn's canonical content hash is
   appended to the existing `audit_log` as `agent.turn.completed`. `ledger verify`
   runs `AuditLog.verify()` and recomputes every turn's proof; a mismatch names
   the turn. We deliberately did not build a parallel hash chain — one chain, one
   verifier, one source of truth.
3. **Reports are deterministic.** `Ledger.report()` computes outcomes, success,
   truncation, tool-failure, pushback and repeated-intent metrics in SQL.
   `Ledger.recommend()` applies fixed rules and cites the turn ids behind each
   recommendation. A model may later write prose over that JSON, but it may not
   produce a number.
4. **The founder decides.** Recommendations are `proposed` until `decide()`
   records `approved` or `rejected` (audited). Applying is separate and limited to
   reversible kinds (a setting, a plugin toggle, a user skill file). Anything that
   touches source code becomes a task for the coding agent, never a self-edit.
5. **The reasoning trail is real.** Steps carry the action, arguments, the model's
   own one-line `plan`, duration and result. We do not claim hidden
   chain-of-thought: for models that expose `reasoning_content` it is shown as
   *provider reasoning*; otherwise the plan + tool timeline is the trail.

## Consequences

- Restarting no longer erases the conversation; `_build_messages` reloads the last
  turns from the ledger.
- Every turn costs a handful of small SQLite writes. They are wrapped so a ledger
  failure can never break a reply.
- The ledger is local and never leaves the machine; it is included in backups via
  the required-tables map for v16.
- Deleting a turn is not offered. The tables are append-only by convention, and
  the audit chain makes silent edits detectable.
- "Is Tommy improving?" now has an evidence-based answer: the report shows whether
  truncation, tool failures, pushback and repeated intents are falling. It does
  **not** mean the model trains on the founder's data — no weights change, and any
  style corpus is built only from explicitly approved turns.
