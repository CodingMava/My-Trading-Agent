"""Paper-trading evidence: is a PAPER strategy ready for LIVE_SMALL?

    python -m trader.execution.report            # each strategy's paper results against the gate
    python -m trader.execution.report --write    # also save docs/research/evidence/<id>.paper.json

The gate (config/gate.toml [paper], the audit's Level 5) wants three months and 40 trades, a paper
expectancy inside the research holdout's 95% interval and above zero, realised costs close to the modelled
ones, 60 unattended sessions in a row without a failed run, no duplicate order, records that reconcile, and
your word that you reviewed at least 20 of the paper trades and agree with them:

    python -m trader.execution.report --reviewed 25 --write

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
from trader.execution.store import PaperStore
from trader.gate import (EVIDENCE_DIR, Evidence, GateConfig, decide_paper, load_evidence, load_gate_config,
                         paper_checks, save_evidence)
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


def main(argv: list[str] | None = None) -> None:
    make_console_utf8()
    parser = argparse.ArgumentParser(description="Score paper trading against the gate.")
    parser.add_argument("--write", action="store_true", help="save the evidence files")
    parser.add_argument("--reviewed", type=int, default=0, metavar="N",
                        help="how many of the paper trades you have reviewed and agree with")
    args = parser.parse_args(argv)
    settings = load_settings()
    store = PaperStore(ROOT / settings.paper_database, settings.paper_starting_capital)
    strategy_ids = sorted(set(store.trades()["strategy_id"])) if not store.trades().empty else []
    if not strategy_ids:
        print("No closed paper trades yet.")
    for strategy_id in strategy_ids:
        evidence = paper_evidence(store, strategy_id, date.today(), reviewed_trades=args.reviewed)
        if evidence is None:
            print(f"{strategy_id}: no research evidence to compare with")
            continue
        print(f"{strategy_id}: {evidence.stats['trades']} trades over {evidence.stats['weeks']:.1f} weeks -> {evidence.decision}")
        for check in evidence.checks:
            print(f"   [{'x' if check['passed'] else ' '}] {check['criterion']}: {check['value']}")
        if args.write:
            print(f"   saved {save_evidence(evidence)}")


if __name__ == "__main__":
    main()
