# ADR 0006: Import one live legacy session atomically

- Status: Accepted
- Date: 2026-11-02

## Context

The legacy desktop prototype stored tasks and notes only in Python lists. The durable core needs an explicit import path if those manager objects are still live during migration. Re-running an importer must not duplicate records or partially import a snapshot.

## Decision

Schema v4 adds an append-only `legacy_imports` receipt keyed by a caller-stable source-session UUID and snapshot SHA-256. The importer validates and hashes a copied task/note snapshot, then inserts deterministic UUID records, the receipt, a persistent event, and an audit entry in one SQLite transaction. A repeat with matching data is a no-op; reusing a session ID for different data is an error.

## Consequences

- A caller must capture a stable session UUID while the legacy managers are alive.
- Legacy recurrence labels are retained as description text until recurrence support exists.
- Source dates had day precision and are represented as midnight UTC.
- The importer does not recover state that disappeared when a legacy process exited.
