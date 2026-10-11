"""Research round 5: a batch of documented monthly effects, judged against
docs/research/round5-preregistration.md.

    python -m trader.research.round5        # writes docs/research/round5-results.md and the evidence files

H11 and H12 hold indices over the turn of the month (India beyond the NIFTY 50; 15 countries); H13 and
H14 buy last year's three strongest sector or country ETFs each month. Nothing is fitted, so each is
judged on its whole span, and each stands on its own. The pre-registration's SHA-256 was recorded before
any of these rules ran on this data.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round2, round3, round4
from trader.research.costs import US_COMMISSION_FREE, ZERODHA_ETF_DELIVERY
from trader.research.datasets import DATA_DIR
from trader.research.phase3 import base_symbol, holm, in_window, selection_test
from trader.research.round3 import Hypothesis
from trader.research.validation import same_day_random_test
from trader.strategies.swing import MomentumParams, momentum_panel, momentum_trades, select_top

PREREGISTRATION = ROOT / "docs" / "research" / "round5-preregistration.md"
PREREGISTRATION_SHA256 = "2a2526fa940f65a30a25b2b0a6c7b27680ffca0df5a8fd783fe9e6219cefaca7"  # 2026-10-11 17:16 IST
RESULTS = ROOT / "docs" / "research" / "round5-results.md"
END = date(2026, 10, 8)
MOMENTUM_TOP_3 = MomentumParams(top_n=3)


@dataclass(frozen=True)
class Test:
    hypothesis: Hypothesis
    effect: str  # "turn of the month" or "momentum"
    data: Path
    traded_as: str


def _h(name, dataset, start, cost):
    return Hypothesis(name, dataset, start, start + (END - start) / 2, END, cost)  # split: the span's midpoint


INDIA_ETF = ZERODHA_ETF_DELIVERY.with_slippage(0.0005).round_trip(100_000)
COUNTRY_ETF = US_COMMISSION_FREE.with_slippage(0.0005).round_trip(10_000)
SECTOR_ETF = US_COMMISSION_FREE.round_trip(10_000)
TESTS = {
    "H11": Test(_h("Turn of the month, Indian indices beyond the NIFTY 50", "nse_indices_daily", date(2008, 1, 1), INDIA_ETF), "turn of the month", DATA_DIR / "round5",
                "BANKBEES, JUNIORBEES, ITBEES, PHARMABEES"),
    "H12": Test(_h("Turn of the month, 15 country ETFs", "country_etfs_daily", date(2001, 1, 1), COUNTRY_ETF),
                "turn of the month", DATA_DIR / "round5", "the ETFs themselves"),
    "H13": Test(_h("Momentum, top 3 of the 9 US sector SPDRs monthly", "sector_spdrs_daily", date(2000, 1, 1), SECTOR_ETF), "momentum", DATA_DIR / "round3", "the ETFs themselves"),
    "H14": Test(_h("Momentum, top 3 of 15 country ETFs monthly", "country_etfs_daily", date(2001, 1, 1), COUNTRY_ETF),
                "momentum", DATA_DIR / "round5", "the ETFs themselves"),
}
# Every daily move above 20% in the data, classified before any strategy ran.
_RESCUE = "Genuine: coordinated bank rescues, worldwide rally"
CLASSIFIED_MOVES = {
    ("EWH", "1997-10-28"): "Genuine: Asian financial crisis, the rebound after the 27 Oct 1997 crash",
    ("EWY", "2008-09-19"): "Genuine: US short-selling ban and bank rescue plan",
    ("XLF", "2008-09-19"): "Genuine: US short-selling ban and bank rescue plan",
    ("EWA", "2008-10-13"): _RESCUE, ("EWW", "2008-10-13"): _RESCUE, ("EWY", "2008-10-13"): _RESCUE,
    ("EWZ", "2008-10-13"): _RESCUE, ("FXI", "2008-10-13"): _RESCUE,
    ("EWY", "2008-10-28"): "Genuine: worldwide rally (US stocks +11%)",
    ("FXI", "2008-10-28"): "Genuine: worldwide rally (US stocks +11%)",
    ("EWY", "2008-10-30"): "Genuine: Fed currency swap lines with Korea and others",
    ("XLE", "2020-03-09"): "Genuine: COVID-19 crash (oil price war)",
    ("EWZ", "2020-03-16"): "Genuine: COVID-19 crash",
    ("FXI", "2022-03-16"): "Genuine: China's pledge to support its markets",
    ("MCHI", "2022-03-16"): "Genuine: China's pledge to support its markets",
}


def check_preregistration() -> str:
    digest = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was recorded (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def classify(symbol: str, day: date) -> str | None:
    return CLASSIFIED_MOVES.get((symbol, day.isoformat()))


def thirds_check(trades: pd.DataFrame, cost: float, start: date, end: date) -> Check:
    """Criterion 9 of this round: expectancy above zero in each third of the span."""
    span = (end - start).days
    edges = [start + timedelta(days=round(span * k / 3)) for k in range(4)]
    edges[-1] = end + timedelta(days=1)
    means = []
    for low, high in zip(edges[:-1], edges[1:]):
        part = trades[(trades["signal_date"] >= low) & (trades["signal_date"] < high)]
        means.append(100 * (part["gross"] - cost).mean() if len(part) else np.nan)
    return Check(9, "Expectancy above 0 in each third of the span", " / ".join(f"{m:+.3f}%" for m in means),
                 all(m > 0 for m in means))


def _instruments(text: str) -> str:
    return text.replace("stocks", "instruments").replace("stock", "instrument")


def momentum_run(pieces: dict, rule: str, start: date, end: date):
    """H3's machinery with the top 3: trades in the span, plus the month-by-month panel for the baseline."""
    panel = momentum_panel(pieces, MOMENTUM_TOP_3)
    panel["symbol"] = panel["symbol"].map(base_symbol)
    panel["selected"] = select_top(panel, MOMENTUM_TOP_3)
    panel["signal_date"] = [stamp.date() for stamp in panel["month_end"]]
    trades = in_window(momentum_trades(panel, panel["selected"].to_numpy(), rule), start, end)
    return trades, panel[(panel["signal_date"] >= start) & (panel["signal_date"] <= end)]


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    h, net = TESTS[key].hypothesis, r["trades"]["gross"] - r["cost"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round5-results.md (python -m trader.research.round5)",
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
    loaded, runs, baselines = {}, {}, {}
    for key, test in TESTS.items():
        h = test.hypothesis
        loaded[key] = round2.load_clean(h.dataset, data=test.data, end=END, classify_move=classify, breaks={})
        if test.effect == "turn of the month":
            trades, pools = round4.turn_of_month_trades(loaded[key][0], key, h.start, h.end)
            baselines[key] = same_day_random_test(pools, trades)
        else:
            trades, panel = momentum_run(loaded[key][0], key, h.start, h.end)
            baselines[key] = selection_test(panel)
        runs[key] = trades
    raw_p = {key: p for key, (_, p) in baselines.items()}
    adjusted = holm(raw_p)

    results = {}
    for key, test in TESTS.items():
        h, trades = test.hypothesis, runs[key]
        checks, stats, by_year, t_week = round3.evaluate(trades, h, loaded[key][0], adjusted[key])
        years = by_year[by_year["trades"] >= 10]
        checks = [thirds_check(trades, h.cost, h.start, h.end) if c.number == 9 else c for c in checks]
        checks = [replace(c, criterion=_instruments(c.criterion), value=_instruments(c.value)) if c.number == 10 else c
                  for c in checks]
        results[key] = {"name": h.name, "trades": trades, "cost": h.cost, "stats": stats, "checks": checks,
                        "by_year": by_year, "decision": decide(checks), "raw_p": raw_p[key], "holm_p": adjusted[key],
                        "random_mean": baselines[key][0], "t_week": t_week,
                        "positive_years": float((years["exp_net_pct"] > 0).mean()) if len(years) else np.nan,
                        "by_instrument": round2.by_instrument(trades, h.cost)}
    if write:
        moves = [move for key in TESTS for move in loaded[key][1]]
        write_report(digest, results, sorted(set(moves), key=lambda m: (m[1], m[0])))
        for key, result in results.items():
            save_evidence(evidence_for(key, result, digest))
    return results


def _pct(value) -> str:
    return "-" if value is None or (isinstance(value, float) and np.isnan(value)) else f"{value:+.3f}%"


def write_report(digest: str, results: dict, moves: list) -> None:
    lines = [
        "# Research round 5 results: a batch of documented monthly effects",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `python -m trader.research.round5`, judged against "
        f"[the pre-registration](round5-preregistration.md) (SHA-256 `{digest[:16]}...`, unchanged since it was "
        "recorded before these rules ran on this data). Returns are per trade, net of costs, over each "
        "hypothesis's whole span.",
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
    lines += ["", "## Data and costs", "",
              "- Daily bars from Yahoo (adjusted), frozen with checksums (`data/round5/`; the sector SPDRs from "
              "`data/round3/`), cut at 8 Oct 2026. Bars without prices and flat zero-volume placeholders were dropped.",
              f"- Round-trip costs: Indian ETFs {100 * INDIA_ETF:.3f}%, country ETFs {100 * COUNTRY_ETF:.3f}%, sector "
              f"SPDRs {100 * SECTOR_ETF:.3f}%; stress test at 1.5x.",
              "", f"Every daily move above {round2.MOVE_LIMIT:.0%} in the data, classified before any strategy ran:", "",
              "| Instrument | Date | Close to close | Open gap | Classification |", "|---|---|---:|---:|---|"]
    lines += [f"| {s} | {d} | {c:+.1%} | {g:+.1%} | {classify(s, d)} |" for s, d, c, g in moves]
    for key, r in results.items():
        test = TESTS[key]
        lines += ["", f"## {key}: {r['name']}", "", f"Traded as: {test.traded_as}.", "",
                  round3.stats_table(r["stats"], test.hypothesis), "",
                  (f"Random baseline (the same four-day hold and stop entered on random days, simultaneous entries kept "
                   f"together): {100 * r['random_mean']:+.3f}% gross per trade" if test.effect == "turn of the month" else
                   f"Random baseline (three ETFs picked at random from the same month's eligible list): "
                   f"{100 * r['random_mean']:+.3f}% gross per trade")
                  + f" vs {100 * r['trades']['gross'].mean():+.3f}% for the strategy; p = {r['raw_p']:.3f} "
                    f"(Holm-adjusted {r['holm_p']:.3f}).", "",
                  "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else '**no**'} |" for c in r["checks"]]
        lines += ["", f"**Decision: {r['decision']}.**", "",
                  f"Informational: {r['positive_years']:.0%} of years (10+ trades) were profitable, the measure rounds 1-4 "
                  "required to be at least 70%.", "", "By year (net of base costs):", "",
                  "| Year | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {year} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for year, row in r["by_year"].iterrows()]
        lines += ["", "By instrument (net of base costs):", "",
                  "| Instrument | Trades | Win rate | Net per trade |", "|---|---:|---:|---:|"]
        lines += [f"| {symbol} | {int(row.trades)} | {row.win_pct:.1f}% | {row.exp_net_pct:+.3f}% |"
                  for symbol, row in r["by_instrument"].iterrows()]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = run()
    for key, r in results.items():
        s = r["stats"]["all"]
        print(f"{key}: {s.get('trades', 0)} trades, win {s.get('win_pct', float('nan')):.1f}%, "
              f"net {s.get('exp_net_pct', float('nan')):+.3f}%/trade, t {s.get('t_stat', float('nan')):.2f}, "
              f"clustered t {r['t_week']:.2f}, random {100 * r['random_mean']:+.3f}% vs "
              f"{100 * r['trades']['gross'].mean():+.3f}% gross, Holm p {r['holm_p']:.3f} -> {r['decision']}")
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    print(f"Report written to {RESULTS}")


if __name__ == "__main__":
    main()
