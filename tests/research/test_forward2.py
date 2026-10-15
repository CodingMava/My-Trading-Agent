"""Forward test 2 on synthetic data only: the paper ledger, month-ends, positions, the evening update, the decision
rules and the downloader. No network (tests/conftest.py blocks it)."""
import io
import json
import sqlite3
import zipfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
import requests

from trader.markets.calendar import CalendarCoverageError
from trader.research import forward2 as f2
from trader.research import round8

IST = ZoneInfo("Asia/Kolkata")


def _security(sid, closes, opens=None, lows=None, present=None):
    n = len(closes)
    closes = np.asarray(closes, float)
    opens = np.asarray(opens if opens is not None else closes, float)
    lows = np.asarray(lows if lows is not None else np.minimum(opens, closes) * 0.995, float)
    present = np.asarray(present if present is not None else [True] * n)
    closes, opens, lows = (np.where(present, a, np.nan) for a in (closes, opens, lows))
    last = np.maximum.accumulate(np.where(present, np.arange(n), -1))
    return round8.Security(sid=sid, present=present, eq=present.copy(), raw_close=closes, raw_open=opens,
                           raw_high=np.fmax(opens, closes) * 1.005, raw_low=lows, raw_prev=np.r_[np.nan, closes[:-1]],
                           value=np.where(present, 1e8, 0.0), adj_open=opens.copy(), adj_low=lows.copy(),
                           adj_close=closes.copy(), last_row=last)


class Calendar:
    """A stand-in for the NSE calendar: the next trading day is the next weekday; nothing beyond `covered`."""

    def __init__(self, covered=date(2026, 12, 31)):
        self.covered = covered

    def next_trading_day(self, day):
        nxt = day + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        if nxt > self.covered:
            raise CalendarCoverageError(str(nxt))
        return nxt


# --------------------------------------------------------------------------------------------- the ledger
def test_the_ledger_refuses_changes(tmp_path):
    ledger = f2.Ledger(tmp_path / "f2.db")
    ledger.add_picks(date(2026, 10, 30), [{"sid": "AAA", "score": 1.2, "tier_rank": 3}], datetime(2026, 10, 30, 20, tzinfo=IST))
    for statement in ("UPDATE picks SET sid = 'BBB'", "DELETE FROM picks"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger.conn.execute(statement)
    with pytest.raises(sqlite3.IntegrityError):  # a month's picks are written once
        ledger.add_picks(date(2026, 10, 30), [{"sid": "AAA", "score": 1.0, "tier_rank": 3}], datetime(2026, 10, 31, tzinfo=IST))
    assert ledger.picks_for(date(2026, 10, 30)) == ["AAA"]
    ledger.add_notice("picks 2026-10-30", datetime(2026, 10, 30, 20, tzinfo=IST), sent=False)
    assert not ledger.sent("picks 2026-10-30")
    ledger.add_notice("picks 2026-10-30", datetime(2026, 10, 31, 20, tzinfo=IST), sent=True)
    assert ledger.sent("picks 2026-10-30")


def test_a_month_end_is_known_from_the_data_or_the_calendar():
    days = [date(2026, 10, 29), date(2026, 10, 30)]
    assert f2.month_ends_known(days, Calendar()) == [1]  # Friday 30 Oct: the next trading day is in November
    assert f2.month_ends_known([date(2026, 10, 28), date(2026, 10, 29)], Calendar()) == []  # 30 Oct is still to come
    assert f2.month_ends_known(days + [date(2026, 11, 2)], Calendar()) == [1]  # November's first session is in
    december = [date(2026, 12, 30), date(2026, 12, 31)]
    assert f2.month_ends_known(december, Calendar(covered=date(2026, 12, 31))) == []  # 2027 unknown: wait for the data


# ------------------------------------------------------------------------------------------------- positions
def test_every_way_a_paper_position_can_end():
    sec = _security("AAA", [100, 100, 101, 102, 104, 106], opens=[100, 100, 100.5, 101, 103, 105])
    assert f2.trade(sec, 6, 8, 6)["outcome"] == "pending"
    assert f2.trade(sec, 1, 10, 6) | {"mark": None} == {"entry_i": 1, "entry_raw": 100.0, "outcome": "open", "mark": None,
                                                        "stop_raw": 90.0}
    t = f2.trade(sec, 1, 4, 6)
    assert (t["outcome"], t["exit_i"], round(t["gross"], 4), t["exit_raw"]) == ("time", 4, 0.03, 103.0)
    stopped = _security("BBB", [100, 100, 92, 88], opens=[100, 100, 95, 85], lows=[99, 99, 89, 84])
    t = f2.trade(stopped, 1, 3, 4)
    assert t["outcome"] == "stop" and t["gross"] == pytest.approx(-0.10) and not t["gapped"]
    locked = _security("CCC", [100, 105])
    locked.raw_open[1] = locked.raw_high[1] = locked.raw_low[1] = locked.raw_close[1] = 105.0
    assert f2.trade(locked, 1, 3, 2)["outcome"] == "not bought"
    present = [True] * 3 + [False] * 31  # no row from its exit date on
    suspended = _security("DDD", [100.0] * 34, present=present)
    assert f2.trade(suspended, 1, 3, 10)["outcome"] == "open"  # waiting for its next session with a row
    t = f2.trade(suspended, 1, 3, 34)  # 20 sessions on: closed at its last close
    assert t["outcome"] == "no further rows" and t["exit_i"] == 2


def test_costs_follow_round_8():
    net, cost = f2.net_of_costs({"gross": 0.05, "outcome": "time"})
    assert cost == pytest.approx(round8.ROUND_TRIP["N2"]) and net == pytest.approx(0.05 - cost)
    _, stop_cost = f2.net_of_costs({"gross": -0.10, "outcome": "stop"})
    assert stop_cost == pytest.approx(round8.ROUND_TRIP["N2"] + round8.SLIPPAGE["N2"])


# --------------------------------------------------------------------------------------------- the update
def _world(n_sessions):
    """Sessions from 29 Oct 2026; 12 tier members (liquidity ranks 101-112) with rising prices; picks by score."""
    days, d = [], date(2026, 10, 29)
    while len(days) < n_sessions:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    secs, rows = {}, []
    for k in range(12):
        sid = f"S{k:02d}"
        closes = 100 * (1 + 0.002 * (k + 1)) ** np.arange(n_sessions)
        secs[sid] = _security(sid, closes, opens=np.r_[closes[0], closes[:-1]])
    for i in round8.month_ends(days):
        rows += [{"i": i, "sid": f"S{k:02d}", "liquidity": 1e8 - k, "score_12-1": 0.1 * k, "rank": 101 + k} for k in range(12)]
    return days, secs, pd.DataFrame(rows)


def test_the_evening_update_records_once_and_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(f2, "nse_calendar", lambda: Calendar())
    ledger = f2.Ledger(tmp_path / "f2.db")
    days, secs, table = _world(2)  # 29 and 30 Oct: October's last session is known from the calendar
    events = f2.update(ledger, days, secs, table, datetime(2026, 10, 30, 19, 30, tzinfo=IST))
    assert [s for s, _ in events["picks"]] == [date(2026, 10, 30)]
    assert ledger.picks_for(date(2026, 10, 30)) == ["S11", "S10", "S09", "S08", "S07"]  # the highest scores
    assert len(events["pending"]) == 5 and not events["closed"]
    days, secs, table = _world(10)  # into November: open positions, nothing closed, nothing recorded twice
    events = f2.update(ledger, days, secs, table, datetime(2026, 11, 11, 19, 30, tzinfo=IST))
    assert not events["picks"] and len(events["open"]) == 5 and ledger.table("trades").empty
    days, secs, table = _world(26)  # through 30 Nov and 1 Dec: October's picks exit, November's are chosen
    events = f2.update(ledger, days, secs, table, datetime(2026, 12, 1, 19, 30, tzinfo=IST))
    trades = ledger.table("trades")
    assert len(trades) == 5 and set(trades["outcome"]) == {"time"} and (trades["net"] > 0).all()
    assert [s for s, _ in events["months"]] == [date(2026, 10, 30)]
    assert len(json.loads(ledger.table("months")["pool"].iloc[0])) == 12  # every tier member could be bought
    assert [s for s, _ in events["picks"]] == [date(2026, 11, 30)]
    again = f2.update(ledger, days, secs, table, datetime(2026, 12, 1, 20, 0, tzinfo=IST))
    assert not again["picks"] and not again["closed"] and not again["months"] and len(ledger.table("trades")) == 5
    keys = [k for k, _ in f2.messages(events)]
    assert keys[0] == "picks 2026-11-30" and keys[1].startswith("closed 2026-10-30")


def test_a_rebuild_that_would_pick_differently_keeps_the_original(tmp_path, monkeypatch):
    monkeypatch.setattr(f2, "nse_calendar", lambda: Calendar())
    ledger = f2.Ledger(tmp_path / "f2.db")
    days, secs, table = _world(2)
    f2.update(ledger, days, secs, table, datetime(2026, 10, 30, 19, 30, tzinfo=IST))
    revised = table.assign(**{"score_12-1": -table["score_12-1"]})  # a corrected file reverses the order
    events = f2.update(ledger, days, secs, revised, datetime(2026, 10, 31, 19, 30, tzinfo=IST))
    assert events["differences"] and ledger.picks_for(date(2026, 10, 30)) == ["S11", "S10", "S09", "S08", "S07"]


# -------------------------------------------------------------------------------------------- the decisions
def _ledger_with(tmp_path, nets, months=24):
    ledger = f2.Ledger(tmp_path / "f2.db")
    at = datetime(2026, 11, 1, tzinfo=IST)
    start = date(2026, 10, 30)
    for m in range(months):
        signal = (pd.Timestamp(2026, 10, 31) + pd.offsets.MonthEnd(m)).date()
        for k in range(5):
            net = nets[(m * 5 + k) % len(nets)]
            ledger.add_trade(signal, f"S{k}", {"entry_date": signal + timedelta(days=2), "entry_price": 100.0,
                                               "exit_date": signal + timedelta(days=33), "exit_price": 100 * (1 + net),
                                               "gross": net + 0.0045, "net": net, "cost": 0.0045, "outcome": "time"}, at)
        ledger.add_month(signal, 200, list(np.linspace(-0.05, 0.03, 50)), at)
    return ledger


def test_looks_and_decisions(tmp_path):
    assert f2.look_number(date(2027, 1, 10)) == 0 and f2.look_number(date(2028, 1, 10)) == 1
    assert f2.look_number(date(2036, 1, 10)) == 9 and f2.look_number(date(2028, 6, 1)) == 0
    assert f2.judge(f2.Ledger(tmp_path / "empty.db"), date(2027, 3, 1))["decision"] == "WAITING"
    losing = _ledger_with(tmp_path / "a", [-0.02, 0.01, -0.03, 0.02])
    r = f2.judge(losing, date(2029, 1, 15))  # look 2: forward expectancy below zero
    assert r["look"] == 2 and r["decision"] == "REJECTED" and 12 not in [c.number for c in r["checks"]]
    winning = _ledger_with(tmp_path / "b", [0.06, 0.05, -0.02, 0.07, 0.04])
    r = f2.judge(winning, date(2028, 1, 15))
    assert r["decision"] in ("PAPER", "CONTINUE")
    assert next(c for c in r["checks"] if c.number == 5).criterion.endswith("0.05/1 = 0.0500")
    assert f2.judge(winning, date(2028, 6, 1))["decision"] == "INFORMATIONAL"


def test_a_drawdown_beyond_20r_rejects_at_any_update(tmp_path):
    crash = _ledger_with(tmp_path, [-0.105], months=6)  # 30 straight losses of about 1R
    r = f2.judge(crash, date(2027, 5, 1))
    assert r["stats"]["max_drawdown_r"] > 20 and r["decision"] == "REJECTED"


# ------------------------------------------------------------------------------------------------ downloads
def _bhavcopy_zip(day):
    header = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,"
              "OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,"
              "ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n")
    row = f"{day},{day},CM,NSE,STK,1,INE002A01018,RELIANCE,EQ,,,,,REL,100,101,99,100.5,100.5,100,,100.5,,,10,1005,5,F1,1,,,,,\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("x.csv", header + row)
    return buffer.getvalue()


class FakeNSE:
    def __init__(self, sessions):
        self.sessions, self.calls = set(sessions), []

    def get(self, url, headers=None, timeout=None):
        self.calls.append(url)
        if "BhavCopy" in url:
            day = datetime.strptime(url.split("_")[6], "%Y%m%d").date()
            if day in self.sessions:
                return type("R", (), {"status_code": 200, "content": _bhavcopy_zip(day.isoformat()), "raise_for_status": lambda s: None})()
            return type("R", (), {"status_code": 404, "content": b"", "raise_for_status": lambda s: None})()
        if "symbolchange" in url:
            body = b"NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\nX Ltd,OLDX,NEWX,01-JAN-2020\n"
            return type("R", (), {"status_code": 200, "content": body, "raise_for_status": lambda s: None})()
        raise requests.ConnectionError(url)


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return type("R", (), {"json": lambda s: [{"symbol": "X", "exDate": "05-Nov-2026", "subject": "Bonus 1:1"}],
                              "raise_for_status": lambda s: None})()


def test_collecting_asks_every_day_since_the_last_file_and_keeps_only_sessions(tmp_path):
    nse = FakeNSE({date(2026, 10, 14), date(2026, 10, 15), date(2026, 10, 19)})
    session = FakeSession()
    got = f2.collect(datetime(2026, 10, 19, 18, 0, tzinfo=IST), nse, tmp_path / "raw", tmp_path / "ca", tmp_path / "sc.csv",
                     have_through=date(2026, 10, 13), session=session)
    assert got["saved"] == [date(2026, 10, 14), date(2026, 10, 15)]  # 19 Oct's file is asked for only from 19:00
    assert got["absent"] == [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18)]
    assert sorted(p.name for p in (tmp_path / "raw" / "2026").iterdir()) == [
        "BhavCopy_NSE_CM_0_0_0_20261014_F_0000.csv.zip", "BhavCopy_NSE_CM_0_0_0_20261015_F_0000.csv.zip"]
    assert got["corporate_actions"] == {"2026-09": 1, "2026-10": 1} and got["symbol_changes"]
    assert sorted(p.name for p in (tmp_path / "ca").iterdir()) == ["2026-09.json", "2026-10.json"]
    later = f2.collect(datetime(2026, 10, 19, 19, 30, tzinfo=IST), nse, tmp_path / "raw", tmp_path / "ca",
                       tmp_path / "sc.csv", have_through=date(2026, 10, 15), session=session)
    assert later["saved"] == [date(2026, 10, 19)] and not later["symbol_changes"]  # refreshed within the week


def test_a_file_that_cannot_be_read_is_not_kept(tmp_path):
    class Garbled(FakeNSE):
        def get(self, url, headers=None, timeout=None):
            return type("R", (), {"status_code": 200, "content": b"PK not really a zip", "raise_for_status": lambda s: None})()

    with pytest.raises(Exception):
        f2.nb.fetch_bhavcopy(date(2026, 10, 14), tmp_path, Garbled(set()))
    assert not any(tmp_path.rglob("*.zip"))


def test_the_preregistration_is_pinned():
    assert f2.check_preregistration() == f2.PREREGISTRATION_SHA256
