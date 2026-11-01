# ADR 0008: Keep recurring series separate from task occurrences

- Status: Accepted
- Date: 2026-11-02

## Context

Completing a recurring task must finish one due date without ending future recurrence. A recurrence definition and a concrete work item have different lifecycles.

## Decision

Schema v5 stores a mutable active series with a recurrence rule and an append-only table linking each `(series, date)` to a normal task. Materialization, occurrence receipt, event, audit entry, and series watermark update commit together. Completion updates only the materialized task and emits an audit/event record; it does not deactivate the series or rewrite the occurrence link.

## Consequences

- Task consumers continue to work with ordinary tasks and due dates.
- Uniqueness plus deterministic IDs makes repeated and concurrent materialization idempotent.
- Pausing controls future materialization; existing tasks and completion history remain.
- Timezone/DST scheduling is not represented by these all-day occurrence dates.
