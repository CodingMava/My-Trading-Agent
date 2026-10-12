"""The order management system for live trading (Phase 8): what was sent to Zerodha, what became of it, and
what the system therefore holds. Nothing is sent unless trader/execution/live.py's interlocks allow it.

Every request carries a tag (trader/execution/broker.py) and goes out at most once. Its tag is recorded as
SENDING before it leaves and, once Kite answers, as SENT (with Kite's id), REJECTED, or UNKNOWN when the answer
was lost. A SENDING or UNKNOWN request is looked up at Kite before anything is sent again (an order by its tag,
a GTT by its stock, trigger and quantity), so neither a crash nor a timeout can place an order twice. Each
order's fill is recorded once, when Kite is done with it, and the system's holdings follow from the fills.
The record of events and fills is append-only.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from trader.core.models import Position
from trader.execution import broker
from trader.execution.kite_orders import KiteOrders, OrderRejected, OutcomeUnknown, held_quantity
from trader.execution.store import backup_copy

SCHEMA = """
CREATE TABLE IF NOT EXISTS broker_orders (
    tag TEXT PRIMARY KEY, session TEXT NOT NULL, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL,
    purpose TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, kite_id TEXT, child_id TEXT,
    filled INTEGER NOT NULL DEFAULT 0, average_price REAL, detail TEXT NOT NULL DEFAULT '',
    stop_distance REAL NOT NULL DEFAULT 0, max_hold_days INTEGER, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS broker_events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, tag TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS live_fills (id INTEGER PRIMARY KEY, session TEXT NOT NULL, tag TEXT UNIQUE NOT NULL,
    strategy_id TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity INTEGER NOT NULL CHECK (quantity > 0), price REAL NOT NULL);
CREATE TABLE IF NOT EXISTS live_positions (symbol TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, quantity INTEGER NOT NULL,
    entry_session TEXT NOT NULL, entry_price REAL NOT NULL, stop_price REAL NOT NULL, max_hold_days INTEGER);
CREATE TABLE IF NOT EXISTS capital_steps (id INTEGER PRIMARY KEY, session TEXT NOT NULL, capital REAL NOT NULL,
    reason TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS steps_no_update BEFORE UPDATE ON capital_steps BEGIN SELECT RAISE(ABORT, 'capital steps are append-only'); END;
CREATE TRIGGER IF NOT EXISTS steps_no_delete BEFORE DELETE ON capital_steps BEGIN SELECT RAISE(ABORT, 'capital steps are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON broker_events BEGIN SELECT RAISE(ABORT, 'broker events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON broker_events BEGIN SELECT RAISE(ABORT, 'broker events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS live_fills_no_update BEFORE UPDATE ON live_fills BEGIN SELECT RAISE(ABORT, 'live fills are append-only'); END;
CREATE TRIGGER IF NOT EXISTS live_fills_no_delete BEFORE DELETE ON live_fills BEGIN SELECT RAISE(ABORT, 'live fills are append-only'); END;
"""
UNSETTLED = ("SENDING", "SENT", "TRIGGERED", "UNKNOWN")  # Kite may still act on these
ORDER_PURPOSES = ("entry", "exit", "time exit", "stop exit")
GTT_GONE = ("deleted", "cancelled", "expired", "disabled", "rejected")
STOP_IN_PATH = re.compile(r"GTT (S[0-9a-f]{19})>")


class LiveStore:
    """The live account's records in SQLite (state/live.db), apart from paper trading's."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def order(self, tag: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM broker_orders WHERE tag = ?", (tag,)).fetchone()

    def orders(self, statuses: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
        query, args = "SELECT * FROM broker_orders", ()
        if statuses:
            query, args = query + f" WHERE status IN ({','.join('?' * len(statuses))})", statuses
        return self.conn.execute(query + " ORDER BY rowid", args).fetchall()

    def record(self, at: datetime, session: date, strategy_id: str, request: broker.KiteRequest, status: str,
               detail: str = "", stop_distance: float = 0.0, max_hold_days: int | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO broker_orders (tag, session, strategy_id, symbol, purpose, request, status, detail, "
            "stop_distance, max_hold_days, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request.tag, session.isoformat(), strategy_id, request.symbol, request.purpose, request.json(), status,
             detail, stop_distance, max_hold_days, at.isoformat()))
        self._event(at, request.tag, status, detail)

    def update(self, at: datetime, tag: str, status: str, detail: str | None = None, **values) -> None:
        columns = {k: v for k, v in values.items() if k in ("kite_id", "child_id", "filled", "average_price")}
        if detail is not None:
            columns["detail"] = detail
        assignments = ", ".join(f"{k} = ?" for k in columns)
        self.conn.execute(f"UPDATE broker_orders SET status = ?, updated_at = ?{', ' + assignments if columns else ''} "
                          "WHERE tag = ?", (status, at.isoformat(), *columns.values(), tag))
        self._event(at, tag, status, detail or "")

    def _event(self, at: datetime, tag: str, status: str, detail: str) -> None:
        self.conn.execute("INSERT INTO broker_events (at, tag, status, detail) VALUES (?, ?, ?, ?)",
                          (at.isoformat(), tag, status, detail))

    def add_fill(self, session: date, tag: str, strategy_id: str, symbol: str, side: str, quantity: int,
                 price: float) -> None:
        self.conn.execute("INSERT INTO live_fills (session, tag, strategy_id, symbol, side, quantity, price) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)", (session.isoformat(), tag, strategy_id, symbol, side,
                                                           quantity, price))

    def add_capital_step(self, session: date, capital: float, reason: str) -> None:
        self.conn.execute("INSERT INTO capital_steps (session, capital, reason) VALUES (?, ?, ?)",
                          (session.isoformat(), capital, reason))

    def capital_steps(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM capital_steps ORDER BY id").fetchall()

    def positions(self) -> dict[str, Position]:
        rows = self.conn.execute("SELECT * FROM live_positions ORDER BY symbol").fetchall()
        return {r["symbol"]: Position(r["strategy_id"], r["symbol"], r["quantity"], r["entry_price"], r["stop_price"],
                                      date.fromisoformat(r["entry_session"]), max_hold_days=r["max_hold_days"])
                for r in rows}

    def save_position(self, p: Position) -> None:
        self.conn.execute("INSERT OR REPLACE INTO live_positions VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (p.symbol, p.strategy_id, p.quantity, p.entry_date.isoformat(), p.entry_price, p.stop_price,
                           p.max_hold_days))

    def delete_position(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM live_positions WHERE symbol = ?", (symbol,))

    def table(self, name: str) -> pd.DataFrame:
        if name not in {"broker_orders", "broker_events", "live_fills", "live_positions", "capital_steps"}:
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY rowid", self.conn)

    def ledger_problems(self) -> list[str]:
        """The holdings must equal what the fills add up to."""
        net = {r["symbol"]: r["net"] for r in self.conn.execute(
            "SELECT symbol, SUM(CASE WHEN side = 'buy' THEN quantity ELSE -quantity END) AS net FROM live_fills "
            "GROUP BY symbol")}
        held = {symbol: p.quantity for symbol, p in self.positions().items()}
        return [f"{symbol}: holding {held.get(symbol, 0)} shares but the fills imply {net.get(symbol, 0)}"
                for symbol in sorted(set(held) | {s for s, q in net.items() if q}) if held.get(symbol, 0) != net.get(symbol, 0)]

    def backup(self, directory: Path | str, day: date) -> Path:
        return backup_copy(self.conn, Path(directory) / f"live-{day.isoformat()}.db")


def _stop_tag(path: str) -> str:
    match = STOP_IN_PATH.search(path)
    if match is None:
        raise ValueError(f"no stop named in {path}")
    return match.group(1)


class OMS:
    def __init__(self, store: LiveStore, kite: KiteOrders, clock):
        self.store, self.kite, self.clock = store, kite, clock

    # --- sending ------------------------------------------------------------------------------------
    def submit(self, session: date, strategy_id: str, request: broker.KiteRequest, stop_distance: float = 0.0,
               max_hold_days: int | None = None) -> str:
        """Send one request, at most once; returns its status. A request already on record is never sent again,
        unless Kite has no trace of it after a crash or a lost answer."""
        row = self.store.order(request.tag)
        if row is not None and (row["status"] not in ("SENDING", "UNKNOWN") or self._found(row)):
            return self.store.order(request.tag)["status"]
        problems = broker.problems(request)
        if problems:
            self.store.record(self.clock(), session, strategy_id, request, "REJECTED", "invalid: " + "; ".join(problems))
            return "REJECTED"
        self.store.record(self.clock(), session, strategy_id, request, "SENDING", stop_distance=stop_distance,
                          max_hold_days=max_hold_days)  # on record before it leaves
        try:
            kite_id = self._send(request)
        except OrderRejected as exc:
            self.store.update(self.clock(), request.tag, "REJECTED", str(exc))
        except OutcomeUnknown as exc:
            self.store.update(self.clock(), request.tag, "UNKNOWN", str(exc))
        else:  # a deletion or a change is done once Kite accepts it; an order or a GTT has only begun
            self.store.update(self.clock(), request.tag, "DONE" if request.method in ("DELETE", "PUT") else "SENT",
                              kite_id=kite_id)
        return self.store.order(request.tag)["status"]

    def _send(self, request: broker.KiteRequest) -> str:
        if request.method == "POST" and request.path.startswith("/orders/"):
            return self.kite.place_order(request.path.split("/")[2], request.params)
        if request.method == "POST" and request.path == "/gtt/triggers":
            return self.kite.place_gtt(request.params)
        stop = self.store.order(_stop_tag(request.path))
        if stop is None or not stop["kite_id"]:
            raise OrderRejected("its stop was never placed")
        if request.method == "DELETE":
            return self.kite.delete_gtt(stop["kite_id"])
        if not stop["child_id"]:
            raise OrderRejected("its stop hasn't placed a sell yet")
        return self.kite.modify_order("regular", stop["child_id"], request.params)

    def _found(self, row: sqlite3.Row) -> bool:
        """Whether a request whose fate was unclear reached Kite after all; if so, record what it became."""
        request = json.loads(row["request"])
        method, path, params = request["method"], request["path"], request["params"]
        status, kite_id = None, None
        if method == "POST" and path.startswith("/orders/"):
            match = next((o for o in self.kite.orders() if o.get("tag") == row["tag"]), None)
            status, kite_id = ("SENT", match["order_id"]) if match else (None, None)
        elif method == "POST":
            condition, leg = params["condition"], params["orders"][0]
            match = next((g for g in self.kite.gtts() if g["status"] in ("active", "triggered")
                          and g["condition"]["tradingsymbol"] == condition["tradingsymbol"]
                          and g["condition"]["trigger_values"] == condition["trigger_values"]
                          and g["orders"][0]["quantity"] == leg["quantity"]), None)
            status, kite_id = ("SENT", str(match["id"])) if match else (None, None)
        else:
            stop = self.store.order(_stop_tag(path))
            if method == "DELETE":
                gtt = next((g for g in self.kite.gtts() if str(g["id"]) == stop["kite_id"]), None)
                status = "DONE" if gtt is None or gtt["status"] != "active" else None
            else:
                order = next((o for o in self.kite.orders() if o["order_id"] == stop["child_id"]), None)
                status = "DONE" if order is not None and order["order_type"] == "MARKET" else None
        if status is None:
            return False
        self.store.update(self.clock(), row["tag"], status, "found at Kite after a lost answer",
                          **({"kite_id": kite_id} if kite_id else {}))
        return True

    # --- following up -------------------------------------------------------------------------------
    def refresh(self, session: date) -> list[str]:
        """Bring every unsettled request up to date with Kite and record its fills; returns what happened."""
        pending = self.store.orders(UNSETTLED)
        if not pending:
            return []
        news = []
        orders = {o["order_id"]: o for o in self.kite.orders()}
        gtts = {str(g["id"]): g for g in self.kite.gtts()} if any(r["purpose"] == "stop" for r in pending) else {}
        for row in pending:
            if row["status"] in ("SENDING", "UNKNOWN") and not self._found(row):
                news.append(f"{row['symbol']} {row['purpose']}: Kite has no record of it yet, so it may be sent again")
                continue
            row = self.store.order(row["tag"])
            if row["purpose"] in ORDER_PURPOSES and row["kite_id"] in orders:
                news += self._settle(row, orders[row["kite_id"]], session)
            elif row["purpose"] == "stop" and row["kite_id"] in gtts:
                gtt = gtts[row["kite_id"]]
                child = ((gtt["orders"][0].get("result") or {}).get("order_result") or {}).get("order_id")
                if gtt["status"] == "triggered" and child:
                    if row["status"] != "TRIGGERED":
                        self.store.update(self.clock(), row["tag"], "TRIGGERED", f"sell order {child}", child_id=str(child))
                        news.append(f"{row['symbol']}: the stop was touched and its sell order placed")
                    if str(child) in orders:
                        news += self._settle(self.store.order(row["tag"]), orders[str(child)], session)
                elif gtt["status"] in GTT_GONE:
                    self.store.update(self.clock(), row["tag"], "CANCELLED", f"GTT {gtt['status']}")
        return news

    def _settle(self, row: sqlite3.Row, order: dict, session: date) -> list[str]:
        """Record what became of an order once Kite is done with it."""
        if order["status"] not in ("COMPLETE", "CANCELLED", "REJECTED"):
            return []
        filled, price = int(order.get("filled_quantity") or 0), float(order.get("average_price") or 0)
        side = "buy" if order["transaction_type"] == "BUY" else "sell"
        if filled == 0:
            why = order.get("status_message") or order["status"].lower()
            self.store.update(self.clock(), row["tag"], order["status"], why)
            return [f"{row['symbol']} {row['purpose']} {order['status'].lower()}: {why}"]
        detail = "" if filled == order["quantity"] else f"only {filled} of {order['quantity']} filled"
        with self.store.transaction():  # the fill, the holding and the status change together or not at all
            self.store.add_fill(session, row["tag"], row["strategy_id"], row["symbol"], side, filled, price)
            self._hold(row, side, filled, price, session)
            self.store.update(self.clock(), row["tag"], "DONE", detail, filled=filled, average_price=price)
        return [f"{row['symbol']} {row['purpose']}: {side} {filled} at {price:,.2f}" + (f" ({detail})" if detail else "")]

    def _hold(self, row: sqlite3.Row, side: str, quantity: int, price: float, session: date) -> None:
        held = self.store.positions().get(row["symbol"])
        if side == "buy":
            if held is None:
                held = Position(row["strategy_id"], row["symbol"], 0, price, price * (1 - row["stop_distance"]), session,
                                max_hold_days=row["max_hold_days"])
            cost = held.quantity * held.entry_price + quantity * price
            held.quantity += quantity
            held.entry_price = cost / held.quantity
            held.stop_price = held.entry_price * (1 - row["stop_distance"])
            self.store.save_position(held)
        elif held is not None:
            held.quantity -= quantity
            if held.quantity > 0:
                self.store.save_position(held)
            else:
                self.store.delete_position(row["symbol"])

    # --- checking -----------------------------------------------------------------------------------
    def reconcile(self) -> list[str]:
        """Every share the system believes it holds must be in the account. The account may hold more: shares
        you bought yourself stay yours, and the system never sells more than its own."""
        problems = self.store.ledger_problems()
        positions = self.store.positions()
        if positions:
            holdings, today = self.kite.holdings(), self.kite.positions()
            for symbol, held in positions.items():
                in_account = held_quantity(holdings, today, symbol.removesuffix(".NS"))
                if in_account < held.quantity:
                    problems.append(f"{symbol}: the system holds {held.quantity} shares but the account has {in_account}")
        return problems
