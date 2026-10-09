"""End-of-day paper trading against synthetic daily bars (no network)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_from_returns
from trader.execution.eod import PaperTrader
from trader.execution.report import paper_evidence
from trader.execution.store import PaperStore
from trader.gate import DecayThresholds, Evidence, save_evidence
from trader.markets.calendar import load_calendars
from trader.registry import StrategyRecord, StrategyRegistry
from trader.research.costs import ZERODHA_DELIVERY
from trader.research.simulator import SIGNAL, STOP, TIME, select_trades, simulate
from trader.risk.engine import RiskEngine
from trader.risk.killswitch import KillSwitch
from trader.risk.limits import RiskLimits
from trader.strategies.catalog import StrategySpec
from trader.strategies.swing import PULLBACK, Signals, pullback_rules, pullback_signals

IST = ZoneInfo("Asia/Kolkata")
NSE = load_calendars()["NSE"]
DAYS = NSE.trading_days(date(2026, 8, 3), date(2026, 8, 31))
CLOCK = datetime(2026, 9, 30, 20, 0, tzinfo=IST)
FEE = ZERODHA_DELIVERY.one_side


def scripted(frame: pd.DataFrame) -> Signals:
    """Test strategy: entry/exit flags come with the synthetic bars; 5% stop."""
    return Signals(frame["entry"].to_numpy(bool), frame["exit"].to_numpy(bool), np.full(len(frame), 0.05))


SPEC = StrategySpec("T1", "test", scripted, 5, ZERODHA_DELIVERY, "test exits")


def bars(changes=None, entries=(), exits=()):
    rows = []
    for day in DAYS:
        price = 100.0 if day < date(2026, 8, 11) else 101.0
        row = {"open": price, "high": price, "low": price, "close": price, "volume": 1_000_000}
        row.update((changes or {}).get(day, {}))
        rows.append({**row, "entry": day in entries, "exit": day in exits})
    return pd.DataFrame(rows, index=pd.DatetimeIndex([pd.Timestamp(d) for d in DAYS]).tz_localize(IST))


SIGNAL_DAY = date(2026, 8, 10)
UNIVERSE = {
    "AAA.NS": bars({date(2026, 8, 13): {"open": 100.0, "high": 101.0, "low": 95.0, "close": 96.0}},  # stop hit
                   entries={SIGNAL_DAY}),
    "BBB.NS": bars({date(2026, 8, 17): {"open": 104.0, "high": 104.0, "low": 104.0, "close": 104.0}},
                   entries={SIGNAL_DAY}, exits={date(2026, 8, 14)}),  # exit signal, sold at the next open
    "CCC.NS": bars({date(2026, 8, 17): {"open": 101.0, "high": 102.0, "low": 100.0, "close": 102.0}},
                   entries={SIGNAL_DAY}),  # held 5 days: time exit at the close
}


class FakeProvider:
    name = "fake"

    def __init__(self, frames):
        self.frames = frames

    def history(self, symbol, interval, start, end):
        frame = self.frames[symbol]
        return frame[(frame.index >= start) & (frame.index < end)].copy()


class FakeNotifier:
    def __init__(self, working=True):
        self.sent, self.working = [], working

    def send(self, text):
        if self.working:
            self.sent.append(text)
        return self.working


def make_trader(tmp_path, frames=None, status="PAPER", limits=None, notifier=None, spec=SPEC, db="paper.db"):
    frames = frames or UNIVERSE
    return PaperTrader(store=PaperStore(tmp_path / db, 1_000_000), provider=FakeProvider(frames), calendar=NSE,
                       registry=StrategyRegistry([StrategyRecord("T1", "Test strategy", status)]),
                       risk=RiskEngine(limits or RiskLimits(), KillSwitch(tmp_path / "KILL_SWITCH")),
                       notifier=notifier or FakeNotifier(), catalog={"T1": spec}, universes={"test": list(frames)},
                       sectors={}, evidence_dir=tmp_path / "evidence", clock=lambda: CLOCK)


def test_a_full_paper_trade_cycle(tmp_path):
    trader = make_trader(tmp_path)
    summary = trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    store = trader.store
    assert summary.sessions == NSE.trading_days(SIGNAL_DAY, date(2026, 8, 18))
    orders = store.table("orders")
    assert list(orders["side"]) == ["buy", "buy", "buy", "sell"] and set(orders["status"]) == {"FILLED"}
    assert (orders.loc[orders["side"] == "buy", "quantity"] == 1000).all()  # Rs 5,000 risk / (Rs 100 x 5%)
    trades = store.trades().set_index("symbol")
    assert trades.loc["AAA.NS", "reason"] == "Stop Loss" and trades.loc["AAA.NS", "exit_price"] == pytest.approx(95.95)
    assert trades.loc["BBB.NS", "reason"] == "Strategy Exit" and trades.loc["BBB.NS", "exit_session"] == "2026-08-17"
    assert trades.loc["BBB.NS", "exit_price"] == 104.0
    assert trades.loc["CCC.NS", "reason"] == "Time Exit" and trades.loc["CCC.NS", "exit_price"] == 102.0
    assert (trades["entry_price"] == 101.0).all() and (trades["entry_session"] == "2026-08-11").all()
    buy_fee = FEE(101_000, "buy")
    assert trades.loc["AAA.NS", "net_pnl"] == pytest.approx(95_950 - 101_000 - buy_fee - FEE(95_950, "sell"))
    assert trades.loc["AAA.NS", "r_multiple"] == pytest.approx(trades.loc["AAA.NS", "net_pnl"] / (101_000 * 0.05))
    expected_cash = (1_000_000 - 3 * (101_000 + buy_fee) + sum(v - FEE(v, "sell") for v in (95_950, 104_000, 102_000)))
    assert store.cash == pytest.approx(expected_cash) and store.positions() == {} and store.reconcile() == []
    sent = trader.notifier.sent
    titles = [text.split("\n")[0] for text in sent]
    assert titles.count("<b>[PAPER] BUY SIGNAL</b>") == 3 and titles.count("<b>[PAPER] BUY EXECUTED</b>") == 3
    assert titles.count("<b>[PAPER] SELL EXECUTED</b>") == 3 and titles[-1].startswith("<b>[PAPER] DAILY SUMMARY 2026-08-18")
    assert summary.messages_sent == len(sent) == 10


def test_rerunning_a_processed_session_changes_nothing(tmp_path):
    trader = make_trader(tmp_path)
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    before = {name: trader.store.table(name) for name in ("orders", "fills", "trades", "sessions")}
    summary = trader.run(until=date(2026, 8, 18))
    assert summary.sessions == [] and "already processed" in summary.notes[0]
    for name, table in before.items():
        pd.testing.assert_frame_equal(trader.store.table(name), table)


def test_catching_up_over_several_runs_matches_one_run(tmp_path):
    single = make_trader(tmp_path, db="single.db")
    single.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    split = make_trader(tmp_path, db="split.db")
    split.run(until=date(2026, 8, 12), start=SIGNAL_DAY)  # positions opened on 11 Aug...
    split.run(until=date(2026, 8, 18))  # ...are managed when the next run catches up
    pd.testing.assert_frame_equal(split.store.trades().drop(columns="id"), single.store.trades().drop(columns="id"))
    assert split.store.cash == pytest.approx(single.store.cash)


def test_a_crash_mid_session_rolls_back_and_the_rerun_completes(tmp_path, monkeypatch):
    clean = make_trader(tmp_path, db="clean.db")
    clean.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    trader = make_trader(tmp_path, db="crash.db")
    original = trader.store.record_session

    def crash_on_13th(session, equity, cash):
        if session == date(2026, 8, 13):
            raise RuntimeError("power cut")
        original(session, equity, cash)

    monkeypatch.setattr(trader.store, "record_session", crash_on_13th)
    with pytest.raises(RuntimeError):
        trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    assert trader.store.last_session() == date(2026, 8, 12)
    assert "AAA.NS" in trader.store.positions() and trader.store.trades().empty  # the 13th's stop-out never happened
    monkeypatch.setattr(trader.store, "record_session", original)
    trader.run(until=date(2026, 8, 18))
    pd.testing.assert_frame_equal(trader.store.trades().drop(columns="id"), clean.store.trades().drop(columns="id"))
    assert trader.store.reconcile() == []


def test_the_kill_switch_blocks_entries(tmp_path):
    trader = make_trader(tmp_path)
    trader.risk.kill_switch.engage("test")
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    decisions = trader.store.table("decisions")
    assert trader.store.table("orders").empty and (decisions["action"] == "NO_TRADE").all()
    assert decisions["detail"].str.contains("kill switch").all()


def test_the_kill_switch_never_traps_open_positions(tmp_path):
    trader = make_trader(tmp_path)
    trader.run(until=date(2026, 8, 12), start=SIGNAL_DAY)
    trader.risk.kill_switch.engage("test")
    trader.run(until=date(2026, 8, 18))
    assert len(trader.store.trades()) == 3 and trader.store.positions() == {}  # stops, exits, time exits still run


def test_a_gap_through_the_stop_fills_at_the_open(tmp_path):
    gap = {date(2026, 8, 13): {"open": 90.0, "high": 92.0, "low": 89.0, "close": 91.0}}
    trader = make_trader(tmp_path, frames={"AAA.NS": bars(gap, entries={SIGNAL_DAY})})
    trader.run(until=date(2026, 8, 13), start=SIGNAL_DAY)
    trade = trader.store.trades().iloc[0]
    assert trade["reason"] == "Stop Loss (gapped through)" and trade["exit_price"] == 90.0
    assert trade["r_multiple"] < -1  # a gap costs more than the planned 1R


def test_the_daily_loss_brake_blocks_new_entries(tmp_path):
    slump = {date(2026, 8, 12): {"open": 101.0, "high": 101.0, "low": 98.0, "close": 98.0}}  # above the stop
    frames = {"AAA.NS": bars(slump, entries={SIGNAL_DAY}), "DDD.NS": bars(entries={date(2026, 8, 12)})}
    trader = make_trader(tmp_path, frames=frames, limits=RiskLimits(max_daily_loss=0.002))
    trader.run(until=date(2026, 8, 12), start=SIGNAL_DAY)
    decision = trader.store.table("decisions").iloc[-1]
    assert decision["symbol"] == "DDD.NS" and decision["action"] == "NO_TRADE" and "today -0.3%" in decision["detail"]
    assert any("RISK ALERT: Daily loss limit" in text for text in trader.notifier.sent)
    assert list(trader.store.positions()) == ["AAA.NS"]


def test_a_missing_bar_alerts_and_the_position_waits(tmp_path):
    frame = bars(entries={SIGNAL_DAY}, exits={date(2026, 8, 12)}).drop(pd.Timestamp("2026-08-13", tz=IST))
    trader = make_trader(tmp_path, frames={"AAA.NS": frame})
    trader.run(until=date(2026, 8, 14), start=SIGNAL_DAY)
    assert any("Stale data" in text and "AAA.NS" in text for text in trader.notifier.sent)
    trade = trader.store.trades().iloc[0]
    assert trade["exit_session"] == "2026-08-14" and trade["reason"] == "Strategy Exit"  # sold at the next bar


def test_a_strategy_suspended_mid_run_opens_nothing_more(tmp_path):
    trader = make_trader(tmp_path, frames={**UNIVERSE, "EEE.NS": bars(entries={date(2026, 8, 14)})})
    trader.decay = DecayThresholds(max_drawdown_r=1)  # AAA's stop-out on 13 Aug (-1.1R) breaches it
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    assert "T1" in trader.store.suspended() and "EEE.NS" not in set(trader.store.table("orders")["symbol"])
    assert any("RISK ALERT: Strategy suspended" in text for text in trader.notifier.sent)
    assert len(trader.store.trades()) == 3  # what it already holds is still managed to the exit
    assert "Strategies trading: 0" in trader.notifier.sent[-1]


def test_no_volume_means_no_trade(tmp_path):
    frame = bars(entries={SIGNAL_DAY})
    frame["volume"] = np.nan
    trader = make_trader(tmp_path, frames={"AAA.NS": frame})
    trader.run(until=SIGNAL_DAY, start=SIGNAL_DAY)
    assert trader.store.table("orders").empty and "no volume" in trader.store.table("decisions")["detail"].iloc[0]


def test_bars_research_drops_are_dropped_here_too(tmp_path):
    holiday = pd.DataFrame({"open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "volume": 0, "entry": False,
                            "exit": False}, index=pd.DatetimeIndex([pd.Timestamp("2026-08-15", tz=IST)]))
    frame = pd.concat([bars(), holiday]).sort_index()  # a flat zero-volume placeholder on a holiday...
    frame.loc[pd.Timestamp("2026-08-20", tz=IST), ["open", "high", "low", "close"]] = np.nan  # ...and a bar without prices
    trader = make_trader(tmp_path, frames={"AAA.NS": frame})
    for_exits, for_entries, problems = trader.load_bars(["AAA.NS"], SIGNAL_DAY, CLOCK)
    assert list(for_exits["AAA.NS"].index.date) == [d for d in DAYS if d != date(2026, 8, 20)]
    assert "AAA.NS" in for_entries and not problems  # the stock stays tradable


def test_nothing_trades_without_a_paper_status(tmp_path):
    trader = make_trader(tmp_path, status="RESEARCH")
    summary = trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    assert trader.store.table("orders").empty and len(summary.sessions) == 7
    assert "no strategy is approved for paper trading" in summary.notes[0]
    assert "NO TRADE" in trader.notifier.sent[-1]


def test_unsent_messages_are_retried_on_the_next_run(tmp_path):
    trader = make_trader(tmp_path, notifier=FakeNotifier(working=False))
    assert trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY).messages_sent == 0
    assert len(trader.store.unsent_messages()) == 10
    trader.notifier.working = True
    assert trader.run(until=date(2026, 8, 18)).messages_sent == 10 and trader.store.unsent_messages() == []


def test_paper_results_match_the_backtester_exactly(tmp_path):
    rng = np.random.default_rng(12)
    warmup = list(pd.bdate_range("2024-06-03", "2025-12-31").date)
    days = warmup + NSE.trading_days(date(2026, 1, 1), date(2026, 9, 30))
    frame = daily_from_returns(rng.normal(0.0007, 0.015, len(days)))
    frame.index = pd.DatetimeIndex([pd.Timestamp(d) for d in days]).tz_localize(IST)
    frame["volume"] = 1_000_000
    start = date(2026, 2, 2)

    def from_start(bars_):
        s = pullback_signals(bars_)
        return Signals(s.entry & (np.asarray(bars_.index.date) >= start), s.exit, s.stop)

    spec = StrategySpec("T1", "test", from_start, PULLBACK.max_hold_days, ZERODHA_DELIVERY, "pullback exits")
    lenient = RiskLimits(risk_per_trade=0.02, max_position=1.0, max_stop_distance=0.5, min_notional=1,
                         max_sector_exposure=1.0, max_daily_loss=0.9, max_drawdown=0.9)
    trader = make_trader(tmp_path, frames={"PPP.NS": frame}, limits=lenient, spec=spec)
    trader.run(until=date(2026, 9, 30), start=start)
    cutoff = date(2026, 9, 15)  # leave out trades the end of the data cut short
    paper = trader.store.trades()
    paper = [(r.entry_session, r.exit_session, r.reason.split(" (")[0], round(r.exit_price / r.entry_price - 1, 10))
             for r in paper.itertuples() if r.exit_session <= cutoff.isoformat()]

    signals = from_start(frame)
    out = simulate(frame, "long", pullback_rules(), "next_open", stop=signals.stop, exit_signal=signals.exit)
    names = {STOP: "Stop Loss", SIGNAL: "Strategy Exit", TIME: "Time Exit"}
    backtest = [(frame.index[i + 1].date().isoformat(), frame.index[out.exit_idx[i]].date().isoformat(),
                 names[out.reason[i]], round(out.gross[i], 10)) for i in select_trades(signals.entry, out)
                if frame.index[out.exit_idx[i]].date() <= cutoff]
    assert len(backtest) >= 3 and paper == backtest


def test_paper_evidence_needs_time_and_trades(tmp_path):
    trader = make_trader(tmp_path)
    trader.run(until=date(2026, 8, 18), start=SIGNAL_DAY)
    save_evidence(Evidence("T1", "research", "PAPER", "2026-08-01", "test",
                           stats={"holdout_mean_net": 0.003, "holdout_sd_net": 0.02, "holdout_trades": 400,
                                  "holdout_win_rate": 0.6}), tmp_path / "evidence")
    evidence = paper_evidence(trader.store, "T1", date(2026, 8, 20), evidence_dir=tmp_path / "evidence")
    assert evidence.kind == "paper" and evidence.stats["trades"] == 3
    assert evidence.decision in ("PAPER", "RESEARCH")  # three trades in a week can't earn LIVE_SMALL
    assert paper_evidence(trader.store, "T1", date(2026, 8, 20), evidence_dir=tmp_path / "none") is None
