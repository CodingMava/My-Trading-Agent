"""Bar-level trade simulation shared by every backtest, intraday or swing.

These conventions decide results, so they live in one place and are covered by tests:

* A signal is evaluated on a completed bar ``k``.
* Entry ``"next_open"`` (the realistic default) fills at the open of bar ``k+1``; ``"signal_close"``
  fills at the close of bar ``k``, the price an alert would quote.
* The position is exposed from bar ``k+1`` onward. On each bar:
    - if the bar opens beyond the stop or the target, the fill is that open (gap-through);
    - if the stop and the target are both touched inside one bar, the stop is assumed to come first,
      unless the bar opened beyond the target;
    - an optional exit signal, true on a bar's close, sells at the next bar's open (a SIGNAL exit;
      that open comes before any stop or target touch on the same bar);
    - otherwise the trade closes at the close of its last allowed bar (a TIME exit).
* The last allowed bar is the session's last bar when ``square_off_each_session`` is set (intraday:
  no position may be opened on that bar). Otherwise it is set by ``max_hold_bars`` /
  ``max_hold_sessions``, or by the end of the data (swing).
* One open position per instrument and strategy: signals that arrive while a trade is open are ignored.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TARGET, STOP, TIME, SIGNAL = 1, -1, 0, 2
REASON_NAMES = {TARGET: "target", STOP: "stop", TIME: "time", SIGNAL: "signal"}
ENTRY_MODES = ("next_open", "signal_close")
SIDES = ("long", "short")
TRADE_COLUMNS = ["ticker", "rule", "side", "signal_time", "exit_time", "signal_date", "exit_date",
                 "tod", "gross", "reason", "hold_bars", "risk"]
_NEVER = np.iinfo(np.int64).max


@dataclass(frozen=True)
class ExitRules:
    stop: float | None = None  # fraction of the entry price, e.g. 0.01 = 1%
    target: float | None = None
    square_off_each_session: bool = False  # True for intraday strategies
    max_hold_bars: int | None = None
    max_hold_sessions: int | None = None

    def __post_init__(self):
        for name in ("stop", "target"):
            value = getattr(self, name)
            if value is not None and not value > 0:
                raise ValueError(f"{name} must be a positive fraction or None, got {value!r}")
        for name in ("max_hold_bars", "max_hold_sessions"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be >= 1 or None, got {value!r}")


@dataclass(frozen=True)
class Outcomes:
    """The trade that a signal on each bar would produce, each computed independently."""
    gross: np.ndarray  # gross return as a fraction of the entry price; NaN = no trade possible
    exit_idx: np.ndarray  # bar index of the exit, -1 when there is no trade
    reason: np.ndarray  # TARGET, STOP, TIME or SIGNAL
    risk: np.ndarray  # stop distance used (fraction of entry), NaN when there was no stop


def session_ids(index: pd.DatetimeIndex) -> np.ndarray:
    """0, 0, ..., 1, 1, ...: a new session starts whenever the bar's local calendar date changes."""
    dates = np.asarray(index.date)
    if len(dates) == 0:
        return np.zeros(0, dtype=np.int64)
    return np.cumsum(np.r_[True, dates[1:] != dates[:-1]]) - 1


def _levels(value, default, n: int) -> np.ndarray:
    value = default if value is None else value
    if value is None:
        return np.full(n, np.nan)
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(n, float(arr))
    elif arr.shape != (n,):
        raise ValueError(f"per-bar stop/target must have length {n}, got shape {arr.shape}")
    if np.any(arr[~np.isnan(arr)] <= 0):
        raise ValueError("stop/target distances must be positive fractions")
    return arr


def simulate(bars: pd.DataFrame, side: str, rules: ExitRules, entry: str = "next_open",
             stop=None, target=None, sessions: np.ndarray | None = None,
             exit_signal: np.ndarray | None = None) -> Outcomes:
    """Outcome of a trade signalled at every bar of one instrument.

    `bars` needs open/high/low/close columns and a DatetimeIndex in local exchange time.
    `stop`/`target` may be scalars or per-bar arrays (e.g. ATR-based) that override the rules.
    `exit_signal` (one boolean per bar) exits at the next open after the first true bar in the trade.
    """
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    if entry not in ENTRY_MODES:
        raise ValueError(f"entry must be one of {ENTRY_MODES}")
    o, h, l, c = (bars[col].to_numpy(dtype=float) for col in ("open", "high", "low", "close"))
    n = len(c)
    sess = session_ids(bars.index) if sessions is None else np.asarray(sessions)
    stops, targets = _levels(stop, rules.stop, n), _levels(target, rules.target, n)
    exits = None if exit_signal is None else np.asarray(exit_signal, dtype=bool)
    if exits is not None and exits.shape != (n,):
        raise ValueError(f"exit_signal must have length {n}, got shape {exits.shape}")
    gross = np.full(n, np.nan)
    exit_idx = np.full(n, -1, dtype=np.int64)
    reason = np.zeros(n, dtype=np.int8)
    risk = np.full(n, np.nan)
    if n < 2:
        return Outcomes(gross, exit_idx, reason, risk)
    session_last = np.flatnonzero(np.r_[sess[1:] != sess[:-1], True])  # last bar of each session
    long = side == "long"

    for k in range(n - 1):
        s = k + 1
        if rules.square_off_each_session:
            if sess[s] != sess[k]:
                continue  # signal on the session's last bar
            end = session_last[sess[k]]
            if (k if entry == "signal_close" else s) >= end:
                continue  # can't open a position on the square-off bar
        else:
            end = n - 1
        if rules.max_hold_bars is not None:
            end = min(end, s + rules.max_hold_bars - 1)
        if rules.max_hold_sessions is not None:
            end = min(end, session_last[min(sess[s] + rules.max_hold_sessions - 1, len(session_last) - 1)])

        e = c[k] if entry == "signal_close" else o[s]
        if not e > 0:
            continue
        stop_dist, target_dist = stops[k], targets[k]
        has_stop, has_target = not np.isnan(stop_dist), not np.isnan(target_dist)
        seg = slice(s, end + 1)
        if long:
            stop_px, target_px = e * (1 - stop_dist), e * (1 + target_dist)
            hit_stop = l[seg] <= stop_px if has_stop else None
            hit_target = h[seg] >= target_px if has_target else None
        else:
            stop_px, target_px = e * (1 + stop_dist), e * (1 - target_dist)
            hit_stop = h[seg] >= stop_px if has_stop else None
            hit_target = l[seg] <= target_px if has_target else None
        js = int(hit_stop.argmax()) if hit_stop is not None and hit_stop.any() else _NEVER
        jt = int(hit_target.argmax()) if hit_target is not None and hit_target.any() else _NEVER
        jx = _NEVER  # offset of the bar whose open fills a signal exit
        if exits is not None and end > s:
            flagged = exits[s:end]  # a signal on the last allowed bar would be overtaken by the time exit
            if flagged.any():
                jx = int(flagged.argmax()) + 1

        if jx != _NEVER and jx <= js and jx <= jt:
            j, x, r = s + jx, o[s + jx], SIGNAL
        elif js == _NEVER and jt == _NEVER:
            j, x, r = end, c[end], TIME
        elif jt < js:
            j, r = s + jt, TARGET
            x = max(o[j], target_px) if long else min(o[j], target_px)
        elif js < jt:
            j, r = s + js, STOP
            x = min(o[j], stop_px) if long else max(o[j], stop_px)
        else:  # both touched in one bar: the stop comes first unless the bar opened beyond the target
            j = s + js
            if (o[j] >= target_px) if long else (o[j] <= target_px):
                x, r = o[j], TARGET
            else:
                x, r = (min(o[j], stop_px) if long else max(o[j], stop_px)), STOP
        gross[k] = x / e - 1 if long else 1 - x / e
        exit_idx[k], reason[k], risk[k] = j, r, stop_dist
    return Outcomes(gross, exit_idx, reason, risk)


def select_trades(signal: np.ndarray, outcomes: Outcomes) -> np.ndarray:
    """Signal bars that become trades, allowing one open position at a time."""
    picked, busy_until = [], -1
    for i in np.flatnonzero(signal):
        if np.isnan(outcomes.gross[i]) or i <= busy_until:
            continue
        picked.append(i)
        busy_until = outcomes.exit_idx[i]
    return np.asarray(picked, dtype=np.int64)


def select_chain(signals: list[np.ndarray], outcomes: list[Outcomes]) -> list[tuple[int, int]]:
    """Like an if/elif chain: on each bar the first true signal wins; one open position at a time.
    Returns (bar index, position in `signals`) pairs."""
    choice = np.full(len(signals[0]), -1)
    for pos in reversed(range(len(signals))):
        choice = np.where(signals[pos], pos, choice)
    picked, busy_until = [], -1
    for i in np.flatnonzero(choice >= 0):
        out = outcomes[choice[i]]
        if np.isnan(out.gross[i]) or i <= busy_until:
            continue
        picked.append((int(i), int(choice[i])))
        busy_until = out.exit_idx[i]
    return picked


def trade_rows(ticker: str, index: pd.DatetimeIndex, picks: np.ndarray, outcomes: Outcomes,
               side: str, rule: str = "") -> pd.DataFrame:
    """One row per trade for signal bars `picks` (as returned by select_trades)."""
    idx = np.asarray(picks, dtype=np.int64)
    if len(idx) == 0:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    exits = outcomes.exit_idx[idx]
    signal_times, exit_times = index[idx], index[exits]
    return pd.DataFrame({
        "ticker": ticker, "rule": rule, "side": side,
        "signal_time": signal_times, "exit_time": exit_times,
        "signal_date": np.asarray(signal_times.date), "exit_date": np.asarray(exit_times.date),
        "tod": np.asarray(signal_times.strftime("%H:%M")),
        "gross": outcomes.gross[idx], "reason": outcomes.reason[idx],
        "hold_bars": exits - idx, "risk": outcomes.risk[idx],
    })


def concat_trades(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TRADE_COLUMNS)


def run_backtest(bars_by_ticker: dict[str, pd.DataFrame], signals: dict[str, np.ndarray], side: str,
                 rules: ExitRules, entry: str = "next_open", stops: dict | None = None,
                 targets: dict | None = None, rule: str = "", exits: dict | None = None) -> pd.DataFrame:
    """Simulate one strategy across many instruments; returns all trades.

    `signals[ticker]` is a boolean array aligned with `bars_by_ticker[ticker]`; `stops`/`targets`
    optionally map tickers to per-bar distance arrays (e.g. 2 x ATR / close), and `exits` to per-bar
    exit signals."""
    frames = []
    for ticker, bars in bars_by_ticker.items():
        if ticker not in signals:
            continue
        out = simulate(bars, side, rules, entry, stop=(stops or {}).get(ticker),
                       target=(targets or {}).get(ticker), exit_signal=(exits or {}).get(ticker))
        frames.append(trade_rows(ticker, bars.index, select_trades(signals[ticker], out), out, side, rule))
    return concat_trades(frames)
