"""Exchange trading calendars: which days trade, and when.

Holiday lists come from config/market_calendars.toml (official exchange lists). A date in a year
the file doesn't cover is unknown, and asking about it raises CalendarCoverageError, so nothing can
quietly trade through a holiday nobody configured.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.config import CONFIG_DIR

CALENDARS_FILE = CONFIG_DIR / "market_calendars.toml"


class CalendarCoverageError(LookupError):
    """No verified calendar for the requested exchange or year."""


@dataclass(frozen=True)
class MarketCalendar:
    name: str
    tz: ZoneInfo
    open: time
    close: time
    years: frozenset[int]
    holidays: dict[date, str] = field(default_factory=dict)
    early_closes: dict[date, time] = field(default_factory=dict)
    special_sessions: dict[date, tuple[time, time]] = field(default_factory=dict)
    source: str = ""

    def covers(self, day: date) -> bool:
        return day.year in self.years

    def _require(self, day: date) -> None:
        if not self.covers(day):
            raise CalendarCoverageError(
                f"no {self.name} holiday list for {day.year}; add it to config/{CALENDARS_FILE.name}")

    def is_trading_day(self, day: date) -> bool:
        self._require(day)
        if day in self.special_sessions:
            return True
        return day.weekday() < 5 and day not in self.holidays

    def session(self, day: date) -> tuple[datetime, datetime] | None:
        """(open, close) as timezone-aware datetimes, or None when the market is closed all day."""
        if not self.is_trading_day(day):
            return None
        if day in self.special_sessions:
            start, end = self.special_sessions[day]
        else:
            start, end = self.open, self.early_closes.get(day, self.close)
        return datetime.combine(day, start, self.tz), datetime.combine(day, end, self.tz)

    def is_open(self, now: datetime) -> bool:
        local = now.astimezone(self.tz)
        session = self.session(local.date())
        return session is not None and session[0] <= local < session[1]

    def previous_trading_day(self, day: date) -> date:
        day -= timedelta(days=1)
        while not self.is_trading_day(day):
            day -= timedelta(days=1)
        return day

    def next_trading_day(self, day: date) -> date:
        day += timedelta(days=1)
        while not self.is_trading_day(day):
            day += timedelta(days=1)
        return day

    def trading_days(self, start: date, end: date) -> list[date]:
        days, day = [], start
        while day <= end:
            if self.is_trading_day(day):
                days.append(day)
            day += timedelta(days=1)
        return days

    def last_completed_session(self, now: datetime) -> date:
        """The most recent trading day whose session had closed by `now`."""
        local = now.astimezone(self.tz)
        session = self.session(local.date())
        if session is not None and local >= session[1]:
            return local.date()
        return self.previous_trading_day(local.date())


def _time(text: str) -> time:
    return time.fromisoformat(text)


def load_calendars(path: Path = CALENDARS_FILE) -> dict[str, MarketCalendar]:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    calendars = {}
    for name, cfg in raw.items():
        years = frozenset(int(y) for y in cfg["years"])
        holidays = {date.fromisoformat(d): label for d, label in cfg.get("holidays", {}).items()}
        early_closes = {date.fromisoformat(d): _time(t) for d, t in cfg.get("early_closes", {}).items()}
        special = {date.fromisoformat(d): (_time(s[0]), _time(s[1]))
                   for d, s in cfg.get("special_sessions", {}).items()}
        outside = sorted(d for d in [*holidays, *early_closes, *special] if d.year not in years)
        if outside:
            raise ValueError(f"{name}: {outside[0]} is outside the covered years {sorted(years)}")
        calendars[name] = MarketCalendar(name, ZoneInfo(cfg["timezone"]), _time(cfg["open"]), _time(cfg["close"]),
                                         years, holidays, early_closes, special, cfg.get("source", ""))
    return calendars


NSE_INDEX_PREFIXES = ("^NSE", "^NSM", "^CNX", "^CRSL", "^INDIAVIX")  # ^NSEBANK, ^NSMIDCP, ^CNXIT, ^CRSLDX


def exchange_for_symbol(symbol: str) -> str:
    """Yahoo-style symbols: RELIANCE.NS and NSE indices (^NSEI, ^CNXIT...) -> NSE, RELIANCE.BO -> BSE,
    AAPL and ^GSPC -> NYSE."""
    if symbol.endswith(".NS") or symbol.startswith(NSE_INDEX_PREFIXES):
        return "NSE"
    if symbol.endswith(".BO"):
        return "BSE"
    if "." not in symbol:
        return "NYSE"  # NYSE and NASDAQ share holidays
    raise CalendarCoverageError(f"no exchange calendar mapping for {symbol}")


def calendar_for_symbol(symbol: str, calendars: dict[str, MarketCalendar]) -> MarketCalendar:
    exchange = exchange_for_symbol(symbol)
    if exchange not in calendars:
        raise CalendarCoverageError(f"no {exchange} calendar configured (needed for {symbol})")
    return calendars[exchange]
