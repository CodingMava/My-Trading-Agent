"""Research round 2: the Phase 3 pullback rules on new markets, judged against
docs/research/round2-preregistration.md.

    python -m trader.research.round2        # writes docs/research/round2-results.md and the evidence files

The pre-registration's SHA-256 was recorded before any strategy ran, and this runner refuses to judge
against a different version of it. It also refuses to run while any daily move above 20% in the data is
unclassified: the pre-registration requires each one to be classified before the strategies see the data.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.features.indicators import sma
from trader.gate import Check, Evidence, ResearchThresholds, decide, research_checks, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research.costs import US_COMMISSION_FREE, ZERODHA_ETF_DELIVERY
from trader.research.datasets import DATA_DIR, load_dataset
from trader.research.phase3 import base_symbol, clean_daily, holm, in_window, stats_table, trading_days
from trader.research.simulator import concat_trades, select_trades, simulate, trade_rows
from trader.research.validation import clustered_t, random_entry_test, same_day_random_test
from trader.strategies.swing import PULLBACK, pullback_rules, pullback_signals

PREREGISTRATION = ROOT / "docs" / "research" / "round2-preregistration.md"
PREREGISTRATION_SHA256 = "f61e6ee0181c1e6266c55af6f2efe8ceead438f8a9075c7ad504784296b3b735"  # 2026-10-09 22:45 IST
RESULTS = ROOT / "docs" / "research" / "round2-results.md"
DATA = DATA_DIR / "round2"
EVAL_START, HOLDOUT_START, EVAL_END = date(2016, 1, 1), date(2022, 1, 1), date(2026, 10, 8)
COSTS = {"us": US_COMMISSION_FREE.round_trip(10_000),
         "india_etf": ZERODHA_ETF_DELIVERY.with_slippage(0.0005).round_trip(100_000)}
STRESS = 1.5
# The criteria exactly as pre-registered (1-10 as in Phase 3, plus 11), written out so later changes to
# config/gate.toml can't change how these hypotheses were judged.
PREREGISTERED = ResearchThresholds(min_trades=50, min_win_rate=0.50, min_profit_factor=1.3, min_t_stat=2.0,
                                   max_p_value=0.05, cost_stress=1.5, max_loss_to_win=1.5, worst_trade_r=-3.0,
                                   min_positive_years=0.70, min_trades_per_year=10, min_breadth=0.60,
                                   min_trades_per_stock=5)
MIN_CLUSTERED_T = 2.0
HYPOTHESES = {  # id: (name, dataset, cost key)
    "H4": ("Oversold pullback in an uptrend, US large caps", "us_stocks_daily", "us"),
    "H5": ("Oversold pullback in an uptrend, Indian index ETFs", "nse_index_daily", "india_etf"),
    "H6": ("Oversold pullback in an uptrend, US sector ETFs", "us_sector_etfs_daily", "us"),
}
ETF_FOR_INDEX = {"^NSEBANK": "BANKBEES.NS", "^CNXIT": "ITBEES.NS", "^CNXPHARMA": "PHARMABEES.NS",
                 "^NSMIDCP": "JUNIORBEES.NS"}

# Every daily move above 20% (close to close, or open gap) in the evaluation data, classified before any
# strategy ran: news for the 2026 moves was checked in press coverage on 2026-10-09.
MOVE_LIMIT = 0.20
CORPORATE_ACTION_BREAKS = {
    "DHR": ["2016-07-05"],  # Fortive spin-off: Yahoo's adjustment leaves everything before it 38% too low
}
MARKET_WIDE = {
    "2020-03-09": "COVID-19 crash (oil price war)", "2020-03-12": "COVID-19 crash", "2020-03-13": "COVID-19 rebound",
    "2020-03-16": "COVID-19 crash", "2020-03-18": "COVID-19 crash", "2020-03-19": "COVID-19 rebound",
    "2020-03-24": "COVID-19 rebound", "2020-03-25": "COVID-19 rebound", "2020-11-09": "Vaccine-news rally",
    "2025-04-09": "Tariff-pause rally",
}
COMPANY_NEWS = {
    ("AMD", "2016-04-22"): "Q1 results and China licensing deal", ("AMD", "2017-05-02"): "Q1 results",
    ("AMD", "2018-10-25"): "Q3 results", ("AMD", "2025-10-06"): "OpenAI chip partnership",
    ("CHTR", "2026-04-24"): "Q1 results", ("CHTR", "2026-06-29"): "Reported SpaceX partnership talks",
    ("CRM", "2020-08-26"): "Q2 results", ("CRM", "2026-08-27"): "Q2 results", ("FDX", "2022-09-16"): "Profit warning",
    ("IBM", "2026-07-14"): "Preliminary Q2 shortfall", ("INTC", "2024-08-02"): "Q2 results and layoffs",
    ("INTC", "2025-09-18"): "Nvidia investment", ("INTC", "2026-04-24"): "Q1 results",
    ("INTU", "2026-05-21"): "Q3 results and layoffs", ("MMM", "2024-07-26"): "Q2 results",
    ("NFLX", "2014-10-16"): "Q3 results", ("NFLX", "2022-01-21"): "Q4 results", ("NFLX", "2022-04-20"): "Q1 results",
    ("NOW", "2016-01-28"): "Q4 results and guidance", ("ORCL", "2025-09-10"): "Q1 results (contract backlog)",
    ("PLTR", "2020-11-25"): "Retail rally after its listing", ("PLTR", "2020-12-07"): "Retail rally after its listing",
    ("PLTR", "2021-01-22"): "Retail rally after its listing", ("PLTR", "2022-05-09"): "Q1 results",
    ("PLTR", "2023-02-14"): "Q4 results", ("PLTR", "2023-05-09"): "Q1 results", ("PLTR", "2023-11-02"): "Q3 results",
    ("PLTR", "2024-02-06"): "Q4 results", ("PLTR", "2024-11-05"): "Q3 results", ("PLTR", "2025-02-04"): "Q4 results",
    ("PLTR", "2026-08-04"): "Q2 results", ("PYPL", "2022-02-02"): "Q4 results",
    ("PYPL", "2026-02-03"): "Q4 results and CEO change", ("QCOM", "2019-04-16"): "Apple settlement",
    ("SBUX", "2024-08-13"): "New CEO", ("TGT", "2019-08-21"): "Q2 results", ("TGT", "2022-05-18"): "Q1 results",
    ("TGT", "2024-11-20"): "Q3 results",
}


def check_preregistration() -> str:
    digest = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def large_moves(frames: dict[str, pd.DataFrame], limit: float = MOVE_LIMIT) -> list[tuple[str, date, float, float]]:
    """(symbol, day, close-to-close move, open gap) for every move above `limit` either way."""
    moves = []
    for symbol, frame in frames.items():
        close = frame["close"]
        change, gap = close.pct_change(), frame["open"] / close.shift() - 1
        for stamp in frame.index[(change.abs() > limit) | (gap.abs() > limit)]:
            moves.append((symbol, stamp.date(), float(change[stamp]), float(gap[stamp])))
    return moves


def classify(symbol: str, day: date) -> str | None:
    """How a flagged move was classified before the strategies ran (None: not yet classified)."""
    if day.isoformat() in CORPORATE_ACTION_BREAKS.get(symbol, []):
        return "Corporate action Yahoo mis-adjusted: series split here"
    reason = MARKET_WIDE.get(day.isoformat()) or COMPANY_NEWS.get((symbol, day.isoformat()))
    return f"Genuine: {reason}" if reason else None


def load_clean(name: str, data: Path = DATA, end: date = EVAL_END, classify_move=None, breaks: dict | None = None):
    """A frozen dataset cut at `end` and cleaned as pre-registered (round 2's settings by default).
    Returns (pieces, flagged moves); refuses to return anything while a flagged move is unclassified."""
    classify_move = classify_move or classify
    breaks = CORPORATE_ACTION_BREAKS if breaks is None else breaks
    raw = {s: f[np.asarray(f.index.date) <= end] for s, f in load_dataset(data / name).items()}
    unsplit, _ = clean_daily(raw, breaks={})
    moves = large_moves(unsplit)
    unclassified = [(s, d) for s, d, _, _ in moves if classify_move(s, d) is None]
    if unclassified:
        raise SystemExit(f"classify these moves above {MOVE_LIMIT:.0%} before running any strategy: {unclassified}")
    pieces, _ = clean_daily(raw, breaks=breaks)
    return pieces, moves


def pullback_trades(pieces: dict[str, pd.DataFrame], rule: str, start: date = EVAL_START, end: date = EVAL_END,
                    pool_start: date = HOLDOUT_START):
    """Trades signalled from `start` to `end`, plus each instrument's entry outcomes by signal day from
    `pool_start` to `end` (the random baseline's pools). Round 2's windows by default."""
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
        pooled = ready & (dates >= pool_start) & (dates <= end)
        pools.setdefault(symbol, []).append(pd.Series(out.gross[pooled], index=dates[pooled]))
    pools = {symbol: pd.concat(parts) for symbol, parts in pools.items()}
    return in_window(concat_trades(frames), start, end), {s: p for s, p in pools.items() if len(p)}


def signal_week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def by_instrument(trades: pd.DataFrame, cost: float) -> pd.DataFrame:
    net = trades["gross"] - cost
    table = pd.DataFrame({"trades": net.groupby(trades["ticker"]).size(),
                          "win_pct": 100 * (net > 0).groupby(trades["ticker"]).mean(),
                          "exp_net_pct": 100 * net.groupby(trades["ticker"]).mean()})
    return table.sort_values("exp_net_pct", ascending=False)


def evaluate(trades: pd.DataFrame, cost: float, pieces: dict, p_holm: float):
    """Criteria 1-10 through the shared gate, plus criterion 11 (cluster-robust t), on the holdout."""
    days = {"design": trading_days(pieces, EVAL_START, date(2021, 12, 31)),
            "holdout": trading_days(pieces, HOLDOUT_START, EVAL_END),
            "all": trading_days(pieces, EVAL_START, EVAL_END)}
    checks, details = research_checks(trades, cost, HOLDOUT_START, days, p_holm, True, PREREGISTERED)
    holdout = trades[trades["signal_date"] >= HOLDOUT_START]
    t_week = clustered_t(holdout["gross"] - cost, [signal_week(d) for d in holdout["signal_date"]])
    checks.append(Check(11, f"Cluster-robust t-statistic (signal weeks as clusters) at least {MIN_CLUSTERED_T}",
                        f"{t_week:.2f}", bool(t_week >= MIN_CLUSTERED_T)))
    return checks, details, t_week


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    """The machine-readable verdict the registry checks (docs/research/evidence/<id>.research.json)."""
    holdout = r["trades"][r["trades"]["signal_date"] >= HOLDOUT_START]
    net = holdout["gross"] - r["cost"]
    h = r["stats"]["holdout"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round2-results.md (python -m trader.research.round2)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"holdout_trades": int(len(net)), "holdout_win_rate": float((net > 0).mean()),
               "holdout_mean_net": float(net.mean()), "holdout_sd_net": float(net.std(ddof=1)),
               "holdout_profit_factor": float(h["profit_factor"]), "holdout_t": float(h["t_stat"]),
               "holdout_t_clustered": r["t_week"], "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"],
               "p_random_independent": r["independent_p"], "round_trip_cost": r["cost"]},
        preregistration_sha256=digest)


def run(write: bool = True) -> dict:
    make_console_utf8()
    digest = check_preregistration()
    loaded = {key: load_clean(dataset) for key, (_, dataset, _) in HYPOTHESES.items()}
    runs = {key: pullback_trades(loaded[key][0], key) for key in HYPOTHESES}

    baselines, independent = {}, {}
    for key, (trades, pools) in runs.items():
        holdout = trades[trades["signal_date"] >= HOLDOUT_START]
        baselines[key] = same_day_random_test(pools, holdout)
        arrays = {s: p.to_numpy() for s, p in pools.items()}
        independent[key] = random_entry_test(arrays, holdout["ticker"], holdout["gross"])[1]
    raw_p = {key: p for key, (_, p) in baselines.items()}
    adjusted = holm(raw_p)

    results = {}
    for key, (name, _, cost_key) in HYPOTHESES.items():
        trades, cost, pieces = runs[key][0], COSTS[cost_key], loaded[key][0]
        checks, details, t_week = evaluate(trades, cost, pieces, adjusted[key])
        results[key] = {"name": name, "trades": trades, "cost": cost, "stats": details["stats"], "checks": checks,
                        "by_year": details["by_year"], "decision": decide(checks), "raw_p": raw_p[key],
                        "holm_p": adjusted[key], "random_mean": baselines[key][0], "independent_p": independent[key],
                        "t_week": t_week, "by_instrument": by_instrument(trades, cost)}
    if write:
        moves = [move for key in HYPOTHESES for move in loaded[key][1]]
        write_report(digest, results, moves)
        for key, result in results.items():
            save_evidence(evidence_for(key, result, digest))
    return results


def _pct(value) -> str:
    return "-" if value is None or (isinstance(value, float) and np.isnan(value)) else f"{value:+.3f}%"


def write_report(digest: str, results: dict, moves: list) -> None:
    lines = [
        "# Research round 2 results: the pullback rules on new markets",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.round2`, judged against "
        f"[the pre-registration](round2-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "recorded before any strategy ran). Returns are per trade, net of costs; holdout = 2022 to 8 Oct 2026.",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Holdout trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | "
        "p vs random (Holm) | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        h = r["stats"]["holdout"]
        lines.append(f"| {key}: {r['name']} | {h.get('trades', 0)} | {h.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(h.get('exp_net_pct'))} | {h.get('profit_factor', np.nan):.2f} | {h.get('t_stat', np.nan):.2f} | "
                     f"{r['t_week']:.2f} | {r['holm_p']:.3f} | **{r['decision']}** |")
    lines += ["", "## Data and costs", "",
              "- Daily bars from Yahoo (adjusted), frozen in `data/round2/` with checksums, cut at 8 Oct 2026: 82 US "
              "large caps, 11 US sector SPDRs, and 4 NSE indices standing in for the ETFs that would be traded "
              f"({', '.join(f'{index} via {etf}' for index, etf in ETF_FOR_INDEX.items())}).",
              "- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.",
              f"- Round-trip costs: US {100 * COSTS['us']:.3f}%, Indian ETFs {100 * COSTS['india_etf']:.3f}% "
              f"(including 0.05% slippage per side); stress test at {STRESS}x.",
              "- Survivorship bias: today's S&P 100 members over a past decade over-represent winners. The random "
              "baseline uses the same instruments and period, so it shares that bias.",
              "",
              f"Every daily move above {MOVE_LIMIT:.0%} in the evaluation data, classified before any strategy ran "
              "(2026 moves checked against press coverage):",
              "",
              "| Instrument | Date | Close to close | Open gap | Classification |", "|---|---|---:|---:|---|"]
    lines += [f"| {symbol} | {day} | {change:+.1%} | {gap:+.1%} | {classify(symbol, day)} |"
              for symbol, day, change, gap in sorted(moves, key=lambda m: (m[1], m[0]))]
    for key, r in results.items():
        holdout_gross = r["trades"][r["trades"]["signal_date"] >= HOLDOUT_START]["gross"].mean()
        lines += ["", f"## {key}: {r['name']}", "", stats_table(r["stats"], r["cost"], r["trades"]), "",
                  f"Random baseline (random days with the same instruments, simultaneous entries kept together), "
                  f"holdout: {100 * r['random_mean']:+.3f}% gross per trade vs {100 * holdout_gross:+.3f}% for the "
                  f"strategy; p = {r['raw_p']:.3f} (Holm-adjusted {r['holm_p']:.3f}).", "",
                  "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else '**no**'} |" for c in r["checks"]]
        lines += ["", f"**Decision: {r['decision']}.**", "", "By year (all trades, net of base costs):", "",
                  "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for year, row in r["by_year"].iterrows()]
        if len(r["by_instrument"]) <= 12:
            lines += ["", "By instrument (all trades, net of base costs):", "",
                      "| Instrument | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
            lines += [f"| {symbol} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                      for symbol, row in r["by_instrument"].iterrows()]
    lines += ["", "## Informational: the Phase 3 baseline (doesn't affect the decisions)", "",
              "The same comparison with every random entry drawn independently, as in Phase 3:", "",
              "| Hypothesis | p, simultaneous entries kept together | p, independent draws |", "|---|---:|---:|"]
    lines += [f"| {key} | {r['raw_p']:.3f} | {r['independent_p']:.3f} |" for key, r in results.items()]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        h = r["stats"]["holdout"]
        print(f"{key}: holdout {h.get('trades', 0)} trades, win {h.get('win_pct', float('nan')):.1f}%, "
              f"net {h.get('exp_net_pct', float('nan')):+.3f}%/trade, t {h.get('t_stat', float('nan')):.2f}, "
              f"clustered t {r['t_week']:.2f}, Holm p {r['holm_p']:.3f} -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
