# Persistent event bus

Schema migration v3 adds `event_stream`, an append-only sequence index over the immutable `events` table. A SQLite `AFTER INSERT` trigger records the stream cursor in the same transaction as each event insert, including writes made through `EventRepository`. Existing v2 events receive stable sequence positions during the migration.

`EventBus.publish()` stores an event before notifying in-process subscribers. Subscribers can filter by tenant and event type, then unsubscribe with the returned UUID. A callback error is surfaced as `EventDispatchError`; its envelope identifies the already-persisted event, which can be recovered through replay. Do not retry the same event ID.

`EventBus.replay(after_sequence=...)` returns matching records oldest first, with stable sequence cursors for consumer checkpoints. Replay is tenant scoped; sequence numbers are global to the database. Subscribers are process-local and synchronous, so applications that need durable consumer offsets must store their own last processed sequence and replay after restart.
