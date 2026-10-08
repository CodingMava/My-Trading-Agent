from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from tests.helpers import session_bars
from trader.config import load_settings
from trader.data.kite import KiteAuthError
from trader.data.providers import OHLCV, YahooProvider, fetch_many, make_provider

IST = ZoneInfo("Asia/Kolkata")
START, END = datetime(2026, 10, 9, 9, 0, tzinfo=IST), datetime(2026, 10, 9, 16, 0, tzinfo=IST)


def test_yahoo_provider_returns_lowercase_ohlcv_only(monkeypatch):
    import yfinance

    seen = {}

    class FakeTicker:
        def __init__(self, symbol):
            seen["symbol"] = symbol

        def history(self, **kwargs):
            seen.update(kwargs)
            index = pd.date_range("2026-10-09 09:15", periods=2, freq="5min", tz="Asia/Kolkata")
            return pd.DataFrame({"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.0], "Close": [1.5, 2.5],
                                 "Volume": [10, 20], "Dividends": 0.0, "Stock Splits": 0.0}, index=index)

    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    frame = YahooProvider().history("RELIANCE.NS", "5m", START, END)
    assert list(frame.columns) == OHLCV
    assert seen == {"symbol": "RELIANCE.NS", "interval": "5m", "start": START, "end": END}


def test_fetch_many_isolates_failures():
    class Flaky:
        name = "flaky"

        def history(self, symbol, interval, start, end):
            if symbol == "BAD":
                raise RuntimeError("boom")
            return pd.DataFrame(columns=OHLCV) if symbol == "EMPTY" else session_bars([date(2026, 10, 9)])

    frames, failures = fetch_many(Flaky(), ["GOOD", "BAD", "EMPTY"], "5m", START, END)
    assert list(frames) == ["GOOD"]
    assert failures == {"BAD": "RuntimeError: boom", "EMPTY": "no data returned"}


def test_make_provider_follows_the_settings(tmp_path):
    assert make_provider(load_settings(env={})).name == "yahoo"
    config = tmp_path / "settings.toml"
    config.write_text('[data]\nprovider = "kite"\n', encoding="utf-8")
    with pytest.raises(KiteAuthError):
        make_provider(load_settings(env={}, settings_file=config))
