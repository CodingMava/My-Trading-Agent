import logging

import requests

from trader.notify import templates
from trader.notify.telegram import LogNotifier, TelegramNotifier


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code, self._payload, self.text = status_code, payload or {}, str(payload)

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def post(self, url, json, timeout):
        self.calls.append(json)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_messages_follow_the_spec_and_escape_values():
    text = templates.buy_signal(symbol="A&B<1>.NS", market="NSE", last_close=1234.5, stop_distance=0.05, quantity=40,
                                strategy="Test <strategy>", exit_note="5-day average", win_rate=0.6, expectancy=0.0025,
                                reason="entry rule met")
    assert text.startswith("<b>[PAPER] BUY SIGNAL</b>")
    assert "Stock: A&amp;B&lt;1&gt;.NS" in text and "Strategy: Test &lt;strategy&gt;" in text
    for field in ("Market: NSE", "Quantity: 40", "Profitable-Trade Rate: 60% in research", "Expectancy: +0.25%",
                  "Stop Loss: 5.0% below the fill", "₹1,234.50", "Reason: entry rule met"):
        assert field in text
    sell = templates.sell_executed(symbol="X.NS", price=99.5, quantity=10, pnl=-120.4, net_return=-0.012,
                                   reason="Stop Loss", paper=False)
    assert sell.startswith("<b>SELL EXECUTED</b>") and "P&amp;L: -₹120.40 after costs" in sell
    assert "Return: -1.20%" in sell and "Reason: Stop Loss" in sell
    alert = templates.risk_alert(title="Kill switch", detail="drawdown 10.5% > 10%")
    assert alert.startswith("<b>[PAPER] RISK ALERT: Kill switch</b>") and "&gt;" in alert


def test_telegram_retries_server_errors_and_uses_html():
    sleeps = []
    http = FakeHTTP([FakeResponse(502), FakeResponse(200)])
    assert TelegramNotifier("123:TOKEN", "42", http=http, sleep=sleeps.append).send("<b>hi</b>")
    assert len(http.calls) == 2 and http.calls[0]["parse_mode"] == "HTML" and sleeps == [2.0]


def test_telegram_honours_rate_limits_and_gives_up_on_bad_requests():
    sleeps = []
    http = FakeHTTP([FakeResponse(429, {"parameters": {"retry_after": 7}}), FakeResponse(200)])
    assert TelegramNotifier("t", "42", http=http, sleep=sleeps.append).send("x") and sleeps == [7.0]
    bad = FakeHTTP([FakeResponse(400, {"description": "can't parse entities"})])
    assert not TelegramNotifier("t", "42", http=bad, sleep=sleeps.append).send("x") and len(bad.calls) == 1


def test_telegram_failures_never_log_the_token(caplog):
    http = FakeHTTP([requests.ConnectionError("Max retries exceeded with url: /bot123:TOKEN/sendMessage")] * 3)
    with caplog.at_level(logging.WARNING):
        assert not TelegramNotifier("123:TOKEN", "42", http=http, sleep=lambda s: None).send("x")
    assert "123:TOKEN" not in caplog.text and "***" in caplog.text


def test_log_notifier_when_telegram_is_off(caplog):
    with caplog.at_level(logging.INFO):
        assert LogNotifier().send("<b>hello</b>\nworld")
    assert "hello" in caplog.text
