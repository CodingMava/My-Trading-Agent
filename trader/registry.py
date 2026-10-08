"""Strategy registry: decides which strategies may emit live signals.

Fail closed: a strategy missing from config/strategies.toml, or with any status other than
LIVE_SMALL or LIVE, cannot produce a live signal.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from trader.config import CONFIG_DIR

STRATEGIES_FILE = CONFIG_DIR / "strategies.toml"
STATUSES = ("REJECTED", "DISABLED", "RESEARCH", "PAPER", "LIVE_SMALL", "LIVE")
LIVE_STATUSES = frozenset({"LIVE_SMALL", "LIVE"})
FAILED_STATUSES = frozenset({"REJECTED", "DISABLED"})


@dataclass(frozen=True)
class StrategyRecord:
    id: str
    name: str
    status: str
    evidence: str = ""

    @property
    def emits_live_signals(self) -> bool:
        return self.status in LIVE_STATUSES


@dataclass(frozen=True)
class Rejection:
    """A candidate signal the registry blocked (a NO TRADE decision)."""
    signal: dict
    strategy_id: str | None
    status: str
    reason: str


class StrategyRegistry:
    def __init__(self, records: list[StrategyRecord]):
        by_name: dict[str, StrategyRecord] = {}
        for record in records:
            if record.status not in STATUSES:
                raise ValueError(f"{record.id}: unknown status {record.status!r}; expected one of {STATUSES}")
            if record.name in by_name:
                raise ValueError(f"duplicate strategy name {record.name!r}")
            by_name[record.name] = record
        self._by_name = by_name

    @classmethod
    def load(cls, path: Path = STRATEGIES_FILE) -> StrategyRegistry:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls([StrategyRecord(id=key, name=entry["name"], status=entry["status"],
                                   evidence=entry.get("evidence", ""))
                    for key, entry in data.items()])

    def get(self, name: str) -> StrategyRecord | None:
        return self._by_name.get(name)

    def records(self) -> list[StrategyRecord]:
        return list(self._by_name.values())

    def live_strategies(self) -> list[StrategyRecord]:
        return [r for r in self._by_name.values() if r.emits_live_signals]

    def partition(self, signals: list[dict]) -> tuple[list[dict], list[Rejection]]:
        """Split candidate signals (each carrying a 'strategy' name) into (approved, rejected)."""
        approved, rejected = [], []
        for signal in signals:
            record = self.get(signal.get("strategy", ""))
            if record is None:
                rejected.append(Rejection(signal, None, "UNREGISTERED", "strategy is not in config/strategies.toml"))
            elif record.emits_live_signals:
                approved.append(signal)
            elif record.status in FAILED_STATUSES:
                rejected.append(Rejection(signal, record.id, record.status, "strategy failed the profitability gate"))
            else:
                rejected.append(Rejection(signal, record.id, record.status,
                                          f"status {record.status} does not allow live signals"))
        return approved, rejected
