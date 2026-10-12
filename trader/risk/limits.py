"""Risk limits from config/risk.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from trader.config import CONFIG_DIR

RISK_FILE = CONFIG_DIR / "risk.toml"


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade: float = 0.005
    max_position: float = 0.20
    max_positions: int = 5
    max_gross_exposure: float = 1.0
    max_sector_exposure: float = 0.40
    max_correlation: float = 0.80
    max_daily_loss: float = 0.02
    max_drawdown: float = 0.10
    max_stop_distance: float = 0.15
    min_notional: float = 25_000
    max_liquidity_share: float = 0.01

    def __post_init__(self):
        for f in fields(self):
            if not getattr(self, f.name) > 0:
                raise ValueError(f"risk limit {f.name} must be positive")
        if self.risk_per_trade > 0.02:
            raise ValueError("risk_per_trade above 2% of equity is not allowed")


def load_limits(path: Path = RISK_FILE, market: str = "NSE") -> RiskLimits:
    """[limits], with a market's own [limits.<market>] values over them (an amount in its currency, say)."""
    with open(path, "rb") as fh:
        raw = tomllib.load(fh).get("limits", {})
    base = {key: value for key, value in raw.items() if not isinstance(value, dict)}
    return RiskLimits(**{**base, **raw.get(market, {})})
