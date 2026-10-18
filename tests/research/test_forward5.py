"""Forward test 5 on synthetic data only: the short NIFTY futures hedge (entry, rolls, exits, missing prices), both F&O file
formats, hedged trades recorded once from the trial's ledger, the looks, and the append-only ledger."""
import io
import sqlite3
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trader.research import forward5

NOW = datetime(2026, 11, 30, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def _fut(rows):
    return pd.DataFrame(rows, columns=["date", "expiry", "open", "high", "low", "close", "settle"])


FUT = _fut([
    ("2026-10-22", "2026-10-27", 100.0, 101, 99, 100.5, 100.5), ("2026-10-22", "2026-11-24", 101.0, 102, 100, 101.5, 101.5),
    ("2026-10-27", "2026-10-27", 98.0, 99, 97, 98.0, 97.0), ("2026-10-27", "2026-11-24", 98.5, 99, 97, 98.0, 98.0),
    ("2026-11-02", "2026-11-24", 96.0, 97, 95, 95.5, 95.5),
    ("2026-10-23", "2026-10-27", 99.0, 100, 98, 99.5, 99.5), ("2026-10-23", "2026-11-24", 100.0, 101, 99, 100.0, 100.0),
])


def test_a_hedge_without_a_roll():
    h, legs = forward5.hedge_return(FUT, date(2026, 10, 22), date(2026, 10, 23), at_close=False)
    assert legs == 1 and h == pytest.approx((100.0 - 99.0) / 100.0)  # short from 100 at the open, out at 99 at the open
    h, _ = forward5.hedge_return(FUT, date(2026, 10, 22), date(2026, 10, 23), at_close=True)
    assert h == pytest.approx((100.0 - 99.5) / 100.0)  # a stop's hedge leaves at the close


def test_a_hedge_rolls_at_expiry_settlement_into_the_next_month():
    h, legs = forward5.hedge_return(FUT, date(2026, 10, 22), date(2026, 11, 2), at_close=False)
    # leg 1: 100 (Oct contract, open 22 Oct) -> 97 (its settlement on 27 Oct); leg 2: 98 (Nov contract, close 27 Oct) -> 96
    assert legs == 2 and h == pytest.approx(((100 - 97) + (98 - 96)) / 100)


def test_a_missing_price_means_wait():
    assert forward5.hedge_return(FUT, date(2026, 10, 22), date(2026, 11, 5), at_close=False) is None
    assert forward5.hedge_return(FUT[FUT["date"] != "2026-10-27"], date(2026, 10, 22), date(2026, 11, 2), False) is None


def test_hedged_trade_arithmetic():
    row = forward5.hedged_row("E2", "ABC", "2026-10-21", "N1", "2026-10-22", "2026-11-02", "time", 0, 0.05, 0.004, 0.03, 2)
    assert row["hedge_cost"] == pytest.approx(0.0024) and row["gross"] == pytest.approx(0.08)
    assert row["net"] == pytest.approx(0.08 - 0.004 - 0.0024) and row["r"] == pytest.approx(row["net"] / 0.15)


def _zip(text, name="x.csv"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def test_nifty_futures_are_read_from_both_file_formats(tmp_path):
    old = ("INSTRUMENT,SYMBOL,EXPIRY_DT,STRIKE_PR,OPTION_TYP,OPEN,HIGH,LOW,CLOSE,SETTLE_PR,CONTRACTS,VAL_INLAKH,OPEN_INT,CHG_IN_OI,TIMESTAMP\n"
           "FUTIDX,NIFTY,26-Feb-2015,0,XX,9005,9010,8800,8872.65,8872.65,1,1,1,1,30-JAN-2015\n"
           "FUTIDX,BANKNIFTY,26-Feb-2015,0,XX,1,1,1,1,1,1,1,1,1,30-JAN-2015\n"
           "FUTSTK,NIFTY,26-Feb-2015,0,XX,1,1,1,1,1,1,1,1,1,30-JAN-2015\n")
    new = ("TradDt,FinInstrmTp,TckrSymb,XpryDt,OpnPric,HghPric,LwPric,ClsPric,SttlmPric\n"
           "2026-09-30,IDF,NIFTY,2026-10-27,22839.9,22900,22600,22707.3,22707.3\n"
           "2026-09-30,STF,NIFTY,2026-10-27,1,1,1,1,1\n")
    (tmp_path / "old.zip").write_bytes(_zip(old))
    (tmp_path / "new.zip").write_bytes(_zip(new))
    a, b = forward5.nifty_futures(tmp_path / "old.zip"), forward5.nifty_futures(tmp_path / "new.zip")
    assert [(r["date"], r["expiry"], r["open"]) for r in a] == [("2015-01-30", "2015-02-26", 9005)]
    assert [(r["date"], r["expiry"], r["settle"]) for r in b] == [("2026-09-30", "2026-10-27", 22707.3)]


def test_each_closed_trial_trade_is_hedged_once_and_waits_for_prices():
    ledger = forward5.Ledger(":memory:")
    ledger.add_futures(FUT.to_dict("records"), NOW)
    trades = pd.DataFrame([
        {"part": "E2", "sid": "A", "signal_date": "2026-10-21", "tier": "N1", "entry_date": "2026-10-22", "exit_date": "2026-11-02",
         "outcome": "time", "gapped": 0, "gross": 0.05, "cost": 0.004},
        {"part": "V2", "sid": "B", "signal_date": "2026-10-21", "tier": "N2", "entry_date": "2026-10-22", "exit_date": "2026-11-05",
         "outcome": "time", "gapped": 0, "gross": 0.02, "cost": 0.005},  # its exit's futures prices aren't in yet
        {"part": "E2", "sid": "C", "signal_date": "2026-10-15", "tier": "N1", "entry_date": "2026-10-16", "exit_date": "2026-10-23",
         "outcome": "time", "gapped": 0, "gross": 0.01, "cost": 0.004},  # before the forward span
    ])
    events = {"hedged": [], "pools": [], "waiting": []}
    forward5.record_hedged(ledger, trades, NOW, events)
    assert [h["sid"] for h in events["hedged"]] == ["A"] and events["waiting"] == [("V2", "B")]
    again = {"hedged": [], "pools": [], "waiting": []}
    forward5.record_hedged(ledger, trades, NOW, again)
    assert again["hedged"] == [] and len(ledger.table("hedged")) == 1
    notes = forward5.messages(events)
    assert len(notes) == 1 and "paper only" in notes[0][1] and "hedged" in notes[0][1]


def test_looks_and_a_20r_drawdown_rejects():
    ledger = forward5.Ledger(":memory:")
    assert forward5.judge(ledger, date(2027, 6, 1))["decision"] == "WAITING"
    for j in range(25):
        d = f"2026-11-{j + 1:02d}"
        ledger.add_hedged(forward5.hedged_row("V2", f"S{j}", d, "N2", d, d, "stop", 0, -0.10, 0.005, -0.0, 1), NOW)
    r = forward5.judge(ledger, date(2027, 6, 1))
    assert r["decision"] == "REJECTED" and r["stats"]["max_drawdown_r"] > 20
    assert 12 not in {c.number for c in r["checks"]} and forward5.judge(ledger, date(2028, 1, 4))["look"] == 1


def test_the_ledger_is_append_only():
    ledger = forward5.Ledger(":memory:")
    ledger.add_run(NOW, "ok", "x")
    with pytest.raises(sqlite3.DatabaseError):
        ledger.conn.execute("UPDATE runs SET status = 'failed'")


def test_forward5_preregistration_matches_its_pin():
    assert forward5.check_preregistration() == forward5.PREREGISTRATION_SHA256
