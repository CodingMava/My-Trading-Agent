"""The nine rules of the original signal_engine.py, kept verbatim as research fixtures.

The 2026-10-08 audit rejected or disabled every one of them (see config/strategies.toml). They are
kept so the audit can be reproduced, and so tests can prove this copy matches the live code in
signal_engine.evaluate_latest(). Don't build new strategies on top of them.
"""
from __future__ import annotations

import contextlib
import io

import numpy as np
import pandas as pd

from ta_engine import TechnicalAnalyzer  # the exact indicator code that was audited
from trader.research.simulator import ExitRules

RULES = (  # (id, name used in alerts, side), in the original if/elif order
    ("R1", "Volume Breakout", "long"),
    ("R2", "Oversold Reversal", "long"),
    ("R3", "Overbought Breakdown", "short"),
    ("R4", "Turtle Trend Breakout", "long"),
    ("R5", "Tudor Jones Macro Filter", "long"),
    ("R6", "Minervini Momentum Stacking", "long"),
    ("R7", "Stat-Arb Mean Reversion", "long"),
    ("R8L", "Crabel Intraday Expansion", "long"),
    ("R8S", "Crabel Intraday Breakdown", "short"),
)
RULE_IDS = tuple(rule for rule, _, _ in RULES)
NAME = {rule: name for rule, name, _ in RULES}
SIDE = {rule: side for rule, _, side in RULES}

# The original code's fixed bracket (1% stop, 2% target) traded intraday on 5-minute bars.
EXITS = ExitRules(stop=0.01, target=0.02, square_off_each_session=True)


def legacy_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Indicators exactly as signal_engine computed them (TechnicalAnalyzer + Bollinger + Turtle)."""
    with contextlib.redirect_stdout(io.StringIO()):
        a = TechnicalAnalyzer().apply_indicators(raw.copy())
    if "sma_200" not in a.columns:  # fewer than 200 bars: TechnicalAnalyzer returns the raw frame
        return a.iloc[0:0]
    a["bb_mid"] = a["close"].rolling(20).mean()
    a["bb_std"] = a["close"].rolling(20).std()
    a["bb_upper"] = a["bb_mid"] + (2 * a["bb_std"])
    a["bb_lower"] = a["bb_mid"] - (2 * a["bb_std"])
    a["turtle_high"] = a["high"].rolling(20).max().shift(1)
    a["turtle_low"] = a["low"].rolling(20).min().shift(1)
    return a


def legacy_masks(a: pd.DataFrame) -> dict[str, np.ndarray]:
    """Per-bar truth of each rule's condition, evaluated on completed bars only."""
    c, h, l = a["close"], a["high"], a["low"]
    prev_c, prev_sma20 = c.shift(1), a["sma_20"].shift(1)
    ph, pl, p2h, p2l = h.shift(1), l.shift(1), h.shift(2), l.shift(2)
    inside_bar = (ph < p2h) & (pl > p2l)
    masks = {
        "R1": a["breakout_bullish"] & a["vol_spike"],
        "R2": (a["rsi_14"] < 30) & (a["macd"] > a["macd_signal"]),
        "R3": (a["rsi_14"] > 70) & a["breakout_bearish"],
        "R4": (c > a["turtle_high"]) & (a["sma_50"] > a["sma_200"]),
        "R5": (prev_c < prev_sma20) & (c > a["sma_20"]) & (c > a["sma_200"]),
        "R6": (c > a["sma_20"]) & (a["sma_20"] > a["sma_50"]) & (a["sma_50"] > a["sma_200"]) & a["vol_spike"],
        "R7": (c < a["bb_lower"]) & (a["rsi_14"] < 25),
        "R8L": inside_bar & (c > ph),
        "R8S": inside_bar & (c < pl),
    }
    return {rule: m.fillna(False).astype(bool).to_numpy() for rule, m in masks.items()}


def chain_choice(masks: dict[str, np.ndarray], i: int) -> str | None:
    """The rule the original if/elif chain would report at bar i (first true rule wins)."""
    for rule in RULE_IDS:
        if masks[rule][i]:
            return rule
    return None
