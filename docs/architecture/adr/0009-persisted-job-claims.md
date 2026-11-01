# ADR 0009: Persisted scheduler claims

- Status: accepted
- Date: 2026-11-02

## Context

Time-based work needs durable definitions and duplicate-safe local claims. A
handler may have external effects, so SQLite cannot make invocation and those
effects one atomic transaction.

## Decision

Store scheduled jobs and run slots in schema v6. Claim each slot under an
immediate SQLite transaction with a deterministic ID and a unique tenant/job/
scheduled-time key. Invoke callbacks after commit and persist the terminal
status, event, and audit entry afterward. Inject the clock to make tests
deterministic. Do not persist callback exception messages or secret-like job
payloads.

## Consequences

The claim is at-most-once for each scheduled slot. A process crash after claim
but before callback invocation leaves a `running` record; startup recovery is
specified by P2-004. Callback side effects must be idempotent where practical.
Interval jobs retain their scheduled cadence and process delayed slots without
silently skipping them, at one slot per polling pass.
