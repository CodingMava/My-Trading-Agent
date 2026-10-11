"""An in-memory Kite for tests: an order book, GTT triggers, holdings, positions and prices, plus failures on
demand. It answers the HTTP calls trader/execution/kite_orders.py makes. No network, no real account."""
import itertools
import json
from urllib.parse import urlparse

import requests

from trader.data.kite import API_ROOT


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code, self._payload = status_code, payload

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


def ok(data):
    return FakeResponse(200, {"status": "success", "data": data})


def error(status_code, error_type, message):
    return FakeResponse(status_code, {"status": "error", "error_type": error_type, "message": message})


class FakeKite:
    def __init__(self):
        self.orders, self.gtts, self.holdings = [], {}, []
        self.positions = {"net": [], "day": []}
        self.prices: dict[str, float] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.failures: list[tuple] = []  # for the next writes: ("timeout", placed) or ("http", status, type, placed)
        self._ids = itertools.count(1001)

    # --- the HTTP surface ---------------------------------------------------------------------------
    def get(self, url, params=None, headers=None, timeout=None):
        path = urlparse(url).path if url.startswith(API_ROOT) else url
        self.calls.append(("GET", path, params))
        if path == "/orders":
            return ok([dict(o) for o in self.orders])
        if path == "/gtt/triggers":
            return ok([json.loads(json.dumps(g)) for g in self.gtts.values()])
        if path == "/portfolio/holdings":
            return ok(list(self.holdings))
        if path == "/portfolio/positions":
            return ok(dict(self.positions))
        if path == "/quote/ltp":
            return ok({key: {"last_price": self.prices[key.split(":", 1)[1]]} for key in params["i"]})
        return error(404, "GeneralException", f"no route {path}")

    def request(self, method, url, data=None, headers=None, timeout=None):
        path = urlparse(url).path
        self.calls.append((method, path, data))
        failure = self.failures.pop(0) if self.failures else None
        if failure and not failure[-1]:  # fails before Kite records anything
            if failure[0] == "timeout":
                raise requests.Timeout("timed out")
            return error(failure[1], failure[2], "injected")
        response = self._write(method, path, data or {})
        if failure:  # Kite recorded it, but the answer was lost or garbled
            if failure[0] == "timeout":
                raise requests.Timeout("timed out")
            return error(failure[1], failure[2], "injected")
        return response

    def _write(self, method, path, data):
        parts = path.strip("/").split("/")
        if method == "POST" and parts[0] == "orders":
            order = {"order_id": str(next(self._ids)), "variety": parts[1], "tag": data.get("tag"),
                     "status": "AMO REQ RECEIVED" if parts[1] == "amo" else "OPEN", "status_message": None,
                     "exchange": data["exchange"], "tradingsymbol": data["tradingsymbol"],
                     "transaction_type": data["transaction_type"], "order_type": data["order_type"],
                     "product": data["product"], "quantity": int(data["quantity"]), "price": data.get("price", 0),
                     "filled_quantity": 0, "pending_quantity": int(data["quantity"]), "average_price": 0}
            self.orders.append(order)
            return ok({"order_id": order["order_id"]})
        if method == "PUT" and parts[0] == "orders":
            order = self.order(parts[2])
            if order is None or order["status"] in ("COMPLETE", "CANCELLED", "REJECTED"):
                return error(400, "OrderException", "order can't be modified")
            order.update({k: v for k, v in data.items() if k in ("order_type", "price", "quantity")})
            return ok({"order_id": order["order_id"]})
        if method == "POST" and path == "/gtt/triggers":
            gtt = {"id": next(self._ids), "type": data["type"], "status": "active",
                   "condition": json.loads(data["condition"]),
                   "orders": [{**leg, "result": None} for leg in json.loads(data["orders"])]}
            self.gtts[gtt["id"]] = gtt
            return ok({"trigger_id": gtt["id"]})
        if method == "DELETE" and parts[:2] == ["gtt", "triggers"]:
            gtt = self.gtts.get(int(parts[2]))
            if gtt is None or gtt["status"] != "active":
                return error(400, "InputException", "Invalid trigger ID")
            gtt["status"] = "deleted"
            return ok({"trigger_id": gtt["id"]})
        return error(405, "InputException", f"{method} {path}")

    # --- what the market does -----------------------------------------------------------------------
    def order(self, order_id):
        return next((o for o in self.orders if o["order_id"] == str(order_id)), None)

    def by_tag(self, tag):
        return next(o for o in self.orders if o["tag"] == tag)

    def fill(self, order, price, quantity=None, then="COMPLETE"):
        """Execute an order (all of it, or `quantity` and then cancel the rest)."""
        filled = order["quantity"] if quantity is None else quantity
        order.update(filled_quantity=filled, pending_quantity=0, average_price=price,
                     status="COMPLETE" if filled == order["quantity"] else then)
        tradingsymbol, sign = order["tradingsymbol"], 1 if order["transaction_type"] == "BUY" else -1
        if sign > 0:  # a delivery buy shows in today's positions; it reaches the holdings the next day
            self.positions["net"].append({"tradingsymbol": tradingsymbol, "exchange": "NSE", "product": "CNC",
                                          "quantity": filled})
        else:
            holding = next((h for h in self.holdings if h["tradingsymbol"] == tradingsymbol), None)
            if holding is not None:
                holding["used_quantity"] = holding.get("used_quantity", 0) + filled
            else:
                self.positions["net"].append({"tradingsymbol": tradingsymbol, "exchange": "NSE", "product": "CNC",
                                              "quantity": -filled})

    def reject(self, order, message):
        order.update(status="REJECTED", status_message=message, pending_quantity=0)

    def new_day(self):
        """Overnight: today's delivery positions become (T+1) holdings, sold holdings leave, and the order book
        is cleared except for after-market orders still waiting for the open."""
        for position in self.positions["net"]:
            holding = next((h for h in self.holdings if h["tradingsymbol"] == position["tradingsymbol"]), None)
            if holding is None:
                holding = {"tradingsymbol": position["tradingsymbol"], "exchange": "NSE", "quantity": 0,
                           "t1_quantity": 0, "used_quantity": 0}
                self.holdings.append(holding)
            holding["t1_quantity"] += position["quantity"]
        for holding in self.holdings:
            holding["quantity"] += holding["t1_quantity"] - holding["used_quantity"]
            holding["t1_quantity"], holding["used_quantity"] = 0, 0
        self.holdings = [h for h in self.holdings if h["quantity"] > 0]
        self.positions = {"net": [], "day": []}
        self.orders = [o for o in self.orders if o["status"] == "AMO REQ RECEIVED"]

    def trigger(self, gtt_id):
        """The price touched a GTT's trigger: it places its LIMIT sell."""
        gtt = self.gtts[int(gtt_id)]
        leg = gtt["orders"][0]
        order = {"order_id": str(next(self._ids)), "variety": "regular", "tag": None, "status": "OPEN",
                 "status_message": None, "exchange": leg["exchange"], "tradingsymbol": leg["tradingsymbol"],
                 "transaction_type": leg["transaction_type"], "order_type": leg["order_type"], "product": leg["product"],
                 "quantity": leg["quantity"], "price": leg["price"], "filled_quantity": 0,
                 "pending_quantity": leg["quantity"], "average_price": 0}
        self.orders.append(order)
        gtt["status"] = "triggered"
        leg["result"] = {"order_result": {"order_id": order["order_id"], "status": "success"}}
        return order
