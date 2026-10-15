"""Round 9 on synthetic data only: the volatility measure, the low-volatility and volatility-adjusted momentum scores,
and the cross-round bar."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from trader.research import round8, round9


def _security(closes, present=None):
    n = len(closes)
    closes = np.asarray(closes, float)
    present = np.asarray(present if present is not None else [True] * n)
    closes = np.where(present, closes, np.nan)
    last = np.maximum.accumulate(np.where(present, np.arange(n), -1))
    return round8.Security(sid="S", present=present, eq=present.copy(), raw_close=closes, raw_open=closes.copy(),
                           raw_high=closes * 1.01, raw_low=closes * 0.99, raw_prev=np.r_[np.nan, closes[:-1]],
                           value=np.where(present, 1e8, 0.0), adj_open=closes.copy(), adj_low=closes * 0.99,
                           adj_close=closes.copy(), last_row=last)


def test_volatility_is_annualised_row_to_row_and_needs_200_returns():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, 400)
    closes = 100 * np.exp(np.cumsum(np.r_[0, returns]))
    vol = round9.volatility(_security(closes))
    assert np.isnan(vol[199]) and not np.isnan(vol[200])  # 200 returns end at row 200
    assert vol[400] == pytest.approx(np.std(returns[-252:], ddof=1) * np.sqrt(252))
    gappy = np.ones(401, bool)
    gappy[100:150] = False  # sessions without a row: returns are from row to row
    vol_gappy = round9.volatility(_security(closes, gappy))
    assert np.isnan(vol_gappy[120]) and not np.isnan(vol_gappy[400])


def test_scores_pick_the_least_volatile_and_the_smoothest_winners():
    rng = np.random.default_rng(1)
    secs, rows = {}, []
    n = 300
    for k in range(6):  # the same trend, more and more noise: k = 0 is the smoothest
        noise = rng.normal(0, 0.002 + 0.01 * k, n)
        closes = 100 * np.exp(np.cumsum(0.001 + noise))
        secs[f"S{k}"] = _security(closes)
        rows.append({"i": n - 1, "sid": f"S{k}", "liquidity": 1e8 - k, "rank": 101 + k,
                     "score_12-1": closes[n - 22] / closes[n - 253] - 1, "score_6-1": closes[n - 22] / closes[n - 127] - 1})
    table = round9.add_scores(pd.DataFrame(rows), secs)
    assert list(table.sort_values("score_L", ascending=False)["sid"])[:3] == ["S0", "S1", "S2"]  # least volatile first
    v = table.set_index("sid")["score_V"]
    m12, m6 = table["score_12-1"] / table["vol"], table["score_6-1"] / table["vol"]
    expected = ((m12 - m12.mean()) / m12.std(ddof=1) + (m6 - m6.mean()) / m6.std(ddof=1)) / 2
    assert np.allclose(v.to_numpy(), expected.to_numpy())
    outside = round9.add_scores(pd.DataFrame(rows).assign(rank=[5, 6, 7, 8, 9, 10]), secs)
    assert outside["score_V"].isna().all()  # V2's scores are only for the 101-300 tier


def test_criterion_12_uses_the_bar_for_28_hypotheses():
    rows, d = [], date(2013, 7, 1)
    for m in range(60):
        for k in range(5):
            net = [0.04, 0.03, -0.01, 0.02, 0.05][k]
            rows.append({"signal_i": m, "signal_date": d + timedelta(days=30 * m), "exit_date": d + timedelta(days=30 * m + 28 + k),
                         "ticker": f"S{(m + k) % 20}", "gross": net + 0.0035, "net": net, "cost": 0.0035, "R": net / 0.1,
                         "stopped": False, "gapped": False})
    trades = pd.DataFrame(rows)
    checks, _ = round9.criteria(trades, (date(2013, 7, 1), date(2018, 6, 1)), 0.001, 0.0019)
    c12 = next(c for c in checks if c.number == 12)
    assert not c12.passed and c12.criterion.endswith("0.05/28 = 0.00179")  # 0.0019 passed round 8's bar, not this one
    checks, _ = round9.criteria(trades, (date(2013, 7, 1), date(2018, 6, 1)), 0.001, 0.0015)
    assert next(c for c in checks if c.number == 12).passed


def test_the_runner_refuses_a_changed_preregistration(monkeypatch, tmp_path):
    changed = tmp_path / "pre.md"
    changed.write_bytes(b"something else\n")
    monkeypatch.setattr(round9, "PREREGISTRATION", changed)
    with pytest.raises(SystemExit):
        round9.check_preregistration()


def test_the_preregistration_is_pinned():
    assert round9.check_preregistration() == round9.PREREGISTRATION_SHA256
