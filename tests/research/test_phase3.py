from datetime import date

import numpy as np
import pandas as pd
import pytest

from tests.helpers import daily_session_bars
from trader.gate import Check, decide
from trader.research.phase3 import check_preregistration, clean_daily, holm, selection_test


def test_the_preregistration_is_unchanged():
    assert check_preregistration().startswith("4be087a7")


def test_cleaning_drops_broken_and_placeholder_bars_and_splits_at_corporate_actions():
    days = [date(2026, 8, d) for d in (3, 4, 5, 6, 7, 10, 11)]
    frame = daily_session_bars(days)
    frame.iloc[2, :4] = frame["close"].iloc[1]  # a flat placeholder bar...
    frame.iloc[2, 4] = 0  # ...with zero volume
    frame.iloc[3, 4] = 0  # zero volume but real prices: kept
    frame.iloc[-1, 3] = np.nan  # a bar without a close
    pieces, notes = clean_daily({"X.NS": frame}, breaks={"X.NS": ["2026-08-07"]})
    assert list(pieces) == ["X.NS", "X.NS#2"]
    assert [d.day for d in pieces["X.NS"].index] == [3, 4, 6]
    assert [d.day for d in pieces["X.NS#2"].index] == [7, 10]
    assert "1 bar(s) without prices and 1 flat" in notes["X.NS"] and "split at 2026-08-07" in notes["X.NS"]


def test_holm_adjustment():
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_selection_baseline_rewards_genuine_skill_only():
    rng = np.random.default_rng(0)
    months = np.repeat(pd.date_range("2022-01-31", periods=36, freq="ME"), 10)
    panel = pd.DataFrame({"month_end": months, "gross": rng.normal(0, 0.05, len(months))})
    best = panel.groupby("month_end")["gross"].rank(ascending=False) <= 2
    _, p_best = selection_test(panel.assign(selected=best))
    assert p_best < 0.001  # picking each month's actual winners beats random picks
    _, p_worst = selection_test(panel.assign(selected=~(panel.groupby("month_end")["gross"].rank() > 2)))
    assert p_worst > 0.999


def test_decision_rule():
    passing = [Check(n, "", "", True) for n in range(1, 10)]
    assert decide(passing) == "PAPER"
    assert decide([Check(1, "", "", False), *passing[1:]]) == "RESEARCH"
    assert decide([*passing[:4], Check(5, "", "", False), *passing[5:]]) == "REJECTED"
