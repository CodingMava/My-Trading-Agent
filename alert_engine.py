import logging

import requests

log = logging.getLogger("alert_engine")


class AlertSystem:
    def __init__(self, bot_token, chat_id, timeout_s=10):
        self._bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_s = timeout_s
        # This is the official Telegram API endpoint for sending messages. It contains the token,
        # so it must never be printed or logged.
        self.base_url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"

    def _redact(self, text):
        return text.replace(self._bot_token, "***") if self._bot_token else text

    def send_telegram_alert(self, message):
        """
        Sends a formatted text message to your Telegram app. Returns True if Telegram accepted it.
        """
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"  # This allows us to use bolding and emojis!
        }
        try:
            response = requests.post(self.base_url, json=payload, timeout=self.timeout_s)
        except Exception as exc:  # network errors include the URL, which contains the token
            log.error("Telegram alert failed: %s", self._redact(str(exc)))
            return False

        if response.status_code == 200:
            log.info("Telegram alert sent.")
            return True
        log.error("Telegram rejected the alert (HTTP %s): %s", response.status_code, self._redact(response.text[:300]))
        return False


# --- Testing the Alert Engine: `python alert_engine.py` sends one message using the keys in .env ---
if __name__ == "__main__":
    from trader.config import load_settings
    from trader.logging_setup import configure_logging

    settings = load_settings()
    configure_logging(secrets=settings.secret_values())
    if not settings.telegram_enabled:
        raise SystemExit("Telegram is not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env (see .env.example).")

    print("Connecting to Telegram...")
    alerter = AlertSystem(settings.telegram_bot_token.reveal(), settings.telegram_chat_id,
                          timeout_s=settings.telegram_timeout_seconds)
    test_message = "🚀 *AI Trading Agent Online*\nConnected. Mode: NO TRADE until a strategy passes the profitability gate."
    alerter.send_telegram_alert(test_message)
