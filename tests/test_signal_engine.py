"""The live scanner, with market data from a fake provider (no network)."""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from signal_engine import (SignalDetector, format_signal_message, is_market_open, market_state,
                           warn_if_calendar_ends_soon)
from tests.helpers import synthetic_intraday
from trader.markets.calendar import load_calendars
from trader.registry import StrategyRecord, StrategyRegistry
from trader.research.legacy_rules import NAME, chain_choice, legacy_features, legacy_masks

IST = ZoneInfo("Asia/Kolkata")
NSE = load_calendars()["NSE"]
AFTER_SYNTHETIC_DATA = datetime(2026, 8, 18, 15, 45, tzinfo=IST)  # 12 synthetic sessions: 3-18 Aug 2026
LENIENT = timedelta(days=30)  # truncated test frames end on different bars, so relax the freshness limit


class FakeProvider:
    name = "fake"

    def __init__(self, frames):
        self.frames = frames

    def history(self, symbol, interval, start, end):
        if symbol not in self.frames:
            raise LookupError("unknown symbol")
        return self.frames[symbol].copy()


def frames_ending_on_a_signal(count=5):
    """Truncations of one synthetic series whose last bar fires a legacy rule: {ticker: (bars, rule name)}."""
    bars = synthetic_intraday(sessions=12, seed=42)
    masks = legacy_masks(legacy_features(bars))
    offset = len(bars) - len(masks["R1"])
    picked = {}
    for i in range(30, len(masks["R1"])):
        rule = chain_choice(masks, i)
        if rule:
            picked[f"T{len(picked)}"] = (bars.iloc[:offset + i + 1], NAME[rule])
        if len(picked) == count:
            break
    return picked


def detector_with(frames, registry, max_delay=LENIENT, extra_symbols=()):
    detector = SignalDetector(registry, provider=FakeProvider(frames), calendar=NSE, max_delay=max_delay)
    detector.symbols = list(frames) + list(extra_symbols)
    return detector


def test_no_signal_leaves_the_scanner_while_no_strategy_is_approved():
    picked = frames_ending_on_a_signal()
    detector = detector_with({t: bars for t, (bars, _) in picked.items()}, StrategyRegistry.load())
    assert detector.scan_market(now=AFTER_SYNTHETIC_DATA) == []
    assert [r.signal["strategy"] for r in detector.last_rejected] == [name for _, name in picked.values()]
    assert all(r.status in ("REJECTED", "DISABLED") for r in detector.last_rejected)
    assert detector.last_skipped == []


def test_an_approved_strategy_passes_through():
    picked = frames_ending_on_a_signal()
    approved_name = next(iter(picked.values()))[1]
    registry = StrategyRegistry([StrategyRecord(rid, name, "LIVE_SMALL" if name == approved_name else "DISABLED")
                                 for rid, name in NAME.items()])
    detector = detector_with({t: bars for t, (bars, _) in picked.items()}, registry)
    signals = detector.scan_market(now=AFTER_SYNTHETIC_DATA)
    assert signals and {s["strategy"] for s in signals} == {approved_name}


def test_five_sessions_of_fresh_bars_are_evaluated():
    # The old `len < 200` check ran after the 199 warm-up rows were dropped, so 5 days never passed.
    detector = detector_with({"T": synthetic_intraday(sessions=5, seed=3)}, StrategyRegistry.load(),
                             max_delay=timedelta(minutes=20))
    detector.scan_market(now=datetime(2026, 8, 7, 15, 45, tzinfo=IST))
    assert detector.last_skipped == []


def test_stale_data_is_not_evaluated():
    detector = detector_with({"T": synthetic_intraday(sessions=5, seed=3)}, StrategyRegistry.load(),
                             max_delay=timedelta(minutes=20))
    detector.scan_market(now=datetime(2026, 8, 10, 11, 0, tzinfo=IST))  # Monday morning; data ends Friday
    assert "stale" in dict(detector.last_skipped)["T"]


def test_bad_data_is_skipped_without_stopping_the_scan():
    good = synthetic_intraday(sessions=5, seed=3)
    frames = {"SHORT": good.iloc[:150], "BROKEN": good.drop(columns=["volume"]), "GOOD": good}
    detector = detector_with(frames, StrategyRegistry.load(), extra_symbols=["MISSING"])
    detector.scan_market(now=datetime(2026, 8, 7, 15, 45, tzinfo=IST))
    reasons = dict(detector.last_skipped)
    assert "insufficient history" in reasons["SHORT"]
    assert "missing columns: volume" in reasons["BROKEN"]
    assert reasons["MISSING"].startswith("no data")
    assert "GOOD" not in reasons


def test_holidays_and_unconfigured_years():
    assert not is_market_open(datetime(2026, 10, 2, 11, 0, tzinfo=IST), NSE)  # Gandhi Jayanti
    assert is_market_open(datetime(2026, 10, 9, 11, 0, tzinfo=IST), NSE)
    assert market_state(NSE, datetime(2027, 1, 4, 11, 0, tzinfo=IST))[0] == "unknown"


def test_december_warning_when_next_years_holidays_are_missing(caplog):
    with caplog.at_level(logging.WARNING):
        warn_if_calendar_ends_soon(NSE, date(2026, 12, 1))
    assert "2027" in caplog.text


def test_alert_message_without_ai_has_no_ai_section():
    signal = {"signal": "BUY", "ticker": "X.NS", "strategy": "S", "price": 100.0, "stop_loss": 99.0,
              "target": 102.0, "rsi": 50.0}
    assert "AI Analysis" not in format_signal_message(signal)
    assert "AI Analysis (Low Confidence)" in format_signal_message(signal, {"confidence": "Low", "explanation": "e"})
