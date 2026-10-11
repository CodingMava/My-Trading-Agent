import logging
from datetime import date

import requests

from trader.core.models import Position
from trader.execution.store import PaperStore
from trader.notify.bot import HELP, CommandBot, Context, reply_to
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
