import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_from_returns
from trader.strategies.swing import (MomentumParams, momentum_panel, momentum_trades, month_ends, pullback_signals,
                                     select_top)


def test_pullback_fires_on_a_sharp_dip_in_an_uptrend_and_exits_on_the_rebound():
    returns = np.r_[np.full(260, 0.004), [-0.03, -0.03], [0.02, 0.02]]  # steady rise, two-day drop, rebound
    signals = pullback_signals(daily_from_returns(returns))
    assert not signals.entry[:261].any()
    assert signals.entry[261]  # close still above the 200-day SMA, 2-day RSI near zero
    assert signals.exit[263] and not signals.exit[261]
    assert 0 < signals.stop[261] < 0.1


def test_pullback_signals_never_use_future_bars():
    bars = daily_from_returns(np.random.default_rng(4).normal(0.0006, 0.018, 700))
    full = pullback_signals(bars)
    for cut in (300, 450, 699):
        part = pullback_signals(bars.iloc[:cut])
        assert np.array_equal(part.entry, full.entry[:cut]) and np.array_equal(part.exit, full.exit[:cut])
        assert np.allclose(part.stop, full.stop[:cut], equal_nan=True)


def momentum_universe(days=420):
    rng = np.random.default_rng(1)
    drifts = {"A.NS": 0.003, "B.NS": 0.001, "C.NS": 0.0, "D.NS": -0.001, "E.NS": -0.002, "F.NS": 0.0005}
    # Low noise, so each stock's 12-1 month return reliably ranks by its drift.
    return {s: daily_from_returns(rng.normal(d, 0.001, days), seed=i) for i, (s, d) in enumerate(drifts.items())}


SMALL = MomentumParams(lookback=252, skip=21, top_n=2, min_history=273)


def test_momentum_picks_the_strongest_past_performers_and_holds_one_month():
    frames = momentum_universe()
    panel = momentum_panel(frames, SMALL)
    panel["selected"] = select_top(panel, SMALL)
    assert set(panel.loc[panel["selected"], "symbol"]) == {"A.NS", "B.NS"}
    row = panel[panel["selected"]].iloc[0]
    bars = frames[row["symbol"]]
    ends = month_ends(bars.index)
    assert row["entry_time"] == bars.index[bars.index.get_loc(row["month_end"]) + 1]  # next day's open
    next_end = ends[ends.index(row["month_end"]) + 1]
    assert row["exit_time"] == bars.index[bars.index.searchsorted(next_end, side="right")]
    assert row["gross"] == pytest.approx(bars.loc[row["exit_time"], "open"] / bars.loc[row["entry_time"], "open"] - 1)
    trades = momentum_trades(panel, panel["selected"].to_numpy())
    assert len(trades) == 2 * panel["month_end"].nunique() and trades["risk"].isna().all()


def test_momentum_scores_ignore_future_prices():
    frames = momentum_universe()
    cutoff = frames["A.NS"].index[350]
    shocked = {s: f.copy() for s, f in frames.items()}
    for frame in shocked.values():
        frame.loc[frame.index > cutoff, ["open", "high", "low", "close"]] *= 3.0
    before = momentum_panel(frames, SMALL)
    after = momentum_panel(shocked, SMALL)
    known = before["month_end"] <= frames["A.NS"].index[350 - 30]  # month-ends whose holding month ends pre-shock
    assert len(before[known]) > 0
    pd.testing.assert_series_equal(before.loc[known, "score"], after.loc[known, "score"])
