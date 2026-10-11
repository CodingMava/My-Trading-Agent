"""Zerodha Kite orders in a dry run (Phase 8). Each step of paper trading becomes the exact Kite Connect
request that would carry it out with real shares. The request is checked against Kite's and NSE's rules and
recorded with its session, but never sent: this module has no network code. Sending is Phase 11, once a
strategy has earned real money.

    python -m trader.execution.broker                       # the latest session's requests
    python -m trader.execution.broker --session 2026-10-12

When a live system would send each request (IST):
  18:00, after the daily run   entry, exit: after-market orders (AMO) for the next open, MARKET with Kite's
                               automatic market protection (Kite rejects market orders without it), CNC
                               (delivery). The exchange fills them at the open, as paper trading assumes.
  09:20, after the open        stop: a GTT trigger for each holding bought at the open. It stays until it is
                               deleted, so a day the PC is off leaves the holding protected. When the price
                               touches the stop it places a LIMIT sell (a GTT can't place any other kind) at
                               up to 5% below the stop. cancel stop: deletes the GTT of a holding the open sold.
                               gap exit: a holding that opened below that limit is still unsold, so the GTT's
                               order becomes a MARKET order (paper trading sells at the open).
  15:15, before the close      time exit: deletes the GTT, then sells at MARKET (paper trading sells at the close).

Before the first real order: register a static IP with Kite (since April 2026 it rejects order requests from
any other address), give Zerodha a DDPI (without one, every sale of delivery shares needs a TPIN approval by
hand), and take each stock's tick size from Kite's instrument list instead of NSE's price bands below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date

from trader.config import ROOT, load_settings
from trader.core.models import Position
from trader.execution.store import PaperStore

AFTER_CLOSE, AFTER_OPEN, BEFORE_CLOSE = "18:00", "09:20", "15:15"  # IST
AUTO_PROTECTION = -1  # Kite's automatic market protection
STOP_LIMIT_BAND = 0.05  # a triggered stop sells at no less than 5% below the stop
# NSE cash-market ticks from 15 Apr 2025 (circular 33/2025), as (highest price, tick); Rs 0.01 below Rs 250.
# NSE sets each stock's band monthly from its last close, so near an edge Kite's instrument list decides.
NSE_TICKS = ((1_000, 0.05), (5_000, 0.10), (10_000, 0.50), (20_000, 1.00), (math.inf, 5.00))
TRADINGSYMBOL = re.compile(r"[A-Z0-9&_-]+")
TAG = re.compile(r"[A-Za-z0-9]{1,20}")


@dataclass(frozen=True)
class KiteRequest:
    symbol: str  # as paper trading names it (RELIANCE.NS)
    purpose: str  # entry, exit, stop, cancel stop, gap exit or time exit
    send_at: str  # IST
    method: str
    path: str  # under https://api.kite.trade; <...> stands for an id Kite assigns when the GTT is created
    params: dict = field(default_factory=dict)  # a GTT's condition and orders are sent as JSON text
    tag: str = ""  # unique per request; an order also carries it to Kite, so a resend can be recognised

    def json(self) -> str:
        return json.dumps({"method": self.method, "path": self.path, "params": self.params})


def tick_size(price: float) -> float:
    return 0.01 if price < 250 else next(tick for highest, tick in NSE_TICKS if price <= highest)


def to_tick(price: float, down: bool = False) -> float:
    """The price on a tick: the nearest one, or the one at or below it."""
    tick = tick_size(price)
    steps = math.floor(price / tick + 1e-9) if down else round(price / tick)
    return round(steps * tick, 2)


def on_tick(price: float) -> bool:
    steps = price / tick_size(price)
    return abs(steps - round(steps)) < 1e-6


def stop_limit(stop_price: float) -> float:
    """The lowest price a triggered stop sells at."""
    return to_tick(to_tick(stop_price) * (1 - STOP_LIMIT_BAND), down=True)


def _tag(kind: str, key: str) -> str:
    return kind + hashlib.sha256(key.encode()).hexdigest()[:19]


def _held(position: Position) -> str:
    return f"{position.symbol}:{position.entry_date}"


def _gtt(position: Position) -> str:
    return f"<GTT {_tag('S', _held(position))}>"


def _market_order(symbol: str, side: str, quantity: int, tag: str) -> dict:
    return {"exchange": "NSE", "tradingsymbol": symbol.removesuffix(".NS"), "transaction_type": side,
            "order_type": "MARKET", "quantity": int(quantity), "product": "CNC", "validity": "DAY",
            "market_protection": AUTO_PROTECTION, "tag": tag}


def entry_order(key: str, symbol: str, quantity: int) -> KiteRequest:
    tag = _tag("E", key)
    return KiteRequest(symbol, "entry", AFTER_CLOSE, "POST", "/orders/amo", _market_order(symbol, "BUY", quantity, tag), tag)


def exit_order(key: str, symbol: str, quantity: int) -> KiteRequest:
    tag = _tag("X", key)
    return KiteRequest(symbol, "exit", AFTER_CLOSE, "POST", "/orders/amo", _market_order(symbol, "SELL", quantity, tag), tag)


def stop_order(position: Position) -> KiteRequest:
    tradingsymbol = position.symbol.removesuffix(".NS")
    condition = {"exchange": "NSE", "tradingsymbol": tradingsymbol, "trigger_values": [to_tick(position.stop_price)],
                 "last_price": float(position.entry_price)}
    orders = [{"exchange": "NSE", "tradingsymbol": tradingsymbol, "transaction_type": "SELL",
               "quantity": int(position.quantity), "order_type": "LIMIT", "product": "CNC",
               "price": stop_limit(position.stop_price)}]
    return KiteRequest(position.symbol, "stop", AFTER_OPEN, "POST", "/gtt/triggers",
                       {"type": "single", "condition": condition, "orders": orders}, _tag("S", _held(position)))


def cancel_stop(position: Position, send_at: str) -> KiteRequest:
    return KiteRequest(position.symbol, "cancel stop", send_at, "DELETE", f"/gtt/triggers/{_gtt(position)}",
                       tag=_tag("C", _held(position)))


def gap_exit(position: Position) -> KiteRequest:
    return KiteRequest(position.symbol, "gap exit", AFTER_OPEN, "PUT", f"/orders/regular/<order from {_gtt(position)[1:-1]}>",
                       {"order_type": "MARKET", "market_protection": AUTO_PROTECTION}, _tag("G", _held(position)))


def time_exit(position: Position) -> KiteRequest:
    tag = _tag("T", _held(position))
    return KiteRequest(position.symbol, "time exit", BEFORE_CLOSE, "POST", "/orders/regular",
                       _market_order(position.symbol, "SELL", position.quantity, tag), tag)


# --- what Kite or NSE would refuse ------------------------------------------------------------------------
def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _shares(value) -> list[str]:
    ok = isinstance(value, int) and not isinstance(value, bool) and value >= 1
    return [] if ok else [f"quantity {value!r} isn't a whole number of shares"]


def _price(value, name: str) -> list[str]:
    ok = _number(value) and value > 0 and on_tick(value)
    return [] if ok else [f"{name} {value!r} isn't a positive price on NSE's tick"]


def _instrument(p: dict) -> list[str]:
    ok = p.get("exchange") == "NSE" and TRADINGSYMBOL.fullmatch(str(p.get("tradingsymbol", "")))
    return [] if ok else [f"{p.get('exchange')}:{p.get('tradingsymbol')} isn't an NSE stock"]


def _market(p: dict) -> list[str]:
    protection = p.get("market_protection")
    ok = protection == AUTO_PROTECTION or (_number(protection) and 0 < protection <= 100)
    found = [] if ok else [f"market protection {protection!r}: Kite rejects a MARKET order without it"]
    return found + (["a MARKET order has no price"] if "price" in p else [])


def _order(p: dict) -> list[str]:
    found = _instrument(p) + _shares(p.get("quantity"))
    if p.get("transaction_type") not in ("BUY", "SELL"):
        found.append(f"transaction type {p.get('transaction_type')!r}")
    if (p.get("product"), p.get("validity")) != ("CNC", "DAY"):
        found.append("a swing order is CNC (delivery), valid for the DAY")
    if p.get("order_type") == "MARKET":
        found += _market(p)
    elif p.get("order_type") == "LIMIT":
        found += _price(p.get("price"), "price")
    else:
        found.append(f"order type {p.get('order_type')!r}")
    return found


def _gtt_problems(p: dict) -> list[str]:
    condition, legs = p.get("condition", {}), p.get("orders", [])
    triggers = condition.get("trigger_values", [])
    if p.get("type") != "single" or len(triggers) != 1 or len(legs) != 1:
        return ["a stop is a single GTT: one trigger, one order"]
    trigger, leg = triggers[0], legs[0]
    found = _instrument(condition) + _price(trigger, "trigger") + _instrument(leg) + _shares(leg.get("quantity"))
    found += _price(leg.get("price"), "limit")
    if not (_number(condition.get("last_price")) and _number(trigger) and trigger < condition["last_price"]):
        found.append("a stop's trigger must be below the last price, or it fires at once")
    if (leg.get("tradingsymbol"), leg.get("transaction_type"), leg.get("order_type"), leg.get("product")) != \
            (condition.get("tradingsymbol"), "SELL", "LIMIT", "CNC"):
        found.append("a stop's order must be a LIMIT sell of the same stock, CNC")
    if _number(leg.get("price")) and _number(trigger) and leg["price"] > trigger:
        found.append("the limit is above the trigger")
    return found


def problems(request: KiteRequest) -> list[str]:
    """Why Kite or NSE would refuse this request; empty when it would be accepted."""
    found = [] if TAG.fullmatch(request.tag) else [f"tag {request.tag!r} isn't 1-20 letters and digits"]
    route = (request.method, request.path.split("/<")[0])
    if route in {("POST", "/orders/amo"), ("POST", "/orders/regular")}:
        found += _order(request.params)
        if request.params.get("tag") != request.tag:
            found.append("the order doesn't carry its tag")
    elif route == ("POST", "/gtt/triggers"):
        found += _gtt_problems(request.params)
    elif route == ("PUT", "/orders/regular"):  # the GTT's unfilled LIMIT sell, made a MARKET order
        found += [] if request.params.get("order_type") == "MARKET" else ["a gap exit turns the order into MARKET"]
        found += _market(request.params)
    elif route != ("DELETE", "/gtt/triggers"):
        found.append(f"{request.method} {request.path} isn't a request this system makes")
    return found


# --- viewing -------------------------------------------------------------------------------------------
def describe(store: PaperStore, session: date | None = None) -> str:
    """One session's requests (by default the latest that has any), in the order they were prepared."""
    rows = store.table("dry_run_orders")
    if rows.empty:
        return "No Kite requests prepared yet."
    day = session.isoformat() if session else rows["session"].max()
    rows = rows[rows["session"] == day]
    if rows.empty:
        return f"No Kite requests for the {day} session."
    lines = [f"Kite requests for the {day} session (dry run: none was sent)"]
    for row in rows.itertuples():
        request = json.loads(row.request)
        lines.append(f"  {row.send_at}  {row.purpose:<11}  {row.symbol:<14} {request['method']} {request['path']}"
                     + (f"  {json.dumps(request['params'])}" if request["params"] else ""))
        if row.problems:
            lines.append(f"         Kite would refuse it: {row.problems}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="The Kite requests the dry run prepared. None is ever sent.")
    parser.add_argument("--session", type=date.fromisoformat, help="default: the latest session with any")
    args = parser.parse_args(argv)
    settings = load_settings()
    database = ROOT / settings.paper_database
    if not database.exists():
        raise SystemExit("No paper records yet: the daily run creates them.")
    print(describe(PaperStore(database, settings.paper_starting_capital), args.session))


if __name__ == "__main__":
    main()
