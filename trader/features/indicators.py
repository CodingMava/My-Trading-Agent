"""Indicators used by research strategies. All are causal: a value depends only on bars up to and
including its own, so computing on truncated data gives the same values (tests check this)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple moving average; NaN until `length` bars are available."""
    return series.rolling(length, min_periods=length).mean()


def wilder_average(values: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing: the first value is the simple mean of the first `length` values, then
    avg[t] = avg[t-1] + (x[t] - avg[t-1]) / length. Leading NaNs are skipped."""
    x = values.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < length:
        return pd.Series(out, index=values.index)
    start = valid[0]
    seed = start + length - 1
    if np.isnan(x[start:seed + 1]).any():
        raise ValueError("wilder_average needs consecutive values after the first valid one")
    out[seed] = x[start:seed + 1].mean()
    for i in range(seed + 1, len(x)):
        out[i] = out[i - 1] + (x[i] - out[i - 1]) / length if not np.isnan(x[i]) else out[i - 1]
    return pd.Series(out, index=values.index)


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index, 0-100."""
    change = close.diff()
    gain = wilder_average(change.clip(lower=0), length)
    loss = wilder_average((-change).clip(lower=0), length)
    with np.errstate(divide="ignore", invalid="ignore"):
        value = 100 - 100 / (1 + gain / loss)
    # No losses in the window: 100 if there were gains, 50 if the price didn't move at all.
    value = value.where(loss != 0, np.where(gain > 0, 100.0, 50.0))
    return value.where(gain.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous = close.shift(1)
    ranges = pd.concat([high - low, (high - previous).abs(), (low - previous).abs()], axis=1)
    return ranges.max(axis=1).where(previous.notna())


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    return wilder_average(true_range(high, low, close), length)
