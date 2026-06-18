import logging

from src.main import SecretRedactionFilter


def test_secret_redaction_filter(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    log_filter = SecretRedactionFilter()
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "request https://example.invalid/bot%s/getMe", ("secret-token",), None,
    )
    assert log_filter.filter(record)
    assert "secret-token" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()

