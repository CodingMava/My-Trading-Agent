import numpy as np
import pandas as pd
import pytest

from trader.research.metrics import summarize
from trader.research.simulator import STOP, TARGET, TIME, TRADE_COLUMNS


def make_trades(gross, risk=0.01, exit_times=None, reasons=None):
    n = len(gross)
    times = pd.date_range("2026-01-05 10:00", periods=n, freq="D", tz="Asia/Kolkata")
    exit_times = pd.DatetimeIndex(exit_times) if exit_times is not None else times
    return pd.DataFrame({
        "ticker": "AAA", "rule": "X", "side": "long", "signal_time": times, "exit_time": exit_times,
        "signal_date": np.asarray(times.date), "exit_date": np.asarray(exit_times.date), "tod": "10:00",
        "gross": gross, "reason": reasons or [TIME] * n, "hold_bars": 1, "risk": risk,
    })


def test_summary_matches_a_hand_calculation():
    trades = make_trades([0.02, -0.01, 0.005, -0.01], reasons=[TARGET, STOP, TIME, STOP])
    stats = summarize(trades, cost=0.001, session_dates=list(trades["signal_date"]))
    # net = +0.019, -0.011, +0.004, -0.011 -> in R (1% stop): +1.9, -1.1, +0.4, -1.1
    assert stats["trades"] == 4 and stats["win_pct"] == 50
    assert stats["profit_factor"] == pytest.approx(0.023 / 0.022)
    assert stats["exp_net_pct"] == pytest.approx(0.025)
    assert stats["exp_gross_pct"] == pytest.approx(0.125)
    assert stats["unit"] == "R" and stats["exp_units"] == pytest.approx(0.025)
    assert stats["max_dd_units"] == pytest.approx(-1.8)  # equity path 1.9, 0.8, 1.2, 0.1
    assert stats["total_units"] == pytest.approx(0.1)
    assert (stats["target_pct"], stats["stop_pct"], stats["time_pct"]) == (25, 50, 25)


def test_simultaneous_exits_are_netted_before_the_drawdown():
    same_time = ["2026-01-05 15:15+05:30"] * 2
    for gross in ([0.01, -0.01], [-0.01, 0.01]):
        stats = summarize(make_trades(gross, exit_times=same_time), cost=0.0, session_dates=[])
        assert stats["max_dd_units"] == 0 and stats["total_units"] == 0


def test_without_stops_path_statistics_fall_back_to_percent():
    stats = summarize(make_trades([0.02, -0.01], risk=np.nan), cost=0.0, session_dates=[])
    assert stats["unit"] == "%" and stats["total_units"] == pytest.approx(1.0)


def test_no_trades():
    assert summarize(pd.DataFrame(columns=TRADE_COLUMNS), 0.001, []) == {"trades": 0}
