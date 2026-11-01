# ADR 0004: Store a globally ordered hash-chained audit log

- Status: Accepted
- Date: 2026-11-02

## Context

The durable core needs an append-only audit history that can detect record edits and partial deletion. The existing domain event table is not enough to prove event order or that a row's content has stayed unchanged.

## Decision

Add schema v2 `audit_log` with one monotonically increasing global sequence. Each SHA-256 digest covers a version marker, sequence, ID, tenant, action, entity reference, timestamp, canonical JSON payload, and previous digest. Serialize writers with the existing immediate SQLite transaction. Keep SQLite update/delete triggers and verify the full chain from a fixed all-zero genesis digest.

## Consequences

- Concurrent appends form one deterministic total order across tenants.
- `append_in_transaction()` supports atomic audit/domain updates.
- Downgrade to v1 is refused while audit rows exist.
- The chain detects modified or partial history but does not defeat a privileged attacker who can replace the whole database and recompute every digest. P1-006 does not add external anchoring or signatures.
