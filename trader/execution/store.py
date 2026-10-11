"""Paper-trading state in SQLite: account, orders, fills, positions, closed trades, session snapshots,
decisions, an outbox of notifications, suspended strategies, and the Kite requests of the dry run.

Each session is processed inside one transaction, so a crash leaves the state exactly as it was before
that session and re-running it gives the same result. Order keys are unique (strategy, stock, session,
side), so the same order can never be placed twice. The record of what happened (fills, closed trades,
decisions, session snapshots, dry-run Kite requests) is append-only: the database itself refuses to
change or delete it.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from trader.core.models import Position

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), starting_capital REAL NOT NULL, cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, equity REAL NOT NULL, cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')), quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_session TEXT NOT NULL, reference_price REAL NOT NULL, stop_distance REAL NOT NULL,
    status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', updated_session TEXT);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY, session TEXT NOT NULL, order_id INTEGER, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL,
    side TEXT NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL, fees REAL NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, quantity INTEGER NOT NULL, entry_price REAL NOT NULL,
    stop_price REAL NOT NULL, entry_session TEXT NOT NULL, sector TEXT NOT NULL, last_price REAL NOT NULL,
    bars_held INTEGER NOT NULL, max_hold_days INTEGER, entry_fees REAL NOT NULL);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL, quantity INTEGER NOT NULL,
    entry_session TEXT NOT NULL, entry_price REAL NOT NULL, exit_session TEXT NOT NULL, exit_price REAL NOT NULL,
    reason TEXT NOT NULL, fees REAL NOT NULL, net_pnl REAL NOT NULL, net_return REAL NOT NULL, r_multiple REAL NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY, session TEXT NOT NULL, strategy_id TEXT NOT NULL, symbol TEXT NOT NULL,
    action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, session TEXT NOT NULL, text TEXT NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS suspended (strategy_id TEXT PRIMARY KEY, session TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'ok', 'halted', 'failed')),
    sessions INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS dry_run_orders (id INTEGER PRIMARY KEY, session TEXT NOT NULL, tag TEXT UNIQUE NOT NULL,
    symbol TEXT NOT NULL, purpose TEXT NOT NULL, send_at TEXT NOT NULL, request TEXT NOT NULL,
    problems TEXT NOT NULL DEFAULT '');
CREATE TRIGGER IF NOT EXISTS fills_no_update BEFORE UPDATE ON fills BEGIN SELECT RAISE(ABORT, 'fills are append-only'); END;
CREATE TRIGGER IF NOT EXISTS fills_no_delete BEFORE DELETE ON fills BEGIN SELECT RAISE(ABORT, 'fills are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trades_no_update BEFORE UPDATE ON trades BEGIN SELECT RAISE(ABORT, 'trades are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trades_no_delete BEFORE DELETE ON trades BEGIN SELECT RAISE(ABORT, 'trades are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS sessions_no_update BEFORE UPDATE ON sessions BEGIN SELECT RAISE(ABORT, 'sessions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS sessions_no_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'sessions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS dry_run_no_update BEFORE UPDATE ON dry_run_orders BEGIN SELECT RAISE(ABORT, 'dry-run orders are append-only'); END;
CREATE TRIGGER IF NOT EXISTS dry_run_no_delete BEFORE DELETE ON dry_run_orders BEGIN SELECT RAISE(ABORT, 'dry-run orders are append-only'); END;
"""


def backup_copy(conn: sqlite3.Connection, target: Path) -> Path:
    """A consistent copy of a whole database (SQLite's online backup) at `target`. It is written under a
    temporary name first, so a crash can't leave a half-written backup."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    copy = sqlite3.connect(str(partial))
    try:
        conn.backup(copy)
    finally:
        copy.close()
    os.replace(partial, target)
    return target


@dataclass(frozen=True)
class Order:
    id: int
    key: str
    strategy_id: str
    symbol: str
    side: str
    quantity: int
    created_session: date
    reference_price: float
    stop_distance: float
    status: str
    note: str


class PaperStore:
    def __init__(self, path: Path | str, starting_capital: float):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)  # explicit transactions below
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if self.conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0:
            self.conn.execute("INSERT INTO account (id, starting_capital, cash) VALUES (1, ?, ?)",
                              (starting_capital, starting_capital))

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

    # account and sessions
    @property
    def starting_capital(self) -> float:
        return self.conn.execute("SELECT starting_capital FROM account").fetchone()[0]

    @property
    def cash(self) -> float:
        return self.conn.execute("SELECT cash FROM account").fetchone()[0]

    def set_cash(self, value: float) -> None:
        self.conn.execute("UPDATE account SET cash = ?", (value,))

    def last_session(self) -> date | None:
        value = self.conn.execute("SELECT MAX(session) FROM sessions").fetchone()[0]
        return date.fromisoformat(value) if value else None

    def record_session(self, session: date, equity: float, cash: float) -> None:
        self.conn.execute("INSERT INTO sessions (session, equity, cash) VALUES (?, ?, ?)", (session.isoformat(), equity, cash))

    def equity_history(self) -> pd.Series:
        rows = self.conn.execute("SELECT session, equity FROM sessions ORDER BY session").fetchall()
        return pd.Series({date.fromisoformat(r["session"]): r["equity"] for r in rows}, dtype=float)

    # positions
    def positions(self) -> dict[str, Position]:
        rows = self.conn.execute("SELECT * FROM positions ORDER BY symbol").fetchall()
        return {r["symbol"]: Position(r["strategy_id"], r["symbol"], r["quantity"], r["entry_price"], r["stop_price"],
                                      date.fromisoformat(r["entry_session"]), r["sector"], r["last_price"],
                                      r["bars_held"], r["max_hold_days"], r["entry_fees"]) for r in rows}

    def save_position(self, p: Position) -> None:
        self.conn.execute("INSERT OR REPLACE INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (p.symbol, p.strategy_id, p.quantity, p.entry_price, p.stop_price, p.entry_date.isoformat(),
                           p.sector, p.price, p.bars_held, p.max_hold_days, p.entry_fees))

    def delete_position(self, symbol: str) -> None:
        self.conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))

    # orders and fills
    def add_order(self, key: str, strategy_id: str, symbol: str, side: str, quantity: int, session: date,
                  reference_price: float, stop_distance: float, note: str = "") -> bool:
        """False if an order with this key already exists (duplicate-order protection)."""
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO orders (key, strategy_id, symbol, side, quantity, created_session, reference_price, "
            "stop_distance, status, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)",
            (key, strategy_id, symbol, side, quantity, session.isoformat(), reference_price, stop_distance, note))
        return cursor.rowcount == 1

    def pending_orders(self, side: str | None = None) -> list[Order]:
        query, args = "SELECT * FROM orders WHERE status = 'NEW'", []
        if side:
            query, args = query + " AND side = ?", [side]
        rows = self.conn.execute(query + " ORDER BY id", args).fetchall()
        return [Order(r["id"], r["key"], r["strategy_id"], r["symbol"], r["side"], r["quantity"],
                      date.fromisoformat(r["created_session"]), r["reference_price"], r["stop_distance"], r["status"],
                      r["note"]) for r in rows]

    def set_order_status(self, order_id: int, status: str, session: date, note: str | None = None) -> None:
        self.conn.execute("UPDATE orders SET status = ?, updated_session = ?, note = COALESCE(?, note) WHERE id = ?",
                          (status, session.isoformat(), note, order_id))

    def add_fill(self, session: date, order_id: int | None, strategy_id: str, symbol: str, side: str, quantity: int,
                 price: float, fees: float, reason: str) -> None:
        self.conn.execute("INSERT INTO fills (session, order_id, strategy_id, symbol, side, quantity, price, fees, reason) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (session.isoformat(), order_id, strategy_id, symbol, side, quantity, price, fees, reason))

    def add_trade(self, strategy_id: str, symbol: str, quantity: int, entry_session: date, entry_price: float,
                  exit_session: date, exit_price: float, reason: str, fees: float, net_pnl: float, net_return: float,
                  r_multiple: float) -> None:
        self.conn.execute("INSERT INTO trades (strategy_id, symbol, quantity, entry_session, entry_price, exit_session, "
                          "exit_price, reason, fees, net_pnl, net_return, r_multiple) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (strategy_id, symbol, quantity, entry_session.isoformat(), entry_price, exit_session.isoformat(),
                           exit_price, reason, fees, net_pnl, net_return, r_multiple))

    def trades(self, strategy_id: str | None = None) -> pd.DataFrame:
        query, args = "SELECT * FROM trades", []
        if strategy_id:
            query, args = query + " WHERE strategy_id = ?", [strategy_id]
        return pd.read_sql_query(query + " ORDER BY id", self.conn, params=args)

    def table(self, name: str) -> pd.DataFrame:
        if name not in {"orders", "fills", "positions", "trades", "decisions", "outbox", "sessions", "suspended", "runs",
                        "dry_run_orders"}:
            raise ValueError(name)
        return pd.read_sql_query(f"SELECT * FROM {name} ORDER BY rowid", self.conn)

    # decisions, notifications, suspensions
    def add_decision(self, session: date, strategy_id: str, symbol: str, action: str, detail: str) -> None:
        self.conn.execute("INSERT INTO decisions (session, strategy_id, symbol, action, detail) VALUES (?, ?, ?, ?, ?)",
                          (session.isoformat(), strategy_id, symbol, action, detail))

    def queue_message(self, session: date, text: str) -> None:
        self.conn.execute("INSERT INTO outbox (session, text) VALUES (?, ?)", (session.isoformat(), text))

    def unsent_messages(self) -> list[tuple[int, str]]:
        return [(r["id"], r["text"]) for r in self.conn.execute("SELECT id, text FROM outbox WHERE sent = 0 ORDER BY id")]

    def mark_sent(self, message_id: int) -> None:
        self.conn.execute("UPDATE outbox SET sent = 1 WHERE id = ?", (message_id,))

    def add_dry_run_order(self, session: date, tag: str, symbol: str, purpose: str, send_at: str, request: str,
                          problems: str = "") -> None:
        """A Kite request the dry run prepared (never sent). Its tag is unique, so preparing the same step twice
        fails the session instead of recording a second request."""
        self.conn.execute("INSERT INTO dry_run_orders (session, tag, symbol, purpose, send_at, request, problems) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)", (session.isoformat(), tag, symbol, purpose, send_at, request, problems))

    def suspend(self, strategy_id: str, session: date, reason: str) -> None:
        self.conn.execute("INSERT OR IGNORE INTO suspended VALUES (?, ?, ?)", (strategy_id, session.isoformat(), reason))

    def suspended(self) -> dict[str, str]:
        return {r["strategy_id"]: r["reason"] for r in self.conn.execute("SELECT * FROM suspended")}

    def backup(self, directory: Path | str, day: date) -> Path:
        """A consistent copy of the whole database as <directory>/paper-<day>.db."""
        return backup_copy(self.conn, Path(directory) / f"paper-{day.isoformat()}.db")

    # runs: one row per unattended run, for monitoring
    def start_run(self, started_at: datetime) -> int:
        return self.conn.execute("INSERT INTO runs (started_at, status) VALUES (?, 'running')",
                                 (started_at.isoformat(),)).lastrowid

    def finish_run(self, run_id: int, status: str, finished_at: datetime, sessions: int = 0, detail: str = "") -> None:
        self.conn.execute("UPDATE runs SET status = ?, finished_at = ?, sessions = ?, detail = ? WHERE id = ?",
                          (status, finished_at.isoformat(), sessions, detail, run_id))

    def runs(self, limit: int = 200) -> pd.DataFrame:
        """The latest runs, newest first."""
        return pd.read_sql_query("SELECT * FROM runs ORDER BY id DESC LIMIT ?", self.conn, params=[limit])

    def reconcile(self, tolerance: float = 0.01) -> list[str]:
        """Rebuild cash and holdings from the fills and compare them with the stored state."""
        problems = []
        flows = self.conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN side = 'buy' THEN -(quantity * price + fees) "
            "ELSE quantity * price - fees END), 0) FROM fills").fetchone()[0]
        expected_cash = self.starting_capital + flows
        if abs(expected_cash - self.cash) > tolerance:
            problems.append(f"cash is {self.cash:,.2f} but the fills imply {expected_cash:,.2f}")
        held = {r["symbol"]: r["quantity"] for r in self.conn.execute("SELECT symbol, quantity FROM positions")}
        net = {r["symbol"]: r["net"] for r in self.conn.execute(
            "SELECT symbol, SUM(CASE WHEN side = 'buy' THEN quantity ELSE -quantity END) AS net FROM fills GROUP BY symbol")}
        for symbol in sorted(set(held) | {s for s, q in net.items() if q}):
            if held.get(symbol, 0) != net.get(symbol, 0):
                problems.append(f"{symbol}: holding {held.get(symbol, 0)} shares but the fills imply {net.get(symbol, 0)}")
        return problems
