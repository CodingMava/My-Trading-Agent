from datetime import date

import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_session_bars
from trader.research import round2
from trader.research.validation import clustered_t, random_entry_test, same_day_random_test


def test_the_preregistration_is_unchanged():
    assert round2.check_preregistration().startswith("f61e6ee0")


def test_clustered_t_equals_the_ordinary_t_with_one_observation_per_cluster():
    x = np.random.default_rng(1).normal(0.1, 1, 200)
    assert clustered_t(x, range(len(x))) == pytest.approx(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def test_clustered_t_does_not_count_copies_as_new_evidence():
    x = np.random.default_rng(2).normal(0.1, 1, 100)
    copies = np.repeat(x, 10)  # ten times the trades, no new information
    naive = copies.mean() / (copies.std(ddof=1) / np.sqrt(len(copies)))
    clustered = clustered_t(copies, np.repeat(np.arange(100), 10))
    assert clustered == pytest.approx(clustered_t(x, range(100)))
    assert naive == pytest.approx(np.sqrt(10) * clustered, rel=0.01)


def test_the_same_day_baseline_is_stricter_when_instruments_move_together():
    rng = np.random.default_rng(3)
    days = pd.date_range("2022-01-03", periods=1000, freq="B").date
    outcome = pd.Series(rng.normal(0, 1, 1000), index=days)
    picked = rng.choice(1000, 50, replace=False)
    outcome.iloc[picked] += 0.4 - outcome.iloc[picked].mean()  # the strategy's days average +0.4 (pool: +0.07)
    pools = {"A": outcome, "B": outcome.copy()}  # two instruments that always move together
    trades = pd.DataFrame({"ticker": ["A", "B"] * 50, "signal_date": np.repeat(days[picked], 2),
                           "gross": np.repeat(outcome.iloc[picked].to_numpy(), 2)})
    _, independent = random_entry_test({k: v.to_numpy() for k, v in pools.items()}, trades["ticker"], trades["gross"])
    _, same_day = same_day_random_test(pools, trades)
    assert independent < 0.002  # 100 "independent" trades look convincing (z = 3.3)...
    assert 0.003 < same_day < 0.03  # ...but they are 50 bets, and the evidence is weaker (z = 2.3)


def test_the_same_day_baseline_only_draws_days_every_instrument_could_trade():
    days = pd.date_range("2022-01-03", periods=10, freq="B").date
    pools = {"A": pd.Series([0.0] * 5 + [1.0] * 5, index=days), "C": pd.Series([0.0] * 5, index=days[5:])}
    trades = pd.DataFrame({"ticker": ["A", "C"], "signal_date": [days[7]] * 2, "gross": [1.0, 0.0]})
    assert same_day_random_test(pools, trades) == (0.5, 1.0)  # C only trades on A's +1.0 days


def test_large_moves_are_flagged_and_must_be_classified(monkeypatch):
    bars = daily_session_bars([date(2016, 6, 28), date(2016, 6, 29), date(2016, 6, 30), date(2016, 7, 1),
                               date(2016, 7, 5), date(2016, 7, 6)])
    bars.iloc[4, :4] = bars.iloc[4, :4] * 1.6  # a +60% jump on 5 Jul 2016
    bars.iloc[5, :4] = bars.iloc[5, :4] * 1.6
    moves = round2.large_moves({"DHR": bars, "XYZ": bars})
    assert [(s, d) for s, d, _, _ in moves] == [("DHR", date(2016, 7, 5)), ("XYZ", date(2016, 7, 5))]
    assert round2.classify("DHR", date(2016, 7, 5)).startswith("Corporate action")
    assert round2.classify("XYZ", date(2020, 3, 16)) == "Genuine: COVID-19 crash"
    assert round2.classify("XYZ", date(2016, 7, 5)) is None
    monkeypatch.setattr(round2, "load_dataset", lambda directory: {"XYZ": bars})
    with pytest.raises(SystemExit, match="XYZ"):
        round2.load_clean("anything")  # an unclassified move stops the run before any strategy sees the data
    monkeypatch.setattr(round2, "load_dataset", lambda directory: {"DHR": bars})
    pieces, _ = round2.load_clean("anything")
    assert list(pieces) == ["DHR", "DHR#2"]  # split at the corporate action
