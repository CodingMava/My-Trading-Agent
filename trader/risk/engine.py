"""The risk engine: every trade intent passes through here before it can become an order.

It sizes the position within every limit, then checks the limits again and records each result.
Any failure means NO TRADE (quantity 0) with the reason kept. A drawdown beyond the limit engages
the kill switch, which blocks all new trades until a person releases it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.core.models import PortfolioState, TradeIntent
from trader.portfolio.exposure import most_correlated
from trader.portfolio.sizing import position_size
from trader.risk.killswitch import KillSwitch
from trader.risk.limits import RiskLimits

TOLERANCE = 1e-9


def pct(fraction: float) -> str:
    """A configured limit as a percentage without false rounding (0.002 -> 0.2%, 0.4 -> 40%)."""
    return f"{fraction * 100:g}%"


@dataclass(frozen=True)
class RiskCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: int
    checks: tuple[RiskCheck, ...]

    @property
    def reason(self) -> str:
        failed = [c for c in self.checks if not c.passed]
        return failed[0].detail if failed else "approved"


class RiskEngine:
    def __init__(self, limits: RiskLimits, kill_switch: KillSwitch, account: str = ""):
        # `account` names the account in the kill switch's reason: one switch blocks every account (US)
        self.limits, self.kill_switch, self.account = limits, kill_switch, account

    def account_checks(self, state: PortfolioState) -> list[RiskCheck]:
        """May the account take on any new risk? Engages the kill switch on a drawdown breach."""
        limits, equity = self.limits, state.equity
        peak = max(state.peak_equity, equity)
        drawdown = equity / peak - 1 if peak > 0 else 0.0
        if drawdown <= -limits.max_drawdown:
            self.kill_switch.engage(f"{self.account + ' account ' if self.account else ''}drawdown {drawdown:.1%} "
                                    f"breached the {pct(limits.max_drawdown)} limit")
        today = equity / state.day_start_equity - 1 if state.day_start_equity > 0 else 0.0
        engaged = self.kill_switch.engaged
        return [
            RiskCheck("kill switch", not engaged, f"kill switch engaged: {self.kill_switch.reason}" if engaged else "off"),
            RiskCheck("drawdown", drawdown > -limits.max_drawdown,
                      f"drawdown {drawdown:.1%} from peak (limit {pct(limits.max_drawdown)})"),
            RiskCheck("daily loss", today > -limits.max_daily_loss,
                      f"today {today:+.1%} (no new entries below -{pct(limits.max_daily_loss)})"),
        ]

    def evaluate(self, intent: TradeIntent, state: PortfolioState,
                 returns: dict[str, pd.Series] | None = None) -> RiskDecision:
        """Size and check one intent. `returns` (daily returns by symbol) enables the correlation check."""
        limits, equity, price = self.limits, state.equity, intent.reference_price
        checks = self.account_checks(state)
        stop_ok = bool(0 < intent.stop_distance <= limits.max_stop_distance)
        checks.append(RiskCheck("stop", stop_ok, f"stop {intent.stop_distance:.1%} below entry "
                                                 f"(must be above 0 and at most {pct(limits.max_stop_distance)})"))
        held = intent.symbol in state.positions
        checks.append(RiskCheck("one position per stock", not held,
                                f"already holding {intent.symbol}" if held else "not held"))
        checks.append(RiskCheck("position count", len(state.positions) < limits.max_positions,
                                f"{len(state.positions)} of {limits.max_positions} positions open"))

        room = {"sector limit": limits.max_sector_exposure * equity - state.sector_value(intent.sector),
                "gross exposure": limits.max_gross_exposure * equity - state.invested}
        size = position_size(equity, state.cash, price, intent.stop_distance if stop_ok else 0.0, limits,
                             intent.avg_traded_value, room=room)
        notional = size.quantity * price
        checks.append(RiskCheck("size", size.quantity >= 1 and notional >= limits.min_notional,
                                f"{size.quantity} shares = Rs {notional:,.0f}, set by {size.binding} "
                                f"(minimum Rs {limits.min_notional:,.0f})"))
        sector_after = (state.sector_value(intent.sector) + notional) / equity if equity > 0 else np.inf
        checks.append(RiskCheck("sector exposure", sector_after <= limits.max_sector_exposure + TOLERANCE,
                                f"{intent.sector} at {sector_after:.0%} of equity after the trade "
                                f"(limit {pct(limits.max_sector_exposure)})"))
        gross_after = (state.invested + notional) / equity if equity > 0 else np.inf
        checks.append(RiskCheck("gross exposure", gross_after <= limits.max_gross_exposure + TOLERANCE,
                                f"{gross_after:.0%} of equity invested after the trade "
                                f"(limit {pct(limits.max_gross_exposure)})"))
        if returns and intent.symbol in returns:
            holdings = {s: returns[s] for s in state.positions if s in returns}
            other, value = most_correlated(returns[intent.symbol], holdings)
            checks.append(RiskCheck("correlation", not value > limits.max_correlation,
                                    f"{value:.2f} with {other} (limit {limits.max_correlation})" if other
                                    else "no open position with enough shared history"))
        approved = all(c.passed for c in checks)
        return RiskDecision(approved, size.quantity if approved else 0, tuple(checks))
