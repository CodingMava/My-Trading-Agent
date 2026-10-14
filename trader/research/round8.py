"""Research round 8: cross-sectional momentum on a survivorship-free NSE universe, judged against
docs/research/round8-preregistration.md.

    python -m trader.research.round8 --stage 1    # development and replication: writes docs/research/round8-stage1.md
    python -m trader.research.round8 --stage 2    # the decision, once: round8-results.md and the evidence for N1, N2

At each month-end the eligible NSE equity shares are ranked by liquidity (median traded value over 126 sessions). N1
takes the 5 highest 12-1 month momentum scores among the 100 most liquid; N2 among ranks 101-300. Each pick is bought
at the next session's open with a 10% stop and sold at the open after the next month-end. The baseline is 5 random
stocks from the same tier in the same months, traded by the same rules. The universe comes from NSE's own daily files,
which include delisted companies, so it has no survivorship bias.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research.costs import ZERODHA_DELIVERY
from trader.research.datasets import DATA_DIR, load_dataset, text_sha256
from trader.research.nse_bhavcopy import PANEL_DIR, load_isins, load_panel
from trader.research.validation import clustered_t

IST = ZoneInfo("Asia/Kolkata")
PREREGISTRATION = ROOT / "docs" / "research" / "round8-preregistration.md"
PREREGISTRATION_SHA256 = "ea4a3c0c281eed614e896c366f69cfc39d89433bdd8bd61b567c3f8c199e1094"  # pinned 2026-10-14 01:38 IST
STAGE1_RESULTS = ROOT / "docs" / "research" / "round8-stage1.md"
RESULTS = ROOT / "docs" / "research" / "round8-results.md"
PANEL_SHA256 = "afb79ad2ce778f187059302864576fba478c9d5a59ae5853cf909007cfb0fb01"  # data/round8/nse_eq/panel.parquet
NIFTY = DATA_DIR / "round4" / "nse_nifty_daily"  # ^NSEI, informational benchmark and trend regime
AUX = DATA_DIR / "round6" / "aux_daily"  # ^INDIAVIX, informational regime

TIERS = {"N1": (1, 100), "N2": (101, 300)}
NAMES = {"N1": "12-1 month momentum, top 5 of the 100 most liquid NSE stocks, monthly",
         "N2": "12-1 month momentum, top 5 of liquidity ranks 101-300, monthly"}
TOP, LOOKBACK, SKIP = 5, 252, 21
MIN_ROWS, PRESENCE_WINDOW, MIN_PRESENT = 273, 252, 227
LIQUIDITY_WINDOW, MIN_PRICE, MAX_STALE = 126, 10.0, 10
STOP = 0.10  # one R
NOTIONAL, EQUITY = 50_000, 1_000_000
ENGINE_WEIGHT, FULL_WEIGHT = 0.05, 0.20
SLIPPAGE = {"N1": 0.0005, "N2": 0.0010}
COSTS = replace(ZERODHA_DELIVERY, exchange_rate=0.0000307, verified="2026-10-14")  # NSE's 0.00307% since Oct 2024
ROUND_TRIP = {key: COSTS.with_slippage(SLIPPAGE[key]).round_trip(NOTIONAL) for key in TIERS}
STAGE1_LAST_SIGNAL = date(2013, 5, 31)
STAGE2_FIRST_SIGNAL, STAGE2_LAST_SIGNAL = date(2013, 6, 28), date(2026, 8, 31)
DRAWS, SEED, CHUNK = 20_000, 8, 500
TESTS_IN_PROJECT = 25  # H1-H14, C1-C6, I1-I3, N1-N2
CROSS_ROUND_ALPHA = 0.05 / TESTS_IN_PROJECT
ETF_SYMBOLS: frozenset[str] = frozenset()  # Appendix A of the pre-registration, from the audit
DELISTING_HAIRCUT = 0.30  # informational sensitivity only
VARIANT_LOOKBACKS = {"6-1": 126, "9-1": 189, "12-1": 252}


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


# ------------------------------------------------------------------------------------------------ data
@dataclass
class Security:
    """One security's rows laid on the market's session grid (NaN or False where it has no row)."""
    sid: str
    present: np.ndarray
    eq: np.ndarray
    raw_close: np.ndarray
    raw_open: np.ndarray
    raw_high: np.ndarray
    raw_low: np.ndarray
    raw_prev: np.ndarray
    value: np.ndarray  # 0 without a row
    adj_open: np.ndarray
    adj_low: np.ndarray
    adj_close: np.ndarray
    last_row: np.ndarray = field(default=None)  # index of the latest row at or before each session (-1 before any)


def is_equity_share(isins: pd.Series, sid: str, etfs: frozenset[str] = ETF_SYMBOLS) -> bool:
    """("Definitions") An ISIN beginning INE on any row; never a fund (INF); without any ISIN, not on the ETF list."""
    values = isins.dropna().astype(str)
    if values.str.startswith("INF").any():
        return False
    if values.str.startswith("INE").any():
        return True
    return values.empty and sid not in etfs


PANEL_COLUMNS = ["date", "sid", "symbol", "series", "open", "high", "low", "close", "prevclose", "value", "adj"]


def session_list(panel: pd.DataFrame) -> list[date]:
    return [pd.Timestamp(d).date() for d in sorted(panel["date"].unique())]


def isins_by_sid(panel: pd.DataFrame, isins: dict[str, str]) -> dict[str, pd.Series]:
    """Every ISIN seen for any symbol a security traded under (from the frozen panel's isins.csv)."""
    pairs = panel[["sid", "symbol"]].drop_duplicates()
    out: dict[str, list[str]] = {}
    for sid, symbol in zip(pairs["sid"].astype(str), pairs["symbol"].astype(str)):
        out.setdefault(sid, []).extend(x for x in str(isins.get(symbol, "")).split(";") if x)
    return {sid: pd.Series(values, dtype="object") for sid, values in out.items()}


def iter_securities(panel: pd.DataFrame, sessions: list[date], isins: dict[str, pd.Series],
                    keep: set[str] | None = None, etfs: frozenset[str] = ETF_SYMBOLS):
    """Each equity share's rows laid on the session grid (prices as float32 to fit in memory)."""
    position = {pd.Timestamp(d): i for i, d in enumerate(sessions)}
    n = len(sessions)
    for sid, rows in panel.groupby("sid", sort=True, observed=True):
        sid = str(sid)
        if keep is not None and sid not in keep:
            continue
        if not is_equity_share(isins.get(sid, pd.Series(dtype="object")), sid, etfs):
            continue
        idx = rows["date"].map(position).to_numpy()

        def grid(values, fill=np.nan, dtype=np.float32):
            arr = np.full(n, fill, dtype=dtype)
            arr[idx] = values
            return arr

        adj = rows["adj"].to_numpy(float)
        present = grid(True, False, bool)
        last = np.maximum.accumulate(np.where(present, np.arange(n), -1)).astype(np.int32)
        yield Security(
            sid=sid, present=present, eq=grid((rows["series"].astype(str) == "EQ").to_numpy(), False, bool),
            raw_close=grid(rows["close"].to_numpy(float)), raw_open=grid(rows["open"].to_numpy(float)),
            raw_high=grid(rows["high"].to_numpy(float)), raw_low=grid(rows["low"].to_numpy(float)),
            raw_prev=grid(rows["prevclose"].to_numpy(float)), value=grid(rows["value"].fillna(0).to_numpy(float), 0.0),
            adj_open=grid(rows["open"].to_numpy(float) * adj), adj_low=grid(rows["low"].to_numpy(float) * adj),
            adj_close=grid(rows["close"].to_numpy(float) * adj), last_row=last)


def securities_from_panel(panel: pd.DataFrame, isins: dict[str, pd.Series] | None = None,
                          etfs: frozenset[str] = ETF_SYMBOLS) -> tuple[list[date], dict[str, Security]]:
    sessions = session_list(panel)
    isins = isins if isins is not None else {}
    return sessions, {sec.sid: sec for sec in iter_securities(panel, sessions, isins, None, etfs)}


def month_ends(sessions: list[date]) -> list[int]:
    """Indices of the last session of each calendar month."""
    keys = [(d.year, d.month) for d in sessions]
    return [i for i in range(len(sessions)) if i + 1 == len(sessions) or keys[i + 1] != keys[i]]


def score_at(sec: Security, i: int, lookback: int) -> float:
    """Adjusted close at i-21 / at i-lookback - 1, from the latest rows at or before those sessions; NaN if either row
    is more than MAX_STALE sessions old or missing."""
    a, b = i - SKIP, i - lookback
    if b < 0:
        return np.nan
    ra, rb = sec.last_row[a], sec.last_row[b]
    if ra < 0 or rb < 0 or a - ra > MAX_STALE or b - rb > MAX_STALE:
        return np.nan
    return float(sec.adj_close[ra] / sec.adj_close[rb] - 1)


def features(sessions: list[date], secs, signal_idx: list[int]) -> pd.DataFrame:
    """Every eligible security at every signal date: liquidity and the momentum scores ("Eligible at signal date s").
    `secs` is a dict of securities or an iterable of them."""
    rows = []
    signal_idx = np.asarray(signal_idx)
    for sec in (secs.values() if isinstance(secs, dict) else secs):
        sid = sec.sid
        count = np.cumsum(sec.present)
        presence = count - np.r_[np.zeros(PRESENCE_WINDOW), count[:-PRESENCE_WINDOW]]
        liquidity = pd.Series(sec.value).rolling(LIQUIDITY_WINDOW).median().to_numpy()
        ok = (sec.eq[signal_idx] & (sec.raw_close[signal_idx] >= MIN_PRICE) & (count[signal_idx] >= MIN_ROWS)
              & (presence[signal_idx] >= MIN_PRESENT) & ~np.isnan(liquidity[signal_idx]))
        for i in signal_idx[ok]:
            scores = {f"score_{label}": score_at(sec, int(i), lb) for label, lb in VARIANT_LOOKBACKS.items()}
            if np.isnan(scores["score_12-1"]):
                continue
            rows.append({"i": int(i), "sid": sid, "liquidity": float(liquidity[i]), **scores})
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    table = table.sort_values(["i", "liquidity", "sid"], ascending=[True, False, True])
    table["rank"] = table.groupby("i").cumcount() + 1
    return table.reset_index(drop=True)


# ------------------------------------------------------------------------------------------- one trade
def enterable(sec: Security, e: int) -> bool:
    """("Not bought") A row on the entry session, a positive open, and not locked at the upper band all day."""
    if e >= len(sec.present) or not sec.present[e] or not sec.raw_open[e] > 0:
        return False
    o, h, l, c, p = sec.raw_open[e], sec.raw_high[e], sec.raw_low[e], sec.raw_close[e], sec.raw_prev[e]
    return not (o == h == l == c and o > p)


def simulate(sec: Security, e: int, x0: int, stop: float | None = STOP) -> dict:
    """Buy at the adjusted open of session e; the stop watched on sessions e..x0-1; exit at the open of x0 or of the
    next session with a row; a security that never trades again exits at its last close ("The trade")."""
    entry = sec.adj_open[e]
    level = entry * (1 - stop) if stop else -np.inf
    n = len(sec.present)
    for j in range(e, min(x0, n)):
        if sec.present[j] and sec.adj_low[j] <= level:
            fill = min(level, sec.adj_open[j])
            return {"gross": fill / entry - 1, "reason": "stop", "exit_i": j, "gapped": bool(sec.adj_open[j] < level)}
    j = x0
    while j < n and not sec.present[j]:
        j += 1
    if j < n:
        return {"gross": sec.adj_open[j] / entry - 1, "reason": "time" if j == x0 else "time, delayed",
                "exit_i": j, "gapped": False}
    last = int(sec.last_row[n - 1])
    return {"gross": sec.adj_close[last] / entry - 1, "reason": "no further rows", "exit_i": last, "gapped": False}


# ------------------------------------------------------------------------------------------------ months
def months(sessions: list[date], first: date | None, last: date) -> list[tuple[int, int, int]]:
    """(signal i, entry e = i+1, scheduled exit x0 = next signal + 1) for signal dates in [first, last] whose exit
    session exists."""
    ends = month_ends(sessions)
    out = []
    for a, b in zip(ends, ends[1:]):
        d = sessions[a]
        if (first is None or d >= first) and d <= last and b + 1 < len(sessions):
            out.append((a, a + 1, b + 1))
    return out


def run_month(table_i: pd.DataFrame, secs: dict[str, Security], e: int, x0: int, key: str, picks: int = TOP,
              score: str = "score_12-1", stop: float | None = STOP) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """One tier in one month: the picks' trades, and the pool (every enterable member's net return and gross without
    a stop, for the baseline and the tier average)."""
    lo, hi = TIERS[key]
    tier = table_i[(table_i["rank"] >= lo) & (table_i["rank"] <= hi)]
    cost, extra = ROUND_TRIP[key], SLIPPAGE[key]
    pool_net, pool_plain, trades = [], [], []
    outcome = {}
    for sid in tier["sid"]:
        sec = secs[sid]
        if not enterable(sec, e):
            continue
        t = simulate(sec, e, x0, stop)
        t["net"] = t["gross"] - cost - (extra if t["reason"] == "stop" else 0.0)
        outcome[sid] = t
        pool_net.append(t["net"])
        pool_plain.append(simulate(sec, e, x0, None)["gross"])
    ranked = tier.dropna(subset=[score]).sort_values([score, "sid"], ascending=[False, True]).head(picks)
    for sid, value, rank in zip(ranked["sid"], ranked[score], ranked["rank"]):
        if sid in outcome:  # a pick that can't be bought leaves its slot in cash for the month
            trades.append({"ticker": sid, "score": float(value), "rank": int(rank), **outcome[sid]})
    return trades, np.asarray(pool_net), np.asarray(pool_plain)


def run_tier(key: str, table: pd.DataFrame, secs: dict[str, Security], sessions: list[date],
             month_list: list[tuple[int, int, int]], picks: int = TOP, score: str = "score_12-1",
             stop: float | None = STOP) -> tuple[pd.DataFrame, dict[int, np.ndarray], dict[int, np.ndarray]]:
    by_i = dict(tuple(table.groupby("i"))) if len(table) else {}
    rows, pools, plain = [], {}, {}
    for i, e, x0 in month_list:
        if i not in by_i:
            continue
        trades, pool_net, pool_plain = run_month(by_i[i], secs, e, x0, key, picks, score, stop)
        if len(pool_net):
            pools[i], plain[i] = pool_net, pool_plain
        for t in trades:
            exit_i = t["exit_i"]
            rows.append({"signal_i": i, "signal_date": sessions[i], "entry_date": sessions[e],
                         "exit_date": sessions[exit_i], "exit_time": sessions[exit_i], "hold_bars": exit_i - e,
                         "risk": STOP if stop else np.nan, **t})
    trades = pd.DataFrame(rows)
    if len(trades):
        trades["cost"] = trades["gross"] - trades["net"]
        trades["R"] = trades["net"] / STOP
        trades["stopped"] = trades["reason"] == "stop"
    return trades, pools, plain


# ------------------------------------------------------------------------------------------------ tests
def baseline(trades: pd.DataFrame, pools: dict[int, np.ndarray], draws: int = DRAWS, seed: int = SEED) -> tuple[float, float, np.ndarray]:
    """("The random baseline, precisely") For every month with k trades, k distinct members of that month's pool, in
    every draw. Returns (mean of the draws' statistics, p, the statistics)."""
    rng = np.random.default_rng(seed)
    counts = trades.groupby("signal_i").size()
    total, n = np.zeros(draws), int(counts.sum())
    for i, k in counts.items():
        pool = pools[i]
        for start in range(0, draws, CHUNK):
            size = min(CHUNK, draws - start)
            keys = rng.random((size, len(pool)))
            chosen = np.argpartition(keys, k - 1, axis=1)[:, :k] if k < len(pool) else np.tile(np.arange(len(pool)), (size, 1))
            total[start:start + size] += pool[chosen].sum(axis=1)
    stats = total / n
    observed = float(trades["net"].mean())
    return float(stats.mean()), (int((stats >= observed).sum()) + 1) / (draws + 1), stats


def holm(p: dict[str, float]) -> dict[str, float]:
    order = sorted(p, key=p.get)
    m, out, running = len(order), {}, 0.0
    for j, key in enumerate(order):
        running = max(running, min(1.0, (m - j) * p[key]))
        out[key] = running
    return out


def drawdown_r(r_in_exit_order: np.ndarray) -> float:
    path = np.cumsum(r_in_exit_order)
    return float(-(path - np.maximum.accumulate(np.r_[0.0, path])[1:]).min()) if len(path) else 0.0


def r_in_exit_order(trades: pd.DataFrame) -> np.ndarray:
    """Trades' R summed by exit session, in exit order (simultaneous exits netted, so row order doesn't matter)."""
    return trades.groupby("exit_date")["R"].sum().sort_index().to_numpy(float)


def criteria(trades: pd.DataFrame, span: tuple[date, date], p_holm: float, p_raw: float) -> tuple[list[Check], dict]:
    """The pinned criteria, each hypothesis on its own ("Pass criteria")."""
    net, n = trades["net"].astype(float), len(trades)
    wins, losses = net[net > 0], net[net <= 0]
    mean = net.mean() if n else np.nan
    sd = net.std(ddof=1) if n > 1 else np.nan
    t = mean / (sd / np.sqrt(n)) if n > 2 and sd > 0 else np.nan
    stress = (trades["gross"] - 1.5 * trades["cost"]).mean() if n else np.nan
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else (np.inf if len(wins) else np.nan)
    avg_win, avg_loss = (wins.mean() if len(wins) else np.nan), (losses.mean() if len(losses) else np.nan)
    worst_r = trades["R"].min() if n else np.nan
    mid = span[0] + (span[1] - span[0]) / 2
    halves = [net[trades["signal_date"] < mid].mean(), net[trades["signal_date"] >= mid].mean()]
    years = net.groupby([d.year for d in trades["signal_date"]]).agg(["count", "mean"])
    counted = years[years["count"] >= 10]
    share_years = float((counted["mean"] > 0).mean()) if len(counted) else np.nan
    per_stock = net.groupby(trades["ticker"]).agg(["count", "mean", "sum"])
    counted_stocks = per_stock[per_stock["count"] >= 5]
    breadth = float((counted_stocks["mean"] > 0).mean()) if len(counted_stocks) else np.nan
    top_stock = per_stock["sum"].idxmax() if len(per_stock) else None
    without_top = net[trades["ticker"] != top_stock].mean() if top_stock is not None else np.nan
    t_month = clustered_t(net, trades["signal_i"]) if n else np.nan
    depth = drawdown_r(r_in_exit_order(trades))
    ratio = -avg_loss / avg_win if avg_win and avg_win > 0 and not np.isnan(avg_loss) else np.nan

    def ok(value, rule):
        return bool(not pd.isna(value) and rule(value))

    checks = [
        Check(1, "At least 50 trades", f"{n}", n >= 50),
        Check(2, "Win rate at least 50%", f"{100 * (net > 0).mean():.1f}%" if n else "-",
              ok((net > 0).mean() if n else np.nan, lambda v: v >= 0.5)),
        Check(3, "Expectancy above 0 at base and 1.5x costs", f"{100 * mean:+.4f}% / {100 * stress:+.4f}%" if n else "-",
              ok(mean, lambda v: v > 0) and ok(stress, lambda v: v > 0)),
        Check(4, "t-statistic at least 2.0", f"{t:.2f}", ok(t, lambda v: v >= 2.0)),
        Check(5, "Beats the random baseline: Holm-adjusted p below 0.05", f"{p_holm:.5f}", ok(p_holm, lambda v: v < 0.05)),
        Check(6, "Profit factor at least 1.3", f"{pf:.2f}", ok(pf, lambda v: v >= 1.3)),
        Check(7, "Average loss at most 1.5x the average win; no trade worse than -3R",
              f"{100 * avg_loss:+.3f}% vs {100 * avg_win:+.3f}% ({ratio:.2f}x); worst {worst_r:.2f}R",
              ok(ratio, lambda v: v <= 1.5) and ok(worst_r, lambda v: v >= -3.0)),
        Check(8, "Expectancy above 0 in each half of the span",
              f"{100 * halves[0]:+.4f}% / {100 * halves[1]:+.4f}% (split {mid})", all(ok(h, lambda v: v > 0) for h in halves)),
        Check(9, "At least 70% of calendar years with 10+ trades profitable",
              f"{share_years:.0%} of {len(counted)} years" if len(counted) else "-", ok(share_years, lambda v: v >= 0.70)),
        Check(10, "At least 60% of stocks with 5+ trades profitable; expectancy above 0 without the top stock",
              f"{breadth:.0%} of {len(counted_stocks)} stocks; {100 * without_top:+.4f}% without {top_stock}",
              ok(breadth, lambda v: v >= 0.60) and ok(without_top, lambda v: v > 0)),
        Check(11, "Cluster-robust t-statistic (signal months as clusters) at least 2.0", f"{t_month:.2f}",
              ok(t_month, lambda v: v >= 2.0)),
        Check(12, f"Raw random-baseline p below 0.05/{TESTS_IN_PROJECT} = {CROSS_ROUND_ALPHA:.4f}", f"{p_raw:.5f}",
              ok(p_raw, lambda v: v < CROSS_ROUND_ALPHA)),
        Check(13, "Drawdown no deeper than 20R (cumulative R in exit order)", f"{depth:.1f}R", depth <= 20.0),
    ]
    stats = {"trades": n, "win_rate": float((net > 0).mean()) if n else np.nan, "mean_net": mean, "sd_net": sd,
             "mean_gross": float(trades["gross"].mean()) if n else np.nan, "t": t, "t_clustered": t_month,
             "profit_factor": pf, "avg_win": avg_win, "avg_loss": avg_loss, "median_net": float(net.median()) if n else np.nan,
             "wins": int((net > 0).sum()), "losses": int((net <= 0).sum()), "worst_r": worst_r,
             "max_drawdown_r": depth, "stops": int(trades["stopped"].sum()) if n else 0,
             "gapped_stops": int(trades["gapped"].sum()) if n else 0, "years": years, "breadth": breadth,
             "top_stock": top_stock, "without_top": without_top}
    return checks, stats


# ---------------------------------------------------------------------------------------- informational
def wilson(wins: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = wins / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def stationary_bootstrap_means(x: np.ndarray, mean_block: float = 6, n_boot: int = 10_000, seed: int = 9) -> np.ndarray:
    """Politis-Romano stationary bootstrap of the mean of a series of monthly values."""
    rng = np.random.default_rng(seed)
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return np.array([])
    out = np.empty(n_boot)
    p = 1.0 / mean_block
    for b in range(n_boot):
        idx = np.empty(n, dtype=int)
        idx[0] = rng.integers(n)
        jumps = rng.random(n) < p
        starts = rng.integers(0, n, size=n)
        for t in range(1, n):
            idx[t] = starts[t] if jumps[t] else (idx[t - 1] + 1) % n
        out[b] = x[idx].mean()
    return out


def monthly_table(trades: pd.DataFrame, plain: dict[int, np.ndarray], pools: dict[int, np.ndarray]) -> pd.DataFrame:
    """Per signal month: the picks' mean net, the pool's mean net (random-pick expectation, same rules) and the
    tier's equal-weighted buy-and-hold gross (no stop)."""
    picks = trades.groupby("signal_i").agg(picks_net=("net", "mean"), n=("net", "size"), picks_sum=("net", "sum"))
    picks["pool_net"] = [pools[i].mean() for i in picks.index]
    picks["tier_gross"] = [plain[i].mean() for i in picks.index]
    picks["excess"] = picks["picks_net"] - picks["pool_net"]
    return picks


def portfolio_stats(monthly_returns: pd.Series) -> dict:
    r = monthly_returns.astype(float)
    if not len(r):
        return {}
    equity = (1 + r).cumprod()
    years = len(r) / 12
    downside = np.sqrt((np.minimum(r, 0) ** 2).mean())
    return {"cagr": float(equity.iloc[-1] ** (1 / years) - 1), "vol": float(r.std() * np.sqrt(12)),
            "sharpe": float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else np.nan,
            "sortino": float(r.mean() / downside * np.sqrt(12)) if downside > 0 else np.nan,
            "max_drawdown": float((equity / equity.cummax() - 1).min())}


def kill_switch_replay(trades: pd.DataFrame, secs: dict[str, Security], sessions: list[date]) -> dict:
    """The Rs 10,00,000 account at the engine's size, marked to market every session; the first session on which the
    10% kill switch would have engaged."""
    if not len(trades):
        return {}
    equity, peak = float(EQUITY), float(EQUITY)
    engaged = None
    worst = 0.0
    position = {d: k for k, d in enumerate(sessions)}
    for _, group in trades.groupby("signal_i"):
        start_equity = equity
        entry_i = position[group["entry_date"].iloc[0]]
        last_exit = int(group["exit_i"].max())
        path = np.zeros(last_exit - entry_i + 1)
        for row in group.itertuples(index=False):
            sec = secs[row.ticker]
            entry = sec.adj_open[entry_i]
            w = ENGINE_WEIGHT * start_equity
            cost_in = (row.cost / 2) * w
            value = np.empty(len(path))
            last_close = entry
            for j in range(entry_i, last_exit + 1):
                k = j - entry_i
                if j < row.exit_i:
                    if sec.present[j]:
                        last_close = sec.adj_close[j]
                    value[k] = w * (last_close / entry - 1) - cost_in
                else:
                    value[k] = row.net * w
            path += value
        for k, pnl in enumerate(path):
            level = start_equity + pnl
            peak = max(peak, level)
            dd = level / peak - 1
            worst = min(worst, dd)
            if engaged is None and dd <= -0.10:
                engaged = sessions[entry_i + k]
        equity = start_equity + path[-1]
        peak = max(peak, equity)
    return {"final_equity": equity, "max_drawdown": worst, "kill_switch_session": engaged}


def dsr(excess: np.ndarray, trials: int, sr_variance: float) -> dict:
    """Deflated Sharpe ratio (Bailey and López de Prado 2014) of a monthly series, against the expected maximum Sharpe
    of `trials` unskilled trials whose Sharpe ratios vary with `sr_variance` (both per month)."""
    x = np.asarray(excess, float)
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return {}
    sr = x.mean() / x.std(ddof=1)
    skew = float(((x - x.mean()) ** 3).mean() / x.std(ddof=0) ** 3)
    kurt = float(((x - x.mean()) ** 4).mean() / x.std(ddof=0) ** 4)
    nd, gamma = NormalDist(), 0.5772156649
    expected_max = np.sqrt(sr_variance) * ((1 - gamma) * nd.inv_cdf(1 - 1 / trials) + gamma * nd.inv_cdf(1 - 1 / (trials * np.e)))
    se = np.sqrt((1 - skew * sr + (kurt - 1) / 4 * sr ** 2) / (n - 1))
    return {"sr_monthly": float(sr), "sr_annual": float(sr * np.sqrt(12)), "expected_max_sr_monthly": float(expected_max),
            "dsr": float(nd.cdf((sr - expected_max) / se)), "psr_vs_zero": float(nd.cdf(sr / se)), "skew": skew,
            "kurtosis": kurt, "months": n, "trials": trials}


def pbo(matrix: np.ndarray, blocks: int = 16) -> dict:
    """Probability of backtest overfitting by combinatorially symmetric cross-validation (Bailey, Borwein, López de
    Prado and Zhu): months x variants of monthly excess returns, cut into `blocks` contiguous blocks."""
    t, v = matrix.shape
    if t < blocks * 2 or v < 2:
        return {}
    parts = np.array_split(np.arange(t), blocks)
    logits = []
    for chosen in combinations(range(blocks), blocks // 2):
        ins = np.concatenate([parts[b] for b in chosen])
        outs = np.concatenate([parts[b] for b in range(blocks) if b not in chosen])
        def sharpe(rows):
            m, s = matrix[rows].mean(axis=0), matrix[rows].std(axis=0, ddof=1)
            return np.where(s > 0, m / s, -np.inf)
        best = int(np.argmax(sharpe(ins)))
        oos = sharpe(outs)
        rank = (oos < oos[best]).sum() + 1  # 1 = worst
        w = rank / (v + 1)
        logits.append(np.log(w / (1 - w)))
    logits = np.asarray(logits)
    return {"pbo": float((logits <= 0).mean()), "combinations": len(logits), "median_logit": float(np.median(logits))}


def regimes(trades: pd.DataFrame) -> dict:
    out = {}
    try:
        nifty = load_dataset(NIFTY)["^NSEI"]["close"].dropna()
        nifty.index = pd.to_datetime(nifty.index).tz_localize(None).date if getattr(nifty.index, "tz", None) else pd.to_datetime(nifty.index).date
        above = (nifty > nifty.rolling(200).mean())
        state = trades["signal_date"].map(lambda d: bool(above[above.index <= d].iloc[-1]) if (above.index <= d).any() else None)
        out["NIFTY above its 200-session average"] = {k: summary(trades.loc[state == v, "net"]) for k, v in (("yes", True), ("no", False))}
    except (FileNotFoundError, KeyError, ValueError):
        pass
    try:
        vix = load_dataset(AUX)["^INDIAVIX"]["close"].dropna()
        vix.index = pd.to_datetime(vix.index).tz_localize(None).date if getattr(vix.index, "tz", None) else pd.to_datetime(vix.index).date
        high = vix > vix.rolling(250, min_periods=60).median()
        state = trades["signal_date"].map(lambda d: bool(high[high.index <= d].iloc[-1]) if (high.index <= d).any() else None)
        out["India VIX above its 250-session median"] = {k: summary(trades.loc[state == v, "net"]) for k, v in (("yes", True), ("no", False))}
    except (FileNotFoundError, KeyError, ValueError):
        pass
    return out


def nifty_monthly(month_list, sessions) -> pd.Series:
    """^NSEI from the open of each entry session to the open of its scheduled exit session (informational)."""
    try:
        nifty = load_dataset(NIFTY)["^NSEI"].dropna(subset=["open"])
    except (FileNotFoundError, KeyError, ValueError):
        return pd.Series(dtype=float)
    idx = pd.to_datetime(nifty.index)
    nifty.index = (idx.tz_localize(None) if idx.tz is None else idx.tz_convert("Asia/Kolkata").tz_localize(None)).date
    out = {}
    for i, e, x0 in month_list:
        a, b = sessions[e], sessions[x0]
        if a in nifty.index and b in nifty.index:
            out[i] = float(nifty.loc[b, "open"] / nifty.loc[a, "open"] - 1)
    return pd.Series(out)


def distribution_days(path: Path = PANEL_DIR / "corporate_actions_applied.csv") -> set[tuple[str, date]]:
    """(security, session) of every distribution adjusted by its ex-date's close (demergers and the like)."""
    try:
        log = pd.read_csv(path)
    except FileNotFoundError:
        return set()
    hit = log[log["applied"].astype(str).eq("True") & log["kind"].isin(["distribution", "manual"])]
    return {(str(s), pd.Timestamp(d).date()) for s, d in zip(hit["sid"], hit["session"])}


def suspect_fills(trades: pd.DataFrame, secs: dict[str, Security], sessions: list[date]) -> pd.DataFrame:
    """Trades that entered or exited on a demerger-type ex-date (where the opening print can be far off, "Data audit"),
    or whose opening fill (entry, or a time exit) was more than 8% from that session's close: listed, not changed."""
    days = distribution_days()
    position = {d: k for k, d in enumerate(sessions)}
    rows = []
    for t in trades.itertuples(index=False):
        sec = secs[t.ticker]
        e, x = position[t.entry_date], int(t.exit_i)
        entry_gap = sec.adj_open[e] / sec.adj_close[e] - 1
        exit_price = sec.adj_open[e] * (1 + t.gross)
        exit_gap = exit_price / sec.adj_close[x] - 1 if sec.present[x] else np.nan
        why = []
        if (t.ticker, t.entry_date) in days or (t.ticker, t.exit_date) in days:
            why.append("demerger-type ex-date")
        if abs(entry_gap) > 0.08:
            why.append(f"entry {100 * entry_gap:+.1f}% from the close")
        if t.reason != "stop" and np.isfinite(exit_gap) and abs(exit_gap) > 0.08:  # stops fill intraday, not at the open
            why.append(f"exit {100 * exit_gap:+.1f}% from the close")
        if why:
            rows.append({"ticker": t.ticker, "entry_date": t.entry_date, "exit_date": t.exit_date, "reason": t.reason,
                         "gross": t.gross, "why": "; ".join(why)})
    return pd.DataFrame(rows, columns=["ticker", "entry_date", "exit_date", "reason", "gross", "why"])


def summary(net: pd.Series) -> dict:
    net = net.astype(float)
    if not len(net):
        return {"trades": 0}
    sd = net.std(ddof=1)
    return {"trades": int(len(net)), "win_rate": float((net > 0).mean()), "mean": float(net.mean()),
            "t": float(net.mean() / (sd / np.sqrt(len(net)))) if len(net) > 2 and sd > 0 else np.nan}


# ----------------------------------------------------------------------------------------------- run
def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_inputs(verify_pins: bool = True):
    """The sessions, the securities that are ever in a tier (laid on the session grid), and the eligibility table.
    Two passes over the panel, so only the securities a test can touch are held in memory."""
    panel = load_panel(PANEL_DIR, PANEL_SHA256 if verify_pins else None, columns=PANEL_COLUMNS)
    isins = isins_by_sid(panel, load_isins(PANEL_DIR))
    sessions = session_list(panel)
    signal_idx = month_ends(sessions)
    table = features(sessions, iter_securities(panel, sessions, isins), signal_idx)
    needed = set(table.loc[table["rank"] <= max(hi for _, hi in TIERS.values()), "sid"])
    secs = {sec.sid: sec for sec in iter_securities(panel, sessions, isins, keep=needed)}
    del panel
    return sessions, secs, table


def evaluate(stage: int, sessions, secs, table, with_informational: bool = True) -> dict:
    if stage == 1:
        month_list = months(sessions, None, STAGE1_LAST_SIGNAL)
    else:
        month_list = months(sessions, STAGE2_FIRST_SIGNAL, STAGE2_LAST_SIGNAL)
    results, raw_p = {}, {}
    for key in TIERS:
        trades, pools, plain = run_tier(key, table, secs, sessions, month_list)
        random_mean, raw_p[key], draws = baseline(trades, pools) if len(trades) else (np.nan, 1.0, np.array([]))
        results[key] = {"name": NAMES[key], "trades": trades, "pools": pools, "plain": plain, "random_mean": random_mean,
                        "span": (sessions[month_list[0][0]], sessions[month_list[-1][0]]), "months": len(month_list)}
    adjusted = holm(raw_p)
    for key, r in results.items():
        checks, stats = criteria(r["trades"], r["span"], adjusted[key], raw_p[key])
        r.update(checks=checks, stats=stats, decision=decide(checks), raw_p=raw_p[key], holm_p=adjusted[key])
        if with_informational:
            r["info"] = informational(key, r, secs, sessions, month_list, table)
    return {"stage": stage, "results": results, "month_list": month_list}


def informational(key: str, r: dict, secs, sessions, month_list, table) -> dict:
    trades = r["trades"]
    if not len(trades):
        return {}
    info = {}
    monthly = monthly_table(trades, r["plain"], r["pools"])
    info["monthly"] = monthly
    boot = stationary_bootstrap_means(monthly["excess"].to_numpy())
    info["excess_mean"] = float(monthly["excess"].mean())
    info["excess_ci"] = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))) if len(boot) else (np.nan, np.nan)
    boot_net = stationary_bootstrap_means(monthly["picks_net"].to_numpy(), seed=10)
    info["net_ci"] = (float(np.percentile(boot_net, 2.5)), float(np.percentile(boot_net, 97.5)))
    info["win_ci"] = wilson(int((trades["net"] > 0).sum()), len(trades))
    engine = (monthly["picks_sum"] * ENGINE_WEIGHT)
    full = (monthly["picks_sum"] * FULL_WEIGHT)
    tier_avg = monthly["tier_gross"]
    nifty = nifty_monthly(month_list, sessions).reindex(monthly.index)
    info["portfolios"] = {"engine size (5 x 5%)": portfolio_stats(engine), "fully invested (5 x 20%)": portfolio_stats(full),
                          "tier average, bought and held (no stop, no costs)": portfolio_stats(tier_avg),
                          "NIFTY 50 price index": portfolio_stats(nifty.dropna())}
    info["kill_switch"] = kill_switch_replay(trades, secs, sessions)
    info["costs"] = {f"{x}x": float((trades["gross"] - x * trades["cost"]).mean()) for x in (0, 1, 1.5, 2, 3)}
    # costs if a stock picked again the next month were simply kept: no exit and re-entry between the two trades
    kept = trades[~trades["stopped"]].groupby("signal_i")["ticker"].apply(set)
    picked = trades.groupby("signal_i")["ticker"].apply(set)
    order = list(picked.index)
    after = {a: picked[b] for a, b in zip(order, order[1:])}
    before = {b: kept.get(a, set()) for a, b in zip(order, order[1:])}
    held_after = [(not s) and t in after.get(i, set()) for i, t, s in zip(trades["signal_i"], trades["ticker"], trades["stopped"])]
    held_before = [t in before.get(i, set()) for i, t in zip(trades["signal_i"], trades["ticker"])]
    realistic = trades["cost"] * (1 - 0.5 * np.asarray(held_before, float) - 0.5 * np.asarray(held_after, float))
    info["retained_share"] = float(np.mean(held_after))
    info["costs"]["kept, not re-traded"] = float((trades["gross"] - realistic).mean())
    info["delisted"] = trades[trades["reason"].isin(["no further rows", "time, delayed"])][
        ["ticker", "signal_date", "entry_date", "exit_date", "reason", "gross", "net"]]
    info["suspect_fills"] = suspect_fills(trades, secs, sessions)
    haircut = trades.copy()
    gone = haircut["reason"] == "no further rows"
    haircut.loc[gone, "net"] = (1 + haircut.loc[gone, "gross"]) * (1 - DELISTING_HAIRCUT) - 1 - haircut.loc[gone, "cost"]
    info["delisting_sensitivity"] = summary(haircut["net"])
    info["regimes"] = regimes(trades)
    info["by_year"] = trades.groupby([d.year for d in trades["signal_date"]])["net"].agg(["count", "mean"])
    info["stops"] = {"stops": int(trades["stopped"].sum()), "gapped": int(trades["gapped"].sum())}
    # parameter sensitivity and PBO over the 12 variants (never used to choose)
    variants, columns = {}, []
    for label in VARIANT_LOOKBACKS:
        for picks in (5, 10):
            for stop in (STOP, None):
                name = f"{label}, top {picks}, {'stop 10%' if stop else 'no stop'}"
                vt, vpools, _ = run_tier(key, table, secs, sessions, month_list, picks, f"score_{label}", stop)
                if not len(vt):
                    continue
                vm = vt.groupby("signal_i")["net"].mean()
                pool_mean = pd.Series({i: vpools[i].mean() for i in vm.index})
                variants[name] = {"trades": len(vt), "win_rate": float((vt["net"] > 0).mean()),
                                  "mean_net": float(vt["net"].mean()), "excess": float((vm - pool_mean).mean())}
                columns.append((name, (vm - pool_mean)))
    info["variants"] = variants
    if columns:
        frame = pd.concat({name: s for name, s in columns}, axis=1).dropna()
        info["pbo"] = pbo(frame.to_numpy())
        sr = frame.mean() / frame.std(ddof=1)
        info["dsr"] = dsr(monthly["excess"].to_numpy(), TESTS_IN_PROJECT, float(sr.var(ddof=1)))
        info["dsr_inputs"] = {"variant_sr_var": float(sr.var(ddof=1))}
    return info


def evidence_for(key: str, r: dict, digest: str, code_sha: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round8-results.md (python -m trader.research.round8 --stage 2)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{r['span'][0]} to {r['span'][1]}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": ROUND_TRIP[key],
               "max_drawdown_r": s["max_drawdown_r"], "runner_sha256": code_sha},
        preregistration_sha256=digest)


def _pct(value, digits: int = 3) -> str:
    return f"{100 * value:+.{digits}f}%" if value is not None and not pd.isna(value) else "-"


def _num(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None and not pd.isna(value) else "-"


def _summary(s: dict) -> str:
    return (f"{s['trades']} trades, {100 * s['win_rate']:.1f}% winners, {_pct(s['mean'])} a trade, t {_num(s['t'])}"
            if s.get("trades") else "no trades")


def write_report(report: dict, digest: str, code_sha: str, path: Path) -> None:
    stage, results = report["stage"], report["results"]
    title = ("Research round 8, stage 1 (development and replication, decides nothing)" if stage == 1
             else "Research round 8 results: stock momentum on a survivorship-free NSE universe")
    lines = [f"# {title}", "",
             f"Run on {datetime.now(IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.round8 --stage {stage}` "
             f"(runner SHA-256 `{code_sha[:16]}...`), against [the pre-registration](round8-preregistration.md) "
             f"(SHA-256 `{digest[:16]}...`) and the frozen panel `data/round8/nse_eq` (SHA-256 `{PANEL_SHA256[:16]}...`). "
             "Every hypothesis is reported. Returns are per trade, net of costs: "
             + ", ".join(f"{k} {100 * v:.4f}% a round trip" for k, v in ROUND_TRIP.items()) + ".", ""]
    lines += ["## Summary", "",
              "| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | "
              "Random picks (same rules) | p raw / Holm | Drawdown | " + ("Decision |" if stage == 2 else "|"),
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key, r in results.items():
        s = r["stats"]
        lines.append(f"| {key}: {r['name']} | {s['trades']} | {s['wins']} / {s['losses']} | {100 * s['win_rate']:.1f}% | "
                     f"{_pct(s['mean_net'])} | {_pct(s['median_net'])} | {_pct(s['avg_win'], 2)} / {_pct(s['avg_loss'], 2)} | "
                     f"{_num(s['t'])} | {_num(s['t_clustered'])} | {_pct(r['random_mean'])} | "
                     f"{r['raw_p']:.5f} / {r['holm_p']:.5f} | {s['max_drawdown_r']:.1f}R | "
                     + (f"**{r['decision']}** |" if stage == 2 else "(stage 1) |"))
    lines += ["", "## The criteria" + (" (stage 1: reported, not applied)" if stage == 1 else ""), "",
              "| # | Criterion | " + " | ".join(results) + " |", "|---|---|" + "---|" * len(results)]
    for i, check in enumerate(next(iter(results.values()))["checks"]):
        cells = [f"{r['checks'][i].value} ({'pass' if r['checks'][i].passed else '**fail**'})" for r in results.values()]
        lines.append(f"| {check.number} | {check.criterion} | " + " | ".join(cells) + " |")
    for key, r in results.items():
        s, info = r["stats"], r.get("info", {})
        traded = r["trades"]["signal_date"] if len(r["trades"]) else pd.Series(dtype=object)
        lines += ["", f"## {key}: {r['name']}", "",
                  f"Signals {traded.min() if len(traded) else '-'} to {traded.max() if len(traded) else '-'} "
                  f"({traded.nunique()} months with trades). Mean net {_pct(s['mean_net'])} a trade "
                  f"against {_pct(r['random_mean'])} for 5 random stocks from the same tier with the same rules "
                  f"(p = {r['raw_p']:.5f}, Holm {r['holm_p']:.5f})."]
        if stage == 2:
            lines += ["", f"**Decision: {r['decision']}.**"]
        if not info:
            continue
        lo, hi = info["win_ci"]
        lines += ["", "Informational (not part of any decision):", "",
                  f"- Win rate 95% interval (Wilson): {100 * lo:.1f}% to {100 * hi:.1f}%. Mean net per month of picks, 95% "
                  f"interval (month-block bootstrap): {_pct(info['net_ci'][0])} to {_pct(info['net_ci'][1])}.",
                  f"- Monthly excess of the picks over the random-pick expectation: {_pct(info['excess_mean'])} "
                  f"(95% interval {_pct(info['excess_ci'][0])} to {_pct(info['excess_ci'][1])}). The dividends missing from "
                  "price returns lower the baseline by at most about 0.08% a month.",
                  f"- Stops: {info['stops']['stops']}, of which {info['stops']['gapped']} filled at a gap. Picks kept from "
                  f"one month to the next: {100 * info['retained_share']:.0f}% of trades.",
                  "- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: " + " / ".join(_pct(info["costs"][k]) for k in ("0x", "1x", "1.5x", "2x", "3x"))
                  + f"; with a stock picked again the next month kept instead of re-traded: {_pct(info['costs']['kept, not re-traded'])}.",
                  f"- With a {100 * DELISTING_HAIRCUT:.0f}% haircut on trades that ended at a last close: "
                  f"{_summary(info['delisting_sensitivity'])}."]
        ks = info.get("kill_switch", {})
        if ks:
            lines.append(f"- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs "
                         f"{ks['final_equity']:,.0f}, deepest drawdown {_pct(ks['max_drawdown'], 1)}; the 10% kill switch "
                         + (f"would have engaged on {ks['kill_switch_session']}." if ks["kill_switch_session"] else "never engaged."))
        if info.get("dsr"):
            d = info["dsr"]
            lines.append(f"- Deflated Sharpe ratio of the monthly excess: {d['dsr']:.3f} (Sharpe {d['sr_annual']:.2f} a year; "
                         f"probability it beats zero {d['psr_vs_zero']:.3f}; {d['trials']} trials, variant Sharpe variance "
                         f"{info['dsr_inputs']['variant_sr_var']:.4f}).")
        if info.get("pbo"):
            lines.append(f"- Probability of backtest overfitting across the 12 variants: {info['pbo']['pbo']:.2f} "
                         f"({info['pbo']['combinations']} combinations).")
        lines += ["", "| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |", "|---|---:|---:|---:|---:|---:|"]
        for label, p in info["portfolios"].items():
            if p:
                lines.append(f"| {label} | {_pct(p['cagr'], 1)} | {_pct(p['vol'], 1)} | {_num(p['sharpe'])} | "
                             f"{_num(p['sortino'])} | {_pct(p['max_drawdown'], 1)} |")
        lines += ["", "| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |",
                  "|---|---:|---:|---:|---:|"]
        for name, v in info["variants"].items():
            lines.append(f"| {name} | {v['trades']} | {100 * v['win_rate']:.1f}% | {_pct(v['mean_net'])} | {_pct(v['excess'])} |")
        for regime, parts in info.get("regimes", {}).items():
            lines.append(f"- {regime}: " + "; ".join(f"{k}: {_summary(v)}" for k, v in parts.items()) + ".")
        lines += ["", "| Year | Trades | Net per trade |", "|---|---:|---:|"]
        lines += [f"| {year} | {int(row['count'])} | {_pct(row['mean'])} |" for year, row in info["by_year"].iterrows()]
        odd = info.get("suspect_fills", pd.DataFrame())
        lines += ["", f"Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that session's close "
                  f"(listed, not changed): {len(odd)}."]
        if len(odd):
            lines += ["", "| Stock | Entry | Exit | How | Gross | Why |", "|---|---|---|---|---:|---|"]
            lines += [f"| {o.ticker} | {o.entry_date} | {o.exit_date} | {o.reason} | {_pct(o.gross, 1)} | {o.why} |"
                      for o in odd.itertuples(index=False)]
        gone = info["delisted"]
        if len(gone):
            lines += ["", "Trades that ended at a suspension or a last close:", "",
                      "| Stock | Signal | Entry | Exit | How | Gross |", "|---|---|---|---|---|---:|"]
            lines += [f"| {g.ticker} | {g.signal_date} | {g.entry_date} | {g.exit_date} | {g.reason} | {_pct(g.gross, 1)} |"
                      for g in gone.itertuples(index=False)]
    lines += ["", "Patterns in the informational sections are hypotheses for future data, not findings."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Round 8: stage 1 (development), then stage 2 (the decision, once).")
    parser.add_argument("--stage", type=int, choices=[1, 2], required=True)
    args = parser.parse_args(argv)
    make_console_utf8()
    digest = check_preregistration()
    code_sha = file_sha(Path(__file__))
    if args.stage == 2:
        if not STAGE1_RESULTS.exists():
            raise SystemExit("stage 1 has not run: run --stage 1 first")
        if RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} already exists: stage 2 runs once")
    sessions, secs, table = load_inputs()
    report = evaluate(args.stage, sessions, secs, table)
    path = STAGE1_RESULTS if args.stage == 1 else RESULTS
    write_report(report, digest, code_sha, path)
    for key, r in report["results"].items():
        s = r["stats"]
        print(f"{key}: {s['trades']} trades, win {100 * s['win_rate']:.1f}%, net {_pct(s['mean_net'])} a trade, "
              f"random {_pct(r['random_mean'])}, p {r['raw_p']:.5f} (Holm {r['holm_p']:.5f}), drawdown "
              f"{s['max_drawdown_r']:.1f}R" + (f" -> {r['decision']}" if args.stage == 2 else ""))
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
        if args.stage == 2:
            save_evidence(evidence_for(key, r, digest, code_sha))
    print(f"Report written to {path}")


if __name__ == "__main__":
    main()
