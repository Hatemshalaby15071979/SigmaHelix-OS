"""Structured, local-only logging with defense-in-depth secret redaction."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from .config import load_settings

_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|private.?key|api.?key|access.?key|authorization",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)(\b(?:password|passwd|token|secret|api[_-]?key|access[_-]?key|client[_-]?secret|credential)\b\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
    ),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,})\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?ms)(-----BEGIN [A-Z ]*PRIVATE KEY-----).*?(-----END [A-Z ]*PRIVATE KEY-----)"
    ),
)
_REDACTED = "[REDACTED]"
_STANDARD_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def redact_text(value: str) -> str:
    """Replace common credential patterns while preserving their field labels."""
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(lambda match: f"{match.group(1)}{_REDACTED}", result)
        else:
            result = pattern.sub(_REDACTED, result)
    return result


def _safe_value(value: Any, key: str | None = None) -> Any:
    if key is not None and _SENSITIVE_KEY.search(key):
        return _REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(child_key): _safe_value(child, str(child_key))
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_value(child) for child in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))


class RedactingJSONFormatter(logging.Formatter):
    """Serialize log records as JSON after scrubbing messages and fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Return one JSON object, redacting message, extras, and exception text."""
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_KEYS and not key.startswith("_"):
                payload[key] = _safe_value(value, key)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact_text(self.formatStack(record.stack_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _PrivateTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Create each active log file with owner-only permissions."""

    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            stream.close()
            raise
        return stream


def configure_logging(
    log_dir: Path | None = None, level: str = "INFO"
) -> logging.Logger:
    """Configure the named logger with a private, seven-day rotating JSON log."""
    normalized_level = level.upper()
    if normalized_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("unsupported log level")
    directory = Path(
        log_dir or load_settings().database_path.parent / "logs"
    ).expanduser()
    if not directory.is_absolute():
        raise ValueError("log directory must be an absolute path")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    handler = _PrivateTimedRotatingFileHandler(
        directory / "sigmahelix.jsonl",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
        utc=True,
        delay=False,
    )
    handler.setFormatter(RedactingJSONFormatter())
    logger = logging.getLogger("sigmahelix")
    logger.setLevel(normalized_level)
    logger.propagate = False
    for existing in logger.handlers:
        existing.close()
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger
