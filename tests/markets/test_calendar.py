from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from trader.markets.calendar import CalendarCoverageError, MarketCalendar, calendar_for_symbol, load_calendars

IST, NEW_YORK = ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")
CALENDARS = load_calendars()
NSE, NYSE = CALENDARS["NSE"], CALENDARS["NYSE"]


def test_nse_holidays_weekends_and_hours():
    assert not NSE.is_trading_day(date(2026, 10, 2))  # Gandhi Jayanti (Friday)
    assert not NSE.is_trading_day(date(2026, 10, 3))  # Saturday
    assert NSE.is_trading_day(date(2026, 10, 9))
    opens, closes = NSE.session(date(2026, 10, 9))
    assert (opens.time(), closes.time()) == (time(9, 15), time(15, 30)) and opens.utcoffset() == timedelta(hours=5, minutes=30)
    assert NSE.is_open(datetime(2026, 10, 9, 9, 15, tzinfo=IST))
    assert not NSE.is_open(datetime(2026, 10, 9, 15, 30, tzinfo=IST))
    assert not NSE.is_open(datetime(2026, 10, 20, 11, 0, tzinfo=IST))  # Dussehra


def test_stepping_over_weekends_and_holidays():
    assert NSE.previous_trading_day(date(2026, 10, 5)) == date(2026, 10, 1)  # skips the weekend and 2 Oct
    assert NSE.next_trading_day(date(2026, 10, 19)) == date(2026, 10, 21)  # skips Dussehra
    assert NSE.trading_days(date(2026, 10, 1), date(2026, 10, 7)) == [date(2026, 10, d) for d in (1, 5, 6, 7)]
    assert NSE.last_completed_session(datetime(2026, 10, 5, 10, 0, tzinfo=IST)) == date(2026, 10, 1)
    assert NSE.last_completed_session(datetime(2026, 10, 5, 15, 31, tzinfo=IST)) == date(2026, 10, 5)


def test_years_without_a_holiday_list_fail_closed():
    with pytest.raises(CalendarCoverageError, match="2027"):
        NSE.is_trading_day(date(2027, 1, 4))
    with pytest.raises(CalendarCoverageError):
        NSE.is_open(datetime(2027, 1, 4, 11, 0, tzinfo=IST))


def test_nyse_daylight_saving_and_early_closes():
    winter, _ = NYSE.session(date(2026, 1, 5))
    summer, _ = NYSE.session(date(2026, 7, 6))
    assert winter.utcoffset() == timedelta(hours=-5) and summer.utcoffset() == timedelta(hours=-4)
    assert NYSE.session(date(2026, 11, 27))[1].time() == time(13, 0)  # day after Thanksgiving
    assert not NYSE.is_trading_day(date(2026, 7, 3))  # Independence Day observed
    assert NYSE.is_trading_day(date(2028, 1, 3)) and not NYSE.is_trading_day(date(2027, 12, 24))


def test_special_sessions_open_otherwise_closed_days():
    calendar = MarketCalendar("TEST", IST, time(9, 15), time(15, 30), frozenset({2026}),
                              special_sessions={date(2026, 11, 8): (time(18, 0), time(19, 0))})
    assert calendar.is_trading_day(date(2026, 11, 8))  # a Sunday, like a Muhurat session
    assert calendar.is_open(datetime(2026, 11, 8, 18, 30, tzinfo=IST))
    assert not calendar.is_open(datetime(2026, 11, 8, 17, 0, tzinfo=IST))


def test_symbols_map_to_exchange_calendars():
    assert calendar_for_symbol("RELIANCE.NS", CALENDARS) is NSE
    assert calendar_for_symbol("^NSEI", CALENDARS) is NSE
    assert calendar_for_symbol("AAPL", CALENDARS) is NYSE and calendar_for_symbol("^GSPC", CALENDARS) is NYSE
    with pytest.raises(CalendarCoverageError):
        calendar_for_symbol("RELIANCE.BO", CALENDARS)  # no BSE calendar configured yet


def test_config_dates_must_be_inside_the_covered_years(tmp_path):
    config = tmp_path / "calendars.toml"
    config.write_text('[X]\ntimezone = "Asia/Kolkata"\nopen = "09:15"\nclose = "15:30"\nyears = [2026]\n'
                      '[X.holidays]\n"2027-01-26" = "Republic Day"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="outside the covered years"):
        load_calendars(config)
