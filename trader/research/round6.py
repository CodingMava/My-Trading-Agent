"""Research round 6: six strategies from Ernest Chan's Algorithmic Trading (2013), judged against
docs/research/round6-preregistration.md on the years after the book appeared.

    python -m trader.research.round6        # writes docs/research/round6-results.md and the evidence files

C1/C2 buy stocks that gapped down at the open but are still above their 20-day average, and sell at the
close (NIFTY 50; S&P 100). C3/C4 trade the index intraday in the direction of an opening gap (NIFTY; SPY).
C5/C6 hold the index for a month only after a positive year, else cash (NIFTY; SPY). Nothing is fitted:
every rule is judged on 1 Jul 2013 to 8 Oct 2026, data its rules were never designed on.

The round was first run outside the project on 12 Oct 2026 (the book's text wasn't available, so the rules
are as described by secondary sources), then recorded here unchanged so the project's count of tested
hypotheses stays complete. The pre-registration's SHA-256 was recorded before any of these rules ran.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.features.indicators import atr
from trader.gate import Check, Evidence, ResearchThresholds, decide, research_checks, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round2, round4, round5
from trader.research.costs import US_COMMISSION_FREE, ZERODHA_ETF_DELIVERY, ZERODHA_INTRADAY
from trader.research.datasets import DATA_DIR, load_dataset, text_sha256
from trader.research.phase3 import base_symbol, clean_daily, holm, trading_days
from trader.research.round3 import halves_check
from trader.research.simulator import STOP, TIME
from trader.research.validation import (clustered_t, random_entry_test, regime_table, same_day_random_test,
                                        trend_regime, volatility_regime)

PREREGISTRATION = ROOT / "docs" / "research" / "round6-preregistration.md"
PREREGISTRATION_SHA256 = "31537d73fbb83c10319f1e8da78c7143a918d97abc991857a9718333279e239b"  # 2026-10-12 23:35 IST
RESULTS = ROOT / "docs" / "research" / "round6-results.md"
AUX = DATA_DIR / "round6" / "aux_daily"  # ^VIX, ^INDIAVIX and ^IRX (T-bill yield), frozen on 2026-10-12
END = date(2026, 10, 8)
START = date(2013, 7, 1)  # the decision span: after the book's publication
SPLIT = START + (END - START) / 2
PREREGISTERED = ResearchThresholds(min_trades=50, min_win_rate=0.50, min_profit_factor=1.3, min_t_stat=2.0,
                                   max_p_value=0.05, cost_stress=1.5, max_loss_to_win=1.5, worst_trade_r=-3.0,
                                   min_positive_years=0.70, min_trades_per_year=10, min_breadth=0.60,
                                   min_trades_per_stock=5)
CROSS_ROUND_ALPHA = 0.05 / 20  # criterion 12: 20 hypotheses have now been tested on overlapping data
COST = {
    "C1": ZERODHA_INTRADAY.with_slippage(0.0005).round_trip(100_000),
    "C2": US_COMMISSION_FREE.with_slippage(0.0005).round_trip(10_000),
    "C3": ZERODHA_INTRADAY.round_trip(200_000),
    "C4": US_COMMISSION_FREE.round_trip(10_000),
    "C5": ZERODHA_ETF_DELIVERY.with_slippage(0.0005).round_trip(100_000),
    "C6": US_COMMISSION_FREE.round_trip(10_000),
}
NAMES = {
    "C1": "Buy-on-gap, NIFTY 50 stocks (intraday, MIS)",
    "C2": "Buy-on-gap, 82 S&P 100 stocks (intraday)",
    "C3": "Opening-gap momentum, NIFTY 50 index (intraday, long/short)",
    "C4": "Opening-gap momentum, SPY (intraday, long/short)",
    "C5": "Time-series momentum, NIFTY 50 (index or cash, monthly)",
    "C6": "Time-series momentum, SPY (SPY or T-bills, monthly)",
}
INDIA_CASH = 0.06  # C5's cash yield a year (an assumption; 0% and 4% are reported too)


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


# ----------------------------------------------------------------------------------------------- data
def load_all() -> dict:
    raw = {s: f[np.asarray(f.index.date) <= END] for s, f in load_dataset(DATA_DIR / "phase3" / "nse_nifty50_daily").items()}
    nifty_stocks, _ = clean_daily(raw)  # Phase 3's three corporate-action splits
    us_stocks, _ = round2.load_clean("us_stocks_daily", end=END)
    nifty, _ = round2.load_clean("nse_nifty_daily", data=DATA_DIR / "round4", end=END, classify_move=round4.classify, breaks={})
    spy, _ = round2.load_clean("us_spy_daily", data=DATA_DIR / "round4", end=END, classify_move=round4.classify, breaks={})
    aux = {k: v[np.asarray(v.index.date) <= END] for k, v in load_dataset(AUX).items()}
    return {"nifty_stocks": nifty_stocks, "us_stocks": us_stocks, "nifty": nifty["^NSEI"], "spy": spy["SPY"], "aux": aux}


# ------------------------------------------------------------------------------------- intraday rules
def features(b: pd.DataFrame) -> pd.DataFrame:
    """sigma (90 daily returns), MA20 and ATR(14) as a fraction of the close, all known before t's open."""
    c = b["close"]
    return pd.DataFrame({
        "sigma": c.pct_change().rolling(90, min_periods=90).std(ddof=1).shift(1),
        "ma20": c.rolling(20, min_periods=20).mean().shift(1),
        "atr": (atr(b["high"], b["low"], c, 14) / c).shift(1),
        "prev_low": b["low"].shift(1), "prev_high": b["high"].shift(1),
    }, index=b.index)


def intraday_outcome(b: pd.DataFrame, stop_frac: pd.Series, side: str, use_stop: bool = True):
    """(gross, reason) of entering at the open and leaving at the close, with a stop `stop_frac` away."""
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    s = stop_frac.to_numpy(float)
    if side == "long":
        px = o * (1 - s)
        hit = (l <= px) & use_stop
        gross = np.where(hit, px, c) / o - 1
    else:
        px = o * (1 + s)
        hit = (h >= px) & use_stop
        gross = 1 - np.where(hit, px, c) / o
    return gross, np.where(hit, STOP, TIME)


def trade_frame(ticker, stamps, gross, reason, risk, side, rule) -> pd.DataFrame:
    stamps = pd.DatetimeIndex(stamps)
    return pd.DataFrame({
        "ticker": ticker, "rule": rule, "side": side, "signal_time": stamps, "exit_time": stamps,
        "signal_date": np.asarray(stamps.date), "exit_date": np.asarray(stamps.date), "tod": "open",
        "gross": np.asarray(gross, float), "reason": np.asarray(reason), "hold_bars": 0, "risk": np.asarray(risk, float),
    })


def buy_on_gap(pieces: dict, rule: str, k: float = 1.0, use_stop: bool = True, top_n: int = 10):
    """All trades over all data (no span filter), plus each stock's daily outcome pool (tradeable days)."""
    rows, pools = [], {}
    for name, b in pieces.items():
        if len(b) < 100:
            continue
        f = features(b)
        gap = b["open"] / f["prev_low"] - 1
        ready = f[["sigma", "ma20", "atr"]].notna().all(axis=1) & (b["open"] > 0) & f["prev_low"].notna()
        eligible = ready & (gap < -k * f["sigma"]) & (b["open"] > f["ma20"])
        gross, reason = intraday_outcome(b, f["atr"].fillna(0.0), "long", use_stop)
        symbol = base_symbol(name)
        rows.append(pd.DataFrame({"ticker": symbol, "stamp": b.index, "gap": gap.to_numpy(), "eligible": eligible.to_numpy(),
                                  "gross": gross, "reason": reason, "risk": f["atr"].to_numpy()}))
        dates = np.asarray(b.index.date)
        pools.setdefault(symbol, []).append(pd.Series(gross[ready.to_numpy()], index=dates[ready.to_numpy()]))
    panel = pd.concat(rows, ignore_index=True)
    picked = panel[panel["eligible"]].sort_values(["stamp", "gap", "ticker"]).groupby("stamp").head(top_n)
    trades = trade_frame(picked["ticker"].to_numpy(), picked["stamp"].to_numpy(), picked["gross"], picked["reason"],
                         picked["risk"], "long", rule)
    trades = trades.sort_values(["signal_time", "ticker"]).reset_index(drop=True)
    return trades, {s: pd.concat(p).sort_index() for s, p in pools.items()}


def opening_gap(b: pd.DataFrame, ticker: str, rule: str, k: float = 0.1, use_stop: bool = True):
    """Long above yesterday's high by k sigma, short below yesterday's low; both out at the close."""
    f = features(b)
    ready = f[["sigma", "atr", "prev_low", "prev_high"]].notna().all(axis=1) & (b["open"] > 0)
    long = ready & (b["open"] > f["prev_high"] * (1 + k * f["sigma"]))
    short = ready & (b["open"] < f["prev_low"] * (1 - k * f["sigma"]))
    frames, pools = [], {}
    dates = np.asarray(b.index.date)
    for side, mask in (("long", long), ("short", short)):
        gross, reason = intraday_outcome(b, f["atr"].fillna(0.0), side, use_stop)
        m = mask.to_numpy()
        frames.append(trade_frame(ticker, b.index[m], gross[m], reason[m], f["atr"].to_numpy()[m], side, rule))
        pools[side] = pd.Series(gross[ready.to_numpy()], index=dates[ready.to_numpy()])
    trades = pd.concat(frames, ignore_index=True).sort_values("signal_time").reset_index(drop=True)
    return trades, pools


# ---------------------------------------------------------------------------------- monthly momentum
def month_end_positions(index: pd.DatetimeIndex) -> np.ndarray:
    months = index.year * 12 + index.month
    return np.flatnonzero(np.r_[months[1:] != months[:-1], False])  # the last bar's month is incomplete: skipped


def tsmom(b: pd.DataFrame, cash_rate: pd.Series, cost: float, lookback: int = 252, ticker: str = "", rule: str = ""):
    """One row per holding month: signal, gross index return (open to open), cash return, switching costs.
    `cash_rate` maps each bar to an annual simple rate known at that bar's close."""
    o, c = b["open"].to_numpy(float), b["close"].to_numpy(float)
    ends = month_end_positions(b.index)
    rows = []
    for this_end, next_end in zip(ends[:-1], ends[1:]):
        if this_end < lookback:
            continue
        entry, exit_ = this_end + 1, next_end + 1
        if exit_ >= len(b):
            continue
        days = (b.index[exit_] - b.index[entry]).days
        rows.append({"signal_time": b.index[this_end], "entry_time": b.index[entry], "exit_time": b.index[exit_],
                     "invested": bool(c[this_end] / c[this_end - lookback] - 1 > 0),
                     "gross": o[exit_] / o[entry] - 1,
                     "cash": float(cash_rate.iloc[this_end]) * days / 365.0, "hold_bars": exit_ - this_end})
    m = pd.DataFrame(rows)
    inv = m["invested"].to_numpy()
    prev_inv = np.r_[False, inv[:-1]]
    next_inv = np.r_[inv[1:], False]
    m["switch_cost"] = np.where(inv, (~prev_inv) * cost / 2 + (~next_inv) * cost / 2, 0.0)
    m["net"] = np.where(inv, m["gross"] - m["switch_cost"], m["cash"])
    m["signal_date"] = [t.date() for t in m["signal_time"]]
    m["ticker"], m["rule"] = ticker, rule
    return m


def tsmom_trades(m: pd.DataFrame, cost_mult: float = 1.0) -> pd.DataFrame:
    """The invested months as trades, net of their switching costs (so the gate's cost is 0)."""
    held = m[m["invested"]]
    stamps, exits = pd.DatetimeIndex(held["signal_time"]), pd.DatetimeIndex(held["exit_time"])
    return pd.DataFrame({
        "ticker": held["ticker"].to_numpy(), "rule": held["rule"].to_numpy(), "side": "long", "signal_time": stamps,
        "exit_time": exits, "signal_date": np.asarray(stamps.date), "exit_date": np.asarray(exits.date), "tod": "close",
        "gross": (held["gross"] - cost_mult * held["switch_cost"]).to_numpy(float), "reason": TIME,
        "hold_bars": held["hold_bars"].to_numpy(int), "risk": np.nan,
    }).reset_index(drop=True)


def months_random_test(m: pd.DataFrame, n_iter: int = 2000, seed: int = 7) -> tuple[float, float]:
    """(mean gross of random months, P(random mean >= the invested months' mean))."""
    rng = np.random.default_rng(seed)
    pool = m["gross"].to_numpy(float)
    held = m.loc[m["invested"], "gross"].to_numpy(float)
    draws = pool[rng.integers(0, len(pool), size=(n_iter, len(held)))].mean(axis=1)
    return float(draws.mean()), float((draws >= held.mean()).mean())


# ------------------------------------------------------------------------------------------- helpers
def span(trades: pd.DataFrame, start=START, end=END) -> pd.DataFrame:
    return trades[(trades["signal_date"] >= start) & (trades["signal_date"] <= end)].reset_index(drop=True)


def pool_span(pools: dict, start=START, end=END) -> dict:
    out = {}
    for key, s in pools.items():
        idx = np.asarray(s.index)
        out[key] = s[(idx >= start) & (idx <= end)]
    return out


def series_stats(returns: pd.Series, periods: int) -> dict:
    r = returns.astype(float).fillna(0.0)
    if len(r) == 0:
        return {}
    growth = (1 + r).cumprod()
    years = len(r) / periods
    downside = np.sqrt((np.minimum(r, 0) ** 2).mean())
    return {"cagr_pct": 100 * (growth.iloc[-1] ** (1 / years) - 1), "vol_pct": 100 * r.std() * np.sqrt(periods),
            "sharpe": r.mean() / r.std() * np.sqrt(periods) if r.std() > 0 else np.nan,
            "sortino": r.mean() / downside * np.sqrt(periods) if downside > 0 else np.nan,
            "max_dd_pct": 100 * float((growth / growth.cummax().clip(lower=1.0) - 1).min()),
            "total_pct": 100 * (growth.iloc[-1] - 1), "years": years}


def daily_portfolio(trades: pd.DataFrame, cost: float, days: list, slots: int) -> pd.Series:
    net = (trades["gross"] - cost).groupby(trades["signal_date"]).sum() / slots
    return net.reindex(days, fill_value=0.0)


def trade_stats(net: pd.Series) -> dict:
    net = net.astype(float)
    if len(net) == 0:
        return {"trades": 0}
    wins, losses = net[net > 0], net[net <= 0]
    sd = net.std(ddof=1)
    return {"trades": int(len(net)), "win_pct": 100 * (net > 0).mean(), "exp_net_pct": 100 * net.mean(),
            "avg_win_pct": 100 * wins.mean() if len(wins) else np.nan,
            "avg_loss_pct": 100 * losses.mean() if len(losses) else np.nan,
            "profit_factor": wins.sum() / -losses.sum() if losses.sum() < 0 else np.inf,
            "t": net.mean() / (sd / np.sqrt(len(net))) if len(net) > 2 and sd > 0 else np.nan}


def finish_checks(checks, trades: pd.DataFrame, cost: float, p_raw: float, monthly: bool, stress_override=None):
    """Criteria 8 (halves), 9 (thirds for monthly), 11 and 12 on top of the gate's checks."""
    out = []
    for c in checks:
        if c.number == 1:
            c = replace(c, criterion=c.criterion.replace(" holdout", ""))
        if c.number == 3 and stress_override is not None:
            c = stress_override
        if c.number == 8:
            c = halves_check(trades, cost, SPLIT)
        if c.number == 9 and monthly:
            c = round5.thirds_check(trades, cost, START, END)
        out.append(c)
    t_week = clustered_t(trades["gross"] - cost, [round2.signal_week(d) for d in trades["signal_date"]])
    out.append(Check(11, "Cluster-robust t-statistic (signal weeks as clusters) at least 2.0", f"{t_week:.2f}",
                     bool(t_week >= 2.0)))
    out.append(Check(12, f"Raw random-baseline p below 0.05/20 = {CROSS_ROUND_ALPHA:.4f} (20 hypotheses tested)",
                     f"{p_raw:.4f}", bool(p_raw < CROSS_ROUND_ALPHA)))
    return out, t_week


def walk_forward(trades_by_param: dict, default, cost: float, first_test_year: int, last_year: int = 2026) -> dict:
    """Rolling 3-year train / 1-year test parameter choice by train net expectancy (>= 20 trades)."""
    chosen_rows, fixed_rows, picks = [], [], {}
    for year in range(first_test_year, last_year + 1):
        best, best_val = default, -np.inf
        for param, tr in trades_by_param.items():
            years = np.array([d.year for d in tr["signal_date"]])
            train = tr[(years >= year - 3) & (years <= year - 1)]
            if len(train) >= 20:
                val = (train["gross"] - cost).mean()
                if val > best_val:
                    best, best_val = param, val
        picks[year] = best
        for param, bucket in ((best, chosen_rows), (default, fixed_rows)):
            tr = trades_by_param[param]
            years = np.array([d.year for d in tr["signal_date"]])
            bucket.append(tr[years == year])
    wf = pd.concat(chosen_rows, ignore_index=True)
    fx = pd.concat(fixed_rows, ignore_index=True)
    return {"walk_forward": trade_stats(wf["gross"] - cost), "fixed": trade_stats(fx["gross"] - cost), "picks": picks}


def walk_forward_monthly(months_by_param: dict, default, first_test_year: int, last_year: int = 2026) -> dict:
    chosen, fixed, picks = [], [], {}
    for year in range(first_test_year, last_year + 1):
        best, best_val = default, -np.inf
        for param, m in months_by_param.items():
            years = np.array([d.year for d in m["signal_date"]])
            train = m.loc[(years >= year - 3) & (years <= year - 1), "net"]
            if len(train) >= 30 and train.std() > 0:
                val = train.mean() / train.std()
                if val > best_val:
                    best, best_val = param, val
        picks[year] = best
        for param, bucket in ((best, chosen), (default, fixed)):
            m = months_by_param[param]
            years = np.array([d.year for d in m["signal_date"]])
            bucket.append(m.loc[years == year, "net"])
    return {"walk_forward": series_stats(pd.concat(chosen, ignore_index=True), 12),
            "fixed": series_stats(pd.concat(fixed, ignore_index=True), 12), "picks": picks}


def regimes_for(index_close: pd.Series, vol_close: pd.Series) -> dict:
    return {"uptrend": trend_regime(index_close, 50), "high vol": volatility_regime(vol_close, 250, 60)}


def by_year(trades: pd.DataFrame, cost: float) -> dict:
    net = trades["gross"] - cost
    years = pd.Series([d.year for d in trades["signal_date"]], index=trades.index)
    return {int(y): {"trades": int(len(g)), "win_pct": 100 * (g > 0).mean(), "exp_net_pct": 100 * g.mean()}
            for y, g in net.groupby(years)}


# ----------------------------------------------------------------------------------------------- run
def run(write: bool = True) -> dict:
    make_console_utf8()
    digest = check_preregistration()
    d = load_all()
    aux = d["aux"]
    irx = aux["^IRX"]["close"] / 100.0
    spy_cash = irx.reindex(d["spy"].index, method="ffill").ffill().fillna(0.0)
    nifty_cash = pd.Series(INDIA_CASH, index=d["nifty"].index)
    regimes = {"India": regimes_for(d["nifty"]["close"], aux["^INDIAVIX"]["close"]),
               "US": regimes_for(d["spy"]["close"], aux["^VIX"]["close"])}

    runs, raw_p, rand_mean = {}, {}, {}
    for key, pieces in (("C1", d["nifty_stocks"]), ("C2", d["us_stocks"])):  # buy-on-gap
        all_trades, pools = buy_on_gap(pieces, key)
        trades = span(all_trades)
        rand_mean[key], raw_p[key] = same_day_random_test(pool_span(pools), trades)
        runs[key] = {"all": all_trades, "trades": trades, "pieces": pieces}
    for key, bars, sym in (("C3", d["nifty"], "^NSEI"), ("C4", d["spy"], "SPY")):  # opening gap
        all_trades, pools = opening_gap(bars, sym, key)
        trades = span(all_trades)
        pools = pool_span(pools)
        rand_mean[key], raw_p[key] = random_entry_test({k: v.to_numpy() for k, v in pools.items()}, trades["side"],
                                                       trades["gross"])
        runs[key] = {"all": all_trades, "trades": trades, "pieces": {sym: bars}}
    for key, bars, sym, cash in (("C5", d["nifty"], "^NSEI", nifty_cash), ("C6", d["spy"], "SPY", spy_cash)):  # momentum
        months = tsmom(bars, cash, COST[key], ticker=sym, rule=key)
        in_span = months[(months["signal_date"] >= START) & (months["signal_date"] <= END)].reset_index(drop=True)
        rand_mean[key], raw_p[key] = months_random_test(in_span)
        runs[key] = {"months_all": months, "months": in_span, "trades": tsmom_trades(in_span), "pieces": {sym: bars}}
    adjusted = holm(raw_p)

    results = {}
    for key in NAMES:
        r = runs[key]
        trades = r["trades"]
        monthly = key in ("C5", "C6")
        cost = 0.0 if monthly else COST[key]  # the invested months already carry their switching costs
        days = trading_days(r["pieces"], START, END)
        stress_override = None
        if monthly:
            held = r["months"][r["months"]["invested"]]
            base = 100 * (held["gross"] - held["switch_cost"]).mean()
            stress = 100 * (held["gross"] - 1.5 * held["switch_cost"]).mean()
            stress_override = Check(3, "Expectancy above 0 at base and 1.5x costs", f"{base:+.3f}% / {stress:+.3f}%",
                                    bool(base > 0 and stress > 0))
        checks, details = research_checks(trades, cost, START, {"design": [], "holdout": days, "all": days},
                                          adjusted[key], key in ("C1", "C2"), PREREGISTERED)
        checks, t_week = finish_checks(checks, trades, cost, raw_p[key], monthly, stress_override)
        res = {"name": NAMES[key], "trades": trades, "cost": cost, "cost_round_trip_pct": 100 * COST[key],
               "decision": decide(checks), "checks": checks, "stats": details["stats"]["holdout"],
               "worst_r": details["worst_r"], "raw_p": raw_p[key], "holm_p": adjusted[key],
               "random_mean_gross_pct": 100 * rand_mean[key],
               "strategy_mean_gross_pct": 100 * (r["months"].loc[r["months"]["invested"], "gross"].mean() if monthly
                                                 else trades["gross"].mean()),
               "t_week": t_week, "by_year": by_year(trades, cost)}
        # ---- informational: none of this affects the decision
        if monthly:
            m = r["months"]
            res["portfolio"] = series_stats(m["net"], 12)
            res["buy_and_hold"] = series_stats(m["gross"], 12)
            res["share_invested_pct"] = 100 * m["invested"].mean()
            res["cost_sensitivity"] = {f"{x}x": 100 * (m.loc[m["invested"], "gross"] - x * m.loc[m["invested"], "switch_cost"]).mean()
                                       for x in (0, 1, 1.5, 2)}
            res["switches"] = int((m["invested"] != m["invested"].shift(fill_value=False)).sum())
            pre = r["months_all"][r["months_all"]["signal_date"] < START]
            res["in_sample_context"] = {"span": f"{pre['signal_date'].iloc[0]} to {pre['signal_date'].iloc[-1]}",
                                        "portfolio": series_stats(pre["net"], 12),
                                        "buy_and_hold": series_stats(pre["gross"], 12)}
            worst = m[m["gross"] <= m["gross"].quantile(0.10)]  # the index's worst tenth of months
            res["worst_decile_months"] = {"months": int(len(worst)), "share_invested_pct": 100 * worst["invested"].mean()}
            bars = r["pieces"][list(r["pieces"])[0]]
            cash = nifty_cash if key == "C5" else spy_cash
            grid = {lb: tsmom(bars, cash, COST[key], lookback=lb, ticker="", rule=key) for lb in (63, 126, 252)}
            first = min(g["signal_date"].iloc[0].year for g in grid.values()) + 3
            res["walk_forward"] = walk_forward_monthly(grid, 252, first + 1)
            if key == "C5":
                res["cash_sensitivity"] = {}
                for rate in (0.0, 0.04):
                    alt = tsmom(bars, pd.Series(rate, index=bars.index), COST[key], ticker="", rule=key)
                    alt = alt[(alt["signal_date"] >= START) & (alt["signal_date"] <= END)]
                    res["cash_sensitivity"][f"{rate:.0%}"] = series_stats(alt["net"], 12)
            res["regimes"] = regime_table(trades, 0.0, regimes["India" if key == "C5" else "US"])
        else:
            slots = 10 if key in ("C1", "C2") else 1
            res["portfolio"] = series_stats(daily_portfolio(trades, COST[key], days, slots), 252)
            res["slots"] = slots
            idx = (d["nifty"] if key in ("C1", "C3") else d["spy"])["close"]
            idx = idx[(np.asarray(idx.index.date) >= START) & (np.asarray(idx.index.date) <= END)]
            res["buy_and_hold"] = series_stats(idx.pct_change().dropna(), 252)
            res["cost_sensitivity"] = {f"{x}x": 100 * (trades["gross"] - x * COST[key]).mean() for x in (0, 1, 1.5, 2)}
            res["regimes"] = regime_table(trades, COST[key], regimes["India" if key in ("C1", "C3") else "US"])
            res["stop_exit_pct"] = 100 * (trades["reason"] == STOP).mean() if len(trades) else np.nan
            if key in ("C3", "C4"):
                res["by_side"] = {s: trade_stats(g["gross"] - COST[key]) for s, g in trades.groupby("side")}
                pre = r["all"][r["all"]["signal_date"] < START]
                res["in_sample_context"] = {"span": f"{pre['signal_date'].min()} to {pre['signal_date'].max()}",
                                            "stats": trade_stats(pre["gross"] - COST[key])}
                bars, sym = r["pieces"][list(r["pieces"])[0]], list(r["pieces"])[0]
                res["no_stop_variant"] = trade_stats(span(opening_gap(bars, sym, key, use_stop=False)[0])["gross"] - COST[key])
                grid = {k: opening_gap(bars, sym, key, k=k)[0] for k in (0.0, 0.1, 0.25, 0.5)}
                res["walk_forward"] = walk_forward(grid, 0.1, COST[key], r["all"]["signal_date"].min().year + 4)
            else:
                res["breadth"] = details["stats"]["holdout"].get("breadth")
                res["no_stop_variant"] = trade_stats(span(buy_on_gap(r["pieces"], key, use_stop=False)[0])["gross"] - COST[key])
                grid = {k: buy_on_gap(r["pieces"], key, k=k)[0] for k in (0.5, 1.0, 1.5)}
                res["walk_forward"] = walk_forward(grid, 1.0, COST[key], 2018)
                res["max_positions_in_a_day"] = int(trades.groupby("signal_date").size().max()) if len(trades) else 0
        results[key] = res
    if write:
        write_report(digest, results)
        for key, result in results.items():
            save_evidence(evidence_for(key, result, digest))
    return results


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    net, s = r["trades"]["gross"] - r["cost"], r["stats"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round6-results.md (python -m trader.research.round6)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{START} to {END}", "holdout_trades": int(len(net)),
               "holdout_win_rate": float((net > 0).mean()), "holdout_mean_net": float(net.mean()),
               "holdout_sd_net": float(net.std(ddof=1)), "holdout_profit_factor": float(s["profit_factor"]),
               "holdout_t": float(s["t_stat"]), "holdout_t_clustered": r["t_week"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": COST[key]},
        preregistration_sha256=digest)


# ---------------------------------------------------------------------------------------------- report
def _finite(value) -> bool:
    return value is not None and np.isfinite(value)


def _pct(value, digits: int = 3) -> str:
    return f"{value:+.{digits}f}%" if _finite(value) else "-"


def _num(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if _finite(value) else "-"


def _growth(p: dict) -> str:
    return (f"CAGR {_pct(p.get('cagr_pct'), 1)}, Sharpe {_num(p.get('sharpe'))}, max drawdown {_pct(p.get('max_dd_pct'), 1)}"
            if p else "-")


def _trades(s: dict) -> str:
    return (f"{s['trades']} trades, {_pct(s.get('exp_net_pct'))} a trade, t {_num(s.get('t'))}" if s.get("trades")
            else "no trades")


def _regimes(row: dict) -> str:
    return "; ".join(f"{label} {_pct(row.get(f'{label} exp%'))} (n={row.get(f'{label} n', 0)})"
                     for name in ("uptrend", "high vol") for label in (name, f"not {name}"))


def write_report(digest: str, results: dict) -> None:
    lines = [
        "# Research round 6 results: Ernest Chan's strategies",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.round6`, judged against "
        f"[the pre-registration](round6-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "pinned on 12 Oct 2026 at 23:35 IST, before any of these rules ran on this data). Returns are per trade, "
        f"net of costs, over the decision span {START} to {END}: after the book appeared in 2013, so data its "
        "rules were never designed on.",
        "",
        "The round was first run outside the project on 12 Oct 2026. The book's text wasn't available, so the "
        "rules are as described by secondary sources (see the pre-registration); this is a test of those rules, "
        "not a verdict on the book. It was recorded here on 13 Oct, with the same runner and data, so the "
        "project's count of tested hypotheses stays complete: 20 (H1-H14, C1-C6), and none has passed.",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (raw / Holm) | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        s = r["stats"]
        lines.append(f"| {key}: {r['name']} | {s.get('trades', 0)} | {s.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(s.get('exp_net_pct'))} | {_num(s.get('profit_factor'))} | {_num(s.get('t_stat'))} | "
                     f"{_num(r['t_week'])} | {r['raw_p']:.3f} / {r['holm_p']:.3f} | **{r['decision']}** |")
    lines += ["", "## The criteria", "",
              "| # | Criterion | " + " | ".join(results) + " |", "|---|---|" + "---|" * len(results)]
    numbers = sorted({c.number for r in results.values() for c in r["checks"]})
    for number in numbers:
        row = {key: next((c for c in r["checks"] if c.number == number), None) for key, r in results.items()}
        criterion = next(c.criterion for c in row.values() if c is not None)
        cells = [f"{c.value} ({'pass' if c.passed else '**fail**'})" if c is not None else "n/a" for c in row.values()]
        lines.append(f"| {number} | {criterion} | " + " | ".join(cells) + " |")
    lines += ["", "## Data and costs", "",
              "- Daily bars from Yahoo (adjusted), frozen with checksums in `data/` (git-ignored): the NIFTY 50 "
              "stocks of Phase 3 (from Sep 2014; today's list, so stocks that left the index are missing, which "
              "flatters buy-the-dip rules), round 2's 82 S&P 100 stocks, ^NSEI (from 2007) and SPY (from 1993) of "
              "round 4, and ^VIX, ^INDIAVIX and ^IRX for regimes and cash (`data/round6/aux_daily`). Cut at 8 Oct 2026.",
              "- Intraday trades fill at the open and the close of daily bars. The gap rules also read the open as "
              "their signal, which real orders can't quite match: this flatters C1-C4.",
              "- Round-trip costs: " + ", ".join(f"{key} {r['cost_round_trip_pct']:.3f}%" for key, r in results.items())
              + " (C5/C6 only on switches); stress test at 1.5x."]
    for key, r in results.items():
        lines += ["", f"## {key}: {r['name']}", "",
                  f"Random baseline: {_pct(r['random_mean_gross_pct'])} gross per trade against "
                  f"{_pct(r['strategy_mean_gross_pct'])} for the strategy; p = {r['raw_p']:.3f} (Holm {r['holm_p']:.3f}).",
                  "", f"**Decision: {r['decision']}.**", "", "Informational (not part of the decision):", ""]
        if key in ("C5", "C6"):
            lines += [f"- The timed portfolio, cash included: {_growth(r['portfolio'])}; the index bought and held: "
                      f"{_growth(r['buy_and_hold'])}. Invested {r['share_invested_pct']:.0f}% of months "
                      f"({r['switches']} switches), including {r['worst_decile_months']['share_invested_pct']:.0f}% "
                      "of the index's worst tenth of months.",
                      f"- Before Jul 2013 ({r['in_sample_context']['span']}): {_growth(r['in_sample_context']['portfolio'])}; "
                      f"bought and held {_growth(r['in_sample_context']['buy_and_hold'])}.",
                      f"- Lookback re-chosen every year (63/126/252 days): {_growth(r['walk_forward']['walk_forward'])}; "
                      f"the fixed 252 days over the same years: {_growth(r['walk_forward']['fixed'])}."]
            if "cash_sensitivity" in r:
                lines.append("- Cash yield: " + "; ".join(f"{rate} a year: CAGR {_pct(s.get('cagr_pct'), 1)}"
                                                         for rate, s in r["cash_sensitivity"].items()) + "; 6% is the base case.")
        else:
            lines += [f"- Portfolio ({r['slots']} slot{'s' if r['slots'] > 1 else ''} of {100 // r['slots']}% of capital): "
                      f"{_growth(r['portfolio'])}; the index bought and held: {_growth(r['buy_and_hold'])}.",
                      f"- Stop exits: {_num(r['stop_exit_pct'], 0)}% of trades. The book's version without the stop: "
                      f"{_trades(r['no_stop_variant'])}.",
                      f"- Threshold re-chosen every year: {_trades(r['walk_forward']['walk_forward'])}; the fixed value "
                      f"over the same years: {_trades(r['walk_forward']['fixed'])}."]
            if key in ("C3", "C4"):
                lines += ["- By side: " + "; ".join(f"{side} {_trades(s)}" for side, s in r["by_side"].items()) + ".",
                          f"- Before Jul 2013 ({r['in_sample_context']['span']}): {_trades(r['in_sample_context']['stats'])}."]
            else:
                lines.append(f"- Up to {r['max_positions_in_a_day']} positions on one day.")
        lines += ["- Net per trade at 0x / 1x / 1.5x / 2x costs: "
                  + " / ".join(_pct(v) for v in r["cost_sensitivity"].values()) + ".",
                  f"- By regime (judged at the previous close): {_regimes(r['regimes'])}.",
                  "", "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {row['trades']} | {row['win_pct']:.1f}% | {_pct(row['exp_net_pct'])} |"
                  for year, row in r["by_year"].items()]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        s = r["stats"]
        print(f"{key}: {s.get('trades', 0)} trades, win {s.get('win_pct', float('nan')):.1f}%, "
              f"net {s.get('exp_net_pct', float('nan')):+.3f}%/trade, t {s.get('t_stat', float('nan')):.2f}, "
              f"clustered t {r['t_week']:.2f}, p {r['raw_p']:.4f} (Holm {r['holm_p']:.3f}) -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
