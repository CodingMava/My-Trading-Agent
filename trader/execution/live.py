"""Live trading through Zerodha Kite (Phase 11). The paper engine decides; these jobs carry its decisions out
with real shares, for the strategies that have earned it. Off by default, and locked several ways.

    python -m trader.execution.live status     # the locks, live holdings and unsettled requests (no Kite calls)
    python -m trader.execution.live check      # read-only: the account through Kite, and the fields relied on
    python -m trader.execution.live evening    # after paper trial 1's evening run: orders for the next open
    python -m trader.execution.live morning    # 09:20 and every 15 minutes to 15:00: stops, stale stops deleted, gap exits
    python -m trader.execution.live preclose   # 15:15: time exits
    python -m trader.execution.live track      # live fills beside the paper fills they mirror

    python -m trader.execution.live evening --dry-run --as-live B1F   # the same jobs on a simulated account

Nothing is sent unless every lock is open:
  1. [live] enabled = true and a live capital in config/settings.toml;
  2. a strategy whose status is LIVE_SMALL or LIVE, which the registry grants only on paper-trading evidence
     (the audit's Level 5), or a real-money trial you decided on without that evidence (config/overrides.toml:
     your reason in writing, at most MAX_TRIAL_DAYS long, under a capital cap); only its orders go out, and only
     for NSE stocks (US trades are placed by hand). Its orders come from its paper account
     (trader/execution/sources.py): the paper engine's for the catalogue's strategies, paper trial 1's ledger for
     its bunch, B1F. A strategy that may no longer open trades (its trial ended, its status fell) still has its
     live trades closed: exits and stops, never entries;
  3. today's Kite login, and an account holding every share the system believes it holds (if not, the kill
     switch engages and nothing is sent);
  4. for new entries: the kill switch off, at most [live] max_orders_per_day a day, each order worth at most
     max_order_fraction of the live capital, and every check of the risk engine (config/risk.toml) on the live
     account, which may cut an order but never enlarges it.
Exits and stops go out even with the kill switch engaged: it blocks new trades, never the way out.

Kite takes orders only from the internet address registered with it (KITE_STATIC_IP), and lets you change that
only once a week. On a day this PC's address differs, the jobs run as usual but send nothing: each order comes to
you on Telegram as a step to do in the Kite app, in plain words, and the jobs then find what you did in Kite and
carry on from there (trader/execution/oms.py). Sending by itself always comes first: this is only the fallback.

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
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from trader.config import CONFIG_DIR, ROOT, Settings, load_settings
from trader.core.models import PortfolioState, Position, TradeIntent
from trader.data.kite import KiteAuthError, session_secrets
from trader.execution import broker
from trader.execution.kite_orders import KiteOrders, from_session, held_quantity
from trader.execution.oms import HAND, OMS, LiveStore
from trader.execution.records import from_fills
from trader.execution.simkite import SimKite
from trader.execution.sources import TRIAL, LiveOrder, Source, paper_orders, trial_orders
from trader.execution.store import PaperStore
from trader.gate import LiveThresholds, load_gate_config
from trader.logging_setup import configure_logging, make_console_utf8, redact
from trader.markets.calendar import MarketCalendar, load_calendars
from trader.notify import templates
from trader.notify.telegram import notifier_from_settings
from trader.portfolio.exposure import load_sectors, sector_of
from trader.registry import StrategyRegistry
from trader.risk.engine import RiskEngine
from trader.risk.killswitch import KillSwitch
from trader.risk.limits import RiskLimits, load_limits
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
# The morning job hands over at 15:00, so it never finds a stop the pre-close job has just deleted.
WINDOWS = {"evening": (time(16, 0), time(23, 59)), "morning": (time(9, 15), time(15, 0)),
           "preclose": (time(15, 0), time(15, 28))}
# The scheduled morning job repeats (scripts/register_tasks.ps1), so a stop missed for want of a login goes in
# soon after the login; each kind of failure is reported once a day and its repeats only logged.
RETRIES = {"morning": "The scheduled morning job tries again every 15 minutes until 15:00; repeats of this are only logged today."}
OVERRIDES_FILE = CONFIG_DIR / "overrides.toml"
MAX_TRIAL_DAYS = 92  # a real-money trial is decided for about three months at most, then renewed in writing or ended
NEVER_TRADE_FILE = CONFIG_DIR / "never_trade.toml"  # git-ignored: the stocks you hold yourself
# Two independent services that answer with the caller's internet address as plain text.
ADDRESS_SERVICES = ("https://api.ipify.org", "https://checkip.amazonaws.com")
ADDRESS = re.compile(r"[0-9]{1,3}(\.[0-9]{1,3}){3}|[0-9a-fA-F:]*:[0-9a-fA-F:]+")


def public_ip(http=requests, timeout: float = 10) -> str | None:
    """This PC's address on the internet, as the first service that answers sees it; None if none does."""
    for url in ADDRESS_SERVICES:
        try:
            answer = http.get(url, timeout=timeout)
        except requests.RequestException:
            continue
        text = answer.text.strip()
        if answer.status_code == 200 and ADDRESS.fullmatch(text):
            return text
    return None


def load_never_trade(path: Path = NEVER_TRADE_FILE) -> frozenset[str]:
    """The stocks you hold yourself (config/never_trade.toml), named as paper trading names them: never bought live."""
    if not path.is_file():
        return frozenset()
    with open(path, "rb") as fh:
        names = [str(stock).strip().upper() for stock in tomllib.load(fh).get("stocks", [])]
    return frozenset(name.removesuffix(".NS") + ".NS" for name in names if name)


@dataclass(frozen=True)
class Override:
    """A real-money trial you decided on without the evidence the gate asks for (config/overrides.toml): small,
    capped and time-limited. It is not evidence: no strategy's status changes, every risk limit still applies,
    and the live capital can't grow under it. `problem` says why it is invalid (empty when it isn't)."""
    strategy_id: str
    decided: date | None
    until: date | None
    max_capital: float
    reason: str
    problem: str = ""


def load_overrides(path: Path = OVERRIDES_FILE) -> tuple[Override, ...]:
    """config/overrides.toml's real-money trials. One that is open-ended, uncapped or unexplained is kept with its
    problem, and can't trade: the live jobs say why instead."""
    if not path.is_file():
        return ()
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    found = []
    for strategy_id, entry in raw.items():
        decided, until, reason = entry.get("decided"), entry.get("until"), str(entry.get("reason", "")).strip()
        try:
            cap = float(entry.get("max_capital", 0))
        except (TypeError, ValueError):
            cap = 0.0
        dated = isinstance(decided, date) and isinstance(until, date)
        problem = ("decided and until must be dates (YYYY-MM-DD)" if not dated
                   else f"until must be on or after decided, and at most {MAX_TRIAL_DAYS} days later"
                   if not 0 <= (until - decided).days <= MAX_TRIAL_DAYS
                   else "max_capital must be an amount above zero" if not cap > 0
                   else "reason must say in your own words why it trades without the evidence" if len(reason) < 20 else "")
        found.append(Override(strategy_id, decided if dated else None, until if dated else None, cap, reason,
                              f"config/overrides.toml [{strategy_id}]: {problem}" if problem else ""))
    return tuple(found)


def override_problem(override: Override, today: date, known: set[str], capital: float) -> str:
    """Why a real-money trial can't open new trades today; empty when it can."""
    return (override.problem
            or (f"{override.strategy_id} has no paper account for the live jobs to follow" if override.strategy_id not in known
                else f"the real-money trial of {override.strategy_id} starts on {override.decided}" if today < override.decided
                else f"the real-money trial of {override.strategy_id} ended on {override.until}" if today > override.until
                else f"[live] capital Rs {capital:,.0f} is above the real-money trial's cap of Rs {override.max_capital:,.0f}"
                if capital > override.max_capital else ""))


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
    limits: RiskLimits = field(default_factory=load_limits)  # config/risk.toml: every live entry is checked against it
    sectors: dict[str, str] = field(default_factory=load_sectors)
    overrides: tuple[Override, ...] = ()  # real-money trials you decided on (config/overrides.toml); never a dry run's
    never_trade: frozenset[str] = frozenset()  # the stocks you hold yourself (config/never_trade.toml): never bought
    address: Callable[[], str | None] | None = None  # this PC's internet address (public_ip); None: not checked

    def __post_init__(self):
        if self.as_live and not self.dry_run:
            raise ValueError("only a dry run may treat a strategy as live")
        if self.overrides and self.dry_run:
            raise ValueError("a dry run treats strategies as live with --as-live, not with a real-money override")


def known_strategies(live: Live) -> set[str]:
    return set(live.catalog) | set(live.sources)


def trials(live: Live) -> dict[str, Override]:
    """The real-money trials that may open trades today."""
    today, known = live.clock().date(), known_strategies(live)
    return {o.strategy_id: o for o in live.overrides
            if not override_problem(o, today, known, live.settings.live_capital)}


def live_strategies(live: Live) -> set[str]:
    """The strategies that may open live trades: LIVE_SMALL or LIVE on evidence, a dry run's, and real-money trials."""
    known = known_strategies(live)
    return ({record.id for record in live.registry.live_strategies() if record.id in known} | (live.as_live & known)
            | set(trials(live)))


def managed_strategies(live: Live) -> set[str]:
    """The strategies whose live trades the jobs carry on: those that may open trades, and any whose holdings are
    still live after it lost that (a trial that ended, a strategy whose status fell): exits, never entries."""
    return live_strategies(live) | ({p.strategy_id for p in live.store.positions().values()} & known_strategies(live))


def say(live: Live, title: str, lines: list[str]) -> None:
    live.notifier.send(templates.live_update(title=title, lines=lines, dry_run=live.dry_run, trial=bool(live.overrides)))


def hand_step(request: broker.KiteRequest) -> str:
    """One order the bot couldn't send, as what to tap in the Kite app."""
    sid, p = request.symbol.removesuffix(".NS"), request.params
    if request.purpose == "entry":
        return (f"BUY {p['quantity']} shares of {sid}\nKite app: {sid} > Buy > AMO > Market > quantity "
                f"{p['quantity']} > Buy. It buys at tomorrow's 9:15 open. Do it tonight, or skip it.")
    if request.purpose == "exit":
        return (f"SELL {p['quantity']} shares of {sid}\nKite app: {sid} > Sell > AMO > Market > quantity "
                f"{p['quantity']} > Sell. It sells at tomorrow's 9:15 open. Please do it tonight.")
    if request.purpose == "stop":
        leg, trigger = p["orders"][0], p["condition"]["trigger_values"][0]
        return (f"SET A STOP-LOSS on {sid}\nKite app: {sid} > Create GTT > Single > Sell > trigger price "
                f"{templates.rupees(trigger)} > quantity {leg['quantity']} > price {templates.rupees(leg['price'])} > "
                f"Create. It sells your {leg['quantity']} shares if the price falls to {templates.rupees(trigger)}.")
    if request.purpose == "cancel stop":
        return f"DELETE the stop-loss of {sid}\nKite app: Orders > GTT > {sid} > Delete."
    if request.purpose == "gap exit":
        return (f"SELL {sid} NOW\nIt fell below its stop-loss, but the stop-loss sell is stuck. Kite app: Orders > "
                f"the open SELL of {sid} > Modify > Market > Modify.")
    why = "its time is up" if request.purpose == "time exit" else "it is already below its stop-loss"
    return (f"SELL {p['quantity']} shares of {sid} NOW, before 3:30 pm ({why})\nKite app: {sid} > Sell > Market > "
            f"quantity {p['quantity']} > Sell.")


def hand_over(live: Live, requests: list[broker.KiteRequest]) -> None:
    """Tell you the orders to do by hand today, in order (a stop-loss is deleted before its shares are sold)."""
    live.notifier.send(templates.by_hand([f"{n}. {hand_step(r)}" for n, r in enumerate(requests, 1)]))


def address_moved(live: Live) -> str:
    """Why nothing may be sent from this PC's internet address (empty when it may, or when it can't be told): Kite
    takes orders only from the address registered in its developer console (KITE_STATIC_IP in .env)."""
    registered = live.settings.kite_static_ip
    seen = live.address() if live.address is not None and registered else None
    if seen is None or seen == registered:
        return ""
    return (f"This PC's internet address is now {seen}, but Kite has {registered} registered, so Kite won't take "
            "orders from me. Until it's fixed, I send you each order to do by hand. To fix it, send /myip.")


def failed(live: Live, job: str, today: date, kind: str, detail: str, trace: bool = False) -> int:
    """A job that couldn't finish: reported the first time today for this kind of failure, logged every time."""
    log.error("Live %s failed: %s", job, detail, exc_info=trace)
    if live.store.first_notice(today, f"{job} {kind}"):
        say(live, f"Live {job} failed", [detail, *([RETRIES[job]] if job in RETRIES else [])])
    return 1


def locks(live: Live) -> list[str]:
    """Why nothing may be sent; empty when the account may trade."""
    reasons = []
    if not live.settings.live_enabled:
        reasons.append("live trading is off ([live] enabled = false in config/settings.toml)")
    if live.settings.live_capital <= 0:
        reasons.append("no live capital is set ([live] capital)")
    if not managed_strategies(live):
        reasons.append("no strategy has earned live money (LIVE_SMALL or LIVE on paper-trading evidence)")
        today, known = live.clock().date(), known_strategies(live)
        reasons += [override_problem(o, today, known, live.settings.live_capital) for o in live.overrides]
    return reasons


def run(job: str, live: Live, backup_dir=None) -> int:
    """One job. Returns 0 when done (or there was nothing to do), 1 when it failed, 2 when reconciliation
    stopped it."""
    blocked = locks(live)
    if blocked:
        log.info("Live %s: nothing sent: %s", job, "; ".join(blocked))
        return 0
    today, oms = live.clock().date(), None
    try:
        moved = address_moved(live)  # Kite would refuse every order, so each is handed to you instead
        oms = OMS(live.store, live.connect(), live.clock, by_hand=moved, calendar=live.calendar)
        news = oms.refresh(today)
        problems = oms.reconcile()
        if problems:  # told when it engages the kill switch, and once a day while the switch stays engaged
            first, engaging = live.store.first_notice(today, f"{job} reconciliation"), not live.kill_switch.engaged
            live.kill_switch.engage("live reconciliation failed: " + problems[0])
            if first or engaging:
                say(live, "Reconciliation failed: nothing was sent", [
                    *problems, "The kill switch is engaged. Compare the account with python -m trader.execution.live "
                    "status and find out why before releasing it."])
            return 2
        start, end = WINDOWS[job]
        now = live.clock().time()
        news += (JOBS[job](live, oms, today) if start <= now <= end else
                 [f"Nothing sent: the {job} job runs between {start:%H:%M} and {end:%H:%M} IST, not at {now:%H:%M}."])
        if moved and live.store.first_notice(today, "address"):  # once a day, though the jobs repeat
            news.insert(0, moved)
        if news:
            say(live, f"Live {job}", news)
    except KiteAuthError as exc:
        return failed(live, job, today, "login", str(exc))
    except Exception as exc:  # recorded and reported, never swallowed
        detail = redact(f"{type(exc).__name__}: {exc}", live.settings.secret_values() + session_secrets())[:500]
        return failed(live, job, today, "error", detail, trace=True)
    finally:  # even when the job failed after it: what was handed to you isn't handed again today
        if oms is not None and oms.handed:
            hand_over(live, oms.handed)
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
    allowed, managed, held = live_strategies(live), managed_strategies(live), live.store.positions()
    batches = []
    if managed & set(live.catalog):
        batches.append(paper_orders(live.paper, today, managed, live.catalog))
    for strategy_id in sorted(managed & set(live.sources)):
        batches.append(live.sources[strategy_id](today, held))
    notes = [note for _, found in batches for note in found]
    if all(orders is None for orders, _ in batches):
        return notes
    capital, news = capital_for_today(live, today)
    news += notes
    state, risk = live_account(live, oms, today, capital, news), RiskEngine(live.limits, live.kill_switch, account="live")
    entries = sum(1 for row in live.store.orders() if row["session"] == today.isoformat() and row["purpose"] in ENTRY_PURPOSES)
    for order in (order for orders, _ in batches for order in orders or ()):
        if order.side == "sell":
            position = held.get(order.symbol)
            if position is None or position.strategy_id != order.strategy_id:
                continue  # nothing live to sell
            request = broker.exit_order(order.key, order.symbol, position.quantity)
            news.append(f"{order.symbol}: sell {position.quantity} at the open ({oms.submit(today, order.strategy_id, request)})")
            continue
        refused, quantity = entry_refusal(live, order, capital, held, entries, allowed)
        if not refused:  # the risk engine on the live account: it may make the order smaller, never bigger
            sector = sector_of(order.symbol, live.sectors)
            decision = risk.review(TradeIntent(order.strategy_id, order.symbol, today, order.reference_price,
                                               order.stop_distance, sector), state, quantity, order.returns)
            refused, quantity = ("" if decision.approved else decision.reason), decision.quantity
        if refused:
            news.append(f"{order.symbol}: entry not sent: {refused}")
            continue
        request = broker.entry_order(order.key, order.symbol, quantity)
        status = oms.submit(today, order.strategy_id, request, order.stop_distance, order.max_hold_days)
        entries += 1
        news.append(f"{order.symbol}: buy {quantity} at the open ({status})")
        # the rest of the evening's entries see it as held, whatever Kite answered (the stricter view)
        state.positions[order.symbol] = Position(order.strategy_id, order.symbol, quantity, order.reference_price,
                                                 order.reference_price * (1 - order.stop_distance), today, sector,
                                                 last_price=order.reference_price)
        state.cash -= quantity * order.reference_price
    return news


def live_account(live: Live, oms: OMS, today: date, capital: float, news: list[str]) -> PortfolioState:
    """The live account as the risk engine sees it: the capital step plus what the live trades made since it began,
    the holdings marked at Kite's last prices. Each evening's equity is recorded: its best since the step began is
    the drawdown limit's peak, and the previous evening's is where the daily-loss limit measures from."""
    since = date.fromisoformat(live.store.capital_steps()[-1]["session"])
    held = live.store.positions()
    prices = oms.kite.ltp([symbol.removesuffix(".NS") for symbol in held])
    positions = {}
    for symbol, position in held.items():
        price = prices.get(symbol.removesuffix(".NS"))
        if price is None:
            news.append(f"{symbol}: no price from Kite, so the risk checks value it at its entry price")
        positions[symbol] = replace(position, sector=sector_of(symbol, live.sectors), last_price=price)
    trips = from_fills(live.store.table("live_fills"))
    made = float(trips.loc[[day >= since for day in trips["sell_date"]], "gain"].sum())
    made += sum(p.market_value - p.quantity * p.entry_price for p in positions.values())
    state = PortfolioState(cash=capital + made - sum(p.market_value for p in positions.values()), positions=positions)
    live.store.record_equity(today, state.equity)
    history = live.store.equity_history(since)
    earlier = [equity for session, equity in history if session < today.isoformat()]
    state.peak_equity = max([capital, state.equity, *(equity for _, equity in history)])
    state.day_start_equity = earlier[-1] if earlier else state.equity
    return state


def entry_refusal(live: Live, order: LiveOrder, capital: float, held: dict, entries: int,
                  allowed: set[str]) -> tuple[str, int]:
    """Why an entry isn't sent (empty when it is), and its live quantity: the paper order scaled to the live capital."""
    quantity = int(order.paper_quantity * capital / order.paper_capital + 1e-9)
    refused = (exits_only(live, order.strategy_id) if order.strategy_id not in allowed
               else "you hold it yourself, so the bot never buys it (config/never_trade.toml)"
               if order.symbol in live.never_trade
               else "the kill switch is engaged" if live.kill_switch.engaged
               else "the live account already holds it" if order.symbol in held
               else f"{order.paper_quantity:.4g} paper shares scale to none (Rs {order.reference_price:,.2f} a share)"
               if quantity < 1
               else f"worth more than {live.settings.live_max_order_fraction:.0%} of the live capital"
               if quantity * order.reference_price > live.settings.live_max_order_fraction * capital
               else f"the day's limit of {live.settings.live_max_orders_per_day} entries is reached"
               if entries >= live.settings.live_max_orders_per_day else "")
    return refused, quantity


def exits_only(live: Live, strategy_id: str) -> str:
    """Why a strategy whose live trades are carried on may not open new ones."""
    today, known = live.clock().date(), known_strategies(live)
    why = [override_problem(o, today, known, live.settings.live_capital) for o in live.overrides if o.strategy_id == strategy_id]
    return f"{why[0] if why else strategy_id + ' is no longer LIVE_SMALL or LIVE'}: its live trades only exit"


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
        if stop is None or stop["status"] in ("SENDING", "UNKNOWN", HAND):  # not placed, not found, or not done by hand
            request = (broker.stop_exit(position) if price <= broker.to_tick(position.stop_price)
                       else broker.stop_order(position, last_price=price))
            status = oms.submit(today, position.strategy_id, request)
            if status != HAND or request in oms.handed:  # a repeat of the job doesn't say it again
                news.append(f"{symbol}: {request.purpose} ({status})")
        elif stop["status"] == "TRIGGERED" and price < broker.stop_limit(position.stop_price):
            news.append(f"{symbol}: gap exit ({oms.submit(today, position.strategy_id, broker.gap_exit(position))})")
        elif stop["status"] not in ("SENT", "TRIGGERED") and live.store.first_notice(today, f"no stop {symbol}"):
            # rejected, deleted, or it sold only part: told once a day, though the job repeats
            news.append(f"{symbol} has no stop at Kite ({stop['status'].lower()}: {stop['detail']}). Place one by hand.")
    current = {broker.stop_order(position).tag for position in held.values()}
    for row in live.store.orders(("SENT",)):
        if row["purpose"] == "stop" and row["tag"] not in current:  # its holding was sold at the open
            request = broker.cancel_stop_tagged(row["symbol"], row["tag"], broker.AFTER_OPEN)
            if (deleted := live.store.order(request.tag)) is None or deleted["status"] != "DONE":  # not said twice
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
            if deleted not in ("DONE", HAND):  # handed to you: you delete it, then sell
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
    blocked, opening = locks(live), sorted(live_strategies(live))
    closing = sorted(managed_strategies(live) - set(opening))
    lines = ["Live trading: " + ("LOCKED: " + "; ".join(blocked) if blocked else
                                 "on" + (f" for {', '.join(opening)}" if opening else "")
                                 + (f", exits only for {', '.join(closing)}" if closing else "")
                                 + f" with Rs {live.settings.live_capital:,.0f}")]
    in_force = trials(live)
    for o in live.overrides:
        lines.append(f"Real-money trial of {o.strategy_id}, decided {o.decided}, until {o.until}, at most "
                     f"Rs {o.max_capital:,.0f}: NOT approved by evidence; you chose to trade it (config/overrides.toml)"
                     if o.strategy_id in in_force else
                     f"Real-money trial not opening trades: {override_problem(o, live.clock().date(), known_strategies(live), live.settings.live_capital)}")
    if live.never_trade:
        lines.append("Never bought (you hold them yourself): "
                     + ", ".join(sorted(symbol.removesuffix(".NS") for symbol in live.never_trade)))
    if live.kill_switch.engaged:
        lines.append(f"Kill switch ENGAGED: {live.kill_switch.reason}")
    held = live.store.positions()
    lines.append("Live holdings: " + ("; ".join(f"{p.symbol} x{p.quantity} @ {p.entry_price:,.2f}, stop {p.stop_price:,.2f}"
                                                for p in held.values()) or "none"))
    unsettled = [r for r in live.store.orders(("SENDING", "SENT", "TRIGGERED", "UNKNOWN", HAND))]
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
            prices=None, never_trade: frozenset[str] = frozenset()) -> Live:
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
                as_live=frozenset(as_live), dry_run=True, never_trade=never_trade)


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
                       set(args.as_live), args.capital, never_trade=load_never_trade())
        unknown = live.as_live - set(live.catalog) - set(live.sources)
        if unknown:
            raise SystemExit(f"No such strategy to treat as live: {', '.join(sorted(unknown))}")
    else:
        # Looking (status, check, track) leaves no live records behind; only a job that may send creates them.
        store = LiveStore(live_db if live_db.exists() or args.job in JOBS else ":memory:")
        live = Live(settings, paper, store, StrategyRegistry.load(), KillSwitch(), calendar, notifier_from_settings(settings),
                    connect=lambda: from_session(settings), steps=load_gate_config().live,
                    sources={TRIAL: lambda today, held: trial_orders(today, held, calendar)}, overrides=load_overrides(),
                    never_trade=load_never_trade(), address=public_ip)
    if args.job == "status":
        print(status_text(live))
    elif args.job == "check":
        try:
            seen, problems = check(live.connect(), live.store)
        except KiteAuthError as exc:
            raise SystemExit(f"Kite: {exc}") from None
        problems += [moved] if (moved := address_moved(live)) else []
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
