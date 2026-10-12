"""Forward test 1: the turn of the month (H11, H12) judged only on sessions after its rules were pinned
(docs/research/forward1-preregistration.md, 13 Oct 2026).

    python -m trader.research.forward1                       # fetch the latest bars, freeze them, write the status
    python -m trader.research.forward1 --as-of 2028-01-05    # the same as on that date (January: a decision look)
    python -m trader.research.forward1 --no-fetch            # use bars already frozen for the look's date

Twenty hypotheses tested on the same history make a lucky pass ever more likely, so the two strongest
near-misses are judged on data that didn't exist when their rules were fixed. Every look writes
docs/research/forward1-results.md. A look outside January, or before 2028, only reports. At the January
looks from 2028 to 2036 the pre-registered decisions apply: passing every criterion makes a candidate for
PAPER (traded only once you approve it), and from 2029 a forward expectancy of zero or below retires it.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np

from trader.config import ROOT
from trader.gate import EVIDENCE_DIR, Check, Evidence, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round2, round3, round4, round5
from trader.research.datasets import DATA_DIR, save_dataset, text_sha256
from trader.research.phase3 import holm
from trader.research.round3 import Hypothesis
from trader.research.validation import same_day_random_test

PREREGISTRATION = ROOT / "docs" / "research" / "forward1-preregistration.md"
PREREGISTRATION_SHA256 = "c30df70e859aca2548316209fa61704996dd982368c0b63176992db9ea738a52"  # 2026-10-13 00:08 IST
RESULTS = ROOT / "docs" / "research" / "forward1-results.md"
DATA = DATA_DIR / "forward1"  # one frozen copy of the bars per look date
EVIDENCE = EVIDENCE_DIR
FIRST_SIGNAL = date(2026, 10, 14)  # the first session after the pin
FETCH_FROM = date(2026, 6, 1)  # enough history for ATR(14) well before the first signal
FIRST_DECISION_YEAR, RETIRE_FROM_YEAR, LAST_YEAR = 2028, 2029, 2036
TESTS = {  # id: (name, dataset, instruments, round-trip cost), as in round 5
    "H11": ("Turn of the month, Indian indices beyond the NIFTY 50", "nse_indices_daily",
            ("^NSEBANK", "^NSMIDCP", "^CNXIT", "^CNXPHARMA"), round5.INDIA_ETF),
    "H12": ("Turn of the month, 15 country ETFs", "country_etfs_daily",
            ("EWA", "EWC", "EWG", "EWH", "EWJ", "EWL", "EWS", "EWT", "EWU", "EWW", "EWY", "EWZ", "FXI", "MCHI", "INDA"),
            round5.COUNTRY_ETF),
}
# Every daily move above 20% after the pin, classified before a look can run (none yet).
CLASSIFIED_MOVES: dict[tuple[str, str], str] = {}


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new forward test instead of editing this one.")
    return digest


def classify(symbol: str, day: date) -> str | None:
    return CLASSIFIED_MOVES.get((symbol, day.isoformat()))


def look_number(as_of: date) -> int:
    """L for the decision look in January 2027 + L (2028 is look 1, 2036 look 9); 0 for any other look."""
    return as_of.year - FIRST_DECISION_YEAR + 1 if as_of.month == 1 and FIRST_DECISION_YEAR <= as_of.year <= LAST_YEAR else 0


def cutoff(as_of: date) -> date:
    """The last session a look uses: the previous 31 December at a January look, else the day before the look."""
    return date(as_of.year - 1, 12, 31) if as_of.month == 1 else as_of - timedelta(days=1)


def decision(look: int, checks: list[Check], net_mean: float) -> str:
    """The pre-registered decision at look `look` (0: informational, nothing is decided)."""
    if look == 0:
        return "INFORMATIONAL"
    if all(c.passed for c in checks):
        return "PAPER"  # a candidate: paper traded only once you approve it
    if look >= LAST_YEAR - FIRST_DECISION_YEAR + 1 or (look >= RETIRE_FROM_YEAR - FIRST_DECISION_YEAR + 1
                                                        and not net_mean > 0):
        return "REJECTED"
    return "CONTINUE"


def fetch(as_of: date, provider=None) -> Path:
    """Download each hypothesis's daily bars and freeze them under data/forward1/<as_of>/."""
    from trader.data.providers import YahooProvider, fetch_many
    provider = provider or YahooProvider()
    directory = DATA / as_of.isoformat()
    start = datetime.combine(FETCH_FROM, time(0), timezone.utc)
    end = datetime.combine(as_of + timedelta(days=1), time(0), timezone.utc)
    for key, (_, dataset, instruments, _) in TESTS.items():
        frames, failures = fetch_many(provider, instruments, "1d", start, end)
        if failures:
            raise SystemExit(f"{key}: no data for {failures}; nothing was judged, try again later")
        save_dataset(frames, directory / dataset, source=provider.name, interval="1d", period=f"{FETCH_FROM} to {as_of}")
    return directory


def load(directory: Path, end: date) -> dict:
    """Each hypothesis's frozen bars, cleaned as in round 5; refuses while a large move is unclassified."""
    return {key: round2.load_clean(dataset, data=directory, end=end, classify_move=classify, breaks={})[0]
            for key, (_, dataset, _, _) in TESTS.items()}


def results_for(pieces: dict, as_of: date) -> dict:
    """Each hypothesis's forward trades, criteria and decision at a look on `as_of`."""
    end, look = cutoff(as_of), look_number(as_of)
    runs = {key: round4.turn_of_month_trades(pieces[key], key, FIRST_SIGNAL, end) for key in TESTS}
    raw_p = {key: same_day_random_test(pools, trades)[1] for key, (trades, pools) in runs.items() if len(trades)}
    adjusted = holm(raw_p) if raw_p else {}
    results = {}
    for key, (name, dataset, _, cost) in TESTS.items():
        trades = runs[key][0]
        r = {"name": name, "trades": trades, "cost": cost, "end": end, "look": look, "checks": [], "stats": {}}
        if len(trades) == 0:
            results[key] = {**r, "decision": "WAITING"}  # no forward trade has completed yet
            continue
        h = Hypothesis(name, dataset, FIRST_SIGNAL, FIRST_SIGNAL + (end - FIRST_SIGNAL) / 2, end, cost)
        p = min(1.0, adjusted[key] * max(look, 1))  # criterion 5's bar falls to 0.05 / L at look L
        checks, stats, _, t_week = round3.evaluate(trades, h, pieces[key], p)
        checks = [round5.thirds_check(trades, cost, FIRST_SIGNAL, end) if c.number == 9 else
                  replace(c, criterion=c.criterion.replace("stocks", "instruments").replace("stock", "instrument"),
                          value=c.value.replace("stocks", "instruments")) if c.number == 10 else c for c in checks]
        net_mean = float((trades["gross"] - cost).mean())
        results[key] = {**r, "checks": checks, "stats": stats["all"], "t_week": t_week, "raw_p": raw_p[key],
                        "holm_p": adjusted[key], "net_mean": net_mean, "decision": decision(look, checks, net_mean)}
    return results


def evidence_for(key: str, r: dict, digest: str) -> Evidence:
    """A decision look's verdict, under a new id (H11F, H12F) so round 5's records stay as they are."""
    net = r["trades"]["gross"] - r["cost"]
    return Evidence(
        strategy_id=f"{key}F", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/forward1-results.md (python -m trader.research.forward1)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{FIRST_SIGNAL} to {r['end']}", "holdout_trades": int(len(net)),
               "holdout_win_rate": float((net > 0).mean()), "holdout_mean_net": float(net.mean()),
               "holdout_sd_net": float(net.std(ddof=1)), "holdout_t_clustered": r["t_week"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": r["cost"],
               "look": r["look"]},
        preregistration_sha256=digest)


def _pct(value) -> str:
    return f"{value:+.3f}%" if value is not None and np.isfinite(value) else "-"


def write_report(as_of: date, results: dict, digest: str) -> None:
    look = look_number(as_of)
    end = next(iter(results.values()))["end"]
    lines = [
        "# Forward test 1: the turn of the month on new sessions",
        "",
        f"Look on {as_of} with data through {end}: "
        + (f"decision look {look}." if look else "informational; nothing is decided at this look.")
        + f" Judged against [the pre-registration](forward1-preregistration.md) (SHA-256 `{digest[:16]}...`, "
        f"pinned on 13 Oct 2026 before any session it judges). Only trades signalled from {FIRST_SIGNAL} count. "
        "Decision looks are each January from 2028 to 2036.",
        "",
        "| Hypothesis | Forward trades | Win rate | Net per trade | t | Cluster-robust t | p vs random (raw / Holm) | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key, r in results.items():
        s = r["stats"]
        if not s:
            lines.append(f"| {key}: {r['name']} | 0 | - | - | - | - | - | {r['decision']} |")
            continue
        lines.append(f"| {key}: {r['name']} | {s.get('trades', 0)} | {s.get('win_pct', np.nan):.1f}% | "
                     f"{_pct(s.get('exp_net_pct'))} | {s.get('t_stat', np.nan):.2f} | {r['t_week']:.2f} | "
                     f"{r['raw_p']:.3f} / {r['holm_p']:.3f} | {r['decision']} |")
    for key, r in results.items():
        if r["checks"]:
            lines += ["", f"## {key}: {r['name']}", "", "| # | Criterion | Value | Pass |", "|---|---|---|---|"]
            lines += [f"| {c.number} | {c.criterion} | {c.value} | {'yes' if c.passed else 'no'} |" for c in r["checks"]]
    lines += ["", "Statuses: WAITING, no forward trade has completed yet; INFORMATIONAL, a look that decides nothing; "
              "CONTINUE, a decision look without a pass or a retirement; PAPER, every criterion passed (a candidate, "
              "paper traded only once you approve it); REJECTED, retired."]
    RESULTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Forward test 1: H11 and H12 on sessions after 13 Oct 2026.")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="the look's date (default today)")
    parser.add_argument("--no-fetch", action="store_true", help="use the bars already frozen for the look's date")
    args = parser.parse_args(argv)
    make_console_utf8()
    digest = check_preregistration()
    directory = DATA / args.as_of.isoformat() if args.no_fetch else fetch(args.as_of)
    results = results_for(load(directory, cutoff(args.as_of)), args.as_of)
    write_report(args.as_of, results, digest)
    for key, r in results.items():
        if r["look"] and r["decision"] in ("PAPER", "REJECTED"):
            save_evidence(evidence_for(key, r, digest), EVIDENCE)
        s = r["stats"]
        print(f"{key}: {s.get('trades', 0)} forward trade(s), net {_pct(s.get('exp_net_pct'))} a trade -> {r['decision']}")
    print(f"Status written to {RESULTS}")


if __name__ == "__main__":
    main()
