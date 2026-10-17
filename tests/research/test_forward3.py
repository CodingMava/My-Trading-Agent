"""Forward test 3 on synthetic data only: the append-only ledger, the board-meeting fetch, signals recorded once (and late
ones kept out), entry decisions and exits recorded once as data arrives, the random-pick pools, and the looks."""
import gzip
import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from trader.research import forward3, round8, round10

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 10, 21, 19, 45, tzinfo=IST)


def _sessions(n=160, start=date(2026, 10, 1)):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _security(sid, closes, lows=None):
    closes = np.asarray(closes, float)
    n = len(closes)
    present = np.ones(n, bool)
    lows = closes.copy() if lows is None else np.asarray(lows, float)
    return round8.Security(sid=sid, present=present, eq=present.copy(), raw_close=closes, raw_open=closes.copy(),
                           raw_high=closes.copy(), raw_low=lows, raw_prev=np.r_[np.nan, closes[:-1]],
                           value=np.full(n, 1e8), adj_open=closes.copy(), adj_low=lows.copy(), adj_close=closes.copy(),
                           last_row=np.arange(n))


def _cut(secs, n):
    c = lambda a: a[:n]
    return {k: replace(s, present=c(s.present), eq=c(s.eq), raw_close=c(s.raw_close), raw_open=c(s.raw_open),
                       raw_high=c(s.raw_high), raw_low=c(s.raw_low), raw_prev=c(s.raw_prev), value=c(s.value),
                       adj_open=c(s.adj_open), adj_low=c(s.adj_low), adj_close=c(s.adj_close), last_row=c(s.last_row))
            for k, s in secs.items()}


def _market(n=160):
    sessions = _sessions(n)
    names = [f"S{j}" for j in range(10)]
    secs = {x: _security(x, [100.0] * n) for x in names}
    lows = [100.0] * n
    lows[14] = 80.0
    secs["S1"] = _security("S1", [100.0] * n, lows=lows)  # stopped on session 14
    universe = round10.Universe(pd.DataFrame({"i": 0, "sid": names, "rank": range(1, 11)}))
    return sessions, secs, universe


def _signals(rows):
    """rows: (sid, signal index, abnormal)"""
    return pd.DataFrame([{"sid": s, "m": i - 1, "signal": i, "i_me": 0, "tier": "N1", "reaction": a, "abnormal": a,
                          "threshold": 0.05, "is_signal": True} for s, i, a in rows])


def test_the_ledger_is_append_only(tmp_path):
    ledger = forward3.Ledger(tmp_path / "f3.db")
    ledger.add_run(NOW, "ok", "x")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("UPDATE runs SET status = 'failed'")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("DELETE FROM runs")
    ledger.close()


class _Response:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode()
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _Session:
    def __init__(self, rows):
        self.rows, self.urls = rows, []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return _Response(self.rows)


def test_board_meetings_are_fetched_in_windows_saved_unchanged_and_added_once(tmp_path):
    ledger = forward3.Ledger(":memory:")
    rows = [{"bm_symbol": "ABC", "bm_date": "28-Oct-2026", "bm_purpose": "Financial Results", "bm_timestamp": "20-Oct-2026 17:05:00"},
            {"bm_symbol": "", "bm_date": "28-Oct-2026", "bm_purpose": "x", "bm_timestamp": "20-Oct-2026 17:05:00"}]
    session = _Session(rows)
    got = forward3.fetch_board_meetings(NOW, ledger, session=session, out_dir=tmp_path)
    assert (got["from"], got["to"]) == (date(2026, 10, 1), date(2026, 12, 5))
    assert len(session.urls) == 3 and "from_date=01-10-2026&to_date=31-10-2026" in session.urls[0]
    files = sorted(tmp_path.glob("*.json.gz"))
    assert len(files) == 3 and json.loads(gzip.decompress(files[0].read_bytes())) == rows
    assert got["new"] == 1 and len(ledger.table("board_notices")) == 1  # the record without a symbol is skipped
    again = forward3.fetch_board_meetings(NOW + timedelta(days=30), ledger, session=_Session(rows), out_dir=tmp_path)
    assert again["new"] == 0
    assert again["from"] == date(2026, 10, 1)  # 20 days before the last fetch, after missed days: not later than that


def test_signals_entries_exits_and_pools_are_recorded_once_as_data_arrives():
    sessions, secs, universe = _market()
    ledger = forward3.Ledger(":memory:")
    sig = _signals([(f"S{j}", 10, 0.2 - 0.01 * j) for j in range(6)])  # S0 strongest ... S5 weakest; entry session 11
    early = forward3.update(ledger, sessions[:11], _cut(secs, 11), universe, sig, NOW)  # entry session not in the data
    assert len(early["signals"]) == 6 and early["entries"] == [] and len(early["waiting"]) == 6
    mid = forward3.update(ledger, sessions[:20], _cut(secs, 20), universe, sig, NOW)
    status = {sid: st for sid, _, st, _ in mid["entries"]}
    assert status == {"S0": "bought", "S1": "bought", "S2": "bought", "S3": "bought", "S4": "bought", "S5": "no free place"}
    assert [sid for sid, _, _ in mid["closed"]] == ["S1"]  # stopped on session 14
    s1 = mid["closed"][0][2]
    assert s1["outcome"] == "stop" and s1["gross"] == pytest.approx(-0.15)
    assert s1["net"] == pytest.approx(-0.15 - round10.ROUND_TRIP["N1"] - round8.SLIPPAGE["N1"])
    assert len(mid["open"]) == 4
    full = forward3.update(ledger, sessions, secs, universe, sig, NOW)
    assert full["entries"] == [] and len(full["closed"]) == 4  # decisions are never taken again
    trades = ledger.table("trades")
    assert len(trades) == 5 and set(trades["outcome"]) == {"stop", "time"}
    assert len(ledger.table("decisions")) == 6
    pools = ledger.table("pools")
    assert len(pools) == 1 and len(json.loads(pools["pool"].iat[0])) == 10  # every enterable tier member
    again = forward3.update(ledger, sessions, secs, universe, sig, NOW)
    assert again["signals"] == again["entries"] == again["closed"] == again["pools"] == []


def test_a_stop_frees_its_place_from_the_next_session_and_late_signals_are_not_candidates():
    sessions, secs, universe = _market()
    ledger = forward3.Ledger(":memory:")
    first = _signals([(f"S{j}", 10, 0.2 - 0.01 * j) for j in range(5)])
    forward3.update(ledger, sessions, secs, universe, first, NOW)
    more = pd.concat([first, _signals([("S6", 13, 0.3), ("S7", 14, 0.3), ("S8", 10, 0.5)])], ignore_index=True)
    events = forward3.update(ledger, sessions, secs, universe, more, NOW)
    status = {sid: st for sid, _, st, _ in events["entries"]}
    assert status == {"S6": "no free place", "S7": "bought"}  # S1's stop on 14 frees a place from 15, S7's entry
    assert [s["sid"] for s in events["late"]] == ["S8"]  # its entry session (11) was already decided
    late = ledger.table("signals").set_index("sid").loc["S8"]
    assert late["late"] == 1


def test_differences_are_reported_and_the_ledger_keeps_what_it_recorded():
    sessions, secs, universe = _market()
    ledger = forward3.Ledger(":memory:")
    forward3.update(ledger, sessions, secs, universe, _signals([("S0", 10, 0.2)]), NOW)
    events = forward3.update(ledger, sessions, secs, universe, _signals([("S0", 10, 0.25)]), NOW)
    assert any("abnormal reaction now" in d for d in events["differences"])
    events = forward3.update(ledger, sessions, secs, universe, _signals([("S2", 10, 0.2)]).iloc[0:0], NOW)
    assert any("no longer gives" in d for d in events["differences"])
    assert ledger.table("signals")["abnormal"].tolist() == [0.2]


def test_looks_are_numbered_from_january_2028_and_a_20r_drawdown_rejects():
    assert forward3.look_number(date(2027, 1, 10)) == 0 and forward3.look_number(date(2028, 1, 5)) == 1
    assert forward3.look_number(date(2036, 1, 5)) == 9 and forward3.look_number(date(2028, 2, 1)) == 0
    assert forward3.cutoff(date(2029, 1, 7)) == date(2028, 12, 31)
    ledger = forward3.Ledger(":memory:")
    assert forward3.judge(ledger, date(2027, 6, 1))["decision"] == "WAITING"
    entry = date(2026, 11, 2)
    for j in range(25):
        e = entry + timedelta(days=j)
        t = {"entry_date": e, "entry_price": 100.0, "exit_date": e + timedelta(days=60), "exit_price": 85.0, "gross": -0.15,
             "net": -0.155, "cost": 0.005, "outcome": "stop", "gapped": False}
        ledger.add_trade(f"S{j}", e - timedelta(days=2), "N1", date(2026, 10, 30), t, NOW)
        ledger.add_pool(date(2026, 10, 30), "N1", e, [0.0, 0.01, -0.01], NOW)
    r = forward3.judge(ledger, date(2027, 6, 1))
    assert r["stats"]["max_drawdown_r"] > 20 and r["decision"] == "REJECTED"
    assert 12 not in {c.number for c in r["checks"]}
    assert "0.05/1" in next(c for c in r["checks"] if c.number == 5).criterion


def test_messages_are_labelled_paper_only():
    s = {"sid": "ABC", "signal_date": date(2026, 10, 21), "abnormal": 0.08}
    record = {"net": 0.031, "outcome": "time", "exit_date": date(2026, 12, 18)}
    events = {"signals": [s], "entries": [("ABC", date(2026, 10, 22), "bought", 0.08)],
              "closed": [("ABC", date(2026, 10, 22), record)]}
    notes = forward3.messages(events, date(2026, 10, 21))
    assert len(notes) == 3 and all("paper only" in text for _, text in notes)
    assert "not a trading signal" in notes[0][1]


def test_forward3_preregistration_matches_its_pin():
    assert forward3.check_preregistration() == forward3.PREREGISTRATION_SHA256
