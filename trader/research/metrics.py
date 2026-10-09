"""Trade statistics. Everything is net of costs unless its name says gross."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader.research.simulator import SIGNAL, STOP, TARGET, TIME


def summarize(trades: pd.DataFrame, cost: float, session_dates, min_trades_per_ticker: int = 3) -> dict:
    """Headline statistics for a set of trades.

    `cost` is the round-trip cost as a fraction of notional (see costs.py). `session_dates` lists every
    session in the test period, so days without trades count as flat days in Sharpe and Sortino.
    Path statistics (expectancy in units, drawdown, total) are in R (P&L / stop distance) when every
    trade had a stop, otherwise in percent of position size; `unit` says which. Simultaneous exits are
    netted before the drawdown is measured, so the result doesn't depend on row order.
    """
    if len(trades) == 0:
        return {"trades": 0}
    session_dates = list(session_dates)
    net = trades["gross"].astype(float) - cost
    n = len(net)
    wins, losses = net[net > 0], net[net <= 0]
    profit_factor = wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf
    sd = net.std(ddof=1)
    t_stat = net.mean() / (sd / np.sqrt(n)) if n > 2 and sd > 0 else np.nan

    risk = trades["risk"].astype(float)
    unit = "R" if risk.notna().all() and (risk > 0).all() else "%"
    per_trade = net / risk if unit == "R" else net * 100
    path = per_trade.groupby(trades["exit_time"]).sum().cumsum().to_numpy()
    peak = np.maximum.accumulate(np.r_[0.0, path])[1:]
    daily = per_trade.groupby(trades["exit_date"]).sum().reindex(session_dates, fill_value=0.0)
    downside = np.sqrt((np.minimum(daily, 0) ** 2).mean())

    ordered = sorted(session_dates)
    half = ordered[len(ordered) // 2] if ordered else None
    first = net[trades["signal_date"] < half] if half else net.iloc[:0]
    second = net[trades["signal_date"] >= half] if half else net.iloc[:0]
    per_ticker = net.groupby(trades["ticker"]).agg(["mean", "count"])
    per_ticker = per_ticker[per_ticker["count"] >= min_trades_per_ticker]
    reason = trades["reason"].astype(int)

    return {
        "trades": n,
        "win_pct": 100 * (net > 0).mean(),
        "avg_win_pct": 100 * wins.mean() if len(wins) else np.nan,
        "avg_loss_pct": 100 * losses.mean() if len(losses) else np.nan,
        "profit_factor": profit_factor,
        "exp_gross_pct": 100 * trades["gross"].astype(float).mean(),
        "exp_net_pct": 100 * net.mean(),
        "t_stat": t_stat,
        "unit": unit,
        "exp_units": per_trade.mean(),
        "max_dd_units": float((path - peak).min()),
        "total_units": float(path[-1]),
        "sharpe": daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else np.nan,
        "sortino": daily.mean() / downside * np.sqrt(252) if downside > 0 else np.nan,
        "target_pct": 100 * (reason == TARGET).mean(),
        "stop_pct": 100 * (reason == STOP).mean(),
        "time_pct": 100 * (reason == TIME).mean(),
        "signal_pct": 100 * (reason == SIGNAL).mean(),
        "avg_hold_bars": trades["hold_bars"].astype(float).mean(),
        "first_half_exp_pct": 100 * first.mean() if len(first) else np.nan,
        "first_half_trades": len(first),
        "second_half_exp_pct": 100 * second.mean() if len(second) else np.nan,
        "second_half_trades": len(second),
        "breadth": f"{int((per_ticker['mean'] > 0).sum())}/{len(per_ticker)}",
    }
