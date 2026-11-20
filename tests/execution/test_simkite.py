"""The simulated Zerodha account behind dry runs, and a dry run of the live jobs for paper trial 1's bunch (B1F): the
order system runs unchanged against it, and nothing but price quotes is ever asked of Kite."""
import html
from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from tests.execution.test_paper_trader import FakeNotifier
from trader.config import load_settings
from trader.core.models import Position
from trader.execution import live as live_jobs
from trader.execution.kite_orders import KiteOrders, OrderRejected, held_quantity
from trader.execution.live import Live, run
from trader.execution.oms import LiveStore
from trader.execution.simkite import SimKite
from trader.execution.sources import TRIAL, trial_orders
from trader.execution.store import PaperStore
from trader.markets.calendar import load_calendars
from trader.registry import StrategyRegistry
from trader.research.costs import ZERODHA_DELIVERY
from trader.risk.killswitch import KillSwitch

IST = ZoneInfo("Asia/Kolkata")
NSE = load_calendars()["NSE"]
CHARGES = ZERODHA_DELIVERY.with_slippage(0.0)  # what each simulated fill pays; slippage is in the price
MON, TUE, WED, THU = date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 8, 10, 18, 30, tzinfo=IST)

    def at(self, day, hour, minute=0):
        self.now = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)

    def __call__(self):
        return self.now


class Quotes:
    """The day's open, high, low and last price per stock, as Kite's quotes would give them."""

    def __init__(self):
        self.day, self.calls = {}, []

    def set(self, symbol, open_, low, last):
        self.day[symbol] = {"open": open_, "high": max(open_, last), "low": low, "last_price": last}

    def __call__(self, symbols):
        self.calls.append(list(symbols))
        return {s: dict(self.day[s]) for s in symbols}


def account(tmp_path, clock, quotes, cash=100_000.0):
    return SimKite(tmp_path / "kite.json", quotes, clock, NSE, cash)


def client(sim):
    return KiteOrders("dry-run", "dry-run", http=sim, sleep=lambda s: None)


def order(symbol, side, quantity, order_type="MARKET", tag="T1"):
    return {"exchange": "NSE", "tradingsymbol": symbol, "transaction_type": side, "order_type": order_type,
            "quantity": quantity, "product": "CNC", "validity": "DAY", "market_protection": -1, "tag": tag}


def stop(symbol, quantity, trigger, limit, last):
    return {"type": "single", "condition": {"exchange": "NSE", "tradingsymbol": symbol, "trigger_values": [trigger],
                                            "last_price": last},
            "orders": [{"exchange": "NSE", "tradingsymbol": symbol, "transaction_type": "SELL", "quantity": quantity,
                        "order_type": "LIMIT", "product": "CNC", "price": limit}]}


def test_after_market_orders_fill_at_the_next_open_and_holdings_settle(tmp_path):
    clock, quotes = Clock(), Quotes()
    kite = client(account(tmp_path, clock, quotes))
    buy = kite.place_order("amo", order("AAA", "BUY", 10))
    with pytest.raises(OrderRejected, match="Markets are closed"):
        kite.place_order("regular", order("AAA", "BUY", 1))
    assert kite.orders()[0]["status"] == "AMO REQ RECEIVED" and quotes.calls == []  # no price needed yet
    clock.at(TUE, 9, 20)
    quotes.set("AAA", 100.0, 99.0, 100.5)
    filled = next(o for o in kite.orders() if o["order_id"] == buy)
    assert (filled["status"], filled["filled_quantity"], filled["average_price"]) == ("COMPLETE", 10, 100.0)
    assert held_quantity(kite.holdings(), kite.positions(), "AAA") == 10
    assert kite.margins()["equity"]["net"] == pytest.approx(100_000 - 1_000 - CHARGES.one_side(1_000, "buy"))
    with pytest.raises(OrderRejected, match="while the market is open"):
        kite.place_order("amo", order("AAA", "SELL", 10))
    clock.at(WED, 9, 20)
    holding = kite.holdings()[0]
    assert (holding["quantity"], holding["t1_quantity"], kite.positions()["net"]) == (0, 10, [])  # T+1 overnight
    again = client(account(tmp_path, clock, quotes))  # the account is kept on disk between jobs
    assert [o["order_id"] for o in again.orders()] == []  # Kite's order book is a day's


def test_a_stop_fires_on_a_later_low_and_a_gap_below_its_limit_waits_for_the_gap_exit(tmp_path):
    clock, quotes = Clock(), Quotes()
    sim = account(tmp_path, clock, quotes)
    kite = client(sim)
    for symbol in ("AAA", "BBB"):
        kite.place_order("amo", order(symbol, "BUY", 10))
    clock.at(TUE, 9, 20)
    quotes.set("AAA", 100.0, 90.0, 100.0)  # today's low is from before the stops existed: it doesn't count
    quotes.set("BBB", 100.0, 90.0, 100.0)
    kite.orders()
    a, b = kite.place_gtt(stop("AAA", 10, 95.0, 90.25, 100.0)), kite.place_gtt(stop("BBB", 10, 95.0, 90.25, 100.0))
    clock.at(TUE, 15, 0)
    quotes.set("AAA", 100.0, 90.0, 96.0)
    assert {g["status"] for g in kite.gtts()} == {"active"}
    clock.at(WED, 9, 20)
    quotes.set("AAA", 97.0, 94.0, 96.0)  # fell to the trigger after the open: sold at the trigger
    quotes.set("BBB", 85.0, 84.0, 86.0)  # opened below the limit: the LIMIT sell waits
    gtts = {str(g["id"]): g for g in kite.gtts()}
    assert gtts[a]["status"] == gtts[b]["status"] == "triggered"
    sells = {o["tradingsymbol"]: o for o in kite.orders() if o["transaction_type"] == "SELL"}
    assert (sells["AAA"]["status"], sells["AAA"]["average_price"]) == ("COMPLETE", 95.0)
    assert sells["BBB"]["status"] == "OPEN"
    kite.modify_order("regular", sells["BBB"]["order_id"], {"order_type": "MARKET", "market_protection": -1})
    sold = next(o for o in kite.orders() if o["order_id"] == sells["BBB"]["order_id"])
    assert (sold["status"], sold["average_price"]) == ("COMPLETE", 86.0)
    assert held_quantity(kite.holdings(), kite.positions(), "AAA") == held_quantity(kite.holdings(), kite.positions(), "BBB") == 0
    paid = 2 * CHARGES.one_side(1_000, "buy") + CHARGES.one_side(950, "sell") + CHARGES.one_side(860, "sell")
    assert sim.state["cash"] == pytest.approx(100_000 - 2_000 + 950 + 860 - paid) and sim.state["charges"] == pytest.approx(paid)


def test_what_kite_would_reject_at_the_open_is_rejected(tmp_path):
    clock, quotes = Clock(), Quotes()
    kite = client(account(tmp_path, clock, quotes, cash=5_000))
    kite.place_order("amo", order("AAA", "BUY", 100, tag="BIG"))
    kite.place_order("amo", order("BBB", "SELL", 5, tag="NONE"))
    clock.at(TUE, 9, 20)
    quotes.set("AAA", 100.0, 99.0, 100.0)
    quotes.set("BBB", 50.0, 49.0, 50.0)
    status = {o["tag"]: (o["status"], o["status_message"]) for o in kite.orders()}
    assert status["BIG"][0] == status["NONE"][0] == "REJECTED"
    assert "Insufficient funds" in status["BIG"][1] and "Insufficient holdings" in status["NONE"][1]


# --- a dry run of the live jobs ------------------------------------------------------------------------------
def plan(entries=(), exits=(), held=(), passed=()):
    return {"entries": list(entries), "exits": list(exits), "held": {sid: "E2" for sid in held}, "passed": list(passed)}


def dry(tmp_path, plans, clock, quotes):
    """A dry run with paper trial 1's plans scripted by session ({today: plan}; a missing day hasn't been processed)."""
    paper = PaperStore(tmp_path / "paper.db", 1_000_000)
    live = live_jobs.dry_run(replace(load_settings(env={}), live_enabled=False, live_capital=0), paper, NSE,
                             FakeNotifier(), {TRIAL}, 100_000, clock=clock, directory=tmp_path / "dry", prices=quotes)
    live.sources[TRIAL] = lambda today, held: trial_orders(today, held, NSE, plan_for=lambda d, nxt: plans.get(d))
    return live


def job(live, clock, name, day, hour, minute=0):
    clock.at(day, hour, minute)
    sent = len(live.notifier.sent)
    return run(name, live), [html.unescape(text) for text in live.notifier.sent[sent:]]


def test_a_dry_run_carries_out_the_trials_plan_on_the_simulated_account(tmp_path):
    clock, quotes = Clock(), Quotes()
    aaa = {"part": "E2", "sid": "AAA", "signal_date": "2026-08-07", "tier": "N1", "strength": 0.08, "close": 100.0}
    plans = {MON: plan([aaa], held=["AAA"], passed=[("E2", "BBB", "no free place")]),
             TUE: plan(held=["AAA"]),
             WED: plan(exits=[{"part": "E2", "sid": "AAA", "signal_date": "2026-08-07", "entry_date": "2026-08-11"}])}
    live = dry(tmp_path, plans, clock, quotes)
    code, messages = job(live, clock, "evening", MON, 21, 30)
    assert code == 0 and "<b>[LIVE DRY RUN · nothing sent to Kite] Live evening</b>" in messages[0]
    assert "AAA.NS: buy 33 at the open (SENT)" in messages[0]  # Rs 3,333 (0.5% of 10 lakh over a 15% stop) scaled to 1 lakh
    assert "BBB: a buy signal, but all 5 slots of our rules are full." in messages[0]
    assert messages[1] == ("[LIVE DRY RUN] <b>India plan for Tue 11 Aug</b>\n\n<b>BUY 33 AAA at 9:15 am, placed by the "
                           "bot</b>\nWhy: after its results, it beat the market by 8% in 2 days (our rule buys these).\n"
                           "Stop-loss: the bot sets it after the buy.\n\n"
                           "BBB: a buy signal, but all 5 slots of our rules are full.")
    quotes.set("AAA", 100.0, 99.0, 100.5)
    code, messages = job(live, clock, "morning", TUE, 9, 20)
    assert "AAA.NS entry: buy 33 at 100.00" in messages[0] and "AAA.NS: stop (SENT)" in messages[0]
    position = live.store.positions()["AAA.NS"]
    assert position.stop_price == pytest.approx(85.0) and position.max_hold_days is None
    assert job(live, clock, "preclose", TUE, 15, 15) == (0, [])  # B1F's exits are at the open, never before the close
    assert job(live, clock, "evening", TUE, 21, 30) == (0, [  # held, as in paper: nothing to send
        "[LIVE DRY RUN] <b>India plan for Wed 12 Aug</b>\nNothing to buy or sell.\n\nNo new buy signals, and nothing to sell."])
    code, messages = job(live, clock, "evening", WED, 21, 30)
    assert "AAA.NS: sell 33 at the open (SENT)" in messages[0]
    quotes.set("AAA", 104.0, 103.0, 104.0)
    code, messages = job(live, clock, "morning", THU, 9, 20)
    assert "AAA.NS exit: sell 33 at 104.00" in messages[0] and "AAA.NS: stop deleted (DONE)" in messages[0]
    assert live.store.positions() == {} and live.store.ledger_problems() == []
    code, messages = job(live, clock, "evening", THU, 21, 30)
    assert "Tonight's rules run hasn't finished, so there is no plan yet" in messages[0]


def test_only_a_dry_run_may_treat_a_strategy_as_live(tmp_path):
    clock, quotes = Clock(), Quotes()
    live = dry(tmp_path, {}, clock, quotes)
    with pytest.raises(ValueError, match="only a dry run"):
        replace(live, dry_run=False)
    real = Live(load_settings(env={}), PaperStore(tmp_path / "p.db", 1_000_000), LiveStore(":memory:"),
                StrategyRegistry([]), KillSwitch(tmp_path / "K"), NSE, FakeNotifier(), connect=lambda: None,
                sources={TRIAL: lambda today, held: ([], [])})
    assert live_jobs.locks(real)[-1].startswith("no strategy has earned live money")  # B1F isn't LIVE_SMALL anywhere


def test_the_trials_orders_sell_what_paper_no_longer_holds():
    held = {"AAA.NS": Position(TRIAL, "AAA.NS", 30, 100.0, 85.0, MON),
            "CCC.NS": Position(TRIAL, "CCC.NS", 10, 50.0, 45.0, MON),
            "DDD.NS": Position("H1", "DDD.NS", 10, 50.0, 45.0, MON)}
    orders, notes = trial_orders(TUE, held, NSE, plan_for=lambda d, nxt: plan(held=["CCC"]))
    assert [(o.symbol, o.side) for o in orders] == [("AAA.NS", "sell")]  # paper doesn't hold AAA; DDD isn't B1F's
    assert notes == []  # the sale carries its reason ("our rules no longer hold it")
    assert trial_orders(TUE, held, NSE, plan_for=lambda d, nxt: None)[0] is None



def test_the_trials_plan_needs_a_good_evening_run_on_the_days_data(tmp_path, monkeypatch):
    from trader.execution import sources
    from trader.research import trial
    real = trial.Ledger
    ledger = real(tmp_path / "trial1.db")
    monkeypatch.setattr(trial, "Ledger", lambda: real(tmp_path / "trial1.db"))
    monkeypatch.setattr(trial, "check_definition", lambda: "pinned")
    sessions, secs = [MON, TUE], {"AAA": SimpleNamespace(adj_close=np.array([100.0, 101.0]))}
    monkeypatch.setattr(trial, "inputs", lambda notices: (sessions, secs, None, "e2", "v2"))
    monkeypatch.setattr(trial, "next_open", lambda led, s, secs, e2, v2, nxt, now: {
        "next": nxt, "e2": e2, "entries": [{"sid": "AAA"}], "held": {"ZZZ": "V2"}})
    assert sources.trial_plan(TUE, WED) is None  # no run yet
    ledger.add_run(datetime(2026, 8, 11, 21, 0, tzinfo=IST), "failed", "ValueError: x")
    assert sources.trial_plan(TUE, WED) is None
    ledger.add_run(datetime(2026, 8, 11, 21, 5, tzinfo=IST), "ok", "data to 2026-08-10; signals 0")
    assert sources.trial_plan(TUE, WED) is None  # yesterday's data
    ledger.add_run(datetime(2026, 8, 11, 21, 9, tzinfo=IST), "ok", "data to 2026-08-11; signals 0")
    plan = sources.trial_plan(TUE, WED)
    assert (plan["next"], plan["e2"]) == (WED, "e2")
    assert list(plan["returns"]) == ["AAA.NS"] and plan["returns"]["AAA.NS"].round(6).tolist() == [0.01]  # ZZZ: no data
    sessions.pop()
    assert sources.trial_plan(TUE, WED) is None  # the inputs lag the ledger
    ledger.close()


def test_a_dry_run_reads_prices_from_kite_with_the_days_login(tmp_path, monkeypatch):
    from tests.execution.fake_kite import FakeKite
    kite = FakeKite()
    kite.prices = {"AAA": 101.5}
    logins = []

    def login(settings):
        logins.append(1)
        return KiteOrders("key", "AT", http=kite, sleep=lambda s: None)
    monkeypatch.setattr(live_jobs, "from_session", login)
    clock = Clock()
    clock.at(TUE, 10, 0)
    live = live_jobs.dry_run(load_settings(env={}), PaperStore(tmp_path / "paper.db", 1_000_000), NSE, FakeNotifier(),
                             {TRIAL}, 300_000, clock=clock, directory=tmp_path / "dry")
    api = live.connect()
    assert api.ltp(["AAA"]) == {"AAA": 101.5} and api.ltp(["AAA"]) == {"AAA": 101.5} and logins == [1]
    assert {call[0] for call in kite.calls} == {"GET"} and {call[1] for call in kite.calls} == {"/quote/ohlc"}


def test_the_dry_run_command_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(live_jobs, "ROOT", tmp_path)
    monkeypatch.setattr(live_jobs, "DRY_RUN_DIR", tmp_path / "state" / "live-dryrun")
    monkeypatch.setattr(live_jobs, "configure_logging", lambda **kwargs: None)
    telegram, kinds = FakeNotifier(), []

    def notifier(settings, kind="note"):
        kinds.append(kind)
        return telegram
    monkeypatch.setattr(live_jobs, "notifier_from_settings", notifier)
    monkeypatch.setattr(live_jobs, "trial_orders", lambda today, held, calendar: (None, ["the trial hasn't run"]))
    clock, original = Clock(), live_jobs.dry_run
    clock.at(MON, 21, 30)  # a trading evening, whenever the test runs
    monkeypatch.setattr(live_jobs, "dry_run", lambda *args, **kwargs: original(*args, **kwargs, clock=clock))
    settings = load_settings()
    PaperStore(tmp_path / settings.paper_database, settings.paper_starting_capital).close()
    for wrong in (["status", "--as-live", "B1F"], ["evening", "--notify"], ["check", "--dry-run"]):
        with pytest.raises(SystemExit) as refused:
            live_jobs.main(wrong)
        assert refused.value.code == 2  # argparse's usage error
    with pytest.raises(SystemExit, match="No such strategy to treat as live: ZZZ"):
        live_jobs.main(["status", "--dry-run", "--as-live", "ZZZ"])
    live_jobs.main(["status", "--dry-run", "--as-live", "B1F"])
    assert "Live trading: on for B1F with Rs 300,000" in capsys.readouterr().out  # the simulated account only
    with pytest.raises(SystemExit) as finished:
        live_jobs.main(["evening", "--dry-run", "--as-live", "B1F", "--notify"])
    assert finished.value.code == 0 and "the trial hasn't run" in capsys.readouterr().out
    assert telegram.sent and all("[LIVE DRY RUN" in text for text in telegram.sent)
    assert kinds == ["note"]  # a dry run's messages are notes: only logged (trader/notify/telegram.py)
    assert not (tmp_path / "state" / "live.db").exists()  # the real live records are untouched


# --- failures on the dry-run path ----------------------------------------------------------------------------
AAA = {"part": "E2", "sid": "AAA", "signal_date": "2026-08-07", "tier": "N1", "strength": 0.08, "close": 100.0}


def test_a_trial_that_refuses_to_run_is_a_reported_failure(tmp_path, monkeypatch):
    from trader.research import trial

    def changed():
        raise SystemExit("trial1-definition.md changed after it was pinned (sha256 x); define a new trial instead.")
    monkeypatch.setattr(trial, "check_definition", changed)
    clock, quotes = Clock(), Quotes()
    live = dry(tmp_path, {}, clock, quotes)
    live.sources[TRIAL] = lambda today, held: trial_orders(today, held, NSE)  # the real plan, which checks the pin
    code, messages = job(live, clock, "evening", MON, 21, 30)
    assert code == 1 and "Live evening failed" in messages[0] and "paper trial 1 refused to run" in messages[0]


def test_a_lost_answer_is_looked_up_and_a_restart_carries_on(tmp_path, monkeypatch):
    import requests
    lost = []

    class Lossy(SimKite):
        """Kite records the order, but the answer to the first write never arrives (a timeout after the fact)."""

        def request(self, method, url, data=None, headers=None, timeout=None):
            response = super().request(method, url, data, headers, timeout)
            if not lost:
                lost.append(url)
                raise requests.Timeout("timed out")
            return response
    monkeypatch.setattr(live_jobs, "SimKite", Lossy)
    clock, quotes = Clock(), Quotes()
    plans = {MON: plan([AAA], held=["AAA"]), TUE: plan(held=["AAA"])}
    live = dry(tmp_path, plans, clock, quotes)
    code, messages = job(live, clock, "evening", MON, 21, 30)
    assert code == 0 and "AAA.NS: buy 33 at the open (UNKNOWN)" in messages[0]
    code, messages = job(live, clock, "evening", MON, 21, 45)  # run again: found at Kite by its tag, not sent twice
    assert "AAA.NS: buy 33 at the open (SENT)" in messages[0]
    assert len(SimKite(tmp_path / "dry" / "kite.json", quotes, clock, NSE, 0).state["orders"]) == 1
    monkeypatch.setattr(live_jobs, "SimKite", SimKite)
    restarted = dry(tmp_path, plans, clock, quotes)  # a new process: the account and the records come from disk
    quotes.set("AAA", 100.0, 99.0, 100.5)
    code, messages = job(restarted, clock, "morning", TUE, 9, 20)
    assert "AAA.NS entry: buy 33 at 100.00" in messages[0] and "AAA.NS: stop (SENT)" in messages[0]


def test_an_entry_with_no_trade_at_the_open_is_cancelled_and_leaves_nothing_held(tmp_path):
    clock, quotes = Clock(), Quotes()
    live = dry(tmp_path, {MON: plan([AAA], held=["AAA"])}, clock, quotes)
    job(live, clock, "evening", MON, 21, 30)
    quotes.set("AAA", 0.0, 0.0, 0.0)  # suspended: no trade, so no open
    code, messages = job(live, clock, "morning", TUE, 9, 20)
    assert code == 0 and "AAA.NS entry cancelled: no trade at the open (simulated)" in messages[0]
    assert live.store.positions() == {} and "stop" not in messages[0]


def test_the_kill_switch_stops_b1f_entries_but_never_its_exits(tmp_path):
    clock, quotes = Clock(), Quotes()
    bbb = {**AAA, "sid": "BBB", "signal_date": "2026-08-11"}
    exit_aaa = {"part": "E2", "sid": "AAA", "signal_date": "2026-08-07", "entry_date": "2026-08-11"}
    live = dry(tmp_path, {MON: plan([AAA], held=["AAA"]), TUE: plan([bbb], [exit_aaa], held=["BBB"])}, clock, quotes)
    job(live, clock, "evening", MON, 21, 30)
    quotes.set("AAA", 100.0, 99.0, 100.5)
    job(live, clock, "morning", TUE, 9, 20)
    live.kill_switch.engage("testing the kill switch")
    code, messages = job(live, clock, "evening", TUE, 21, 30)
    assert "BBB.NS: entry not sent: the kill switch is engaged" in messages[0]
    assert "AAA.NS: sell 33 at the open (SENT)" in messages[0]  # the way out is never blocked


def test_the_trials_orders_say_why_in_plain_words():
    v2 = {"part": "V2", "sid": "VVV", "signal_date": "2026-07-31", "tier": "N1", "strength": 2.0, "close": 50.0}
    old = {"part": "V2", "sid": "OLD", "signal_date": "2026-06-30", "entry_date": "2026-07-01"}
    late = {"part": "E2", "sid": "EEE", "signal_date": "2026-06-10", "entry_date": "2026-06-11"}
    held = {"GONE.NS": Position(TRIAL, "GONE.NS", 3, 100.0, 85.0, MON)}
    orders, _ = trial_orders(TUE, held, NSE, plan_for=lambda d, nxt: plan([AAA, v2], exits=[old, late], held=["AAA", "VVV"]))
    assert [o.reason for o in orders] == [
        "after its results, it beat the market by 8% in 2 days (our rule buys these)",
        "one of the steadiest risers of the past year: a top pick this month",
        "a new month: our rule sells and picks again", "its 40 trading days are up (our rule)",
        "our rules no longer hold it"]
