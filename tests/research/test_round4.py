from datetime import date

import numpy as np

from tests.helpers import daily_session_bars
from trader.markets.calendar import load_calendars
from trader.research import round4
from trader.research.simulator import TIME, simulate
from trader.strategies.swing import turn_of_month_rules, turn_of_month_signals

NSE = load_calendars()["NSE"]


def test_the_preregistration_is_unchanged():
    assert round4.check_preregistration().startswith("3346175f")


def test_entries_fall_on_each_months_second_to_last_trading_day():
    days = NSE.trading_days(date(2026, 1, 1), date(2026, 6, 30))
    entries = [d for d, e in zip(days, turn_of_month_signals(daily_session_bars(days)).entry) if e]
    expected = [[d for d in days if d.month == month][-2] for month in range(1, 6)]
    assert entries == expected  # June's month-end isn't known from the data yet, so June never signals


def test_no_trade_before_the_stop_can_be_sized():
    days = NSE.trading_days(date(2026, 1, 20), date(2026, 3, 31))  # January's month-end comes too early for ATR(14)
    entries = [d for d, e in zip(days, turn_of_month_signals(daily_session_bars(days)).entry) if e]
    assert [d.month for d in entries] == [2]


def test_a_trade_runs_from_the_months_last_day_to_the_third_day_of_the_next():
    days = NSE.trading_days(date(2026, 1, 1), date(2026, 3, 31))
    bars = daily_session_bars(days, seed=3)
    signals = turn_of_month_signals(bars)
    out = simulate(bars, "long", turn_of_month_rules(), "next_open", stop=signals.stop, exit_signal=signals.exit)
    february, march = [d for d in days if d.month == 2], [d for d in days if d.month == 3]
    k = int(np.flatnonzero(signals.entry)[1])  # February's signal
    assert days[k] == february[-2] and days[k + 1] == february[-1]
    assert days[out.exit_idx[k]] == march[2] and out.reason[k] == TIME
