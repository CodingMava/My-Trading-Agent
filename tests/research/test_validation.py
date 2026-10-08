import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_from_returns
from trader.research.costs import ZERODHA_DELIVERY
from trader.research.metrics import summarize
from trader.research.simulator import ExitRules, select_trades, simulate, trade_rows
from trader.research.validation import (outcome_pools, period_table, random_entry_test, regime_table,
                                        walk_forward_folds)

COST = ZERODHA_DELIVERY.round_trip(100_000)


def backtest_daily(bars, signal, rules):
    out = simulate(bars, "long", rules, "next_open")
    trades = trade_rows("SYN", bars.index, select_trades(signal, out), out, "long", "test")
    return out, trades


def test_a_planted_edge_is_detected_and_beats_random_entries():
    rng = np.random.default_rng(3)
    n = 2000
    returns = rng.normal(0, 0.01, n)
    signal = np.zeros(n, dtype=bool)
    signal[20:n - 10:15] = True
    for k in np.flatnonzero(signal):
        returns[k + 1:k + 6] += 0.01  # the five days after each signal drift up 1% a day
    bars = daily_from_returns(returns)
    out, trades = backtest_daily(bars, signal, ExitRules(max_hold_bars=5))
    stats = summarize(trades, COST, list(bars.index.date))
    assert stats["exp_net_pct"] > 2 and stats["t_stat"] > 5

    pools = outcome_pools([(np.full(n, "all"), out.gross)])
    random_mean, p_value = random_entry_test(pools, pd.Series(["all"] * len(trades)), trades["gross"])
    assert p_value < 0.01 and random_mean < trades["gross"].mean()


def test_random_signals_on_a_random_walk_show_no_edge():
    rng = np.random.default_rng(11)
    n = 3000
    bars = daily_from_returns(rng.normal(0, 0.005, n), seed=11)  # low volatility: costs dominate the noise
    _, trades = backtest_daily(bars, rng.random(n) < 0.1, ExitRules(stop=0.03, target=0.03, max_hold_bars=10))
    gross = trades["gross"]
    assert abs(gross.mean() / (gross.std() / np.sqrt(len(gross)))) < 3
    assert summarize(trades, COST, list(bars.index.date))["exp_net_pct"] < 0  # costs make chance a loser


def test_walk_forward_folds_are_chronological_and_never_overlap():
    dates = list(pd.bdate_range("2020-01-01", periods=100).date)
    folds = walk_forward_folds(dates, train_size=40, test_size=20)
    assert len(folds) == 3
    for train, test in folds:
        assert len(train) == 40 and len(test) == 20 and max(train) < min(test)
    assert folds[1][0][0] == dates[20]
    anchored = walk_forward_folds(dates, 40, 20, anchored=True)
    assert anchored[2][0][0] == dates[0] and len(anchored[2][0]) == 80


def test_period_and_regime_tables():
    trades = pd.DataFrame({"signal_date": [pd.Timestamp("2025-03-03").date(), pd.Timestamp("2025-09-01").date()],
                           "gross": [0.012, -0.008]})
    blocks = period_table(trades, cost=0.002)
    assert blocks.loc["2025H1", "mean"] == pytest.approx(1.0) and blocks.loc["2025H2", "mean"] == pytest.approx(-1.0)
    regime = pd.Series({trades["signal_date"][0]: True, trades["signal_date"][1]: False})
    row = regime_table(trades, 0.002, {"bull": regime})
    assert row["bull n"] == 1 and row["bull exp%"] == pytest.approx(1.0)
    assert row["not bull n"] == 1 and row["not bull win%"] == 0
