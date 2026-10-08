"""The configured holidays must match the days the market actually traded (frozen index data)."""
import pandas as pd
import pytest

from trader.markets.calendar import load_calendars
from trader.research.audit import AUDIT_DIR
from trader.research.datasets import load_dataset

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (AUDIT_DIR / "idx_1d" / "manifest.json").exists(), reason="frozen index data not present"),
]


@pytest.mark.parametrize("exchange, index_symbol", [("NSE", "^NSEI"), ("NYSE", "^GSPC")])
def test_2026_holidays_match_index_trading_days(exchange, index_symbol):
    calendar = load_calendars()[exchange]
    traded = {stamp.date() for stamp in load_dataset(AUDIT_DIR / "idx_1d")[index_symbol].index}
    for day in pd.date_range("2026-01-01", max(traded)).date:
        assert (day in traded) == calendar.is_trading_day(day), day
