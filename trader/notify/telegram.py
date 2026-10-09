"""Sending notifications to Telegram, with a timeout, retries, and the bot token never logged."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)
RETRY_STATUSES = {429, 500, 502, 503, 504}


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: float = 10, attempts: int = 3, http=requests,
                 sleep=time.sleep):
        self._token, self._chat_id = token, chat_id
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"  # contains the token: never log it
        self._timeout, self._attempts, self._http, self._sleep = timeout, attempts, http, sleep

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def send(self, text: str) -> bool:
        """True once Telegram accepts the message; False after the last failed attempt."""
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        for attempt in range(1, self._attempts + 1):
            try:
                response = self._http.post(self._url, json=payload, timeout=self._timeout)
            except Exception as exc:  # network errors include the URL, hence the redaction
                log.warning("Telegram send failed (attempt %d): %s", attempt, self._redact(str(exc)))
            else:
                if response.status_code == 200:
                    return True
                log.warning("Telegram refused the message (HTTP %s, attempt %d): %s", response.status_code, attempt,
                            self._redact(response.text[:300]))
                if response.status_code not in RETRY_STATUSES:
                    return False
                if response.status_code == 429:
                    try:
                        self._sleep(float(response.json().get("parameters", {}).get("retry_after", 1)))
                    except Exception:
                        self._sleep(1.0)
                    continue
            if attempt < self._attempts:
                self._sleep(2.0 * attempt)
        return False


class LogNotifier:
    """Used when Telegram isn't configured: messages only go to the log."""

    def send(self, text: str) -> bool:
        log.info("Notification (Telegram off): %s", text.replace("\n", " | "))
        return True


def notifier_from_settings(settings):
    if settings.telegram_enabled:
        return TelegramNotifier(settings.telegram_bot_token.reveal(), settings.telegram_chat_id,
                                timeout=settings.telegram_timeout_seconds)
    return LogNotifier()
