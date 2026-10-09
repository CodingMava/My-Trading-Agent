"""Robustness checks: random-entry baselines, period stability, market regimes, walk-forward folds."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def outcome_pools(items: Iterable[tuple[np.ndarray, np.ndarray]]) -> dict[str, np.ndarray]:
    """Group the gross outcome of every tradeable bar by a key (time of day for intraday bars).

    `items` yields (keys, gross) arrays per instrument; bars with no possible trade (NaN) are skipped."""
    pools: dict[str, list[float]] = {}
    for keys, gross in items:
        ok = ~np.isnan(gross)
        for key, g in zip(np.asarray(keys)[ok], gross[ok]):
            pools.setdefault(key, []).append(g)
    return {key: np.asarray(values) for key, values in pools.items()}


def random_entry_test(pools: dict, trade_keys: pd.Series, trade_gross: pd.Series,
                      n_iter: int = 2000, seed: int = 7) -> tuple[float, float]:
    """Does the strategy beat random entries taken at the same keys (e.g. same time of day)?

    Returns (mean gross of the random entries, P(random mean >= strategy mean)). A small p-value means
    the entries carry information; a large one means timing is indistinguishable from chance."""
    if len(trade_keys) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    total = np.zeros(n_iter)
    for key, count in trade_keys.value_counts().items():
        pool = pools[key]
        total += pool[rng.integers(0, len(pool), size=(n_iter, count))].sum(axis=1)
    random_means = total / len(trade_keys)
    return float(random_means.mean()), float((random_means >= trade_gross.mean()).mean())


def same_day_random_test(pools: dict[str, pd.Series], trades: pd.DataFrame, n_iter: int = 2000,
                         seed: int = 7) -> tuple[float, float]:
    """Random-entry baseline that keeps trades entered on the same day together.

    Signals in correlated instruments often fire on the same day (many stocks after one market drop);
    drawn independently, they'd make the baseline look more certain than it is. Here, for every day the
    strategy entered, one random day is drawn on which all the instruments it entered that day could be
    entered, and their outcomes on that day stand in for the strategy's. `pools` maps each instrument to
    the gross outcome of entering on each day (a Series indexed by date); `trades` needs ticker,
    signal_date and gross. Returns (mean gross of the random entries, P(random mean >= strategy mean))."""
    if len(trades) == 0:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    total, sums = np.zeros(n_iter), {}
    for _, tickers in trades.groupby("signal_date", sort=True)["ticker"]:
        key = tuple(sorted(tickers))
        if key not in sums:  # each instrument's outcome on the days all of them could be entered, added up
            sums[key] = pd.concat([pools[t] for t in key], axis=1, join="inner").sum(axis=1).to_numpy()
        day_sums = sums[key]
        total += day_sums[rng.integers(0, len(day_sums), size=n_iter)]
    random_means = total / len(trades)
    return float(random_means.mean()), float((random_means >= trades["gross"].mean()).mean())


def clustered_t(values, clusters) -> float:
    """t-statistic of the mean with a cluster-robust (CR1) standard error, for observations that may be
    correlated within a cluster (e.g. trades signalled in the same week). With one observation per
    cluster it equals the ordinary t-statistic."""
    x = np.asarray(values, dtype=float)
    groups = pd.factorize(pd.Series(list(clusters)))[0]
    n, k = len(x), int(groups.max()) + 1 if len(x) else 0
    if k < 2:
        return np.nan
    residual_sums = np.bincount(groups, weights=x - x.mean())
    variance = k / (k - 1) * float((residual_sums ** 2).sum()) / n ** 2
    return float(x.mean() / np.sqrt(variance)) if variance > 0 else np.nan


def period_table(trades: pd.DataFrame, cost: float) -> pd.DataFrame:
    """Net expectancy (%) and trade count per half-year block of signal dates."""
    if len(trades) == 0:
        return pd.DataFrame(columns=["mean", "count"])
    dt = pd.to_datetime(pd.Series(trades["signal_date"].to_numpy()))
    block = dt.dt.year.astype(str) + np.where(dt.dt.month <= 6, "H1", "H2")
    net = (trades["gross"].to_numpy(dtype=float) - cost) * 100
    return pd.DataFrame({"block": block.to_numpy(), "net": net}).groupby("block")["net"].agg(["mean", "count"])


def trend_regime(index_close: pd.Series, window: int = 50) -> pd.Series:
    """Date -> was the index's previous close above its moving average? (known before the open)"""
    regime = (index_close > index_close.rolling(window).mean()).shift(1)
    regime.index = regime.index.date
    return regime


def volatility_regime(vol_index_close: pd.Series, window: int = 250, min_periods: int = 60) -> pd.Series:
    """Date -> was the volatility index's previous close above its rolling median?"""
    regime = (vol_index_close > vol_index_close.rolling(window, min_periods=min_periods).median()).shift(1)
    regime.index = regime.index.date
    return regime


def regime_table(trades: pd.DataFrame, cost: float, regimes: dict[str, pd.Series]) -> dict:
    """Net expectancy (%), win rate and count when each regime was on vs off."""
    net = trades["gross"].astype(float) - cost
    row = {}
    for name, regime in regimes.items():
        state = trades["signal_date"].map(regime)
        for label, mask in ((f"{name}", state == True), (f"not {name}", state == False)):  # noqa: E712
            row[f"{label} n"] = int(mask.sum())
            row[f"{label} exp%"] = 100 * net[mask].mean() if mask.any() else np.nan
            row[f"{label} win%"] = 100 * (net[mask] > 0).mean() if mask.any() else np.nan
    return row


def walk_forward_folds(dates, train_size: int, test_size: int, step: int | None = None,
                       anchored: bool = False) -> list[tuple[list, list]]:
    """Rolling-origin folds over sorted unique dates: fit on `train_size` dates, test on the next
    `test_size`, then move forward by `step` (default: test_size). Test windows never overlap
    their training window, and folds stay in chronological order."""
    unique = sorted(set(dates))
    step = step or test_size
    folds, start = [], 0
    while start + train_size + test_size <= len(unique):
        train = unique[0 if anchored else start:start + train_size]
        test = unique[start + train_size:start + train_size + test_size]
        folds.append((train, test))
        start += step
    return folds
