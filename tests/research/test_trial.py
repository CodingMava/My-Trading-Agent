"""Paper trial 1 on synthetic data only: E2 (3 places) and V2 (2 places) in one account, one position per stock, V2's
picks that can't be bought, decisions recorded once, the kill switch and the decay rule, and labelled messages."""
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from trader.research import forward2, round8, round10, trial

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 2, 20, 0, tzinfo=IST)


def _sessions(n=160, start=date(2026, 10, 1)):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _security(sid, n, closes=None, lows=None, locked=()):
    closes = np.full(n, 100.0) if closes is None else np.asarray(closes, float)
    lows = closes.copy() if lows is None else np.asarray(lows, float)
    opens, highs, prev = closes.copy(), closes.copy(), np.r_[np.nan, closes[:-1]]
    highs = np.maximum(highs, opens)
    for j in locked:  # locked at the upper band all day: open = high = low = close, above the previous close
        prev[j] = 90.0
    present = np.ones(n, bool)
    return round8.Security(sid=sid, present=present, eq=present.copy(), raw_close=closes, raw_open=opens, raw_high=highs,
                           raw_low=lows, raw_prev=prev, value=np.full(n, 1e8), adj_open=opens.copy(), adj_low=lows.copy(),
                           adj_close=closes.copy(), last_row=np.arange(n))


def _cut(s, n):
    c = lambda a: a[:n]
    return replace(s, present=c(s.present), eq=c(s.eq), raw_close=c(s.raw_close), raw_open=c(s.raw_open), raw_high=c(s.raw_high),
                   raw_low=c(s.raw_low), raw_prev=c(s.raw_prev), value=c(s.value), adj_open=c(s.adj_open), adj_low=c(s.adj_low),
                   adj_close=c(s.adj_close), last_row=c(s.last_row))

def _market(n=160, **special):
    sessions = _sessions(n)
    secs = {s: special.get(s) or _security(s, n) for s in "ABCDEFGHIJ"}
    return sessions, secs


def _e2(rows):
    return pd.DataFrame([{"sid": s, "m": i - 1, "signal": i, "i_me": 0, "tier": "N1", "reaction": a, "abnormal": a,
                          "threshold": 0.05, "is_signal": True} for s, i, a in rows])


def _v2(sessions, month_end, names):
    i = sessions.index(month_end)
    return {i: pd.DataFrame({"sid": list(names), "score_V": np.linspace(2, 1, len(names))})}


def test_the_ledger_is_append_only(tmp_path):
    ledger = trial.Ledger(tmp_path / "t.db")
    ledger.add_run(NOW, "ok", "x")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("UPDATE runs SET status = 'x'")
    ledger.close()


def test_e2_takes_three_places_v2_two_and_one_position_per_stock():
    sessions, secs = _market()
    oct30 = date(2026, 10, 30)
    e2 = _e2([("A", 10, 0.30), ("B", 10, 0.25), ("C", 10, 0.20), ("D", 10, 0.15)])  # entry session 11
    v2 = _v2(sessions, oct30, ["A", "E", "F", "G"])
    ledger = trial.Ledger(":memory:")
    events = trial.update(ledger, sessions, secs, e2, v2, NOW)
    status = {(p, s): st for p, s, _, st in events["entries"]}
    assert status[("E2", "A")] == status[("E2", "B")] == status[("E2", "C")] == "bought"
    assert status[("E2", "D")] == "no free place"
    assert status[("V2", "A")] == "already held" and status[("V2", "E")] == status[("V2", "F")] == "bought"
    assert ("V2", "G") not in status  # V2's two places were used before G
    again = trial.update(ledger, sessions, secs, e2, v2, NOW)
    assert again["entries"] == [] and again["signals"] == []  # decided once
    closed = ledger.table("trades")
    v2_trades = closed[closed["part"] == "V2"]
    nov_end = max(d for d in sessions if d.month == 11)
    assert set(v2_trades["exit_date"]) == {sessions[sessions.index(nov_end) + 1].isoformat()}  # the open after November's end
    assert v2_trades["r"].tolist() == pytest.approx((v2_trades["net"] / 0.10).tolist())
    e2_trades = closed[closed["part"] == "E2"]
    assert set(e2_trades["exit_date"]) == {sessions[11 + 40].isoformat()}


def test_a_v2_pick_that_cannot_be_bought_keeps_its_place_in_cash_for_the_month():
    sessions = _sessions()
    oct30 = date(2026, 10, 30)
    entry = sessions.index(oct30) + 1
    secs = {s: _security(s, len(sessions)) for s in "ABCDEFGHIJ"}
    secs["E"] = _security("E", len(sessions), locked=(entry,))
    ledger = trial.Ledger(":memory:")
    events = trial.update(ledger, sessions, secs, _e2([]), _v2(sessions, oct30, ["E", "F", "G"]), NOW)
    status = {s: st for p, s, _, st in events["entries"]}
    assert status == {"E": "not bought", "F": "bought"}  # G isn't reached: E's place stays in cash


def test_a_stop_frees_its_place_from_the_next_session():
    sessions = _sessions()
    lows = np.full(len(sessions), 100.0)
    lows[13] = 80.0
    secs = {s: _security(s, len(sessions)) for s in "ABCDEFGHIJ"}
    secs["A"] = _security("A", len(sessions), lows=lows)
    e2 = _e2([("A", 10, 0.3), ("B", 10, 0.25), ("C", 10, 0.2), ("D", 12, 0.5), ("E", 13, 0.5)])
    ledger = trial.Ledger(":memory:")
    events = trial.update(ledger, sessions, secs, e2, {}, NOW)
    status = {s: st for _, s, _, st in events["entries"]}
    assert status["D"] == "no free place" and status["E"] == "bought"  # A stopped on 13 frees a place from 14
    a = ledger.table("trades").set_index("sid").loc["A"]
    assert a["outcome"] == "stop" and a["r"] == pytest.approx(a["net"] / 0.15)


def test_the_kill_switch_blocks_new_entries_after_a_20r_drawdown():
    trades = pd.DataFrame({"id": range(1, 32), "part": "E2", "exit_date": [f"2027-01-{d:02d}" for d in range(1, 32)],
                           "r": [-1.0] * 21 + [0.5] * 10})
    states = trial.brake_states(trades)
    assert states["account"][0] == "kill switch" and states["account"][1] == "2027-01-20"
    assert states["E2"][0] == "stopped"  # its own 20R limit, the gate's decay rule


def test_the_decay_rule_pauses_a_part_that_loses_over_its_last_50_trades():
    r = [0.3, -0.35] * 25  # wins half the time but loses money on average
    trades = pd.DataFrame({"id": range(1, 51), "part": "V2", "exit_date": [f"2027-{1 + j // 28:02d}-{1 + j % 28:02d}" for j in range(50)],
                           "r": r})
    states = trial.brake_states(trades)
    assert states["V2"][0] == "paused" and "account" not in states


def test_messages_are_labelled_paper_trial():
    events = {"signals": [("E2", "ABC", date(2026, 11, 2), 0.08, False)], "entries": [("E2", "ABC", date(2026, 11, 3), "bought")],
              "closed": [], "brakes": [("account", "kill switch", "2027-01-20", "x")]}
    notes = trial.messages(events, pd.DataFrame(columns=["exit_date", "r"]), date(2026, 11, 2))
    assert len(notes) == 3 and all("PAPER TRIAL 1" in text and "paper only" in text for _, text in notes)


def test_trial_definition_matches_its_pin():
    assert trial.check_definition() == trial.DEFINITION_SHA256



def test_forward_test_4_pools_are_recorded_once_closed_and_the_look_applies_the_criteria():
    sessions = _sessions()
    secs = {s: _security(s, len(sessions)) for s in "ABCDEFGHIJ"}
    oct30 = sessions.index(date(2026, 10, 30))
    table = pd.DataFrame({"i": oct30, "sid": list("ABCDEFGHIJ"), "rank": [1, 2, 3, 4, 5, 101, 102, 103, 104, 105]})
    universe = round10.Universe(table)
    e2 = _e2([("A", oct30 + 4, 0.3)])  # an E2 signal after October's month-end, entry the next session
    v2 = _v2(sessions, date(2026, 10, 30), ["F", "G"])
    ledger = trial.Ledger(":memory:")
    early = {}
    trial.update(ledger, sessions[:oct30 + 10], {k: _cut(s, oct30 + 10) for k, s in secs.items()}, e2, v2, NOW)
    trial.record_pools(ledger, sessions[:oct30 + 10], {k: _cut(s, oct30 + 10) for k, s in secs.items()}, universe, NOW, early)
    assert early.get("pools", []) == [] and ledger.table("pools").empty  # nothing has closed yet
    events = {}
    trial.update(ledger, sessions, secs, e2, v2, NOW)
    trial.record_pools(ledger, sessions, secs, universe, NOW, events)
    pools = ledger.table("pools")
    assert sorted(zip(pools["part"], pools["tier"])) == [("E2", "N1"), ("V2", "N2")]
    assert all(len(__import__("json").loads(p)) == 5 for p in pools["pool"])  # every enterable member of the tier
    trial.record_pools(ledger, sessions, secs, universe, NOW, {})
    assert len(ledger.table("pools")) == 2  # once each
    r = trial.judge(ledger, date(2027, 6, 1))
    assert r["decision"] == "INFORMATIONAL" and r["covered"] == len(r["trades"]) == 3
    assert {c.number for c in r["checks"]} == set(range(1, 12)) | {13}
    assert trial.judge(ledger, date(2028, 1, 5))["look"] == 1


def test_forward_4_preregistration_matches_its_pin():
    assert trial.check_forward4() == trial.FORWARD4_SHA256
