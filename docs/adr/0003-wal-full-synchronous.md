# ADR 0003: Use FULL synchronous mode with WAL

- Status: Accepted
- Date: 2026-11-02

## Context

The plan's storage section suggests `synchronous=NORMAL`, while the product's durability requirement says committed state must survive power loss. [SQLite documents](https://www.sqlite.org/pragma.html#pragma_synchronous) that a WAL transaction committed under `NORMAL` may roll back after power loss or a system crash; `FULL` syncs the WAL after each transaction commit.

## Decision

Keep `journal_mode=WAL` and use `synchronous=FULL` on every application connection.

## Consequences

- A successful commit gets the stronger power-loss durability guarantee supported by SQLite's FULL WAL mode.
- Each commit performs an additional WAL sync, trading write throughput for durability.
- The current evidence covers configuration and transactional behavior; actual power-loss behavior depends on the operating system, filesystem, storage device, and is not claimed as hardware-tested.
