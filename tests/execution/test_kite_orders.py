"""Kite's trading endpoints against an in-memory Kite (no network, no real account)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tests.execution.fake_kite import FakeKite, FakeResponse, error, ok
from trader.config import load_settings
from trader.data.kite import KiteAuthError, KiteError, KiteSession, save_session
from trader.execution.kite_orders import KiteOrders, OrderRejected, OutcomeUnknown, from_session, held_quantity

ORDER = {"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "BUY", "order_type": "MARKET", "quantity": 5,
         "product": "CNC", "validity": "DAY", "market_protection": -1, "tag": "Eabc"}
GTT = {"type": "single",
       "condition": {"exchange": "NSE", "tradingsymbol": "INFY", "trigger_values": [95.0], "last_price": 100.0},
       "orders": [{"exchange": "NSE", "tradingsymbol": "INFY", "transaction_type": "SELL", "quantity": 5,
                   "order_type": "LIMIT", "product": "CNC", "price": 90.25}]}


def client(http):
    return KiteOrders("key", "AT", http=http, sleep=lambda seconds: None)


class Scripted:
    """Answers reads from a list of responses."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_orders_and_stops_reach_kites_endpoints():
    kite = FakeKite()
    api = client(kite)
    order_id = api.place_order("amo", ORDER)
    assert kite.calls[-1][:2] == ("POST", "/orders/amo") and kite.order(order_id)["status"] == "AMO REQ RECEIVED"
    assert api.modify_order("amo", order_id, {"order_type": "LIMIT", "price": 99.5}) == order_id
    trigger_id = api.place_gtt(GTT)
    sent = kite.calls[-1][2]
    assert json.loads(sent["condition"]) == GTT["condition"] and json.loads(sent["orders"]) == GTT["orders"]
    assert api.delete_gtt(trigger_id) == trigger_id and kite.gtts[int(trigger_id)]["status"] == "deleted"
    assert [o["order_id"] for o in api.orders()] == [order_id] and str(api.gtts()[0]["id"]) == trigger_id
    kite.holdings, kite.prices = [{"tradingsymbol": "INFY"}], {"INFY": 101.5, "M&M": 3001.0}
    assert api.holdings() == kite.holdings and api.positions() == {"net": [], "day": []}
    assert api.ltp(["INFY", "M&M"]) == {"INFY": 101.5, "M&M": 3001.0} and api.ltp([]) == {}


def test_a_write_that_may_have_arrived_is_never_resent():
    for failure in (("timeout", True), ("timeout", False), ("http", 502, "NetworkException", False),
                    ("http", 500, "GeneralException", True), ("http", 200, "DataException", True)):
        kite = FakeKite()
        kite.failures = [failure]
        with pytest.raises(OutcomeUnknown):
            client(kite).place_order("amo", ORDER)
        assert [c[0] for c in kite.calls] == ["POST"], failure  # one attempt, whatever happened at Kite
        assert len(kite.orders) == (1 if failure[-1] else 0)


def test_refusals_are_final_and_a_rate_limit_is_retried():
    for kind in ("MarginException", "HoldingException", "InputException", "OrderException"):
        kite = FakeKite()
        kite.failures = [("http", 400, kind, False)]
        with pytest.raises(OrderRejected, match=kind):
            client(kite).place_order("amo", ORDER)
    kite = FakeKite()
    kite.failures = [("http", 429, "", False)]  # the rate limiter turned it away: Kite never processed it
    assert client(kite).place_order("amo", ORDER) and len(kite.calls) == 2 and len(kite.orders) == 1
    kite = FakeKite()
    kite.failures = [("http", 429, "", False)] * 3
    with pytest.raises(OrderRejected, match="429"):
        client(kite).place_order("amo", ORDER)
    kite = FakeKite()
    kite.failures = [("http", 403, "TokenException", False)]
    with pytest.raises(KiteAuthError, match="login"):
        client(kite).place_order("amo", ORDER)


def test_reads_are_retried_and_errors_named():
    http = Scripted(FakeResponse(503, None), ok([{"order_id": "1"}]))
    assert client(http).orders() == [{"order_id": "1"}] and http.calls == 2
    with pytest.raises(KiteError, match="GeneralException: down"):
        client(Scripted(*[error(500, "GeneralException", "down")] * 3)).orders()
    with pytest.raises(KiteAuthError):
        client(Scripted(error(403, "TokenException", "expired"))).holdings()


def test_shares_in_the_account():
    holdings = [{"tradingsymbol": "INFY", "exchange": "NSE", "quantity": 10, "t1_quantity": 5, "used_quantity": 3},
                {"tradingsymbol": "INFY", "exchange": "BSE", "quantity": 100}]
    bought_today = {"net": [{"tradingsymbol": "INFY", "exchange": "NSE", "product": "CNC", "quantity": 4},
                            {"tradingsymbol": "INFY", "exchange": "NSE", "product": "MIS", "quantity": 50}]}
    assert held_quantity(holdings, bought_today, "INFY") == 10 + 5 - 3 + 4  # not BSE's, not intraday
    sold_today = {"net": [{"tradingsymbol": "INFY", "exchange": "NSE", "product": "CNC", "quantity": -3}]}
    assert held_quantity(holdings, sold_today, "INFY") == 12  # the sale is already in used_quantity
    assert held_quantity([], {"net": []}, "INFY") == 0


def test_a_client_needs_todays_kite_session(tmp_path):
    session_file = tmp_path / "session.json"
    with pytest.raises(KiteAuthError, match="KITE_API_KEY"):
        from_session(load_settings(env={}), session_file)
    settings = load_settings(env={"KITE_API_KEY": "key", "KITE_API_SECRET": "sec"})
    with pytest.raises(KiteAuthError, match="login"):
        from_session(settings, session_file)
    save_session(KiteSession("key", "AT", "U", datetime.now(ZoneInfo("Asia/Kolkata"))), session_file)
    assert isinstance(from_session(settings, session_file), KiteOrders)
