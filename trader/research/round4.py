"""Research round 4: the turn-of-the-month effect, judged against docs/research/round4-preregistration.md.

    python -m trader.research.round4        # writes docs/research/round4-results.md and the evidence files

H9 holds SPY and H10 the NIFTY 50 (standing in for NIFTYBEES) over every turn of the month. Nothing is
fitted, so each is judged on its whole span, and each stands on its own. The pre-registration's SHA-256
was recorded before the rule ran on any data.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round2, round3
from trader.research.costs import US_COMMISSION_FREE, ZERODHA_ETF_DELIVERY
from trader.research.datasets import DATA_DIR, text_sha256
from trader.research.phase3 import base_symbol, holm, in_window
from trader.research.round3 import Hypothesis
from trader.research.simulator import concat_trades, select_trades, simulate, trade_rows
from trader.research.validation import same_day_random_test
from trader.strategies.swing import turn_of_month_rules, turn_of_month_signals

PREREGISTRATION = ROOT / "docs" / "research" / "round4-preregistration.md"
PREREGISTRATION_SHA256 = "3346175fbab3abd907a0ba6aa80fa5f14095bb614a791fab0daf6125ec2cccca"  # 2026-10-11 16:22 IST
RESULTS = ROOT / "docs" / "research" / "round4-results.md"
DATA = DATA_DIR / "round4"
HYPOTHESES = {
    "H9": Hypothesis("Turn of the month, S&P 500 (SPY)", "us_spy_daily", date(1993, 2, 1), date(2010, 1, 1),
                     date(2026, 10, 8), US_COMMISSION_FREE.round_trip(10_000)),
    "H10": Hypothesis("Turn of the month, NIFTY 50 (via NIFTYBEES)", "nse_nifty_daily", date(2008, 1, 1),
                      date(2017, 1, 1), date(2026, 10, 8), ZERODHA_ETF_DELIVERY.round_trip(100_000)),
}
CLASSIFIED_MOVES: dict[tuple[str, str], str] = {}  # the data-quality report found no daily move above 20%


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def classify(symbol: str, day: date) -> str | None:
    return CLASSIFIED_MOVES.get((symbol, day.isoformat()))


def turn_of_month_trades(pieces: dict[str, pd.DataFrame], rule: str, start: date, end: date):
    """Trades signalled from `start` to `end`, plus the random baseline's pools: the outcome of the same
    four-day hold with the same stop, entered on any day of the span."""
    frames, pools = [], {}
    for name, bars in pieces.items():
        signals = turn_of_month_signals(bars)
        out = simulate(bars, "long", turn_of_month_rules(), "next_open", stop=signals.stop, exit_signal=signals.exit)
        symbol = base_symbol(name)
        frames.append(trade_rows(symbol, bars.index, select_trades(signals.entry, out), out, "long", rule))
        dates = np.asarray(bars.index.date)
        pooled = np.isfinite(signals.stop) & ~np.isnan(out.gross) & (dates >= start) & (dates <= end)
        pools.setdefault(symbol, []).append(pd.Series(out.gross[pooled], index=dates[pooled]))
    pools = {symbol: pd.concat(parts) for symbol, parts in pools.items()}
    return in_window(concat_trades(frames), start, end), pools


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    """The machine-readable verdict the registry checks. The whole span plays the holdout's part."""
    h, net = HYPOTHESES[key], r["trades"]["gross"] - r["cost"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round4-results.md (python -m trader.research.round4)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{h.start} to {h.end}", "holdout_trades": int(len(net)),
               "holdout_win_rate": float((net > 0).mean()), "holdout_mean_net": float(net.mean()),
               "holdout_sd_net": float(net.std(ddof=1)), "holdout_profit_factor": float(r["stats"]["all"]["profit_factor"]),
               "holdout_t": float(r["stats"]["all"]["t_stat"]), "holdout_t_clustered": r["t_week"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": r["cost"]},
        preregistration_sha256=digest)


def run(write: bool = True) -> dict:
    make_console_utf8()
    digest = check_preregistration()
    loaded, runs = {}, {}
    for key, h in HYPOTHESES.items():
        loaded[key] = round2.load_clean(h.dataset, data=DATA, end=h.end, classify_move=classify, breaks={})
        runs[key] = turn_of_month_trades(loaded[key][0], key, h.start, h.end)
    baselines = {key: same_day_random_test(pools, trades) for key, (trades, pools) in runs.items()}
    raw_p = {key: p for key, (_, p) in baselines.items()}
    adjusted = holm(raw_p)

    results = {}
    for key, h in HYPOTHESES.items():
        trades = runs[key][0]
        checks, stats, by_year, t_week = round3.evaluate(trades, h, loaded[key][0], adjusted[key],
                                                         several_instruments=False)
        results[key] = {"name": h.name, "trades": trades, "cost": h.cost, "stats": stats, "checks": checks,
                        "by_year": by_year, "decision": decide(checks), "raw_p": raw_p[key], "holm_p": adjusted[key],
                        "random_mean": baselines[key][0], "t_week": t_week}
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
        "# Research round 4 results: the turn-of-the-month effect",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.round4`, judged against "
        f"[the pre-registration](round4-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "recorded before the rule ran on any data). Returns are per trade, net of costs, over each hypothesis's "
        "whole span.",
        "",
        "## Verdict",
        "",
        "| Hypothesis | Trades | Win rate | Net per trade | Profit factor | t | p vs random (Holm) | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        s = r["stats"]["all"]
        lines.append(f"| {key}: {r['name']} | {s.get('trades', 0)} | {s.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(s.get('exp_net_pct'))} | {s.get('profit_factor', np.nan):.2f} | {s.get('t_stat', np.nan):.2f} | "
                     f"{r['holm_p']:.3f} | **{r['decision']}** |")
    lines += ["", "## Data and costs", "",
              "- Daily bars from Yahoo (adjusted), frozen in `data/round4/` with checksums, cut at 8 Oct 2026: SPY "
              "from its listing, and the NIFTY 50 index from Yahoo's first bar (17 Sep 2007), standing in for NIFTYBEES.",
              "- Bars without prices and Yahoo's flat zero-volume placeholder bars were dropped.",
              f"- Round-trip costs: H9 {100 * HYPOTHESES['H9'].cost:.3f}%, H10 {100 * HYPOTHESES['H10'].cost:.3f}%; "
              "stress test at 1.5x.",
              f"- Daily moves above {round2.MOVE_LIMIT:.0%}: "
              + ("; ".join(f"{s} {d} ({classify(s, d)})" for s, d, _, _ in moves) if moves else "none in either series.")]
    for key, r in results.items():
        h = HYPOTHESES[key]
        lines += ["", f"## {key}: {r['name']}", "", round3.stats_table(r["stats"], h), "",
                  f"Random baseline (the same four-day hold and stop entered on random days of the span): "
                  f"{100 * r['random_mean']:+.3f}% gross per trade vs {100 * r['trades']['gross'].mean():+.3f}% at the "
                  f"turn of the month; p = {r['raw_p']:.3f} (Holm-adjusted {r['holm_p']:.3f}).", "",
                  "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else '**no**'} |" for c in r["checks"]]
        lines += ["", f"**Decision: {r['decision']}.**", "", "By year (net of base costs):", "",
                  "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for year, row in r["by_year"].iterrows()]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        s = r["stats"]["all"]
        print(f"{key}: {s.get('trades', 0)} trades, win {s.get('win_pct', float('nan')):.1f}%, "
              f"net {s.get('exp_net_pct', float('nan')):+.3f}%/trade, t {s.get('t_stat', float('nan')):.2f}, "
              f"random {100 * r['random_mean']:+.3f}% vs {100 * r['trades']['gross'].mean():+.3f}% gross, "
              f"Holm p {r['holm_p']:.3f} -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
