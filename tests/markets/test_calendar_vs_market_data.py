"""The configured holidays must match the days the market actually traded (frozen index data, from Yahoo and,
where present, from Kite)."""
from datetime import date

import pandas as pd
import pytest

from trader.markets.calendar import load_calendars
from trader.research.audit import AUDIT_DIR
from trader.research.datasets import DATA_DIR, load_dataset

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (AUDIT_DIR / "idx_1d" / "manifest.json").exists(), reason="frozen index data not present"),
]
KITE_MINUTES = DATA_DIR / "kite_minute" / "nifty_1m"
# Sessions Yahoo's daily data lacks, each confirmed by the exchange's notice and by Kite's bars.
MISSING_FROM_YAHOO = {"NSE": {date(2026, 2, 1): "Union Budget session on a Sunday"}}


@pytest.mark.parametrize("exchange, index_symbol", [("NSE", "^NSEI"), ("NYSE", "^GSPC")])
def test_2026_holidays_match_index_trading_days(exchange, index_symbol):
    calendar = load_calendars()[exchange]
    traded = {stamp.date() for stamp in load_dataset(AUDIT_DIR / "idx_1d")[index_symbol].index}
    missing = MISSING_FROM_YAHOO.get(exchange, {})
    for day in pd.date_range("2026-01-01", max(traded)).date:
        assert (day in traded or day in missing) == calendar.is_trading_day(day), day
    assert not set(missing) & traded  # once Yahoo has the session, the exception isn't needed


@pytest.mark.skipif(not (KITE_MINUTES / "manifest.json").exists(), reason="frozen Kite minute data not present")
def test_2026_nse_sessions_match_kites_minute_bars():
    calendar = load_calendars()["NSE"]
    traded = {stamp.date() for stamp in load_dataset(KITE_MINUTES)["^NSEI"].index.tz_convert("Asia/Kolkata")}
    for day in pd.date_range("2026-01-01", max(traded)).date:
        assert (day in traded) == calendar.is_trading_day(day), day
