"""The live order management system against an in-memory Kite: at most one order per tag, lost answers
looked up instead of resent, fills recorded once, and holdings reconciled with the account."""
import sqlite3
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from tests.execution.fake_kite import FakeKite
from trader.execution import broker
from trader.execution.kite_orders import KiteOrders
from trader.execution.oms import OMS, LiveStore

IST = ZoneInfo("Asia/Kolkata")
DAY, NEXT = date(2026, 8, 10), date(2026, 8, 11)
ENTRY = broker.entry_order("T1:INFY.NS:2026-08-10:buy", "INFY.NS", 5)


def probe(request):
    """The same request under a throwaway tag: a refused tag is never sent again."""
    return replace(request, tag=request.tag[0] + "0" * 19)


def make(tmp_path):
    kite = FakeKite()
    oms = OMS(LiveStore(tmp_path / "live.db"), KiteOrders("key", "AT", http=kite, sleep=lambda s: None),
              clock=lambda: datetime(2026, 8, 10, 18, 30, tzinfo=IST))
    return kite, oms


def bought(kite, oms, price=100.0):
    """The entry went out last evening and filled at today's open."""
    assert oms.submit(DAY, "T1", ENTRY, stop_distance=0.05, max_hold_days=5) == "SENT"
    kite.new_day()
    kite.fill(kite.by_tag(ENTRY.tag), price)
    return oms.refresh(NEXT)


def test_an_entry_goes_out_once_and_its_fill_becomes_a_holding(tmp_path):
    kite, oms = make(tmp_path)
    assert bought(kite, oms) == ["INFY.NS entry: buy 5 at 100.00"]
    assert oms.submit(DAY, "T1", ENTRY) == "DONE" and len([c for c in kite.calls if c[0] == "POST"]) == 1
    held = oms.store.positions()["INFY.NS"]
    assert (held.quantity, held.entry_price, held.stop_price, held.entry_date, held.max_hold_days) == (5, 100.0, 95.0, NEXT, 5)
    assert oms.reconcile() == [] and oms.refresh(NEXT) == []  # nothing left to follow up
    events = oms.store.table("broker_events")
    assert list(events["status"]) == ["SENDING", "SENT", "DONE"]


def test_a_lost_answer_is_looked_up_not_resent(tmp_path):
    kite, oms = make(tmp_path)
    kite.failures = [("timeout", True)]  # Kite placed it, but the answer never came
    assert oms.submit(DAY, "T1", ENTRY) == "UNKNOWN"
    assert oms.submit(DAY, "T1", ENTRY) == "SENT" and len(kite.orders) == 1  # found by its tag: not placed again
    other = broker.entry_order("T1:TCS.NS:2026-08-10:buy", "TCS.NS", 2)
    kite.failures = [("timeout", False)]  # this one never reached Kite
    assert oms.submit(DAY, "T1", other) == "UNKNOWN"
    assert "Kite has no record of it yet" in oms.refresh(DAY)[0]
    assert oms.submit(DAY, "T1", other) == "SENT" and [o["tag"] for o in kite.orders].count(other.tag) == 1


def test_a_crash_between_sending_and_recording_is_safe(tmp_path):
    kite, oms = make(tmp_path)
    oms.store.record(oms.clock(), DAY, "T1", ENTRY, "SENDING")  # the process died here...
    oms.kite.place_order("amo", ENTRY.params)  # ...after Kite had placed it
    assert oms.submit(DAY, "T1", ENTRY) == "SENT" and len(kite.orders) == 1


def test_refusals_are_final(tmp_path):
    kite, oms = make(tmp_path)
    kite.failures = [("http", 400, "MarginException", False)]
    assert oms.submit(DAY, "T1", ENTRY) == "REJECTED" and oms.submit(DAY, "T1", ENTRY) == "REJECTED"
    assert len(kite.calls) == 1 and "MarginException" in oms.store.order(ENTRY.tag)["detail"]
    invalid = replace(ENTRY, tag="Ezero", params={**ENTRY.params, "tag": "Ezero", "quantity": 0})
    assert oms.submit(DAY, "T1", invalid) == "REJECTED" and len(kite.calls) == 1  # never sent
    assert oms.store.order("Ezero")["detail"].startswith("invalid: quantity 0")


def test_partial_and_missing_fills(tmp_path):
    kite, oms = make(tmp_path)
    oms.submit(DAY, "T1", ENTRY, stop_distance=0.05)
    kite.new_day()
    kite.fill(kite.by_tag(ENTRY.tag), 100.0, quantity=3, then="CANCELLED")
    assert oms.refresh(NEXT) == ["INFY.NS entry: buy 3 at 100.00 (only 3 of 5 filled)"]
    assert oms.store.positions()["INFY.NS"].quantity == 3
    other = broker.entry_order("T1:TCS.NS:2026-08-10:buy", "TCS.NS", 2)
    oms.submit(DAY, "T1", other)
    kite.reject(kite.by_tag(other.tag), "RMS: insufficient funds")
    assert oms.refresh(NEXT) == ["TCS.NS entry rejected: RMS: insufficient funds"]
    assert oms.store.order(other.tag)["status"] == "REJECTED" and "TCS.NS" not in oms.store.positions()


def test_a_stop_protects_the_holding_until_it_sells(tmp_path):
    kite, oms = make(tmp_path)
    bought(kite, oms)
    held = oms.store.positions()["INFY.NS"]
    stop = broker.stop_order(held, last_price=101.0)
    assert oms.submit(NEXT, "T1", stop) == "SENT" and oms.refresh(NEXT) == []  # waiting at Kite
    gtt = kite.gtts[int(oms.store.order(stop.tag)["kite_id"])]
    assert gtt["condition"]["trigger_values"] == [95.0] and gtt["condition"]["last_price"] == 101.0
    sell = kite.trigger(gtt["id"])
    assert oms.refresh(NEXT) == ["INFY.NS: the stop was touched and its sell order placed"]
    kite.fill(sell, 94.8)
    assert oms.refresh(NEXT) == ["INFY.NS stop: sell 5 at 94.80"]
    assert oms.store.positions() == {} and oms.reconcile() == []
    assert list(oms.store.table("live_fills")["side"]) == ["buy", "sell"]


def test_a_gap_below_the_limit_makes_the_stops_sell_a_market_order(tmp_path):
    kite, oms = make(tmp_path)
    bought(kite, oms)
    held = oms.store.positions()["INFY.NS"]
    oms.submit(NEXT, "T1", broker.stop_order(held, last_price=101.0))
    assert oms.submit(NEXT, "T1", probe(broker.gap_exit(held))) == "REJECTED"  # nothing to change before it triggers
    sell = kite.trigger(kite.gtts[int(oms.store.order(broker.stop_order(held).tag)["kite_id"])]["id"])
    oms.refresh(NEXT)
    assert oms.submit(NEXT, "T1", broker.gap_exit(held)) == "DONE" and sell["order_type"] == "MARKET"
    kite.fill(sell, 80.0)
    assert oms.refresh(NEXT) == ["INFY.NS stop: sell 5 at 80.00"] and oms.store.positions() == {}


def test_deleting_a_stop(tmp_path):
    kite, oms = make(tmp_path)
    bought(kite, oms)
    held = oms.store.positions()["INFY.NS"]
    early = probe(broker.cancel_stop(held, broker.AFTER_OPEN))
    assert oms.submit(NEXT, "T1", early) == "REJECTED"  # its stop was never placed
    assert oms.store.order(early.tag)["detail"] == "its stop was never placed"
    oms.submit(NEXT, "T1", broker.stop_order(held, last_price=101.0))
    cancel = broker.cancel_stop(held, broker.AFTER_OPEN)
    kite.failures = [("timeout", True)]
    assert oms.submit(NEXT, "T1", cancel) == "UNKNOWN"
    assert oms.submit(NEXT, "T1", cancel) == "DONE"  # Kite had deleted it: found, not repeated
    assert oms.refresh(NEXT) == [] and oms.store.order(broker.stop_order(held).tag)["status"] == "CANCELLED"


def test_holdings_are_reconciled_with_the_account(tmp_path):
    kite, oms = make(tmp_path)
    bought(kite, oms)
    kite.positions["net"].append({"tradingsymbol": "INFY", "exchange": "NSE", "product": "CNC", "quantity": 20})
    assert oms.reconcile() == []  # more in the account is fine: your own shares
    kite.positions = {"net": [], "day": []}
    assert oms.reconcile() == ["INFY.NS: the system holds 5 shares but the account has 0"]
    oms.store.delete_position("INFY.NS")
    assert oms.reconcile() == ["INFY.NS: holding 0 shares but the fills imply 5"]


def test_the_live_record_is_append_only_and_backed_up(tmp_path):
    kite, oms = make(tmp_path)
    bought(kite, oms)
    for statement in ("UPDATE broker_events SET status = 'x'", "DELETE FROM broker_events",
                      "UPDATE live_fills SET price = 1", "DELETE FROM live_fills"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            oms.store.conn.execute(statement)
    copy = sqlite3.connect(oms.store.backup(tmp_path / "backups", NEXT))
    assert copy.execute("SELECT COUNT(*) FROM live_fills").fetchone()[0] == 1
    copy.close()
    with pytest.raises(ValueError):
        oms.store.table("sqlite_master")
