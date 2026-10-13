"""Research round 7: market intraday momentum in NIFTYBEES on the frozen Kite 1-minute bars, judged against
docs/research/round7-preregistration.md (pinned 13 Oct 2026, SHA-256 68cac73e...).

    python -m trader.research.round7        # once: writes docs/research/round7-results.md and the evidence

The signal is r_first, the NIFTY 50 index's change from the previous session's 15:14 bar to today's 09:44 bar
(Gao, Han, Li and Zhou, 2018). I1 buys NIFTYBEES from 14:45 to 15:14 after a rising morning, I2 shorts it after
a falling one, and I3 trades either way only after a big morning. Each is judged on its own. The runner refuses
to run if the pre-registration or the frozen data changed, if the code has uncommitted changes, or if results
already exist: the test runs once.
"""
from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict, replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research.costs import ZERODHA_INTRADAY
from trader.research.datasets import DATA_DIR, load_dataset, load_manifest, text_sha256
from trader.research.phase3 import holm
from trader.research.round2 import signal_week
from trader.research.validation import clustered_t, volatility_regime

IST = ZoneInfo("Asia/Kolkata")
PREREGISTRATION = ROOT / "docs" / "research" / "round7-preregistration.md"
PREREGISTRATION_SHA256 = "68cac73e66d2c285fafb0f0513ee06e656c8c9d4bdfca2484035786f030eb8e9"  # 2026-10-13 15:41 IST
RESULTS = ROOT / "docs" / "research" / "round7-results.md"
DATA = DATA_DIR / "kite_minute" / "nifty_1m"
AUX = DATA_DIR / "round6" / "aux_daily"  # India VIX, for the informational regime table only
ETF, INDEX = "NIFTYBEES.NS", "^NSEI"
DATA_SHA256 = {ETF: "50366de7326503bc73d0ade0210bce612eaa2821167d35b17a6e25a5f2c8ce8d",
               INDEX: "943600f23529989296aeb0528be3bba28801bd9f6d72b94816836376dc562a96"}
SIGNAL_BAR, PREVIOUS_BAR, ENTRY_BAR, EXIT_BAR = time(9, 44), time(15, 14), time(14, 45), time(15, 14)
STOP = 0.005  # 0.5% of the entry price: one R
BIG_LOOKBACK, BIG_PERCENTILE = 250, 80
NOTIONAL, EQUITY = 200_000, 1_000_000
COSTS = replace(ZERODHA_INTRADAY, exchange_rate=0.0000307, verified="2026-10-13")  # today's NSE charge
ROUND_TRIP = COSTS.round_trip(NOTIONAL)  # 0.1191%
STOP_EXTRA = COSTS.slippage_per_side  # a stopped trade's exit pays double slippage
DRAWS, SEED, CHUNK = 20_000, 7, 1_000
TESTS_IN_PROJECT = 23  # H1-H14, C1-C6, I1-I3
CROSS_ROUND_ALPHA = 0.05 / TESTS_IN_PROJECT
AUCTION_START = date(2026, 8, 3)
NAMES = {"I1": "Long side: buy after a rising morning",
         "I2": "Short side: short after a falling morning",
         "I3": "Big mornings: trade in the morning's direction"}


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


# ------------------------------------------------------------------------------------------------ data
def load(directory: Path = DATA, verify_pins: bool = True) -> dict[str, pd.DataFrame]:
    """The frozen bars in IST, sorted, duplicates dropped; nothing else is cleaned ("Data")."""
    if verify_pins:
        files = load_manifest(directory)["files"]
        changed = [t for t, sha in DATA_SHA256.items() if files.get(t, {}).get("sha256") != sha]
        if changed:
            raise SystemExit(f"the frozen data isn't the pinned data: {changed}")
    frames = load_dataset(directory)  # also checks every file against its manifest checksum
    out = {}
    for ticker in (ETF, INDEX):
        frame = frames[ticker]
        frame = frame[~frame.index.duplicated(keep="first")].sort_index()
        out[ticker] = frame.tz_convert(IST)
    return out


def by_day(frame: pd.DataFrame) -> dict[date, pd.DataFrame]:
    return {day: bars for day, bars in frame.groupby(frame.index.date)}


def bar_at(frame: pd.DataFrame, at: time) -> pd.DataFrame:
    rows = frame[frame.index.time == at]
    rows.index = rows.index.date
    return rows


# ------------------------------------------------------------------------------------------- sessions
def sessions(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per session (a day with index bars): r_first, whether it can be traded and why not, and I3's
    threshold. Everything here is known by 14:45 ("Timing")."""
    index, etf = frames[INDEX], frames[ETF]
    signal, previous, entry = bar_at(index, SIGNAL_BAR)["close"], bar_at(index, PREVIOUS_BAR)["close"], bar_at(etf, ENTRY_BAR)
    rows, last_close = [], None  # the latest earlier session's 15:14 index close
    for day in sorted(set(index.index.date)):
        r_first, reason = np.nan, ""
        if day not in signal.index:
            reason = "no index 09:44 bar"
        elif last_close is None:
            reason = "no earlier session with an index 15:14 bar"
        else:
            r_first = float(signal[day]) / last_close - 1
            if day not in entry.index:
                reason = "no NIFTYBEES 14:45 bar"
            elif not float(entry.loc[day, "volume"]) > 0:
                reason = "NIFTYBEES 14:45 bar without trades"
        rows.append({"session": day, "r_first": r_first, "traded": reason == "", "reason": reason})
        if day in previous.index:
            last_close = float(previous[day])
    table = pd.DataFrame(rows).set_index("session")
    computable = table["r_first"].dropna().abs()  # the previous 250 sessions with r_first, today excluded
    threshold = computable.rolling(BIG_LOOKBACK).quantile(BIG_PERCENTILE / 100, interpolation="linear").shift(1)
    table["big_threshold"] = threshold.reindex(table.index)
    table["big"] = table["big_threshold"].notna() & (table["r_first"].abs() >= table["big_threshold"])
    return table


def window(bars: pd.DataFrame, side: str, use_stop: bool = True) -> dict:
    """One session's trade: entry at the 14:45 bar's open; the stop watched on bars with trades; exit at the
    15:14 bar's close, or at the last traded bar's close before it ("Simulating the 0.5% stop")."""
    span = bars[(bars.index.time >= ENTRY_BAR) & (bars.index.time <= EXIT_BAR)]
    traded = span[span["volume"] > 0]
    o, h, l, c = (traded[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    entry = o[0]  # the 14:45 bar, which traded (checked before the session counts as traded)
    stop = entry * (1 - STOP) if side == "long" else entry * (1 + STOP)
    if use_stop:
        hits = np.flatnonzero(l <= stop) if side == "long" else np.flatnonzero(h >= stop)
        if len(hits):
            i = hits[0]
            fill = min(stop, o[i]) if side == "long" else max(stop, o[i])
            gapped = o[i] < stop if side == "long" else o[i] > stop
            return {"entry": entry, "exit": fill, "stopped": True, "gapped": bool(gapped), "exit_time": traded.index[i]}
    return {"entry": entry, "exit": c[-1], "stopped": False, "gapped": False, "exit_time": traded.index[-1]}


def gross(trade: dict, side: str) -> float:
    return trade["exit"] / trade["entry"] - 1 if side == "long" else 1 - trade["exit"] / trade["entry"]


def outcomes(frames: dict[str, pd.DataFrame], table: pd.DataFrame) -> pd.DataFrame:
    """For every traded session: the window traded long and short, with and without the stop (the pools)."""
    days, rows = by_day(frames[ETF]), []
    for day in table.index[table["traded"]]:
        row = {"session": day}
        for side in ("long", "short"):
            trade = window(days[day], side)
            row[f"{side}_gross"], row[f"{side}_stopped"] = gross(trade, side), trade["stopped"]
            row[f"{side}_gapped"], row[f"{side}_exit_time"] = trade["gapped"], trade["exit_time"]
            row[f"{side}_gross_no_stop"] = gross(window(days[day], side, use_stop=False), side)
        rows.append(row)
    return pd.DataFrame(rows).set_index("session")


def hypothesis_trades(key: str, table: pd.DataFrame, out: pd.DataFrame) -> pd.DataFrame:
    """A hypothesis's trades (one per session at most), net of costs ("Hypotheses", "Costs")."""
    traded = table.loc[out.index]
    if key == "I1":
        sides = pd.Series("long", index=traded.index[traded["r_first"] > 0])
    elif key == "I2":
        sides = pd.Series("short", index=traded.index[traded["r_first"] < 0])
    else:
        big = traded[traded["big"] & (traded["r_first"] != 0)]
        sides = pd.Series(np.where(big["r_first"] > 0, "long", "short"), index=big.index)
    rows = []
    for day, side in sides.items():
        o = out.loc[day]
        g, stopped = float(o[f"{side}_gross"]), bool(o[f"{side}_stopped"])
        cost = ROUND_TRIP + (STOP_EXTRA if stopped else 0.0)
        rows.append({"session": day, "side": side, "r_first": float(traded.loc[day, "r_first"]), "gross": g,
                     "stopped": stopped, "gapped": bool(o[f"{side}_gapped"]), "cost": cost, "net": g - cost,
                     "R": (g - cost) / STOP, "gross_no_stop": float(o[f"{side}_gross_no_stop"]),
                     "exit_time": o[f"{side}_exit_time"]})
    return pd.DataFrame(rows).sort_values("exit_time").reset_index(drop=True)


def eligible_sessions(key: str, table: pd.DataFrame, out: pd.DataFrame) -> pd.Index:
    """The sessions a hypothesis could trade: its pools and its span."""
    return out.index if key in ("I1", "I2") else out.index[table.loc[out.index, "big_threshold"].notna().to_numpy()]


# ------------------------------------------------------------------------------------------- the tests
def baseline(pools: dict[str, np.ndarray], counts: dict[str, int], observed: float, draws: int = DRAWS,
             seed: int = SEED) -> tuple[float, float]:
    """("The random baseline, precisely") Mean gross of `draws` random samples, with replacement, of as many
    sessions from each side's pool as the hypothesis traded on that side; p = (k + 1) / (draws + 1), k counting
    the draws at least as high as `observed`. Returns (mean of the draws, p)."""
    rng = np.random.default_rng(seed)
    n, means = sum(counts.values()), np.empty(draws)
    for start in range(0, draws, CHUNK):
        size, total = min(CHUNK, draws - start), np.zeros(min(CHUNK, draws - start))
        for side in ("long", "short"):
            if counts.get(side, 0):
                pool = pools[side]
                total += pool[rng.integers(0, len(pool), size=(size, counts[side]))].sum(axis=1)
        means[start:start + size] = total / n
    return float(means.mean()), (int((means >= observed).sum()) + 1) / (draws + 1)


def drawdown_r(r_in_exit_order: np.ndarray) -> float:
    """Deepest fall of the cumulative R from its running peak (starting at 0), as a positive depth."""
    path = np.cumsum(r_in_exit_order)
    return float(-(path - np.maximum.accumulate(np.r_[0.0, path])[1:]).min()) if len(path) else 0.0


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
    halves = [net[trades["session"] < mid].mean(), net[trades["session"] >= mid].mean()]
    years = net.groupby([d.year for d in trades["session"]]).agg(["count", "mean"]) if n else pd.DataFrame()
    counted = years[years["count"] >= 10] if n else years
    share_years = float((counted["mean"] > 0).mean()) if len(counted) else np.nan
    t_week = clustered_t(net, [signal_week(d) for d in trades["session"]]) if n else np.nan
    depth = drawdown_r(trades["R"].to_numpy(float))
    ratio = -avg_loss / avg_win if avg_win and avg_win > 0 and not np.isnan(avg_loss) else np.nan

    def ok(value, rule):
        return bool(not pd.isna(value) and rule(value))

    checks = [
        Check(1, "At least 50 trades", f"{n}", n >= 50),
        Check(2, "Win rate at least 50%", f"{100 * (net > 0).mean():.1f}%" if n else "-", ok((net > 0).mean() if n else np.nan, lambda v: v >= 0.5)),
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
        Check(11, "Cluster-robust t-statistic (signal ISO weeks as clusters) at least 2.0", f"{t_week:.2f}",
              ok(t_week, lambda v: v >= 2.0)),
        Check(12, f"Raw random-baseline p below 0.05/{TESTS_IN_PROJECT} = {CROSS_ROUND_ALPHA:.5f}", f"{p_raw:.5f}",
              ok(p_raw, lambda v: v < CROSS_ROUND_ALPHA)),
        Check(13, "Drawdown no deeper than 20R (cumulative R in exit order)", f"{depth:.1f}R", depth <= 20.0),
    ]
    stats = {"trades": n, "win_rate": float((net > 0).mean()) if n else np.nan, "mean_net": mean, "sd_net": sd,
             "mean_gross": float(trades["gross"].mean()) if n else np.nan, "t": t, "t_clustered": t_week,
             "profit_factor": pf, "max_drawdown_r": depth, "stops": int(trades["stopped"].sum()) if n else 0,
             "gapped_stops": int(trades["gapped"].sum()) if n else 0, "years": years}
    return checks, stats


# ---------------------------------------------------------------------------------------- informational
def summary(net: pd.Series) -> dict:
    net = net.astype(float)
    if not len(net):
        return {"trades": 0}
    sd = net.std(ddof=1)
    return {"trades": int(len(net)), "win_rate": float((net > 0).mean()), "mean": float(net.mean()),
            "t": float(net.mean() / (sd / np.sqrt(len(net)))) if len(net) > 2 and sd > 0 else np.nan}


def portfolio(trades: pd.DataFrame, all_sessions: pd.Index) -> dict:
    """Rs 10,00,000 with one Rs 2,00,000 position a session: daily P&L, compounded on the account."""
    pnl = (trades.set_index("session")["net"] * NOTIONAL).reindex(all_sessions, fill_value=0.0)
    equity = EQUITY + pnl.cumsum()
    daily = pnl / equity.shift(1, fill_value=EQUITY)
    years = len(all_sessions) / 252
    downside = np.sqrt((np.minimum(daily, 0) ** 2).mean())
    return {"final_equity": float(equity.iloc[-1]), "cagr": float((equity.iloc[-1] / EQUITY) ** (1 / years) - 1),
            "sharpe": float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else np.nan,
            "sortino": float(daily.mean() / downside * np.sqrt(252)) if downside > 0 else np.nan,
            "max_drawdown": float((equity / equity.cummax().clip(lower=EQUITY) - 1).min())}


def vix_regime(trades: pd.DataFrame) -> dict:
    try:
        vix = load_dataset(AUX)["^INDIAVIX"]["close"]
    except (FileNotFoundError, KeyError, ValueError):
        return {}
    regime = volatility_regime(vix, 250, 60)
    state = trades["session"].map(regime)
    return {label: summary(trades.loc[state == flag, "net"]) for label, flag in (("high", True), ("normal", False))}


# ----------------------------------------------------------------------------------------------- run
def git_commit() -> tuple[str, bool]:
    """(HEAD, whether the code, configuration and this round's documents have uncommitted changes)."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "trader", "config", "docs/research/round7-preregistration.md"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return head, bool(dirty)


def run(directory: Path = DATA, verify_pins: bool = True) -> dict:
    digest = check_preregistration()
    frames = load(directory, verify_pins)
    table = sessions(frames)
    out = outcomes(frames, table)
    results, raw_p = {}, {}
    for key in NAMES:
        trades = hypothesis_trades(key, table, out)
        pool_days = eligible_sessions(key, table, out)
        pools = {side: out.loc[pool_days, f"{side}_gross"].to_numpy(float) for side in ("long", "short")}
        counts = trades["side"].value_counts().to_dict() if len(trades) else {}
        observed = float(trades["gross"].mean()) if len(trades) else np.nan
        random_mean, raw_p[key] = baseline(pools, counts, observed) if len(trades) else (np.nan, 1.0)
        results[key] = {"name": NAMES[key], "trades": trades, "span": (pool_days.min(), pool_days.max()),
                        "random_mean": random_mean, "sessions": len(pool_days)}
    adjusted = holm(raw_p)
    for key, r in results.items():
        checks, stats = criteria(r["trades"], r["span"], adjusted[key], raw_p[key])
        trades = r["trades"]
        r.update(checks=checks, stats=stats, decision=decide(checks), raw_p=raw_p[key], holm_p=adjusted[key],
                 by_period={label: summary(trades.loc[mask, "net"]) for label, mask in (
                     ("before 3 Aug 2026", trades["session"] < AUCTION_START),
                     ("from 3 Aug 2026", trades["session"] >= AUCTION_START))} if len(trades) else {},
                 no_stop=summary(trades["gross_no_stop"] - ROUND_TRIP) if len(trades) else {},
                 costs={f"{x}x": float((trades["gross"] - x * trades["cost"]).mean()) for x in (0, 1, 1.5, 2)}
                 if len(trades) else {},
                 vix=vix_regime(trades) if len(trades) else {}, portfolio=portfolio(trades, table.index))
    unconditional = summary(out["long_gross"] - ROUND_TRIP - STOP_EXTRA * out["long_stopped"])
    untraded = table.loc[~table["traded"], "reason"].value_counts().to_dict()
    return {"digest": digest, "results": results, "sessions": len(table), "traded_sessions": int(table["traded"].sum()),
            "untraded": untraded, "unconditional": unconditional}


def evidence_for(key: str, r: dict, digest: str, commit: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round7-results.md (python -m trader.research.round7)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{r['span'][0]} to {r['span'][1]}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": ROUND_TRIP,
               "max_drawdown_r": s["max_drawdown_r"], "git_commit": commit},
        preregistration_sha256=digest)


def _pct(value, digits: int = 4) -> str:
    return f"{100 * value:+.{digits}f}%" if value is not None and not pd.isna(value) else "-"


def _num(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if value is not None and not pd.isna(value) else "-"


def _summary(s: dict) -> str:
    return (f"{s['trades']} trades, {100 * s['win_rate']:.1f}% winners, {_pct(s['mean'])} a trade, t {_num(s['t'])}"
            if s.get("trades") else "no trades")


def write_report(report: dict, commit: str) -> None:
    results = report["results"]
    lines = [
        "# Research round 7 results: market intraday momentum in NIFTYBEES",
        "",
        f"Run once on {datetime.now(IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.round7` at commit `{commit[:12]}`, "
        f"against [the pre-registration](round7-preregistration.md) (SHA-256 `{report['digest'][:16]}...`, pinned and "
        "pushed before this code was written) and the frozen data `data/kite_minute/nifty_1m` (checksums as pinned). "
        "Every hypothesis is reported, pass or fail. Returns are per trade and net of costs: "
        f"{100 * ROUND_TRIP:.4f}% a round trip, {100 * (ROUND_TRIP + STOP_EXTRA):.4f}% for a stopped trade.",
        "",
        f"Sessions: {report['sessions']} in the data, {report['traded_sessions']} could be traded. The rest were "
        "skipped because: " + "; ".join(f"{why}: {count}" for why, count in report["untraded"].items()) + ".",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Trades | Win rate | Net per trade | t | Cluster-robust t | p vs random (raw / Holm) | Drawdown | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        s = r["stats"]
        lines.append(f"| {key}: {r['name']} | {s['trades']} | {_pct(s['win_rate'], 1)[1:]} | {_pct(s['mean_net'])} | "
                     f"{_num(s['t'])} | {_num(s['t_clustered'])} | {r['raw_p']:.5f} / {r['holm_p']:.5f} | "
                     f"{s['max_drawdown_r']:.1f}R | **{r['decision']}** |")
    lines += ["", "## The criteria", "", "| # | Criterion | " + " | ".join(results) + " |",
              "|---|---|" + "---|" * len(results)]
    for i, check in enumerate(next(iter(results.values()))["checks"]):
        cells = [f"{r['checks'][i].value} ({'pass' if r['checks'][i].passed else '**fail**'})" for r in results.values()]
        lines.append(f"| {check.number} | {check.criterion} | " + " | ".join(cells) + " |")
    for key, r in results.items():
        s, trades = r["stats"], r["trades"]
        lines += ["", f"## {key}: {r['name']}", "",
                  f"Span {r['span'][0]} to {r['span'][1]} ({r['sessions']} sessions it could trade). "
                  f"Mean gross {_pct(s['mean_gross'])} a trade against {_pct(r['random_mean'])} for the same window on "
                  f"random sessions (p = {r['raw_p']:.5f}, Holm {r['holm_p']:.5f}).", "",
                  f"**Decision: {r['decision']}.**", "", "Informational (not part of the decision):", "",
                  f"- Stops: {s['stops']}, of which {s['gapped_stops']} filled at a gap.",
                  "- " + "; ".join(f"{label}: {_summary(v)}" for label, v in r["by_period"].items()) + ".",
                  "- By India VIX regime: " + ("; ".join(f"{label}: {_summary(v)}" for label, v in r["vix"].items()) or "-") + ".",
                  f"- Without the stop: {_summary(r['no_stop'])}.",
                  "- Net per trade at 0x / 1x / 1.5x / 2x costs: " + " / ".join(_pct(v) for v in r["costs"].values()) + ".",
                  f"- Portfolio (Rs 10,00,000, one Rs 2,00,000 position a session): CAGR {_pct(r['portfolio']['cagr'], 2)}, "
                  f"Sharpe {_num(r['portfolio']['sharpe'])}, Sortino {_num(r['portfolio']['sortino'])}, "
                  f"maximum drawdown {_pct(r['portfolio']['max_drawdown'], 2)}.",
                  "", "| Year | Trades | Net per trade |", "|---|---:|---:|"]
        lines += [f"| {year} | {int(row['count'])} | {_pct(row['mean'])} |" for year, row in s["years"].iterrows()]
    lines += ["", "## Informational, across hypotheses", "",
              f"- The window traded long on every tradable session, regardless of r_first: {_summary(report['unconditional'])}.",
              "", "Patterns in the informational sections are hypotheses for future data, not findings. Nothing here "
              "changes a rule: a changed rule is a new hypothesis, which can only be judged on data that doesn't exist yet."]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description="Round 7: run once on the frozen minute data.").parse_args(argv)
    make_console_utf8()
    if RESULTS.exists():
        raise SystemExit(f"{RESULTS.name} already exists: round 7 runs once. A runner bug found later is fixed, "
                         "documented and re-run under the pre-registration's protocol, step 5.")
    commit, dirty = git_commit()
    if dirty:
        raise SystemExit("uncommitted changes to the code, the configuration or the pre-registration: run round 7 "
                         "from a committed, pushed state")
    report = run()
    write_report(report, commit)
    for key, r in report["results"].items():
        save_evidence(evidence_for(key, r, report["digest"], commit))
        s = r["stats"]
        print(f"{key}: {s['trades']} trades, win {_pct(s['win_rate'], 1)}, net {_pct(s['mean_net'])} a trade, "
              f"t {_num(s['t'])}, p {r['raw_p']:.5f} (Holm {r['holm_p']:.5f}), drawdown {s['max_drawdown_r']:.1f}R "
              f"-> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
