# Alarm actions

Each inbox notification has one durable alarm state: `pending`, `snoozed`,
`rescheduled`, or `dismissed`. Snoozing and rescheduling atomically create a
one-shot scheduler job and append an action record; a later dismissal disables
that job. The job creates a new deduplicated inbox item when due. The original
notification and each state transition remain in the database and audit chain.

Pending alarms can be snoozed, rescheduled, or dismissed. Snoozed and
rescheduled alarms can be snoozed again, rescheduled again, or dismissed.
Dismissed alarms are terminal. Times must be timezone-aware and in the future.
Alarm delivery uses the optional native notifier plus the durable in-app inbox;
it never invokes TTS.
