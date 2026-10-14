"""Round 8 and the NSE bhavcopy loader, on synthetic data only."""
import io
import zipfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from trader.research import nse_bhavcopy as nb
from trader.research import round8 as r8


# ---------------------------------------------------------------------------------------------- the loader
def _zip(path, name, text):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, text)
    return path


def test_parse_reads_both_formats_and_keeps_equity_series(tmp_path):
    old = _zip(tmp_path / "cm03JAN2005bhav.csv.zip", "cm03JAN2005bhav.csv",
               "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,\n"
               "AAA,EQ,10,11,9,10.5,10.5,10,100,1050,3-JAN-2005,\n"
               "BBB,BE,20,21,19,20,20,20,5,100,3-JAN-2005,\n"
               "CCC,N1,100,100,100,100,100,100,1,100,3-JAN-2005,\n")
    frame = nb.parse(old)
    assert list(frame["symbol"]) == ["AAA", "BBB"] and frame["date"].iloc[0] == pd.Timestamp(2005, 1, 3)
    assert frame["isin"].isna().all() and frame.loc[0, "value"] == 1050
    header = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,"
              "OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
              "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n")
    new = _zip(tmp_path / "BhavCopy_NSE_CM_0_0_0_20261012_F_0000.csv.zip", "x.csv", header +
               "2026-10-12,2026-10-12,CM,NSE,STK,1,INE002A01018,RELIANCE,EQ,,,,,REL,1180,1185,1153,1158.9,1158.9,1170.3,,1158.9,,,10,11589,5,F1,1,,,,,\n"
               "2026-10-12,2026-10-12,CM,NSE,STK,2,INF204KB14I2,NIFTYBEES,EQ,,,,,ETF,257,258,254,254.66,254.69,257.35,,254.66,,,10,2546,4,F1,1,,,,,\n"
               "2026-10-12,2026-10-12,CM,NSE,STK,3,INE041025011,EMBASSY,RR,,,,,REIT,431,435,430,433,432,430,,433,,,10,4330,3,F1,1,,,,,\n")
    frame = nb.parse(new)
    assert list(frame["symbol"]) == ["RELIANCE", "NIFTYBEES"] and frame["date"].iloc[0] == pd.Timestamp(2026, 10, 12)
    assert frame.loc[frame["symbol"] == "RELIANCE", "prevclose"].iloc[0] == 1170.3


def test_parse_refuses_a_file_whose_rows_are_dated_differently(tmp_path):
    bad = _zip(tmp_path / "cm04JAN2005bhav.csv.zip", "cm04JAN2005bhav.csv",
               "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,\n"
               "AAA,EQ,10,11,9,10.5,10.5,10,100,1050,3-JAN-2005,\n")
    with pytest.raises(ValueError):
        nb.parse(bad)


def _rows(sid, closes, start=date(2020, 1, 1), opens=None, days=None):
    days = days or [start + timedelta(days=k) for k in range(len(closes))]
    opens = opens or closes
    return [{"date": pd.Timestamp(d), "symbol": sid, "series": "EQ", "open": o, "high": max(o, c) * 1.01,
             "low": min(o, c) * 0.99, "close": c, "prevclose": closes[k - 1] if k else c, "value": 1e8}
            for k, (d, o, c) in enumerate(zip(days, opens, closes))]


def _prepared(rows):
    panel = pd.DataFrame(rows)
    panel["sid"] = panel["symbol"]
    panel = nb.one_row_per_day(panel)
    same = panel["sid"].eq(panel["sid"].shift(1))
    panel["prev_row_close"] = panel["close"].shift(1).where(same)
    return panel


def _actions(*records):
    rows = []
    for symbol, ex, subject, face in records:
        ratio, kinds = nb.parse_ratio(subject)
        rights = nb.parse_rights(subject, face) if "right" in subject.lower() else None
        rows.append({"symbol": symbol, "isin": "", "ex_date": pd.Timestamp(ex), "subject": subject, "ratio": ratio,
                     "kinds": "; ".join(kinds), "distribution": bool(nb.DISTRIBUTION.search(subject)) and not kinds,
                     "rights_per_share": rights[0] if rights else np.nan, "rights_price": rights[1] if rights else np.nan,
                     "dividend": nb.parse_dividend(subject, face) if "div" in subject.lower() else 0.0})
    return pd.DataFrame(rows, columns=["symbol", "isin", "ex_date", "subject", "ratio", "kinds", "distribution",
                                       "rights_per_share", "rights_price", "dividend"])


def test_parsers_read_nse_corporate_action_subjects():
    assert nb.parse_ratio("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share")[0] == pytest.approx(0.2)
    assert nb.parse_ratio("Fv Spl-Rs5 To Rs2/Bon 1:1")[0] == pytest.approx(0.2)
    assert nb.parse_ratio("Fv Spl-Rs10tors5/Bon-2:1")[0] == pytest.approx(1 / 6)
    assert nb.parse_ratio("Bonus 1:2")[0] == pytest.approx(2 / 3)
    assert nb.parse_ratio("Scheme Of Arrangement - Bonus Ncrps 4:1")[0] == 1.0
    assert nb.parse_ratio("Agm/Div-Rs.5/-/Spl Div-Rs.2")[0] == 1.0
    assert nb.parse_rights("Rights 87:38 @ Premium Of Rs 2.50 Per Share", 10) == pytest.approx((87 / 38, 12.5))
    assert nb.parse_dividend("Special Dividend - Rs 118 Per Share", 10) == 118
    assert nb.parse_dividend("Agm/Div-125%", 10) == pytest.approx(12.5)


def test_a_recorded_split_is_applied_and_prices_stay_continuous():
    panel = _prepared(_rows("AAA", [100, 102, 51, 52], opens=[100, 101, 50.5, 51]))
    factor, log = nb.corporate_action_factors(panel, _actions(("AAA", "2020-01-03", "Bonus 1:1", 10)))
    assert list(factor) == [1.0, 1.0, 0.5, 1.0] and bool(log["applied"].iloc[0])


def test_a_record_dated_off_the_price_change_moves_to_it_or_is_not_applied():
    panel = _prepared(_rows("AAA", [100, 102, 103, 51, 52], opens=[100, 101, 102, 51, 51]))
    factor, log = nb.corporate_action_factors(panel, _actions(("AAA", "2020-01-02", "Bonus 1:1", 10)))
    assert list(factor) == [1.0, 1.0, 1.0, 0.5, 1.0] and log["why"].iloc[0] == "shifted to the price change"
    flat = _prepared(_rows("BBB", [100] * 15))
    factor, log = nb.corporate_action_factors(flat, _actions(("BBB", "2020-01-05", "Bonus 1:1", 10)))
    assert (factor == 1.0).all() and not bool(log["applied"].iloc[0])


def test_rights_dividends_and_demergers():
    rights = _prepared(_rows("RRR", [29.0, 18.25], opens=[29.0, 17.95]))
    factor, _ = nb.corporate_action_factors(rights, _actions(("RRR", "2020-01-02", "Rights 87:38 @ Premium Of Rs 2.50", 10)))
    assert factor.iloc[1] == pytest.approx((29 + 87 / 38 * 12.5) / (1 + 87 / 38) / 29)
    div = _prepared(_rows("DDD", [513.35, 399.5], opens=[513.35, 397.0]))
    factor, _ = nb.corporate_action_factors(div, _actions(("DDD", "2020-01-02", "Special Dividend - Rs 118 Per Share", 10)))
    assert factor.iloc[1] == pytest.approx(1 - 118 / 513.35)
    demerger = _prepared(_rows("EEE", [637.0, 109.75], opens=[637.0, 573.3]))
    factor, _ = nb.corporate_action_factors(demerger, _actions(("EEE", "2020-01-02", "Demerger", 10)))
    assert factor.iloc[1] == pytest.approx(109.75 / 637)  # the close, not the unreliable open


def test_a_missing_split_is_inferred_only_at_a_standard_ratio():
    split = _prepared(_rows("SSS", [1000, 201, 205], opens=[1000, 199, 202]))
    factor, log = nb.corporate_action_factors(split, _actions())
    assert factor.iloc[1] == pytest.approx(0.2) and log["why"].iloc[0] == "inferred from the price change"
    crash = _prepared(_rows("CCC", [100, 70, 68], opens=[100, 70, 69]))  # a 30% fall: not inferred
    factor, _ = nb.corporate_action_factors(crash, _actions())
    assert (factor == 1.0).all()


def test_renames_join_only_when_the_previous_close_continues():
    old = _rows("OLDNAME", [10, 11], days=[date(2020, 1, 1), date(2020, 1, 2)])
    new = _rows("NEWNAME", [12, 13], days=[date(2020, 1, 3), date(2020, 1, 6)])
    new[0]["prevclose"] = 11
    other = _rows("XOLD", [10, 11], days=[date(2020, 1, 1), date(2020, 1, 2)])
    other_new = _rows("XNEW", [50, 51], days=[date(2020, 1, 3), date(2020, 1, 6)])
    other_new[0]["prevclose"] = 40
    panel = pd.DataFrame(old + new + other + other_new)
    changes = pd.DataFrame({"old": ["OLDNAME", "XOLD"], "new": ["NEWNAME", "XNEW"],
                            "effective": [pd.Timestamp(2020, 1, 3), pd.Timestamp(2020, 1, 3)]})
    joined, report = nb.join_renames(panel, changes)
    assert set(joined.loc[joined["symbol"] == "OLDNAME", "sid"]) == {"NEWNAME"}
    assert set(joined.loc[joined["symbol"] == "XOLD", "sid"]) == {"XOLD"}
    assert list(report["joined"]) == [True, False]


def test_equity_shares_exclude_funds():
    assert r8.is_equity_share(pd.Series(["INE002A01018"]), "RELIANCE")
    assert not r8.is_equity_share(pd.Series(["INF204KB14I2"]), "NIFTYBEES")
    assert r8.is_equity_share(pd.Series([None, None]), "OLDCO")
    assert not r8.is_equity_share(pd.Series([None]), "NIFTYBEES", frozenset({"NIFTYBEES"}))


# ------------------------------------------------------------------------------------------- the rules
def _security(closes, opens=None, lows=None, present=None, eq=None, value=None):
    n = len(closes)
    closes = np.asarray(closes, float)
    opens = np.asarray(opens if opens is not None else closes, float)
    lows = np.asarray(lows if lows is not None else np.minimum(opens, closes) * 0.995, float)
    present = np.asarray(present if present is not None else [True] * n)
    closes, opens, lows = (np.where(present, a, np.nan) for a in (closes, opens, lows))
    last = np.maximum.accumulate(np.where(present, np.arange(n), -1))
    return r8.Security(sid="S", present=present, eq=np.asarray(eq if eq is not None else present), raw_close=closes,
                       raw_open=opens, raw_high=np.fmax(opens, closes) * 1.005, raw_low=lows,
                       raw_prev=np.r_[np.nan, closes[:-1]], value=np.where(present, value or 1e8, 0.0),
                       adj_open=opens, adj_low=lows, adj_close=closes, last_row=last)


def test_month_ends():
    days = [date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3), date(2020, 2, 28), date(2020, 3, 2)]
    assert r8.month_ends(days) == [1, 3, 4]


def test_momentum_score_skips_the_last_month_and_refuses_stale_rows():
    closes = np.linspace(100, 200, 300)
    sec = _security(closes)
    assert r8.score_at(sec, 299, 252) == pytest.approx(closes[278] / closes[47] - 1)
    present = np.ones(300, bool)
    present[30:60] = False  # no rows for 30 sessions around i-252
    stale = _security(closes, present=present)
    assert np.isnan(r8.score_at(stale, 299, 252))


def test_a_stock_locked_at_its_upper_band_cannot_be_bought():
    sec = _security([100, 105])
    sec.raw_open[1] = sec.raw_high[1] = sec.raw_low[1] = sec.raw_close[1] = 105.0
    assert not r8.enterable(sec, 1)
    assert r8.enterable(_security([100, 105]), 1)
    gone = _security([100, 105], present=[True, False])
    assert not r8.enterable(gone, 1)


def test_stop_fills_at_the_stop_or_at_a_gap_open():
    sec = _security([100, 100, 95, 92, 99], opens=[100, 100, 96, 92, 99], lows=[99, 99, 89, 91, 98])
    t = r8.simulate(sec, 1, 4, 0.10)  # entry 100, stop 90: day 2's low 89 reaches it
    assert t["reason"] == "stop" and t["gross"] == pytest.approx(-0.10) and not t["gapped"]
    gap = _security([100, 100, 85, 86], opens=[100, 100, 80, 86], lows=[99, 99, 79, 85])
    t = r8.simulate(gap, 1, 3, 0.10)
    assert t["reason"] == "stop" and t["gross"] == pytest.approx(-0.20) and t["gapped"]


def test_time_exit_at_the_next_open_with_a_row_or_the_last_close():
    sec = _security([100, 100, 104, 108, 110], opens=[100, 100, 103, 107, 109])
    t = r8.simulate(sec, 1, 3, 0.10)
    assert t["reason"] == "time" and t["gross"] == pytest.approx(0.07) and t["exit_i"] == 3
    suspended = _security([100, 100, 104, 108, 110], opens=[100, 100, 103, 107, 109], present=[True, True, True, False, True])
    t = r8.simulate(suspended, 1, 3, 0.10)
    assert t["reason"] == "time, delayed" and t["exit_i"] == 4 and t["gross"] == pytest.approx(0.09)
    delisted = _security([100, 100, 104, 108, 110], opens=[100, 100, 103, 107, 109], present=[True, True, True, False, False])
    t = r8.simulate(delisted, 1, 3, 0.10)
    assert t["reason"] == "no further rows" and t["gross"] == pytest.approx(0.04)


def test_features_apply_the_eligibility_rules():
    n = 400
    days = [date(2020, 1, 1) + timedelta(days=k) for k in range(n)]
    good = _security(np.linspace(100, 150, n))
    cheap = _security(np.linspace(5, 8, n))  # below Rs 10
    young = _security(np.linspace(100, 150, n), present=[k >= 200 for k in range(n)])  # under 273 rows
    be = _security(np.linspace(100, 150, n), eq=[k < n - 1 for k in range(n)])  # not EQ on the signal day
    secs = {"GOOD": good, "CHEAP": cheap, "YOUNG": young, "BE": be}
    for sid, sec in secs.items():
        sec.sid = sid
    table = r8.features(days, secs, [n - 1])
    assert list(table["sid"]) == ["GOOD"] and table["rank"].iloc[0] == 1


# ------------------------------------------------------------------------------------------- the tests
def test_baseline_counts_random_picks_at_least_as_good():
    pools = {0: np.array([0.01, 0.02, 0.03, 0.10]), 1: np.array([0.0, 0.0, 0.05, 0.20])}
    best = pd.DataFrame({"signal_i": [0, 1], "net": [0.10, 0.20]})
    mean, p, stats = r8.baseline(best, pools, draws=2000, seed=1)
    assert p == pytest.approx((int((stats >= 0.15).sum()) + 1) / 2001)
    assert p < 0.1 and mean == pytest.approx(np.mean([pools[0].mean(), pools[1].mean()]), abs=0.005)
    worst = pd.DataFrame({"signal_i": [0, 1], "net": [0.01, 0.0]})
    assert r8.baseline(worst, pools, draws=2000, seed=1)[1] > 0.9


def test_baseline_draws_without_replacement_within_a_month():
    pools = {0: np.array([1.0, 0.0])}
    trades = pd.DataFrame({"signal_i": [0, 0], "net": [0.5, 0.5]})
    _, _, stats = r8.baseline(trades, pools, draws=100, seed=3)
    assert np.allclose(stats, 0.5)  # both members drawn every time


def test_holm():
    assert r8.holm({"N1": 0.01, "N2": 0.04}) == {"N1": 0.02, "N2": 0.04}
    assert r8.holm({"N1": 0.03, "N2": 0.02}) == {"N2": 0.04, "N1": 0.04}


def _trades(net, months=60, per_month=5, seed=0):
    rng = np.random.default_rng(seed)
    rows, start = [], date(2013, 7, 1)
    tickers = [f"S{k}" for k in range(30)]
    for m in range(months):
        d = start + timedelta(days=30 * m)
        for k in range(per_month):
            g = net[(m * per_month + k) % len(net)] + 0.0035
            rows.append({"signal_i": m, "signal_date": d, "exit_date": d + timedelta(days=28 + k), "ticker": tickers[rng.integers(30)],
                         "gross": g, "net": g - 0.0035, "cost": 0.0035, "R": (g - 0.0035) / 0.10,
                         "stopped": False, "gapped": False})
    return pd.DataFrame(rows)


def test_criteria_pass_a_strong_strategy_and_fail_a_weak_one():
    strong = _trades([0.04, 0.03, -0.01, 0.02, 0.05, -0.02, 0.03])
    checks, stats = r8.criteria(strong, (date(2013, 7, 1), date(2018, 6, 1)), 0.001, 0.0005)
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
    weak = _trades([0.01, -0.02, -0.01, -0.01])
    checks, _ = r8.criteria(weak, (date(2013, 7, 1), date(2018, 6, 1)), 0.5, 0.4)
    assert not checks[1].passed and r8.decide(checks) == "REJECTED"


def test_drawdown_in_r_nets_simultaneous_exits():
    trades = pd.DataFrame({"exit_date": [date(2020, 1, 1)] * 2 + [date(2020, 1, 2)], "R": [-1.0, 0.5, -2.0]})
    assert r8.drawdown_r(r8.r_in_exit_order(trades)) == pytest.approx(2.5)


def test_pbo_low_when_one_variant_dominates_everywhere_and_about_half_for_noise_on_average():
    noise = np.random.default_rng(0).normal(0, 0.02, size=(160, 6))
    dominant = noise.copy()
    dominant[:, 0] += 0.05
    assert r8.pbo(dominant)["pbo"] < 0.05
    # one noise sample can land anywhere; over many samples the IS-best variant is OOS-median half the time
    values = [r8.pbo(np.random.default_rng(seed).normal(0, 0.02, size=(160, 6)), blocks=8)["pbo"] for seed in range(40)]
    assert 0.4 < np.mean(values) < 0.6


def test_deflated_sharpe_falls_with_more_trials():
    rng = np.random.default_rng(1)
    x = rng.normal(0.005, 0.03, 160)
    few, many = r8.dsr(x, 2, 0.01), r8.dsr(x, 200, 0.01)
    assert many["dsr"] < few["dsr"] and 0 <= many["dsr"] <= 1


def test_wilson_interval():
    lo, hi = r8.wilson(50, 100)
    assert lo == pytest.approx(0.4038, abs=1e-3) and hi == pytest.approx(0.5962, abs=1e-3)


def test_round_trip_costs_match_the_preregistration():
    assert r8.ROUND_TRIP["N1"] == pytest.approx(0.0035316, abs=2e-6)
    assert r8.ROUND_TRIP["N2"] == pytest.approx(0.0045316, abs=2e-6)


def test_the_runner_refuses_a_changed_preregistration(monkeypatch, tmp_path):
    changed = tmp_path / "pre.md"
    changed.write_bytes(b"something else\n")
    monkeypatch.setattr(r8, "PREREGISTRATION", changed)
    with pytest.raises(SystemExit):
        r8.check_preregistration()


def test_the_preregistration_is_pinned():
    assert r8.check_preregistration() == r8.PREREGISTRATION_SHA256
    assert len(r8.PANEL_SHA256) == 64
