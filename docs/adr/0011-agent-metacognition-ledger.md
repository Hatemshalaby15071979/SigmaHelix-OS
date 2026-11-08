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

## Amendment — 2026-11-08: the proof covers the steps, and the founder's word sticks

The original version of this ADR made two claims that the implementation did not
actually honour. A review of the two landed commits found it, and both claims are
now true:

1. *"the audit chain makes silent edits detectable"* was **false** for the two
   richest tables. The proof hashed the turn row only, so editing a step's
   arguments or deleting a step left `ledger verify` reporting `valid: true`, and
   deleting a whole turn removed it from the check entirely — the verifier
   iterated the table it was supposed to be checking. The proof now includes the
   canonical digest of the turn's ordered steps, verification is driven from the
   `agent.turn.completed` anchors (an anchor without a turn is an orphan, a turn
   with two anchors is a duplicate), and the steps, the turn row, the proof and
   the anchor are written in **one transaction**. A closed turn cannot be closed
   twice.
2. *"the founder decides"* was **decorative**. The status guard accepted every
   status, and the recommendation table kept one *open* row per rule — so a
   rejected recommendation came back as a fresh proposal on the next analysis.
   There is now one row per (kind, title) for ever: a rejection sticks until the
   founder reopens it, and decisions follow an explicit transition table that is
   audited with the state each decision came from.

Two consequences of the same review are also now part of the decision:

- **What is stored is redacted.** The founder's text, the reply and every step
  argument pass through `redact_text` before they are written, so a pasted
  credential is never persisted in plaintext.
- **The ledger does not leak to the cloud.** Past turns are replayed into the
  prompt by the local model only. Replaying them to a cloud provider is
  opt-in (`cloud_replay_history`), because persistence must not become standing
  exfiltration of the founder's history.

