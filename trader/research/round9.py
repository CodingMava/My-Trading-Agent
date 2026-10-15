"""Research round 9: low volatility (L1, L2) and volatility-adjusted momentum (V2) on round 8's survivorship-free NSE
universe, judged against docs/research/round9-preregistration.md.

    python -m trader.research.round9 --stage 1    # development and replication: writes docs/research/round9-stage1.md
    python -m trader.research.round9 --stage 2    # the decision, once: round9-results.md and the evidence for L1, L2, V2

Everything but the choice of stocks is round 8's: the universe, liquidity tiers, the monthly trade with a 10% stop,
costs, the random baseline from the same tier and the criteria. L1 and L2 pick the 5 least volatile stocks of the top
100 and of ranks 101-300; V2 picks the 5 highest volatility-adjusted momentum scores in ranks 101-300. round8.py is
reused, not changed, so round 8's recorded runner stays the code that ran.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader.config import ROOT
from trader.gate import Check, Evidence, decide, save_evidence
from trader.logging_setup import make_console_utf8
from trader.research import round8
from trader.research.datasets import text_sha256

PREREGISTRATION = ROOT / "docs" / "research" / "round9-preregistration.md"
PREREGISTRATION_SHA256 = "2f35fd4b44e1b9ef455509ceab5506820dbe0299daafe06f79b4bd6360ddbbf4"  # pinned 2026-10-14 23:33 IST
STAGE1_RESULTS = ROOT / "docs" / "research" / "round9-stage1.md"
RESULTS = ROOT / "docs" / "research" / "round9-results.md"
TESTS_IN_PROJECT = 28  # H1-H14, C1-C6, I1-I3, N1-N2, L1, L2, V2
CROSS_ROUND_ALPHA = 0.05 / TESTS_IN_PROJECT
VOL_WINDOW, VOL_MIN = 252, 200
# hypothesis: (round 8's tier and costs, score column (highest first), name)
HYPOTHESES = {
    "L1": ("N1", "score_L", "Low volatility: the 5 least volatile of the 100 most liquid NSE stocks, monthly"),
    "L2": ("N2", "score_L", "Low volatility: the 5 least volatile of liquidity ranks 101-300, monthly"),
    "V2": ("N2", "score_V", "Volatility-adjusted momentum: the top 5 of liquidity ranks 101-300, monthly"),
}


def check_preregistration() -> str:
    digest = text_sha256(PREREGISTRATION)
    if digest != PREREGISTRATION_SHA256:
        raise SystemExit(f"{PREREGISTRATION.name} changed after it was pinned (sha256 {digest}); "
                         "pre-register a new hypothesis set instead of editing this one.")
    return digest


# ----------------------------------------------------------------------------------------------- scores
def volatility(sec: round8.Security) -> np.ndarray:
    """("Volatility at signal date s") On the session grid: the standard deviation of the last 252 daily log returns of
    the adjusted close, row to row, times sqrt(252); NaN with fewer than 200, and on sessions without a row."""
    out = np.full(len(sec.present), np.nan)
    rows = np.flatnonzero(sec.present)
    if len(rows) < 2:
        return out
    returns = pd.Series(np.diff(np.log(sec.adj_close[rows].astype(float))))
    out[rows[1:]] = (returns.rolling(VOL_WINDOW, min_periods=VOL_MIN).std(ddof=1) * np.sqrt(252)).to_numpy()
    return out


def add_scores(table: pd.DataFrame, secs: dict[str, round8.Security]) -> pd.DataFrame:
    """Round 8's table plus vol, score_L (minus vol: the least volatile first) and score_V (the 101-300 tier's z-scores of
    the 12-1 and 6-1 returns divided by vol, averaged). Stocks without a volatility get no score."""
    table = table.copy()
    vols = {sid: volatility(sec) for sid, sec in secs.items()}
    table["vol"] = [vols[s][i] if s in vols else np.nan for s, i in zip(table["sid"], table["i"])]
    table["score_L"] = -table["vol"]
    table["score_V"] = np.nan
    lo, hi = round8.TIERS["N2"]
    tier = table["rank"].between(lo, hi) & table["vol"].notna()
    for i, rows in table[tier].groupby("i"):
        m12 = rows["score_12-1"] / rows["vol"]
        m6 = rows["score_6-1"] / rows["vol"]
        if len(rows) < 2:
            continue
        z = ((m12 - m12.mean()) / m12.std(ddof=1) + (m6 - m6.mean()) / m6.std(ddof=1)) / 2
        table.loc[rows.index, "score_V"] = z
    return table


def add_variant_scores(table: pd.DataFrame) -> pd.DataFrame:
    """Informational sensitivity only: 12-1 or 6-1 alone, each divided by vol (not z-scored: the ranking is the same)."""
    table = table.copy()
    table["score_V12"] = table["score_12-1"] / table["vol"]
    table["score_V6"] = table["score_6-1"] / table["vol"]
    return table


# ------------------------------------------------------------------------------------------------- tests
def criteria(trades: pd.DataFrame, span, p_holm: float, p_raw: float):
    """Round 8's criteria, with criterion 12's bar at 0.05 / 28."""
    checks, stats = round8.criteria(trades, span, p_holm, p_raw)
    checks = [Check(12, f"Raw random-baseline p below 0.05/{TESTS_IN_PROJECT} = {CROSS_ROUND_ALPHA:.5f}", f"{p_raw:.5f}",
                    bool(not pd.isna(p_raw) and p_raw < CROSS_ROUND_ALPHA)) if c.number == 12 else c for c in checks]
    return checks, stats


def evaluate(stage: int, sessions, secs, table, with_informational: bool = True) -> dict:
    month_list = (round8.months(sessions, None, round8.STAGE1_LAST_SIGNAL) if stage == 1
                  else round8.months(sessions, round8.STAGE2_FIRST_SIGNAL, round8.STAGE2_LAST_SIGNAL))
    results, raw_p = {}, {}
    for key, (tier, score, name) in HYPOTHESES.items():
        trades, pools, plain = round8.run_tier(tier, table, secs, sessions, month_list, score=score)
        random_mean, raw_p[key], _ = round8.baseline(trades, pools) if len(trades) else (np.nan, 1.0, None)
        results[key] = {"name": name, "tier": tier, "score": score, "trades": trades, "pools": pools, "plain": plain,
                        "random_mean": random_mean, "span": (sessions[month_list[0][0]], sessions[month_list[-1][0]]),
                        "months": len(month_list)}
    adjusted = round8.holm(raw_p)
    for key, r in results.items():
        checks, stats = criteria(r["trades"], r["span"], adjusted[key], raw_p[key])
        r.update(checks=checks, stats=stats, decision=decide(checks), raw_p=raw_p[key], holm_p=adjusted[key])
        if with_informational and len(r["trades"]):
            r["info"] = informational(key, r, secs, sessions, month_list, table)
    return {"stage": stage, "results": results, "month_list": month_list}


def informational(key: str, r: dict, secs, sessions, month_list, table) -> dict:
    trades, tier = r["trades"], r["tier"]
    info = {}
    monthly = round8.monthly_table(trades, r["plain"], r["pools"])
    boot = round8.stationary_bootstrap_means(monthly["excess"].to_numpy())
    info["excess_mean"] = float(monthly["excess"].mean())
    info["excess_ci"] = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))
    boot_net = round8.stationary_bootstrap_means(monthly["picks_net"].to_numpy(), seed=10)
    info["net_ci"] = (float(np.percentile(boot_net, 2.5)), float(np.percentile(boot_net, 97.5)))
    info["win_ci"] = round8.wilson(int((trades["net"] > 0).sum()), len(trades))
    nifty = round8.nifty_monthly(month_list, sessions).reindex(monthly.index)
    info["portfolios"] = {"engine size (5 x 5%)": round8.portfolio_stats(monthly["picks_sum"] * round8.ENGINE_WEIGHT),
                          "fully invested (5 x 20%)": round8.portfolio_stats(monthly["picks_sum"] * round8.FULL_WEIGHT),
                          "tier average, bought and held (no stop, no costs)": round8.portfolio_stats(monthly["tier_gross"]),
                          "NIFTY 50 price index": round8.portfolio_stats(nifty.dropna())}
    info["kill_switch"] = round8.kill_switch_replay(trades, secs, sessions)
    info["costs"] = {f"{x}x": float((trades["gross"] - x * trades["cost"]).mean()) for x in (0, 1, 1.5, 2, 3)}
    info["regimes"] = round8.regimes(trades)
    info["by_year"] = trades.groupby([d.year for d in trades["signal_date"]])["net"].agg(["count", "mean"])
    info["stops"] = {"stops": int(trades["stopped"].sum()), "gapped": int(trades["gapped"].sum())}
    info["suspect_fills"] = round8.suspect_fills(trades, secs, sessions)
    info["delisted"] = trades[trades["reason"].isin(["no further rows", "time, delayed"])][
        ["ticker", "signal_date", "entry_date", "exit_date", "reason", "gross", "net"]]
    variants = {}
    scored = add_variant_scores(table)
    options = ([("10 picks", r["score"], 10, round8.STOP), ("no stop", r["score"], 5, None)]
               + ([("12-1 / vol alone", "score_V12", 5, round8.STOP), ("6-1 / vol alone", "score_V6", 5, round8.STOP)]
                  if key == "V2" else []))
    columns = [("as pre-registered", monthly["excess"])]
    for label, score, picks, stop in options:
        vt, vpools, _ = round8.run_tier(tier, scored, secs, sessions, month_list, picks, score, stop)
        if not len(vt):
            continue
        vm = vt.groupby("signal_i")["net"].mean()
        excess = vm - pd.Series({i: vpools[i].mean() for i in vm.index})
        variants[label] = {"trades": len(vt), "win_rate": float((vt["net"] > 0).mean()),
                           "mean_net": float(vt["net"].mean()), "excess": float(excess.mean())}
        columns.append((label, excess))
    info["variants"] = variants
    frame = pd.concat({name: s for name, s in columns}, axis=1).dropna()
    sr = frame.mean() / frame.std(ddof=1)
    info["dsr"] = round8.dsr(monthly["excess"].to_numpy(), TESTS_IN_PROJECT, float(sr.var(ddof=1)) if len(sr) > 1 else 0.0)
    return info


# ------------------------------------------------------------------------------------------------ report
_pct, _num, _summary = round8._pct, round8._num, round8._summary


def write_report(report: dict, digest: str, code_sha: str, path: Path) -> None:
    stage, results = report["stage"], report["results"]
    title = ("Research round 9, stage 1 (development and replication, decides nothing)" if stage == 1
             else "Research round 9 results: low volatility and volatility-adjusted momentum on the NSE universe")
    lines = [f"# {title}", "",
             f"Run on {datetime.now(round8.IST):%Y-%m-%d %H:%M} IST by `python -m trader.research.round9 --stage {stage}` "
             f"(runner SHA-256 `{code_sha[:16]}...`), against [the pre-registration](round9-preregistration.md) (SHA-256 "
             f"`{digest[:16]}...`) and round 8's frozen panel (SHA-256 `{round8.PANEL_SHA256[:16]}...`). Every hypothesis is "
             "reported. Returns are per trade, net of round 8's costs.", "",
             "## Summary", "",
             "| Hypothesis | Trades | Wins / losses | Win rate | Net per trade | Median | Avg win / avg loss | t | Cluster t | "
             "Random picks (same rules) | p raw / Holm | Drawdown | " + ("Decision |" if stage == 2 else "|"),
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key, r in results.items():
        s = r["stats"]
        if not s["trades"]:
            lines.append(f"| {key}: {r['name']} | 0 | - | - | - | - | - | - | - | - | - | - | {r['decision']} |")
            continue
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
                  f"({traded.nunique()} months with trades). Mean net {_pct(s.get('mean_net'))} a trade against "
                  f"{_pct(r['random_mean'])} for 5 random stocks from the same tier with the same rules "
                  f"(p = {r['raw_p']:.5f}, Holm {r['holm_p']:.5f})."]
        if stage == 2:
            lines += ["", f"**Decision: {r['decision']}.**"]
            failed = [c.number for c in r["checks"] if not c.passed]
            if failed == [2]:
                lines += ["", "INELIGIBLE UNDER CURRENT POLICY: every criterion passes except the 50% win-rate floor."]
        if not info:
            continue
        lo, hi = info["win_ci"]
        lines += ["", "Informational (not part of any decision):", "",
                  f"- Win rate 95% interval (Wilson): {100 * lo:.1f}% to {100 * hi:.1f}%. Mean net per month of picks, 95% "
                  f"interval (month-block bootstrap): {_pct(info['net_ci'][0])} to {_pct(info['net_ci'][1])}.",
                  f"- Monthly excess over the random-pick expectation: {_pct(info['excess_mean'])} (95% interval "
                  f"{_pct(info['excess_ci'][0])} to {_pct(info['excess_ci'][1])}).",
                  f"- Stops: {info['stops']['stops']}, of which {info['stops']['gapped']} filled at a gap.",
                  "- Net per trade at 0x / 1x / 1.5x / 2x / 3x costs: " + " / ".join(_pct(v) for v in info["costs"].values()) + "."]
        ks = info.get("kill_switch", {})
        if ks:
            lines.append(f"- The account at the engine's size (Rs 10,00,000, 5 x 5%), marked daily: final Rs "
                         f"{ks['final_equity']:,.0f}, deepest drawdown {_pct(ks['max_drawdown'], 1)}; the 10% kill switch "
                         + (f"would have engaged on {ks['kill_switch_session']}." if ks["kill_switch_session"] else "never engaged."))
        if info.get("dsr"):
            d = info["dsr"]
            lines.append(f"- Deflated Sharpe ratio of the monthly excess: {d['dsr']:.3f} (Sharpe {d['sr_annual']:.2f} a year; "
                         f"{d['trials']} trials).")
        lines += ["", "| Portfolio (monthly) | CAGR | Volatility | Sharpe | Sortino | Max drawdown |", "|---|---:|---:|---:|---:|---:|"]
        for label, p in info["portfolios"].items():
            if p:
                lines.append(f"| {label} | {_pct(p['cagr'], 1)} | {_pct(p['vol'], 1)} | {_num(p['sharpe'])} | "
                             f"{_num(p['sortino'])} | {_pct(p['max_drawdown'], 1)} |")
        lines += ["", "| Variant (sensitivity, never used to choose) | Trades | Win rate | Net per trade | Monthly excess over random |",
                  "|---|---:|---:|---:|---:|"]
        lines += [f"| {name} | {v['trades']} | {100 * v['win_rate']:.1f}% | {_pct(v['mean_net'])} | {_pct(v['excess'])} |"
                  for name, v in info["variants"].items()]
        for regime, parts in info.get("regimes", {}).items():
            lines.append(f"- {regime}: " + "; ".join(f"{k}: {_summary(v)}" for k, v in parts.items()) + ".")
        lines += ["", "| Year | Trades | Net per trade |", "|---|---:|---:|"]
        lines += [f"| {year} | {int(row['count'])} | {_pct(row['mean'])} |" for year, row in info["by_year"].iterrows()]
        odd = info["suspect_fills"]
        lines += ["", f"Trades entering or exiting on a demerger-type ex-date, or filled at an open more than 8% from that "
                  f"session's close (listed, not changed): {len(odd)}."]
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


def evidence_for(key: str, r: dict, digest: str, code_sha: str) -> Evidence:
    s = r["stats"]
    return Evidence(
        strategy_id=key, kind="research", decision=r["decision"], generated=date.today().isoformat(),
        source="docs/research/round9-results.md (python -m trader.research.round9 --stage 2)",
        checks=tuple(asdict(c) for c in r["checks"]),
        stats={"evaluation_span": f"{r['span'][0]} to {r['span'][1]}", "holdout_trades": s["trades"],
               "holdout_win_rate": s["win_rate"], "holdout_mean_net": s["mean_net"], "holdout_sd_net": s["sd_net"],
               "holdout_profit_factor": s["profit_factor"], "holdout_t": s["t"], "holdout_t_clustered": s["t_clustered"],
               "p_random_raw": r["raw_p"], "p_random_holm": r["holm_p"], "round_trip_cost": round8.ROUND_TRIP[r["tier"]],
               "max_drawdown_r": s["max_drawdown_r"], "runner_sha256": code_sha},
        preregistration_sha256=digest)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Round 9: stage 1 (development), then stage 2 (the decision, once).")
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
    sessions, secs, table = round8.load_inputs()
    table = add_scores(table, secs)
    report = evaluate(args.stage, sessions, secs, table)
    path = STAGE1_RESULTS if args.stage == 1 else RESULTS
    write_report(report, digest, code_sha, path)
    for key, r in report["results"].items():
        s = r["stats"]
        print(f"{key}: {s['trades']} trades, win {100 * s.get('win_rate', np.nan):.1f}%, net {_pct(s.get('mean_net'))} a trade, "
              f"random {_pct(r['random_mean'])}, p {r['raw_p']:.5f} (Holm {r['holm_p']:.5f}), drawdown "
              f"{s.get('max_drawdown_r', np.nan):.1f}R" + (f" -> {r['decision']}" if args.stage == 2 else ""))
        for c in r["checks"]:
            print(f"   [{'x' if c.passed else ' '}] {c.number}. {c.criterion}: {c.value}")
        if args.stage == 2:
            save_evidence(evidence_for(key, r, digest, code_sha))
    print(f"Report written to {path}")


if __name__ == "__main__":
    main()
