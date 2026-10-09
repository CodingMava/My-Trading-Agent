"""Strategy registry: decides which strategies may emit live signals.

Fail closed: a strategy missing from config/strategies.toml, or with any status other than
LIVE_SMALL or LIVE, cannot produce a live signal. On load, every status is checked against the
evidence on file (trader/gate.py): a strategy whose evidence doesn't support its status is lowered
to the status it does support, and the reason is kept in `problems`.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from datetime import date
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
    def __init__(self, records: list[StrategyRecord], problems: list[str] | None = None):
        by_name: dict[str, StrategyRecord] = {}
        for record in records:
            if record.status not in STATUSES:
                raise ValueError(f"{record.id}: unknown status {record.status!r}; expected one of {STATUSES}")
            if record.name in by_name:
                raise ValueError(f"duplicate strategy name {record.name!r}")
            by_name[record.name] = record
        self._by_name = by_name
        self.problems = list(problems or [])

    @classmethod
    def load(cls, path: Path = STRATEGIES_FILE, enforce_evidence: bool = True, evidence_dir: Path | None = None,
             today: date | None = None) -> StrategyRegistry:
        """Read config/strategies.toml and, unless told otherwise, hold every status to its evidence."""
        from trader.gate import EVIDENCE_DIR, load_gate_config, supported_status

        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        records = [StrategyRecord(id=key, name=entry["name"], status=entry["status"], evidence=entry.get("evidence", ""))
                   for key, entry in data.items()]
        problems = []
        if enforce_evidence:
            gate, today = load_gate_config(), today or date.today()
            checked = []
            for record in records:
                if record.status not in STATUSES:
                    raise ValueError(f"{record.id}: unknown status {record.status!r}; expected one of {STATUSES}")
                status, problem = supported_status(record.status, record.id, today, gate, evidence_dir or EVIDENCE_DIR)
                if problem:
                    problems.append(f"{record.id} ({record.name}) lowered from {record.status} to {status}: {problem}")
                checked.append(replace(record, status=status))
            records = checked
        return cls(records, problems)

    def get(self, name: str) -> StrategyRecord | None:
        return self._by_name.get(name)

    def get_by_id(self, strategy_id: str) -> StrategyRecord | None:
        return next((r for r in self._by_name.values() if r.id == strategy_id), None)

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
