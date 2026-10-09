import numpy as np
import pandas as pd
import pytest

from tests.helpers import make_bars
from trader.research.simulator import (SIGNAL, STOP, TARGET, TIME, TRADE_COLUMNS, ExitRules, run_backtest,
                                       select_chain, select_trades, session_ids, simulate, trade_rows)

INTRADAY = ExitRules(stop=0.01, target=0.02, square_off_each_session=True)
FLAT = [100.0, 100.0, 100.0, 100.0]


def first_trade(bars, side="long", rules=INTRADAY, entry="signal_close", **levels):
    out = simulate(bars, side, rules, entry, **levels)
    return out.gross[0], out.reason[0], out.exit_idx[0]


def daily(opens, highs, lows, closes):
    return make_bars(opens, highs, lows, closes, start="2026-01-05", freq="B")


# --- the seven exit checks from the audit harness ---

def test_flat_session_is_squared_off_at_zero():
    assert first_trade(make_bars(FLAT, FLAT, FLAT, FLAT)) == (0.0, TIME, 3)


def test_long_reaches_target():
    gross, reason, _ = first_trade(make_bars(FLAT, [100, 102.5, 100, 100], [100, 99.5, 100, 100], FLAT))
    assert gross == pytest.approx(0.02) and reason == TARGET


def test_stop_is_assumed_first_when_both_are_touched_in_one_bar():
    gross, reason, _ = first_trade(make_bars(FLAT, [100, 102.5, 100, 100], [100, 98.9, 100, 100], FLAT))
    assert gross == pytest.approx(-0.01) and reason == STOP


def test_gap_through_the_stop_fills_at_the_open():
    opens = [100, 97, 97, 97]
    gross, reason, _ = first_trade(make_bars(opens, [100, 97.5, 97, 97], [100, 96.5, 97, 97], opens))
    assert gross == pytest.approx(-0.03) and reason == STOP


def test_short_stop_and_target_mirror_the_long_side():
    gross, reason, _ = first_trade(make_bars(FLAT, [100, 102.5, 100, 100], [100, 99.5, 100, 100], FLAT), side="short")
    assert gross == pytest.approx(-0.01) and reason == STOP
    gross, reason, _ = first_trade(make_bars(FLAT, [100, 100.5, 100, 100], [100, 97.9, 100, 100], FLAT), side="short")
    assert gross == pytest.approx(0.02) and reason == TARGET


def test_next_open_entry_fills_at_the_next_bars_open():
    opens = [100, 101, 101, 101]
    gross, reason, _ = first_trade(make_bars(opens, [100, 101, 103.1, 101], [100, 101, 101, 101], opens),
                                   entry="next_open")
    assert gross == pytest.approx(0.02) and reason == TARGET  # target 101 * 1.02 = 103.02


def test_bar_opening_beyond_the_target_fills_at_that_open():
    gross, reason, _ = first_trade(make_bars([100, 103, 100, 100], [100, 103.5, 100, 100],
                                             [100, 98.0, 100, 100], [100, 99, 100, 100]))
    assert gross == pytest.approx(0.03) and reason == TARGET


# --- intraday session rules ---

def test_no_intraday_position_is_opened_on_the_square_off_bar():
    index = pd.DatetimeIndex(["2026-01-05 15:05", "2026-01-05 15:10", "2026-01-05 15:15",
                              "2026-01-06 09:15", "2026-01-06 09:20"]).tz_localize("Asia/Kolkata")
    p = [100.0] * 5
    bars = pd.DataFrame({"open": p, "high": p, "low": p, "close": p}, index=index)
    at_close = simulate(bars, "long", INTRADAY, "signal_close")
    at_open = simulate(bars, "long", INTRADAY, "next_open")
    assert at_close.exit_idx[0] == 2  # squared off on the same session's last bar
    assert not np.isnan(at_close.gross[1]) and np.isnan(at_close.gross[2])
    assert not np.isnan(at_open.gross[0]) and np.isnan(at_open.gross[1])


def test_session_ids_follow_the_local_calendar_date():
    index = pd.DatetimeIndex(["2026-01-05 09:15", "2026-01-05 15:15", "2026-01-06 09:15"]).tz_localize("Asia/Kolkata")
    assert list(session_ids(index)) == [0, 0, 1]


# --- swing (multi-day) rules ---

SWING = ExitRules(stop=0.05, target=0.10, max_hold_bars=3)


def test_swing_trade_exits_on_time_after_max_hold_bars():
    out = simulate(daily([100.0] * 6, [104.0] * 6, [96.0] * 6, [100, 100, 101, 102, 103, 104]), "long", SWING)
    assert out.reason[0] == TIME and out.exit_idx[0] == 3 and out.gross[0] == pytest.approx(0.02)


def test_swing_overnight_gap_through_the_stop_fills_at_the_open():
    opens = [100, 100, 100, 90, 90]
    out = simulate(daily(opens, [100, 101, 100, 91, 90], [100, 99, 99, 89, 90], [100, 100, 100, 90, 90]), "long", SWING)
    assert out.reason[0] == STOP and out.exit_idx[0] == 3 and out.gross[0] == pytest.approx(-0.10)


def test_per_bar_levels_override_the_rules():
    stops = np.array([0.02, np.nan, np.nan, np.nan])
    targets = np.array([0.04, np.nan, np.nan, np.nan])
    out = simulate(daily(FLAT, [100, 103, 104.5, 100], [100, 98.5, 99, 100], FLAT), "long",
                   ExitRules(max_hold_bars=5), stop=stops, target=targets)
    assert out.reason[0] == TARGET and out.gross[0] == pytest.approx(0.04) and out.risk[0] == 0.02
    assert out.reason[1] == TIME and np.isnan(out.risk[1])


def test_open_trade_is_closed_at_the_last_close_of_the_data():
    out = simulate(daily([100.0] * 3, [100, 100, 105], [100, 100, 100], [100, 100, 105]), "long",
                   ExitRules(stop=0.5, target=0.5))
    assert out.reason[0] == TIME and out.exit_idx[0] == 2 and out.gross[0] == pytest.approx(0.05)


def test_max_hold_sessions_counts_sessions_not_bars():
    stamps = [f"2026-01-0{d} {t}" for d in (5, 6, 7) for t in ("09:15", "12:00", "15:15")]
    p = [100.0] * 9
    bars = pd.DataFrame({"open": p, "high": p, "low": p, "close": p},
                        index=pd.DatetimeIndex(stamps).tz_localize("Asia/Kolkata"))
    out = simulate(bars, "long", ExitRules(stop=0.5, target=0.5, max_hold_sessions=2))
    assert out.exit_idx[0] == 5  # entered in session 0, closed at the end of session 1


# --- trade selection ---

def test_one_open_position_at_a_time():
    out = simulate(daily([100.0] * 6, [100.0] * 6, [100.0] * 6, [100.0] * 6), "long", ExitRules(max_hold_bars=2))
    signal = np.array([True, True, True, True, False, False])
    assert list(select_trades(signal, out)) == [0, 3]


def test_chain_takes_the_first_true_rule_and_respects_open_positions():
    out = simulate(daily([100.0] * 6, [100.0] * 6, [100.0] * 6, [100.0] * 6), "long", ExitRules(max_hold_bars=1))
    first = np.array([False, False, False, True, False, False])
    second = np.array([True, True, False, True, False, False])
    assert select_chain([first, second], [out, out]) == [(0, 1), (3, 0)]


def test_trade_rows_and_run_backtest():
    bars = daily([100.0] * 5, [100, 102, 103, 100, 100], [100, 99, 99, 100, 100], [100.0] * 5)
    rules = ExitRules(stop=0.02, target=0.03, max_hold_bars=3)
    out = simulate(bars, "long", rules)
    rows = trade_rows("AAA", bars.index, np.array([0]), out, "long", "demo")
    assert list(rows.columns) == TRADE_COLUMNS
    assert rows.loc[0, "reason"] == TARGET and rows.loc[0, "hold_bars"] == 2 and rows.loc[0, "risk"] == 0.02
    trades = run_backtest({"AAA": bars, "BBB": bars}, {"AAA": np.array([True, False, False, False, False])},
                          "long", rules, rule="demo")
    assert list(trades["ticker"]) == ["AAA"] and trades.loc[0, "gross"] == pytest.approx(0.03)


# --- rule-based exits (an exit signal on a close sells at the next open) ---

EXIT_AFTER_DAY_2 = np.array([False, False, True, False, False])


def test_exit_signal_sells_at_the_next_open():
    bars = daily([100, 100, 101, 104, 104], [100, 101, 102, 105, 104], [100, 99.5, 100.5, 103, 104],
                 [100, 100.5, 102, 104, 104])
    out = simulate(bars, "long", ExitRules(stop=0.05, max_hold_bars=4), exit_signal=EXIT_AFTER_DAY_2)
    assert out.reason[0] == SIGNAL and out.exit_idx[0] == 3 and out.gross[0] == pytest.approx(0.04)


def test_a_stop_hit_before_the_exit_signal_wins():
    bars = daily([100.0] * 5, [100.0] * 5, [100, 99, 94, 100, 100], [100.0] * 5)
    out = simulate(bars, "long", ExitRules(stop=0.05, max_hold_bars=4), exit_signal=EXIT_AFTER_DAY_2)
    assert out.reason[0] == STOP and out.exit_idx[0] == 2 and out.gross[0] == pytest.approx(-0.05)


def test_the_exit_open_comes_before_a_stop_touched_later_that_day():
    bars = daily([100, 100, 100, 101, 100], [100, 100, 100, 101, 100], [100, 99, 99, 90, 100], [100.0] * 5)
    out = simulate(bars, "long", ExitRules(stop=0.05, max_hold_bars=4), exit_signal=EXIT_AFTER_DAY_2)
    assert out.reason[0] == SIGNAL and out.gross[0] == pytest.approx(0.01)


def test_an_exit_signal_on_the_last_allowed_day_leaves_the_time_exit():
    bars = daily([100.0] * 5, [102.0] * 5, [100.0] * 5, [100, 100, 102, 102, 102])
    out = simulate(bars, "long", ExitRules(max_hold_bars=2), exit_signal=EXIT_AFTER_DAY_2)
    assert out.reason[0] == TIME and out.exit_idx[0] == 2 and out.gross[0] == pytest.approx(0.02)


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        simulate(daily(FLAT, FLAT, FLAT, FLAT), "long", SWING, exit_signal=np.array([True]))
    bars = daily(FLAT, FLAT, FLAT, FLAT)
    with pytest.raises(ValueError):
        ExitRules(stop=0)
    with pytest.raises(ValueError):
        ExitRules(max_hold_bars=0)
    with pytest.raises(ValueError):
        simulate(bars, "sideways", SWING)
    with pytest.raises(ValueError):
        simulate(bars, "long", SWING, entry="tomorrow")
    with pytest.raises(ValueError):
        simulate(bars, "long", SWING, stop=np.array([0.01, 0.02]))
