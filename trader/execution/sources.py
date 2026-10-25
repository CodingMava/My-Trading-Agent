"""Where the live evening job's orders come from (Phase 11): each paper decision for the next open, as one LiveOrder.

  the paper engine's account (state/paper.db)   the catalogue's strategies (H1, H2): the day's pending orders.
  paper trial 1's ledger (state/trial1.db)       its bunch, B1F (E2 x3 + V2 x2): the entries and time exits the trial
                                                 will make at the next open, planned the evening before by the trial's
                                                 own rules (trader.research.trial.next_open), after its evening run.

trader/execution/live.py scales each order to the live capital and sends it only for a strategy at LIVE_SMALL or LIVE
(in a dry run, one named with --as-live). A source that hasn't processed the day yet says so and gives no orders.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from trader.core.models import Position
from trader.execution.eod import market_of
from trader.execution.store import PaperStore
from trader.strategies.catalog import StrategySpec

IST = ZoneInfo("Asia/Kolkata")
TRIAL = "B1F"  # forward test 4's name for paper trial 1's bunch
RETURN_SESSIONS = 90  # daily returns handed to the risk engine's correlation check (it uses the last 60 in common)


@dataclass(frozen=True)
class LiveOrder:
    """One paper decision for the next open."""
    strategy_id: str
    key: str  # unique per paper decision: its Kite tag is made from it, so it is never sent twice
    symbol: str  # as paper trading names it (RELIANCE.NS)
    side: str  # buy or sell; a sale sells what the live account holds for the strategy
    paper_quantity: float  # shares in the paper account (a trial position is a rupee amount, so a fraction)
    paper_capital: float
    reference_price: float  # the latest close
    stop_distance: float = 0.0
    max_hold_days: int | None = None  # None: the source decides the exit (no time exit before the close)
    # Daily returns of the stock and of what the source holds, by symbol, for the live risk engine's correlation
    # check; None leaves it out (the paper engine's orders: it doesn't check correlation either).
    returns: dict[str, pd.Series] | None = field(default=None, compare=False, repr=False)


Source = Callable[[date, dict[str, Position]], tuple[list[LiveOrder] | None, list[str]]]


def paper_orders(store: PaperStore, today: date, allowed: set[str], catalog: dict[str, StrategySpec]
                 ) -> tuple[list[LiveOrder] | None, list[str]]:
    """The paper engine's orders made today for the next open, of the allowed strategies' NSE stocks."""
    if store.last_session() != today:
        return None, [f"The paper run hasn't processed {today} yet, so nothing was sent for tomorrow's open."]
    return [LiveOrder(o.strategy_id, o.key, o.symbol, o.side, o.quantity, store.starting_capital, o.reference_price,
                      o.stop_distance, catalog[o.strategy_id].max_hold_days)
            for o in store.pending_orders()
            if o.created_session == today and o.strategy_id in allowed and o.strategy_id in catalog
            and market_of(o.symbol) == "NSE"], []


def trial_orders(today: date, held: dict[str, Position], calendar, plan_for=None) -> tuple[list[LiveOrder] | None, list[str]]:
    """B1F's orders for the next open: paper trial 1's planned entries (each the trial's rupee position, 0.5% of
    Rs 10,00,000 at risk over its part's stop) and time exits, and a sale of any B1F holding the trial no longer holds
    (an entry the trial counted as not bought, or a stop that fired in paper but not live). `plan_for(today, next)`
    returns the trial's plan (trader.research.trial.next_open on its inputs); None when the trial hasn't processed
    `today` yet."""
    from trader.research import trial

    next_session = calendar.next_trading_day(today)
    plan = (plan_for or trial_plan)(today, next_session)
    if plan is None:
        return None, [f"Paper trial 1 hasn't processed {today} yet, so nothing was sent for B1F at tomorrow's open."]
    orders, notes = [], []
    for e in plan["entries"]:
        value = trial.CAPITAL * trial.RISK / trial.STOPS[e["part"]]
        orders.append(LiveOrder(TRIAL, f"{TRIAL} {e['part']} {e['sid']} {e['signal_date']} entry", e["sid"] + ".NS", "buy",
                                value / e["close"], trial.CAPITAL, e["close"], trial.STOPS[e["part"]],
                                returns=plan.get("returns")))
    for x in plan["exits"]:
        orders.append(LiveOrder(TRIAL, f"{TRIAL} {x['part']} {x['sid']} {x['signal_date']} exit {next_session}",
                                x["sid"] + ".NS", "sell", 0, trial.CAPITAL, 0.0))
    selling = {x["sid"] for x in plan["exits"]}
    for symbol, position in held.items():
        sid = symbol.removesuffix(".NS")
        if position.strategy_id == TRIAL and sid not in plan["held"] and sid not in selling:
            orders.append(LiveOrder(TRIAL, f"{TRIAL} {sid} {position.entry_date} unmatched exit {next_session}", symbol,
                                    "sell", 0, trial.CAPITAL, 0.0))
            notes.append(f"{symbol}: held live for {TRIAL} but not by paper trial 1, so it is sold at the open")
    notes += [f"{TRIAL} {part} {sid}: no paper entry at the open ({status})" for part, sid, status in plan["passed"]]
    return orders, notes


def daily_returns(sessions: list[date], secs: dict, sids) -> dict[str, pd.Series]:
    """The latest RETURN_SESSIONS daily returns of each stock's adjusted close, by paper trading's symbol."""
    index = pd.Index(sessions[-RETURN_SESSIONS - 1:])
    out = {}
    for sid in sorted(set(sids) & set(secs)):
        close = pd.Series(secs[sid].adj_close[-RETURN_SESSIONS - 1:], index=index)
        out[sid + ".NS"] = (close / close.shift(1) - 1).dropna()
    return out


def trial_plan(today: date, next_session: date) -> dict | None:
    """Paper trial 1's plan for `next_session`, from its ledger and inputs; None unless its latest evening run was
    good and had `today`'s data. Its "returns" are the daily returns of the stocks it enters and holds."""
    from trader.research import trial

    try:
        trial.check_definition()
        ledger = trial.Ledger()
        try:
            runs = ledger.table("runs")
            if runs.empty or runs["status"].iat[-1] != "ok" or not runs["detail"].iat[-1].startswith(f"data to {today};"):
                return None
            sessions, secs, _, e2, v2 = trial.inputs(None)
            if sessions[-1] != today:
                return None
            plan = trial.next_open(ledger, sessions, secs, e2, v2, next_session, datetime.now(IST))
            plan["returns"] = daily_returns(sessions, secs, [e["sid"] for e in plan["entries"]] + list(plan["held"]))
            return plan
        finally:
            ledger.close()
    except SystemExit as exc:  # a pin or frozen-data check stops the trial; for a live job it is a failure to report
        raise RuntimeError(f"paper trial 1 refused to run: {exc}") from None
