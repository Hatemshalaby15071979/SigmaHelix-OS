# ADR 0007: Define deterministic date recurrence semantics

- Status: Accepted
- Date: 2026-11-02

## Context

The plan requires daily, weekly, monthly, weekday, and every-N rules, including month-end and leap-day behavior. No prior persisted recurrence schema or dependency exists.

## Decision

Implement a dependency-free, pure `date` rule model. Intervals are positive integers; weekly rules default to the anchor weekday; weekday selection is supported on daily/weekly rules; monthly rules clamp the selected day to the month's last calendar day. `count` is measured from the anchor and `end_date` is inclusive. Timezone/DST conversion is left to the scheduler.

## Consequences

- The engine is deterministic and can be property-tested independently from persistence and clocks.
- The chosen clamp behavior avoids skipping a monthly occurrence for day 29, 30, or 31.
- All-day date semantics do not yet represent a wall-clock alarm; P2-003 will add clock and timezone behavior.
