"""Research round 11: option-implied information (O2: options cheap relative to realized volatility) on round 8's
survivorship-free NSE universe, judged against docs/research/round11-preregistration.md.

    python -m trader.research.round11 --stage 1    # development (2008 - May 2013): writes docs/research/round11-stage1.md
    python -m trader.research.round11 --stage 2    # the decision, once: round11-results.md and O2's evidence

The universe, signal dates, entry rule, exits and cost model are round 8's (reused, not changed). New here: NSE's F&O
files (stored outside OneDrive, see trader/research/nse_fo.py), Black-Scholes implied volatilities from traded options,
total returns (dividends under 5% added), a 15% stop and costs at the engine's Rs 33,333 position (round 10's).
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import nse_fo, round8, round10
from trader.research import nse_bhavcopy as nb
from trader.research.datasets import text_sha256

PREREGISTRATION = ROOT / "docs" / "research" / "round11-preregistration.md"
PREREGISTRATION_SHA256 = "a2b4c2b8efb5bbf4394b0fb6cb1dd7381b82edc08accdd6dc0c23851110a5723"  # pinned 2026-10-18 23:45 IST
FO_MANIFEST_SHA256 = "d99ffe9ced87abf1d504fa83b6dd8e61cd42a475b690c01713d0f6e996bd2d90"
COMPACT_MANIFEST = nse_fo.COMPACT / "compact_manifest.json"
COMPACT_MANIFEST_SHA256 = "aa94ce3b6452a7dacccc6a20804f9a5d6d5c09e214a38072fe9c4e80b4bc7fdc"
STAGE1_RESULTS = ROOT / "docs" / "research" / "round11-stage1.md"
RESULTS = ROOT / "docs" / "research" / "round11-results.md"
TESTS_IN_PROJECT = 67
CROSS_ROUND_ALPHA = 0.05 / TESTS_IN_PROJECT
STOP, PICKS, RATE, MIN_DAYS = 0.15, 5, 0.065, 7
ATM_BAND = (0.97, 1.03)
RV_RETURNS, RV_WINDOW = 21, 41
SPANS = {1: (date(2008, 1, 31), round8.STAGE1_LAST_SIGNAL), 2: (round8.STAGE2_FIRST_SIGNAL, round8.STAGE2_LAST_SIGNAL)}
DRAWS, SEED = 20_000, 11
NAME = "O2: the 5 stocks whose options are cheapest relative to realized volatility, ranks 1-300, monthly, 15% stop"


# ------------------------------------------------------------------------------------------------- pins
def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


def check_data() -> None:
    for path, expected in ((nse_fo.MANIFEST, FO_MANIFEST_SHA256), (COMPACT_MANIFEST, COMPACT_MANIFEST_SHA256)):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise SystemExit(f"{path} changed (sha256 {digest})")
    for name, sha in json.loads(COMPACT_MANIFEST.read_text(encoding="utf-8")).items():
        if hashlib.sha256((nse_fo.COMPACT / name).read_bytes()).hexdigest() != sha:
            raise SystemExit(f"{name} changed since it was built")


# ------------------------------------------------------------------------------------- option pricing
def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(S: float, K: float, T: float, sigma: float, call: bool) -> float:
    d1 = (math.log(S / K) + (RATE + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if call:
        return S * _cdf(d1) - K * math.exp(-RATE * T) * _cdf(d2)
    return K * math.exp(-RATE * T) * _cdf(-d2) - S * _cdf(-d1)


def implied_vol(price: float, S: float, K: float, T: float, call: bool) -> float:
    """("Implied volatility") Bisection on [0.01, 3.0]; NaN when the price isn't above intrinsic value (strike
    discounted) or isn't below the underlying (calls) or the strike (puts)."""
    intrinsic = max(0.0, (S - K * math.exp(-RATE * T)) if call else (K * math.exp(-RATE * T) - S))
    if not price > intrinsic or not price < (S if call else K):
        return math.nan
    lo, hi = 0.01, 3.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def atm_iv(chain: pd.DataFrame, S: float, day: date) -> float:
    """("ATM strike") One stock's traded options on `day`: the nearest expiry at least 7 days away; among strikes where both
    a call and a put traded, the one nearest S with strike / S in [0.97, 1.03]; the mean of their IVs."""
    chain = chain[(chain["contracts"] > 0) & (chain["close"] > 0)]
    expiries = sorted(e for e in chain["expiry"].unique() if (e - day).days >= MIN_DAYS)
    if not expiries or not S > 0:
        return math.nan
    chain = chain[chain["expiry"] == expiries[0]]
    T = (expiries[0] - day).days / 365
    calls = chain[chain["kind"] == "CE"].groupby("strike")["close"].first()
    puts = chain[chain["kind"] == "PE"].groupby("strike")["close"].first()
    both = sorted((k for k in set(calls.index) & set(puts.index) if ATM_BAND[0] <= k / S <= ATM_BAND[1]),
                  key=lambda k: (abs(k / S - 1), k))
    if not both:
        return math.nan
    k = both[0]
    c, p = implied_vol(float(calls[k]), S, k, T, True), implied_vol(float(puts[k]), S, k, T, False)
    return 0.5 * (c + p) if math.isfinite(c) and math.isfinite(p) else math.nan


def realized_vol(sec: round8.Security, i: int) -> float:
    """("Realized volatility") The last 21 log returns of the adjusted close over the stock's last 22 rows within the 41
    sessions ending at i, annualised; NaN with fewer than 22 rows."""
    start = max(0, i - RV_WINDOW + 1)
    rows = (np.flatnonzero(sec.present[start:i + 1]) + start)[-(RV_RETURNS + 1):]
    if len(rows) < RV_RETURNS + 1:
        return math.nan
    return float(np.std(np.diff(np.log(sec.adj_close[rows].astype(float))), ddof=1) * math.sqrt(252))


# ------------------------------------------------------------------------------------------- dividends
def dividend_events(actions: pd.DataFrame, sessions: list[date], secs: dict) -> dict[str, list[tuple[int, float, float]]]:
    """Each security's dividends: (ex session, rupees a share, yield against the raw close of its previous row)."""
    out: dict = {}
    n = len(sessions)
    for sym, ex, amount in zip(actions["symbol"], actions["ex_date"].dt.date, actions["dividend"]):
        if not amount > 0 or sym not in secs:
            continue
        k = bisect.bisect_left(sessions, ex)
        if k <= 0 or k >= n:
            continue
        s = secs[sym]
        prev = int(s.last_row[k - 1])
        if prev < 0 or not s.raw_close[prev] > 0:
            continue
        out.setdefault(sym, []).append((k, float(amount), float(amount) / float(s.raw_close[prev])))
    for sym in out:
        out[sym].sort()
    return out


def dividend_return(sec: round8.Security, events, e: int, exit_i: int, outcome: str) -> float:
    """("Trade") Dividends under 5% with an ex-date after the entry session and on or before the exit session (the day
    after the last row for a stock that never trades again), in adjusted terms, over the adjusted entry price."""
    end = exit_i + 1 if outcome == "no further rows" else exit_i
    total = 0.0
    for k, amount, y in events:
        if e < k <= end and y < nb.LARGE_DIVIDEND and k < len(sec.raw_close) and sec.raw_close[k] > 0:
            total += amount * (sec.adj_close[k] / sec.raw_close[k]) / sec.adj_open[e]
    return total if math.isfinite(total) else 0.0


def trade(sec: round8.Security, events, e: int, x0: int, tier: str) -> dict:
    t = round8.simulate(sec, e, x0, STOP)
    cost = round10.ROUND_TRIP[tier] + (round8.SLIPPAGE[tier] if t["reason"] == "stop" else 0.0)
    div = dividend_return(sec, events, e, t["exit_i"], t["reason"])
    return {**t, "div": div, "cost": cost, "net": t["gross"] + div - cost}


# --------------------------------------------------------------------------------------------- the run
def load_everything(verify: bool = True):
    if verify:
        check_data()
    sessions, secs, table = round8.load_inputs(verify_pins=verify)
    signal_idx = [i for i, _, _ in round8.months(sessions, None, round8.STAGE2_LAST_SIGNAL)]
    days = {sessions[i]: i for i in signal_idx}
    frames = [pd.read_parquet(nse_fo.COMPACT / f"fo_{y}.parquet")
              for y in sorted({d.year for d in days}) if (nse_fo.COMPACT / f"fo_{y}.parquet").exists()]
    fo = pd.concat(frames, ignore_index=True)
    fo["date"] = pd.to_datetime(fo["date"]).dt.date
    fo["expiry"] = pd.to_datetime(fo["expiry"]).dt.date
    fo = fo[fo["date"].isin(days) & fo["kind"].isin(["CE", "PE"])]
    panel = round8.load_panel(nb.PANEL_DIR, round8.PANEL_SHA256 if verify else None, columns=["date", "symbol", "sid", "close"])
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    panel = panel[panel["date"].isin(days)]
    to_sid = {(d, s): (sid, float(c)) for d, s, sid, c in zip(panel["date"], panel["symbol"], panel["sid"], panel["close"])}
    signals = {}
    for (day, sym), chain in fo.groupby(["date", "symbol"]):
        key = to_sid.get((day, sym))
        if key is None or key[0] not in secs:
            continue
        sid, S = key
        i = days[day]
        iv, rv = atm_iv(chain, S, day), realized_vol(secs[sid], i)
        if math.isfinite(iv) and math.isfinite(rv):
            signals[(i, sid)] = iv - rv
    events = dividend_events(nb.load_corporate_actions(), sessions, secs)
    return sessions, secs, table, signals, events


def run(stage: int, sessions, secs, table, signals, events) -> tuple[pd.DataFrame, dict[int, np.ndarray]]:
    """O2's trades and each month's random-pick pool ("The hypothesis", "The random baseline")."""
    month_list = round8.months(sessions, *SPANS[stage])
    by_i = dict(tuple(table.groupby("i")))
    rows, pools = [], {}
    for i, e, x0 in month_list:
        if i not in by_i:
            continue
        members = by_i[i][by_i[i]["rank"] <= 300]
        scored = [(signals[(i, s)], s, "N1" if r <= 100 else "N2") for s, r in zip(members["sid"], members["rank"])
                  if (i, s) in signals and s in secs]
        if not scored:
            continue
        outcomes = {s: trade(secs[s], events.get(s, []), e, x0, t) for _, s, t in scored if round8.enterable(secs[s], e)}
        if outcomes:
            pools[i] = np.array([o["net"] for o in outcomes.values()])
        for score, sid, tier in sorted(scored, key=lambda x: (x[0], x[1]))[:PICKS]:
            if sid not in outcomes:  # a pick that can't be bought leaves its slot in cash for the month
                continue
            t = outcomes[sid]
            rows.append({"signal_i": i, "signal_date": sessions[i], "entry_date": sessions[e],
                         "exit_date": sessions[t["exit_i"]], "ticker": sid, "tier": tier, "score": score,
                         "gross": t["gross"], "div": t["div"], "cost": t["cost"], "net": t["net"], "reason": t["reason"],
                         "gapped": t["gapped"]})
    trades = pd.DataFrame(rows)
    if len(trades):
        trades["R"] = trades["net"] / STOP
        trades["stopped"] = trades["reason"] == "stop"
    return trades, pools


def criteria(trades: pd.DataFrame, span, p_raw: float):
    """Round 8's criteria; one hypothesis (Holm p = raw p); criterion 12 at 0.05 / 67."""
    checks, stats = round8.criteria(trades, span, p_raw, p_raw)
    checks = [Check(12, f"Raw random-baseline p below 0.05/{TESTS_IN_PROJECT} = {CROSS_ROUND_ALPHA:.6f}", f"{p_raw:.6f}",
                    bool(not pd.isna(p_raw) and p_raw < CROSS_ROUND_ALPHA)) if c.number == 12 else c for c in checks]
    return checks, stats


def evaluate(stage: int, sessions, secs, table, signals, events) -> dict:
    trades, pools = run(stage, sessions, secs, table, signals, events)
    random_mean, raw_p, _ = round8.baseline(trades, pools, DRAWS, SEED) if len(trades) else (np.nan, 1.0, None)
    span = SPANS[stage]
    checks, stats = criteria(trades, span, raw_p)
    excess = trades["net"] - [pools[i].mean() for i in trades["signal_i"]] if len(trades) else pd.Series(dtype=float)
    return {"stage": stage, "span": span, "trades": trades, "pools": pools, "checks": checks, "stats": stats,
            "raw_p": raw_p, "random_mean": random_mean, "excess": excess, "decision": decide(checks),
            "universe": pd.Series([i for i, _ in signals]).value_counts()}


# ---------------------------------------------------------------------------------------------- report
_pct, _num = round8._pct, round8._num


def write_report(r: dict, digest: str, code_sha: str, path: Path) -> None:
    s, t = r["stats"], r["trades"]
    stage = r["stage"]
    title = ("Research round 11, stage 1 (development; decides nothing)" if stage == 1
             else "Research round 11 results: option-implied information (O2)")
    lines = [f"# {title}", "",
             f"Run on {datetime.now(round8.IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.round11 --stage {stage}` "
             f"(runner SHA-256 `{code_sha[:16]}...`), against [the pre-registration](round11-preregistration.md) (SHA-256 "
             f"`{digest[:16]}...`), the F&O manifests (`{FO_MANIFEST_SHA256[:8]}...`, `{COMPACT_MANIFEST_SHA256[:8]}...`) and "
             f"round 8's panel (`{round8.PANEL_SHA256[:8]}...`). Total returns after costs (Rs 33,333 positions, 15% stop).", ""]
    if not s.get("trades"):
        lines.append("No trades.")
    else:
        months = r["universe"]
        lines += [f"Signals {r['span'][0]} to {r['span'][1]}: {len(t)} trades; stocks with the signal per month: median "
                  f"{int(months[months.index.isin(t['signal_i'])].median())}.", "",
                  "| Trades | Win rate | Net per trade | Avg win / avg loss | PF | t | Cluster t | Random picks | p raw | Drawdown | "
                  + ("Decision |" if stage == 2 else "|"), "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
                  f"| {s['trades']} | {100 * s['win_rate']:.1f}% | {_pct(s['mean_net'])} | {_pct(s['avg_win'], 2)} / "
                  f"{_pct(s['avg_loss'], 2)} | {_num(s['profit_factor'])} | {_num(s['t'])} | {_num(s['t_clustered'])} | "
                  f"{_pct(r['random_mean'])} | {r['raw_p']:.6f} | {s['max_drawdown_r']:.1f}R | "
                  + (f"**{r['decision']}** |" if stage == 2 else "(stage 1) |"), "",
                  "| # | Criterion | Value | Result |", "|---|---|---|---|"]
        lines += [f"| {c.number} | {c.criterion} | {c.value} | {'pass' if c.passed else '**fail**'} |" for c in r["checks"]]
        if stage == 2 and [c.number for c in r["checks"] if not c.passed] == [2]:
            lines += ["", "INELIGIBLE UNDER CURRENT POLICY: every criterion passes except the 50% win-rate floor."]
        ex = r["excess"]
        lines += ["", "Informational (not part of any decision):", "",
                  f"- Beat random picks by {_pct(float(ex.mean()))} a trade (month-clustered t "
                  f"{_num(round8.clustered_t(ex, t['signal_i']))}).",
                  f"- Dividends added {_pct(float(t['div'].mean()))} a trade; price-only net {_pct(float((t['gross'] - t['cost']).mean()))}.",
                  "- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: "
                  + " / ".join(_pct(float((t["gross"] + t["div"] - x * t["cost"]).mean())) for x in (0, 1, 1.5, 2, 3)) + ".",
                  f"- Stops: {int(t['stopped'].sum())}, of which {int(t['gapped'].sum())} filled at a gap.",
                  "- By tier: " + "; ".join(f"{k}: {len(g)} trades, net {_pct(float(g['net'].mean()))}"
                                           for k, g in t.groupby("tier")) + ".", "",
                  "| Year | Trades | Net per trade | Beat random by |", "|---|---:|---:|---:|"]
        yr = t.assign(excess=ex.to_numpy(), year=[d.year for d in t["signal_date"]]).groupby("year")
        lines += [f"| {y} | {len(g)} | {_pct(float(g['net'].mean()))} | {_pct(float(g['excess'].mean()))} |" for y, g in yr]
    lines += ["", "Patterns in the informational sections are hypotheses for future data, not findings."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evidence_for(r: dict, digest: str, code_sha: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id="O2", kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round11-results.md (python -m trader.research.round11 --stage 2)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{r['span'][0]} to {r['span'][1]}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["raw_p"], "round_trip_cost": round10.ROUND_TRIP["N2"],
               "max_drawdown_r": s["max_drawdown_r"], "runner_sha256": code_sha},
        preregistration_sha256=digest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Round 11: stage 1 (development), then stage 2 (the decision, once).")
    parser.add_argument("--stage", type=int, choices=[1, 2], required=True)
    args = parser.parse_args(argv)
    make_console_utf8()
    digest = check_preregistration()
    code_sha = round8.file_sha(Path(__file__))
    if args.stage == 2:
        if not STAGE1_RESULTS.exists():
            raise SystemExit("stage 1 has not run: run --stage 1 first")
        if RESULTS.exists():
            raise SystemExit(f"{RESULTS.name} already exists: stage 2 runs once")
    sessions, secs, table, signals, events = load_everything()
    r = evaluate(args.stage, sessions, secs, table, signals, events)
    path = STAGE1_RESULTS if args.stage == 1 else RESULTS
    write_report(r, digest, code_sha, path)
    s = r["stats"]
    print(f"O2: {s['trades']} trades, win {100 * s.get('win_rate', np.nan):.1f}%, net {_pct(s.get('mean_net'))} a trade, "
          f"random {_pct(r['random_mean'])}, p {r['raw_p']:.6f}, drawdown {s.get('max_drawdown_r', np.nan):.1f}R"
          + (f" -> {r['decision']}" if args.stage == 2 else ""))
    for c in r["checks"]:
        print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
    if args.stage == 2:
        save_evidence(evidence_for(r, digest, code_sha))
    print(f"Report written to {path}")


if __name__ == "__main__":
    main()
