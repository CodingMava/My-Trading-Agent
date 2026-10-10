"""Read-only views for the ops dashboard (dashboard.py). Nothing here can trade or change state."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from trader.execution.store import PaperStore
from trader.gate import EVIDENCE_DIR, load_evidence
from trader.registry import StrategyRegistry


def strategy_table(registry: StrategyRegistry, evidence_dir: Path = EVIDENCE_DIR) -> pd.DataFrame:
    """Every registered strategy with its status and its research verdict, if it has one."""
    rows = []
    for record in registry.records():
        evidence = load_evidence(record.id, "research", evidence_dir)
        stats = (evidence.stats or {}) if evidence else {}
        rows.append({"Strategy": record.id, "Name": record.name, "Status": record.status,
                     "Research verdict": evidence.decision if evidence else "",
                     "Trades": stats.get("holdout_trades"), "Win rate": stats.get("holdout_win_rate"),
                     "Net per trade": stats.get("holdout_mean_net"),
                     "Evidence date": evidence.generated if evidence else ""})
    return pd.DataFrame(rows)


def account(store: PaperStore) -> dict:
    """Headline numbers for the paper account."""
    history = store.equity_history()
    equity = float(history.iloc[-1]) if len(history) else store.starting_capital
    return {"equity": equity, "cash": store.cash, "return": equity / store.starting_capital - 1,
            "positions": len(store.positions()), "last_session": store.last_session()}


def positions_table(store: PaperStore) -> pd.DataFrame:
    return pd.DataFrame([{"Stock": p.symbol, "Strategy": p.strategy_id, "Quantity": p.quantity,
                          "Entry": p.entry_price, "Last": p.price, "Stop": p.stop_price, "Value": p.market_value,
                          "P&L": p.quantity * (p.price - p.entry_price) - p.entry_fees,
                          "Since": p.entry_date, "Days held": p.bars_held}
                         for p in store.positions().values()])


def newest_first(frame: pd.DataFrame, limit: int = 200) -> pd.DataFrame:
    return frame.iloc[::-1].head(limit).reset_index(drop=True)
