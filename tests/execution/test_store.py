import sqlite3
from datetime import date

import pytest

from trader.core.models import Position
from trader.execution.store import PaperStore

DAY = date(2026, 8, 10)


def test_duplicate_orders_are_refused(tmp_path):
    store = PaperStore(tmp_path / "p.db", 100_000)
    assert store.add_order("T1:AAA:2026-08-10:buy", "T1", "AAA", "buy", 10, DAY, 100.0, 0.05)
    assert not store.add_order("T1:AAA:2026-08-10:buy", "T1", "AAA", "buy", 10, DAY, 100.0, 0.05)
    assert len(store.pending_orders()) == 1


def test_a_failed_transaction_leaves_nothing_behind(tmp_path):
    store = PaperStore(tmp_path / "p.db", 100_000)
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.add_order("k", "T1", "AAA", "buy", 10, DAY, 100.0, 0.05)
            store.set_cash(1.0)
            raise RuntimeError("crash")
    assert store.pending_orders() == [] and store.cash == 100_000


def test_positions_persist_and_reconciliation_catches_drift(tmp_path):
    path = tmp_path / "p.db"
    store = PaperStore(path, 100_000)
    store.add_fill(DAY, None, "T1", "AAA", "buy", 10, 100.0, 1.0, "Entry")
    store.set_cash(100_000 - 1_001)
    store.save_position(Position("T1", "AAA", 10, 100.0, 95.0, DAY, "Tech", last_price=101.0, entry_fees=1.0))
    reopened = PaperStore(path, 999)  # the starting capital is only used when the database is new
    assert reopened.starting_capital == 100_000 and reopened.positions()["AAA"].price == 101.0
    assert reopened.reconcile() == []
    reopened.set_cash(50_000)
    reopened.save_position(Position("T1", "AAA", 12, 100.0, 95.0, DAY, "Tech"))
    problems = reopened.reconcile()
    assert len(problems) == 2 and "cash" in problems[0] and "AAA" in problems[1]


def test_the_record_of_what_happened_can_only_be_added_to(tmp_path):
    store = PaperStore(tmp_path / "p.db", 100_000)
    store.add_fill(DAY, None, "T1", "AAA", "buy", 10, 100.0, 1.0, "Entry")
    store.add_decision(DAY, "T1", "AAA", "BUY_SIGNAL", "10 shares")
    store.record_session(DAY, 100_000, 99_000)
    store.add_trade("T1", "AAA", 10, DAY, 100.0, DAY, 101.0, "Time Exit", 2.0, 8.0, 0.008, 0.16)
    for statement in ("UPDATE fills SET price = 1", "DELETE FROM fills", "UPDATE trades SET net_pnl = 1e6",
                      "DELETE FROM decisions", "UPDATE sessions SET equity = 1", "DELETE FROM sessions"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            store.conn.execute(statement)
    store.save_position(Position("T1", "AAA", 10, 100.0, 95.0, DAY))
    store.delete_position("AAA")  # live state (positions, orders, cash) still changes as it must
    assert store.positions() == {}


def test_a_backup_is_a_complete_consistent_copy(tmp_path):
    store = PaperStore(tmp_path / "p.db", 100_000)
    store.add_fill(DAY, None, "T1", "AAA", "buy", 10, 100.0, 1.0, "Entry")
    store.set_cash(100_000 - 1_001)
    store.save_position(Position("T1", "AAA", 10, 100.0, 95.0, DAY, entry_fees=1.0))
    path = store.backup(tmp_path / "backups", date(2026, 10, 12))
    assert path.name == "paper-2026-10-12.db" and [p.name for p in path.parent.iterdir()] == [path.name]
    copy = PaperStore(path, 1)
    assert copy.cash == 100_000 - 1_001 and len(copy.table("fills")) == 1 and copy.reconcile() == []
    copy.close()
    store.add_fill(DAY, None, "T1", "BBB", "buy", 1, 50.0, 0.1, "Entry")
    store.backup(tmp_path / "backups", date(2026, 10, 12))  # the same day again: replaced, not duplicated
    assert len(list(path.parent.iterdir())) == 1
