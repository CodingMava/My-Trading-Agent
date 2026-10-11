"""Research round 3: confirming or retiring H6, judged against docs/research/round3-preregistration.md.

    python -m trader.research.round3        # writes docs/research/round3-results.md and the evidence files

H7 runs H6's rules on the 9 original sector SPDRs over 2000-2015, H8 on 15 iShares country ETFs over
2016-2026. Nothing is fitted, so each is judged on its whole span, and the round passes only if both do
(criterion 12). The pre-registration's SHA-256 was recorded before any strategy ran.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, ResearchThresholds, decide, research_checks, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round2
from trader.research.costs import US_COMMISSION_FREE
from trader.research.datasets import DATA_DIR, text_sha256
from trader.research.metrics import summarize
from trader.research.phase3 import holm, trading_days
from trader.research.simulator import concat_trades
from trader.research.validation import clustered_t, random_entry_test, same_day_random_test

PREREGISTRATION = ROOT / "docs" / "research" / "round3-preregistration.md"
PREREGISTRATION_SHA256 = "78c1275b406b9bb9a65f3735b34ec2543a62b60c26a9338ec689a045cbe237d4"  # 2026-10-09 23:10 IST
RESULTS = ROOT / "docs" / "research" / "round3-results.md"
DATA = DATA_DIR / "round3"
STRESS = 1.5
MIN_CLUSTERED_T = 2.0
# Criteria 1-7, 9 and 10 exactly as pre-registered (the same thresholds as rounds 1 and 2), written out so
# later changes to config/gate.toml can't change how these hypotheses were judged.
PREREGISTERED = ResearchThresholds(min_trades=50, min_win_rate=0.50, min_profit_factor=1.3, min_t_stat=2.0,
                                   max_p_value=0.05, cost_stress=1.5, max_loss_to_win=1.5, worst_trade_r=-3.0,
                                   min_positive_years=0.70, min_trades_per_year=10, min_breadth=0.60,
                                   min_trades_per_stock=5)


@dataclass(frozen=True)
class Hypothesis:
    name: str
    dataset: str
    start: date
    split: date  # the first day of the span's second half
    end: date
    cost: float  # round trip, as a fraction


HYPOTHESES = {
    "H7": Hypothesis("Oversold pullback in an uptrend, US sector SPDRs, 2000-2015", "sector_spdrs_daily",
                     date(2000, 1, 1), date(2008, 1, 1), date(2015, 12, 31), US_COMMISSION_FREE.round_trip(10_000)),
    "H8": Hypothesis("Oversold pullback in an uptrend, iShares country ETFs, 2016-2026", "country_etfs_daily",
                     date(2016, 1, 1), date(2021, 1, 1), date(2026, 10, 8),
                     US_COMMISSION_FREE.with_slippage(0.0005).round_trip(10_000)),
}
# Every daily move above 20% in the evaluation data, classified before any strategy ran.
CLASSIFIED_MOVES = {
    ("XLF", "2008-09-19"): "Genuine: US short-selling ban and bank rescue plan",
    ("EWZ", "2020-03-16"): "Genuine: COVID-19 crash",
    ("FXI", "2022-03-16"): "Genuine: China's pledge to support its markets",
    ("MCHI", "2022-03-16"): "Genuine: China's pledge to support its markets",
}


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def classify(symbol: str, day: date) -> str | None:
    return CLASSIFIED_MOVES.get((symbol, day.isoformat()))


def halves_check(trades: pd.DataFrame, cost: float, split: date) -> Check:
    """Criterion 8 for a span with no design period: each half must be profitable on its own."""
    halves = [100 * (part["gross"] - cost).mean() if len(part) else np.nan
              for part in (trades[trades["signal_date"] < split], trades[trades["signal_date"] >= split])]
    return Check(8, "Expectancy above 0 in each half of the span", f"{halves[0]:+.3f}% / {halves[1]:+.3f}%",
                 all(value > 0 for value in halves))


def evaluate(trades: pd.DataFrame, h: Hypothesis, pieces: dict, p_holm: float, several_instruments: bool = True):
    """Criteria 1-11 on the whole span: 1-7, 9 and 10 through the shared gate (the whole span as its
    'holdout'; 10, breadth across instruments, only with several), 8 replaced by the halves check, 11 the
    cluster-robust t."""
    days = trading_days(pieces, h.start, h.end)
    checks, details = research_checks(trades, h.cost, h.start, {"design": [], "holdout": days, "all": days},
                                      p_holm, several_instruments, PREREGISTERED)
    checks = [halves_check(trades, h.cost, h.split) if c.number == 8
              else replace(c, criterion=c.criterion.replace(" holdout", "")) if c.number == 1 else c for c in checks]
    t_week = clustered_t(trades["gross"] - h.cost, [round2.signal_week(d) for d in trades["signal_date"]])
    checks.append(Check(11, f"Cluster-robust t-statistic (signal weeks as clusters) at least {MIN_CLUSTERED_T}",
                        f"{t_week:.2f}", bool(t_week >= MIN_CLUSTERED_T)))
    first, second = trades[trades["signal_date"] < h.split], trades[trades["signal_date"] >= h.split]
    stats = {"first": summarize(first, h.cost, trading_days(pieces, h.start, h.split - timedelta(days=1))),
             "second": summarize(second, h.cost, trading_days(pieces, h.split, h.end)),
             "all": details["stats"]["holdout"]}
    return checks, stats, details["by_year"], t_week


def join_verdicts(results: dict) -> None:
    """Criterion 12 (the round is one test: each hypothesis also needs the other to pass 1-11), then the
    decision for each."""
    passed = {key: all(c.passed for c in r["checks"]) for key, r in results.items()}
    for key, r in results.items():
        other = next(k for k in results if k != key)
        r["checks"].append(Check(12, "The other hypothesis of this round also passes criteria 1-11",
                                 f"{other} {'passes' if passed[other] else 'fails'}", passed[other]))
        r["decision"] = decide(r["checks"])


def sector_record(h7_trades: pd.DataFrame) -> dict:
    """Informational: the sector SPDRs under these rules, 2000-2026 (H7's trades, then round 2's H6)."""
    pieces, _ = round2.load_clean("us_sector_etfs_daily")
    h6_trades, _ = round2.pullback_trades(pieces, "H6")
    trades = concat_trades([h7_trades, h6_trades])
    cost = round2.COSTS["us"]
    net = trades["gross"] - cost
    return {"trades": len(net), "win_pct": 100 * (net > 0).mean(), "exp_net_pct": 100 * net.mean(),
            "t_stat": net.mean() / (net.std(ddof=1) / np.sqrt(len(net))),
            "t_week": clustered_t(net, [round2.signal_week(d) for d in trades["signal_date"]])}


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    """The machine-readable verdict the registry checks. The whole span plays the holdout's part."""
    h, net = HYPOTHESES[key], r["trades"]["gross"] - r["cost"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round3-results.md (python -m trader.research.round3)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{h.start} to {h.end}", "holdout_trades": int(len(net)),
               "holdout_win_rate": float((net > 0).mean()), "holdout_mean_net": float(net.mean()),
               "holdout_sd_net": float(net.std(ddof=1)), "holdout_profit_factor": float(r["stats"]["all"]["profit_factor"]),
               "holdout_t": float(r["stats"]["all"]["t_stat"]), "holdout_t_clustered": r["t_week"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "p_random_independent": r["independent_p"],
               "round_trip_cost": r["cost"]},
        preregistration_sha256=digest)


def run(write: bool = True) -> dict:
    make_console_utf8()
    digest = check_preregistration()
    loaded, runs = {}, {}
    for key, h in HYPOTHESES.items():
        loaded[key] = round2.load_clean(h.dataset, data=DATA, end=h.end, classify_move=classify, breaks={})
        runs[key] = round2.pullback_trades(loaded[key][0], key, start=h.start, end=h.end, pool_start=h.start)

    baselines, independent = {}, {}
    for key, (trades, pools) in runs.items():
        baselines[key] = same_day_random_test(pools, trades)
        arrays = {s: p.to_numpy() for s, p in pools.items()}
        independent[key] = random_entry_test(arrays, trades["ticker"], trades["gross"])[1]
    raw_p = {key: p for key, (_, p) in baselines.items()}
    adjusted = holm(raw_p)

    results = {}
    for key, h in HYPOTHESES.items():
        trades = runs[key][0]
        checks, stats, by_year, t_week = evaluate(trades, h, loaded[key][0], adjusted[key])
        results[key] = {"name": h.name, "trades": trades, "cost": h.cost, "stats": stats, "checks": checks,
                        "by_year": by_year, "raw_p": raw_p[key], "holm_p": adjusted[key],
                        "random_mean": baselines[key][0], "independent_p": independent[key], "t_week": t_week,
                        "by_instrument": round2.by_instrument(trades, h.cost)}
    join_verdicts(results)
    if write:
        moves = [move for key in HYPOTHESES for move in loaded[key][1]]
        write_report(digest, results, moves, sector_record(results["H7"]["trades"]))
        for key, result in results.items():
            save_evidence(evidence_for(key, result, digest))
    return results


def _pct(value) -> str:
    return "-" if value is None or (isinstance(value, float) and np.isnan(value)) else f"{value:+.3f}%"


def stats_table(stats: dict, h: Hypothesis) -> str:
    lines = ["| Period | Trades | Win rate | Avg win | Avg loss | Profit factor | Net per trade | t | Max drawdown | Sharpe |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for label, key in ((f"{h.start.year}-{h.split.year - 1}", "first"), (f"{h.split.year}-{h.end.year}", "second"),
                       (f"All {h.start.year}-{h.end.year}", "all")):
        s = stats[key]
        if not s.get("trades"):
            lines.append(f"| {label} | 0 | - | - | - | - | - | - | - | - |")
            continue
        lines.append(f"| {label} | {s['trades']} | {s['win_pct']:.1f}% | {s['avg_win_pct']:+.2f}% | {s['avg_loss_pct']:+.2f}% | "
                     f"{s['profit_factor']:.2f} | {s['exp_net_pct']:+.3f}% | {s['t_stat']:.2f} | "
                     f"{s['max_dd_units']:.1f}{s['unit']} | {s['sharpe']:.2f} |")
    return "\n".join(lines)


def write_report(digest: str, results: dict, moves: list, record: dict) -> None:
    confirmed = all(r["decision"] == "PAPER" for r in results.values())
    lines = [
        "# Research round 3 results: confirming or retiring H6",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.round3`, judged against "
        f"[the pre-registration](round3-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "recorded before any strategy ran). Returns are per trade, net of costs, over each hypothesis's whole span.",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | Cluster-robust t | p vs random (Holm) | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        s = r["stats"]["all"]
        lines.append(f"| {key}: {r['name']} | {s.get('trades', 0)} | {s.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(s.get('exp_net_pct'))} | {s.get('profit_factor', np.nan):.2f} | {s.get('t_stat', np.nan):.2f} | "
                     f"{r['t_week']:.2f} | {r['holm_p']:.3f} | **{r['decision']}** |")
    lines += ["", ("**H6 is confirmed:** its rules may be paper traded on both sets of ETFs once the paper engine "
                   "supports US markets." if confirmed else
                   "**H6 is not confirmed.** As pre-registered, the pullback rules are retired: no variant of them "
                   "is tested again in this project."),
              "", "## Data and costs", "",
              "- Daily bars from Yahoo (adjusted), frozen in `data/round3/` with checksums: the 9 original sector "
              "SPDRs cut at 31 Dec 2015 (H7), and 15 iShares country ETFs cut at 8 Oct 2026 (H8).",
              "- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.",
              f"- Round-trip costs: H7 {100 * HYPOTHESES['H7'].cost:.3f}%, H8 {100 * HYPOTHESES['H8'].cost:.3f}% "
              f"(0.05% slippage per side); stress test at {STRESS}x.",
              "",
              f"Every daily move above {round2.MOVE_LIMIT:.0%} in the evaluation data, classified before any strategy ran:",
              "",
              "| Instrument | Date | Close to close | Open gap | Classification |", "|---|---|---:|---:|---|"]
    lines += [f"| {symbol} | {day} | {change:+.1%} | {gap:+.1%} | {classify(symbol, day)} |"
              for symbol, day, change, gap in sorted(moves, key=lambda m: (m[1], m[0]))]
    for key, r in results.items():
        h = HYPOTHESES[key]
        lines += ["", f"## {key}: {r['name']}", "", stats_table(r["stats"], h), "",
                  f"Random baseline (random days with the same instruments, simultaneous entries kept together): "
                  f"{100 * r['random_mean']:+.3f}% gross per trade vs {100 * r['trades']['gross'].mean():+.3f}% for "
                  f"the strategy; p = {r['raw_p']:.3f} (Holm-adjusted {r['holm_p']:.3f}).", "",
                  "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else '**no**'} |" for c in r["checks"]]
        lines += ["", f"**Decision: {r['decision']}.**", "", "By year (net of base costs):", "",
                  "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for year, row in r["by_year"].iterrows()]
        lines += ["", "By instrument (net of base costs):", "",
                  "| Instrument | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {symbol} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for symbol, row in r["by_instrument"].iterrows()]
    lines += ["", "## Informational (doesn't affect the decisions)", "",
              "The same comparison with every random entry drawn independently, as in Phase 3:", "",
              "| Hypothesis | p, simultaneous entries kept together | p, independent draws |", "|---|---:|---:|"]
    lines += [f"| {key} | {r['raw_p']:.3f} | {r['independent_p']:.3f} |" for key, r in results.items()]
    lines += ["", "The sector SPDRs under these rules, 2000-2026 (H7's trades, then round 2's H6 on the 11 SPDRs), "
                  f"net of {100 * round2.COSTS['us']:.3f}% per trade: {record['trades']} trades, {record['win_pct']:.1f}% "
                  f"winners, {record['exp_net_pct']:+.3f}% per trade, t {record['t_stat']:.2f}, cluster-robust t "
                  f"{record['t_week']:.2f}."]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        s = r["stats"]["all"]
        print(f"{key}: {s.get('trades', 0)} trades, win {s.get('win_pct', float('nan')):.1f}%, "
              f"net {s.get('exp_net_pct', float('nan')):+.3f}%/trade, t {s.get('t_stat', float('nan')):.2f}, "
              f"clustered t {r['t_week']:.2f}, Holm p {r['holm_p']:.3f} -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
