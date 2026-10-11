"""Zerodha Kite Connect trading endpoints: orders, GTT stops and the portfolio (Phase 8).

This module only talks to Kite. trader/execution/oms.py decides what is sent, and trader/execution/live.py
only lets it send for strategies whose evidence has earned real money. The rule kept here is about doubt:
a write that may or may not have reached Kite (a timeout, a dropped connection, a Kite-side failure) is
never retried. It raises OutcomeUnknown, and the order system looks the order up before sending anything
again. Reads are retried, and so is a write that Kite's rate limiter turned away (HTTP 429): Kite never
processed it.
"""
from __future__ import annotations

import json
import time as _time

import requests

from trader.data.kite import API_ROOT, SESSION_FILE, KiteAuthError, KiteError, load_session

RETRY_READS = frozenset({429, 500, 502, 503, 504})
REFUSALS = frozenset({"InputException", "OrderException", "MarginException", "HoldingException", "UserException"})


class OrderRejected(KiteError):
    """Kite refused the request, so nothing was placed."""


class OutcomeUnknown(KiteError):
    """The request may or may not have been placed: look it up before sending anything again."""


def _data(response, write: bool):
    """The `data` of a successful response; otherwise the exception that says what went wrong."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    kind, message = payload.get("error_type", ""), payload.get("message", "")
    if response.status_code == 403 or kind == "TokenException":
        raise KiteAuthError(f"{message or 'session expired'} (run: python -m trader.data.kite login)")
    if response.status_code == 200 and payload.get("status") == "success":
        return payload["data"]
    label = kind or f"HTTP {response.status_code}"
    detail = f"{label}: {message}" if message else label
    if not write:
        raise KiteError(detail)
    if kind in REFUSALS or (not kind and response.status_code in (400, 404, 405, 410, 429)):
        raise OrderRejected(detail)
    raise OutcomeUnknown(detail)  # NetworkException, DataException, GeneralException, a 5xx, an unreadable reply


class KiteOrders:
    def __init__(self, api_key: str, access_token: str, http=None, timeout: float = 10, sleep=_time.sleep):
        self._headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}
        self._http = http if http is not None else requests.Session()
        self._timeout, self._sleep = timeout, sleep

    def _read(self, path: str, params: dict | None = None):
        for attempt in range(3):  # pragma: no branch (the last attempt always returns)
            response = self._http.get(API_ROOT + path, params=params, headers=self._headers, timeout=self._timeout)
            if response.status_code not in RETRY_READS or attempt == 2:
                return _data(response, write=False)
            self._sleep(1.0 + attempt)

    def _write(self, method: str, path: str, data: dict | None = None):
        for attempt in range(3):  # pragma: no branch (the last attempt always returns)
            try:
                response = self._http.request(method, API_ROOT + path, data=data, headers=self._headers,
                                              timeout=self._timeout)
            except requests.RequestException as exc:  # it may have arrived: never resend blindly
                raise OutcomeUnknown(f"{method} {path}: {type(exc).__name__}") from None
            if response.status_code != 429 or attempt == 2:
                return _data(response, write=True)
            self._sleep(1.0 + attempt)

    # writes
    def place_order(self, variety: str, params: dict) -> str:
        return str(self._write("POST", f"/orders/{variety}", params)["order_id"])

    def modify_order(self, variety: str, order_id: str, params: dict) -> str:
        return str(self._write("PUT", f"/orders/{variety}/{order_id}", params)["order_id"])

    def place_gtt(self, params: dict) -> str:
        form = {"type": params["type"], "condition": json.dumps(params["condition"]), "orders": json.dumps(params["orders"])}
        return str(self._write("POST", "/gtt/triggers", form)["trigger_id"])

    def delete_gtt(self, trigger_id: str) -> str:
        return str(self._write("DELETE", f"/gtt/triggers/{trigger_id}")["trigger_id"])

    # reads
    def orders(self) -> list[dict]:
        """Today's orders: Kite keeps the order book for a day."""
        return list(self._read("/orders"))

    def gtts(self) -> list[dict]:
        return list(self._read("/gtt/triggers"))

    def holdings(self) -> list[dict]:
        return list(self._read("/portfolio/holdings"))

    def positions(self) -> dict:
        return dict(self._read("/portfolio/positions"))

    def margins(self) -> dict:
        return dict(self._read("/user/margins"))

    def ltp(self, tradingsymbols: list[str], exchange: str = "NSE") -> dict[str, float]:
        if not tradingsymbols:
            return {}
        data = self._read("/quote/ltp", {"i": [f"{exchange}:{symbol}" for symbol in tradingsymbols]})
        return {key.split(":", 1)[1]: float(quote["last_price"]) for key, quote in data.items()}


def held_quantity(holdings: list[dict], positions: dict, tradingsymbol: str, exchange: str = "NSE") -> int:
    """Shares of one stock in the account: settled and T+1 holdings less what was sold from them today, plus
    today's net delivery (CNC) buys, which reach the holdings only the next day."""
    held = sum(int(h.get("quantity", 0)) + int(h.get("t1_quantity", 0)) - int(h.get("used_quantity", 0))
               for h in holdings if h.get("tradingsymbol") == tradingsymbol and h.get("exchange") == exchange)
    bought = sum(int(p.get("quantity", 0)) for p in positions.get("net", [])
                 if p.get("tradingsymbol") == tradingsymbol and p.get("exchange") == exchange and p.get("product") == "CNC")
    return held + max(0, bought)  # today's sales from holdings are already in used_quantity


def from_session(settings, session_file=SESSION_FILE) -> KiteOrders:
    """A client for today's Kite session (python -m trader.data.kite login)."""
    if not (settings.kite_api_key and settings.kite_api_secret):
        raise KiteAuthError("set KITE_API_KEY and KITE_API_SECRET in .env (see .env.example)")
    session = load_session(session_file)
    if session is None or session.api_key != settings.kite_api_key.reveal():
        raise KiteAuthError("no valid Kite session today (run: python -m trader.data.kite login)")
    return KiteOrders(session.api_key, session.access_token)
