"""Phase 3: run the pre-registered swing hypotheses and write the evidence report.

    python -m trader.research.phase3        # writes docs/research/phase3-results.md

Everything follows docs/research/phase3-preregistration.md. Its SHA-256 was recorded before any
strategy ran, and this runner refuses to judge against a different version of that file.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.data.validate import placeholder_bars
from trader.features.indicators import sma
from trader.gate import Evidence, ResearchThresholds, decide, research_checks, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research.costs import US_COMMISSION_FREE, ZERODHA_DELIVERY, ZERODHA_ETF_DELIVERY
from trader.research.datasets import DATA_DIR, load_dataset, text_sha256
from trader.research.metrics import summarize
from trader.research.simulator import concat_trades, select_trades, simulate, trade_rows
from trader.research.validation import random_entry_test
from trader.strategies.swing import (MOMENTUM, PULLBACK, momentum_panel, momentum_trades, pullback_rules,
                                     pullback_signals, select_top)

PREREGISTRATION = ROOT / "docs" / "research" / "phase3-preregistration.md"
PREREGISTRATION_SHA256 = "4be087a7804f649981adee6fe9d194ddbb0c24a513b54bf718b7cc8c7dd536a2"  # 2026-10-09 00:52 IST
RESULTS = ROOT / "docs" / "research" / "phase3-results.md"
DATA = DATA_DIR / "phase3"
EVAL_START, HOLDOUT_START, EVAL_END = date(2016, 1, 1), date(2022, 1, 1), date(2026, 10, 8)
COSTS = {"stocks": ZERODHA_DELIVERY.round_trip(100_000), "etf": ZERODHA_ETF_DELIVERY.round_trip(100_000),
         "us": US_COMMISSION_FREE.round_trip(10_000)}
STRESS = 1.5
# Unadjusted corporate actions found by the data-quality report before any strategy ran. Yahoo didn't
# adjust these series, so each is split at the event: no trade or indicator spans the fake jump.
CORPORATE_ACTION_BREAKS = {
    "ADANIENT.NS": ["2015-06-03"],  # demerger; the open printed at 3.2x the previous close
    "TMPV.NS": ["2025-10-14"],  # Tata Motors demerger (price x0.60)
    "TRENT.NS": ["2026-01-01"],  # 1:2 bonus issue (price x2/3)
}
RANDOM_BASELINE = {"H1": "random days, same stocks, same exits", "H2": "random days, same index, same exits",
                   "H3": "5 random stocks from the same month's eligible list"}
# The criteria exactly as pre-registered. Written out here, not read from config/gate.toml, so later
# changes to the gate can't change how these hypotheses were judged.
PREREGISTERED = ResearchThresholds(min_trades=50, min_win_rate=0.50, min_profit_factor=1.3, min_t_stat=2.0,
                                   max_p_value=0.05, cost_stress=1.5, max_loss_to_win=1.5, worst_trade_r=-3.0,
                                   min_positive_years=0.70, min_trades_per_year=10, min_breadth=0.60,
                                   min_trades_per_stock=5)


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def base_symbol(name: str) -> str:
    return name.split("#")[0]


def clean_daily(frames: dict[str, pd.DataFrame], breaks: dict | None = None):
    """Drop bars without prices and Yahoo's flat zero-volume placeholder bars (seen on NSE holidays),
    then split series at unadjusted corporate actions. Returns (pieces, notes)."""
    breaks = CORPORATE_ACTION_BREAKS if breaks is None else breaks
    pieces, notes = {}, {}
    for symbol, frame in frames.items():
        frame = frame[~frame.index.duplicated(keep="first")].sort_index()
        prices = frame[["open", "high", "low", "close"]]
        missing = prices.isna().any(axis=1)
        flat = placeholder_bars(frame)
        kept = frame[~missing & ~flat]
        cuts = [pd.Timestamp(when).tz_localize(kept.index.tz) for when in breaks.get(symbol, [])]
        edges = [None, *cuts, None]
        for k, (low, high) in enumerate(zip(edges[:-1], edges[1:])):
            part = kept if low is None else kept[kept.index >= low]
            part = part if high is None else part[part.index < high]
            if len(part):
                pieces[symbol if k == 0 else f"{symbol}#{k + 1}"] = part
        if missing.any() or flat.any() or cuts:
            note = f"dropped {int(missing.sum())} bar(s) without prices and {int(flat.sum())} flat zero-volume placeholder(s)"
            notes[symbol] = note + (f"; split at {', '.join(breaks[symbol])}" if cuts else "")
    return pieces, notes


def trading_days(pieces: dict[str, pd.DataFrame], start: date, end: date) -> list[date]:
    days = {d for frame in pieces.values() for d in frame.index.date}
    return sorted(d for d in days if start <= d <= end)


def in_window(trades: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return trades[(trades["signal_date"] >= start) & (trades["signal_date"] <= end)].reset_index(drop=True)


def run_pullback(pieces: dict[str, pd.DataFrame], rule: str):
    """H1/H2 trades over the evaluation span, plus holdout random-entry pools keyed by symbol."""
    frames, pools = [], {}
    for name, bars in pieces.items():
        if len(bars) <= PULLBACK.trend_sma:
            continue
        signals = pullback_signals(bars)
        out = simulate(bars, "long", pullback_rules(), "next_open", stop=signals.stop, exit_signal=signals.exit)
        symbol = base_symbol(name)
        frames.append(trade_rows(symbol, bars.index, select_trades(signals.entry, out), out, "long", rule))
        dates = np.asarray(bars.index.date)
        ready = sma(bars["close"], PULLBACK.trend_sma).notna().to_numpy() & ~np.isnan(out.gross)
        holdout = ready & (dates >= HOLDOUT_START) & (dates <= EVAL_END)
        pools.setdefault(symbol, []).append(out.gross[holdout])
    pools = {symbol: np.concatenate(parts) for symbol, parts in pools.items()}
    return in_window(concat_trades(frames), EVAL_START, EVAL_END), {s: p for s, p in pools.items() if len(p)}


def run_momentum(pieces: dict[str, pd.DataFrame]):
    """H3 trades over the evaluation span, plus the full panel of eligible stocks for its baseline."""
    panel = momentum_panel(pieces)
    panel["symbol"] = panel["symbol"].map(base_symbol)
    panel["selected"] = select_top(panel)
    panel["signal_date"] = [stamp.date() for stamp in panel["month_end"]]
    trades = in_window(momentum_trades(panel, panel["selected"].to_numpy()), EVAL_START, EVAL_END)
    return trades, panel


def selection_test(panel: pd.DataFrame, n_iter: int = 2000, seed: int = 7) -> tuple[float, float]:
    """H3's baseline: the same number of random picks from each month's eligible stocks.
    Returns (mean gross of random picks, P(random mean >= momentum mean))."""
    rng = np.random.default_rng(seed)
    total, count = np.zeros(n_iter), 0
    for _, month in panel.groupby("month_end"):
        k = int(month["selected"].sum())
        if k == 0:
            continue
        returns = month["gross"].to_numpy(float)
        picks = rng.random((n_iter, len(returns))).argsort(axis=1)[:, :k]
        total += returns[picks].sum(axis=1)
        count += k
    random_means = total / count
    observed = panel.loc[panel["selected"], "gross"].mean()
    return float(random_means.mean()), float((random_means >= observed).mean())


def momentum_portfolio_view(panel: pd.DataFrame, index_bars: pd.DataFrame) -> list[tuple[str, float, float, float]]:
    """Informational: holdout months as equally weighted monthly portfolios, net of each one's costs.
    Returns (label, average monthly return, total return, max drawdown) rows."""
    hold = panel[(panel["signal_date"] >= HOLDOUT_START) & (panel["signal_date"] <= EVAL_END)]
    momentum = hold[hold["selected"]].groupby("month_end")["gross"].mean() - COSTS["stocks"]
    universe = hold.groupby("month_end")["gross"].mean() - COSTS["stocks"]
    index_open, index_returns = index_bars["open"], {}
    for month_end, group in hold.groupby("month_end"):
        entry = index_open.index.searchsorted(group["entry_time"].iloc[0])
        exit_ = index_open.index.searchsorted(group["exit_time"].iloc[0])
        if exit_ < len(index_open):
            index_returns[month_end] = index_open.iloc[exit_] / index_open.iloc[entry] - 1 - COSTS["etf"]
    rows = []
    for label, monthly in (("H3: momentum, top 5 stocks", momentum),
                           ("All eligible NIFTY 50 stocks, equal weight", universe),
                           ("NIFTY 50 index via ETF", pd.Series(index_returns))):
        growth = (1 + monthly.sort_index()).cumprod()
        drawdown = float((growth / growth.cummax().clip(lower=1.0) - 1).min())
        rows.append((label, float(monthly.mean()), float(growth.iloc[-1] - 1), drawdown))
    return rows


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (step-down, kept monotone)."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[name] = running
    return adjusted


def evaluate(trades: pd.DataFrame, cost: float, pieces: dict, p_holm: float, stocks: bool):
    """The pre-registered criteria (via the shared gate), scored on the holdout."""
    days = {"design": trading_days(pieces, EVAL_START, date(2021, 12, 31)),
            "holdout": trading_days(pieces, HOLDOUT_START, EVAL_END),
            "all": trading_days(pieces, EVAL_START, EVAL_END)}
    checks, details = research_checks(trades, cost, HOLDOUT_START, days, p_holm, stocks, PREREGISTERED)
    return details["stats"], checks, details["by_year"], decide(checks), details["stress"], details["worst_r"]


def evidence_for(key: str, result: dict, digest: str) -> Evidence:
    """The machine-readable verdict the registry checks (docs/research/evidence/<id>.research.json)."""
    holdout = result["trades"][result["trades"]["signal_date"] >= HOLDOUT_START]
    net = holdout["gross"] - result["cost"]
    h = result["stats"]["holdout"]
    return Evidence(
        strategy_id=key, kind="research", decision=result["decision"], generated=date.today().isoformat(),
        source="docs/research/phase3-results.md (python -m trader.research.phase3)",
        checks=tuple(asdict(c) for c in result["checks"]),
        stats={"holdout_trades": int(len(net)), "holdout_win_rate": float((net > 0).mean()),
               "holdout_mean_net": float(net.mean()), "holdout_sd_net": float(net.std(ddof=1)),
               "holdout_profit_factor": float(h["profit_factor"]), "holdout_t": float(h["t_stat"]),
               "p_random_raw": result["raw_p"], "p_random_holm": result["holm_p"], "round_trip_cost": result["cost"]},
        preregistration_sha256=digest)


def _pct(value) -> str:
    return "-" if value is None or (isinstance(value, float) and np.isnan(value)) else f"{value:+.3f}%"


def stats_table(stats: dict, cost: float, trades: pd.DataFrame) -> str:
    lines = ["| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, key in (("Design 2016-2021", "design"), ("Holdout 2022-2026", "holdout"), ("All", "all")):
        s = stats[key]
        if not s.get("trades"):
            lines.append(f"| {label} | 0 | - | - | - | - | - | - | - | - |")
            continue
        lines.append(f"| {label} | {s['trades']} | {s['win_pct']:.1f}% | {s['avg_win_pct']:+.2f}% | {s['avg_loss_pct']:+.2f}% | "
                     f"{s['profit_factor']:.2f} | {s['exp_net_pct']:+.3f}% | {s['t_stat']:.2f} | "
                     f"{s['max_dd_units']:.1f}{s['unit']} | {s['sharpe']:.2f} |")
    return "\n".join(lines)


def run(write: bool = True) -> dict:
    make_console_utf8()
    digest = check_preregistration()
    raw_stocks = load_dataset(DATA / "nse_nifty50_daily")
    raw_index = load_dataset(DATA / "nse_index_daily")
    raw_us = load_dataset(DATA / "us_daily")
    stocks, stock_notes = clean_daily(raw_stocks)
    index, index_notes = clean_daily(raw_index)
    us, us_notes = clean_daily(raw_us, breaks={})

    h1, h1_pools = run_pullback(stocks, "H1")
    h2, h2_pools = run_pullback(index, "H2")
    h3, panel = run_momentum(stocks)

    h1_holdout = h1[h1["signal_date"] >= HOLDOUT_START]
    h2_holdout = h2[h2["signal_date"] >= HOLDOUT_START]
    holdout_panel = panel[(panel["signal_date"] >= HOLDOUT_START) & (panel["signal_date"] <= EVAL_END)]
    baselines = {"H1": random_entry_test(h1_pools, h1_holdout["ticker"], h1_holdout["gross"]),
                 "H2": random_entry_test(h2_pools, h2_holdout["ticker"], h2_holdout["gross"]),
                 "H3": selection_test(holdout_panel)}
    random_means = {key: mean for key, (mean, _) in baselines.items()}
    raw_p = {key: p for key, (_, p) in baselines.items()}
    adjusted = holm(raw_p)

    results = {}
    for key, trades, cost, pieces, is_stocks, name in (
            ("H1", h1, COSTS["stocks"], stocks, True, "Oversold pullback in an uptrend, NIFTY 50 stocks"),
            ("H2", h2, COSTS["etf"], index, False, "Oversold pullback in an uptrend, NIFTY 50 index via ETF"),
            ("H3", h3, COSTS["stocks"], stocks, True, "12-1 month momentum, top 5 NIFTY 50 stocks monthly")):
        stats, checks, by_year, decision, stress, worst_r = evaluate(trades, cost, pieces, adjusted[key], is_stocks)
        results[key] = {"name": name, "trades": trades, "cost": cost, "stats": stats, "checks": checks,
                        "by_year": by_year, "decision": decision, "raw_p": raw_p[key], "holm_p": adjusted[key],
                        "random_mean": random_means[key]}

    us_rows = []
    us_stocks = {k: v for k, v in us.items() if k != "SPY"}
    for label, pieces in (("H1 rules on 20 US large caps", us_stocks), ("H2 rules on SPY", {"SPY": us["SPY"]})):
        trades, pools = run_pullback(pieces, "US")
        holdout = trades[trades["signal_date"] >= HOLDOUT_START]
        s = summarize(holdout, COSTS["us"], trading_days(pieces, HOLDOUT_START, EVAL_END))
        p = random_entry_test(pools, holdout["ticker"], holdout["gross"])[1] if len(holdout) else np.nan
        us_rows.append((label, s, p))

    portfolios = momentum_portfolio_view(panel, index["^NSEI"])
    if write:
        write_report(digest, results, us_rows, stock_notes, index_notes, raw_stocks, portfolios)
        for key, result in results.items():
            save_evidence(evidence_for(key, result, digest))
    return results


def write_report(digest, results, us_rows, stock_notes, index_notes, raw_stocks, portfolios) -> None:
    lines = [
        "# Phase 3 results: swing-trading hypotheses",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.phase3`, judged against "
        f"[the pre-registration](phase3-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "recorded before any strategy ran). Returns are per trade, net of costs; holdout = 2022 to 8 Oct 2026.",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Holdout trades | Win rate | Net per trade | Profit factor | t | p vs random (Holm) | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        h = r["stats"]["holdout"]
        lines.append(f"| {key}: {r['name']} | {h.get('trades', 0)} | {h.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(h.get('exp_net_pct'))} | {h.get('profit_factor', np.nan):.2f} | {h.get('t_stat', np.nan):.2f} | "
                     f"{r['holm_p']:.3f} | **{r['decision']}** |")
    lines += ["", "## Data and costs", "",
              f"- NIFTY 50 stocks: {len(raw_stocks)} symbols, daily, Yahoo (adjusted), frozen in `data/phase3/` with checksums.",
              "- Cleaning, fixed after the data-quality report and before any strategy ran: bars without prices "
              "(Yahoo's broken 8 Oct 2026 bar) and Yahoo's flat zero-volume placeholder bars on NSE holidays were "
              "dropped; three unadjusted corporate actions split their series (ADANIENT 3 Jun 2015 demerger, TMPV "
              "14 Oct 2025 demerger, TRENT 1 Jan 2026 bonus).",
              f"- Round-trip costs: stocks {100 * COSTS['stocks']:.3f}% (Zerodha delivery), NIFTY ETF {100 * COSTS['etf']:.3f}%, "
              f"US {100 * COSTS['us']:.3f}%; stress test at {STRESS}x.",
              "- Survivorship bias: today's index members over a past decade over-represent winners. The random "
              "baselines use the same stocks and period, so they share that bias."]
    for key, r in results.items():
        lines += ["", f"## {key}: {r['name']}", "", stats_table(r["stats"], r["cost"], r["trades"]), "",
                  f"Random baseline ({RANDOM_BASELINE[key]}), holdout: {100 * r['random_mean']:+.3f}% gross per trade "
                  f"vs {100 * r['trades'][r['trades']['signal_date'] >= HOLDOUT_START]['gross'].mean():+.3f}% for the strategy; "
                  f"p = {r['raw_p']:.3f} (Holm-adjusted {r['holm_p']:.3f}).", "",
                  "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else '**no**'} |" for c in r["checks"]]
        lines += ["", f"**Decision: {r['decision']}.**", "", "By year (all trades, net of base costs):", "",
                  "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for year, row in r["by_year"].iterrows()]
        if key == "H3":
            lines += ["", "H3's drawdown above adds up five simultaneous positions. As equally weighted monthly "
                          "portfolios over the holdout months, each net of its own monthly trading costs "
                          "(informational; doesn't affect the decision):", "",
                      "| Portfolio | Average month | Total return | Max drawdown |", "|---|---:|---:|---:|"]
            lines += [f"| {label} | {100 * avg:+.2f}% | {100 * total:+.1f}% | {100 * dd:.1f}% |"
                      for label, avg, total, dd in portfolios]
    lines += ["", "## Informational: the same rules in the US (doesn't affect the decisions)", "",
              "| Test | Holdout trades | Win rate | Net per trade | t | p vs random |", "|---|---:|---:|---:|---:|---:|"]
    for label, s, p in us_rows:
        lines.append(f"| {label} | {s.get('trades', 0)} | {s.get('win_pct', np.nan):.1f}% | {_pct(s.get('exp_net_pct'))} | "
                     f"{s.get('t_stat', np.nan):.2f} | {p:.3f} |")
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        h = r["stats"]["holdout"]
        print(f"{key}: holdout {h.get('trades', 0)} trades, win {h.get('win_pct', float('nan')):.1f}%, "
              f"net {h.get('exp_net_pct', float('nan')):+.3f}%/trade, t {h.get('t_stat', float('nan')):.2f}, "
              f"Holm p {r['holm_p']:.3f} -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
