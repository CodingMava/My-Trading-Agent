"""Sector membership and return correlation, for the risk engine's exposure checks."""
from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import CONFIG_DIR

SECTORS_FILE = CONFIG_DIR / "sectors.toml"
CORRELATION_DAYS = 60
MIN_OVERLAP = 40


def load_sectors(path: Path = SECTORS_FILE) -> dict[str, str]:
    with open(path, "rb") as fh:
        return dict(tomllib.load(fh).get("sectors", {}))


def sector_of(symbol: str, sectors: dict[str, str]) -> str:
    return sectors.get(symbol, "UNKNOWN")


def correlation(a: pd.Series, b: pd.Series, days: int = CORRELATION_DAYS) -> float:
    """Correlation of two daily-return series over their last `days` common dates (NaN if too short)."""
    joined = pd.concat([a, b], axis=1, join="inner").dropna().tail(days)
    if len(joined) < MIN_OVERLAP:
        return np.nan
    return float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def most_correlated(candidate: pd.Series, holdings: dict[str, pd.Series]) -> tuple[str | None, float]:
    """The open position whose returns move most closely with the candidate's, and that correlation."""
    best, value = None, -np.inf
    for symbol, returns in holdings.items():
        c = correlation(candidate, returns)
        if not np.isnan(c) and c > value:
            best, value = symbol, c
    return best, (value if best else np.nan)
