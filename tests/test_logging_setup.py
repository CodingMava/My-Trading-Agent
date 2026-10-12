import logging
import sys

from trader.logging_setup import configure_logging


def test_secrets_are_masked_in_messages_and_tracebacks(tmp_path):
    configure_logging(secrets=["TOPSECRET"], log_dir=tmp_path, filename="test.log")
    root = logging.getLogger()
    try:
        log = logging.getLogger("test.redaction")
        log.error("token TOPSECRET in a message")
        try:
            raise RuntimeError("Max retries exceeded with url: /botTOPSECRET/sendMessage")
        except RuntimeError:
            log.exception("request failed")
    finally:
        for handler in [h for h in root.handlers if getattr(h, "_trader_handler", False)]:
            root.removeHandler(handler)
            handler.close()
    text = (tmp_path / "test.log").read_text(encoding="utf-8")
    assert "TOPSECRET" not in text
    assert text.count("***") >= 3  # message, exception message, traceback line


def test_without_a_console_it_logs_to_the_file_only(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)  # as under pythonw, which the scheduled tasks use
    configure_logging(log_dir=tmp_path, filename="test.log")
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "_trader_handler", False)]
    try:
        logging.getLogger("test.windowless").warning("still recorded")
    finally:
        for handler in ours:
            root.removeHandler(handler)
            handler.close()
    assert [type(h).__name__ for h in ours] == ["RotatingFileHandler"]
    assert "still recorded" in (tmp_path / "test.log").read_text(encoding="utf-8")
