"""Checks every set of bars must pass before it is used for a decision.

* drop_incomplete_bars() removes bars still forming at `now` (Yahoo returns the live candle).
* validate_bars() reports problems. "error" means the data must not drive a trading decision
  (NO TRADE); "warning" means usable but worth knowing; "info" is a note.
* validate_dataset() also compares instruments with each other, which catches missing sessions
  even in years the calendar doesn't cover.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from trader.data.intervals import bar_length, is_daily
from trader.markets.calendar import (CalendarCoverageError, MarketCalendar, calendar_for_symbol,
                                     exchange_for_symbol)

ERROR, WARNING, INFO = "error", "warning", "info"
COLUMNS = ("open", "high", "low", "close", "volume")
DAILY_SETTLE = timedelta(minutes=30)  # a daily bar counts as final this long after the close
# Bar-to-bar moves above these are flagged: a bad tick, an unadjusted split/bonus, or real news.
MAX_MOVE = {"1d": 0.20, "1h": 0.08, "60m": 0.08}
INTRADAY_MAX_MOVE = 0.05
CONSENSUS_SHARE = 0.8  # a day "most instruments traded" in validate_dataset()


@dataclass(frozen=True)
class Issue:
    check: str
    severity: str
    message: str


@dataclass
class ValidationReport:
    symbol: str
    interval: str
    rows: int
    first: pd.Timestamp | None = None
    last: pd.Timestamp | None = None
    issues: list[Issue] = field(default_factory=list)

    def add(self, check: str, severity: str, message: str) -> None:
        self.issues.append(Issue(check, severity, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        """Nothing blocks using this data for a decision."""
        return not self.errors

    def summary(self) -> str:
        return "; ".join(f"{i.severity}: {i.message}" for i in self.issues if i.severity != INFO) or "ok"

    def as_dict(self) -> dict:
        return {"rows": self.rows, "first": str(self.first), "last": str(self.last),
                "issues": [{"check": i.check, "severity": i.severity, "message": i.message} for i in self.issues]}


def _session_close(day, calendar: MarketCalendar | None):
    if calendar is None:
        return None
    try:
        session = calendar.session(day)
    except CalendarCoverageError:
        return None
    return session[1] if session else None


def bar_complete(start: pd.Timestamp, interval: str, now: datetime, calendar: MarketCalendar | None = None) -> bool:
    """Had the bar that starts at `start` finished by `now`?"""
    # Daily bars are stamped at local midnight; intraday bars may arrive in another timezone.
    day = start.tz_convert(calendar.tz).date() if calendar is not None and not is_daily(interval) else start.date()
    close = _session_close(day, calendar)
    if is_daily(interval):
        if close is None:  # without a calendar, a daily bar is final once its day is over
            return now.astimezone(start.tz).date() > start.date()
        return now >= close + DAILY_SETTLE
    end = start + bar_length(interval)
    if close is not None:
        end = min(end, close)
    return now >= end


def drop_incomplete_bars(df: pd.DataFrame, interval: str, now: datetime,
                         calendar: MarketCalendar | None = None) -> pd.DataFrame:
    """Remove trailing bars that were still forming at `now`."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    keep = len(df)
    while keep and not bar_complete(df.index[keep - 1], interval, now, calendar):
        keep -= 1
    return df.iloc[:keep]


def validate_bars(df: pd.DataFrame, symbol: str, interval: str, *, calendar: MarketCalendar | None = None,
                  now: datetime | None = None, max_delay: timedelta | None = None,
                  max_move: float | None = None) -> ValidationReport:
    """Check one instrument's bars. Pass `now` to also check that the newest bar is fresh."""
    report = ValidationReport(symbol, interval, len(df), df.index[0] if len(df) else None,
                              df.index[-1] if len(df) else None)
    if df.empty:
        report.add("empty", ERROR, "no bars")
        return report
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        report.add("columns", ERROR, f"missing columns: {', '.join(missing)}")
        return report
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        report.add("timestamps", ERROR, "index must be a timezone-aware DatetimeIndex")
        return report
    _check_integrity(df, interval, report)
    _check_moves(df, interval, max_move, report)
    if calendar is not None:
        _check_sessions(df, interval, calendar, now, report)
    if now is not None:
        _check_fresh(df, interval, calendar, now, max_delay, report)
    return report


def _check_integrity(df: pd.DataFrame, interval: str, report: ValidationReport) -> None:
    index = df.index
    duplicates = int(index.duplicated().sum())
    if duplicates:
        report.add("duplicates", ERROR, f"{duplicates} duplicate timestamps")
    if not index.is_monotonic_increasing:
        report.add("order", ERROR, "timestamps are not in increasing order")
    prices = df[["open", "high", "low", "close"]].astype(float)
    missing = int(prices.isna().any(axis=1).sum())
    if missing:
        report.add("missing_prices", ERROR, f"{missing} bars with missing prices")
    non_positive = int((prices <= 0).any(axis=1).sum())
    if non_positive:
        report.add("non_positive", ERROR, f"{non_positive} bars with zero or negative prices")
    body_high, body_low = prices[["open", "close"]].max(axis=1), prices[["open", "close"]].min(axis=1)
    tolerance = 1e-9
    broken = ((prices["high"] < body_high * (1 - tolerance)) | (prices["low"] > body_low * (1 + tolerance))
              | (prices["high"] < prices["low"]))
    if broken.any():
        report.add("ohlc", ERROR, f"{int(broken.sum())} bars whose high/low don't contain the open/close")
    zero = (df["volume"] == 0).to_numpy()
    if zero.any():
        message = f"{int(zero.sum())} bars with zero volume"
        if not is_daily(interval):
            times = pd.Series(index[zero].strftime("%H:%M")).value_counts()
            if times.iloc[0] >= 0.5 * zero.sum():
                message += f", mostly the {times.index[0]} bar"
        report.add("zero_volume", WARNING, message)


def _check_moves(df: pd.DataFrame, interval: str, max_move: float | None, report: ValidationReport) -> None:
    limit = max_move or MAX_MOVE.get(interval, INTRADAY_MAX_MOVE)
    close = df["close"].astype(float)
    move = close.pct_change().abs()
    gap = (df["open"].astype(float) / close.shift(1) - 1).abs()
    big = ((move > limit) | (gap > limit)).to_numpy()
    if big.any():
        latest = bool(big[-1])
        report.add("large_move", ERROR if latest else WARNING,
                   f"{int(big.sum())} bar-to-bar moves above {limit:.0%} (first at {df.index[big][0]})"
                   f"{'; the latest bar is one of them' if latest else ''}: a bad tick, an unadjusted "
                   "split/bonus, or real news")


def _check_sessions(df: pd.DataFrame, interval: str, calendar: MarketCalendar, now: datetime | None,
                    report: ValidationReport) -> None:
    local = df.index if is_daily(interval) else df.index.tz_convert(calendar.tz)
    days = np.asarray(local.date)
    unique = sorted(set(days))
    covered = [d for d in unique if calendar.covers(d)]
    uncovered = sorted({d.year for d in unique if not calendar.covers(d)})
    if uncovered:
        report.add("calendar", INFO, f"the {calendar.name} calendar doesn't cover {uncovered}; "
                                     "session checks skipped for those years")
    if not covered:
        return
    closed = [d for d in covered if not calendar.is_trading_day(d)]
    if closed:
        report.add("closed_day", WARNING,
                   f"bars on {len(closed)} day(s) the {calendar.name} calendar marks closed (first {closed[0]})")
    expected = [d for d in pd.date_range(unique[0], unique[-1]).date
                if calendar.covers(d) and calendar.is_trading_day(d)]
    absent_days = sorted(set(expected) - set(unique))
    if absent_days:
        report.add("missing_sessions", WARNING, f"no bars on {len(absent_days)} trading day(s) (first {absent_days[0]})")
    if is_daily(interval):
        return
    length = bar_length(interval)
    outside = short = absent_bars = 0
    for day in covered:
        session = calendar.session(day)
        if session is None:
            continue
        start, end = session
        stamps = local[days == day]
        inside = (stamps >= start) & (stamps < end)
        outside += int((~inside).sum())
        if now is not None and now < end:
            continue  # this session hasn't finished, so later bars are still to come
        expected_bars = math.ceil((end - start) / length)
        if int(inside.sum()) < expected_bars:
            short += 1
            absent_bars += expected_bars - int(inside.sum())
    if outside:
        report.add("outside_session", WARNING, f"{outside} bars outside session hours")
    if short:
        report.add("missing_bars", WARNING, f"{short} session(s) are missing {absent_bars} bar(s) in total")


def _minutes(delta) -> str:
    minutes = int(pd.Timedelta(delta).total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60:02d}m" if minutes >= 60 else f"{minutes} min"


def _check_fresh(df: pd.DataFrame, interval: str, calendar: MarketCalendar | None, now: datetime,
                 max_delay: timedelta | None, report: ValidationReport) -> None:
    last = df.index[-1]
    try:
        if is_daily(interval):
            if calendar is not None:
                expected = calendar.last_completed_session(now - DAILY_SETTLE)
                if last.date() < expected:
                    report.add("stale", ERROR, f"latest daily bar is {last.date()}, expected {expected}")
            return
        length = bar_length(interval)
        delay = pd.Timedelta(max_delay) if max_delay is not None else max(2 * length, pd.Timedelta(minutes=10))
        end, reference, against = last + length, now, "now"
        if calendar is not None:
            close = _session_close(last.tz_convert(calendar.tz).date(), calendar)
            if close is not None:
                end = min(end, close)
            if not calendar.is_open(now):
                reference = calendar.session(calendar.last_completed_session(now))[1]
                against = "the last close"
        lag = reference - end
        if lag > delay:
            report.add("stale", ERROR, f"newest bar ended {_minutes(lag)} before {against} (limit {_minutes(delay)})")
    except CalendarCoverageError as exc:
        report.add("stale", ERROR, f"can't check freshness: {exc}")


def validate_dataset(frames: dict[str, pd.DataFrame], interval: str,
                     calendars: dict[str, MarketCalendar] | None = None) -> dict[str, ValidationReport]:
    """Validate each instrument, then flag days that most instruments on the same exchange traded
    but one didn't (this works even for years the calendar doesn't cover)."""
    reports = {}
    for symbol, frame in frames.items():
        try:
            calendar = calendar_for_symbol(symbol, calendars) if calendars else None
        except CalendarCoverageError:
            calendar = None
        reports[symbol] = validate_bars(frame, symbol, interval, calendar=calendar)

    groups: dict[str, list[str]] = {}
    for symbol, frame in frames.items():
        try:
            exchange = exchange_for_symbol(symbol)
        except CalendarCoverageError:
            continue
        if len(frame):
            groups.setdefault(exchange, []).append(symbol)
    for exchange, symbols in groups.items():
        if len(symbols) < 3:
            continue
        traded = {s: set(frames[s].index.date) for s in symbols}
        counts = Counter(day for days in traded.values() for day in days)
        consensus = {day for day, n in counts.items() if n >= CONSENSUS_SHARE * len(symbols)}
        for symbol, days in traded.items():
            gaps = sorted(d for d in consensus if min(days) <= d <= max(days) and d not in days)
            if gaps:
                reports[symbol].add("consensus_gap", WARNING, f"no bars on {len(gaps)} day(s) when most other "
                                                              f"{exchange} instruments traded (first {gaps[0]})")
    return reports


def report_table(reports: dict[str, ValidationReport]) -> pd.DataFrame:
    return pd.DataFrame([{"symbol": s, "rows": r.rows, "errors": len(r.errors), "warnings": len(r.warnings),
                          "details": r.summary()} for s, r in reports.items()])
