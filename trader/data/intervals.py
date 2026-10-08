"""Bar intervals, written the Yahoo way: "5m", "1h", "1d"."""
from __future__ import annotations

import pandas as pd

DAILY = "1d"
_MINUTES = {"1m": 1, "2m": 2, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60, "90m": 90, "1h": 60}


def is_daily(interval: str) -> bool:
    return interval == DAILY


def bar_length(interval: str) -> pd.Timedelta:
    """Length of an intraday bar."""
    if interval not in _MINUTES:
        raise ValueError(f"unsupported intraday interval {interval!r}; use one of {sorted(_MINUTES)}")
    return pd.Timedelta(minutes=_MINUTES[interval])


def check_interval(interval: str) -> str:
    if not is_daily(interval):
        bar_length(interval)
    return interval
