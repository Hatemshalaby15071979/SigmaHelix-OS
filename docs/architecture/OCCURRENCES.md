# Recurring task occurrence materialization

Schema v5 stores a recurring task definition in `task_series` and each materialized date in the append-only `task_occurrences` table. A unique `(tenant_id, series_id, scheduled_for)` key and deterministic UUIDv5 task IDs prevent duplicate materialization. Each occurrence links to an ordinary task row; its due date is midnight UTC for the all-day calendar date.

`OccurrenceService.materialize()` advances a date watermark in the same write transaction as the task, occurrence receipt, persistent event, and audit record. A full batch advances only to its last generated date, so callers can repeat the same `through` date until the range is drained. Repeated materialization does not create duplicates. Completion changes one task's status and records its event/audit entry; the series remains active and later dates can still be materialized. Pausing a series prevents future materialization without changing existing occurrences.

Timezone-aware wall-clock alarms, snooze, notifications, and scheduler recovery are separate P2 tasks.
