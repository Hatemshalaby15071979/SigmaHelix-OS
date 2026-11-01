# Local structured logging

`configure_logging()` installs a JSON Lines handler for the `sigmahelix` logger. By default, logs go under the data directory beside the configured database, in `logs/sigmahelix.jsonl`. The directory is owner-only (`0700`); active and rotated log files are owner-only (`0600`). The handler rotates at UTC midnight and retains seven daily files.

`RedactingJSONFormatter` scrubs the rendered message, exception and stack text, nested structured fields, and values under sensitive field names. It covers credential assignments, bearer authorization values, common GitHub token prefixes, JWT-shaped values, and PEM private-key blocks. Redaction is defense in depth: callers should avoid putting credentials or personal data in log messages in the first place.

No handler is installed at import time. Applications call `configure_logging()` at startup, optionally passing an absolute log directory and a validated level. The logger does not propagate to the root logger, preventing a second unredacted output path.
