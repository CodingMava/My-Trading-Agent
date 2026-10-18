"""Round 11 on synthetic data only: the option pricing, the ATM implied volatility from traded options, realized
volatility, dividends inside the holding window, O2's monthly picks and pool, and the cross-round bar."""
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from trader.research import round8, round10, round11


def _security(sid, closes, lows=None, present=None, locked=()):
    closes = np.asarray(closes, float)
    n = len(closes)
    present = np.ones(n, bool) if present is None else np.asarray(present, bool)
    lows = closes.copy() if lows is None else np.asarray(lows, float)
    prev = np.r_[np.nan, closes[:-1]]
    for j in locked:
        prev[j] = closes[j] * 0.9
    return round8.Security(sid=sid, present=present, eq=present.copy(), raw_close=closes, raw_open=closes.copy(),
                           raw_high=closes.copy(), raw_low=lows, raw_prev=prev, value=np.full(n, 1e8),
                           adj_open=closes.copy(), adj_low=lows.copy(), adj_close=closes.copy(),
                           last_row=np.maximum.accumulate(np.where(present, np.arange(n), -1)))


def test_black_scholes_and_its_inverse():
    c, p = round11.bs_price(100, 100, 1, 0.2, True), round11.bs_price(100, 100, 1, 0.2, False)
    assert c - p == pytest.approx(100 - 100 * math.exp(-0.065), abs=1e-9)  # put-call parity
    assert round11.implied_vol(c, 100, 100, 1, True) == pytest.approx(0.2, abs=1e-6)
    assert round11.implied_vol(p, 100, 100, 1, False) == pytest.approx(0.2, abs=1e-6)
    assert math.isnan(round11.implied_vol(1.0, 120, 100, 0.1, True))  # below intrinsic value
    assert math.isnan(round11.implied_vol(150.0, 100, 100, 0.1, True))  # above the underlying


def _chain(day, expiry, rows):
    return pd.DataFrame([{"expiry": expiry, "kind": k, "strike": s, "close": c, "contracts": n} for k, s, c, n in rows])


def test_atm_iv_uses_traded_options_of_the_nearest_expiry_at_least_seven_days_away():
    day = date(2020, 1, 31)
    S, T = 100.0, 27 / 365
    c, p = round11.bs_price(S, 100, T, 0.3, True), round11.bs_price(S, 100, T, 0.3, False)
    near, far = day + timedelta(days=5), day + timedelta(days=27)
    chain = pd.concat([
        _chain(day, near, [("CE", 100, 9.0, 50), ("PE", 100, 9.0, 50)]),  # too close to expiry
        _chain(day, far, [("CE", 100, c, 10), ("PE", 100, p, 10), ("CE", 102, 1.0, 0), ("PE", 102, 9.0, 3),
                          ("CE", 110, 0.5, 9)]),  # 102's call didn't trade; 110 is outside the band
    ])
    assert round11.atm_iv(chain, S, day) == pytest.approx(0.3, abs=1e-5)
    untraded = chain.assign(contracts=0)
    assert math.isnan(round11.atm_iv(untraded, S, day))


def test_realized_volatility_needs_22_rows_in_41_sessions():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, 60)
    closes = 100 * np.exp(np.cumsum(np.r_[0, r]))
    sec = _security("A", closes)
    assert round11.realized_vol(sec, 60) == pytest.approx(np.std(r[-21:], ddof=1) * math.sqrt(252))
    gappy = np.ones(61, bool)
    gappy[25:55] = False  # only 12 rows in the 41 sessions ending at 60
    assert math.isnan(round11.realized_vol(_security("B", closes, present=gappy), 60))


def test_dividends_count_inside_the_holding_window_under_5_percent_only():
    sec = _security("A", [100.0] * 60)
    events = [(5, 1.0, 0.01), (10, 2.0, 0.02), (30, 1.0, 0.01), (12, 8.0, 0.08)]  # (ex session, rupees, yield)
    assert round11.dividend_return(sec, events, 6, 20, "time") == pytest.approx(0.02)  # only 10 (12 is >= 5%)
    assert round11.dividend_return(sec, events, 10, 20, "time") == 0.0  # ex on the entry session: bought ex-dividend
    t = round11.trade(sec, events, 6, 25, "N1")
    assert t["div"] == pytest.approx(0.02) and t["net"] == pytest.approx(0.02 - round10.ROUND_TRIP["N1"])


def test_o2_buys_the_five_lowest_and_a_pick_that_cannot_be_bought_stays_in_cash():
    days, d = [], date(2009, 12, 1)
    while len(days) < 80:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    jan = max(i for i, x in enumerate(days) if x.month == 1)
    names = [f"S{j}" for j in range(8)]
    secs = {s: _security(s, [100.0] * 80, locked=(jan + 1,) if s == "S1" else ()) for s in names}
    table = pd.DataFrame({"i": jan, "sid": names, "rank": [1, 2, 3, 4, 5, 150, 160, 170]})
    signals = {(jan, s): float(j) for j, s in enumerate(names)}  # S0 lowest
    old = round11.SPANS
    round11.SPANS = {1: (date(2010, 1, 1), date(2010, 1, 31))}
    try:
        trades, pools = round11.run(1, days, secs, table, signals, {})
    finally:
        round11.SPANS = old
    assert list(trades["ticker"]) == ["S0", "S2", "S3", "S4"]  # S1 locked at its band on the entry open
    assert len(pools[jan]) == 7  # every enterable member with the signal
    assert set(trades["tier"]) == {"N1"} and trades["R"].tolist() == pytest.approx((trades["net"] / 0.15).tolist())


def test_criterion_12_uses_the_bar_of_0_05_over_67():
    rng = np.random.default_rng(1)
    dates = [date(2014, 1, 31) + timedelta(days=30 * k) for k in range(100)]
    net = rng.normal(0.01, 0.05, 100)
    trades = pd.DataFrame({"net": net, "gross": net + 0.004, "cost": 0.004, "R": net / 0.15, "ticker": [f"S{k % 25}" for k in range(100)],
                           "signal_date": dates, "signal_i": range(100), "exit_date": dates, "stopped": False, "gapped": False})
    checks, _ = round11.criteria(trades, (date(2013, 6, 28), date(2026, 8, 31)), 0.0007)
    c12 = next(c for c in checks if c.number == 12)
    assert "0.05/67" in c12.criterion and c12.passed
    assert not next(c for c in round11.criteria(trades, (date(2013, 6, 28), date(2026, 8, 31)), 0.0008)[0] if c.number == 12).passed


def test_round11_preregistration_matches_its_pin():
    assert round11.check_preregistration() == round11.PREREGISTRATION_SHA256
