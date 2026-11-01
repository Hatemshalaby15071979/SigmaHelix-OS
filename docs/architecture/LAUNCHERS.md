# Launcher profiles

Launcher profiles are registered commands with an executable resolved to an
absolute path, a fixed argument vector, and a working directory. Profiles are
immutable after creation and can only be disabled. `preview()` returns a
shell-quoted display string and working directory; it never starts a process.

`launch(profile_id)` is the only execution entrypoint. It accepts an existing
enabled profile ID, uses `subprocess.Popen` with an argv list and `shell=False`,
and supplies a small desktop-oriented environment allowlist. It discards child
stdin/stdout/stderr by default. Unknown names or IDs cannot become commands.
Secret-like flags are rejected from stored arguments.

Each explicit launch has a durable run record and start/finish event plus audit
entry. The caller polls `refresh(handle)` to store the child's exit code. A
process still running when the app stops remains marked `running`; crash
reconciliation is a later task. No command is run by preview or registration.
