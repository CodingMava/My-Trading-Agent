"""Reproduce the 2026-10-08 audit of the legacy rules from frozen data.

    python -m trader.research.audit                                     # India 5-min, as deployed
    python -m trader.research.audit --dataset us_5m_60d                 # unseen market
    python -m trader.research.audit --dataset in_1h_730d --blocks --regimes
    python -m trader.research.audit --multiday                          # hold longs for days instead

Frozen data lives in data/audit_2026-10-08/<dataset>/ (git-ignored; Yahoo data must not be
redistributed). Entry "A" fills at the alert price (signal-bar close); "B" at the next bar's open.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from trader.logging_setup import make_console_utf8
from trader.research import legacy_rules as legacy
from trader.research.costs import AUDIT_2026_10_08
from trader.research.datasets import DATA_DIR, load_dataset
from trader.research.metrics import summarize
from trader.research.simulator import (ENTRY_MODES, SIDES, ExitRules, Outcomes, concat_trades,
                                       select_chain, select_trades, session_ids, simulate, trade_rows)
from trader.research.validation import (outcome_pools, period_table, random_entry_test, regime_table,
                                        trend_regime, volatility_regime)

AUDIT_DIR = DATA_DIR / "audit_2026-10-08"
INDEX_DATASET = "idx_1d"
DATASETS = {
    "in_5m_60d": {"costs": "india_intraday", "drop_dates": ()},
    # The US session was still open when this was downloaded, so its partial last day is dropped.
    "us_5m_60d": {"costs": "us_intraday", "drop_dates": (date(2026, 10, 8),)},
    "in_1h_730d": {"costs": "india_intraday", "drop_dates": ()},
}
ENTRY_CODE = {"signal_close": "A", "next_open": "B"}
MULTIDAY_EXITS = ExitRules(stop=0.01, target=0.02, max_hold_sessions=10)


@dataclass
class Prepared:
    features: pd.DataFrame
    masks: dict[str, np.ndarray]
    outcomes: dict[tuple[str, str], Outcomes]
    dates: np.ndarray
    tod: np.ndarray


def prepare(raw: dict[str, pd.DataFrame], drop_dates=(), exits: ExitRules = legacy.EXITS,
            sides=SIDES, entries=ENTRY_MODES) -> dict[str, Prepared]:
    prepared = {}
    for ticker, frame in raw.items():
        frame = frame[~frame.index.duplicated(keep="first")].sort_index()
        if drop_dates:
            frame = frame[~pd.Index(frame.index.date).isin(list(drop_dates))]
        feats = legacy.legacy_features(frame)
        if len(feats) < 50:
            continue
        sessions = session_ids(feats.index)
        outcomes = {(side, entry): simulate(feats, side, exits, entry, sessions=sessions)
                    for side in sides for entry in entries}
        prepared[ticker] = Prepared(feats, legacy.legacy_masks(feats), outcomes,
                                    np.asarray(feats.index.date), np.asarray(feats.index.strftime("%H:%M")))
    return prepared


def session_dates(prepared: dict[str, Prepared]) -> list:
    return sorted(set(np.concatenate([p.dates for p in prepared.values()])))


def independent_trades(prepared: dict[str, Prepared], rule: str, entry: str) -> pd.DataFrame:
    side = legacy.SIDE[rule]
    frames = []
    for ticker, p in prepared.items():
        out = p.outcomes[(side, entry)]
        frames.append(trade_rows(ticker, p.features.index, select_trades(p.masks[rule], out), out, side, rule))
    return concat_trades(frames)


def chain_trades(prepared: dict[str, Prepared], entry: str) -> pd.DataFrame:
    """The deployed setup: rules in if/elif order, one position per stock at a time."""
    frames = []
    for ticker, p in prepared.items():
        outs = [p.outcomes[(legacy.SIDE[rule], entry)] for rule in legacy.RULE_IDS]
        picks = select_chain([p.masks[rule] for rule in legacy.RULE_IDS], outs)
        per_rule = [trade_rows(ticker, p.features.index, [i for i, pos in picks if pos == k], outs[k],
                               legacy.SIDE[rule], rule) for k, rule in enumerate(legacy.RULE_IDS)]
        frames.append(concat_trades(per_rule).sort_values("signal_time", kind="stable"))
    return concat_trades(frames)


def scorecard(prepared: dict[str, Prepared], dates: list, costs: dict,
              entries=("signal_close", "next_open"), random_test: bool = True) -> pd.DataFrame:
    """Every rule on its own, net of base costs, with stress costs and the random-entry test."""
    rows, pools = [], {}
    for entry in entries:
        for rule in legacy.RULE_IDS:
            trades = independent_trades(prepared, rule, entry)
            row = {"entry": ENTRY_CODE[entry], "rule": rule, "name": legacy.NAME[rule],
                   **summarize(trades, costs["base"], dates)}
            if len(trades):
                row["exp_net_stress_pct"] = 100 * (trades["gross"] - costs["stress"]).mean()
                if random_test:
                    key = (legacy.SIDE[rule], entry)
                    if key not in pools:
                        pools[key] = outcome_pools((p.tod, p.outcomes[key].gross) for p in prepared.values())
                    random_mean, p_value = random_entry_test(pools[key], trades["tod"], trades["gross"])
                    row["random_exp_gross_pct"], row["p_vs_random"] = 100 * random_mean, p_value
            rows.append(row)
    return pd.DataFrame(rows)


def signal_diagnostics(prepared: dict[str, Prepared]) -> tuple[pd.DataFrame, str]:
    """How often each condition is true, how often on the session's opening bar, and how persistent."""
    open_tod = min(t for p in prepared.values() for t in p.tod)
    stock_days = sum(len(set(p.dates)) for p in prepared.values())
    rows = []
    for rule in legacy.RULE_IDS:
        total = sum(int(p.masks[rule].sum()) for p in prepared.values())
        at_open = sum(int((p.masks[rule] & (p.tod == open_tod)).sum()) for p in prepared.values())
        runs = []
        for p in prepared.values():
            m = p.masks[rule].astype(int)
            if m.any():
                starts = np.flatnonzero(np.diff(np.r_[0, m]) == 1)
                ends = np.flatnonzero(np.diff(np.r_[m, 0]) == -1)
                runs.extend(ends - starts + 1)
        rows.append({"rule": rule, "name": legacy.NAME[rule], "signal_bars": total,
                     "per_stock_day": total / stock_days,
                     "pct_on_open_bar": 100 * at_open / total if total else np.nan,
                     "avg_consecutive_bars": float(np.mean(runs)) if runs else np.nan})
    return pd.DataFrame(rows), open_tod


def volume_spike_rates(prepared: dict[str, Prepared], open_tod: str) -> tuple[float, float]:
    """vol_spike frequency on the opening bar vs the median of all other bars of the day."""
    spikes = pd.concat([pd.Series(p.features["vol_spike"].to_numpy(), index=p.tod) for p in prepared.values()])
    rate = spikes.groupby(level=0).mean() * 100
    return float(rate.get(open_tod, np.nan)), float(rate.drop(open_tod).median())


def overlap(prepared: dict[str, Prepared]) -> tuple[pd.DataFrame, dict]:
    stacked = {r: np.concatenate([p.masks[r] for p in prepared.values()]) for r in legacy.RULE_IDS}
    longs = [r for r in legacy.RULE_IDS if legacy.SIDE[r] == "long"]
    jaccard = pd.DataFrame(index=longs, columns=longs, dtype=float)
    for x in longs:
        for y in longs:
            jaccard.loc[x, y] = (stacked[x] & stacked[y]).sum() / max((stacked[x] | stacked[y]).sum(), 1)
    shares = {r: (stacked[r] & stacked["R1"]).sum() / max(stacked[r].sum(), 1) for r in ("R4", "R6")}
    return jaccard, shares


def multiday_table(raw: dict[str, pd.DataFrame], drop_dates, cost: float) -> pd.DataFrame:
    """Sensitivity: hold long signals until stop/target for up to 10 sessions instead of squaring off."""
    prepared = prepare(raw, drop_dates, exits=MULTIDAY_EXITS, sides=("long",), entries=("next_open",))
    dates = session_dates(prepared)
    keys = ("trades", "win_pct", "exp_gross_pct", "exp_net_pct", "profit_factor", "t_stat", "target_pct", "stop_pct")
    rows = []
    for rule in legacy.RULE_IDS:
        if legacy.SIDE[rule] == "long":
            stats = summarize(independent_trades(prepared, rule, "next_open"), cost, dates)
            rows.append({"rule": rule, "name": legacy.NAME[rule], **{k: stats.get(k) for k in keys}})
    return pd.DataFrame(rows)


def regimes_for(dataset: str, data_dir: Path) -> dict[str, pd.Series]:
    index = load_dataset(data_dir / INDEX_DATASET)
    if dataset.startswith("us"):
        return {"S&P500>50DMA": trend_regime(index["^GSPC"]["close"])}
    return {"NIFTY>50DMA": trend_regime(index["^NSEI"]["close"]),
            "VIX>median": volatility_regime(index["^INDIAVIX"]["close"])}


def _show(title: str, frame: pd.DataFrame) -> None:
    print(f"\n{title}")
    print(frame.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv: list[str] | None = None) -> None:
    make_console_utf8()
    pd.set_option("display.width", 250)
    parser = argparse.ArgumentParser(description="Reproduce the 2026-10-08 audit of the legacy rules.")
    parser.add_argument("--dataset", default="in_5m_60d", choices=sorted(DATASETS))
    parser.add_argument("--data-dir", default=str(AUDIT_DIR), help="folder holding the frozen datasets")
    parser.add_argument("--blocks", action="store_true", help="half-year stability table")
    parser.add_argument("--regimes", action="store_true", help="market-trend and volatility regime split")
    parser.add_argument("--multiday", action="store_true", help="hold long signals for up to 10 sessions")
    parser.add_argument("--no-random", action="store_true", help="skip the random-entry test (faster)")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    spec = DATASETS[args.dataset]
    costs = AUDIT_2026_10_08[spec["costs"]]
    raw = load_dataset(data_dir / args.dataset)
    prepared = prepare(raw, spec["drop_dates"])
    dates = session_dates(prepared)
    print(f"=== {args.dataset}: {len(prepared)} stocks, {len(dates)} sessions {dates[0]} -> {dates[-1]}; "
          f"round-trip costs base {100 * costs['base']:.3f}%, stress {100 * costs['stress']:.3f}% ===")

    diag, open_tod = signal_diagnostics(prepared)
    _show("RAW SIGNAL DIAGNOSTICS (how often each condition is true on a completed bar)", diag)
    at_open, elsewhere = volume_spike_rates(prepared, open_tod)
    print(f"vol_spike rate: opening bar {open_tod} = {at_open:.1f}%  vs  median other bars = {elsewhere:.1f}%")
    jaccard, shares = overlap(prepared)
    print("\nOverlap of long-rule signal bars (Jaccard):")
    print(jaccard.round(2).to_string())
    print(f"Share of R4 signals that are also R1: {100 * shares['R4']:.1f}%; R6 also R1: {100 * shares['R6']:.1f}%")

    card = scorecard(prepared, dates, costs, random_test=not args.no_random)
    columns = ["entry", "rule", "name", "trades", "win_pct", "avg_win_pct", "avg_loss_pct", "profit_factor",
               "exp_gross_pct", "exp_net_pct", "exp_net_stress_pct", "t_stat", "random_exp_gross_pct",
               "p_vs_random", "max_dd_units", "sharpe", "target_pct", "stop_pct", "time_pct",
               "first_half_exp_pct", "second_half_exp_pct", "breadth"]
    _show("EACH RULE ON ITS OWN (returns in % of position; 1R = the 1% stop; win = net P&L > 0)",
          card[[c for c in columns if c in card.columns]])

    for entry in ("signal_close", "next_open"):
        trades = chain_trades(prepared, entry)
        stats = summarize(trades, costs["base"], dates)
        print(f"\nAS DEPLOYED (if/elif chain, one position per stock), entry {ENTRY_CODE[entry]}: "
              f"{stats['trades']} trades, {stats['win_pct']:.1f}% winners, net {stats['exp_net_pct']:+.3f}%/trade, "
              f"PF {stats['profit_factor']:.2f}, t {stats['t_stat']:.2f}, total {stats['total_units']:+.0f}R, "
              f"max drawdown {stats['max_dd_units']:.0f}R")
        rows = []
        for rule in legacy.RULE_IDS:
            sub = trades[trades["rule"] == rule]
            if len(sub):
                s = summarize(sub, costs["base"], dates)
                rows.append({"rule": rule, "name": legacy.NAME[rule], "trades": s["trades"], "win_pct": s["win_pct"],
                             "exp_net_pct": s["exp_net_pct"], "profit_factor": s["profit_factor"], "t_stat": s["t_stat"]})
        print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    if args.blocks or args.regimes:
        by_rule = {rule: independent_trades(prepared, rule, "next_open") for rule in legacy.RULE_IDS}
        by_rule["CHAIN"] = chain_trades(prepared, "next_open")
    if args.blocks:
        rows = []
        for rule, trades in by_rule.items():
            if len(trades):
                table = period_table(trades, costs["base"])
                row = {"rule": rule, **{b: f"{v['mean']:+.3f} ({int(v['count'])})" for b, v in table.iterrows()}}
                row["blocks>0"] = f"{int((table['mean'] > 0).sum())}/{len(table)}"
                rows.append(row)
        _show("HALF-YEAR BLOCKS (entry B, net % per trade, trade count in brackets)", pd.DataFrame(rows))
    if args.regimes:
        regimes = regimes_for(args.dataset, data_dir)
        rows = [{"rule": rule, **regime_table(trades, costs["base"], regimes)}
                for rule, trades in by_rule.items() if len(trades)]
        _show("REGIMES (entry B, base costs; regime known before the session opens)", pd.DataFrame(rows))
    if args.multiday:
        cost = AUDIT_2026_10_08["india_delivery"] if spec["costs"].startswith("india") else costs["base"]
        _show(f"MULTI-DAY HOLDING (longs, entry B, stop/target or 10 sessions; cost {100 * cost:.3f}%)",
              multiday_table(raw, spec["drop_dates"], cost))


if __name__ == "__main__":
    main()
