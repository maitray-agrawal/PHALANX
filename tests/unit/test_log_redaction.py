"""Unit tests for LogRedactionFilter ensuring secrets in msg and args are redacted."""

import logging

from app.api.middleware import LogRedactionFilter


def test_log_redaction_in_msg():
    """Secrets directly in message string are redacted."""
    filter_ = LogRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connection created with password=supersecret123 and token: mytoken456",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    output = record.getMessage()
    assert "supersecret123" not in output
    assert "mytoken456" not in output
    assert "password=[REDACTED]" in output
    assert "token: [REDACTED]" in output


def test_log_redaction_in_record_args():
    """Secrets supplied in record.args (%s formatting) are formatted then redacted."""
    filter_ = LogRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=20,
        msg="API call failed with secret=%s, authorization=%s, and header Bearer %s",
        args=("very_secret_key_999", "admin_pass_000", "eyJh_token_here_xyz"),
        exc_info=None,
    )
    filter_.filter(record)
    output = record.getMessage()
    assert "very_secret_key_999" not in output
    assert "admin_pass_000" not in output
    assert "eyJh_token_here_xyz" not in output
    assert "secret=[REDACTED]" in output
    assert "authorization=[REDACTED]" in output
    assert "Bearer [REDACTED]" in output
    assert record.args == ()


def test_log_redaction_non_string_msg():
    """Non-string msg is converted to string and does not crash."""
    filter_ = LogRedactionFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=30,
        msg={"key": "value", "secret": "123"},
        args=(),
        exc_info=None,
    )
    assert filter_.filter(record) is True
    output = record.getMessage()
    assert "[REDACTED]" in output
    assert "123" not in output
