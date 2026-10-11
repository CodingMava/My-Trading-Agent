"""The swing hypotheses, exactly as pre-registered in docs/research/ (the pullback and momentum rules in
phase3-preregistration.md, the turn-of-the-month rule in round4-preregistration.md).

Parameters are fixed there. Changing one makes a new hypothesis that needs its own pre-registration
and fresh data, never a re-run on the data these were judged on.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.features.indicators import atr, rsi, sma
from trader.research.simulator import TIME, TRADE_COLUMNS, ExitRules


@dataclass(frozen=True)
class Signals:
    entry: np.ndarray  # True on a completed bar: buy at the next open
    exit: np.ndarray  # True on a completed bar: sell at the next open
    stop: np.ndarray  # stop distance as a fraction of price (NaN = none)


@dataclass(frozen=True)
class PullbackParams:
    """H1 (stocks) and H2 (index): oversold pullback in an uptrend."""
    trend_sma: int = 200
    rsi_length: int = 2
    rsi_below: float = 10.0
    exit_sma: int = 5
    atr_length: int = 14
    atr_stop: float = 2.5
    max_hold_days: int = 10


PULLBACK = PullbackParams()


def pullback_signals(bars: pd.DataFrame, params: PullbackParams = PULLBACK) -> Signals:
    """Enter when the close is above its 200-day SMA and the 2-day RSI is below 10; exit on the first
    close above the 5-day SMA; stop 2.5 x ATR(14) below entry."""
    close = bars["close"]
    entry = (close > sma(close, params.trend_sma)) & (rsi(close, params.rsi_length) < params.rsi_below)
    exit_ = close > sma(close, params.exit_sma)
    stop = params.atr_stop * atr(bars["high"], bars["low"], close, params.atr_length) / close
    return Signals(entry.to_numpy(bool), exit_.to_numpy(bool), stop.to_numpy(float))


def pullback_rules(params: PullbackParams = PULLBACK) -> ExitRules:
    return ExitRules(max_hold_bars=params.max_hold_days)


@dataclass(frozen=True)
class MomentumParams:
    """H3: 12-1 month momentum, top stocks bought each month-end and held one month."""
    lookback: int = 252
    skip: int = 21
    top_n: int = 5
    min_history: int = 273


MOMENTUM = MomentumParams()


def month_ends(stamps) -> list[pd.Timestamp]:
    """The last trading day of each calendar month among `stamps`."""
    index = pd.DatetimeIndex(sorted(set(stamps)))
    last = pd.Series(index, index=index).groupby([index.year, index.month]).max()
    return list(last.to_numpy())


def momentum_panel(frames: dict[str, pd.DataFrame], params: MomentumParams = MOMENTUM) -> pd.DataFrame:
    """One row per (month-end, eligible stock): the 12-1 momentum score known at that close, and the
    open-to-open return from the next day to the day after the following month-end."""
    ends = month_ends(stamp for frame in frames.values() for stamp in frame.index)
    rows = []
    for symbol, frame in frames.items():
        index = frame.index
        close, open_ = frame["close"].to_numpy(float), frame["open"].to_numpy(float)
        position = {stamp: i for i, stamp in enumerate(index)}
        for this_end, next_end in zip(ends[:-1], ends[1:]):
            i = position.get(this_end)
            if i is None or i + 1 < params.min_history:
                continue  # didn't trade that day, or not enough history yet
            entry_i = i + 1
            exit_i = int(index.searchsorted(next_end, side="right"))
            if exit_i >= len(index) or entry_i >= exit_i:
                continue  # the holding month isn't complete in the data
            rows.append({"month_end": this_end, "symbol": symbol,
                         "score": close[i - params.skip] / close[i - params.lookback] - 1,
                         "entry_time": index[entry_i], "exit_time": index[exit_i],
                         "gross": open_[exit_i] / open_[entry_i] - 1, "hold_bars": exit_i - i})
    return pd.DataFrame(rows)


def select_top(panel: pd.DataFrame, params: MomentumParams = MOMENTUM) -> pd.Series:
    """Boolean mask over `panel`: the top-N scores each month (ties broken by symbol)."""
    ranked = panel.sort_values(["month_end", "score", "symbol"], ascending=[True, False, True])
    chosen = ranked.groupby("month_end").head(params.top_n).index
    return panel.index.isin(chosen)


def momentum_trades(panel: pd.DataFrame, selected, rule: str = "H3") -> pd.DataFrame:
    """Trades for the selected panel rows, in the shared trade-table format."""
    picked = panel[selected]
    if picked.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    signal_times = pd.DatetimeIndex(picked["month_end"])
    exit_times = pd.DatetimeIndex(picked["exit_time"])
    return pd.DataFrame({
        "ticker": picked["symbol"].to_numpy(), "rule": rule, "side": "long",
        "signal_time": signal_times, "exit_time": exit_times,
        "signal_date": np.asarray(signal_times.date), "exit_date": np.asarray(exit_times.date),
        "tod": "00:00", "gross": picked["gross"].to_numpy(float), "reason": TIME,
        "hold_bars": picked["hold_bars"].to_numpy(int), "risk": np.nan,
    })


@dataclass(frozen=True)
class TurnOfMonthParams:
    """H9 and H10: hold over the turn of the month (Lakonishok & Smidt 1988; McConnell & Xu 2008)."""
    hold_days: int = 4  # the month's last trading day and the next month's first three
    atr_length: int = 14
    atr_stop: float = 2.5


TURN_OF_MONTH = TurnOfMonthParams()


def turn_of_month_signals(bars: pd.DataFrame, params: TurnOfMonthParams = TURN_OF_MONTH) -> Signals:
    """Enter at the close of each month's second-to-last trading day (filled at the next open, the month's
    last trading day); the time limit ends each trade at the close of the next month's third trading day;
    protective stop 2.5 x ATR(14) below entry. Month-ends come from the bars' own dates, so the final bars,
    whose next month isn't in the data yet, never signal; neither does a day without an ATR yet."""
    index = pd.DatetimeIndex(bars.index)
    months = (index.year * 12 + index.month).to_numpy()
    last_of_month = np.zeros(len(bars), dtype=bool)
    last_of_month[:-1] = months[1:] != months[:-1]  # the next bar starts a new month
    stop = (params.atr_stop * atr(bars["high"], bars["low"], bars["close"], params.atr_length) / bars["close"]).to_numpy(float)
    entry = np.zeros(len(bars), dtype=bool)
    entry[:-1] = last_of_month[1:]  # the day before the month's last trading day
    return Signals(entry & np.isfinite(stop), np.zeros(len(bars), dtype=bool), stop)


def turn_of_month_rules(params: TurnOfMonthParams = TURN_OF_MONTH) -> ExitRules:
    return ExitRules(max_hold_bars=params.hold_days)
