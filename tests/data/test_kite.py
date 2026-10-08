"""Kite Connect client against recorded-style responses (no network, no real credentials)."""
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trader.config import load_settings
from trader.data.kite import (KiteAuthError, KiteClient, KiteError, KiteProvider, KiteSession, checksum,
                              create_session, load_session, provider_from_settings, request_token_from,
                              save_session)

IST = ZoneInfo("Asia/Kolkata")
OCT_1, OCT_10 = datetime(2026, 10, 1, tzinfo=IST), datetime(2026, 10, 10, tzinfo=IST)
INSTRUMENTS_CSV = ("instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,"
                   "lot_size,instrument_type,segment,exchange\n"
                   "408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n"
                   "256265,1001,NIFTY 50,NIFTY 50,0,,,0,0,EQ,INDICES,NSE\n")


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code, self._payload, self.text = status_code, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class FakeHTTP:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


def candles(*rows):
    return FakeResponse(200, {"status": "success", "data": {"candles": list(rows)}})


def client(http, **kwargs):
    return KiteClient("key", "AT", http=http, sleep=kwargs.pop("sleep", lambda seconds: None), **kwargs)


def test_checksum_is_sha256_of_key_token_and_secret():
    assert checksum("key", "req", "sec") == hashlib.sha256(b"keyreqsec").hexdigest()


def test_request_token_from_the_redirect_url_or_alone():
    url = "https://example.com/callback?action=login&type=login&status=success&request_token=abc123"
    assert request_token_from(url) == "abc123" and request_token_from("  abc123 ") == "abc123"
    for bad in ("https://example.com/callback?status=failed&request_token=x",
                "https://example.com/callback?status=success", "two words"):
        with pytest.raises(ValueError):
            request_token_from(bad)


def test_login_posts_the_documented_fields_and_hides_the_token():
    http = FakeHTTP([FakeResponse(200, {"status": "success", "data": {"access_token": "AT", "user_id": "AB1234"}})])
    session = create_session("key", "sec", "req", http=http, now=datetime(2026, 10, 9, 8, 30, tzinfo=IST))
    call = http.calls[0]
    assert call["url"] == "https://api.kite.trade/session/token" and call["headers"] == {"X-Kite-Version": "3"}
    assert call["data"] == {"api_key": "key", "request_token": "req", "checksum": checksum("key", "req", "sec")}
    assert session.access_token == "AT" and "AT" not in repr(session)
    assert session.expires_at == datetime(2026, 10, 10, 6, 0, tzinfo=IST)


def test_sessions_expire_at_six_in_the_morning(tmp_path):
    assert KiteSession("key", "AT", "U", datetime(2026, 10, 9, 5, 0, tzinfo=IST)).expires_at == \
        datetime(2026, 10, 9, 6, 0, tzinfo=IST)
    path = tmp_path / "session.json"
    save_session(KiteSession("key", "AT", "U", datetime(2026, 10, 9, 9, 0, tzinfo=IST)), path)
    assert load_session(path, now=datetime(2026, 10, 9, 20, 0, tzinfo=IST)).access_token == "AT"
    assert load_session(path, now=datetime(2026, 10, 10, 6, 0, tzinfo=IST)) is None
    assert load_session(tmp_path / "missing.json") is None


def test_historical_request_format_and_parsing():
    http = FakeHTTP([candles(["2026-10-08T00:00:00+0530", 2900.5, 2950, 2890, 2940.25, 123456],
                             ["2026-10-09T00:00:00+0530", 2940, 2960, 2930, 2955, 98765])])
    frame = client(http).historical(408065, "1d", OCT_1, OCT_10)
    call = http.calls[0]
    assert call["url"] == "https://api.kite.trade/instruments/historical/408065/day"
    assert call["params"] == {"from": "2026-10-01 00:00:00", "to": "2026-10-09 23:59:59"}
    assert call["headers"] == {"X-Kite-Version": "3", "Authorization": "token key:AT"}
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index[0] == pd.Timestamp("2026-10-08", tz="Asia/Kolkata") and str(frame.index.tz) == "Asia/Kolkata"
    assert frame["close"].iloc[-1] == 2955 and frame["volume"].iloc[0] == 123456


def test_long_ranges_are_fetched_in_contiguous_chunks():
    http = FakeHTTP([candles(), candles(), candles()])
    start = datetime(2026, 5, 1, tzinfo=IST)
    client(http).historical(1, "5m", start, start + timedelta(days=150))
    assert [(c["params"]["from"], c["params"]["to"]) for c in http.calls] == [
        ("2026-05-01 00:00:00", "2026-06-29 23:59:59"),
        ("2026-06-30 00:00:00", "2026-08-28 23:59:59"),
        ("2026-08-29 00:00:00", "2026-09-27 23:59:59"),
    ]


def test_historical_requests_are_spaced_to_respect_the_rate_limit():
    ticks, waits = iter([10.0, 10.1, 10.5, 10.6, 11.0]), []
    http = FakeHTTP([candles(), candles(), candles()])
    client(http, sleep=waits.append, clock=lambda: next(ticks)).historical(1, "1m", OCT_1, OCT_1 + timedelta(days=90))
    assert waits == [pytest.approx(0.24), pytest.approx(0.24)]


def test_rate_limited_requests_are_retried():
    sleeps = []
    http = FakeHTTP([FakeResponse(429, {"status": "error", "message": "Too many requests", "error_type": "NetworkException"}),
                     candles(["2026-10-09T00:00:00+0530", 1, 1, 1, 1, 1])])
    assert len(client(http, sleep=sleeps.append).historical(1, "1d", OCT_1, OCT_10)) == 1
    assert len(http.calls) == 2 and sleeps == [1.0]


def test_errors_are_named_and_expired_sessions_ask_for_login():
    expired = FakeHTTP([FakeResponse(403, {"status": "error", "message": "Incorrect api_key or access_token.",
                                           "error_type": "TokenException"})])
    with pytest.raises(KiteAuthError, match="login"):
        client(expired).historical(1, "1d", OCT_1, OCT_10)
    too_long = FakeHTTP([FakeResponse(400, {"status": "error", "message": "interval exceeds max limit",
                                            "error_type": "InputException"})])
    with pytest.raises(KiteError, match="InputException"):
        client(too_long).historical(1, "1d", OCT_1, OCT_10)


def test_provider_maps_yahoo_symbols_to_instrument_tokens():
    http = FakeHTTP([FakeResponse(200, text=INSTRUMENTS_CSV), candles(), candles()])
    provider = KiteProvider(client(http))
    provider.history("INFY.NS", "1d", OCT_1, OCT_10)
    provider.history("^NSEI", "1d", OCT_1, OCT_10)
    assert http.calls[0]["url"].endswith("/instruments/NSE")
    assert http.calls[1]["url"].endswith("/408065/day") and http.calls[2]["url"].endswith("/256265/day")
    with pytest.raises(KiteError, match="not in Kite"):
        provider.instrument_token("NOPE.NS")


def test_provider_needs_keys_and_a_session_from_today(tmp_path):
    settings = load_settings(env={"KITE_API_KEY": "key", "KITE_API_SECRET": "sec"})
    with pytest.raises(KiteAuthError, match="KITE_API_KEY"):
        provider_from_settings(load_settings(env={}), session_file=tmp_path / "none.json")
    with pytest.raises(KiteAuthError, match="login"):
        provider_from_settings(settings, session_file=tmp_path / "none.json")
    path = tmp_path / "session.json"
    save_session(KiteSession("key", "AT", "U", datetime.now(IST)), path)
    assert isinstance(provider_from_settings(settings, session_file=path), KiteProvider)
