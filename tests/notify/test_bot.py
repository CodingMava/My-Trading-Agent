import logging
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from trader.config import load_settings
from trader.core.models import Position
from trader.data.kite import KiteAuthError, KiteError, KiteSession, load_session, save_session
from trader.execution.kite_orders import KiteOrders
from trader.execution.store import PaperStore
from trader.markets.calendar import load_calendars
from trader.notify import bot as bot_module
from trader.notify.bot import HELP, CommandBot, Context, kite_check_text, kite_login, login_reminder, reply_to
from trader.ops.health import ALERT, OK, Health
from trader.registry import StrategyRecord, StrategyRegistry
from trader.risk.killswitch import KillSwitch

CHAT = "4242"


def context(tmp_path, store=True, checks=()):
    return Context(PaperStore(tmp_path / "p.db", 1_000_000) if store else None,
                   StrategyRegistry([StrategyRecord("H1", "Pullback", "REJECTED")]), KillSwitch(tmp_path / "KILL"),
                   list(checks))


class FakeTelegram:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def get(self, url, params, timeout):
        self.calls.append(params)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return type("Response", (), {"json": lambda self: reply})()


class Inbox:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True


def message(update_id, chat, text):
    return {"update_id": update_id, "message": {"chat": {"id": chat}, "text": text}}


def test_status_shows_mode_kill_switch_account_and_health(tmp_path):
    ctx = context(tmp_path, checks=[Health("daily run", ALERT, "missed <today>"), Health("calendar", OK, "fine")])
    text = reply_to("/status", ctx)
    assert text.startswith("<b>Status</b>") and "Mode: NO TRADE" in text and "Kill switch: off" in text
    assert "Equity: ₹1,000,000.00" in text and "Needs attention:" in text and "missed &lt;today&gt;" in text
    assert "No paper-trading records yet" in reply_to("/status", context(tmp_path / "b", store=False))
    assert "All health checks pass." in reply_to("/status@MyTradingBot", context(tmp_path / "c"))


def test_positions_and_trades(tmp_path):
    ctx = context(tmp_path)
    assert reply_to("/positions", ctx) == "No open positions." and reply_to("/trades", ctx) == "No closed trades yet."
    ctx.store.save_position(Position("H1", "AAA.NS", 10, 100.0, 95.0, date(2026, 8, 11), last_price=90.0, bars_held=3,
                                     entry_fees=1.0))
    ctx.store.add_trade("H1", "BBB.NS", 5, date(2026, 8, 1), 200.0, date(2026, 8, 5), 210.0, "Strategy Exit", 2.0, 48.0,
                        0.048, 0.5)
    assert ("AAA.NS x10: entry ₹100.00, last ₹90.00, stop ₹95.00, P&amp;L -₹101.00, held 3 day(s)"
            in reply_to("/positions", ctx))
    assert "2026-08-05 BBB.NS (H1): Strategy Exit, +₹48.00 (+4.80%)" in reply_to("/trades", ctx)


def test_kill_engages_once_and_no_command_releases_it(tmp_path):
    ctx = context(tmp_path)
    assert "Kill switch engaged" in reply_to("/kill the data looks broken", ctx)
    assert "engaged from Telegram: the data looks broken" in ctx.kill_switch.reason
    assert "already engaged" in reply_to("/kill again", ctx)
    for attempt in ("/release", "/unkill", "/resume", "/start"):
        assert reply_to(attempt, ctx) == HELP
    assert ctx.kill_switch.engaged


def test_only_commands_from_the_configured_chat_are_answered(tmp_path):
    telegram, inbox = FakeTelegram({"ok": True, "result": [
        message(1, 4242, "/status"), message(2, 999, "/kill now"), message(3, 4242, "just chatting"),
        message(4, 4242, "/help")]}), Inbox()
    bot = CommandBot("123:TOKEN", CHAT, inbox, lambda: context(tmp_path), http=telegram, sleep=lambda s: None)
    assert bot.poll_once() == 2 and bot.offset == 5  # every update confirmed, two answered
    assert inbox.sent[0].startswith("<b>Status</b>") and inbox.sent[1] == HELP
    assert not KillSwitch(tmp_path / "KILL").engaged  # the stranger's /kill was ignored


def test_polling_survives_network_trouble_and_never_logs_the_token(tmp_path, caplog):
    telegram = FakeTelegram(requests.ConnectionError("https://api.telegram.org/bot123:TOKEN/getUpdates"),
                            {"ok": False, "description": "Conflict: terminated by other getUpdates request"},
                            {"ok": True, "result": []})
    sleeps = []
    bot = CommandBot("123:TOKEN", CHAT, Inbox(), lambda: context(tmp_path), http=telegram, sleep=sleeps.append)
    with caplog.at_level(logging.WARNING):
        assert [bot.poll_once(), bot.poll_once(), bot.poll_once()] == [0, 0, 0]
    assert sleeps == [30, 30] and "123:TOKEN" not in caplog.text and "Conflict" in caplog.text
    assert telegram.calls[0]["timeout"] == 50 and "offset" not in telegram.calls[0]


def test_a_failed_lookup_gets_an_answer_instead_of_silence(tmp_path):
    def busy():
        raise OSError("database is locked")

    inbox = Inbox()
    bot = CommandBot("t", CHAT, inbox, busy, http=FakeTelegram({"ok": True, "result": [message(7, 4242, "/status")]}),
                     sleep=lambda s: None)
    assert bot.poll_once() == 1 and "Couldn't read the records just now (OSError)" in inbox.sent[0]


MONDAY_MORNING = datetime(2026, 10, 12, 8, 45, tzinfo=ZoneInfo("Asia/Kolkata"))


class KiteSessionEndpoint:
    """Kite's token exchange, answering with `payload` (or failing to answer)."""

    def __init__(self, payload=None, status=200, error=None):
        self.payload, self.status, self.error, self.calls = payload, status, error, []

    def post(self, url, headers=None, timeout=None, data=None):
        self.calls.append(data)
        if self.error:
            raise self.error
        return type("Response", (), {"status_code": self.status, "json": lambda response: self.payload})()


def test_logging_in_to_kite_from_the_phone(tmp_path):
    settings, session_file = load_settings(env={"KITE_API_KEY": "key", "KITE_API_SECRET": "sec"}), tmp_path / "s.json"
    link = kite_login(settings, "", session_file, now=MONDAY_MORNING)
    assert "Not logged in today." in link and "https://kite.zerodha.com/connect/login?v=3&amp;api_key=key" in link
    kite = KiteSessionEndpoint({"status": "success", "data": {"access_token": "AT-SECRET", "user_id": "AB1234"}})
    redirect = "https://127.0.0.1/?action=login&type=login&status=success&request_token=req1"
    reply = kite_login(settings, redirect, session_file, http=kite, now=MONDAY_MORNING)
    assert reply == "Logged in to Kite as AB1234 until 13 Oct 06:00 IST." and kite.calls[0]["request_token"] == "req1"
    assert load_session(session_file, MONDAY_MORNING).access_token == "AT-SECRET"  # kept on the PC, never sent back
    assert "Logged in until 13 Oct 06:00 IST." in kite_login(settings, "", session_file, now=MONDAY_MORNING)
    expired = KiteSessionEndpoint({"status": "error", "error_type": "TokenException",
                                   "message": "Token is invalid or has expired."}, 403)
    assert kite_login(settings, "req2", session_file, http=expired).startswith("Login failed: Token is invalid")
    offline = KiteSessionEndpoint(error=requests.ConnectionError("https://api.kite.trade/session/token req3"))
    assert kite_login(settings, "req3", session_file, http=offline) == (
        "Login failed: couldn't reach Kite (ConnectionError). Try again.")
    garbled = kite_login(settings, "not a token", session_file)
    assert garbled.startswith("Login failed: ") and "look like a request_token" in garbled
    assert "Kite isn't set up" in kite_login(load_settings(env={}), "", session_file)
    assert "/login" in HELP


def test_login_is_answered_even_when_the_records_cant_be_read(tmp_path):
    inbox = Inbox()

    def unreadable():
        raise RuntimeError("database is locked")
    telegram = FakeTelegram({"ok": True, "result": [message(1, CHAT, "/login https://x/?status=success&request_token=t")]})
    bot = CommandBot("TOKEN", CHAT, inbox, unreadable, http=telegram,
                     direct={"/login": lambda argument: f"login with {argument}"})
    assert bot.poll_once() == 1 and inbox.sent == ["login with https://x/?status=success&request_token=t"]


def test_a_live_trading_morning_without_a_login_gets_one_reminder(tmp_path):
    nse, session_file = load_calendars()["NSE"], tmp_path / "s.json"
    off = load_settings(env={})
    on = replace(off, live_enabled=True)
    assert "Kite login needed" in login_reminder(on, nse, MONDAY_MORNING, session_file)
    assert login_reminder(off, nse, MONDAY_MORNING, session_file) is None  # live trading off: no login needed
    for when in (MONDAY_MORNING.replace(hour=8, minute=0), MONDAY_MORNING.replace(hour=9, minute=30),
                 MONDAY_MORNING.replace(day=11)):  # too early, too late, a Sunday
        assert login_reminder(on, nse, when, session_file) is None
    save_session(KiteSession("key", "AT", "U", MONDAY_MORNING), session_file)
    assert login_reminder(on, nse, MONDAY_MORNING, session_file) is None  # already logged in
    inbox = Inbox()
    bot = CommandBot("TOKEN", CHAT, inbox, lambda: None, reminder=lambda: "log in")
    for day in (date(2026, 10, 12), date(2026, 10, 12), date(2026, 10, 13)):
        bot.remind(day)
    assert inbox.sent == ["log in", "log in"]  # at most once a day
    quiet = CommandBot("TOKEN", CHAT, inbox, lambda: None, reminder=lambda: None)
    quiet.remind(date(2026, 10, 14))
    assert len(inbox.sent) == 2



def test_the_kite_check_from_the_phone_sends_counts_and_a_verdict_only(monkeypatch):
    from tests.execution.fake_kite import FakeKite
    monkeypatch.setattr(bot_module, "open_live_store", lambda settings: None)  # not the real state/
    kite = FakeKite()
    kite.holdings = [{"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 10, "t1_quantity": 0, "used_quantity": 0}]
    kite.prices = {"NIFTYBEES": 254.66}
    settings = load_settings(env={})
    text = kite_check_text(settings, connect=lambda: KiteOrders("key", "AT", http=kite, sleep=lambda seconds: None))
    assert text.startswith("<b>Kite check (read-only)</b>") and "holdings: 1" in text and "NIFTYBEES last price: 254.66" in text
    assert "Every field the order system relies on is there" in text
    assert "INFY" not in text and "funds" not in text  # nothing about the money goes through Telegram

    def fails(error):
        def connect():
            raise error
        return connect
    no_login = KiteAuthError("no valid Kite session today (run: python -m trader.data.kite login)")
    assert kite_check_text(settings, fails(no_login)).startswith("Log in first: send /login.")
    assert "Kite check failed: PermissionException" in kite_check_text(settings, fails(KiteError("PermissionException")))
    offline = kite_check_text(settings, fails(requests.ConnectionError("https://api.kite.trade/portfolio/holdings")))
    assert offline == "Kite check failed: couldn't reach Kite (ConnectionError)."
    assert "/kitecheck" in HELP
