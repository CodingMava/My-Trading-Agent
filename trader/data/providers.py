"""Where bars come from. Every provider returns the same shape: a timezone-aware DatetimeIndex in
exchange time and lowercase open/high/low/close/volume columns, for bars with start <= time < end."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd

from trader.data.intervals import check_interval

OHLCV = ["open", "high", "low", "close", "volume"]


class MarketDataProvider(Protocol):
    name: str

    def history(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame: ...


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Lowercase OHLCV columns only (drops extras such as dividends and splits)."""
    if frame.empty:
        return pd.DataFrame(columns=OHLCV)
    frame = frame.rename(columns=lambda c: str(c).lower())
    missing = [c for c in OHLCV if c not in frame.columns]
    if missing:
        raise ValueError(f"provider returned no {', '.join(missing)} column(s)")
    return frame[OHLCV]


class YahooProvider:
    """Yahoo Finance via yfinance: free and unofficial, split- and dividend-adjusted. Fine for research.
    For live NSE decisions prefer Kite: Yahoo's NSE 5-minute bars lack opening-bar volume and often the
    last minutes of each session, and intraday history only reaches back about 60 days."""
    name = "yahoo"

    def history(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        import yfinance as yf

        check_interval(interval)
        return normalize(yf.Ticker(symbol).history(interval=interval, start=start, end=end))


def fetch_many(provider: MarketDataProvider, symbols, interval: str, start: datetime,
               end: datetime) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Fetch every symbol; one failure doesn't stop the rest. Returns (frames, failures)."""
    frames, failures = {}, {}
    for symbol in symbols:
        try:
            frame = provider.history(symbol, interval, start, end)
        except Exception as exc:
            failures[symbol] = f"{type(exc).__name__}: {exc}"
            continue
        if frame.empty:
            failures[symbol] = "no data returned"
        else:
            frames[symbol] = frame
    return frames, failures


def make_provider(settings) -> MarketDataProvider:
    """The provider chosen in config/settings.toml ([data] provider)."""
    if settings.data_provider == "kite":
        from trader.data.kite import provider_from_settings
        return provider_from_settings(settings)
    return YahooProvider()
