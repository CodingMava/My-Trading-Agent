import logging

import requests

import alert_engine
from alert_engine import AlertSystem


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_alert_uses_a_timeout_and_reports_success(monkeypatch):
    calls = {}

    def fake_post(url, json, timeout):
        calls.update(url=url, json=json, timeout=timeout)
        return FakeResponse(200)

    monkeypatch.setattr(alert_engine.requests, "post", fake_post)
    assert AlertSystem("123:TOKEN", "42", timeout_s=7).send_telegram_alert("hello") is True
    assert calls["timeout"] == 7 and calls["json"]["chat_id"] == "42"


def test_network_errors_never_log_the_token(monkeypatch, caplog):
    def broken_post(*args, **kwargs):
        raise requests.ConnectionError("Max retries exceeded with url: /bot123:TOKEN/sendMessage")

    monkeypatch.setattr(alert_engine.requests, "post", broken_post)
    with caplog.at_level(logging.ERROR):
        assert AlertSystem("123:TOKEN", "42").send_telegram_alert("hello") is False
    assert "123:TOKEN" not in caplog.text and "***" in caplog.text


def test_rejected_messages_are_reported(monkeypatch, caplog):
    monkeypatch.setattr(alert_engine.requests, "post", lambda *a, **k: FakeResponse(400, "can't parse entities"))
    with caplog.at_level(logging.ERROR):
        assert AlertSystem("123:TOKEN", "42").send_telegram_alert("*unbalanced") is False
    assert "HTTP 400" in caplog.text
