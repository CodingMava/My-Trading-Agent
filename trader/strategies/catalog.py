"""Strategies the paper-trading (and later live) engine knows how to run.

Being listed here doesn't let a strategy trade: it also needs a status in config/strategies.toml that
its evidence supports (PAPER for paper trading). Cross-sectional strategies such as H3 need a
portfolio-level runner and aren't listed.
"""
from __future__ import annotations

import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from trader.config import CONFIG_DIR
from trader.research.costs import ZERODHA_DELIVERY, ZERODHA_ETF_DELIVERY, CostModel
from trader.strategies.swing import PULLBACK, Signals, pullback_signals

UNIVERSES_FILE = CONFIG_DIR / "universes.toml"


@dataclass(frozen=True)
class StrategySpec:
    id: str
    universe: str  # a key in config/universes.toml
    signals: Callable[[pd.DataFrame], Signals]
    max_hold_days: int
    costs: CostModel
    exit_note: str  # how positions are exited, for messages


def load_universes(path: Path = UNIVERSES_FILE) -> dict[str, list[str]]:
    with open(path, "rb") as fh:
        return {name: list(symbols) for name, symbols in tomllib.load(fh).items()}


_PULLBACK_EXIT = (f"the first close above the {PULLBACK.exit_sma}-day average, a {PULLBACK.atr_stop:g} x ATR stop, "
                  f"or {PULLBACK.max_hold_days} trading days")

CATALOG: dict[str, StrategySpec] = {
    "H1": StrategySpec("H1", "nifty50", pullback_signals, PULLBACK.max_hold_days, ZERODHA_DELIVERY, _PULLBACK_EXIT),
    "H2": StrategySpec("H2", "nifty_etf", pullback_signals, PULLBACK.max_hold_days, ZERODHA_ETF_DELIVERY,
                       _PULLBACK_EXIT),
}
