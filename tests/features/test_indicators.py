import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_from_returns
from trader.features.indicators import atr, rsi, sma, true_range, wilder_average


def test_sma():
    assert sma(pd.Series([1.0, 2, 3, 4]), 2).tolist()[1:] == [1.5, 2.5, 3.5] and np.isnan(sma(pd.Series([1.0]), 2)[0])


def test_wilder_average_seeds_with_a_simple_mean():
    out = wilder_average(pd.Series([np.nan, 2.0, 4.0, 6.0, 0.0]), 2)
    assert np.isnan(out[:2]).all()
    assert out[2] == 3.0 and out[3] == 4.5 and out[4] == 2.25  # 3 + (6-3)/2, then 4.5 + (0-4.5)/2


def test_rsi_matches_a_hand_calculation():
    # changes +0.34, -0.25, -0.48, +0.72 -> Wilder(2) averages: gains .17, .085, .4025; losses .125, .3025, .15125
    values = rsi(pd.Series([44.0, 44.34, 44.09, 43.61, 44.33]), 2)
    assert np.isnan(values[:2]).all()
    assert values[2:].tolist() == pytest.approx([100 - 100 / (1 + 0.17 / 0.125), 100 - 100 / (1 + 0.085 / 0.3025),
                                                 100 - 100 / (1 + 0.4025 / 0.15125)])


def test_rsi_edge_cases():
    assert rsi(pd.Series([1.0, 2, 3, 4, 5]), 2).iloc[-1] == 100  # only gains
    assert rsi(pd.Series([5.0, 5, 5, 5]), 2).iloc[-1] == 50  # no movement at all


def test_atr_matches_a_hand_calculation():
    high, low, close = pd.Series([10.0, 11, 12, 11]), pd.Series([9.0, 10, 10, 9]), pd.Series([9.5, 10.5, 11, 10])
    assert true_range(high, low, close).tolist()[1:] == [1.5, 2.0, 2.0]  # max(h-l, |h-prev c|, |l-prev c|)
    assert atr(high, low, close, 2).tolist()[2:] == [1.75, 1.875]


def test_indicators_are_causal():
    bars = daily_from_returns(np.random.default_rng(5).normal(0.0005, 0.015, 400))
    full = {"sma": sma(bars["close"], 50), "rsi": rsi(bars["close"], 2),
            "atr": atr(bars["high"], bars["low"], bars["close"], 14)}
    for cut in (120, 250, 399):
        part = bars.iloc[:cut]
        truncated = {"sma": sma(part["close"], 50), "rsi": rsi(part["close"], 2),
                     "atr": atr(part["high"], part["low"], part["close"], 14)}
        for name in full:
            pd.testing.assert_series_equal(truncated[name], full[name].iloc[:cut], check_names=False)


def test_rsi_agrees_with_pandas_ta_once_warmed_up():
    import pandas_ta

    close = daily_from_returns(np.random.default_rng(9).normal(0, 0.01, 600))["close"]
    ours, theirs = rsi(close, 14), pandas_ta.rsi(close, length=14)
    assert np.allclose(ours.iloc[300:], theirs.iloc[300:], atol=1e-6)
