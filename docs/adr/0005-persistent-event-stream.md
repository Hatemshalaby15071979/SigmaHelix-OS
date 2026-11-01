# ADR 0005: Add an ordered persistent event stream

- Status: Accepted
- Date: 2026-11-02

## Context

The core event table already persists immutable events, but timestamp ordering is not a reliable replay cursor: timestamps can tie or be supplied out of order. The in-process publisher also needs a durable ordering shared with direct repository inserts.

## Decision

Schema v3 creates an append-only `event_stream` with an autoincrement sequence and event ID. An SQLite insert trigger mirrors every event in the same transaction, and migration backfills existing v2 events in `(occurred_at, id)` order. `EventBus` publishes through the existing event repository, dispatches only after commit, and exposes sequence-based replay.

## Consequences

- Publish order and replay cursors are stable even when event timestamps tie.
- A failed subscriber does not undo the persisted event; the event envelope can be replayed.
- Subscribers are process-local and synchronous. Durable consumer checkpoints remain the caller's responsibility.
- Downgrade to v2 drops only the derived sequence index; the source event rows remain.
