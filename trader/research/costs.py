"""Transaction-cost models. Every backtest pays these; results are reported net of costs.

Rates change: budgets revise STT, exchanges revise fees, brokers revise DP charges. Each preset
records when it was last checked. Update the preset; never hard-code a cost inside a backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CostModel:
    name: str
    brokerage_rate: float = 0.0  # per order, fraction of order value
    brokerage_cap: float | None = None  # per order, in currency (e.g. Rs 20 for Zerodha intraday)
    stt_buy: float = 0.0  # securities transaction tax, fraction of buy value
    stt_sell: float = 0.0
    exchange_rate: float = 0.0  # exchange transaction charge, per side
    sebi_rate: float = 0.0  # SEBI turnover fee, per side
    stamp_buy: float = 0.0  # stamp duty on the buy side
    gst_rate: float = 0.0  # GST on brokerage + exchange + SEBI charges
    sell_fee_rate: float = 0.0  # e.g. the US SEC Section 31 fee on sale proceeds
    fixed_per_sell: float = 0.0  # e.g. Zerodha's DP charge per scrip per sell day (GST included)
    slippage_per_side: float = 0.0  # spread + slippage assumption, fraction per side
    verified: str = ""

    def breakdown(self, notional: float) -> dict[str, float]:
        """Round-trip costs, in currency, of buying and then selling `notional` worth of stock."""
        if notional <= 0:
            raise ValueError("notional must be positive")
        per_order = self.brokerage_rate * notional
        if self.brokerage_cap is not None:
            per_order = min(per_order, self.brokerage_cap)
        brokerage = 2 * per_order
        exchange = 2 * self.exchange_rate * notional
        sebi = 2 * self.sebi_rate * notional
        return {
            "brokerage": brokerage,
            "stt": (self.stt_buy + self.stt_sell) * notional,
            "exchange": exchange,
            "sebi": sebi,
            "gst": self.gst_rate * (brokerage + exchange + sebi),
            "stamp": self.stamp_buy * notional,
            "sell_fees": self.sell_fee_rate * notional + self.fixed_per_sell,
            "slippage": 2 * self.slippage_per_side * notional,
        }

    def one_side(self, notional: float, side: str) -> float:
        """Costs in currency for a single order ("buy" or "sell"); a buy plus a sell of the same
        notional adds up to breakdown()'s total."""
        if notional <= 0:
            raise ValueError("notional must be positive")
        brokerage = self.brokerage_rate * notional
        if self.brokerage_cap is not None:
            brokerage = min(brokerage, self.brokerage_cap)
        fees = (self.exchange_rate + self.sebi_rate) * notional
        if side == "buy":
            taxes = (self.stt_buy + self.stamp_buy) * notional
        elif side == "sell":
            taxes = (self.stt_sell + self.sell_fee_rate) * notional + self.fixed_per_sell
        else:
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        return brokerage + fees + self.gst_rate * (brokerage + fees) + taxes + self.slippage_per_side * notional

    def round_trip(self, notional: float) -> float:
        """Round-trip cost as a fraction of notional: what a backtest subtracts from each trade."""
        return sum(self.breakdown(notional).values()) / notional

    def with_slippage(self, per_side: float) -> CostModel:
        return replace(self, slippage_per_side=per_side)


# NSE intraday equity (MIS) at Zerodha. Check zerodha.com/charges before relying on these numbers.
ZERODHA_INTRADAY = CostModel(
    name="NSE intraday (Zerodha MIS)", brokerage_rate=0.0003, brokerage_cap=20.0, stt_sell=0.00025,
    exchange_rate=0.0000297, sebi_rate=0.000001, stamp_buy=0.00003, gst_rate=0.18,
    slippage_per_side=0.0003, verified="2026-10-08",
)

# NSE delivery equity (CNC) at Zerodha: the default for swing trades. Brokerage is zero, but STT is
# 0.1% on both sides, and the DP charge is a fixed amount per scrip per sell day, which makes small
# positions expensive.
ZERODHA_DELIVERY = CostModel(
    name="NSE delivery (Zerodha CNC)", stt_buy=0.001, stt_sell=0.001, exchange_rate=0.0000297,
    sebi_rate=0.000001, stamp_buy=0.00015, gst_rate=0.18, fixed_per_sell=15.34,
    slippage_per_side=0.0003, verified="2026-10-08",
)

# Equity ETFs (e.g. a NIFTY 50 ETF) on delivery at Zerodha: STT is only 0.001% and only on the sell
# side, about a hundredth of the rate on stocks; other charges as for stocks.
ZERODHA_ETF_DELIVERY = CostModel(
    name="NSE equity ETF delivery (Zerodha)", stt_sell=0.00001, exchange_rate=0.0000297,
    sebi_rate=0.000001, stamp_buy=0.00015, gst_rate=0.18, fixed_per_sell=15.34,
    slippage_per_side=0.0003, verified="2026-10-09",
)

# US equities at a commission-free broker (US trades are placed manually). Check the current SEC
# Section 31 rate; FINRA's per-share TAF is negligible at these sizes and is ignored.
US_COMMISSION_FREE = CostModel(
    name="US equities (commission-free broker)", sell_fee_rate=0.0000278, slippage_per_side=0.0002,
    verified="2026-10-08",
)

# The exact round-trip fractions the 2026-10-08 audit used, kept so the audit reproduces exactly.
AUDIT_2026_10_08 = {
    "india_intraday": {"base": 0.000825 + 2 * 0.0003, "stress": 0.000825 + 2 * 0.0005},
    "us_intraday": {"base": 0.00003 + 2 * 0.0002, "stress": 0.00003 + 2 * 0.0004},
    "india_delivery": 0.001 * 2 + 0.00015 + 0.0000594 + 0.0002 + 2 * 0.0003,
}
