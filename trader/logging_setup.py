"""Logging that is safe to run unattended: UTF-8 everywhere, a rotating file, secrets masked."""
from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from trader.config import ROOT

LOG_DIR = ROOT / "logs"
LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "peewee")


def redact(text: str, secrets: Iterable[str]) -> str:
    """`text` with every known secret replaced by '***' (for logs, and for alerts built from errors)."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class RedactingFormatter(logging.Formatter):
    """Formats as usual, then masks every known secret, including inside tracebacks."""

    def __init__(self, fmt: str, secrets: Iterable[str]):
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets)


def make_console_utf8() -> None:
    """On Windows, redirected stdout defaults to cp1252 and crashes on emoji; force UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def configure_logging(secrets: Iterable[str] = (), level: int = logging.INFO, log_dir: Path = LOG_DIR,
                      filename: str = "trader.log") -> None:
    """Send logs to stdout (when there is one) and to a rotating UTF-8 file, with every secret replaced by '***'."""
    make_console_utf8()
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter(LOG_FORMAT, list(secrets))
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_trader_handler", False)]:
        root.removeHandler(handler)
        handler.close()
    handlers = [RotatingFileHandler(log_dir / filename, maxBytes=5_000_000, backupCount=5, encoding="utf-8")]
    if sys.stdout is not None:  # pythonw (the scheduled tasks) has no console: the file only
        handlers.append(logging.StreamHandler(sys.stdout))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler._trader_handler = True
        root.addHandler(handler)
    root.setLevel(level)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
