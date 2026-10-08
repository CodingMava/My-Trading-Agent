"""Deterministic synthetic market data for tests (no network, no real prices)."""
import numpy as np
import pandas as pd


def make_bars(opens, highs, lows, closes, start="2026-01-05 09:15", freq="5min", tz="Asia/Kolkata"):
    """Bars from explicit prices. freq="5min" keeps them in one session; freq="B" makes one bar per day."""
    index = pd.date_range(start, periods=len(closes), freq=freq, tz=tz)
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=index, dtype=float)


def synthetic_intraday(sessions=12, bars_per_session=75, seed=42, tz="Asia/Kolkata", price=1000.0):
    """NSE-like 5-minute OHLCV with trending stretches, volatility bursts and volume spikes.
    Sessions run on consecutive weekdays from Monday 3 Aug 2026 (no NSE holidays until 14 Sep)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2026-08-03", periods=sessions)
    stamps = [pd.Timestamp(f"{day.date()} 09:15") + pd.Timedelta(minutes=5 * i)
              for day in days for i in range(bars_per_session)]
    index = pd.DatetimeIndex(stamps).tz_localize(tz)
    n = len(index)
    drift = np.repeat(rng.normal(0, 0.0012, n // 30 + 1), 30)[:n]
    bursts = np.where(rng.random(n) < 0.05, 3.0, 1.0)
    close = price * np.exp(np.cumsum(drift + rng.normal(0, 0.0015, n) * bursts))
    open_ = np.r_[price, close[:-1]] * (1 + rng.normal(0, 0.0003, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0008, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0008, n)))
    volume = (rng.lognormal(10, 0.4, n) * np.where(rng.random(n) < 0.06, 3.5, 1.0)).astype("int64")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index)


def session_bars(days, minutes=5, open_time="09:15", close_time="15:30", tz="Asia/Kolkata", price=100.0, seed=0):
    """Clean intraday bars covering whole sessions on the given days."""
    rng = np.random.default_rng(seed)
    stamps = []
    for day in days:
        start, end = pd.Timestamp(f"{day} {open_time}", tz=tz), pd.Timestamp(f"{day} {close_time}", tz=tz)
        stamps.extend(pd.date_range(start, end, freq=f"{minutes}min", inclusive="left"))
    n = len(stamps)
    close = price * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    open_ = np.r_[price, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.001,
                         "low": np.minimum(open_, close) * 0.999, "close": close,
                         "volume": rng.integers(1_000, 5_000, n)}, index=pd.DatetimeIndex(stamps))


def daily_session_bars(days, tz="Asia/Kolkata", price=100.0, seed=0):
    """Clean daily bars stamped at local midnight, one per given day."""
    rng = np.random.default_rng(seed)
    n = len(days)
    close = price * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.r_[price, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * 1.005,
                         "low": np.minimum(open_, close) * 0.995, "close": close,
                         "volume": rng.integers(100_000, 500_000, n)},
                        index=pd.DatetimeIndex([pd.Timestamp(str(day), tz=tz) for day in days]))


def daily_from_returns(returns, price=100.0, seed=0, tz="Asia/Kolkata"):
    """Daily bars whose close-to-close returns are `returns`; each open equals the previous close."""
    rng = np.random.default_rng(seed)
    returns = np.asarray(returns, dtype=float)
    close = price * np.exp(np.cumsum(returns))
    open_ = np.r_[price, close[:-1]]
    wiggle = np.abs(rng.normal(0, 0.003, len(returns)))
    index = pd.bdate_range("2019-01-01", periods=len(returns), tz=tz)
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + wiggle),
                         "low": np.minimum(open_, close) * (1 - wiggle), "close": close}, index=index)
