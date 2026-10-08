"""Zerodha Kite Connect over REST: the daily login and historical candles.

    python -m trader.data.kite login               # once per day: sessions expire at 06:00 IST
    python -m trader.data.kite check RELIANCE.NS   # fetch recent candles and validate them
    python -m trader.data.kite logout

Needs KITE_API_KEY and KITE_API_SECRET in .env, from your Kite Connect app (developers.kite.trade).
The day's access token is kept in .kite_session.json (git-ignored) and is never printed or logged.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time as _time
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from trader.config import ROOT
from trader.data.intervals import check_interval
from trader.data.providers import OHLCV

API_ROOT = "https://api.kite.trade"
LOGIN_URL = "https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"
SESSION_FILE = ROOT / ".kite_session.json"
IST = ZoneInfo("Asia/Kolkata")
SESSION_EXPIRY = time(6, 0)  # access tokens expire at 06:00 IST the next day (regulatory requirement)
INTERVALS = {"1m": "minute", "3m": "3minute", "5m": "5minute", "10m": "10minute", "15m": "15minute",
             "30m": "30minute", "1h": "60minute", "60m": "60minute", "1d": "day"}
# Days per historical request. Kite doesn't publish its caps; these stay well below the limits
# reported on its developer forum (60 days for 1-minute bars up to 2000 days for daily bars).
CHUNK_DAYS = {"minute": 30, "3minute": 60, "5minute": 60, "10minute": 60, "15minute": 100,
              "30minute": 100, "60minute": 200, "day": 1500}
HISTORICAL_MIN_GAP = 0.34  # seconds between historical requests: Kite allows 3 per second
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
INDEX_SYMBOLS = {"^NSEI": "NIFTY 50", "^NSEBANK": "NIFTY BANK", "^INDIAVIX": "INDIA VIX"}


class KiteError(RuntimeError):
    """Kite rejected a request."""


class KiteAuthError(KiteError):
    """No valid session: run `python -m trader.data.kite login`."""


def checksum(api_key: str, request_token: str, api_secret: str) -> str:
    """SHA-256 of api_key + request_token + api_secret, as the login exchange requires."""
    return hashlib.sha256((api_key + request_token + api_secret).encode()).hexdigest()


def request_token_from(text: str) -> str:
    """Accept the full URL Kite redirected to after login, or just the request_token."""
    text = text.strip()
    if "?" in text:
        query = parse_qs(urlparse(text).query)
        if query.get("status", ["success"])[0] != "success":
            raise ValueError("the Kite login did not succeed (status is not 'success')")
        if not query.get("request_token"):
            raise ValueError("that URL has no request_token")
        return query["request_token"][0]
    if not text or any(ch.isspace() for ch in text) or "/" in text:
        raise ValueError("that doesn't look like a request_token")
    return text


@dataclass(frozen=True)
class KiteSession:
    api_key: str
    access_token: str
    user_id: str
    created_at: datetime

    @property
    def expires_at(self) -> datetime:
        local = self.created_at.astimezone(IST)
        expiry = datetime.combine(local.date(), SESSION_EXPIRY, IST)
        return expiry if local < expiry else expiry + timedelta(days=1)

    def is_valid(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(IST)) < self.expires_at

    def __repr__(self) -> str:  # never show the token
        return f"KiteSession(user_id={self.user_id!r}, expires_at={self.expires_at:%Y-%m-%d %H:%M} IST)"


def save_session(session: KiteSession, path: Path = SESSION_FILE) -> None:
    path.write_text(json.dumps({"api_key": session.api_key, "access_token": session.access_token,
                                "user_id": session.user_id, "created_at": session.created_at.isoformat()}),
                    encoding="utf-8")


def _read_session(path: Path) -> KiteSession | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return KiteSession(data["api_key"], data["access_token"], data.get("user_id", ""),
                       datetime.fromisoformat(data["created_at"]))


def load_session(path: Path = SESSION_FILE, now: datetime | None = None) -> KiteSession | None:
    """Today's session, or None when there is none or it has expired."""
    session = _read_session(path)
    return session if session is not None and session.is_valid(now) else None


def session_secrets(path: Path = SESSION_FILE) -> list[str]:
    """The stored access token (even if expired), so logging can mask it."""
    session = _read_session(path)
    return [session.access_token] if session else []


def _payload(response) -> dict:
    """The JSON body of a successful response; otherwise a KiteError naming Kite's error."""
    try:
        payload = response.json()
    except ValueError:
        raise KiteError(f"HTTP {response.status_code}: Kite returned a non-JSON response") from None
    if response.status_code == 403 or payload.get("error_type") == "TokenException":
        raise KiteAuthError(f"{payload.get('message', 'session expired or invalid')} "
                            "(run: python -m trader.data.kite login)")
    if response.status_code != 200 or payload.get("status") != "success":
        raise KiteError(f"{payload.get('error_type', 'Error')} (HTTP {response.status_code}): "
                        f"{payload.get('message', '')}")
    return payload


def create_session(api_key: str, api_secret: str, request_token: str, http=requests,
                   now: datetime | None = None) -> KiteSession:
    """Exchange the one-time request_token from the login redirect for the day's access token."""
    response = http.post(f"{API_ROOT}/session/token", headers={"X-Kite-Version": "3"}, timeout=15,
                         data={"api_key": api_key, "request_token": request_token,
                               "checksum": checksum(api_key, request_token, api_secret)})
    data = _payload(response)["data"]
    return KiteSession(api_key, data["access_token"], data.get("user_id", ""), now or datetime.now(IST))


def candles_frame(rows: list) -> pd.DataFrame:
    """Kite candle rows [timestamp, open, high, low, close, volume(, oi)] as an OHLCV frame in IST."""
    if not rows:
        return pd.DataFrame(columns=OHLCV)
    frame = pd.DataFrame([row[:6] for row in rows], columns=["date", *OHLCV])
    index = pd.DatetimeIndex(pd.to_datetime(frame["date"], format="%Y-%m-%dT%H:%M:%S%z")).tz_convert(IST)
    out = frame[OHLCV].astype({"open": float, "high": float, "low": float, "close": float, "volume": "int64"})
    out.index = index.rename("Datetime")
    return out


class KiteClient:
    def __init__(self, api_key: str, access_token: str, http=None, timeout: float = 15,
                 min_gap: float = HISTORICAL_MIN_GAP, sleep=_time.sleep, clock=_time.monotonic):
        self._headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}
        self._http = http if http is not None else requests.Session()
        self._timeout, self._min_gap = timeout, min_gap
        self._sleep, self._clock = sleep, clock
        self._last_historical = None

    def _get(self, path: str, params: dict | None = None):
        for attempt in range(3):
            response = self._http.get(f"{API_ROOT}{path}", params=params, headers=self._headers,
                                      timeout=self._timeout)
            if response.status_code not in RETRY_STATUSES or attempt == 2:
                return response
            self._sleep(1.0 + attempt)  # rate-limited or Kite-side failure: back off and retry

    def instruments(self, exchange: str = "NSE") -> pd.DataFrame:
        """Kite's daily instrument dump for one exchange (CSV)."""
        response = self._get(f"/instruments/{exchange}")
        if response.status_code != 200:
            _payload(response)  # raises a descriptive KiteError
        return pd.read_csv(io.StringIO(response.text))

    def historical(self, instrument_token: int, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Candles with start <= time < end, fetched in date-range chunks Kite accepts."""
        kite_interval = INTERVALS[check_interval(interval)]
        step = timedelta(days=CHUNK_DAYS[kite_interval])
        chunk_start, end = start.astimezone(IST), end.astimezone(IST)
        rows = []
        while chunk_start < end:
            chunk_end = min(chunk_start + step, end)
            if self._last_historical is not None:
                wait = self._min_gap - (self._clock() - self._last_historical)
                if wait > 0:
                    self._sleep(wait)
            params = {"from": chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                      "to": (chunk_end - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")}
            response = self._get(f"/instruments/historical/{instrument_token}/{kite_interval}", params)
            self._last_historical = self._clock()
            rows.extend(_payload(response)["data"]["candles"])
            chunk_start = chunk_end
        return candles_frame(rows)


class KiteProvider:
    """MarketDataProvider backed by Kite Connect. Symbols use Yahoo style (RELIANCE.NS, ^NSEI).
    Kite's documentation doesn't say whether daily history is adjusted for splits and bonuses;
    the validator flags the jumps an unadjusted corporate action would leave."""
    name = "kite"

    def __init__(self, client: KiteClient, exchange: str = "NSE"):
        self.client, self.exchange = client, exchange
        self._tokens: dict[str, int] | None = None

    def instrument_token(self, symbol: str) -> int:
        tradingsymbol = INDEX_SYMBOLS.get(symbol, symbol.removesuffix(".NS"))
        if self._tokens is None:
            table = self.client.instruments(self.exchange)
            table = table[table["exchange"] == self.exchange]
            tokens = dict(zip(table["tradingsymbol"], table["instrument_token"].astype(int)))
            equities = table[table["instrument_type"] == "EQ"]  # equities win any name clash
            tokens.update(zip(equities["tradingsymbol"], equities["instrument_token"].astype(int)))
            self._tokens = tokens
        if tradingsymbol not in self._tokens:
            raise KiteError(f"{symbol} is not in Kite's {self.exchange} instrument list")
        return self._tokens[tradingsymbol]

    def history(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        return self.client.historical(self.instrument_token(symbol), interval, start, end)


def provider_from_settings(settings, session_file: Path = SESSION_FILE) -> KiteProvider:
    if not (settings.kite_api_key and settings.kite_api_secret):
        raise KiteAuthError("set KITE_API_KEY and KITE_API_SECRET in .env (see .env.example)")
    session = load_session(session_file)
    if session is None or session.api_key != settings.kite_api_key.reveal():
        raise KiteAuthError("no valid Kite session today (run: python -m trader.data.kite login)")
    return KiteProvider(KiteClient(session.api_key, session.access_token))


def main(argv: list[str] | None = None) -> None:
    from trader.config import load_settings
    from trader.data.validate import drop_incomplete_bars, validate_bars
    from trader.logging_setup import configure_logging
    from trader.markets.calendar import calendar_for_symbol, load_calendars

    parser = argparse.ArgumentParser(description="Zerodha Kite Connect session and data check.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="log in for today (sessions expire at 06:00 IST)")
    check = sub.add_parser("check", help="fetch recent candles for one symbol and validate them")
    check.add_argument("symbol", help="e.g. RELIANCE.NS")
    check.add_argument("--interval", default="1d")
    check.add_argument("--days", type=int, default=30)
    sub.add_parser("logout", help="invalidate today's session and delete it")
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets())
    key, secret = settings.kite_api_key.reveal(), settings.kite_api_secret.reveal()

    if args.command == "login":
        if not (key and secret):
            raise SystemExit("Set KITE_API_KEY and KITE_API_SECRET in .env first (see .env.example).")
        print("1. Open this URL and log in to Kite:\n   " + LOGIN_URL.format(api_key=key))
        print("2. Kite then redirects to your app's redirect URL. Paste that full URL here (or just the request_token):")
        session = create_session(key, secret, request_token_from(input("> ")))
        save_session(session)
        print(f"Logged in as {session.user_id}. The session is valid until {session.expires_at:%d %b %Y %H:%M} IST.")
    elif args.command == "check":
        now = datetime.now(IST)
        calendar = calendar_for_symbol(args.symbol, load_calendars())
        try:
            provider = provider_from_settings(settings)
            history = provider.history(args.symbol, args.interval, now - timedelta(days=args.days), now)
        except KiteError as exc:
            raise SystemExit(f"Kite: {exc}") from None
        bars = drop_incomplete_bars(history, args.interval, now, calendar)
        report = validate_bars(bars, args.symbol, args.interval, calendar=calendar, now=now)
        print(bars.tail(5).to_string())
        print(f"{len(bars)} complete bars. Validation: {report.summary()}")
    else:
        session = _read_session(SESSION_FILE)
        if session is not None:
            try:
                requests.delete(f"{API_ROOT}/session/token", headers={"X-Kite-Version": "3"}, timeout=15,
                                params={"api_key": session.api_key, "access_token": session.access_token})
            except requests.RequestException as exc:  # the message would contain the token, so print the type only
                print(f"Couldn't reach Kite to invalidate the session ({type(exc).__name__}); deleting it locally.")
            SESSION_FILE.unlink(missing_ok=True)
        print("Logged out of Kite; the local session file is deleted.")


if __name__ == "__main__":
    main()
