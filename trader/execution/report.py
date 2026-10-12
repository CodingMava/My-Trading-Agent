"""Paper- and live-trading evidence: is a PAPER strategy ready for LIVE_SMALL, and a LIVE_SMALL one for LIVE?

    python -m trader.execution.report            # each strategy's paper results against the gate
    python -m trader.execution.report --write    # also save docs/research/evidence/<id>.paper.json
    python -m trader.execution.report --live --kill-switch-tested --no-overrides --write   # Level 6

The gate (config/gate.toml [paper], the audit's Level 5) wants three months and 40 trades, a paper
expectancy inside the research holdout's 95% interval and above zero, realised costs close to the modelled
ones, 60 unattended sessions in a row without a failed run, no duplicate order, records that reconcile, and
your word that you reviewed at least 20 of the paper trades and agree with them:

    python -m trader.execution.report --reviewed 25 --write

With --live it scores small-capital live trading instead (config/gate.toml [live], the audit's Level 6): three
months, live fills and results tracking paper's, slippage within the cost model, no live request that needed
a person, and your word that the kill switch was tested live and that you rode out a bad week without
overriding the system. Passing it lets the live capital grow in steps (Level 7).

Saving the evidence doesn't change any status: a person still edits config/strategies.toml, and the
registry then checks it.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trader.config import ROOT, load_settings
from trader.execution.live import track
from trader.execution.oms import LiveStore
from trader.execution.records import from_fills
from trader.execution.store import PaperStore
from trader.gate import (EVIDENCE_DIR, Evidence, GateConfig, decide_paper, decide_small_live, load_evidence,
                         load_gate_config, paper_checks, save_evidence, small_live_checks)
from trader.logging_setup import make_console_utf8
from trader.ops.health import clean_sessions, duplicate_orders
from trader.strategies.catalog import CATALOG

IST = ZoneInfo("Asia/Kolkata")


def paper_evidence(store: PaperStore, strategy_id: str, today: date, cfg: GateConfig | None = None,
                   evidence_dir: Path = EVIDENCE_DIR, reviewed_trades: int = 0, now: datetime | None = None) -> Evidence | None:
    """None when there are no paper trades yet, or no research evidence to compare them with."""
    cfg = cfg or load_gate_config()
    trades = store.trades(strategy_id)
    research = load_evidence(strategy_id, "research", evidence_dir)
    if trades.empty or research is None or not research.stats:
        return None
    weeks = (date.fromisoformat(trades["exit_session"].max()) - date.fromisoformat(trades["entry_session"].min())).days / 7
    notional = trades["quantity"] * trades["entry_price"]
    realised = float((trades["fees"] / notional).mean())
    spec = CATALOG.get(strategy_id)
    modelled = spec.costs.round_trip(float(notional.mean())) if spec else realised
    stats = research.stats
    now = now or datetime.now(IST)
    clean, duplicates, problems = clean_sessions(store, now), duplicate_orders(store), len(store.reconcile())
    checks = paper_checks(trades["net_return"], weeks, stats["holdout_mean_net"], stats["holdout_sd_net"],
                          int(stats["holdout_trades"]), realised, modelled, cfg.paper, clean, duplicates, problems,
                          reviewed_trades)
    return Evidence(strategy_id=strategy_id, kind="paper", decision=decide_paper(checks), generated=today.isoformat(),
                    source="python -m trader.execution.report", checks=tuple(asdict(c) for c in checks),
                    stats={"trades": int(len(trades)), "weeks": weeks, "win_rate": float((trades["net_return"] > 0).mean()),
                           "mean_net": float(trades["net_return"].mean()), "realised_cost": realised,
                           "modelled_cost": modelled, "clean_sessions": clean, "duplicate_orders": duplicates,
                           "reconciliation_problems": problems, "reviewed_trades": reviewed_trades})


def live_evidence(paper: PaperStore, live: LiveStore, strategy_id: str, today: date, capital: float,
                  kill_switch_tested: bool = False, no_overrides: bool = False, cfg: GateConfig | None = None) -> Evidence | None:
    """Small-capital live evidence (Level 6) for one strategy; None before its first live fill. Live trading
    began with the strategy's first request to Kite: the paper orders made since then are the ones live
    should have mirrored."""
    cfg = cfg or load_gate_config()
    fills = live.table("live_fills")
    fills = fills[fills["strategy_id"] == strategy_id]
    if fills.empty:
        return None
    requests = live.table("broker_orders")
    requests = requests[requests["strategy_id"] == strategy_id]
    began = requests["session"].min()
    trips = from_fills(fills)
    live_net = trips["gain"] / trips["buy_value"]
    trades = paper.trades(strategy_id)
    paper_net = trades.loc[trades["entry_session"] >= fills["session"].min(), "net_return"]
    orders = paper.table("orders")
    should_mirror = orders[(orders["strategy_id"] == strategy_id) & (orders["created_session"] >= began)
                           & (orders["status"] == "FILLED") & orders["symbol"].str.endswith(".NS")]
    tracked = track(paper, live)
    tracked = tracked[tracked["strategy"] == strategy_id]
    fill_rate = len(tracked) / len(should_mirror) if len(should_mirror) else 0.0
    slippage = float(tracked["slippage"].mean()) if len(tracked) else 0.0
    spec = CATALOG.get(strategy_id)
    modelled = spec.costs.slippage_per_side if spec else 0.0
    interventions = int(requests["status"].isin(["REJECTED", "UNKNOWN", "SENDING"]).sum())
    week = [f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}" for d in trips["sell_date"]]
    weekly = trips["gain"].groupby(week).sum() if len(trips) else trips["gain"]
    worst_week = float(weekly.min() / capital) if len(weekly) and capital > 0 else 0.0
    weeks = (today - date.fromisoformat(began)).days / 7
    checks = small_live_checks(live_net, paper_net, weeks, fill_rate, slippage, modelled, interventions, worst_week,
                               kill_switch_tested, no_overrides, cfg.live)
    return Evidence(strategy_id=strategy_id, kind="live", decision=decide_small_live(checks), generated=today.isoformat(),
                    source="python -m trader.execution.report --live", checks=tuple(asdict(c) for c in checks),
                    stats={"round_trips": int(len(trips)), "weeks": weeks, "mean_net": float(live_net.mean()) if len(trips) else None,
                           "paper_mean_net": float(paper_net.mean()) if len(paper_net) else None, "fill_rate": fill_rate,
                           "slippage": slippage, "modelled_slippage": modelled, "interventions": interventions,
                           "worst_week": worst_week, "capital": capital})


def show(evidence: Evidence, summary: str, write: bool) -> None:
    print(f"{evidence.strategy_id}: {summary} -> {evidence.decision}")
    for check in evidence.checks:
        print(f"   [{'x' if check['passed'] else ' '}] {check['criterion']}: {check['value']}")
    if write:
        print(f"   saved {save_evidence(evidence)}")


def main(argv: list[str] | None = None) -> None:
    make_console_utf8()
    parser = argparse.ArgumentParser(description="Score paper trading against the gate.")
    parser.add_argument("--write", action="store_true", help="save the evidence files")
    parser.add_argument("--reviewed", type=int, default=0, metavar="N",
                        help="how many of the paper trades you have reviewed and agree with")
    parser.add_argument("--live", action="store_true", help="score small-capital live trading (Level 6) instead")
    parser.add_argument("--market", choices=["NSE", "US"], default="NSE", help="which paper account (default NSE)")
    parser.add_argument("--kill-switch-tested", action="store_true",
                        help="you engaged the kill switch while live and saw entries stop and exits go on")
    parser.add_argument("--no-overrides", action="store_true",
                        help="you never overrode the system while live (no manual trades in its stocks)")
    args = parser.parse_args(argv)
    settings = load_settings()
    store = (PaperStore(ROOT / settings.paper_us_database, settings.paper_us_starting_capital) if args.market == "US"
             else PaperStore(ROOT / settings.paper_database, settings.paper_starting_capital))
    if args.live:
        live_db = ROOT / settings.live_database
        live = LiveStore(live_db) if live_db.exists() else None
        fills = live.table("live_fills") if live is not None else None
        if fills is None or fills.empty:
            print("No live fills yet.")
            return
        steps = live.capital_steps()
        capital = steps[-1]["capital"] if steps else settings.live_capital
        for strategy_id in sorted(set(fills["strategy_id"])):
            evidence = live_evidence(store, live, strategy_id, date.today(), capital, args.kill_switch_tested,
                                     args.no_overrides)
            show(evidence, f"{evidence.stats['round_trips']} live round trips over {evidence.stats['weeks']:.1f} weeks",
                 args.write)
        return
    strategy_ids = sorted(set(store.trades()["strategy_id"])) if not store.trades().empty else []
    if not strategy_ids:
        print("No closed paper trades yet.")
    for strategy_id in strategy_ids:
        evidence = paper_evidence(store, strategy_id, date.today(), reviewed_trades=args.reviewed)
        if evidence is None:
            print(f"{strategy_id}: no research evidence to compare with")
            continue
        show(evidence, f"{evidence.stats['trades']} trades over {evidence.stats['weeks']:.1f} weeks", args.write)


if __name__ == "__main__":
    main()
