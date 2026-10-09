"""Position sizing: the largest whole quantity that respects every per-position limit."""
from __future__ import annotations

import math
from dataclasses import dataclass

from trader.risk.limits import RiskLimits


@dataclass(frozen=True)
class Size:
    quantity: int
    binding: str  # the limit that set the size
    candidates: dict[str, int]  # the quantity each limit alone would allow


def position_size(equity: float, cash: float, price: float, stop_distance: float, limits: RiskLimits,
                  avg_traded_value: float | None = None, lot_size: int = 1,
                  room: dict[str, float] | None = None) -> Size:
    """Quantity such that hitting the stop loses at most risk_per_trade of equity, the position is at
    most max_position of equity, it is paid for in cash (no leverage), and it is a small share of
    the stock's daily trading. `room` adds caps in currency (e.g. what is left under the sector limit).
    Rounded down to whole lots."""
    if not (price > 0 and stop_distance > 0 and equity > 0):
        return Size(0, "invalid input", {})
    candidates = {
        "risk per trade": math.floor(equity * limits.risk_per_trade / (price * stop_distance)),
        "max position": math.floor(equity * limits.max_position / price),
        "cash": math.floor(max(cash, 0.0) / price),
    }
    if avg_traded_value:
        candidates["liquidity"] = math.floor(limits.max_liquidity_share * avg_traded_value / price)
    for name, value in (room or {}).items():
        candidates[name] = math.floor(max(value, 0.0) / price)
    binding = min(candidates, key=candidates.get)
    quantity = max(candidates[binding], 0)
    return Size(quantity - quantity % lot_size, binding, candidates)
