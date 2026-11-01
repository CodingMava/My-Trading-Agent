"""Live trading's jobs and locks: the paper engine decides, the live jobs carry it out at an in-memory Kite."""
import html
import re
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
import requests

from tests.execution.fake_kite import FakeKite, ok
from tests.execution.test_paper_trader import SIGNAL_DAY, SPEC, FakeNotifier, make_trader
from trader.config import load_settings
from trader.core.models import Position
from trader.data.kite import KiteAuthError
from trader.execution import broker, live as live_jobs
from trader.execution.kite_orders import KiteOrders
from trader.execution.live import (Live, Override, capital_for_today, check, load_never_trade, load_overrides, locks, run,
                                   status_text, step_drawdown, track)
from trader.execution.oms import OMS, LiveStore
from trader.execution.sources import LiveOrder
from trader.execution.store import PaperStore
from trader.markets.calendar import load_calendars
from trader.registry import StrategyRecord, StrategyRegistry
from trader.risk.killswitch import KillSwitch

IST = ZoneInfo("Asia/Kolkata")
NSE = load_calendars()["NSE"]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 8, 10, 18, 30, tzinfo=IST)

    def at(self, day, hour, minute=0):
        self.now = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)

    def __call__(self):
        return self.now


def setup(tmp_path, status="LIVE_SMALL", capital=100_000, enabled=True, **limits):
    paper = make_trader(tmp_path, status=status)
    kite, clock = FakeKite(), Clock()
    settings = replace(load_settings(env={}), live_enabled=enabled, live_capital=capital, **limits)
    live = Live(settings, paper.store, LiveStore(tmp_path / "live.db"),
                StrategyRegistry([StrategyRecord("T1", "Test strategy", status)]), KillSwitch(tmp_path / "KILL"), NSE,
                FakeNotifier(), connect=lambda: KiteOrders("key", "AT", http=kite, sleep=lambda s: None),
                catalog={"T1": SPEC}, clock=clock)
    return paper, live, kite, clock


def job(live, clock, name, day, hour, minute=0):
    clock.at(day, hour, minute)
    sent_before = len(live.notifier.sent)
    code = run(name, live)
    return code, [html.unescape(text) for text in live.notifier.sent[sent_before:]]


def test_a_week_of_live_trading_mirrors_paper(tmp_path):
    paper, live, kite, clock = setup(tmp_path)  # paper: AAA stopped out, BBB sold on a signal, CCC sold on time
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert code == 0 and "AAA.NS: buy 100 at the open (SENT)" in messages[0]  # 1000 paper shares x 1 lakh / 10 lakh
    assert [o["quantity"] for o in kite.orders] == [100, 100, 100] and {o["variety"] for o in kite.orders} == {"amo"}

    kite.new_day()  # Tue 11 Aug: the after-market buys fill at the open
    for order in list(kite.orders):
        kite.fill(order, 101.0)
    kite.prices = {"AAA": 101.0, "BBB": 101.0, "CCC": 101.0}
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert code == 0 and "AAA.NS: stop (SENT)" in messages[0] and len(kite.gtts) == 3
    assert {g["condition"]["trigger_values"][0] for g in kite.gtts.values()} == {95.95}
    paper.run(until=date(2026, 8, 13))

    aaa_stop = next(g for g in kite.gtts.values() if g["condition"]["tradingsymbol"] == "AAA")
    kite.fill(kite.trigger(aaa_stop["id"]), 95.95)  # Thu 13 Aug: AAA touches its stop, like on paper
    code, messages = job(live, clock, "evening", date(2026, 8, 13), 18, 30)
    assert "AAA.NS stop: sell 100 at 95.95" in messages[0] and "AAA.NS" not in live.store.positions()

    paper.run(until=date(2026, 8, 14))  # BBB's exit signal at the close
    code, messages = job(live, clock, "evening", date(2026, 8, 14), 18, 30)
    assert "BBB.NS: sell 100 at the open (SENT)" in messages[0]

    kite.new_day()  # Mon 17 Aug: BBB's sell fills at the open; CCC's time is up at the close
    kite.fill(kite.by_tag(broker.exit_order("T1:BBB.NS:2026-08-14:sell", "BBB.NS", 100).tag), 104.0)
    code, messages = job(live, clock, "morning", date(2026, 8, 17), 9, 20)
    assert "BBB.NS exit: sell 100 at 104.00" in messages[0] and "BBB.NS: stop deleted (DONE)" in messages[0]
    bbb_stop = next(g for g in kite.gtts.values() if g["condition"]["tradingsymbol"] == "BBB")
    del kite.gtts[bbb_stop["id"]]  # should Kite stop listing a deleted GTT, the repeat doesn't say it again
    assert job(live, clock, "morning", date(2026, 8, 17), 9, 35) == (0, [])
    code, messages = job(live, clock, "preclose", date(2026, 8, 17), 15, 15)
    assert "CCC.NS: time exit, sell 100 (SENT)" in messages[0]
    ccc_stop = next(g for g in kite.gtts.values() if g["condition"]["tradingsymbol"] == "CCC")
    assert ccc_stop["status"] == "deleted"  # deleted first, so the stop can't sell too
    kite.fill(kite.by_tag(broker.time_exit(Position("T1", "CCC.NS", 100, 101.0, 95.95, date(2026, 8, 11))).tag), 102.0)
    paper.run(until=date(2026, 8, 17))
    job(live, clock, "evening", date(2026, 8, 17), 18, 30)

    assert live.store.positions() == {} and live.store.ledger_problems() == []
    fills = live.store.table("live_fills")
    assert list(fills["side"]).count("buy") == 3 and list(fills["side"]).count("sell") == 3
    tracked = track(paper.store, live.store)
    assert len(tracked) == 4 and set(tracked["slippage"]) == {0.0}  # 3 entries and BBB's exit, at paper's prices
    assert "Live holdings: none" in status_text(live) and "on for T1" in status_text(live)


def test_nothing_is_sent_while_a_lock_is_closed(tmp_path):
    for status, capital, enabled in (("LIVE_SMALL", 100_000, False), ("PAPER", 100_000, True), ("LIVE_SMALL", 0, True)):
        paper, live, kite, clock = setup(tmp_path / f"{status}{capital}{enabled}", status, capital, enabled)
        live.connect = lambda: pytest.fail("a locked job must not touch Kite")
        paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
        assert job(live, clock, "evening", SIGNAL_DAY, 18, 30) == (0, []) and locks(live)
        assert "LOCKED" in status_text(live)


def test_the_kill_switch_stops_entries_but_never_exits(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    live.kill_switch.engage("test")
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert "AAA.NS: entry not sent: the kill switch is engaged" in messages[0] and kite.orders == []
    assert "Kill switch ENGAGED" in status_text(live) and track(paper.store, live.store).empty  # nothing went live
    held = Position("T1", "BBB.NS", 100, 101.0, 95.95, date(2026, 8, 11))
    live.store.save_position(held)
    live.store.add_fill(date(2026, 8, 11), "Ebought", "T1", "BBB.NS", "buy", 100, 101.0)
    kite.positions["net"].append({"tradingsymbol": "BBB", "exchange": "NSE", "product": "CNC", "quantity": 100})
    kite.prices = {"BBB": 101.0}
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert "BBB.NS: stop (SENT)" in messages[0]  # protecting a holding is not a new trade


def test_entries_within_limits(tmp_path):
    for capital, limits, why in ((500, {}, "scale to none"),
                                 (100_000, {"live_max_order_fraction": 0.05}, "worth more than 5%"),
                                 (100_000, {"live_max_orders_per_day": 2}, "the day's limit of 2 entries")):
        paper, live, kite, clock = setup(tmp_path / why.replace(" ", "_").replace("%", ""), capital=capital, **limits)
        paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
        code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
        assert why in messages[0], (why, messages)


def test_a_mismatch_with_the_account_engages_the_kill_switch(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    live.store.save_position(Position("T1", "AAA.NS", 100, 101.0, 95.95, date(2026, 8, 11)))
    live.store.add_fill(date(2026, 8, 11), "Ebought", "T1", "AAA.NS", "buy", 100, 101.0)
    code, messages = job(live, clock, "morning", date(2026, 8, 12), 9, 20)  # the account holds none of it
    assert code == 2 and live.kill_switch.engaged and "AAA.NS: the system holds 100 shares" in messages[0]
    assert not any(call[0] in ("POST", "PUT", "DELETE") for call in kite.calls)
    assert job(live, clock, "morning", date(2026, 8, 12), 9, 35) == (2, [])  # the repeat is only logged
    live.kill_switch.release()  # released too soon: engaging it again is news
    code, messages = job(live, clock, "morning", date(2026, 8, 12), 9, 50)
    assert code == 2 and live.kill_switch.engaged and "Reconciliation failed" in messages[0]
    code, messages = job(live, clock, "morning", date(2026, 8, 13), 9, 20)
    assert code == 2 and "Reconciliation failed" in messages[0]  # and again each day it stays engaged


def test_failures_are_reported(tmp_path):
    paper, live, kite, clock = setup(tmp_path)

    def no_login():
        raise KiteAuthError("no valid Kite session today (run: python -m trader.data.kite login)")
    live.connect = no_login
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert code == 1 and "[LIVE] Live morning failed" in messages[0] and "login" in messages[0]
    assert "tries again every 15 minutes" in messages[0]
    live.connect = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert code == 1 and "RuntimeError: boom" in messages[0]  # another kind of failure: told too
    assert job(live, clock, "morning", date(2026, 8, 11), 9, 35) == (1, [])  # its repeat: only logged
    code, messages = job(live, clock, "preclose", date(2026, 8, 11), 15, 15)
    assert code == 1 and "Live preclose failed" in messages[0] and "tries again" not in messages[0]  # runs once


def test_a_stop_missed_for_want_of_a_login_goes_in_after_the_login(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    live.store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, today))
    live.store.add_fill(today, "Eaaa", "T1", "AAA.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "AAA", "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"AAA": 100.0}
    logged_in, live.connect = live.connect, lambda: (_ for _ in ()).throw(KiteAuthError("no valid Kite session today"))
    code, messages = job(live, clock, "morning", today, 9, 20)  # nobody logged in before 09:20
    assert code == 1 and len(messages) == 1 and kite.gtts == {}
    assert job(live, clock, "morning", today, 9, 35) == (1, [])  # still no login: told once, not every 15 minutes
    live.connect = logged_in  # the login at 11:07
    code, messages = job(live, clock, "morning", today, 11, 20)
    assert code == 0 and "AAA.NS: stop (SENT)" in messages[0] and len(kite.gtts) == 1
    assert job(live, clock, "morning", today, 11, 35) == (0, [])  # nothing new: nothing said
    code, messages = job(live, clock, "morning", today, 15, 5)  # the pre-close job's turn
    assert "Nothing sent: the morning job runs between 09:15 and 15:00" in messages[0]


def from_source(tmp_path, orders_on, capital=100_000):
    """A live strategy (TS) whose orders come from its own paper account, as B1F's come from paper trial 1."""
    paper, live, kite, clock = setup(tmp_path, capital=capital)
    live.registry, live.catalog = StrategyRegistry([StrategyRecord("TS", "Source strategy", "LIVE_SMALL")]), {}
    live.sources = {"TS": lambda today, held: (orders_on.get(today, []), [])}
    return live, kite, clock


def entry(symbol, returns=None, paper_quantity=1000):
    """A paper entry of Rs 1,00,000 in a Rs 10,00,000 account with a 5% stop: 100 shares at Rs 1,00,000 live."""
    return LiveOrder("TS", f"TS {symbol} entry", symbol, "buy", paper_quantity, 1_000_000, 100.0, 0.05, returns=returns)


def test_live_entries_pass_the_risk_engine_on_the_live_account(tmp_path):
    rng = np.random.default_rng(1)
    base = pd.Series(rng.normal(0, 0.01, 90), index=pd.bdate_range("2026-04-01", periods=90))
    returns = {"AAA.NS": base, "BBB.NS": base + rng.normal(0, 0.001, 90),  # BBB moves with AAA
               "CCC.NS": pd.Series(rng.normal(0, 0.01, 90), index=base.index)}
    live, kite, clock = from_source(tmp_path, {SIGNAL_DAY: [entry(s, returns) for s in ("AAA.NS", "BBB.NS", "CCC.NS")]})
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert "AAA.NS: buy 100 at the open (SENT)" in messages[0] and "CCC.NS: buy 100 at the open (SENT)" in messages[0]
    assert re.search(r"BBB\.NS: entry not sent: 0\.9\d with AAA\.NS \(limit 0\.8\)", messages[0])
    assert [o["tradingsymbol"] for o in kite.orders] == ["AAA", "CCC"]


def test_a_bad_day_stops_new_live_entries_and_a_smaller_account_buys_less(tmp_path):
    tue, wed, thu = date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)
    live, kite, clock = from_source(tmp_path, {SIGNAL_DAY: [entry("AAA.NS")], wed: [entry("BBB.NS")],
                                               thu: [entry("CCC.NS")]})
    job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    kite.new_day()
    kite.fill(kite.orders[0], 100.0)
    kite.prices = {"AAA": 100.0}
    job(live, clock, "morning", tue, 9, 20)
    assert job(live, clock, "evening", tue, 18, 30) == (0, [])  # nothing to send; the evening's equity is recorded
    kite.prices = {"AAA": 70.0}  # AAA closes 30% down, below its stop: the account is down 3% today
    code, messages = job(live, clock, "evening", wed, 18, 30)
    assert "BBB.NS: entry not sent: today -3.0% (no new entries below -2%)" in messages[0]
    kite.prices = {}  # Kite has no price for AAA: valued at its entry price, the account is Rs 97,000 again...
    code, messages = job(live, clock, "evening", thu, 18, 30)
    assert "AAA.NS: no price from Kite, so the risk checks value it at its entry price" in messages[0]
    assert "CCC.NS: buy 100 at the open (SENT)" in messages[0]  # ...up 3% on the day, Rs 500 of risk is 100 shares
    assert [(r["session"], r["equity"]) for _, r in live.store.table("live_equity").iterrows()] == [
        ("2026-08-10", 100_000.0), ("2026-08-11", 100_000.0), ("2026-08-12", 97_000.0), ("2026-08-13", 100_000.0)]
    live, kite, clock = from_source(tmp_path / "smaller", {SIGNAL_DAY: [entry("AAA.NS", paper_quantity=2000)]})
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)  # 20% of the account at a 5% stop risks 1%
    assert "AAA.NS: buy 100 at the open (SENT)" in messages[0]  # 200 scaled, cut to 100 by the 0.5% risk limit


REASON = "I chose to trade it with real money before it has passed its criteria."


def test_a_real_money_trial_must_be_dated_capped_and_explained(tmp_path):
    path = tmp_path / "overrides.toml"
    assert load_overrides(path) == ()
    good = 'max_capital = 300000\nreason = "' + REASON + '"\n'
    path.write_text("[B1F]\ndecided = 2026-10-25\nuntil = 2027-01-24\n" + good
                    + "[LONG]\ndecided = 2026-10-25\nuntil = 2027-06-30\n" + good
                    + "[UNDATED]\ndecided = \"soon\"\nuntil = 2027-01-24\n" + good
                    + "[UNCAPPED]\ndecided = 2026-10-25\nuntil = 2027-01-24\nmax_capital = \"lots\"\nreason = \"" + REASON + "\"\n"
                    + "[TERSE]\ndecided = 2026-10-25\nuntil = 2027-01-24\nmax_capital = 300000\nreason = \"why not\"\n",
                    encoding="utf-8")
    found = {o.strategy_id: o for o in load_overrides(path)}
    assert found["B1F"] == Override("B1F", date(2026, 10, 25), date(2027, 1, 24), 300_000.0, REASON)
    assert "until must be on or after decided, and at most 92 days later" in found["LONG"].problem
    assert "must be dates" in found["UNDATED"].problem and found["UNDATED"].decided is None
    assert "max_capital must be an amount above zero" in found["UNCAPPED"].problem
    assert "reason must say in your own words" in found["TERSE"].problem
    paper, live, kite, clock = setup(tmp_path)  # T1 is LIVE_SMALL on evidence
    live.overrides = (found["TERSE"], Override("XX", SIGNAL_DAY, SIGNAL_DAY, 1.0, REASON))
    text = status_text(live)
    assert "Real-money trial not opening trades: config/overrides.toml [TERSE]: reason must say" in text
    assert "XX has no paper account for the live jobs to follow" in text and "on for T1" in text
    with pytest.raises(ValueError, match="not with a real-money override"):
        replace(live, dry_run=True)


def test_a_real_money_trial_opens_trades_only_within_its_limits(tmp_path):
    live, kite, clock = from_source(tmp_path, {SIGNAL_DAY: [entry("AAA.NS")]})
    live.registry = StrategyRegistry([])  # TS has passed nothing
    assert job(live, clock, "evening", SIGNAL_DAY, 18, 30) == (0, [])
    live.overrides = (Override("TS", SIGNAL_DAY, date(2026, 8, 31), 150_000.0, REASON),)
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert messages[0].startswith("<b>[LIVE · real-money trial, not approved by evidence] Live evening</b>")
    assert "AAA.NS: buy 100 at the open (SENT)" in messages[0]
    assert "on for TS with Rs 100,000" in status_text(live)
    assert "Real-money trial of TS, decided 2026-08-10, until 2026-08-31, at most Rs 150,000: NOT approved" in status_text(live)
    live.settings = replace(live.settings, live_capital=150_000)
    assert "TS must first pass Level 6 (status LIVE)" in capital_for_today(live, date(2026, 8, 28))[1][0]  # can't grow
    live.settings = replace(live.settings, live_capital=200_000)
    assert "capital Rs 200,000 is above the real-money trial's cap of Rs 150,000" in status_text(live)
    live.settings = replace(live.settings, live_capital=100_000)
    clock.at(date(2026, 8, 7), 18, 30)
    assert "the real-money trial of TS starts on 2026-08-10" in status_text(live)


def holding_aaa(tmp_path, orders_on):
    """A live strategy (TS) that bought AAA at Tuesday's open and protected it with a stop."""
    live, kite, clock = from_source(tmp_path, {SIGNAL_DAY: [entry("AAA.NS")], **orders_on})
    job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    kite.new_day()
    kite.fill(kite.orders[0], 100.0)
    kite.prices = {"AAA": 100.0}
    job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    return live, kite, clock


def test_when_a_trial_ends_or_a_status_falls_its_live_trades_only_exit(tmp_path):
    wed, thu = date(2026, 8, 12), date(2026, 8, 13)
    sell = LiveOrder("TS", "TS AAA.NS exit", "AAA.NS", "sell", 0, 1_000_000, 0.0)
    live, kite, clock = holding_aaa(tmp_path / "trial", {wed: [entry("BBB.NS"), sell]})
    live.registry = StrategyRegistry([])
    live.overrides = (Override("TS", SIGNAL_DAY, date(2026, 8, 11), 100_000.0, REASON),)  # its last session: Tuesday
    code, messages = job(live, clock, "evening", wed, 18, 30)
    assert "BBB.NS: entry not sent: the real-money trial of TS ended on 2026-08-11: its live trades only exit" in messages[0]
    assert "AAA.NS: sell 100 at the open (SENT)" in messages[0] and "exits only for TS" in status_text(live)
    kite.new_day()
    kite.fill(kite.by_tag(broker.exit_order("TS AAA.NS exit", "AAA.NS", 100).tag), 101.0)
    code, messages = job(live, clock, "morning", thu, 9, 20)
    assert "AAA.NS exit: sell 100 at 101.00" in messages[0] and "AAA.NS: stop deleted (DONE)" in messages[0]
    assert "LOCKED" in status_text(live) and "the real-money trial of TS ended on 2026-08-11" in status_text(live)

    live, kite, clock = holding_aaa(tmp_path / "fell", {wed: [entry("BBB.NS"), sell]})
    live.registry = StrategyRegistry([StrategyRecord("TS", "Source strategy", "PAPER")])  # its evidence decayed
    code, messages = job(live, clock, "evening", wed, 18, 30)
    assert "BBB.NS: entry not sent: TS is no longer LIVE_SMALL or LIVE: its live trades only exit" in messages[0]
    assert "AAA.NS: sell 100 at the open (SENT)" in messages[0]


def test_the_stocks_you_hold_yourself_are_never_bought(tmp_path):
    path = tmp_path / "never_trade.toml"
    assert load_never_trade(path) == frozenset()
    path.write_text('stocks = ["mine", "OWNED.NS", " KEPT ", ""]\n', encoding="utf-8")
    assert load_never_trade(path) == {"MINE.NS", "OWNED.NS", "KEPT.NS"}
    sell = LiveOrder("TS", "TS AAA.NS exit", "AAA.NS", "sell", 0, 1_000_000, 0.0)
    live, kite, clock = holding_aaa(tmp_path / "live", {date(2026, 8, 12): [entry("BBB.NS"), entry("CCC.NS"), sell]})
    live.never_trade = frozenset({"AAA.NS", "BBB.NS"})  # AAA was bought before it was listed: its exit still goes
    code, messages = job(live, clock, "evening", date(2026, 8, 12), 18, 30)
    assert "BBB.NS: entry not sent: you hold it yourself, so the bot never buys it" in messages[0]
    assert "CCC.NS: buy 100 at the open (SENT)" in messages[0] and "AAA.NS: sell 100 at the open (SENT)" in messages[0]
    assert "Never bought (you hold them yourself): AAA, BBB" in status_text(live)


def test_the_morning_job_handles_stops_that_cant_wait(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    for symbol in ("AAA.NS", "BBB.NS", "CCC.NS"):
        live.store.save_position(Position("T1", symbol, 10, 100.0, 95.0, today))
        live.store.add_fill(today, "E" + symbol[:3], "T1", symbol, "buy", 10, 100.0)
        kite.positions["net"].append({"tradingsymbol": symbol[:3], "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"AAA": 94.0, "BBB": 100.0, "CCC": 100.0}  # AAA is below its stop already
    code, messages = job(live, clock, "morning", today, 9, 20)
    assert "AAA.NS: stop exit (SENT)" in messages[0] and "BBB.NS: stop (SENT)" in messages[0]
    assert kite.by_tag(broker.stop_exit(live.store.positions()["AAA.NS"]).tag)["order_type"] == "MARKET"
    bbb = live.store.positions()["BBB.NS"]
    gtt = kite.gtts[int(live.store.order(broker.stop_order(bbb).tag)["kite_id"])]
    sell = kite.trigger(gtt["id"])
    kite.prices = {"AAA": 94.0, "BBB": 85.0, "CCC": 100.0}  # BBB gapped below its stop's limit: its sell can't fill
    ccc = live.store.positions()["CCC.NS"]
    kite.gtts[int(live.store.order(broker.stop_order(ccc).tag)["kite_id"])]["status"] = "rejected"
    code, messages = job(live, clock, "morning", today, 9, 25)
    assert "BBB.NS: gap exit (DONE)" in messages[0] and sell["order_type"] == "MARKET"
    assert "CCC.NS has no stop at Kite (cancelled: GTT rejected). Place one by hand." in messages[0]
    code, messages = job(live, clock, "morning", today, 9, 40)
    assert not any("CCC.NS has no stop" in text for text in messages)  # said once a day, though the job repeats
    code, messages = job(live, clock, "morning", date(2026, 8, 12), 9, 20)
    assert "CCC.NS has no stop at Kite" in messages[0]  # and again the next day, until it's fixed


def test_the_evening_job_waits_for_the_paper_run(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)  # the paper run hasn't processed the day
    assert "hasn't processed 2026-08-10 yet" in messages[0] and kite.orders == []
    assert job(live, clock, "evening", date(2026, 8, 15), 18, 30) == (0, [])  # a Saturday: nothing to do


def test_live_stops_and_time_exits_on_a_quiet_day(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    live.store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, today, max_hold_days=5))
    live.store.add_fill(today, "Eaaa", "T1", "AAA.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "AAA", "exchange": "NSE", "product": "CNC", "quantity": 10})
    assert job(live, clock, "preclose", today, 15, 15) == (0, [])  # day 1 of 5
    for weekend_job, hour in (("morning", 9), ("preclose", 15)):  # Saturday: no session, nothing to do
        assert job(live, clock, weekend_job, date(2026, 8, 15), hour, 20) == (0, [])
    kite.prices = {"AAA": 100.0}
    job(live, clock, "morning", today, 9, 20)
    gtt = next(iter(kite.gtts.values()))
    kite.trigger(gtt["id"])  # its sell is working on the last day
    code, messages = job(live, clock, "preclose", date(2026, 8, 17), 15, 15)
    assert "AAA.NS: no time exit: its stop's sell is already working" in messages[-1]


def test_the_command_needs_paper_records(tmp_path, monkeypatch):
    monkeypatch.setattr(live_jobs, "ROOT", tmp_path)
    monkeypatch.setattr(live_jobs, "configure_logging", lambda **kwargs: None)  # not into the real logs/
    with pytest.raises(SystemExit, match="No paper records yet"):
        live_jobs.main(["status"])


def test_the_evening_job_sends_only_todays_orders_of_live_strategies(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    store = paper.store
    store.record_session(SIGNAL_DAY, 1_000_000, 1_000_000)
    store.add_order("T1:AAA.NS:2026-08-07:buy", "T1", "AAA.NS", "buy", 1000, date(2026, 8, 7), 100.0, 0.05)  # an old one
    store.add_order("T2:BBB.NS:2026-08-10:buy", "T2", "BBB.NS", "buy", 1000, SIGNAL_DAY, 100.0, 0.05)  # not live
    store.add_order("T1:AAPL:2026-08-10:buy", "T1", "AAPL", "buy", 10, SIGNAL_DAY, 100.0, 0.05)  # US: by hand
    store.add_order("T1:CCC.NS:2026-08-10:sell", "T1", "CCC.NS", "sell", 1000, SIGNAL_DAY, 100.0, 0.0)  # none held live
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert code == 0 and messages[0].endswith("Live capital: Rs 100,000 (the first step).") and kite.orders == []


def test_a_time_exit_waits_while_its_stop_cant_be_deleted(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    live.store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, today, max_hold_days=1))
    live.store.add_fill(today, "Eaaa", "T1", "AAA.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "AAA", "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"AAA": 100.0}
    job(live, clock, "morning", today, 9, 20)
    kite.failures = [("http", 400, "InputException", False)]  # Kite refuses to delete the stop
    code, messages = job(live, clock, "preclose", today, 15, 15)
    assert "AAA.NS: time exit not sent: its stop couldn't be deleted (REJECTED)" in messages[-1]
    assert not any(order["transaction_type"] == "SELL" for order in kite.orders)  # never two sells at once
    assert run("morning", live, backup_dir=tmp_path / "backups") == 0
    assert (tmp_path / "backups" / "live-2026-08-11.db").exists()


def command_line(tmp_path, monkeypatch, **changes):
    """The command, apart from this PC's own setup: records in tmp_path, live off unless changed, no override, no
    never-trade list, and no internet address looked up."""
    settings = replace(load_settings(env={}), live_enabled=False, live_capital=0.0, **changes)
    monkeypatch.setattr(live_jobs, "ROOT", tmp_path)
    monkeypatch.setattr(live_jobs, "configure_logging", lambda **kwargs: None)  # not into the real logs/
    monkeypatch.setattr(live_jobs, "notifier_from_settings", lambda settings: FakeNotifier())
    monkeypatch.setattr(live_jobs, "load_settings", lambda: settings)
    monkeypatch.setattr(live_jobs, "load_overrides", lambda: ())
    monkeypatch.setattr(live_jobs, "load_never_trade", lambda: frozenset())
    monkeypatch.setattr(live_jobs, "public_ip", lambda: pytest.fail("no internet address lookup expected"))
    PaperStore(tmp_path / settings.paper_database, settings.paper_starting_capital).close()
    return settings


def test_the_command_line(tmp_path, monkeypatch, capsys):
    command_line(tmp_path, monkeypatch)
    live_jobs.main(["status"])
    assert "Live trading: LOCKED" in capsys.readouterr().out  # off
    live_jobs.main(["track"])
    assert "live price" in capsys.readouterr().out
    assert not (tmp_path / "state" / "live.db").exists()  # looking leaves no live records behind
    with pytest.raises(SystemExit) as stopped:
        live_jobs.main(["evening"])
    assert stopped.value.code == 0


def test_a_job_run_late_sends_nothing(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    for name, day, hour in (("preclose", date(2026, 8, 11), 16), ("evening", SIGNAL_DAY, 10), ("morning", SIGNAL_DAY, 8)):
        code, messages = job(live, clock, name, day, hour)
        assert code == 0 and f"Nothing sent: the {name} job runs between" in messages[0]
    assert kite.orders == [] and kite.gtts == {}


def test_a_stop_whose_answer_was_lost_is_sent_again_only_if_kite_lacks_it(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    for symbol in ("AAA.NS", "BBB.NS"):
        live.store.save_position(Position("T1", symbol, 10, 100.0, 95.0, today))
        live.store.add_fill(today, "E" + symbol[:3], "T1", symbol, "buy", 10, 100.0)
        kite.positions["net"].append({"tradingsymbol": symbol[:3], "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"AAA": 100.0, "BBB": 100.0}
    kite.failures = [("timeout", True), ("timeout", False)]  # AAA's stop reached Kite, BBB's didn't
    job(live, clock, "morning", today, 9, 20)
    assert len(kite.gtts) == 1
    job(live, clock, "morning", today, 9, 25)
    assert sorted(g["condition"]["tradingsymbol"] for g in kite.gtts.values()) == ["AAA", "BBB"]  # one each


def test_a_time_exit_without_a_stop_sells_straight_away(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    today = date(2026, 8, 11)
    live.store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, today, max_hold_days=1))
    live.store.add_fill(today, "Eaaa", "T1", "AAA.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "AAA", "exchange": "NSE", "product": "CNC", "quantity": 10})
    code, messages = job(live, clock, "preclose", today, 15, 15)  # the morning job never ran: no stop to delete
    assert "AAA.NS: time exit, sell 10 (SENT)" in messages[0] and [c[0] for c in kite.calls].count("DELETE") == 0


def test_the_read_only_check_holds_kites_answers_to_what_the_code_relies_on(tmp_path):
    kite = FakeKite()
    api = KiteOrders("key", "AT", http=kite, sleep=lambda s: None)
    kite.holdings = [{"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 10, "t1_quantity": 5, "used_quantity": 0}]
    kite.prices = {"NIFTYBEES": 285.5}
    api.place_order("amo", broker.entry_order("k", "INFY.NS", 5).params)
    api.place_gtt(broker.stop_order(Position("T1", "INFY.NS", 5, 100.0, 95.0, date(2026, 8, 11))).params)
    writes_before = [call for call in kite.calls if call[0] != "GET"]
    seen, problems = check(api)
    assert problems == [] and "Equity funds available: Rs 100,000.00" in seen
    assert "  NSE:INFY: 10 settled + 5 T+1 - 0 sold today = 15 held" in seen and "NIFTYBEES last price: 285.5" in seen
    assert "NIFTYBEES today: open 285.5, high 285.5, low 285.5" in seen  # what a dry run fills at
    assert [call for call in kite.calls if call[0] != "GET"] == writes_before  # it wrote nothing
    counts, _ = check(api, detail=False)  # for Telegram: no funds, no holdings
    assert not any("funds" in line or "INFY" in line for line in counts) and "holdings: 1" in counts
    del kite.holdings[0]["t1_quantity"]
    kite.positions = {"net": []}
    kite.gtts[next(iter(kite.gtts))]["condition"].pop("trigger_values")
    store = LiveStore(tmp_path / "live.db")
    store.save_position(Position("T1", "TCS.NS", 3, 50.0, 47.5, date(2026, 8, 11)))
    store.add_fill(date(2026, 8, 11), "Etcs", "T1", "TCS.NS", "buy", 3, 50.0)
    seen, problems = check(api, store)
    assert problems == ["positions: the answer lacks the 'net' and 'day' lists", "holdings: 1 without 't1_quantity'",
                        "GTTs: a trigger without its trigger values or its order's quantity",
                        "TCS.NS: the system holds 3 shares but the account has 0"]


def test_the_check_command(tmp_path, monkeypatch, capsys):
    command_line(tmp_path, monkeypatch, kite_static_ip="198.51.100.7")

    def no_login(settings):
        raise KiteAuthError("no valid Kite session today (run: python -m trader.data.kite login)")
    monkeypatch.setattr(live_jobs, "from_session", no_login)
    with pytest.raises(SystemExit, match="Kite: no valid Kite session today"):
        live_jobs.main(["check"])
    kite = FakeKite()
    kite.prices = {"NIFTYBEES": 285.5}
    monkeypatch.setattr(live_jobs, "from_session", lambda settings: KiteOrders("key", "AT", http=kite, sleep=lambda s: None))
    monkeypatch.setattr(live_jobs, "public_ip", lambda: "198.51.100.7")  # still at the registered address
    with pytest.raises(SystemExit) as finished:
        live_jobs.main(["check"])
    assert finished.value.code == 0 and "Every field the order system relies on is there" in capsys.readouterr().out
    monkeypatch.setattr(live_jobs, "public_ip", lambda: "203.0.113.9")  # the provider gave this PC a new address
    with pytest.raises(SystemExit) as finished:
        live_jobs.main(["check"])
    assert finished.value.code == 1 and "PROBLEM: This PC's internet address is now 203.0.113.9" in capsys.readouterr().out


class Answer:
    def __init__(self, status_code, text):
        self.status_code, self.text = status_code, text


def test_this_pcs_internet_address_and_kites_registered_one(tmp_path):
    def asked(*answers):
        queue = list(answers)

        class Http:
            @staticmethod
            def get(url, timeout):
                answer = queue.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return answer
        return Http
    assert live_jobs.public_ip(asked(Answer(200, "203.0.113.9\n"))) == "203.0.113.9"
    assert live_jobs.public_ip(asked(requests.ConnectionError("down"), Answer(200, "2001:db8::1"))) == "2001:db8::1"
    assert live_jobs.public_ip(asked(Answer(503, "busy"), Answer(200, "<html>not an address</html>"))) is None

    paper, live, kite, clock = setup(tmp_path)
    live.settings = replace(live.settings, kite_static_ip="198.51.100.7")
    live.store.save_position(Position("T1", "AAA.NS", 10, 100.0, 95.0, date(2026, 8, 11)))
    live.store.add_fill(date(2026, 8, 11), "Eaaa", "T1", "AAA.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "AAA", "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"AAA": 100.0}
    live.address = lambda: "203.0.113.9"  # the address changed overnight
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert code == 0 and "This PC's internet address is now 203.0.113.9, but Kite has 198.51.100.7" in messages[0]
    assert "AAA.NS: stop (HAND)" in messages[0] and "[LIVE · real money] Please do this by hand" in messages[1]
    assert "1. SET A STOP-LOSS on AAA\nKite app: AAA > Create GTT > Single > Sell > trigger price ₹95.00 > quantity 10 " \
           "> price ₹90.25 > Create." in messages[1]
    assert writes(kite) == [] and kite.gtts == {}  # only read: Kite would refuse the stop, and not take it again
    assert job(live, clock, "morning", date(2026, 8, 11), 9, 35) == (0, [])  # told once a day
    live.address = lambda: None  # the address can't be looked up: Kite decides
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 50)
    assert code == 0 and "AAA.NS: stop (SENT)" in messages[0]  # a stop you didn't place goes in by itself


def writes(kite):
    return [call for call in kite.calls if call[0] != "GET"]


def test_orders_kite_refuses_are_handed_to_you_and_followed_once_done(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    live.settings = replace(live.settings, kite_static_ip="198.51.100.7")
    live.address = lambda: "203.0.113.9"
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    code, messages = job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    assert code == 0 and "AAA.NS: buy 100 at the open (HAND)" in messages[0] and writes(kite) == []
    assert ("1. BUY 100 shares of AAA\nKite app: AAA > Buy > AMO > Market > quantity 100 > Buy. It buys at tomorrow's "
            "9:15 open. Do it tonight, or skip it.") in messages[1] and "3. BUY 100 shares of CCC" in messages[1]
    assert {r["status"] for r in live.store.orders()} == {"HAND"}
    aaa, ccc = kite.by_hand("AAA", "BUY", 100), kite.by_hand("CCC", "BUY", 60)  # you buy two of the three, CCC smaller

    kite.new_day()  # Tue 11 Aug: your after-market buys fill at the open; the address is fixed
    kite.fill(aaa, 101.0)
    kite.fill(ccc, 102.0)
    kite.prices = {"AAA": 101.0, "CCC": 102.0}
    live.address = lambda: "198.51.100.7"
    code, messages = job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    assert "AAA.NS: your buy is in Kite. Thanks, I'll take it from here" in messages[0]
    assert "AAA.NS entry: buy 100 at 101.00" in messages[0] and "CCC.NS entry: buy 60 at 102.00" in messages[0]
    assert "AAA.NS: stop (SENT)" in messages[0] and "CCC.NS: stop (SENT)" in messages[0] and len(messages) == 1
    assert {s: p.quantity for s, p in live.store.positions().items()} == {"AAA.NS": 100, "CCC.NS": 60}
    assert not any(o["tradingsymbol"] == "BBB" for o in kite.orders)  # a buy handed to you is never also sent
    assert live.store.order(broker.entry_order("T1:BBB.NS:2026-08-10:buy", "BBB.NS", 100).tag)["status"] == "HAND"

    code, messages = job(live, clock, "morning", date(2026, 8, 12), 9, 20)  # its open has passed: BBB is skipped
    assert "BBB.NS: your buy wasn't done in time, so I skip it" in messages[0]
    assert live.store.order(broker.entry_order("T1:BBB.NS:2026-08-10:buy", "BBB.NS", 100).tag)["status"] == "NOT DONE"
    assert live.store.ledger_problems() == [] and live.kill_switch.engaged is False


def test_a_time_exit_by_hand_deletes_the_stop_first(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    live.settings = replace(live.settings, kite_static_ip="198.51.100.7")
    live.address = lambda: "198.51.100.7"
    held = Position("T1", "CCC.NS", 100, 101.0, 95.95, date(2026, 8, 11), max_hold_days=1)
    live.store.save_position(held)
    live.store.add_fill(date(2026, 8, 11), "Eccc", "T1", "CCC.NS", "buy", 100, 101.0)
    kite.positions["net"].append({"tradingsymbol": "CCC", "exchange": "NSE", "product": "CNC", "quantity": 100})
    kite.prices = {"CCC": 101.0}
    job(live, clock, "morning", date(2026, 8, 11), 9, 20)  # the stop goes in as usual
    live.address = lambda: "203.0.113.9"
    code, messages = job(live, clock, "preclose", date(2026, 8, 11), 15, 15)
    assert "1. DELETE the stop-loss of CCC\nKite app: Orders > GTT > CCC > Delete." in messages[-1]
    assert "2. SELL 100 shares of CCC NOW, before 3:30 pm (its time is up)" in messages[-1]
    [stop] = kite.gtts.values()
    stop["status"] = "deleted"  # you delete it, then sell
    kite.fill(kite.by_hand("CCC", "SELL", 100, "regular"), 100.0)
    code, messages = job(live, clock, "evening", date(2026, 8, 11), 18, 30)
    assert "CCC.NS: your sell is in Kite" in messages[0] and "CCC.NS time exit: sell 100 at 100.00" in messages[0]
    assert live.store.positions() == {} and writes(kite)[-1][0] == "POST"  # only the stop the bot placed itself


def test_your_own_trades_and_the_stops_own_sell_are_never_taken_for_hand_orders(tmp_path):
    paper, live, kite, clock = setup(tmp_path)
    live.settings = replace(live.settings, kite_static_ip="198.51.100.7")
    live.address = lambda: "203.0.113.9"
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    tagged = kite.by_hand("AAA", "BUY", 100)
    tagged["tag"] = "Eother"  # another app's order carries a tag
    kite.by_hand("BBB", "SELL", 5)  # the other side
    kite.reject(kite.by_hand("CCC", "BUY", 100), "insufficient funds")  # refused: still to do
    job(live, clock, "evening", SIGNAL_DAY, 19, 0)
    assert {r["status"] for r in live.store.orders()} == {"HAND"}

    live.address = lambda: "198.51.100.7"  # a holding whose stop goes in; then a sale of it is handed to you
    live.store.save_position(Position("T1", "DDD.NS", 10, 100.0, 95.0, date(2026, 8, 11)))
    live.store.add_fill(date(2026, 8, 11), "Eddd", "T1", "DDD.NS", "buy", 10, 100.0)
    kite.positions["net"].append({"tradingsymbol": "DDD", "exchange": "NSE", "product": "CNC", "quantity": 10})
    kite.prices = {"DDD": 100.0}
    job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    oms = OMS(live.store, live.connect(), clock, by_hand="the address moved", calendar=NSE)
    sale = broker.exit_order("T1:DDD.NS:2026-08-11:sell", "DDD.NS", 10)
    assert oms.submit(date(2026, 8, 11), "T1", sale) == "HAND" and oms.handed == [sale]
    [stop] = kite.gtts.values()
    kite.trigger(stop["id"])  # the stop's own sell has no tag either: it is the stop's, not your sale
    oms.refresh(date(2026, 8, 11))
    assert live.store.order(sale.tag)["status"] == "HAND"
    assert live.store.order(broker.stop_order(live.store.positions()["DDD.NS"]).tag)["status"] == "TRIGGERED"



def test_live_capital_grows_only_in_deliberate_steps(tmp_path):
    paper, live, kite, clock = setup(tmp_path, capital=50_000)  # T1 at LIVE_SMALL
    first = date(2026, 8, 10)
    assert capital_for_today(live, first) == (50_000, ["Live capital: Rs 50,000 (the first step)."])
    assert capital_for_today(live, first) == (50_000, [])
    live.settings = replace(live.settings, live_capital=100_000)
    capital, news = capital_for_today(live, date(2026, 9, 30))
    assert capital == 50_000 and "T1 must first pass Level 6 (status LIVE)" in news[0]
    live.registry = StrategyRegistry([StrategyRecord("T1", "Test strategy", "LIVE")])
    live.settings = replace(live.settings, live_capital=150_000)
    assert "more than 2x the current step" in capital_for_today(live, date(2026, 9, 30))[1][0]
    live.settings = replace(live.settings, live_capital=100_000)
    assert "1 of 4 weeks since the last step" in capital_for_today(live, date(2026, 8, 17))[1][0]
    assert capital_for_today(live, date(2026, 9, 30)) == (100_000, ["Live capital raised to Rs 100,000."])
    live.settings = replace(live.settings, live_capital=60_000)
    assert capital_for_today(live, date(2026, 10, 1)) == (60_000, ["Live capital lowered to Rs 60,000."])
    assert [row["reason"] for row in live.store.capital_steps()] == ["first step", "raised", "lowered"]


def test_a_losing_step_reverts_by_itself_and_raising_again_is_deliberate(tmp_path):
    paper, live, kite, clock = setup(tmp_path, status="LIVE", capital=10_000)
    capital_for_today(live, date(2026, 8, 3))
    live.settings = replace(live.settings, live_capital=20_000)
    assert capital_for_today(live, date(2026, 9, 7))[0] == 20_000
    live.store.add_fill(date(2026, 9, 8), "E1", "T1", "INFY.NS", "buy", 100, 100.0)
    live.store.add_fill(date(2026, 9, 9), "X1", "T1", "INFY.NS", "sell", 100, 75.0)  # about 12.7% of the step
    capital, news = capital_for_today(live, date(2026, 9, 10))
    assert capital == 10_000 and news[0].startswith("Live capital reverted to Rs 10,000: the Rs 20,000 step lost 12.")
    later = date(2026, 11, 2)
    assert "after a revert, lower [live] capital" in capital_for_today(live, later)[1][0]  # still asking for 20,000
    live.settings = replace(live.settings, live_capital=10_000)
    assert capital_for_today(live, later) == (10_000, ["Live capital stays at Rs 10,000: the revert is acknowledged."])
    live.settings = replace(live.settings, live_capital=20_000)
    assert capital_for_today(live, date(2026, 12, 7)) == (20_000, ["Live capital raised to Rs 20,000."])


def test_a_first_step_that_loses_too_much_stops_new_live_entries(tmp_path):
    paper, live, kite, clock = setup(tmp_path, capital=10_000)
    capital_for_today(live, date(2026, 8, 3))
    assert step_drawdown(live.store, date(2026, 8, 3), 10_000) == 0.0  # no trades yet
    live.store.add_fill(date(2026, 8, 4), "E1", "T1", "INFY.NS", "buy", 100, 100.0)
    live.store.add_fill(date(2026, 8, 5), "X1", "T1", "INFY.NS", "sell", 100, 85.0)
    assert step_drawdown(live.store, date(2026, 8, 3), 0) == 0.0
    capital, news = capital_for_today(live, date(2026, 8, 6))
    assert capital == 0.0 and news[0].startswith("Live capital reverted to Rs 0")



def a_live_week(tmp_path):
    """The week of test_a_week_of_live_trading_mirrors_paper, without its checks."""
    paper, live, kite, clock = setup(tmp_path)
    paper.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    job(live, clock, "evening", SIGNAL_DAY, 18, 30)
    kite.new_day()
    for order in list(kite.orders):
        kite.fill(order, 101.0)
    kite.prices = {"AAA": 101.0, "BBB": 101.0, "CCC": 101.0}
    job(live, clock, "morning", date(2026, 8, 11), 9, 20)
    paper.run(until=date(2026, 8, 14))
    kite.fill(kite.trigger(next(g for g in kite.gtts.values() if g["condition"]["tradingsymbol"] == "AAA")["id"]), 95.95)
    job(live, clock, "evening", date(2026, 8, 14), 18, 30)
    kite.new_day()
    kite.fill(kite.by_tag(broker.exit_order("T1:BBB.NS:2026-08-14:sell", "BBB.NS", 100).tag), 104.0)
    job(live, clock, "morning", date(2026, 8, 17), 9, 20)
    job(live, clock, "preclose", date(2026, 8, 17), 15, 15)
    kite.fill(kite.by_tag(broker.time_exit(Position("T1", "CCC.NS", 100, 101.0, 95.95, date(2026, 8, 11))).tag), 102.0)
    paper.run(until=date(2026, 8, 17))
    job(live, clock, "evening", date(2026, 8, 17), 18, 30)
    return paper, live


def test_level_6_evidence_from_a_live_week(tmp_path):
    from trader.execution.report import live_evidence
    paper, live = a_live_week(tmp_path)
    evidence = live_evidence(paper.store, live.store, "T1", date(2026, 8, 18), 100_000)
    stats = evidence.stats
    assert (stats["round_trips"], stats["fill_rate"], stats["slippage"], stats["interventions"]) == (3, 1.0, 0.0, 0)
    assert stats["worst_week"] == pytest.approx(-0.00548, abs=1e-5)  # AAA's stop (Rs 505 and charges): not yet bad
    failed = {c["number"] for c in evidence.checks if not c["passed"]}
    assert failed == {1, 2, 6, 7} and evidence.decision == "LIVE_SMALL"  # too early to say more, and nothing wrong
    assert evidence.kind == "live" and live_evidence(paper.store, live.store, "T9", date(2026, 8, 18), 100_000) is None


def test_the_read_only_check_finds_quotes_a_dry_run_cant_fill_at():
    class NoOhlc(FakeKite):
        def get(self, url, params=None, headers=None, timeout=None):
            if url.endswith("/quote/ohlc"):
                return ok({key: {"last_price": 285.5} for key in params["i"]})
            return super().get(url, params, headers, timeout)
    kite = NoOhlc()
    kite.prices = {"NIFTYBEES": 285.5}
    seen, problems = check(KiteOrders("key", "AT", http=kite, sleep=lambda s: None))
    assert problems == ["quotes: the open, high and low a dry run relies on are missing"]
