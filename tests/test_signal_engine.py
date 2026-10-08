"""The live scanner, with market data replaced by synthetic bars (no network)."""
from signal_engine import SignalDetector, format_signal_message
from tests.helpers import synthetic_intraday
from trader.registry import StrategyRecord, StrategyRegistry
from trader.research.legacy_rules import NAME, chain_choice, legacy_features, legacy_masks


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


def detector_with(frames, registry):
    detector = SignalDetector(registry)
    detector.tracker.tickers = list(frames)
    detector.tracker.fetch_latest_data = lambda interval, period: {t: f.copy() for t, f in frames.items()}
    return detector


def test_no_signal_leaves_the_scanner_while_no_strategy_is_approved():
    picked = frames_ending_on_a_signal()
    detector = detector_with({t: bars for t, (bars, _) in picked.items()}, StrategyRegistry.load())
    assert detector.scan_market() == []
    assert [r.signal["strategy"] for r in detector.last_rejected] == [name for _, name in picked.values()]
    assert all(r.status in ("REJECTED", "DISABLED") for r in detector.last_rejected)
    assert detector.last_skipped == []


def test_an_approved_strategy_passes_through():
    picked = frames_ending_on_a_signal()
    approved_name = next(iter(picked.values()))[1]
    registry = StrategyRegistry([StrategyRecord(rid, name, "LIVE_SMALL" if name == approved_name else "DISABLED")
                                 for rid, name in NAME.items()])
    detector = detector_with({t: bars for t, (bars, _) in picked.items()}, registry)
    signals = detector.scan_market()
    assert signals and {s["strategy"] for s in signals} == {approved_name}


def test_five_sessions_of_bars_are_enough_history():
    # The old `len < 200` check ran after the 199 warm-up rows were dropped, so 5 days never passed.
    detector = detector_with({"T": synthetic_intraday(sessions=5, seed=3)}, StrategyRegistry.load())
    detector.scan_market()
    assert detector.last_skipped == []


def test_short_history_and_broken_data_are_skipped_without_stopping_the_scan():
    good = synthetic_intraday(sessions=5, seed=3)
    frames = {"SHORT": good.iloc[:150], "BROKEN": good.drop(columns=["volume"]), "GOOD": good}
    detector = detector_with(frames, StrategyRegistry.load())
    detector.tracker.tickers.append("MISSING")
    detector.scan_market()
    reasons = dict(detector.last_skipped)
    assert "insufficient history" in reasons["SHORT"]
    assert "error" in reasons["BROKEN"]
    assert reasons["MISSING"] == "no data returned"
    assert "GOOD" not in reasons


def test_alert_message_without_ai_has_no_ai_section():
    signal = {"signal": "BUY", "ticker": "X.NS", "strategy": "S", "price": 100.0, "stop_loss": 99.0,
              "target": 102.0, "rsi": 50.0}
    assert "AI Analysis" not in format_signal_message(signal)
    assert "AI Analysis (Low Confidence)" in format_signal_message(signal, {"confidence": "Low", "explanation": "e"})
