import json
import logging
from logging.handlers import TimedRotatingFileHandler

import pytest

from sigmahelix.core.logging import (
    RedactingJSONFormatter,
    configure_logging,
    redact_text,
)

SECRET_VALUES = (
    "super-secret-value",
    "ghp_1234567890abcdefghijklmnop",
    "eyJabcdefghijk.abcdefghijk.abcdefghijk",
    "-----BEGIN RSA PRIVATE KEY-----\nprivate-material\n-----END RSA PRIVATE KEY-----",
)


@pytest.mark.parametrize(
    "value",
    [
        "password=super-secret-value",
        "api_key: super-secret-value",
        "Authorization: Bearer super-secret-value",
        "ghp_1234567890abcdefghijklmnop",
        "eyJabcdefghijk.abcdefghijk.abcdefghijk",
        "-----BEGIN RSA PRIVATE KEY-----\nprivate-material\n-----END RSA PRIVATE KEY-----",
    ],
)
def test_redact_text_scrubs_secret_patterns(value):
    result = redact_text(value)

    for secret in SECRET_VALUES:
        assert secret not in result
    assert "[REDACTED]" in result


def test_json_formatter_redacts_message_sensitive_fields_and_nested_values():
    record = logging.LogRecord(
        "sigmahelix.test",
        logging.INFO,
        __file__,
        10,
        "request Authorization: Bearer %s password=%s",
        (SECRET_VALUES[0], SECRET_VALUES[0]),
        None,
    )
    record.api_token = SECRET_VALUES[0]
    record.context = {"nested": "api_key=" + SECRET_VALUES[0]}

    rendered = RedactingJSONFormatter().format(record)
    payload = json.loads(rendered)

    assert payload["level"] == "INFO"
    assert payload["api_token"] == "[REDACTED]"
    assert SECRET_VALUES[0] not in rendered
    assert "Bearer [REDACTED]" in payload["message"]
    assert "api_key=[REDACTED]" in payload["context"]["nested"]


def test_formatter_redacts_exception_tracebacks():
    try:
        raise RuntimeError("credential=super-secret-value")
    except RuntimeError:
        record = logging.LogRecord(
            "sigmahelix.test", logging.ERROR, __file__, 20, "operation failed", (), None
        )
        record.exc_info = __import__("sys").exc_info()

    rendered = RedactingJSONFormatter().format(record)

    assert "super-secret-value" not in rendered
    assert "credential=[REDACTED]" in json.loads(rendered)["exception"]


def test_configured_logs_are_private_json_and_rotate_for_seven_days(tmp_path):
    logger = configure_logging(tmp_path / "logs", "DEBUG")
    logger.info("connected with token=%s", SECRET_VALUES[0])

    handler = logger.handlers[0]
    assert isinstance(handler, TimedRotatingFileHandler)
    assert handler.backupCount == 7
    assert handler.when == "MIDNIGHT"
    handler.flush()
    log_path = tmp_path / "logs" / "sigmahelix.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "super-secret-value" not in log_path.read_text(encoding="utf-8")
    assert payload["message"] == "connected with token=[REDACTED]"
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "logs").stat().st_mode & 0o777 == 0o700
    handler.close()
    logger.handlers.clear()


def test_configure_logging_rejects_relative_directory(tmp_path):
    with pytest.raises(ValueError, match="absolute path"):
        configure_logging(tmp_path.name, "INFO")
