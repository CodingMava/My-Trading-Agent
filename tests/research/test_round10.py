"""Round 10 on synthetic data only: notice timing, reschedules, the reaction signal's point-in-time threshold, the
promoter-purchase filter, the shared 5-position account, costs at the engine's size and the random baseline."""
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from trader.research import round8, round10


def _sessions(n=160, start=date(2020, 1, 1)):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _security(sid, closes, lows=None, present=None):
    closes = np.asarray(closes, float)
    n = len(closes)
    present = np.ones(n, bool) if present is None else np.asarray(present, bool)
    closes = np.where(present, closes, np.nan)
    lows = closes.copy() if lows is None else np.where(present, np.asarray(lows, float), np.nan)
    last = np.maximum.accumulate(np.where(present, np.arange(n), -1))
    return round8.Security(sid=sid, present=present, eq=present.copy(), raw_close=closes, raw_open=closes.copy(),
                           raw_high=closes.copy(), raw_low=lows, raw_prev=np.r_[np.nan, closes[:-1]],
                           value=np.where(present, 1e8, 0.0), adj_open=closes.copy(), adj_low=lows, adj_close=closes.copy(),
                           last_row=last)


def _universe(sids, i=0):
    return round10.Universe(pd.DataFrame({"i": i, "sid": sids, "rank": range(1, len(sids) + 1)}))


def test_costs_are_round_8s_model_at_the_engine_position_of_rs_33333():
    assert round10.NOTIONAL == pytest.approx(33_333.33, abs=0.01)
    assert 100 * round10.ROUND_TRIP["N1"] == pytest.approx(0.3685, abs=1e-4)
    assert 100 * round10.ROUND_TRIP["N2"] == pytest.approx(0.4685, abs=1e-4)


def test_a_notice_counts_from_the_session_whose_1800_decision_follows_it():
    s = _sessions(10)  # 1 Jan 2020 is a Wednesday
    assert round10.known_session(datetime(2020, 1, 2, 17, 59), s) == 1
    assert round10.known_session(datetime(2020, 1, 2, 18, 0), s) == 1
    assert round10.known_session(datetime(2020, 1, 2, 18, 1), s) == 2  # after the run: the next session
    assert round10.known_session(datetime(2020, 1, 4, 10, 0), s) == 3  # a Saturday: Monday's decision


def test_the_latest_notice_wins_so_a_reschedule_moves_the_meeting():
    ks = np.array([3, 5, 5])
    meetings = np.array([date(2020, 1, 20), date(2020, 1, 22), date(2020, 1, 24)], dtype=object)
    assert round10.latest_meeting((ks, meetings), 2) is None
    assert round10.latest_meeting((ks, meetings), 4) == date(2020, 1, 20)
    assert round10.latest_meeting((ks, meetings), 5) == date(2020, 1, 24)  # same session: the later meeting


def test_reaction_events_are_abnormal_to_the_universe_and_drop_rescheduled_meetings():
    s = _sessions(60)
    flat = [100.0] * 60
    jump = [100.0] * 60
    for j in range(20, 60):
        jump[j] = 110.0  # +10% from m-1 (19) to m+1 (21) when m = 20
    secs = {"A": _security("A", jump), "B": _security("B", flat), "C": _security("C", flat), "D": _security("D", jump)}
    universe = _universe(["A", "B", "C", "D"])
    notices = {"A": (np.array([10]), np.array([s[20]], dtype=object)),
               "D": (np.array([10, 21]), np.array([s[20], s[40]], dtype=object))}  # D moved its meeting on m+1
    events = round10.reaction_events(notices, s, secs, universe)
    a = events[events["sid"] == "A"].iloc[0]
    assert (a["m"], a["signal"], a["tier"]) == (20, 21, "N1")
    assert a["reaction"] == pytest.approx(0.10) and a["abnormal"] == pytest.approx(0.10 - 0.05)  # mean of A,B,C,D
    assert list(events[events["sid"] == "D"]["m"]) == [40]  # the 20th meeting was superseded by m+1


def test_the_threshold_uses_only_earlier_events_and_needs_300():
    rows = [{"sid": f"S{j}", "signal": sig, "abnormal": 0.01 * (j % 10)} for sig in range(300) for j in range(2)]
    rows.append({"sid": "X", "signal": 300, "abnormal": 0.5})
    rows.append({"sid": "Y", "signal": 300, "abnormal": 0.0})
    events = round10.flag_signals(pd.DataFrame(rows))
    early = events[events["signal"] < 150]
    assert early["threshold"].isna().all() and not early["is_signal"].any()  # fewer than 300 earlier events
    x = events[events["sid"] == "X"].iloc[0]
    prior = [r["abnormal"] for r in rows if 50 <= r["signal"] < 300]
    assert x["threshold"] == pytest.approx(np.percentile(prior, 90)) and x["is_signal"]
    assert not events[events["sid"] == "Y"].iloc[0]["is_signal"]
    # an event on the same session never enters another's threshold
    assert events[events["sid"] == "Y"].iloc[0]["threshold"] == pytest.approx(x["threshold"])


def test_promoter_purchases_filter_category_mode_side_security_and_value():
    base = {"personCategory": "Promoters", "acqMode": "Market Purchase", "tdpTransactionType": "Buy",
            "secType": "Equity Shares", "secVal": "1500000", "date": "15-Mar-2017 18:37", "symbol": "ABC"}
    variants = [{}, {"personCategory": "Promoter Group"}, {"personCategory": "Director"}, {"acqMode": "Off Market"},
                {"tdpTransactionType": "Sell"}, {"secType": "Warrants"}, {"secVal": "999999"}, {"secType": "EQUITY"}]
    pit = pd.DataFrame([{**base, **v, "symbol": f"S{j}"} for j, v in enumerate(variants)])
    kept = round10.promoter_purchases(pit)
    assert sorted(kept["sid"]) == ["S0", "S1", "S7"]
    assert kept["ts"].iloc[0] == pd.Timestamp(2017, 3, 15, 18, 37)


def _cands(rows):
    return pd.DataFrame(rows, columns=["part", "sid", "entry", "i_me", "tier", "priority", "order", "strength"])


def test_the_account_holds_five_frees_places_correctly_and_drops_the_rest():
    s = _sessions(160)
    names = [f"S{j}" for j in range(8)]
    secs = {x: _security(x, [100.0] * 160) for x in names}
    lows = [100.0] * 160
    lows[13] = 80.0  # S0 is stopped on session 13
    secs["S0"] = _security("S0", [100.0] * 160, lows=lows)
    universe = _universe(names)
    rows = [("E2", f"S{j}", 10, 0, "N1", 0, -0.1 * (6 - j), 0.1 * (6 - j)) for j in range(6)]  # S0 strongest ... S5
    rows += [("Q", "S6", 13, 0, "N1", 1, "a", np.nan), ("Q", "S7", 14, 0, "N1", 1, "b", np.nan)]
    trades = round10.run_account(_cands(rows), secs, s, (s[0], s[-1]))
    assert list(trades["ticker"]) == ["S0", "S1", "S2", "S3", "S4", "S7"]  # S5 dropped (full); S6 too early
    s0 = trades[trades["ticker"] == "S0"].iloc[0]
    assert s0["reason"] == "stop" and s0["exit_i"] == 13 and s0["gross"] == pytest.approx(-0.15)
    assert s0["net"] == pytest.approx(-0.15 - round10.ROUND_TRIP["N1"] - round8.SLIPPAGE["N1"])
    assert s0["R"] == pytest.approx(s0["net"] / 0.15)
    s7 = trades[trades["ticker"] == "S7"].iloc[0]
    assert s7["entry_i"] == 14 and s7["exit_i"] == 54 and s7["net"] == pytest.approx(-round10.ROUND_TRIP["N1"])
    every = round10.run_account(_cands(rows), secs, s, (s[0], s[-1]), cap=None)
    assert len(every) == 8  # no cap: every candidate


def test_an_exit_at_an_open_frees_its_place_for_an_entry_at_that_same_open():
    s = _sessions(160)
    names = [f"S{j}" for j in range(6)]
    secs = {x: _security(x, [100.0] * 160) for x in names}
    rows = [("E2", f"S{j}", 10, 0, "N1", 0, float(j), 0.0) for j in range(5)]
    rows += [("Q", "S5", 50, 0, "N1", 1, "x", np.nan)]  # the five exit at the open of session 50
    trades = round10.run_account(_cands(rows), secs, s, (s[0], s[-1]))
    assert "S5" in set(trades["ticker"])


def test_the_mix_takes_e2_first_then_q_in_hash_order_and_one_position_per_stock():
    s = _sessions(160)
    names = [f"S{j}" for j in range(8)]
    secs = {x: _security(x, [100.0] * 160) for x in names}
    rows = [("Q", "S5", 10, 0, "N1", 1, "0", np.nan), ("Q", "S6", 10, 0, "N1", 1, "f", np.nan),
            ("E2", "S0", 10, 0, "N1", 0, -0.2, 0.2), ("E2", "S1", 10, 0, "N1", 0, -0.3, 0.3),
            ("E2", "S2", 10, 0, "N1", 0, -0.1, 0.1), ("E2", "S3", 10, 0, "N1", 0, -0.05, 0.05),
            ("Q", "S0", 11, 0, "N1", 1, "1", np.nan)]  # S0 already held
    trades = round10.run_account(_cands(rows), secs, s, (s[0], s[-1]))
    assert list(trades["ticker"]) == ["S1", "S0", "S2", "S3", "S5"]  # E2 strongest first, then Q's lowest hash
    assert list(trades["part"]) == ["E2", "E2", "E2", "E2", "Q"]


def test_q_candidates_are_one_per_stock_and_session_in_the_universe_with_a_hash_order():
    s = _sessions(30)
    secs = {"A": _security("A", [100.0] * 30), "B": _security("B", [100.0] * 30)}
    universe = _universe(["A"])
    purchases = pd.DataFrame({"sid": ["A", "A", "B", "Z"],
                              "ts": pd.to_datetime(["2020-01-02 10:00", "2020-01-02 12:00", "2020-01-02 10:00", "2020-01-02 10:00"])})
    q = round10.q_candidates(purchases, s, secs, universe)
    assert list(q["sid"]) == ["A"] and list(q["entry"]) == [2]
    import hashlib
    assert q["order"].iat[0] == hashlib.sha256(f"A|{s[2]}".encode()).hexdigest()


def test_the_baseline_draws_the_same_number_from_the_same_pool():
    trades = pd.DataFrame({"i_me": [0, 0, 0], "tier": ["N1", "N1", "N2"], "entry_i": [5, 5, 5], "net": [0.02, 0.02, 0.02]})
    pools = {(0, "N1", 5): np.array([0.02, 0.02, 0.02]), (0, "N2", 5): np.array([0.02])}
    mean, p = round10.baseline(trades, pools, draws=200)
    assert mean == pytest.approx(0.02) and p == 1.0  # every draw ties the observed mean
    pools = {(0, "N1", 5): np.array([0.0, -0.01, 0.01]), (0, "N2", 5): np.array([0.0])}
    mean, p = round10.baseline(trades, pools, draws=200)
    assert p == pytest.approx(1 / 201)  # no draw reaches +2%
    assert mean == pytest.approx(0.0, abs=0.01)


def test_criteria_use_entry_months_and_the_bar_of_0_05_over_57():
    rng = np.random.default_rng(0)
    entries = [date(2018, 1, 1) + timedelta(days=int(d)) for d in sorted(rng.integers(0, 3000, 120))]
    net = rng.normal(0.02, 0.05, 120)
    trades = pd.DataFrame({"net": net, "gross": net + 0.004, "cost": 0.004, "R": net / 0.15, "ticker": [f"S{j % 30}" for j in range(120)],
                           "signal_date": entries, "signal_i": [d.year * 12 + d.month for d in entries],
                           "exit_date": [d + timedelta(days=60) for d in entries], "stopped": False, "gapped": False})
    checks, stats = round10.criteria(trades, (date(2018, 1, 1), date(2026, 3, 31)), 0.0001, 0.0005)
    c11 = next(c for c in checks if c.number == 11)
    c12 = next(c for c in checks if c.number == 12)
    assert "entry months" in c11.criterion
    assert "0.05/57" in c12.criterion and c12.passed
    _, _ = round10.criteria(trades, (date(2018, 1, 1), date(2026, 3, 31)), 0.0001, 0.0009)
    assert not next(c for c in round10.criteria(trades, (date(2018, 1, 1), date(2026, 3, 31)), 0.0001, 0.0009)[0]
                    if c.number == 12).passed


def test_round10_preregistration_matches_its_pin():
    assert round10.check_preregistration() == round10.PREREGISTRATION_SHA256
