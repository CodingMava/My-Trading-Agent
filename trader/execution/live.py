"""Live trading through Zerodha Kite (Phase 11). The paper engine decides; these jobs carry its decisions out
with real shares, for the strategies that have earned it. Off by default, and locked several ways.

    python -m trader.execution.live status     # the locks, live holdings and unsettled requests (no Kite calls)
    python -m trader.execution.live check      # read-only: the account through Kite, and the fields relied on
    python -m trader.execution.live evening    # after paper trial 1's evening run: orders for the next open
    python -m trader.execution.live morning    # 09:20: stops for new holdings, stale stops deleted, gap exits
    python -m trader.execution.live preclose   # 15:15: time exits
    python -m trader.execution.live track      # live fills beside the paper fills they mirror

    python -m trader.execution.live evening --dry-run --as-live B1F   # the same jobs on a simulated account

Nothing is sent unless every lock is open:
  1. [live] enabled = true and a live capital in config/settings.toml;
  2. a strategy whose status is LIVE_SMALL or LIVE, which the registry grants only on paper-trading evidence
     (the audit's Level 5); only its orders go out, and only for NSE stocks (US trades are placed by hand). Its
     orders come from its paper account (trader/execution/sources.py): the paper engine's for the catalogue's
     strategies, paper trial 1's ledger for its bunch, B1F;
  3. today's Kite login, and an account holding every share the system believes it holds (if not, the kill
     switch engages and nothing is sent);
  4. for new entries: the kill switch off, at most [live] max_orders_per_day a day, and each order worth at
     most max_order_fraction of the live capital.
Exits and stops go out even with the kill switch engaged: it blocks new trades, never the way out.

A live entry is its paper order scaled by live capital / paper capital, so it risks the same share of the
account. An exit sells what the account holds for that strategy, never more.

The live capital grows in recorded steps (the audit's Level 7). [live] capital is what you ask for; an
increase takes effect only when every live strategy has passed Level 6 (status LIVE), it at most doubles the
current step, and the step is at least min_step_weeks old (config/gate.toml [live]). A step that loses more
than max_step_drawdown from its peak reverts to the previous one by itself; downward moves are automatic,
upward ones deliberate.

A dry run (--dry-run) runs the same jobs, interlocks and order system against a simulated Zerodha account
(trader/execution/simkite.py, kept in state/live-dryrun/) on real Kite prices: only price quotes are read from Kite,
with today's login, and nothing is sent. --as-live names the strategies it treats as live, without touching the
registry, and --capital the simulated account's rupees. Its messages are labelled [LIVE DRY RUN].
"""
from __future__ import annotations

import argparse
import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from trader.config import ROOT, Settings, load_settings
from trader.data.kite import KiteAuthError, session_secrets
from trader.execution import broker
from trader.execution.kite_orders import KiteOrders, from_session, held_quantity
from trader.execution.oms import OMS, LiveStore
from trader.execution.records import from_fills
from trader.execution.simkite import SimKite
from trader.execution.sources import TRIAL, LiveOrder, Source, paper_orders, trial_orders
from trader.execution.store import PaperStore
from trader.gate import LiveThresholds, load_gate_config
from trader.logging_setup import configure_logging, make_console_utf8, redact
from trader.markets.calendar import MarketCalendar, load_calendars
from trader.notify import templates
from trader.notify.telegram import notifier_from_settings
from trader.registry import StrategyRegistry
from trader.risk.killswitch import KillSwitch
from trader.strategies.catalog import CATALOG, StrategySpec

log = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
ENTRY_PURPOSES = ("entry",)
DRY_RUN_DIR = ROOT / "state" / "live-dryrun"
DRY_RUN_CAPITAL = 300_000.0  # about the least at which B1F's positions are whole shares for 95% of its stocks
# What the order system reads from Kite, and the fields it relies on (checked by `live check`).
RELIED_ON = {"holdings": ("tradingsymbol", "exchange", "quantity", "t1_quantity", "used_quantity"),
             "net positions": ("tradingsymbol", "exchange", "product", "quantity"),
             "orders": ("order_id", "status", "tag", "transaction_type", "order_type", "quantity",
                        "filled_quantity", "average_price", "status_message"),
             "GTTs": ("id", "status", "condition", "orders")}
# When each job may send (IST). A job run late, say after the PC was asleep, must not do something else
# than paper trading assumes: a time exit after the close, or an "after-market" order into the open market.
WINDOWS = {"evening": (time(16, 0), time(23, 59)), "morning": (time(9, 15), time(15, 25)),
           "preclose": (time(15, 0), time(15, 28))}


@dataclass
class Live:
    settings: Settings
    paper: PaperStore
    store: LiveStore
    registry: StrategyRegistry
    kill_switch: KillSwitch
    calendar: MarketCalendar
    notifier: object
    connect: Callable[[], KiteOrders]  # called only once every lock is open, so a locked job never touches Kite
    catalog: dict[str, StrategySpec] = field(default_factory=lambda: CATALOG)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(IST))
    steps: LiveThresholds = field(default_factory=LiveThresholds)
    sources: dict[str, Source] = field(default_factory=dict)  # strategies whose orders come from their own paper account
    as_live: frozenset[str] = frozenset()  # a dry run's strategies treated as live; never the registry's business
    dry_run: bool = False

    def __post_init__(self):
        if self.as_live and not self.dry_run:
            raise ValueError("only a dry run may treat a strategy as live")


def live_strategies(live: Live) -> set[str]:
    known = set(live.catalog) | set(live.sources)
    return {record.id for record in live.registry.live_strategies() if record.id in known} | (live.as_live & known)


def say(live: Live, title: str, lines: list[str]) -> None:
    live.notifier.send(templates.live_update(title=title, lines=lines, dry_run=live.dry_run))


def locks(live: Live) -> list[str]:
    """Why nothing may be sent; empty when the account may trade."""
    reasons = []
    if not live.settings.live_enabled:
        reasons.append("live trading is off ([live] enabled = false in config/settings.toml)")
    if live.settings.live_capital <= 0:
        reasons.append("no live capital is set ([live] capital)")
    if not live_strategies(live):
        reasons.append("no strategy has earned live money (LIVE_SMALL or LIVE on paper-trading evidence)")
    return reasons


def run(job: str, live: Live, backup_dir=None) -> int:
    """One job. Returns 0 when done (or there was nothing to do), 1 when it failed, 2 when reconciliation
    stopped it."""
    blocked = locks(live)
    if blocked:
        log.info("Live %s: nothing sent: %s", job, "; ".join(blocked))
        return 0
    today = live.clock().date()
    try:
        oms = OMS(live.store, live.connect(), live.clock)
        news = oms.refresh(today)
        problems = oms.reconcile()
        if problems:
            live.kill_switch.engage("live reconciliation failed: " + problems[0])
            say(live, "Reconciliation failed: nothing was sent", [
                *problems, "The kill switch is engaged. Compare the account with python -m trader.execution.live "
                "status and find out why before releasing it."])
            return 2
        start, end = WINDOWS[job]
        now = live.clock().time()
        news += (JOBS[job](live, oms, today) if start <= now <= end else
                 [f"Nothing sent: the {job} job runs between {start:%H:%M} and {end:%H:%M} IST, not at {now:%H:%M}."])
    except KiteAuthError as exc:
        say(live, f"Live {job} failed", [str(exc)])
        return 1
    except Exception as exc:  # recorded and reported, never swallowed
        detail = redact(f"{type(exc).__name__}: {exc}", live.settings.secret_values() + session_secrets())[:500]
        log.error("Live %s failed: %s", job, detail, exc_info=True)
        say(live, f"Live {job} failed", [detail])
        return 1
    if news:
        say(live, f"Live {job}", news)
    if backup_dir is not None:
        live.store.backup(backup_dir, today)
    return 0


def step_drawdown(store: LiveStore, since: date, capital: float) -> float:
    """How far the live account's closed trades since `since` fell from their best, as a share of `capital`."""
    trips = from_fills(store.table("live_fills"))
    gains = trips.loc[[day >= since for day in trips["sell_date"]], "gain"].cumsum()
    if gains.empty or capital <= 0:
        return 0.0
    return float((gains.cummax().clip(lower=0) - gains).max() / capital)


def capital_for_today(live: Live, today: date) -> tuple[float, list[str]]:
    """Level 7: the capital the live jobs may use today, and what changed. Every step is recorded."""
    steps, wanted, t = live.store.capital_steps(), live.settings.live_capital, live.steps
    if not steps:
        live.store.add_capital_step(today, wanted, "first step")
        return wanted, [f"Live capital: Rs {wanted:,.0f} (the first step)."]
    current, since = steps[-1]["capital"], date.fromisoformat(steps[-1]["session"])
    if (drawdown := step_drawdown(live.store, since, current)) > t.max_step_drawdown:
        previous = steps[-2]["capital"] if len(steps) > 1 else 0.0
        live.store.add_capital_step(today, previous, f"reverted: the step lost {drawdown:.1%} from its peak")
        return previous, [f"Live capital reverted to Rs {previous:,.0f}: the Rs {current:,.0f} step lost "
                          f"{drawdown:.1%} from its peak (limit {t.max_step_drawdown:.0%})."]
    if wanted < current:  # downward is always allowed
        live.store.add_capital_step(today, wanted, "lowered")
        return wanted, [f"Live capital lowered to Rs {wanted:,.0f}."]
    if wanted == current:
        if steps[-1]["reason"].startswith("reverted"):  # asking for the step it reverted to acknowledges the revert
            live.store.add_capital_step(today, current, "revert acknowledged")
            return current, [f"Live capital stays at Rs {current:,.0f}: the revert is acknowledged."]
        return current, []
    weeks = (today - since).days / 7
    unproven = sorted(i for i in live_strategies(live)
                      if (record := live.registry.get_by_id(i)) is None or record.status != "LIVE")
    refused = ("after a revert, lower [live] capital to the current step first, then raise it again"
               if steps[-1]["reason"].startswith("reverted") else
               f"{', '.join(unproven)} must first pass Level 6 (status LIVE)" if unproven else
               f"more than {t.max_step_increase:g}x the current step" if wanted > t.max_step_increase * current else
               f"{weeks:.0f} of {t.min_step_weeks} weeks since the last step" if weeks < t.min_step_weeks else "")
    if refused:
        return current, [f"Live capital stays at Rs {current:,.0f}, not Rs {wanted:,.0f}: {refused}."]
    live.store.add_capital_step(today, wanted, "raised")
    return wanted, [f"Live capital raised to Rs {wanted:,.0f}."]


def evening(live: Live, oms: OMS, today: date) -> list[str]:
    """After the paper runs: tomorrow's entries and exits, as after-market orders for the open."""
    if not live.calendar.is_trading_day(today):
        return []
    allowed, held = live_strategies(live), live.store.positions()
    batches = []
    if allowed & set(live.catalog):
        batches.append(paper_orders(live.paper, today, allowed, live.catalog))
    for strategy_id in sorted(allowed & set(live.sources)):
        batches.append(live.sources[strategy_id](today, held))
    notes = [note for _, found in batches for note in found]
    if all(orders is None for orders, _ in batches):
        return notes
    capital, news = capital_for_today(live, today)
    news += notes
    entries = sum(1 for row in live.store.orders() if row["session"] == today.isoformat() and row["purpose"] in ENTRY_PURPOSES)
    for order in (order for orders, _ in batches for order in orders or ()):
        if order.side == "sell":
            position = held.get(order.symbol)
            if position is None or position.strategy_id != order.strategy_id:
                continue  # nothing live to sell
            request = broker.exit_order(order.key, order.symbol, position.quantity)
            news.append(f"{order.symbol}: sell {position.quantity} at the open ({oms.submit(today, order.strategy_id, request)})")
            continue
        refused, quantity = entry_refusal(live, order, capital, held, entries)
        if refused:
            news.append(f"{order.symbol}: entry not sent: {refused}")
            continue
        request = broker.entry_order(order.key, order.symbol, quantity)
        status = oms.submit(today, order.strategy_id, request, order.stop_distance, order.max_hold_days)
        entries += 1
        news.append(f"{order.symbol}: buy {quantity} at the open ({status})")
    return news


def entry_refusal(live: Live, order: LiveOrder, capital: float, held: dict, entries: int) -> tuple[str, int]:
    """Why an entry isn't sent (empty when it is), and its live quantity: the paper order scaled to the live capital."""
    quantity = int(order.paper_quantity * capital / order.paper_capital + 1e-9)
    refused = ("the kill switch is engaged" if live.kill_switch.engaged
               else "the live account already holds it" if order.symbol in held
               else f"{order.paper_quantity:.4g} paper shares scale to none (Rs {order.reference_price:,.2f} a share)"
               if quantity < 1
               else f"worth more than {live.settings.live_max_order_fraction:.0%} of the live capital"
               if quantity * order.reference_price > live.settings.live_max_order_fraction * capital
               else f"the day's limit of {live.settings.live_max_orders_per_day} entries is reached"
               if entries >= live.settings.live_max_orders_per_day else "")
    return refused, quantity


def morning(live: Live, oms: OMS, today: date) -> list[str]:
    """After the open: protect what was bought, sell what is already below its stop, drop the stops of what
    the open sold, and turn a triggered stop's unfilled sell into a market order when the price gapped below it."""
    if not live.calendar.is_trading_day(today):
        return []
    news, held = [], live.store.positions()
    prices = oms.kite.ltp([symbol.removesuffix(".NS") for symbol in held])
    for symbol, position in held.items():
        price = prices[symbol.removesuffix(".NS")]
        stop = live.store.order(broker.stop_order(position).tag)
        if stop is None or stop["status"] in ("SENDING", "UNKNOWN"):  # not placed, or not found at Kite
            request = (broker.stop_exit(position) if price <= broker.to_tick(position.stop_price)
                       else broker.stop_order(position, last_price=price))
            news.append(f"{symbol}: {request.purpose} ({oms.submit(today, position.strategy_id, request)})")
        elif stop["status"] == "TRIGGERED" and price < broker.stop_limit(position.stop_price):
            news.append(f"{symbol}: gap exit ({oms.submit(today, position.strategy_id, broker.gap_exit(position))})")
        elif stop["status"] not in ("SENT", "TRIGGERED"):  # rejected, deleted, or it sold only part
            news.append(f"{symbol} has no stop at Kite ({stop['status'].lower()}: {stop['detail']}). Place one by hand.")
    current = {broker.stop_order(position).tag for position in held.values()}
    for row in live.store.orders(("SENT",)):
        if row["purpose"] == "stop" and row["tag"] not in current:  # its holding was sold at the open
            request = broker.cancel_stop_tagged(row["symbol"], row["tag"], broker.AFTER_OPEN)
            news.append(f"{row['symbol']}: stop deleted ({oms.submit(today, row['strategy_id'], request)})")
    return news


def preclose(live: Live, oms: OMS, today: date) -> list[str]:
    """Before the close: sell the holdings whose time is up (paper trading sells them at the close). The stop
    is deleted first, so the two can't both sell."""
    if not live.calendar.is_trading_day(today):
        return []
    news = []
    for symbol, position in live.store.positions().items():
        if not position.max_hold_days or len(live.calendar.trading_days(position.entry_date, today)) < position.max_hold_days:
            continue
        stop = live.store.order(broker.stop_order(position).tag)
        if stop is not None and stop["status"] == "TRIGGERED":
            news.append(f"{symbol}: no time exit: its stop's sell is already working")
            continue
        if stop is not None and stop["status"] == "SENT":
            deleted = oms.submit(today, position.strategy_id, broker.cancel_stop(position, broker.BEFORE_CLOSE))
            if deleted != "DONE":
                news.append(f"{symbol}: time exit not sent: its stop couldn't be deleted ({deleted})")
                continue
        news.append(f"{symbol}: time exit, sell {position.quantity} ({oms.submit(today, position.strategy_id, broker.time_exit(position))})")
    return news


JOBS = {"evening": evening, "morning": morning, "preclose": preclose}


def track(paper: PaperStore, store: LiveStore) -> pd.DataFrame:
    """Each live entry and exit beside the paper fill of the same order: what the live account paid or got,
    and the slippage against paper (positive is worse for the live account)."""
    fills = store.table("live_fills").set_index("tag")
    orders = paper.table("orders")
    paper_fills = paper.table("fills").dropna(subset=["order_id"]).set_index("order_id")
    rows = []
    for order in orders.itertuples():
        tag = (broker.entry_order if order.side == "buy" else broker.exit_order)(order.key, order.symbol, order.quantity).tag
        if tag not in fills.index:
            continue
        live, paper_price = fills.loc[tag], paper_fills["price"].get(order.id)
        sign = 1 if order.side == "buy" else -1
        rows.append({"session": live["session"], "strategy": order.strategy_id, "symbol": order.symbol, "side": order.side,
                     "live quantity": int(live["quantity"]), "live price": float(live["price"]), "paper price": paper_price,
                     "slippage": sign * (float(live["price"]) / paper_price - 1) if paper_price else None})
    return pd.DataFrame(rows, columns=["session", "strategy", "symbol", "side", "live quantity", "live price",
                                       "paper price", "slippage"])


def check(kite: KiteOrders, store: LiveStore | None = None, symbol: str = "NIFTYBEES",
          detail: bool = True) -> tuple[list[str], list[str]]:
    """Read-only: the account as Kite reports it, and whether each answer has the fields the order system
    relies on. It places, changes and deletes nothing. Returns (what it saw, problems). Without `detail`, what
    it saw is counts only: no funds and no holdings (for Telegram)."""
    seen, problems = [], []
    equity = kite.margins().get("equity", {})
    if detail:
        seen.append(f"Equity funds available: Rs {float(equity.get('net', 0)):,.2f}")
    holdings, positions = kite.holdings(), kite.positions()
    if not {"net", "day"} <= set(positions):
        problems.append("positions: the answer lacks the 'net' and 'day' lists")
    gtts = kite.gtts()
    answers = {"holdings": holdings, "net positions": positions.get("net", []), "orders": kite.orders(), "GTTs": gtts}
    for name, items in answers.items():
        seen.append(f"{name}: {len(items)}")
        problems += [f"{name}: {missing} without '{field}'" for field in RELIED_ON[name]
                     if (missing := sum(1 for item in items if field not in item))]
    legs = [g["orders"][0] for g in gtts if g.get("orders")]
    if any("trigger_values" not in g.get("condition", {}) for g in gtts) or any("quantity" not in leg for leg in legs):
        problems.append("GTTs: a trigger without its trigger values or its order's quantity")
    for h in holdings if detail else []:
        exchange, symbol_held = h.get("exchange", "NSE"), h.get("tradingsymbol")
        seen.append(f"  {exchange}:{symbol_held}: {h.get('quantity', 0)} settled + {h.get('t1_quantity', 0)} T+1 - "
                    f"{h.get('used_quantity', 0)} sold today = {held_quantity(holdings, positions, symbol_held, exchange)} held")
    seen.append(f"{symbol} last price: {kite.ltp([symbol]).get(symbol)}")
    try:  # what a dry run fills at: the session's open, high and low
        quote = kite.ohlc([symbol])[symbol]
        seen.append(f"{symbol} today: open {quote['open']}, high {quote['high']}, low {quote['low']}")
    except (KeyError, TypeError):
        problems.append("quotes: the open, high and low a dry run relies on are missing")
    if store is not None:
        problems += OMS(store, kite, lambda: datetime.now(IST)).reconcile()
    return seen, problems


def status_text(live: Live) -> str:
    """The locks, the live holdings and anything unsettled, from the records alone (no Kite calls)."""
    blocked = locks(live)
    lines = ["Live trading: " + ("LOCKED: " + "; ".join(blocked) if blocked else
                                 f"on for {', '.join(sorted(live_strategies(live)))} with Rs {live.settings.live_capital:,.0f}")]
    if live.kill_switch.engaged:
        lines.append(f"Kill switch ENGAGED: {live.kill_switch.reason}")
    held = live.store.positions()
    lines.append("Live holdings: " + ("; ".join(f"{p.symbol} x{p.quantity} @ {p.entry_price:,.2f}, stop {p.stop_price:,.2f}"
                                                for p in held.values()) or "none"))
    unsettled = [r for r in live.store.orders(("SENDING", "SENT", "TRIGGERED", "UNKNOWN"))]
    lines.append("Unsettled requests: " + ("; ".join(f"{r['symbol']} {r['purpose']} {r['status']}" for r in unsettled) or "none"))
    return "\n".join(lines)


class Console:
    """A dry run's messages, printed (and with --notify sent on, through `then`)."""

    def __init__(self, then=None):
        self.then = then

    def send(self, text: str) -> bool:
        print(html.unescape(re.sub(r"<[^>]+>", "", text)) + "\n")
        return self.then.send(text) if self.then is not None else True


def dry_run_waiting(directory: Path | None = None) -> bool:
    """Whether a dry run's simulated account holds shares or has requests outstanding (its morning job needs prices)."""
    path = (directory or DRY_RUN_DIR) / "live.db"
    if not path.is_file():
        return False
    store = LiveStore(path)
    try:
        return bool(store.positions() or store.orders(("SENDING", "SENT", "TRIGGERED", "UNKNOWN")))
    finally:
        store.close()


def dry_run(settings: Settings, paper: PaperStore, calendar: MarketCalendar, notifier, as_live: set[str],
            capital: float, clock: Callable[[], datetime] | None = None, directory: Path | None = None,
            prices=None) -> Live:
    """The live jobs on a simulated account (trader/execution/simkite.py) in `directory`. Prices come from
    `prices(tradingsymbols)`, by default the real Kite's quotes with today's login; nothing else reaches Kite."""
    clock, directory = clock or (lambda: datetime.now(IST)), directory or DRY_RUN_DIR
    real = []

    def quotes(symbols: list[str]) -> dict[str, dict]:
        if not real:
            real.append(from_session(settings))
        return real[0].ohlc(symbols)

    account = SimKite(directory / "kite.json", prices or quotes, clock, calendar, capital)
    return Live(replace(settings, live_enabled=True, live_capital=capital), paper, LiveStore(directory / "live.db"),
                StrategyRegistry.load(), KillSwitch(directory / "KILL_SWITCH"), calendar, notifier,
                connect=lambda: KiteOrders("dry-run", "dry-run", http=account), clock=clock,
                steps=load_gate_config().live, sources={TRIAL: lambda today, held: trial_orders(today, held, calendar)},
                as_live=frozenset(as_live), dry_run=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Live trading through Zerodha Kite (locked until earned).")
    parser.add_argument("job", choices=["status", "check", "evening", "morning", "preclose", "track"])
    parser.add_argument("--dry-run", action="store_true",
                        help="run on a simulated account in state/live-dryrun/ (real Kite prices; nothing is sent)")
    parser.add_argument("--as-live", action="append", default=[], metavar="STRATEGY",
                        help="dry run only: treat this strategy as live, e.g. B1F (the registry is not changed)")
    parser.add_argument("--capital", type=float, default=DRY_RUN_CAPITAL,
                        help="dry run only: the simulated account's capital in rupees (default %(default)s)")
    parser.add_argument("--notify", action="store_true", help="dry run only: also send its messages on Telegram")
    args = parser.parse_args(argv)
    if not args.dry_run and (args.as_live or args.notify or args.capital != DRY_RUN_CAPITAL):
        parser.error("--as-live, --capital and --notify are for dry runs only")
    if args.dry_run and args.job == "check":
        parser.error("check is already read-only: run it without --dry-run")
    make_console_utf8()
    settings = load_settings()
    configure_logging(secrets=settings.secret_values() + session_secrets(),
                      filename="live-dryrun.log" if args.dry_run else "live.log")
    paper_db, live_db = ROOT / settings.paper_database, ROOT / settings.live_database
    if not paper_db.exists():
        raise SystemExit("No paper records yet: the daily run creates them.")
    paper, calendar = PaperStore(paper_db, settings.paper_starting_capital), load_calendars()["NSE"]
    if args.dry_run:
        live_db = DRY_RUN_DIR / "live.db"
        live = dry_run(settings, paper, calendar, Console(notifier_from_settings(settings) if args.notify else None),
                       set(args.as_live), args.capital)
        unknown = live.as_live - set(live.catalog) - set(live.sources)
        if unknown:
            raise SystemExit(f"No such strategy to treat as live: {', '.join(sorted(unknown))}")
    else:
        # Looking (status, check, track) leaves no live records behind; only a job that may send creates them.
        store = LiveStore(live_db if live_db.exists() or args.job in JOBS else ":memory:")
        live = Live(settings, paper, store, StrategyRegistry.load(), KillSwitch(), calendar, notifier_from_settings(settings),
                    connect=lambda: from_session(settings), steps=load_gate_config().live,
                    sources={TRIAL: lambda today, held: trial_orders(today, held, calendar)})
    if args.job == "status":
        print(status_text(live))
    elif args.job == "check":
        try:
            seen, problems = check(live.connect(), live.store)
        except KiteAuthError as exc:
            raise SystemExit(f"Kite: {exc}") from None
        print("\n".join(seen))
        print("\n".join(f"PROBLEM: {p}" for p in problems) or "Every field the order system relies on is there; "
              "the account holds every share the system believes it holds.")
        raise SystemExit(1 if problems else 0)
    elif args.job == "track":
        print(track(live.paper, live.store).to_string(index=False))
    else:
        raise SystemExit(run(args.job, live, backup_dir=live_db.parent / "backups"))


if __name__ == "__main__":
    main()
