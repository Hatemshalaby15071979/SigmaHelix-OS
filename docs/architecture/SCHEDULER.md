# Persisted scheduler

SigmaHelix stores job definitions and run claims in SQLite. `Scheduler` accepts
an injected timezone-aware clock, making due-time behavior deterministic in
tests. A one-shot job is disabled when its due slot is claimed. An interval job
advances from the scheduled slot rather than from handler completion time.

`BEGIN IMMEDIATE` serializes claims across scheduler instances. Each due slot
has a deterministic UUID and a unique `(tenant_id, job_id, scheduled_for)` key,
so concurrent pollers cannot invoke a slot twice. The handler runs after the
claim transaction commits; its success or exception type is then persisted in
`job_runs`, with a matching event and audit record. Exception messages and
secret-like payloads are not stored.

This provides at-most-once handler invocation for a claimed slot, rather than
exactly-once side effects. Call `recover_missed()` once at startup before
polling. It persists overdue unclaimed slots and interrupted `running` claims,
emits an event and audit record, and returns them for review. An overdue slot
stays blocked from dispatch until `acknowledge_missed()` is called; after that,
the ordinary poll can deliver it. An interrupted claim is never automatically
retried because its side effects may already have happened. Long gaps on
interval jobs are surfaced one scheduled slot per poll. Handlers must be
registered in each process before polling. Scheduler callbacks are synchronous
and should remain short; GUI notification delivery is handled by P2-005.
