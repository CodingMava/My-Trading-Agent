import numpy as np
import pandas as pd
import pytest

from trader.research import round6
from trader.research.simulator import STOP, TIME


def rising(days=110, start="2024-01-01"):
    """Bars that rise 1.5% and 0.5% on alternate days, each opening at the previous close: no gaps, a
    90-day sigma near 0.5%, and the 20-day average about 9% below the price."""
    returns = np.where(np.arange(days) % 2 == 0, 0.015, 0.005)
    close = 100 * np.cumprod(1 + returns)
    open_ = np.r_[100.0, close[:-1]]
    frame = pd.DataFrame({"open": open_, "close": close, "high": np.maximum(open_, close) * 1.001,
                          "low": np.minimum(open_, close) * 0.999, "volume": 1_000},
                         index=pd.bdate_range(start, periods=days, tz="Asia/Kolkata"))
    return frame


def gap_day(frame, gap, close=1.0, low=None):
    """The last bar opens `gap` below the previous low; it closes at `close` x the open."""
    frame = frame.copy()
    open_ = frame["low"].iloc[-2] * (1 + gap)
    frame.iloc[-1, frame.columns.get_indexer(["open", "close", "high", "low"])] = [
        open_, open_ * close, max(open_, open_ * close) * 1.001, open_ * (low if low else min(1.0, close) * 0.999)]
    return frame


def test_the_preregistration_is_unchanged():
    assert round6.check_preregistration().startswith("31537d73")


def test_buy_on_gap_buys_the_deepest_gaps_still_above_their_20_day_average():
    pieces = {"AAA.NS": gap_day(rising(), -0.03, close=1.01),  # deepest gap; recovers 1% by the close
              "BBB.NS#2": gap_day(rising(), -0.02, low=0.95),  # falls through its stop during the day
              "CCC.NS": gap_day(rising(), -0.01, close=0.995),  # a smaller gap: third in line
              "DDD.NS": gap_day(rising(), -0.002)}  # less than one sigma: not a gap that counts
    trades, pools = round6.buy_on_gap(pieces, "C1", top_n=2)
    assert list(trades["ticker"]) == ["AAA.NS", "BBB.NS"] and set(trades["signal_date"]) == {pieces["AAA.NS"].index[-1].date()}
    stop = round6.features(pieces["BBB.NS#2"])["atr"].iloc[-1]  # one ATR below the entry
    assert trades["gross"].tolist() == pytest.approx([0.01, -stop]) and trades["reason"].tolist() == [TIME, STOP]
    assert len(round6.buy_on_gap(pieces, "C1")[0]) == 3  # up to 10 a day by default
    assert set(pools) == {"AAA.NS", "BBB.NS", "CCC.NS", "DDD.NS"} and len(pools["AAA.NS"]) == 110 - 91


def test_opening_gap_trades_in_the_gaps_direction_until_the_close():
    up = gap_day(rising(), 0.0)
    up.iloc[-1, up.columns.get_indexer(["open", "close", "high", "low"])] = (
        up["high"].iloc[-2] * 1.01 * np.array([1, 1.004, 1.005, 0.999]))  # gaps above yesterday's high, rises 0.4%
    trades, pools = round6.opening_gap(up, "^NSEI", "C3")
    assert trades["side"].tolist() == ["long"] and trades["gross"].iloc[0] == pytest.approx(0.004)
    down = gap_day(rising(), -0.01, close=0.995)  # opens below yesterday's low and falls 0.5%: a winning short
    trades, _ = round6.opening_gap(down, "^NSEI", "C3")
    assert trades["side"].tolist() == ["short"] and trades["gross"].iloc[0] == pytest.approx(0.005)
    assert set(pools) == {"long", "short"}


def monthly(prices, start="2020-01-01"):
    index = pd.bdate_range(start, periods=len(prices), tz="America/New_York")
    return pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices}, index=index)


def test_time_series_momentum_holds_only_after_a_positive_year_and_pays_each_switch_once():
    prices = np.r_[100 * 1.001 ** np.arange(500), 100 * 1.001 ** 499 * 0.998 ** np.arange(1, 260)]  # up, then down
    months = round6.tsmom(monthly(prices), pd.Series(0.05, index=monthly(prices).index), cost=0.002)
    invested = months["invested"].tolist()
    first_out = invested.index(False)
    assert invested[0] and not any(invested[first_out:]) and all(invested[:first_out])  # in, then out for good
    assert months["switch_cost"].sum() == pytest.approx(0.002)  # half on the way in, half on the way out
    cash = months[~months["invested"]]
    days = (cash["exit_time"] - cash["entry_time"]).dt.days
    assert cash["net"].tolist() == pytest.approx((0.05 * days / 365).tolist())  # cash months earn the cash rate
    trades = round6.tsmom_trades(months)
    assert len(trades) == first_out and trades["gross"].iloc[0] == pytest.approx(months["gross"].iloc[0] - 0.001)


def test_invested_months_are_compared_with_random_months():
    months = pd.DataFrame({"gross": [0.01] * 5 + [-0.01] * 5, "invested": [True] * 5 + [False] * 5})
    mean, p = round6.months_random_test(months)
    assert mean == pytest.approx(0.0, abs=0.002) and p < 0.1  # five +1% months in a row is rare by chance
    assert round6.months_random_test(months.assign(gross=0.01))[1] == 1.0  # all months alike: no information
