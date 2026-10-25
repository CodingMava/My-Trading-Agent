"""A simulated Zerodha account for dry runs of the live jobs (python -m trader.execution.live <job> --dry-run).

It answers the HTTP calls trader/execution/kite_orders.py makes, so the order system runs exactly as it would live,
but every order, GTT, holding and rupee is simulated and kept in a JSON file (state/live-dryrun/kite.json). Only
prices come from Kite, through `quotes` (the day's open, high, low and last price, read with today's login). No other
request reaches Kite, and no write ever does.

How the simulated market behaves (IST, on NSE trading days):
  after-market orders   accepted outside 09:00-15:45; they fill at the open of the next session, when a later call
                        sees it (the morning job, normally). A buy the cash can't pay for, or a sale of shares not
                        held, is rejected then, as Kite rejects it at the open.
  regular orders        accepted 09:15-15:30 only; a MARKET order fills at once at the last price.
  GTT single triggers   fire when the session's low reaches the trigger (on the day a GTT is placed, only when a
                        later call sees the last price there). Its LIMIT sell fills at the open if the open was at
                        or below the trigger and not below the limit, at the trigger when the price fell to it
                        later, and stays open when the open was below the limit (the morning job's gap exit).
  holdings              a delivery buy shows in the day's positions and becomes a T+1 holding the next trading day.
  the order book        cleared every trading day, except after-market orders still waiting for the open.
Each fill pays Zerodha's delivery charges from the cash (STT, exchange and SEBI fees, GST, stamp duty, the DP charge;
trader/research/costs.py); slippage is in the fill price itself. A day no job ran is seen only through the next call's
quotes, so the dry run needs the scheduled jobs to run every trading day, like live trading does.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from trader.data.kite import API_ROOT
from trader.research.costs import ZERODHA_DELIVERY, CostModel

IST = ZoneInfo("Asia/Kolkata")
OPEN, CLOSE = time(9, 15), time(15, 30)
AMO_CLOSED = (time(9, 0), time(15, 45))  # after-market orders aren't taken while the market is (nearly) open
DONE = ("COMPLETE", "CANCELLED", "REJECTED")


class Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code, self._payload = status_code, payload

    def json(self) -> dict:
        return self._payload


def ok(data) -> Response:
    return Response(200, {"status": "success", "data": data})


def refused(error_type: str, message: str, status_code: int = 400) -> Response:
    return Response(status_code, {"status": "error", "error_type": error_type, "message": f"{message} (simulated)"})


class SimKite:
    """The HTTP surface of a simulated Kite account. `quotes(tradingsymbols)` returns {symbol: {"open", "high", "low",
    "last_price"}} for the current session from the real Kite; it is called only when a price is needed."""

    def __init__(self, path: Path | str, quotes: Callable[[list[str]], dict[str, dict]], clock: Callable[[], datetime],
                 calendar, cash: float, costs: CostModel = ZERODHA_DELIVERY.with_slippage(0.0)):
        self.path, self.quotes, self.clock, self.calendar, self.costs = Path(path), quotes, clock, calendar, costs
        if self.path.is_file():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.state = {"day": None, "cash": float(cash), "next_id": 1001, "orders": [], "gtts": [], "holdings": [],
                          "positions": [], "charges": 0.0}
        self._prices: dict[str, dict] = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    # --- the HTTP surface ---------------------------------------------------------------------------
    def get(self, url, params=None, headers=None, timeout=None):
        path = urlparse(url).path if url.startswith(API_ROOT) else url
        self._prices = {}
        self.advance()
        self.save()
        s = self.state
        if path == "/orders":
            return ok([dict(o) for o in s["orders"]])
        if path == "/gtt/triggers":
            return ok([json.loads(json.dumps(g)) for g in s["gtts"]])
        if path == "/portfolio/holdings":
            return ok([dict(h) for h in s["holdings"]])
        if path == "/portfolio/positions":
            return ok({"net": [dict(p) for p in s["positions"]], "day": []})
        if path == "/user/margins":
            return ok({"equity": {"net": s["cash"], "available": {"cash": s["cash"]}}, "commodity": {}})
        if path == "/quote/ltp":
            symbols = [key.split(":", 1)[1] for key in params["i"]]
            return ok({f"NSE:{symbol}": {"last_price": self._price(symbol)["last_price"]} for symbol in symbols})
        return refused("GeneralException", f"no route {path}", 404)

    def request(self, method, url, data=None, headers=None, timeout=None):
        path = urlparse(url).path
        self._prices = {}
        self.advance()
        response = self._write(method, path, dict(data or {}))
        self.save()
        return response

    # --- writes -------------------------------------------------------------------------------------
    def _write(self, method: str, path: str, data: dict) -> Response:
        parts, now = path.strip("/").split("/"), self.clock()
        if method == "POST" and parts[0] == "orders":
            variety = parts[1]
            if variety == "amo" and self._trading(now.date()) and AMO_CLOSED[0] <= now.time() < AMO_CLOSED[1]:
                return refused("InputException", "after-market orders can't be placed while the market is open")
            if variety == "regular" and not self._market_open(now):
                return refused("InputException", "Markets are closed right now")
            order = {"order_id": str(self._id()), "variety": variety, "tag": data.get("tag"), "placed_at": now.isoformat(),
                     "status": "AMO REQ RECEIVED" if variety == "amo" else "OPEN", "status_message": None,
                     "exchange": data["exchange"], "tradingsymbol": data["tradingsymbol"],
                     "transaction_type": data["transaction_type"], "order_type": data["order_type"],
                     "product": data["product"], "quantity": int(data["quantity"]), "price": data.get("price", 0),
                     "filled_quantity": 0, "pending_quantity": int(data["quantity"]), "average_price": 0}
            self.state["orders"].append(order)
            if variety == "regular" and order["order_type"] == "MARKET":
                self._execute(order, self._price(order["tradingsymbol"])["last_price"])
            return ok({"order_id": order["order_id"]})
        if method == "PUT" and parts[0] == "orders":
            order = self._order(parts[2])
            if order is None or order["status"] in DONE:
                return refused("OrderException", "order can't be modified")
            if not self._market_open(now):
                return refused("InputException", "Markets are closed right now")
            order.update({k: v for k, v in data.items() if k in ("order_type", "price", "quantity")})
            if order["order_type"] == "MARKET":
                self._execute(order, self._price(order["tradingsymbol"])["last_price"])
            return ok({"order_id": order["order_id"]})
        if method == "POST" and path == "/gtt/triggers":
            gtt = {"id": self._id(), "type": data["type"], "status": "active", "placed_at": now.isoformat(),
                   "condition": json.loads(data["condition"]),
                   "orders": [{**leg, "result": None} for leg in json.loads(data["orders"])]}
            self.state["gtts"].append(gtt)
            return ok({"trigger_id": gtt["id"]})
        if method == "DELETE" and parts[:2] == ["gtt", "triggers"]:
            gtt = next((g for g in self.state["gtts"] if str(g["id"]) == parts[2]), None)
            if gtt is None or gtt["status"] != "active":
                return refused("InputException", "Invalid trigger ID")
            gtt["status"] = "deleted"
            return ok({"trigger_id": gtt["id"]})
        return refused("InputException", f"{method} {path}", 405)

    # --- what the market does -----------------------------------------------------------------------
    def advance(self) -> None:
        """Bring the account up to now: each new trading day's rollover, then the open's fills, then the stops."""
        now = self.clock()
        today = now.date()
        last = date.fromisoformat(self.state["day"]) if self.state["day"] else None
        if self._trading(today) and last != today and (last is None or last < today):
            if last is not None:
                self._roll()
            self.state["day"] = today.isoformat()
        if not (self._trading(today) and now.time() >= OPEN):
            return
        opening = datetime.combine(today, AMO_CLOSED[0], IST)
        for order in self.state["orders"]:
            if order["status"] == "AMO REQ RECEIVED" and datetime.fromisoformat(order["placed_at"]) < opening:
                price = self._price(order["tradingsymbol"])["open"]
                if not price > 0:
                    order.update(status="CANCELLED", status_message="no trade at the open (simulated)", pending_quantity=0)
                else:
                    self._execute(order, price)
        for gtt in self.state["gtts"]:
            if gtt["status"] == "active":
                self._watch(gtt, now)
        for order in self.state["orders"]:  # a triggered stop's sell waiting below its limit
            if order["status"] == "OPEN" and order["order_type"] == "LIMIT" and self._market_open(now):
                if self._price(order["tradingsymbol"])["last_price"] >= order["price"]:
                    self._execute(order, order["price"])

    def _watch(self, gtt: dict, now: datetime) -> None:
        symbol, trigger = gtt["condition"]["tradingsymbol"], gtt["condition"]["trigger_values"][0]
        quote = self._price(symbol)
        placed_today = datetime.fromisoformat(gtt["placed_at"]).date() == now.date()
        if placed_today:  # only what the price did after the GTT went in counts
            if not (self._market_open(now) and quote["last_price"] <= trigger):
                return
            at = quote["last_price"]
        else:
            if not quote["low"] <= trigger:
                return
            at = quote["open"] if quote["open"] <= trigger else trigger
        leg = gtt["orders"][0]
        order = {"order_id": str(self._id()), "variety": "regular", "tag": None, "placed_at": now.isoformat(),
                 "status": "OPEN", "status_message": None, "exchange": leg["exchange"], "tradingsymbol": symbol,
                 "transaction_type": leg["transaction_type"], "order_type": leg["order_type"], "product": leg["product"],
                 "quantity": int(leg["quantity"]), "price": leg["price"], "filled_quantity": 0,
                 "pending_quantity": int(leg["quantity"]), "average_price": 0}
        self.state["orders"].append(order)
        gtt["status"] = "triggered"
        leg["result"] = {"order_result": {"order_id": order["order_id"], "status": "success"}}
        if at >= leg["price"]:
            self._execute(order, at)

    def _execute(self, order: dict, price: float) -> None:
        quantity, symbol = order["quantity"], order["tradingsymbol"]
        side = "buy" if order["transaction_type"] == "BUY" else "sell"
        charges = self.costs.one_side(price * quantity, side)
        if side == "buy":
            if price * quantity + charges > self.state["cash"]:
                order.update(status="REJECTED", pending_quantity=0,
                             status_message=f"Insufficient funds: needs Rs {price * quantity + charges:,.2f} (simulated)")
                return
            self.state["cash"] -= price * quantity + charges
            self._position(symbol)["quantity"] += quantity
        else:
            if self.held(symbol) < quantity:
                order.update(status="REJECTED", pending_quantity=0,
                             status_message=f"Insufficient holdings: {self.held(symbol)} held (simulated)")
                return
            self.state["cash"] += price * quantity - charges
            holding = next((h for h in self.state["holdings"] if h["tradingsymbol"] == symbol), None)
            from_holdings = min(quantity, 0 if holding is None else
                                holding["quantity"] + holding["t1_quantity"] - holding["used_quantity"])
            if from_holdings:
                holding["used_quantity"] += from_holdings
            if quantity > from_holdings:
                self._position(symbol)["quantity"] -= quantity - from_holdings
        self.state["charges"] = self.state.get("charges", 0.0) + charges
        order.update(status="COMPLETE", filled_quantity=quantity, pending_quantity=0, average_price=round(price, 2))

    def held(self, symbol: str) -> int:
        holding = sum(h["quantity"] + h["t1_quantity"] - h["used_quantity"] for h in self.state["holdings"]
                      if h["tradingsymbol"] == symbol)
        return holding + sum(max(0, p["quantity"]) for p in self.state["positions"] if p["tradingsymbol"] == symbol)

    def _roll(self) -> None:
        """Overnight: the day's delivery buys become T+1 holdings, yesterday's T+1 settle, sold holdings leave, and the
        order book keeps only after-market orders still waiting for the open."""
        holdings = {h["tradingsymbol"]: h for h in self.state["holdings"]}
        for h in holdings.values():
            h["quantity"] += h["t1_quantity"] - h["used_quantity"]
            h["t1_quantity"], h["used_quantity"] = 0, 0
        for p in self.state["positions"]:
            if p["quantity"] > 0:
                h = holdings.setdefault(p["tradingsymbol"], {"tradingsymbol": p["tradingsymbol"], "exchange": "NSE",
                                                             "quantity": 0, "t1_quantity": 0, "used_quantity": 0})
                h["t1_quantity"] += p["quantity"]
        self.state["holdings"] = [h for h in holdings.values() if h["quantity"] + h["t1_quantity"] > 0]
        self.state["positions"] = []
        self.state["orders"] = [o for o in self.state["orders"] if o["status"] == "AMO REQ RECEIVED"]

    # --- helpers ------------------------------------------------------------------------------------
    def _position(self, symbol: str) -> dict:
        position = next((p for p in self.state["positions"] if p["tradingsymbol"] == symbol), None)
        if position is None:
            position = {"tradingsymbol": symbol, "exchange": "NSE", "product": "CNC", "quantity": 0}
            self.state["positions"].append(position)
        return position

    def _price(self, symbol: str) -> dict:
        if symbol not in self._prices:
            self._prices.update(self.quotes([symbol]))
        return self._prices[symbol]

    def _order(self, order_id: str) -> dict | None:
        return next((o for o in self.state["orders"] if o["order_id"] == str(order_id)), None)

    def _id(self) -> int:
        self.state["next_id"] += 1
        return self.state["next_id"] - 1

    def _trading(self, day: date) -> bool:
        return self.calendar.is_trading_day(day)

    def _market_open(self, now: datetime) -> bool:
        return self._trading(now.date()) and OPEN <= now.time() <= CLOSE
