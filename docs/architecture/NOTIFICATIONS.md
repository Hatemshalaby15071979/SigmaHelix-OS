# Notifications

`NotificationService.deliver()` writes every notification to the tenant-scoped
in-app inbox before attempting native delivery. The default Linux adapter uses
`notify-send` with an argument list and a short timeout; if the command is not
installed or fails, the inbox item remains available with `unavailable` or
`failed` status. Tests and callers can inject a sender, including `None` to use
in-app delivery only. `(tenant_id, dedupe_key)` makes delivery idempotent and
prevents duplicate native alerts for a repeated scheduler slot.

Inbox entries are retained and can be marked read once. Notification titles and
bodies reject secret-like patterns. No TTS or audio output is part of this
service; speech playback remains an explicit user action elsewhere in the app.
