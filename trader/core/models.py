"""Domain objects shared by strategies, risk, portfolio and execution. Long positions only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class TradeIntent:
    """A strategy's wish to buy, before sizing or any risk check."""
    strategy_id: str
    symbol: str
    signal_date: date
    reference_price: float  # the signal day's close; the order fills at the next open
    stop_distance: float  # as a fraction of price
    sector: str = "UNKNOWN"
    avg_traded_value: float | None = None  # average daily traded value (price x volume), in currency
    max_hold_days: int | None = None
    note: str = ""


@dataclass
class Position:
    strategy_id: str
    symbol: str
    quantity: int
    entry_price: float
    stop_price: float
    entry_date: date
    sector: str = "UNKNOWN"
    last_price: float | None = None
    bars_held: int = 0
    max_hold_days: int | None = None

    @property
    def price(self) -> float:
        return self.last_price if self.last_price is not None else self.entry_price

    @property
    def market_value(self) -> float:
        return self.quantity * self.price


@dataclass
class PortfolioState:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)  # by symbol
    peak_equity: float = 0.0
    day_start_equity: float = 0.0

    @property
    def equity(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions.values())

    @property
    def invested(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def sector_value(self, sector: str) -> float:
        return sum(p.market_value for p in self.positions.values() if p.sector == sector)
