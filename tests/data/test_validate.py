from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from tests.helpers import daily_session_bars, session_bars
from trader.data.validate import (ERROR, WARNING, bar_complete, drop_incomplete_bars, report_table, validate_bars,
                                  validate_dataset)
from trader.markets.calendar import load_calendars

IST = ZoneInfo("Asia/Kolkata")
CALENDARS = load_calendars()
NSE = CALENDARS["NSE"]
WEEK = [date(2026, 10, d) for d in (5, 6, 7, 8, 9)]  # Friday 2 Oct was a holiday


def checks(report, severity=None):
    return {i.check for i in report.issues if severity is None or i.severity == severity}


def test_a_clean_week_passes_every_check():
    report = validate_bars(session_bars(WEEK), "X.NS", "5m", calendar=NSE, now=datetime(2026, 10, 9, 15, 45, tzinfo=IST))
    assert report.ok and report.issues == [] and report.summary() == "ok"


def test_the_forming_bar_is_dropped():
    bars = session_bars([date(2026, 10, 9)])
    now = datetime(2026, 10, 9, 10, 2, tzinfo=IST)
    live_feed = bars[bars.index <= now]  # what a live feed returns: includes the 10:00 bar still forming
    assert drop_incomplete_bars(live_feed, "5m", now, NSE).index[-1] == pd.Timestamp("2026-10-09 09:55", tz=IST)


def test_the_session_close_completes_a_short_last_bar():
    last_hourly_bar = session_bars([date(2026, 10, 9)], minutes=60).index[-1]  # 15:15, only 15 minutes long
    assert last_hourly_bar.strftime("%H:%M") == "15:15"
    assert bar_complete(last_hourly_bar, "1h", datetime(2026, 10, 9, 15, 31, tzinfo=IST), NSE)
    assert not bar_complete(last_hourly_bar, "1h", datetime(2026, 10, 9, 15, 20, tzinfo=IST), NSE)


def test_a_daily_bar_is_final_only_after_the_close_settles():
    daily = daily_session_bars(WEEK)
    assert len(drop_incomplete_bars(daily, "1d", datetime(2026, 10, 9, 15, 0, tzinfo=IST), NSE)) == 4
    assert len(drop_incomplete_bars(daily, "1d", datetime(2026, 10, 9, 16, 5, tzinfo=IST), NSE)) == 5


def test_integrity_problems_are_errors():
    bars = session_bars(WEEK)
    broken = pd.concat([bars, bars.iloc[[10]]]).sort_index()  # a duplicated timestamp
    broken.iloc[20, broken.columns.get_loc("high")] = broken["low"].iloc[20] * 0.9  # high below low
    broken.iloc[30, broken.columns.get_loc("close")] = np.nan
    report = validate_bars(broken, "X.NS", "5m")
    assert {"duplicates", "ohlc", "missing_prices"} <= checks(report, ERROR) and not report.ok


def test_zero_volume_on_the_opening_bar_is_only_a_warning():
    bars = session_bars(WEEK)
    bars.loc[bars.index.strftime("%H:%M") == "09:15", "volume"] = 0  # Yahoo's NSE pattern
    report = validate_bars(bars, "X.NS", "5m", calendar=NSE)
    assert report.ok and any(i.check == "zero_volume" and "09:15" in i.message for i in report.warnings)


def test_large_moves_warn_but_block_when_on_the_latest_bar():
    bars = session_bars(WEEK)
    jumped = bars.copy()
    jumped.iloc[100:, :4] *= 1.08  # an 8% jump mid-series
    assert "large_move" in checks(validate_bars(jumped, "X.NS", "5m"), WARNING)
    latest = bars.copy()
    latest.iloc[-1, :4] *= 1.08
    assert "large_move" in checks(validate_bars(latest, "X.NS", "5m"), ERROR)


def test_missing_sessions_missing_bars_and_closed_days_are_reported():
    bars = session_bars(WEEK)
    gappy = bars[(bars.index.date != date(2026, 10, 7)) & (bars.index.strftime("%H:%M") < "15:20")]
    on_holiday = session_bars([date(2026, 10, 2)])  # NSE was closed for Gandhi Jayanti
    report = validate_bars(pd.concat([on_holiday, gappy]), "X.NS", "5m", calendar=NSE)
    assert {"missing_sessions", "missing_bars", "closed_day"} <= checks(report, WARNING) and report.ok


def test_freshness_during_and_after_the_session():
    bars = session_bars(WEEK)
    late_morning = datetime(2026, 10, 9, 11, 0, tzinfo=IST)
    limit = timedelta(minutes=20)
    old = bars[bars.index < pd.Timestamp("2026-10-09 10:00", tz=IST)]  # newest bar ended 10:00
    assert checks(validate_bars(old, "X.NS", "5m", calendar=NSE, now=late_morning, max_delay=limit), ERROR) == {"stale"}
    recent = bars[bars.index < pd.Timestamp("2026-10-09 10:50", tz=IST)]  # newest bar ended 10:50
    assert validate_bars(recent, "X.NS", "5m", calendar=NSE, now=late_morning, max_delay=limit).ok
    monday_morning = datetime(2026, 10, 12, 8, 0, tzinfo=IST)  # closed: compare with Friday's close
    assert validate_bars(bars, "X.NS", "5m", calendar=NSE, now=monday_morning).ok
    up_to_thursday = bars[bars.index.date < date(2026, 10, 9)]
    assert "stale" in checks(validate_bars(up_to_thursday, "X.NS", "5m", calendar=NSE, now=monday_morning), ERROR)


def test_daily_freshness():
    up_to_thursday = daily_session_bars(WEEK[:-1])
    assert "stale" in checks(validate_bars(up_to_thursday, "X.NS", "1d", calendar=NSE,
                                           now=datetime(2026, 10, 9, 17, 0, tzinfo=IST)), ERROR)
    assert validate_bars(up_to_thursday, "X.NS", "1d", calendar=NSE, now=datetime(2026, 10, 9, 12, 0, tzinfo=IST)).ok


def test_years_without_a_calendar_fail_closed():
    report = validate_bars(session_bars([date(2026, 12, 31)]), "X.NS", "5m", calendar=NSE,
                           now=datetime(2027, 1, 4, 10, 0, tzinfo=IST))
    assert "stale" in checks(report, ERROR) and "2027" in report.errors[0].message


def test_dataset_check_flags_days_other_stocks_traded():
    days = [date(2026, 8, d) for d in (3, 4, 5, 6, 7)]
    frames = {f"S{i}.NS": daily_session_bars(days, seed=i) for i in range(4)}
    frames["GAP.NS"] = daily_session_bars([d for d in days if d != date(2026, 8, 5)])
    reports = validate_dataset(frames, "1d", CALENDARS)
    assert "consensus_gap" in checks(reports["GAP.NS"], WARNING)
    assert all(r.ok for r in reports.values())
    assert set(report_table(reports)["symbol"]) == set(frames)


def test_empty_and_malformed_frames():
    assert checks(validate_bars(pd.DataFrame(), "X.NS", "5m"), ERROR) == {"empty"}
    no_volume = session_bars(WEEK).drop(columns=["volume"])
    assert checks(validate_bars(no_volume, "X.NS", "5m"), ERROR) == {"columns"}
    naive = session_bars(WEEK)
    naive.index = naive.index.tz_localize(None)
    assert checks(validate_bars(naive, "X.NS", "5m"), ERROR) == {"timestamps"}
